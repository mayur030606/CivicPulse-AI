import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getTracking } from '../api/tracking.js'
import { PriorityBadge, StatusBadge } from '../components/ui/Badge.jsx'
import Button from '../components/ui/Button.jsx'
import Card from '../components/ui/Card.jsx'
import EmptyState from '../components/ui/EmptyState.jsx'
import PageHeader from '../components/ui/PageHeader.jsx'
import Spinner from '../components/ui/Spinner.jsx'
import {
  TRACKING_QUERY_PARAM,
  describeTrackingError,
  mapTrackingResult,
  normalizeTrackingId,
  trackingLookupState,
  validateTrackingId,
} from '../lib/trackingView.js'

export default function TrackingPage() {
  const [searchParams] = useSearchParams()
  const queryId = normalizeTrackingId(searchParams.get(TRACKING_QUERY_PARAM))
  const [trackingId, setTrackingId] = useState(queryId)
  const [fieldError, setFieldError] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const requestIdRef = useRef(0)
  const lastQueryIdRef = useRef('')

  const lookup = useCallback(async (rawId) => {
    const id = normalizeTrackingId(rawId)
    const validationError = validateTrackingId(id)

    if (validationError) {
      requestIdRef.current += 1
      setFieldError(validationError)
      setResult(null)
      setError(null)
      setLoading(false)
      return
    }

    const requestId = requestIdRef.current + 1
    requestIdRef.current = requestId
    setFieldError('')
    setResult(null)
    setError(null)
    setLoading(true)

    try {
      const data = await getTracking(id)

      if (requestId !== requestIdRef.current) return
      setResult(data)
    } catch (requestError) {
      if (requestId !== requestIdRef.current) return
      setError(requestError)
    } finally {
      if (requestId === requestIdRef.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!queryId) {
      lastQueryIdRef.current = ''
      return
    }

    if (queryId === lastQueryIdRef.current) return

    lastQueryIdRef.current = queryId
    setTrackingId(queryId)
    lookup(queryId)
  }, [queryId, lookup])

  function handleSubmit(event) {
    event.preventDefault()
    lookup(trackingId)
  }

  function handleChange(event) {
    requestIdRef.current += 1
    setTrackingId(event.target.value)
    setFieldError('')
    setResult(null)
    setError(null)
    setLoading(false)
  }

  const viewState = trackingLookupState({ loading, error, result })
  const view = result ? mapTrackingResult(result) : null
  const errorView = error ? describeTrackingError(error) : null

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Public tracking"
        title="Track a report"
        description="Enter the tracking ID you received after submitting a report. No login or registration is required."
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-4">
          <Card>
            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
              <div>
                <label
                  htmlFor="tracking-id"
                  className="block text-sm font-medium text-slate-700"
                >
                  Tracking ID
                </label>
                <p
                  id="tracking-id-help"
                  className="mt-1 text-xs text-slate-500"
                >
                  Paste the ID exactly as shown after submission.
                </p>
                <input
                  id="tracking-id"
                  name="trackingId"
                  type="text"
                  value={trackingId}
                  onChange={handleChange}
                  autoComplete="off"
                  spellCheck={false}
                  required
                  placeholder="Enter your tracking ID"
                  aria-invalid={Boolean(fieldError)}
                  aria-describedby={
                    fieldError
                      ? 'tracking-id-help tracking-id-error'
                      : 'tracking-id-help'
                  }
                  className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm shadow-sm outline-none focus:border-civic-500 focus:ring-2 focus:ring-civic-200"
                />
                {fieldError ? (
                  <p
                    id="tracking-id-error"
                    role="alert"
                    className="mt-2 text-sm text-rose-600"
                  >
                    {fieldError}
                  </p>
                ) : null}
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <Button type="submit" disabled={loading}>
                  {loading ? 'Looking up…' : 'Track report'}
                </Button>
                <Button to="/report" variant="secondary">
                  Report an issue
                </Button>
              </div>
            </form>
          </Card>

          {viewState === 'loading' ? (
            <Card>
              <Spinner label="Looking up your report…" />
            </Card>
          ) : null}

          {viewState === 'not-found' || viewState === 'error' ? (
            <Card
              role="alert"
              className="border-rose-200 bg-rose-50 text-rose-900"
            >
              <h2 className="text-sm font-semibold">{errorView.title}</h2>
              <p className="mt-1 text-sm">{errorView.message}</p>
              <p className="mt-2 text-xs text-rose-700">
                {errorView.guidance}
              </p>
            </Card>
          ) : null}

          {viewState === 'success' && view ? (
            <Card role="status" aria-live="polite">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-civic-600">
                    Tracking result
                  </p>
                  <p className="mt-2 text-xs font-medium uppercase tracking-wide text-slate-400">
                    Tracking ID
                  </p>
                  <h2 className="font-mono text-xl font-semibold text-slate-900">
                    {view.trackingId || '—'}
                  </h2>
                </div>
                <div className="flex flex-wrap gap-2">
                  <StatusBadge status={view.status} />
                  <PriorityBadge priority={view.priority} />
                </div>
              </div>

              <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-slate-100 pt-4 text-sm sm:grid-cols-4">
                <div>
                  <dt className="text-xs font-medium text-slate-400">
                    Category
                  </dt>
                  <dd className="mt-0.5 text-slate-700">
                    {view.categoryLabel}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-medium text-slate-400">
                    Severity
                  </dt>
                  <dd className="mt-0.5 text-slate-700">
                    {view.severityLabel}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-medium text-slate-400">
                    Location
                  </dt>
                  <dd className="mt-0.5 text-slate-700">
                    {view.coordinatesLabel}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-medium text-slate-400">
                    Reported
                  </dt>
                  <dd className="mt-0.5 text-slate-700">
                    {view.createdLabel}
                  </dd>
                </div>
              </dl>

              <p className="mt-4 text-xs text-slate-500">
                This is the public status returned by the tracking API.
              </p>
            </Card>
          ) : null}

          {viewState === 'idle' ? (
            <EmptyState
              title="Enter a tracking ID"
              description="The latest public status of your report will appear here. No login or registration is required."
            />
          ) : null}
        </div>

        <div className="space-y-4">
          <Card>
            <h2 className="text-sm font-semibold text-slate-900">
              What this page shows
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">
              The public tracking endpoint returns only the tracking ID,
              category, status, severity, priority, coordinates, and submission
              time.
            </p>
            <p className="mt-3 text-xs leading-relaxed text-slate-500">
              It does not include a timeline, department assignment, address,
              description, or status history.
            </p>
          </Card>

          <Card>
            <h2 className="text-sm font-semibold text-slate-900">
              Need to report something?
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">
              Submit a new civic issue and receive a tracking ID.
            </p>
            <Button
              to="/report"
              variant="secondary"
              size="sm"
              className="mt-3"
            >
              Report an issue
            </Button>
          </Card>
        </div>
      </div>
    </div>
  )
}
