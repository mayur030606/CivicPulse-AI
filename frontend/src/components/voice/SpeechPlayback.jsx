import { useCallback, useEffect, useRef, useState } from 'react'
import { synthesizeVoiceSpeech } from '../../api/ai.js'
import Button from '../ui/Button.jsx'
import {
  describeSpeechError,
  ensureWavBlob,
  speechButtonLabel,
  ttsLanguageFor,
} from '../../lib/tts.js'

/**
 * Optional, user-initiated confirmation audio. Nothing is requested or played
 * until the citizen presses Play. The report confirmation remains usable even
 * if speech synthesis or browser playback fails.
 *
 * If the text or language can change while this component stays mounted, give
 * it a React ``key`` derived from those values so playback state resets.
 */
export default function SpeechPlayback({
  text,
  language,
  label = 'Audio confirmation',
  disabled = false,
  className,
}) {
  const ttsLanguage = ttsLanguageFor(language)
  const [status, setStatus] = useState('idle')
  const [error, setError] = useState(null)
  const [hasAudio, setHasAudio] = useState(false)

  const audioRef = useRef(null)
  const objectUrlRef = useRef(null)
  const abortRef = useRef(null)
  const mountedRef = useRef(false)

  const releaseAudio = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.onended = null
      audioRef.current.onerror = null
      audioRef.current.pause()
      audioRef.current.removeAttribute('src')
      audioRef.current.load()
      audioRef.current = null
    }

    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current)
      objectUrlRef.current = null
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true

    return () => {
      mountedRef.current = false
      if (abortRef.current) {
        abortRef.current.abort()
        abortRef.current = null
      }
      releaseAudio()
    }
  }, [releaseAudio])

  if (!ttsLanguage || !text) return null

  async function startPlayback() {
    if (disabled || status === 'loading' || status === 'playing') return

    if (audioRef.current) {
      try {
        audioRef.current.currentTime = 0
        setError(null)
        setStatus('playing')
        await audioRef.current.play()
      } catch {
        if (!mountedRef.current) return
        setStatus('error')
        setError({
          title: 'Could not play the confirmation audio',
          message: 'The browser could not play the synthesized audio.',
          guidance:
            'Your report is still submitted. You can use the tracking ID above.',
        })
      }
      return
    }

    setStatus('loading')
    setError(null)

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const data = await synthesizeVoiceSpeech(text, ttsLanguage, {
        signal: controller.signal,
      })

      if (!mountedRef.current || controller.signal.aborted) return

      const blob = ensureWavBlob(data)
      const url = URL.createObjectURL(blob)

      if (!mountedRef.current || controller.signal.aborted) {
        URL.revokeObjectURL(url)
        return
      }

      objectUrlRef.current = url

      const audio = new Audio(url)
      audioRef.current = audio
      setHasAudio(true)

      audio.onended = () => {
        if (mountedRef.current) setStatus('idle')
      }
      audio.onerror = () => {
        if (!mountedRef.current) return
        releaseAudio()
        setHasAudio(false)
        setStatus('error')
        setError({
          title: 'Could not play the confirmation audio',
          message: 'The browser could not play the synthesized audio.',
          guidance:
            'Your report is still submitted. You can use the tracking ID above.',
        })
      }

      setStatus('playing')
      await audio.play()
    } catch (requestError) {
      if (!mountedRef.current || controller.signal.aborted) return
      if (requestError?.code === 'ERR_CANCELED') return

      setStatus('error')
      setError(describeSpeechError(requestError))
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null
      }
    }
  }

  const buttonLabel = speechButtonLabel(status, hasAudio)

  return (
    <div className={className}>
      <p className="text-xs font-semibold uppercase tracking-wider text-emerald-700">
        {label}
      </p>

      <div className="mt-2 flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={startPlayback}
          disabled={disabled || status === 'loading' || status === 'playing'}
          aria-label={buttonLabel}
          aria-busy={status === 'loading'}
        >
          {buttonLabel}
        </Button>

        {status === 'loading' ? (
          <span
            className="text-xs text-emerald-800"
            role="status"
            aria-live="polite"
          >
            Preparing audio…
          </span>
        ) : null}

        {status === 'playing' ? (
          <span
            className="text-xs text-emerald-800"
            role="status"
            aria-live="polite"
          >
            Playing confirmation…
          </span>
        ) : null}
      </div>

      <p className="mt-2 text-xs text-emerald-800">
        Optional. Your report has already been submitted.
      </p>

      {error ? (
        <div
          className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900"
          role="alert"
        >
          <p className="font-semibold">{error.title}</p>
          <p className="mt-1">{error.message}</p>
          <p className="mt-1 text-amber-800">{error.guidance}</p>
        </div>
      ) : null}
    </div>
  )
}
