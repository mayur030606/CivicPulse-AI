import apiClient, { multipartConfig } from './client.js'
import { ensureWavBlob, ttsLanguageFor } from '../lib/tts.js'

/**
 * AI integration endpoints. Speech, transcription and image analysis depend on
 * external providers; complaint understanding currently uses the backend's
 * deterministic keyword classifier.
 */

export async function transcribeAudio(
  file,
  languageCode = 'indic-auto',
  { signal, onUploadProgress, timeout = 70000 } = {},
) {
  const formData = new FormData()
  formData.append('audio_file', file)
  formData.append('language_code', languageCode || 'indic-auto')

  const { data } = await apiClient.post(
    '/voice/transcribe',
    formData,
    multipartConfig({ signal, onUploadProgress, timeout }),
  )
  return data
}

export async function understandComplaint(description, language) {
  const payload = { text: String(description ?? '').trim() }
  if (language) payload.language = language

  const { data } = await apiClient.post('/ai/understand', payload)
  return data
}

export async function synthesizeSpeech(text, language) {
  const { data } = await apiClient.post(
    '/ai/speech',
    { text, language },
    { responseType: 'blob' },
  )
  return data
}

/**
 * Synthesize speech with the backend ``/voice/speak`` endpoint.
 *
 * Only the confirmed Timbre languages are accepted. The backend returns an
 * ``audio/wav`` body, so the response is requested as a Blob and normalized to
 * that MIME type before it reaches the audio element.
 */
export async function synthesizeVoiceSpeech(
  text,
  language,
  { signal, timeout = 70000 } = {},
) {
  const ttsLanguage = ttsLanguageFor(language)

  if (!ttsLanguage) {
    const error = new Error(
      'Text-to-speech is available in English, Hindi, and Marathi only.',
    )
    error.status = 422
    throw error
  }

  const { data } = await apiClient.post(
    '/voice/speak',
    { text, language: ttsLanguage },
    { responseType: 'blob', signal, timeout },
  )

  return ensureWavBlob(data)
}

export async function analyzeImage(file) {
  const formData = new FormData()
  formData.append('file', file)

  const { data } = await apiClient.post('/ai/analyze-image', formData)
  return data
}
