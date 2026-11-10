import { useEffect, useRef, useState } from 'react'
import { understandComplaint } from '../api/ai.js'
import { createIncident } from '../api/incidents.js'
import Button from '../components/ui/Button.jsx'
import Card from '../components/ui/Card.jsx'
import PageHeader from '../components/ui/PageHeader.jsx'
import SpeechPlayback from '../components/voice/SpeechPlayback.jsx'
import VoiceRecorder from '../components/voice/VoiceRecorder.jsx'
import {
  INCIDENT_CATEGORIES,
  LANGUAGES,
  PRIORITIES,
  SEVERITIES,
} from '../lib/constants.js'
import {
  formatAccuracy,
  getGeolocationPermissionState,
  isGeolocationSupported,
  isSecureGeolocationContext,
  requestCurrentPosition,
} from '../lib/geolocation.js'
import {
  applyClassificationSuggestion,
  buildIncidentPayload,
  describeClassificationError,
  describeIncidentRequestError,
  validateIncidentForm,
} from '../lib/incidentForm.js'
import { trackingPath } from '../lib/trackingView.js'
import { applyVoiceTranscript } from '../lib/voice.js'
import { buildConfirmationSpeech } from '../lib/tts.js'

const CLASSIFICATION_DEBOUNCE_MS = 800

const LOCATION_MESSAGES = {
  checking: 'Checking your current location...',
  captured:
    'Current location captured. You can edit or clear these coordinates before submitting.',
  denied:
    'Location permission was denied. Enter latitude and longitude manually, or allow location access in your browser settings.',
  unavailable:
    'Current location is unavailable. Enter latitude and longitude manually.',
  timeout:
    'Location lookup timed out. Enter latitude and longitude manually.',
  unsupported:
    'Geolocation is not available in this browser. Enter latitude and longitude manually.',
}

const INSECURE_LOCATION_MESSAGE =
  'Current location requires HTTPS or localhost. Enter latitude and longitude manually.'

const initialForm = {
  category: '',
  severity: '',
  priority: '',
  description: '',
  language: 'en',
  latitude: '',
  longitude: '',
}

const inputBaseClass =
  'mt-1.5 w-full rounded-lg border bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition focus:ring-2'
const inputClass = `${inputBaseClass} border-slate-300 focus:border-civic-500 focus:ring-civic-200`
const inputErrorClass = `${inputBaseClass} border-rose-400 focus:border-rose-500 focus:ring-rose-200`

function fieldClass(error) {
  return error ? inputErrorClass : inputClass
}

function optionLabel(options, value) {
  return options.find((option) => option.value === value)?.label || value || 'Not set'
}

function createTouchedState() {
  return { category: false, severity: false, priority: false }
}

function classificationKey(description, language) {
  return `${description.trim()}\u0000${language || ''}`
}

function locationStatusFromError(error) {
  if (error?.code === 'denied') return 'denied'
  if (error?.code === 'timeout') return 'timeout'
  if (error?.code === 'unsupported') return 'unsupported'
  return 'unavailable'
}

function locationMessageFromError(error) {
  if (error?.code === 'denied') return LOCATION_MESSAGES.denied
  if (error?.code === 'timeout') return LOCATION_MESSAGES.timeout
  if (error?.code === 'unsupported') return LOCATION_MESSAGES.unsupported
  return LOCATION_MESSAGES.unavailable
}

function locationStatusClass(status) {
  if (status === 'captured') {
    return 'rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900'
  }
  if (status === 'checking') {
    return 'rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600'
  }
  return 'rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900'
}

export default function ReportPage() {
  const [form, setForm] = useState(initialForm)
  const [fieldErrors, setFieldErrors] = useState({})
  const [submitError, setSubmitError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [created, setCreated] = useState(null)
  const [createdLanguage, setCreatedLanguage] = useState('en')
  const [classification, setClassification] = useState(null)
  const [classificationStatus, setClassificationStatus] = useState('idle')
  const [classificationError, setClassificationError] = useState(null)
  const [locationStatus, setLocationStatus] = useState('idle')
  const [locationAccuracy, setLocationAccuracy] = useState(null)
  const [locationMessage, setLocationMessage] = useState('')

  const classificationRequestRef = useRef(0)
  const classificationTimerRef = useRef(null)
  const lastClassificationKeyRef = useRef('')
  const inFlightClassificationKeyRef = useRef('')
  const touchedFieldsRef = useRef(createTouchedState())
  const currentClassificationKeyRef = useRef('')
  const autoLocationRef = useRef(null)
  const locationRequestIdRef = useRef(0)
  const manualLocationEditedRef = useRef(false)

  const descriptionText = form.description.trim()
  const hasCoordinates = [form.latitude, form.longitude].some(
    (value) => value !== '' && value != null,
  )
  const roundedLocationAccuracy = formatAccuracy(locationAccuracy)

  const selectedLanguage =
    LANGUAGES.find((language) => language.value === form.language)?.label ||
    form.language

  const confirmationSpeech = created
    ? buildConfirmationSpeech(createdLanguage)
    : null

  async function runClassification(description, language) {
    const text = description.trim()
    if (!text) return

    const key = classificationKey(text, language)
    if (key === lastClassificationKeyRef.current) return
    if (key === inFlightClassificationKeyRef.current) return

    inFlightClassificationKeyRef.current = key
    const requestId = classificationRequestRef.current + 1
    classificationRequestRef.current = requestId
    setClassification(null)
    setClassificationStatus('loading')
    setClassificationError(null)

    try {
      const result = await understandComplaint(text, language)

      // Ignore stale responses if the description or language changed while
      // the request was in flight.
      if (requestId !== classificationRequestRef.current) return
      if (key !== currentClassificationKeyRef.current) return

      lastClassificationKeyRef.current = key
      setClassification(result)
      setClassificationStatus('success')

      const touched = touchedFieldsRef.current
      setForm((current) =>
        applyClassificationSuggestion(current, result, touched),
      )
      setFieldErrors((current) => {
        if (!current.category || touched.category || !result.category) {
          return current
        }
        const next = { ...current }
        delete next.category
        return next
      })
    } catch (requestError) {
      if (requestId !== classificationRequestRef.current) return
      if (key !== currentClassificationKeyRef.current) return
      if (requestError.code === 'ERR_CANCELED') return

      setClassification(null)
      setClassificationStatus('error')
      setClassificationError(describeClassificationError(requestError))
    } finally {
      if (inFlightClassificationKeyRef.current === key) {
        inFlightClassificationKeyRef.current = ''
      }
    }
  }

  function resetClassification({ resetTouched = false } = {}) {
    classificationRequestRef.current += 1
    lastClassificationKeyRef.current = ''
    inFlightClassificationKeyRef.current = ''
    currentClassificationKeyRef.current = ''

    if (resetTouched) {
      touchedFieldsRef.current = createTouchedState()
    }

    if (classificationTimerRef.current) {
      clearTimeout(classificationTimerRef.current)
      classificationTimerRef.current = null
    }

    setClassification(null)
    setClassificationStatus('idle')
    setClassificationError(null)
  }

  useEffect(() => {
    const description = form.description.trim()

    if (!description) {
      return undefined
    }

    // Programmatic changes, such as inserting a voice transcript, must also
    // become the current key so stale classification responses are ignored.
    currentClassificationKeyRef.current = classificationKey(
      description,
      form.language,
    )

    const timer = setTimeout(() => {
      classificationTimerRef.current = null
      runClassification(description, form.language)
    }, CLASSIFICATION_DEBOUNCE_MS)

    classificationTimerRef.current = timer

    return () => {
      clearTimeout(timer)
      if (classificationTimerRef.current === timer) {
        classificationTimerRef.current = null
      }
    }
  }, [form.description, form.language])

  function applyCapturedLocation(location) {
    manualLocationEditedRef.current = false
    setForm((current) => ({
      ...current,
      latitude: location.latitude.toFixed(6),
      longitude: location.longitude.toFixed(6),
    }))
    setFieldErrors((current) => {
      const next = { ...current }
      delete next.latitude
      delete next.longitude
      return next
    })
    setSubmitError(null)
    setLocationStatus('captured')
    setLocationAccuracy(location.accuracy ?? null)
    setLocationMessage(LOCATION_MESSAGES.captured)
  }

  useEffect(() => {
    const effectState = { active: true }

    async function checkAndCapture(requestId) {
      if (!isSecureGeolocationContext()) {
        return {
          status: 'unavailable',
          message: INSECURE_LOCATION_MESSAGE,
        }
      }

      if (!isGeolocationSupported()) {
        return {
          status: 'unsupported',
          message: LOCATION_MESSAGES.unsupported,
        }
      }

      const permission = await getGeolocationPermissionState()

      if (requestId !== locationRequestIdRef.current) {
        return { status: 'idle', message: '' }
      }

      if (permission === 'denied') {
        return { status: 'denied', message: LOCATION_MESSAGES.denied }
      }

      if (permission !== 'granted') {
        // Do not trigger a permission prompt automatically. The manual button
        // remains the explicit opt-in when permission is prompt or unknown.
        return { status: 'idle', message: '' }
      }

      if (manualLocationEditedRef.current) {
        return { status: 'idle', message: '' }
      }

      try {
        const location = await requestCurrentPosition()
        return {
          status: 'captured',
          location,
          message: LOCATION_MESSAGES.captured,
        }
      } catch (error) {
        return {
          status: locationStatusFromError(error),
          message: locationMessageFromError(error),
        }
      }
    }

    if (!autoLocationRef.current) {
      const requestId = locationRequestIdRef.current + 1
      locationRequestIdRef.current = requestId
      setLocationStatus('checking')
      setLocationMessage(LOCATION_MESSAGES.checking)
      setLocationAccuracy(null)
      autoLocationRef.current = {
        requestId,
        promise: checkAndCapture(requestId),
      }
    }

    const { requestId, promise } = autoLocationRef.current

    promise
      .then((result) => {
        if (!effectState.active || requestId !== locationRequestIdRef.current) {
          return
        }

        if (result.status === 'captured') {
          if (manualLocationEditedRef.current) {
            setLocationStatus('idle')
            setLocationMessage('')
            setLocationAccuracy(null)
            return
          }

          applyCapturedLocation(result.location)
          return
        }

        setLocationStatus(result.status)
        setLocationMessage(result.message)
        setLocationAccuracy(null)
      })
      .catch(() => {
        if (!effectState.active || requestId !== locationRequestIdRef.current) {
          return
        }
        setLocationStatus('unavailable')
        setLocationMessage(LOCATION_MESSAGES.unavailable)
        setLocationAccuracy(null)
      })

    return () => {
      effectState.active = false
    }
  }, [])

  function update(field) {
    return (event) => {
      const { value } = event.target

      if (field === 'category' || field === 'severity' || field === 'priority') {
        touchedFieldsRef.current[field] = true
      }

      if (field === 'description' || field === 'language') {
        const nextDescription =
          field === 'description' ? value : form.description
        const nextLanguage = field === 'language' ? value : form.language
        currentClassificationKeyRef.current = classificationKey(
          nextDescription,
          nextLanguage,
        )
      }

      if (field === 'description' && !value.trim()) {
        resetClassification()
      }

      if (field === 'latitude' || field === 'longitude') {
        manualLocationEditedRef.current = true
        setLocationStatus('idle')
        setLocationAccuracy(null)
        setLocationMessage('')
      }

      setForm((current) => ({ ...current, [field]: value }))
      setFieldErrors((current) => {
        if (!current[field]) return current
        const next = { ...current }
        delete next[field]
        return next
      })
      setSubmitError(null)
    }
  }

  function handleDescriptionBlur() {
    if (classificationTimerRef.current) {
      clearTimeout(classificationTimerRef.current)
      classificationTimerRef.current = null
    }

    if (descriptionText) {
      runClassification(descriptionText, form.language)
    }
  }

  function handleVoiceTranscript({ transcript, detectedLanguageCode }) {
    const nextForm = applyVoiceTranscript(
      form,
      transcript,
      detectedLanguageCode,
    )

    currentClassificationKeyRef.current = classificationKey(
      nextForm.description,
      nextForm.language,
    )

    setForm((current) =>
      applyVoiceTranscript(current, transcript, detectedLanguageCode),
    )

    setFieldErrors((current) => {
      if (!current.description) return current
      const next = { ...current }
      delete next.description
      return next
    })
    setSubmitError(null)
  }

  function applyLocationFailure(error, message) {
    setLocationStatus(locationStatusFromError(error))
    setLocationAccuracy(null)
    setLocationMessage(message || locationMessageFromError(error))
  }

  function clearLocation() {
    locationRequestIdRef.current += 1
    manualLocationEditedRef.current = true
    setForm((current) => ({
      ...current,
      latitude: '',
      longitude: '',
    }))
    setFieldErrors((current) => {
      const next = { ...current }
      delete next.latitude
      delete next.longitude
      return next
    })
    setLocationStatus('idle')
    setLocationAccuracy(null)
    setLocationMessage('')
    setSubmitError(null)
  }

  async function useCurrentLocation() {
    if (!isSecureGeolocationContext()) {
      applyLocationFailure(
        { code: 'unavailable' },
        INSECURE_LOCATION_MESSAGE,
      )
      return
    }

    if (!isGeolocationSupported()) {
      applyLocationFailure({ code: 'unsupported' })
      return
    }

    if (manualLocationEditedRef.current && hasCoordinates) {
      setLocationStatus('idle')
      setLocationAccuracy(null)
      setLocationMessage(
        'Clear the coordinate fields before using your current location.',
      )
      return
    }

    const requestId = locationRequestIdRef.current + 1
    locationRequestIdRef.current = requestId
    setLocationStatus('checking')
    setLocationMessage(LOCATION_MESSAGES.checking)
    setLocationAccuracy(null)
    setSubmitError(null)

    try {
      const location = await requestCurrentPosition()
      if (requestId !== locationRequestIdRef.current) return
      applyCapturedLocation(location)
    } catch (error) {
      if (requestId !== locationRequestIdRef.current) return
      applyLocationFailure(error)
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()

    const errors = validateIncidentForm(form)
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors)
      setSubmitError(null)
      setCreated(null)
      return
    }

    setSubmitting(true)
    setSubmitError(null)
    setCreated(null)

    const submittedLanguage = form.language

    try {
      const incident = await createIncident(buildIncidentPayload(form))
      setCreated(incident)
      setCreatedLanguage(submittedLanguage)
      resetClassification({ resetTouched: true })
      locationRequestIdRef.current += 1
      manualLocationEditedRef.current = false
      setLocationStatus('idle')
      setLocationAccuracy(null)
      setLocationMessage('')
      setForm(initialForm)
      setFieldErrors({})
    } catch (requestError) {
      setSubmitError(describeIncidentRequestError(requestError))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Citizen intake"
        title="Report a civic issue"
        description="Describe the problem, choose the closest category and add a location if you can. Your report is saved as an incident and you will receive a tracking ID."
      />

      {created ? (
        <div
          role="status"
          aria-live="polite"
          className="rounded-xl border border-emerald-200 bg-emerald-50 p-5 text-emerald-900"
        >
          <p className="text-xs font-semibold uppercase tracking-wider text-emerald-700">
            Report submitted
          </p>
          <p className="mt-2 text-sm">
            Keep this tracking ID to check your report later:
          </p>
          <p className="mt-2 break-all font-mono text-2xl font-bold tracking-wide text-emerald-950">
            {created.tracking_id}
          </p>
          {created.status ? (
            <p className="mt-2 text-xs text-emerald-800">
              Status: {created.status}
            </p>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              to={trackingPath(created.tracking_id)}
              size="sm"
              variant="secondary"
            >
              Track this report
            </Button>
          </div>
          <div className="mt-4 border-t border-emerald-200 pt-4">
            {confirmationSpeech ? (
              <SpeechPlayback
                key={`${confirmationSpeech.language}:${confirmationSpeech.text}`}
                text={confirmationSpeech.text}
                language={confirmationSpeech.language}
                label="Audio confirmation"
              />
            ) : (
              <p className="text-xs text-emerald-800">
                Audio confirmation is available in English, Hindi, and Marathi.
              </p>
            )}
          </div>
        </div>
      ) : null}

      {submitError ? (
        <div
          role="alert"
          className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900"
        >
          <p className="font-semibold">{submitError.title}</p>
          <p className="mt-1">{submitError.message}</p>
          <p className="mt-1 text-xs text-rose-700">{submitError.guidance}</p>
        </div>
      ) : null}

      {Object.keys(fieldErrors).length > 0 ? (
        <div
          role="alert"
          className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"
        >
          Please fix the highlighted fields below.
        </div>
      ) : null}

      <form
        onSubmit={handleSubmit}
        noValidate
        className="grid gap-6 lg:grid-cols-[1.4fr_0.6fr]"
      >
        <Card className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="category" className="text-sm font-medium text-slate-700">
                Category <span className="text-rose-600">*</span>
              </label>
              <select
                id="category"
                required
                value={form.category}
                onChange={update('category')}
                aria-invalid={Boolean(fieldErrors.category)}
                aria-describedby={
                  fieldErrors.category ? 'category-error' : undefined
                }
                className={fieldClass(fieldErrors.category)}
              >
                <option value="">Select a category</option>
                {INCIDENT_CATEGORIES.map((category) => (
                  <option key={category.value} value={category.value}>
                    {category.label}
                  </option>
                ))}
              </select>
              {fieldErrors.category ? (
                <p id="category-error" className="mt-1.5 text-xs font-medium text-rose-600">
                  {fieldErrors.category}
                </p>
              ) : null}
            </div>

            <div>
              <label htmlFor="language" className="text-sm font-medium text-slate-700">
                Language (hint)
              </label>
              <select
                id="language"
                value={form.language}
                onChange={update('language')}
                className={inputClass}
              >
                {LANGUAGES.map((language) => (
                  <option key={language.value} value={language.value}>
                    {language.label}
                  </option>
                ))}
              </select>
              <p className="mt-1.5 text-xs text-slate-500">
                Used only as a hint for translation and triage. It is not sent
                to the incident API.
              </p>
            </div>
          </div>

          <div>
            <label htmlFor="description" className="text-sm font-medium text-slate-700">
              Description <span className="text-rose-600">*</span>
            </label>
            <textarea
              id="description"
              required
              rows={6}
              maxLength={4000}
              value={form.description}
              onChange={update('description')}
              onBlur={handleDescriptionBlur}
              aria-invalid={Boolean(fieldErrors.description)}
              aria-describedby={
                fieldErrors.description ? 'description-error' : 'description-hint'
              }
              placeholder="Include a short summary, what happened, when you noticed it, and any nearby landmark."
              className={fieldClass(fieldErrors.description)}
            />
            {fieldErrors.description ? (
              <p
                id="description-error"
                className="mt-1.5 text-xs font-medium text-rose-600"
              >
                {fieldErrors.description}
              </p>
            ) : (
              <p id="description-hint" className="mt-1.5 text-xs text-slate-500">
                Put the issue title and supporting details here. Up to 4,000
                characters.
              </p>
            )}
          </div>

          <VoiceRecorder
            onTranscript={handleVoiceTranscript}
            disabled={submitting}
          />

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="severity" className="text-sm font-medium text-slate-700">
                Severity
              </label>
              <select
                id="severity"
                value={form.severity}
                onChange={update('severity')}
                className={inputClass}
              >
                <option value="">Not set</option>
                {SEVERITIES.map((severity) => (
                  <option key={severity.value} value={severity.value}>
                    {severity.label}
                  </option>
                ))}
              </select>
              <p className="mt-1.5 text-xs text-slate-500">
                Suggested automatically when available. You can change it.
              </p>
            </div>

            <div>
              <label htmlFor="priority" className="text-sm font-medium text-slate-700">
                Priority
              </label>
              <select
                id="priority"
                value={form.priority}
                onChange={update('priority')}
                className={inputClass}
              >
                <option value="">Not set</option>
                {PRIORITIES.map((priority) => (
                  <option key={priority.value} value={priority.value}>
                    {priority.label}
                  </option>
                ))}
              </select>
              <p className="mt-1.5 text-xs text-slate-500">
                Suggested automatically when available. You can change it.
              </p>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="latitude" className="text-sm font-medium text-slate-700">
                Latitude
              </label>
              <input
                id="latitude"
                type="number"
                step="any"
                min="-90"
                max="90"
                inputMode="decimal"
                value={form.latitude}
                onChange={update('latitude')}
                aria-invalid={Boolean(fieldErrors.latitude)}
                aria-describedby={
                  fieldErrors.latitude ? 'latitude-error' : undefined
                }
                placeholder="23.0225"
                className={fieldClass(fieldErrors.latitude)}
              />
              {fieldErrors.latitude ? (
                <p id="latitude-error" className="mt-1.5 text-xs font-medium text-rose-600">
                  {fieldErrors.latitude}
                </p>
              ) : null}
            </div>

            <div>
              <label htmlFor="longitude" className="text-sm font-medium text-slate-700">
                Longitude
              </label>
              <input
                id="longitude"
                type="number"
                step="any"
                min="-180"
                max="180"
                inputMode="decimal"
                value={form.longitude}
                onChange={update('longitude')}
                aria-invalid={Boolean(fieldErrors.longitude)}
                aria-describedby={
                  fieldErrors.longitude ? 'longitude-error' : undefined
                }
                placeholder="72.5714"
                className={fieldClass(fieldErrors.longitude)}
              />
              {fieldErrors.longitude ? (
                <p
                  id="longitude-error"
                  className="mt-1.5 text-xs font-medium text-rose-600"
                >
                  {fieldErrors.longitude}
                </p>
              ) : null}
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={useCurrentLocation}
                disabled={submitting}
              >
                Use my current location
              </Button>
              {hasCoordinates ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={clearLocation}
                  disabled={submitting}
                >
                  Clear location
                </Button>
              ) : null}
            </div>
            {locationMessage ? (
              <div
                role="status"
                aria-live="polite"
                className={locationStatusClass(locationStatus)}
              >
                <p>{locationMessage}</p>
                {locationStatus === 'captured' &&
                roundedLocationAccuracy != null ? (
                  <p className="mt-1 font-medium">
                    Accuracy: about {roundedLocationAccuracy} m
                  </p>
                ) : null}
              </div>
            ) : null}
            <p className="text-xs text-slate-500">
              Coordinates are optional, but they help teams locate the issue.
            </p>
          </div>

          <div className="flex flex-col gap-3 border-t border-slate-100 pt-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-slate-500">
              Category and description are required.
            </p>
            <Button type="submit" disabled={submitting}>
              {submitting ? 'Submitting…' : 'Submit report'}
            </Button>
          </div>
        </Card>

        <div className="space-y-4">
          {descriptionText ? (
            <Card>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className="text-sm font-semibold text-slate-900">
                    Triage preview
                  </h2>
                  <p className="mt-1 text-xs text-slate-500">
                    Rule-based keyword matching. Not an LLM.
                  </p>
                </div>
                {classificationStatus === 'loading' ? (
                  <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600">
                    Checking…
                  </span>
                ) : null}
              </div>

              {classificationStatus === 'loading' ? (
                <p className="mt-3 text-xs text-slate-500">
                  Checking the description with deterministic keyword rules…
                </p>
              ) : null}

              {classificationError ? (
                <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                  <p className="font-semibold">{classificationError.title}</p>
                  <p className="mt-1">{classificationError.message}</p>
                  <p className="mt-1 text-amber-800">
                    {classificationError.guidance}
                  </p>
                </div>
              ) : null}

              {classification ? (
                <>
                  <dl className="mt-4 space-y-2.5 text-sm">
                    <div className="flex items-start justify-between gap-3">
                      <dt className="text-slate-500">Category</dt>
                      <dd className="text-right font-medium text-slate-900">
                        {optionLabel(INCIDENT_CATEGORIES, classification.category)}
                      </dd>
                    </div>
                    <div className="flex items-start justify-between gap-3">
                      <dt className="text-slate-500">Severity</dt>
                      <dd className="text-right font-medium text-slate-900">
                        {optionLabel(SEVERITIES, classification.severity)}
                      </dd>
                    </div>
                    <div className="flex items-start justify-between gap-3">
                      <dt className="text-slate-500">Priority</dt>
                      <dd className="text-right font-medium text-slate-900">
                        {optionLabel(PRIORITIES, classification.priority)}
                      </dd>
                    </div>
                    <div className="flex items-start justify-between gap-3">
                      <dt className="text-slate-500">Department</dt>
                      <dd className="text-right font-medium text-slate-900">
                        {classification.responsible_department || 'Not available'}
                      </dd>
                    </div>
                    {classification.location_hint ? (
                      <div className="flex items-start justify-between gap-3">
                        <dt className="text-slate-500">Location hint</dt>
                        <dd className="text-right font-medium text-slate-900">
                          {classification.location_hint}
                        </dd>
                      </div>
                    ) : null}
                  </dl>

                  <div className="mt-4 border-t border-slate-100 pt-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                      Explanation
                    </p>
                    <p className="mt-1 text-xs leading-5 text-slate-600">
                      {classification.explanation}
                    </p>
                  </div>

                  <div className="mt-3 flex items-center justify-between gap-2">
                    <span className="text-xs text-slate-500">Needs review</span>
                    <span
                      className={
                        classification.needs_review
                          ? 'rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-800'
                          : 'rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-800'
                      }
                    >
                      {classification.needs_review ? 'Yes — review recommended' : 'No'}
                    </span>
                  </div>

                  <p className="mt-3 text-[11px] text-slate-400">
                    Method:{' '}
                    {classification.provider === 'deterministic_rules'
                      ? 'deterministic keyword rules'
                      : classification.provider}
                  </p>
                </>
              ) : null}

              {!classification &&
              !classificationError &&
              classificationStatus !== 'loading' ? (
                <p className="mt-3 text-xs text-slate-500">
                  Classification starts after you pause typing, or when the
                  description loses focus.
                </p>
              ) : null}
            </Card>
          ) : null}

          <Card>
            <h2 className="text-sm font-semibold text-slate-900">Language hint</h2>
            <p className="mt-2 text-sm text-slate-600">
              Selected: <span className="font-medium">{selectedLanguage}</span>
            </p>
            <p className="mt-2 text-xs text-slate-500">
              This selection guides triage. Voice transcription uses its own
              language setting and updates this hint when it detects a supported
              language. It is not part of the incident payload.
            </p>
          </Card>

          <Card>
            <h2 className="text-sm font-semibold text-slate-900">
              What happens next
            </h2>
            <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-slate-600">
              <li>Rule-based triage suggests category, severity and priority.</li>
              <li>You can edit the suggestions before submitting.</li>
              <li>Optional voice notes are transcribed into the description for review.</li>
              <li>The backend returns a tracking ID.</li>
            </ol>
          </Card>
        </div>
      </form>
    </div>
  )
}
