import assert from 'node:assert/strict'
import test from 'node:test'

import { VOICE_LANGUAGES } from '../src/lib/constants.js'
import {
  buildIncidentPayload,
  validateIncidentForm,
} from '../src/lib/incidentForm.js'
import {
  MAX_AUDIO_BYTES,
  MAX_RECORDING_SECONDS,
  appendTranscript,
  applyVoiceTranscript,
  describeMicrophoneError,
  describeVoiceTranscriptionError,
  formatRecordingDuration,
  validateAudioFile,
  voiceLanguageToHint,
} from '../src/lib/voice.js'

test('voice language options match the backend Prisma codes', () => {
  assert.deepEqual(
    VOICE_LANGUAGES.map((language) => language.value),
    [
      'indic-auto',
      'bn-IN',
      'en-IN',
      'gu-IN',
      'hi-IN',
      'kn-IN',
      'ml-IN',
      'mr-IN',
      'pa-IN',
      'ta-IN',
      'te-IN',
    ],
  )
})

test('recording limits match the backend contract', () => {
  assert.equal(MAX_RECORDING_SECONDS, 30)
  assert.equal(MAX_AUDIO_BYTES, 10 * 1024 * 1024)
})

test('recording duration is displayed as minutes and seconds', () => {
  assert.equal(formatRecordingDuration(0), '0:00')
  assert.equal(formatRecordingDuration(5), '0:05')
  assert.equal(formatRecordingDuration(30), '0:30')
  assert.equal(formatRecordingDuration(65), '1:05')
})

test('transcript is appended without deleting existing description text', () => {
  const description = 'Existing description with a landmark.'
  const result = appendTranscript(description, '  Voice transcript.  ')

  assert.ok(result.startsWith(description))
  assert.match(result, /Voice transcript\.$/)
  assert.equal(result, `${description}\n\nVoice transcript.`)
})

test('transcript insertion keeps an empty description usable', () => {
  assert.equal(appendTranscript('', 'Voice transcript.'), 'Voice transcript.')
  assert.equal(appendTranscript('   ', 'Voice transcript.'), 'Voice transcript.')
})

test('empty transcripts do not change the description', () => {
  assert.equal(appendTranscript('Existing text.', ''), 'Existing text.')
  assert.equal(appendTranscript('Existing text.', '   '), 'Existing text.')
})

test('transcript insertion respects the description limit', () => {
  const existing = 'Keep this text.'
  const result = appendTranscript(existing, 'x'.repeat(100), 20)

  assert.equal(result.length, 20)
  assert.ok(result.startsWith(existing))
})

test('voice transcript insertion produces a submittable description without language', () => {
  const description = appendTranscript(
    'Pothole near the school gate.',
    'It is getting bigger after the rain.',
  )
  const form = {
    category: 'pothole',
    description,
    language: 'hi',
    latitude: '',
    longitude: '',
  }

  assert.deepEqual(validateIncidentForm(form), {})
  const payload = buildIncidentPayload(form)

  assert.match(payload.description, /Pothole near the school gate\./)
  assert.match(payload.description, /It is getting bigger after the rain\./)
  assert.equal('language' in payload, false)
})

test('voice transcript changes the description so classification runs again', () => {
  const form = {
    description: 'Existing description.',
    language: 'en',
  }
  const next = applyVoiceTranscript(form, 'Voice transcript.', 'hi-IN')

  assert.equal(next.description, 'Existing description.\n\nVoice transcript.')
  assert.notEqual(next.description, form.description)
  assert.equal(next.language, 'hi')
})

test('unsupported detected languages leave the triage language hint unchanged', () => {
  const form = {
    description: 'Existing description.',
    language: 'en',
  }
  const next = applyVoiceTranscript(form, 'Malayalam transcript.', 'ml-IN')

  assert.equal(next.description, 'Existing description.\n\nMalayalam transcript.')
  assert.equal(next.language, 'en')
})

test('audio file validation accepts supported files under 10 MB', () => {
  assert.equal(
    validateAudioFile({ name: 'clip.wav', size: 1024, type: 'audio/wav' }),
    null,
  )
  assert.equal(
    validateAudioFile({ name: 'clip.m4a', size: 1024, type: 'audio/mp4' }),
    null,
  )
})

test('audio file validation rejects oversized and unsupported files', () => {
  assert.match(
    validateAudioFile({
      name: 'clip.wav',
      size: MAX_AUDIO_BYTES + 1,
      type: 'audio/wav',
    }),
    /too large/i,
  )
  assert.match(
    validateAudioFile({ name: 'clip.webm', size: 1024, type: 'audio/webm' }),
    /Unsupported audio format/,
  )
  assert.match(
    validateAudioFile({ name: 'clip.wav', size: 0, type: 'audio/wav' }),
    /empty/i,
  )
})

test('transcription errors are distinct for 422, 501, 502, 503 and 504', () => {
  const statuses = [422, 501, 502, 503, 504]
  const titles = statuses.map((status) => {
    const error = describeVoiceTranscriptionError({
      status,
      message: `Status ${status}`,
    })
    assert.match(error.guidance, /manual|type|try/i)
    return error.title
  })

  assert.deepEqual(titles, [
    'Audio could not be transcribed',
    'Voice transcription not configured',
    'Speech service rejected the request',
    'Speech service unavailable',
    'Speech service timed out',
  ])
  assert.equal(new Set(titles).size, statuses.length)
})

test('transcription 413 and 415 errors explain file limits and formats', () => {
  const tooLarge = describeVoiceTranscriptionError({
    status: 413,
    message: 'Audio file is too large.',
  })
  const unsupported = describeVoiceTranscriptionError({
    status: 415,
    message: 'Unsupported audio format.',
  })

  assert.equal(tooLarge.title, 'Audio file too large')
  assert.match(tooLarge.guidance, /10 MB/)
  assert.equal(unsupported.title, 'Unsupported audio format')
  assert.match(unsupported.guidance, /WAV, MP3, OGG, FLAC, AAC or M4A/)
})

test('network and timeout failures leave manual submission available', () => {
  const network = describeVoiceTranscriptionError({
    status: undefined,
    message: 'Network Error',
  })
  const timeout = describeVoiceTranscriptionError({
    status: undefined,
    code: 'ECONNABORTED',
    message: 'timeout exceeded',
  })

  assert.equal(network.title, 'Could not reach the speech service')
  assert.match(network.guidance, /type the description manually/i)
  assert.equal(timeout.title, 'Speech service timed out')
  assert.match(timeout.guidance, /Manual submission is still available/i)
})

test('microphone errors explain permission and device failures', () => {
  assert.equal(
    describeMicrophoneError({ name: 'NotAllowedError' }).title,
    'Microphone permission denied',
  )
  assert.equal(
    describeMicrophoneError({ name: 'NotFoundError' }).title,
    'No microphone found',
  )
  assert.equal(
    describeMicrophoneError({ name: 'NotReadableError' }).title,
    'Microphone unavailable',
  )
  assert.equal(
    describeMicrophoneError({ name: 'UnknownError' }).title,
    'Could not start recording',
  )
})

test('detected voice language maps to the triage language hint when supported', () => {
  assert.equal(voiceLanguageToHint('hi-IN'), 'hi')
  assert.equal(voiceLanguageToHint('en-IN'), 'en')
  assert.equal(voiceLanguageToHint('ml-IN'), null)
  assert.equal(voiceLanguageToHint('indic-auto'), null)
  assert.equal(voiceLanguageToHint(undefined), null)
})
