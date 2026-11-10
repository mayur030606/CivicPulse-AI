/**
 * Pure helpers for voice-note recording, upload validation, transcript
 * insertion and user-facing error messages.
 *
 * The browser component owns MediaRecorder and microphone cleanup. Keeping the
 * validation and message mapping here makes the important behavior testable
 * without a DOM or a running backend.
 */

export const MAX_RECORDING_SECONDS = 30
export const MAX_AUDIO_BYTES = 10 * 1024 * 1024
export const MAX_DESCRIPTION_LENGTH = 4000

export const SUPPORTED_AUDIO_EXTENSIONS = [
  '.wav',
  '.mp3',
  '.ogg',
  '.flac',
  '.aac',
  '.m4a',
]

export const SUPPORTED_AUDIO_ACCEPT = [
  ...SUPPORTED_AUDIO_EXTENSIONS,
  'audio/wav',
  'audio/wave',
  'audio/x-wav',
  'audio/mpeg',
  'audio/mp3',
  'audio/ogg',
  'audio/flac',
  'audio/x-flac',
  'audio/aac',
  'audio/x-aac',
  'audio/mp4',
  'audio/m4a',
  'audio/x-m4a',
].join(',')

const VOICE_LANGUAGE_TO_HINT = {
  'bn-IN': 'bn',
  'en-IN': 'en',
  'gu-IN': 'gu',
  'hi-IN': 'hi',
  'kn-IN': 'kn',
  'mr-IN': 'mr',
  'ta-IN': 'ta',
  'te-IN': 'te',
}

export function formatRecordingDuration(seconds) {
  const safeSeconds = Math.max(0, Math.floor(Number(seconds) || 0))
  const minutes = Math.floor(safeSeconds / 60)
  const remainder = safeSeconds % 60
  return `${minutes}:${String(remainder).padStart(2, '0')}`
}

/**
 * Append a transcript without removing anything the citizen already typed.
 * The description limit is respected by truncating only the incoming tail.
 */
export function appendTranscript(
  description,
  transcript,
  maxLength = MAX_DESCRIPTION_LENGTH,
) {
  const existing = String(description ?? '')
  const incoming = String(transcript ?? '').trim()

  if (!incoming) return description

  const combined = existing.trim() ? `${existing}\n\n${incoming}` : incoming
  return combined.slice(0, maxLength)
}

export function validateAudioFile(file) {
  if (!file) {
    return 'Choose an audio file to transcribe.'
  }

  if (!file.size) {
    return 'The selected audio file is empty.'
  }

  if (file.size > MAX_AUDIO_BYTES) {
    return 'Audio file is too large. The maximum upload size is 10 MB.'
  }

  const name = String(file.name || '')
  const dotIndex = name.lastIndexOf('.')
  const extension = dotIndex >= 0 ? name.slice(dotIndex).toLowerCase() : ''

  if (!SUPPORTED_AUDIO_EXTENSIONS.includes(extension)) {
    return 'Unsupported audio format. Use WAV, MP3, OGG, FLAC, AAC or M4A.'
  }

  return null
}

export function voiceLanguageToHint(languageCode) {
  return VOICE_LANGUAGE_TO_HINT[languageCode] || null
}

/**
 * Return the next form state after a voice transcript is inserted. Changing
 * ``description`` is what causes ReportPage's existing debounced classification
 * effect to run again.
 */
export function applyVoiceTranscript(form, transcript, detectedLanguageCode) {
  const detectedHint = voiceLanguageToHint(detectedLanguageCode)

  return {
    ...form,
    description: appendTranscript(form.description, transcript),
    ...(detectedHint ? { language: detectedHint } : {}),
  }
}

export function describeMicrophoneError(error) {
  const name = error?.name

  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return {
      title: 'Microphone permission denied',
      message: 'The browser blocked access to your microphone.',
      guidance:
        'Allow microphone access in your browser settings, or upload an audio file instead.',
    }
  }

  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return {
      title: 'No microphone found',
      message: 'The browser could not find a microphone on this device.',
      guidance: 'Connect a microphone, or upload an audio file instead.',
    }
  }

  if (name === 'NotReadableError' || name === 'TrackStartError') {
    return {
      title: 'Microphone unavailable',
      message: 'The microphone is already in use or could not be started.',
      guidance:
        'Close other apps using the microphone, or upload an audio file instead.',
    }
  }

  if (name === 'OverconstrainedError' || name === 'ConstraintNotSatisfiedError') {
    return {
      title: 'Microphone settings unavailable',
      message: 'The browser could not apply the requested microphone settings.',
      guidance: 'Try another microphone, or upload an audio file instead.',
    }
  }

  return {
    title: 'Could not start recording',
    message: 'The browser could not start audio recording.',
    guidance: 'Try again, or upload an audio file instead.',
  }
}

export function describeVoiceTranscriptionError(requestError) {
  if (requestError.status === 413) {
    return {
      title: 'Audio file too large',
      message:
        requestError.message ||
        'The audio file exceeds the maximum upload size.',
      guidance:
        'Record a shorter clip or choose a file smaller than 10 MB. You can still type the description manually.',
    }
  }

  if (requestError.status === 415) {
    return {
      title: 'Unsupported audio format',
      message:
        requestError.message ||
        'The server does not accept the selected audio format.',
      guidance:
        'Use WAV, MP3, OGG, FLAC, AAC or M4A, or type the description manually.',
    }
  }

  if (requestError.status === 422) {
    return {
      title: 'Audio could not be transcribed',
      message:
        requestError.message ||
        'The server rejected the audio or language selection.',
      guidance:
        'Check that the clip is under 30 seconds and uses a supported format. You can still type the description manually.',
    }
  }

  if (requestError.status === 501) {
    return {
      title: 'Voice transcription not configured',
      message:
        requestError.message ||
        'The speech-to-text service is not configured on this server.',
      guidance:
        'Type the description manually. You can still submit the report.',
    }
  }

  if (requestError.status === 502) {
    return {
      title: 'Speech service rejected the request',
      message:
        requestError.message ||
        'The speech service could not process the audio clip.',
      guidance:
        'Try again, or type the description manually. Manual submission is still available.',
    }
  }

  if (requestError.status === 503) {
    return {
      title: 'Speech service unavailable',
      message:
        requestError.message ||
        'The speech service is busy or temporarily unavailable.',
      guidance:
        'Try again in a moment, or type the description manually. Manual submission is still available.',
    }
  }

  if (requestError.status === 504 || requestError.code === 'ECONNABORTED') {
    return {
      title: 'Speech service timed out',
      message:
        requestError.message ||
        'The speech service did not respond before the request timed out.',
      guidance:
        'Try a shorter clip, or type the description manually. Manual submission is still available.',
    }
  }

  if (!requestError.status) {
    return {
      title: 'Could not reach the speech service',
      message:
        requestError.message ||
        'The transcription request did not reach the server.',
      guidance:
        'Check your connection, or type the description manually. Manual submission is still available.',
    }
  }

  return {
    title: 'Transcription failed',
    message:
      requestError.message || 'The speech service returned an unexpected error.',
    guidance:
      'Try again, or type the description manually. Manual submission is still available.',
  }
}
