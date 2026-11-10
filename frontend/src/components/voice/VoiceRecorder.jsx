import { useEffect, useId, useRef, useState } from 'react'

import { transcribeAudio } from '../../api/ai.js'
import Button from '../ui/Button.jsx'
import Spinner from '../ui/Spinner.jsx'
import { VOICE_LANGUAGES } from '../../lib/constants.js'
import { cx } from '../../lib/cx.js'
import {
  MAX_AUDIO_BYTES,
  MAX_RECORDING_SECONDS,
  SUPPORTED_AUDIO_ACCEPT,
  describeMicrophoneError,
  describeVoiceTranscriptionError,
  formatRecordingDuration,
  validateAudioFile,
} from '../../lib/voice.js'

const RECORDER_MIME_CANDIDATES = [
  'audio/webm;codecs=opus',
  'audio/ogg;codecs=opus',
  'audio/mp4',
  'audio/webm',
  'audio/ogg',
]

function canRecordInBrowser() {
  return (
    typeof window !== 'undefined' &&
    typeof window.MediaRecorder !== 'undefined' &&
    typeof navigator !== 'undefined' &&
    Boolean(navigator.mediaDevices?.getUserMedia)
  )
}

function pickRecorderMimeType() {
  if (
    typeof window === 'undefined' ||
    typeof window.MediaRecorder === 'undefined' ||
    typeof window.MediaRecorder.isTypeSupported !== 'function'
  ) {
    return ''
  }

  return (
    RECORDER_MIME_CANDIDATES.find((mimeType) =>
      window.MediaRecorder.isTypeSupported(mimeType),
    ) || ''
  )
}

function writeAscii(view, offset, value) {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index))
  }
}

/**
 * MediaRecorder commonly produces WebM/Opus in Chromium and OGG or MP4 in
 * other browsers. The backend accepts WAV/MP3/OGG/FLAC/AAC/M4A, so recorded
 * audio is decoded and encoded as 16-bit PCM WAV before upload.
 */
function encodeWav(audioBuffer, maxSeconds = MAX_RECORDING_SECONDS) {
  const sampleRate = audioBuffer.sampleRate
  const sourceChannelCount = Math.max(1, audioBuffer.numberOfChannels)
  const channelCount = 1
  const frameCount = Math.min(
    audioBuffer.length,
    Math.max(0, Math.floor(sampleRate * maxSeconds)),
  )

  if (!frameCount) {
    throw new Error('The recording did not contain any audio frames.')
  }

  const bytesPerSample = 2
  const blockAlign = channelCount * bytesPerSample
  const dataSize = frameCount * blockAlign
  const buffer = new ArrayBuffer(44 + dataSize)
  const view = new DataView(buffer)

  writeAscii(view, 0, 'RIFF')
  view.setUint32(4, 36 + dataSize, true)
  writeAscii(view, 8, 'WAVE')
  writeAscii(view, 12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, channelCount, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * blockAlign, true)
  view.setUint16(32, blockAlign, true)
  view.setUint16(34, 16, true)
  writeAscii(view, 36, 'data')
  view.setUint32(40, dataSize, true)

  const channels = []
  for (let channel = 0; channel < sourceChannelCount; channel += 1) {
    channels.push(audioBuffer.getChannelData(channel))
  }

  let offset = 44
  for (let frame = 0; frame < frameCount; frame += 1) {
    let sample = 0
    for (let channel = 0; channel < sourceChannelCount; channel += 1) {
      sample += channels[channel][frame] || 0
    }
    sample = Math.max(-1, Math.min(1, sample / sourceChannelCount))
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
    offset += 2
  }

  return buffer
}

async function convertRecordingToWavFile(blob) {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext
  if (!AudioContextClass) {
    throw new Error('Web Audio is not available in this browser.')
  }

  const audioContext = new AudioContextClass()
  try {
    const sourceBuffer = await blob.arrayBuffer()
    const audioBuffer = await audioContext.decodeAudioData(sourceBuffer)
    const wavBuffer = encodeWav(audioBuffer, MAX_RECORDING_SECONDS)
    const filename = `civicpulse-voice-${Date.now()}.wav`
    return new File([wavBuffer], filename, { type: 'audio/wav' })
  } finally {
    if (typeof audioContext.close === 'function') {
      await audioContext.close()
    }
  }
}

export default function VoiceRecorder({
  onTranscript,
  disabled = false,
  className,
}) {
  const languageSelectId = useId()
  const fileInputId = useId()
  const titleId = useId()

  const [recordingSupported] = useState(canRecordInBrowser)
  const [voiceLanguage, setVoiceLanguage] = useState('indic-auto')
  const [status, setStatus] = useState('idle')
  const [duration, setDuration] = useState(0)
  const [uploadProgress, setUploadProgress] = useState(null)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState('')
  const [detectedLanguage, setDetectedLanguage] = useState(null)

  const recorderRef = useRef(null)
  const streamRef = useRef(null)
  const chunksRef = useRef([])
  const timerRef = useRef(null)
  const startedAtRef = useRef(0)
  const discardRef = useRef(false)
  const stoppingRef = useRef(false)
  const abortRef = useRef(null)
  const mountedRef = useRef(true)

  const recording = status === 'recording'
  const busy =
    status === 'requesting' ||
    status === 'processing' ||
    status === 'uploading' ||
    status === 'transcribing'
  const controlsDisabled = disabled || busy || recording

  useEffect(() => {
    mountedRef.current = true

    return () => {
      mountedRef.current = false
      discardRef.current = true

      if (timerRef.current) {
        window.clearInterval(timerRef.current)
        timerRef.current = null
      }

      abortRef.current?.abort()
      abortRef.current = null

      const recorder = recorderRef.current
      if (recorder) {
        recorder.ondataavailable = null
        recorder.onstop = null
        recorder.onerror = null
        if (recorder.state !== 'inactive') {
          try {
            recorder.stop()
          } catch {
            // The recorder may already have been stopped by the browser.
          }
        }
      }
      recorderRef.current = null
      chunksRef.current = []

      const stream = streamRef.current
      if (stream) {
        stream.getTracks().forEach((track) => track.stop())
        streamRef.current = null
      }
    }
  }, [])

  function clearTimer() {
    if (timerRef.current) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
  }

  function stopStreamTracks() {
    const stream = streamRef.current
    if (!stream) return
    stream.getTracks().forEach((track) => track.stop())
    streamRef.current = null
  }

  function stopRecording() {
    if (stoppingRef.current) return

    const recorder = recorderRef.current
    if (!recorder || recorder.state === 'inactive') return

    stoppingRef.current = true
    clearTimer()
    setStatus('processing')

    try {
      recorder.stop()
    } catch {
      stoppingRef.current = false
      setStatus('idle')
      setError({
        title: 'Could not stop recording',
        message: 'The browser could not finish the recording.',
        guidance: 'Try again, or upload an audio file instead.',
      })
    }
  }

  function handleCancel() {
    discardRef.current = true
    stoppingRef.current = false
    clearTimer()

    const recorder = recorderRef.current
    if (recorder && recorder.state !== 'inactive') {
      try {
        recorder.stop()
      } catch {
        // The stream is stopped below even if the recorder has already ended.
      }
    } else {
      recorderRef.current = null
      chunksRef.current = []
    }

    stopStreamTracks()
    setDuration(0)
    setUploadProgress(null)
    setStatus('idle')
    setError(null)
    setNotice('Recording cancelled.')
  }

  async function uploadAudioFile(file) {
    const controller = new AbortController()
    abortRef.current = controller

    setError(null)
    setNotice('')
    setDetectedLanguage(null)
    setUploadProgress(null)
    setStatus('uploading')

    try {
      const result = await transcribeAudio(file, voiceLanguage, {
        signal: controller.signal,
        onUploadProgress: (event) => {
          if (!mountedRef.current) return
          if (!event.total) return

          const percent = Math.min(
            100,
            Math.round((event.loaded / event.total) * 100),
          )
          setUploadProgress(percent)
          if (percent >= 100) setStatus('transcribing')
        },
      })

      if (!mountedRef.current) return

      if (result?.success === false) {
        setStatus('idle')
        setUploadProgress(null)
        setError({
          title: 'Transcription failed',
          message: 'The speech service did not return a transcript.',
          guidance:
            'Try again, or type the description manually. Manual submission is still available.',
        })
        return
      }

      const transcript = String(result?.transcript ?? '').trim()
      const detected = result?.detected_language_code || null
      setDetectedLanguage(detected)

      if (!transcript) {
        setStatus('idle')
        setUploadProgress(null)
        setError({
          title: 'No speech detected',
          message: 'The clip did not contain any recognizable speech.',
          guidance: 'Try recording again, or type the description manually.',
        })
        return
      }

      onTranscript?.({
        transcript,
        detectedLanguageCode: detected,
        truncated: Boolean(result?.truncated),
      })

      setStatus('idle')
      setUploadProgress(null)
      setNotice(
        result?.truncated
          ? 'Transcript added to the description. The service marked it as incomplete; review and edit it before submitting.'
          : 'Transcript added to the description. You can edit it before submitting.',
      )
    } catch (requestError) {
      if (!mountedRef.current || requestError.code === 'ERR_CANCELED') return

      setStatus('idle')
      setUploadProgress(null)
      setError(describeVoiceTranscriptionError(requestError))
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null
      }
    }
  }

  async function handleRecorderStop() {
    clearTimer()
    stopStreamTracks()

    const recorder = recorderRef.current
    const mimeType = recorder?.mimeType || 'audio/webm'
    const chunks = chunksRef.current

    chunksRef.current = []
    recorderRef.current = null
    stoppingRef.current = false

    if (discardRef.current) {
      discardRef.current = false
      setDuration(0)
      setStatus('idle')
      return
    }

    if (!chunks.length) {
      setDuration(0)
      setStatus('idle')
      setError({
        title: 'No audio captured',
        message: 'The browser did not capture any audio from the microphone.',
        guidance: 'Try recording again, or upload an audio file instead.',
      })
      return
    }

    setStatus('processing')

    let wavFile
    try {
      const recordingBlob = new Blob(chunks, { type: mimeType })
      wavFile = await convertRecordingToWavFile(recordingBlob)
    } catch {
      if (!mountedRef.current) return
      setStatus('idle')
      setError({
        title: 'Recording format unsupported',
        message:
          'This browser recorded audio in a format that could not be prepared for transcription.',
        guidance:
          'Upload a WAV, MP3, OGG, FLAC, AAC or M4A file instead, or type the description manually.',
      })
      return
    }

    if (!mountedRef.current) return

    if (wavFile.size > MAX_AUDIO_BYTES) {
      setStatus('idle')
      setError({
        title: 'Recording too large',
        message: 'The prepared audio file exceeds the 10 MB upload limit.',
        guidance: 'Record a shorter clip, or type the description manually.',
      })
      return
    }

    await uploadAudioFile(wavFile)
  }

  async function handleStart() {
    setError(null)
    setNotice('')
    setDetectedLanguage(null)

    if (!recordingSupported) {
      setError({
        title: 'Recording not supported',
        message: 'This browser does not support microphone recording.',
        guidance: 'Upload a WAV, MP3, OGG, FLAC, AAC or M4A file instead.',
      })
      return
    }

    setStatus('requesting')

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })

      if (!mountedRef.current) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }

      streamRef.current = stream

      const mimeType = pickRecorderMimeType()
      if (!mimeType) {
        stopStreamTracks()
        setStatus('idle')
        setError({
          title: 'Recording format unsupported',
          message:
            'This browser cannot record audio in a format the transcription service can prepare.',
          guidance:
            'Upload a WAV, MP3, OGG, FLAC, AAC or M4A file instead, or type the description manually.',
        })
        return
      }

      const recorder = new window.MediaRecorder(stream, { mimeType })
      recorderRef.current = recorder
      chunksRef.current = []
      discardRef.current = false
      stoppingRef.current = false

      recorder.ondataavailable = (event) => {
        if (event.data?.size) {
          chunksRef.current.push(event.data)
        }
      }

      recorder.onerror = () => {
        discardRef.current = true
        clearTimer()
        stopStreamTracks()
        setStatus('idle')
        setDuration(0)
        setError({
          title: 'Recording failed',
          message: 'The browser could not record audio from the microphone.',
          guidance: 'Try again, or upload an audio file instead.',
        })
      }

      recorder.onstop = () => {
        void handleRecorderStop()
      }

      startedAtRef.current = Date.now()
      setDuration(0)
      setUploadProgress(null)
      recorder.start()
      setStatus('recording')

      timerRef.current = window.setInterval(() => {
        const elapsed = (Date.now() - startedAtRef.current) / 1000
        setDuration(Math.min(elapsed, MAX_RECORDING_SECONDS))

        if (elapsed >= MAX_RECORDING_SECONDS) {
          stopRecording()
        }
      }, 200)
    } catch (microphoneError) {
      stopStreamTracks()
      if (!mountedRef.current) return
      setStatus('idle')
      setError(describeMicrophoneError(microphoneError))
    }
  }

  async function handleFileChange(event) {
    const file = event.target.files?.[0]
    event.target.value = ''

    if (!file) return

    setError(null)
    setNotice('')
    setDetectedLanguage(null)

    const validationError = validateAudioFile(file)
    if (validationError) {
      setError({
        title: 'Audio file not accepted',
        message: validationError,
        guidance:
          'Choose a WAV, MP3, OGG, FLAC, AAC or M4A file up to 10 MB, or type the description manually.',
      })
      return
    }

    await uploadAudioFile(file)
  }

  return (
    <section
      className={cx(
        'rounded-xl border border-slate-200 bg-slate-50 p-4',
        className,
      )}
      aria-labelledby={titleId}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3
            id={titleId}
            className="text-sm font-semibold text-slate-900"
          >
            Add a voice note
          </h3>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            Record a short complaint with Gnani Prisma speech-to-text. The
            transcript is added to the description and you can edit it before
            submitting. Audio is never sent to the incident API.
          </p>
        </div>
      </div>

      <div className="mt-3 max-w-xs">
        <label
          htmlFor={languageSelectId}
          className="text-xs font-medium text-slate-700"
        >
          Voice language
        </label>
        <select
          id={languageSelectId}
          value={voiceLanguage}
          onChange={(event) => setVoiceLanguage(event.target.value)}
          disabled={controlsDisabled}
          className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition focus:border-civic-500 focus:ring-2 focus:ring-civic-200 disabled:cursor-not-allowed disabled:bg-slate-100"
        >
          {VOICE_LANGUAGES.map((language) => (
            <option key={language.value} value={language.value}>
              {language.label}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-slate-500">
          Auto-detect uses <span className="font-mono">indic-auto</span>. The
          transcript stays in the language that was spoken.
        </p>
      </div>

      {status === 'requesting' ? (
        <div className="mt-3">
          <Spinner label="Requesting microphone permission…" />
        </div>
      ) : null}

      {status === 'processing' ? (
        <div className="mt-3">
          <Spinner label="Preparing the recording for transcription…" />
        </div>
      ) : null}

      {recording ? (
        <div className="mt-3 flex flex-wrap items-center gap-3 rounded-lg border border-rose-200 bg-rose-50 p-3">
          <span className="inline-flex items-center gap-2 text-sm font-semibold text-rose-700">
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-rose-600" />
            Recording
          </span>
          <span className="font-mono text-sm font-semibold text-rose-900">
            {formatRecordingDuration(duration)} /{' '}
            {formatRecordingDuration(MAX_RECORDING_SECONDS)}
          </span>
          <Button size="sm" variant="secondary" onClick={stopRecording}>
            Stop recording
          </Button>
          <Button size="sm" variant="ghost" onClick={handleCancel}>
            Cancel
          </Button>
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {recordingSupported ? (
            <Button
              size="sm"
              onClick={handleStart}
              disabled={disabled || busy}
            >
              Start recording
            </Button>
          ) : null}

          <label
            htmlFor={fileInputId}
            className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg bg-white px-3 py-1.5 text-sm font-semibold text-slate-700 ring-1 ring-slate-300 transition-colors hover:bg-slate-50 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-slate-400 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {recordingSupported ? 'Upload audio instead' : 'Upload audio file'}
            <input
              id={fileInputId}
              type="file"
              accept={SUPPORTED_AUDIO_ACCEPT}
              onChange={handleFileChange}
              disabled={disabled || busy}
              className="sr-only"
            />
          </label>
        </div>
      )}

      {status === 'uploading' || status === 'transcribing' ? (
        <div className="mt-3 rounded-lg border border-slate-200 bg-white p-3">
          <div className="flex items-center justify-between gap-3 text-xs text-slate-600">
            <span>
              {status === 'transcribing'
                ? 'Transcribing audio…'
                : 'Uploading audio…'}
            </span>
            {uploadProgress !== null ? (
              <span className="font-mono">{uploadProgress}%</span>
            ) : null}
          </div>
          {uploadProgress !== null ? (
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200">
              <div
                className="h-full rounded-full bg-civic-600 transition-all"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          ) : (
            <div className="mt-2">
              <Spinner label="Waiting for the speech service…" />
            </div>
          )}
        </div>
      ) : null}

      {error ? (
        <div
          role="alert"
          className="mt-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-900"
        >
          <p className="font-semibold">{error.title}</p>
          <p className="mt-1">{error.message}</p>
          <p className="mt-1 text-rose-700">{error.guidance}</p>
        </div>
      ) : null}

      {notice ? (
        <div
          role="status"
          className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900"
        >
          {notice}
        </div>
      ) : null}

      {detectedLanguage ? (
        <p className="mt-2 text-xs text-slate-500">
          Detected language:{' '}
          <span className="font-medium text-slate-700">{detectedLanguage}</span>
        </p>
      ) : null}

      <p className="mt-2 text-xs text-slate-500">
        Maximum 30 seconds and 10 MB. Supported uploads: WAV, MP3, OGG, FLAC,
        AAC, M4A.
      </p>

      {!recordingSupported ? (
        <p className="mt-2 text-xs font-medium text-amber-700">
          Microphone recording is not available in this browser. Upload an
          audio file instead.
        </p>
      ) : null}
    </section>
  )
}
