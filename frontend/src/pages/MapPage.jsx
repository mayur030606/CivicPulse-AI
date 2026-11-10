import { useEffect, useState } from 'react'
import { listIncidents } from '../api/incidents.js'
import AccessDenied from '../components/auth/AccessDenied.jsx'
import StaffSignInRequired from '../components/auth/StaffSignInRequired.jsx'
import IncidentMap from '../components/map/IncidentMap.jsx'
import Button from '../components/ui/Button.jsx'
import Card from '../components/ui/Card.jsx'
import EmptyState from '../components/ui/EmptyState.jsx'
import PageHeader from '../components/ui/PageHeader.jsx'
import Spinner from '../components/ui/Spinner.jsx'
import { useAuth } from '../context/AuthContext.jsx'
import {
  mapPageState,
  mappedIncidentMarkers,
  missingLocationCount,
} from '../lib/mapView.js'
import { requestErrorKind, requestErrorMessage } from '../lib/requestState.js'
import {
  STAFF_ROLES,
  accessStateForRoles,
} from '../lib/routeAccess.js'

const severityStyles = {
  low: 'bg-sky-500',
  medium: 'bg-amber-500',
  high: 'bg-orange-500',
  critical: 'bg-rose-500',
  unknown: 'bg-slate-500',
}

function IncidentMapPage() {
  const [incidents, setIncidents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false

    listIncidents()
      .then((data) => {
        if (cancelled) return
        setIncidents(Array.isArray(data) ? data : [])
        setError(null)
      })
      .catch((requestError) => {
        if (cancelled) return
        setIncidents([])
        setError(requestError)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [reloadKey])

  function refresh() {
    setLoading(true)
    setError(null)
    setReloadKey((key) => key + 1)
  }

  const state = mapPageState({ loading, error, incidents })
  const errorKind = requestErrorKind(error)
  const markers = mappedIncidentMarkers(incidents)
  const missingCount = missingLocationCount(incidents)
  const incidentCountLabel = `${incidents.length} incident${
    incidents.length === 1 ? '' : 's'
  }`

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Geo intelligence"
        title="Incident map"
        description="Live incident reports with valid coordinates from the CivicPulse API."
        actions={
          <Button variant="secondary" size="sm" onClick={refresh}>
            Refresh
          </Button>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <Card className="h-[62vh] min-h-[420px] p-0">
          {state === 'loading' ? (
            <div className="flex h-full items-center justify-center p-6">
              <Spinner label="Loading incidents…" />
            </div>
          ) : null}

          {state === 'error' && errorKind === 'forbidden' ? (
            <div className="flex h-full items-center justify-center p-6">
              <div className="w-full max-w-md">
                <AccessDenied
                  compact
                  title="Incident map unavailable"
                  description="The backend denied incident access for this account."
                />
              </div>
            </div>
          ) : null}

          {state === 'error' && errorKind === 'unauthorized' ? (
            <div className="flex h-full items-center justify-center p-6">
              <div className="w-full max-w-md">
                <EmptyState
                  title="Session expired"
                  description={requestErrorMessage(error)}
                  action={<Button to="/login">Sign in again</Button>}
                />
              </div>
            </div>
          ) : null}

          {state === 'error' &&
          errorKind !== 'forbidden' &&
          errorKind !== 'unauthorized' ? (
            <div className="flex h-full items-center justify-center p-6">
              <div className="w-full max-w-md">
                <EmptyState
                  title="Could not load incidents"
                  description={requestErrorMessage(
                    error,
                    'Unable to load incidents. Make sure the backend is running and try again.',
                  )}
                  action={<Button onClick={refresh}>Try again</Button>}
                />
              </div>
            </div>
          ) : null}

          {state === 'empty' ? (
            <div className="flex h-full items-center justify-center p-6">
              <div className="w-full max-w-md">
                <EmptyState
                  title="No incidents yet"
                  description="Incident markers will appear here once reports are submitted."
                  action={<Button to="/report">Report an issue</Button>}
                />
              </div>
            </div>
          ) : null}

          {state === 'no-location' ? (
            <div className="flex h-full items-center justify-center p-6">
              <div className="w-full max-w-md">
                <EmptyState
                  title="No incidents with coordinates"
                  description={`${incidentCountLabel} returned, but none include latitude and longitude.`}
                  action={<Button onClick={refresh}>Refresh</Button>}
                />
              </div>
            </div>
          ) : null}

          {state === 'ready' ? <IncidentMap markers={markers} /> : null}
        </Card>

        <div className="space-y-4">
          <Card>
            <h2 className="text-sm font-semibold text-slate-900">Legend</h2>
            <ul className="mt-3 space-y-2 text-sm text-slate-600">
              {Object.entries(severityStyles).map(([severity, color]) => (
                <li key={severity} className="flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className={`h-2.5 w-2.5 rounded-full ${color}`}
                  />
                  <span className="capitalize">{severity} severity</span>
                </li>
              ))}
            </ul>
          </Card>

          <Card className="p-0">
            <div className="border-b border-slate-100 px-4 py-3">
              <h2 className="text-sm font-semibold text-slate-900">
                Mapped incidents
              </h2>
              <p className="mt-0.5 text-xs text-slate-500">
                {state === 'loading'
                  ? 'Loading incidents…'
                  : state === 'error'
                    ? 'Incident list unavailable'
                    : `${markers.length} mapped · ${missingCount} without location`}
              </p>
            </div>

            {state === 'error' ? (
              <p className="px-4 py-3 text-sm text-slate-500">
                {requestErrorMessage(error, 'Incident list unavailable.')}
              </p>
            ) : null}

            {state === 'empty' ? (
              <p className="px-4 py-3 text-sm text-slate-500">
                No incidents yet.
              </p>
            ) : null}

            {state === 'no-location' ? (
              <p className="px-4 py-3 text-sm text-slate-500">
                No incidents have latitude and longitude.
              </p>
            ) : null}

            {state === 'ready' ? (
              <ul className="max-h-96 divide-y divide-slate-100 overflow-y-auto">
                {markers.map((marker, index) => (
                  <li
                    key={marker.id ?? marker.trackingId ?? index}
                    className="px-4 py-3"
                  >
                    <p className="text-sm font-medium text-slate-900">
                      {marker.categoryLabel}
                    </p>
                    <p className="mt-0.5 font-mono text-xs text-slate-500">
                      {marker.trackingId || 'No tracking ID'}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      {marker.statusLabel} · {marker.severityLabel} severity
                    </p>
                  </li>
                ))}
              </ul>
            ) : null}

            {state === 'ready' && missingCount > 0 ? (
              <p className="border-t border-slate-100 px-4 py-3 text-xs text-slate-500">
                {missingCount} incident{missingCount === 1 ? '' : 's'} without
                coordinates are not shown on the map.
              </p>
            ) : null}
          </Card>
        </div>
      </div>
    </div>
  )
}

export default function MapPage() {
  const { status, user } = useAuth()
  const access = accessStateForRoles({ status, user, roles: STAFF_ROLES })

  if (access === 'loading') {
    return (
      <div className="py-12">
        <Spinner label="Checking staff access…" />
      </div>
    )
  }

  if (access === 'sign-in') {
    return (
      <StaffSignInRequired
        title="Incident map"
        description="Incident coordinates and protected map data are restricted to signed-in municipal staff. Citizens can still report an issue or track a complaint."
      />
    )
  }

  if (access === 'forbidden') {
    return (
      <AccessDenied
        title="Incident map unavailable"
        description="Your account does not have permission to view incident coordinates."
      />
    )
  }

  return <IncidentMapPage />
}
