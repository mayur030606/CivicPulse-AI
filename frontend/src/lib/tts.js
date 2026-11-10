import { TTS_LANGUAGES } from './constants.js'

/**
 * Pure helpers for the optional confirmation text-to-speech feature.
 *
 * Only the languages confirmed by the backend Timbre service are exposed:
 * en-IN, hi-IN and mr-IN. The confirmation sentences below are the exact
 * examples in ``backend/app/schemas/voice.py``; do not add unverified
 * translations here.
 */

const TTS_LANGUAGE_ALIASES = {
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

const TTS_LANGUAGE_VALUES = new Set(
  TTS_LANGUAGES.map((language) => language.value),
)

const CONFIRMATION_SPEECH = {
  'en-IN': 'Your complaint has been registered successfully.',
  'hi-IN': 'आपकी शिकायत सफलतापूर्वक दर्ज हो गई है।',
  'mr-IN': 'आपली तक्रार यशस्वीरित्या नोंदवली गेली आहे.',
}

export function ttsLanguageFor(language) {
  const key = String(language ?? '')
    .trim()
    .toLowerCase()
  const resolved = TTS_LANGUAGE_ALIASES[key]
  return resolved && TTS_LANGUAGE_VALUES.has(resolved) ? resolved : null
}

export function buildConfirmationSpeech(language) {
  const ttsLanguage = ttsLanguageFor(language)
  if (!ttsLanguage) return null

  return {
    text: CONFIRMATION_SPEECH[ttsLanguage],
    language: ttsLanguage,
  }
}

export function ensureWavBlob(data) {
  if (typeof Blob === 'undefined' || data == null) return data
  if (data instanceof Blob && data.type === 'audio/wav') return data

  return new Blob([data], { type: 'audio/wav' })
}

export function speechButtonLabel(status, hasAudio) {
  if (status === 'loading') return 'Preparing audio…'
  if (status === 'playing') return 'Playing…'
  if (status === 'error' && !hasAudio) return 'Try again'
  if (hasAudio) return 'Replay confirmation'
  return 'Play confirmation'
}

export function describeSpeechError(requestError) {
  if (requestError?.status === 422) {
    return {
      title: 'Confirmation audio unavailable',
      message:
        requestError.message ||
        'The voice service rejected the confirmation text or language.',
      guidance:
        'Your report is still submitted. You can use the tracking ID above.',
    }
  }

  if (requestError?.status === 501) {
    return {
      title: 'Voice playback not configured',
      message:
        requestError.message ||
        'The server does not have text-to-speech configured.',
      guidance:
        'Your report is still submitted. You can use the tracking ID above.',
    }
  }

  if (requestError?.status === 502) {
    return {
      title: 'Voice service rejected the request',
      message:
        requestError.message ||
        'The voice service could not generate the confirmation audio.',
      guidance:
        'Your report is still submitted. Try again later or use the tracking ID above.',
    }
  }

  if (requestError?.status === 503) {
    return {
      title: 'Voice service unavailable',
      message:
        requestError.message ||
        'The voice service is busy or temporarily unavailable.',
      guidance:
        'Your report is still submitted. Try again later or use the tracking ID above.',
    }
  }

  if (requestError?.status === 504 || requestError?.code === 'ECONNABORTED') {
    return {
      title: 'Voice service timed out',
      message:
        requestError.message ||
        'The voice service did not respond before the request timed out.',
      guidance:
        'Your report is still submitted. Try again or use the tracking ID above.',
    }
  }

  if (!requestError?.status) {
    return {
      title: 'Could not reach the voice service',
      message:
        requestError?.message ||
        'The audio request did not reach the server.',
      guidance:
        'Your report is still submitted. Check your connection or use the tracking ID above.',
    }
  }

  return {
    title: 'Could not prepare confirmation audio',
    message:
      requestError?.message ||
      'The voice service returned an unexpected error.',
    guidance:
      'Your report is still submitted. You can use the tracking ID above.',
  }
}
