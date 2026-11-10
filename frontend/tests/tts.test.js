import assert from 'node:assert/strict'
import test from 'node:test'

import apiClient from '../src/api/client.js'
import { synthesizeVoiceSpeech } from '../src/api/ai.js'
import { TTS_LANGUAGES } from '../src/lib/constants.js'
import {
  buildConfirmationSpeech,
  describeSpeechError,
  ensureWavBlob,
  speechButtonLabel,
  ttsLanguageFor,
} from '../src/lib/tts.js'

test('TTS exposes only the languages confirmed by the backend', () => {
  assert.deepEqual(
    TTS_LANGUAGES.map((language) => language.value),
    ['en-IN', 'hi-IN', 'mr-IN'],
  )
})

test('TTS language mapping mirrors the backend aliases', () => {
  const expected = {
    en: 'en-IN',
    'en-in': 'en-IN',
    english: 'en-IN',
    hi: 'hi-IN',
    'hi-in': 'hi-IN',
    hindi: 'hi-IN',
    mr: 'mr-IN',
    'mr-in': 'mr-IN',
    marathi: 'mr-IN',
  }

  for (const [alias, value] of Object.entries(expected)) {
    assert.equal(ttsLanguageFor(alias), value, alias)
    assert.equal(ttsLanguageFor(alias.toUpperCase()), value, alias)
  }

  for (const language of TTS_LANGUAGES) {
    assert.equal(ttsLanguageFor(language.value), language.value)
  }
})

test('TTS rejects languages that are not confirmed by the provider', () => {
  for (const language of [
    'gu',
    'gu-IN',
    'ta',
    'ta-IN',
    'te',
    'te-IN',
    'kn',
    'kn-IN',
    'bn',
    'bn-IN',
    'ml-IN',
    'pa-IN',
    'indic-auto',
    '',
    null,
    undefined,
  ]) {
    assert.equal(ttsLanguageFor(language), null, String(language))
  }
})

test('confirmation text uses the exact backend examples', () => {
  assert.deepEqual(buildConfirmationSpeech('en'), {
    text: 'Your complaint has been registered successfully.',
    language: 'en-IN',
  })
  assert.deepEqual(buildConfirmationSpeech('hi'), {
    text: 'आपकी शिकायत सफलतापूर्वक दर्ज हो गई है।',
    language: 'hi-IN',
  })
  assert.deepEqual(buildConfirmationSpeech('mr'), {
    text: 'आपली तक्रार यशस्वीरित्या नोंदवली गेली आहे.',
    language: 'mr-IN',
  })
  assert.equal(buildConfirmationSpeech('gu'), null)
})

test('WAV blobs are normalized to audio/wav without losing bytes', async () => {
  const bytes = new Uint8Array([82, 73, 70, 70, 1, 2, 3])

  const alreadyWav = new Blob([bytes], { type: 'audio/wav' })
  assert.equal(ensureWavBlob(alreadyWav), alreadyWav)

  const octetStream = new Blob([bytes], { type: 'application/octet-stream' })
  const normalized = ensureWavBlob(octetStream)
  assert.equal(normalized.type, 'audio/wav')
  assert.deepEqual(new Uint8Array(await normalized.arrayBuffer()), bytes)

  const fromBuffer = ensureWavBlob(bytes.buffer)
  assert.equal(fromBuffer.type, 'audio/wav')
  assert.deepEqual(new Uint8Array(await fromBuffer.arrayBuffer()), bytes)
})

test('playback button labels reflect loading, playing, error and replay states', () => {
  assert.equal(speechButtonLabel('idle', false), 'Play confirmation')
  assert.equal(speechButtonLabel('loading', false), 'Preparing audio…')
  assert.equal(speechButtonLabel('playing', false), 'Playing…')
  assert.equal(speechButtonLabel('error', false), 'Try again')
  assert.equal(speechButtonLabel('idle', true), 'Replay confirmation')
  assert.equal(speechButtonLabel('error', true), 'Replay confirmation')
  assert.equal(speechButtonLabel('playing', true), 'Playing…')
})

test('speech errors map backend failures to non-blocking guidance', () => {
  const cases = [
    [422, 'Confirmation audio unavailable'],
    [501, 'Voice playback not configured'],
    [502, 'Voice service rejected the request'],
    [503, 'Voice service unavailable'],
    [504, 'Voice service timed out'],
  ]

  for (const [status, title] of cases) {
    const description = describeSpeechError({ status })
    assert.equal(description.title, title)
    assert.match(description.guidance, /report is still submitted/i)
    assert.match(description.guidance, /tracking ID/i)
  }

  const timeout = describeSpeechError({ code: 'ECONNABORTED' })
  assert.equal(timeout.title, 'Voice service timed out')
  assert.match(timeout.guidance, /tracking ID/i)

  const network = describeSpeechError(new Error('Network Error'))
  assert.equal(network.title, 'Could not reach the voice service')
  assert.match(network.guidance, /tracking ID/i)

  const unexpected = describeSpeechError({ status: 500 })
  assert.equal(unexpected.title, 'Could not prepare confirmation audio')
  assert.match(unexpected.guidance, /tracking ID/i)
})

test('voice speech helper posts a blob request to /voice/speak', async () => {
  const originalPost = apiClient.post
  const calls = []
  const bytes = new Uint8Array([82, 73, 70, 70, 1, 2, 3])

  apiClient.post = async (...args) => {
    calls.push(args)
    return { data: new Blob([bytes], { type: 'audio/wav' }) }
  }

  try {
    const blob = await synthesizeVoiceSpeech('Confirmation', 'hi')

    assert.equal(calls.length, 1)
    assert.equal(calls[0][0], '/voice/speak')
    assert.deepEqual(calls[0][1], {
      text: 'Confirmation',
      language: 'hi-IN',
    })
    assert.equal(calls[0][2].responseType, 'blob')
    assert.equal(calls[0][2].timeout, 70000)
    assert.equal(blob.type, 'audio/wav')
    assert.deepEqual(new Uint8Array(await blob.arrayBuffer()), bytes)
  } finally {
    apiClient.post = originalPost
  }
})

test('voice speech helper forwards the abort signal and custom timeout', async () => {
  const originalPost = apiClient.post
  const calls = []
  const controller = new AbortController()

  apiClient.post = async (...args) => {
    calls.push(args)
    return { data: new Blob([new Uint8Array([1])], { type: 'audio/wav' }) }
  }

  try {
    await synthesizeVoiceSpeech('Confirmation', 'en-IN', {
      signal: controller.signal,
      timeout: 1234,
    })

    assert.equal(calls[0][2].signal, controller.signal)
    assert.equal(calls[0][2].timeout, 1234)
  } finally {
    apiClient.post = originalPost
  }
})

test('voice speech helper rejects unsupported languages before requesting', async () => {
  const originalPost = apiClient.post
  let called = false

  apiClient.post = async () => {
    called = true
    return { data: new Blob() }
  }

  try {
    await assert.rejects(
      () => synthesizeVoiceSpeech('Confirmation', 'gu'),
      (error) => error.status === 422,
    )
    assert.equal(called, false)
  } finally {
    apiClient.post = originalPost
  }
})
