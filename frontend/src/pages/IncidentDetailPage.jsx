import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getIncident, updateIncident } from '../api/incidents.js'
import AccessDenied from '../components/auth/AccessDenied.jsx'
import { PriorityBadge, StatusBadge } from '../components/ui/Badge.jsx'
import Button from '../components/ui/Button.jsx'
import Card from '../components/ui/Card.jsx'
import EmptyState from '../components/ui/EmptyState.jsx'
import PageHeader from '../components/ui/PageHeader.jsx'
import Spinner from '../components/ui/Spinner.jsx'
import { useAuth } from '../context/AuthContext.jsx'
import { INCIDENT_STATUSES } from '../lib/constants.js'
import { formatDate } from '../lib/format.js'
import {
  formatIncidentCoordinates,
  incidentCategoryLabel,
  incidentPriorityLabel,
  incidentSeverityLabel,
  isAllowedIncidentStatus,
} from '../lib/incidentsView.js'
import { requestErrorKind, requestErrorMessage } from '../lib/requestState.js'
import { canUpdateIncidentStatus } from '../lib/routeAccess.js'

export default function IncidentDetailPage() {
  const { incidentId } = useParams()
  const numericId = Number(incidentId)
  const validId = Number.isInteger(numericId) && numericId > 0
  const { user } = useAuth()
  const canUpdate = canUpdateIncidentStatus(user)

  const [incident, setIncident] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [reloadKey, setReloadKey] = useState(0)

  const [selectedStatus, setSelectedStatus] = useState('')
  const [updating, setUpdating] = useState(false)
  const [updateError, setUpdateError] = useState('')
  const [updateMessage, setUpdateMessage] = useState('')

  useEffect(() => {
    let cancelled = false

    if (!validId) {
      setIncident(null)
      setLoading(false)
      setError({ status: 404, message: 'Incident not found.' })
      return () => {
        cancelled = true
      }
    }

    setLoading(true)
    setError(null)

    getIncident(numericId)
      .then((data) => {
        if (cancelled) return
        setIncident(data ?? null)
        setError(null)
      })
      .catch((requestError) => {
        if (cancelled) return
        setIncident(null)
        setError(requestError)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [numericId, reloadKey, validId])

  useEffect(() => {
    if (!incident) {
      setSelectedStatus('')
      return
    }

    setSelectedStatus(
      isAllowedIncidentStatus(incident.status) ? incident.status : '',
    )
  }, [incident])

  function refresh() {
    setLoading(true)
    setError(null)
    setReloadKey((key) => key + 1)
  }

  async function handleStatusSubmit(event) {
    event.preventDefault()

    if (!incident || !selectedStatus || !canUpdate) return
    if (selectedStatus === incident.status) {
      setUpdateError('Choose a different status before updating.')
      return
    }

    setUpdating(true)
    setUpdateError('')
    setUpdateMessage('')

    try {
      const updated = await updateIncident(incident.id, {
        status: selectedStatus,
      })
      setIncident(updated ?? incident)
      setUpdateMessage('Status updated successfully.')
    } catch (requestError) {
      setUpdateError(
        requestErrorMessage(requestError, 'Could not update the status.'),
      )
    } finally {
      setUpdating(false)
    }
  }

  const errorKind = requestErrorKind(error)

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={validId ? `Incident #${numericId}` : 'Incident details'}
        title={
          incident
            ? incidentCategoryLabel(incident.category)
            : 'Incident details'
        }
        description="Protected incident record from the staff API."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button to="/incidents" variant="secondary" size="sm">
              Back to incidents
            </Button>
            <Button variant="ghost" size="sm" onClick={refresh}>
              Refresh
            </Button>
          </div>
        }
      />

      {loading ? <Spinner label="Loading incident…" /> : null}

      {!loading && errorKind === 'forbidden' ? (
        <AccessDenied
          compact
          title="Incident access denied"
          description="The backend denied access to this incident for your account."
        />
      ) : null}

      {!loading && errorKind === 'unauthorized' ? (
        <EmptyState
          title="Session expired"
          description={requestErrorMessage(error)}
          action={<Button to="/login">Sign in again</Button>}
        />
      ) : null}

      {!loading && errorKind === 'not-found' ? (
        <EmptyState
          title="Incident not found"
          description="The incident does not exist or is no longer available."
          action={<Button to="/incidents">Back to incidents</Button>}
        />
      ) : null}

      {!loading && errorKind === 'error' ? (
        <EmptyState
          title="Could not load the incident"
          description={requestErrorMessage(error)}
          action={<Button onClick={refresh}>Try again</Button>}
        />
      ) : null}

      {!loading && incident ? (
        <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
          <Card>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-civic-600">
                  {incidentCategoryLabel(incident.category)}
                </p>
                <p className="mt-2 text-xs font-medium uppercase tracking-wide text-slate-400">
                  Tracking ID
                </p>
                <h2 className="font-mono text-base font-semibold text-slate-900">
                  {incident.tracking_id || '—'}
                </h2>
              </div>
              <div className="flex flex-wrap gap-2">
                <StatusBadge status={incident.status} />
                <PriorityBadge priority={incident.priority} />
              </div>
            </div>

            <p className="mt-4 whitespace-pre-line text-sm text-slate-600">
              {incident.description || 'No description provided.'}
            </p>

            <dl className="mt-5 grid grid-cols-2 gap-3 border-t border-slate-100 pt-4 text-xs text-slate-500 sm:grid-cols-3">
              <div>
                <dt className="font-medium text-slate-400">Incident ID</dt>
                <dd className="mt-0.5 text-slate-700">{incident.id ?? '—'}</dd>
              </div>
              <div>
                <dt className="font-medium text-slate-400">Status</dt>
                <dd className="mt-0.5 text-slate-700">
                  {incident.status || 'Unknown'}
                </dd>
              </div>
              <div>
                <dt className="font-medium text-slate-400">Category</dt>
                <dd className="mt-0.5 text-slate-700">
                  {incidentCategoryLabel(incident.category)}
                </dd>
              </div>
              <div>
                <dt className="font-medium text-slate-400">Severity</dt>
                <dd className="mt-0.5 text-slate-700">
                  {incidentSeverityLabel(incident.severity)}
                </dd>
              </div>
              <div>
                <dt className="font-medium text-slate-400">Priority</dt>
                <dd className="mt-0.5 text-slate-700">
                  {incidentPriorityLabel(incident.priority)}
                </dd>
              </div>
              <div>
                <dt className="font-medium text-slate-400">Location</dt>
                <dd className="mt-0.5 text-slate-700">
                  {formatIncidentCoordinates(
                    incident.latitude,
                    incident.longitude,
                  )}
                </dd>
              </div>
              <div>
                <dt className="font-medium text-slate-400">Reported</dt>
                <dd className="mt-0.5 text-slate-700">
                  {formatDate(incident.created_at)}
                </dd>
              </div>
            </dl>
          </Card>

          <Card>
            <h2 className="text-sm font-semibold text-slate-900">
              Workflow status
            </h2>

            {canUpdate ? (
              <form className="mt-4 space-y-3" onSubmit={handleStatusSubmit}>
                <label
                  htmlFor="incident-status"
                  className="block text-sm font-medium text-slate-700"
                >
                  Change status
                </label>
                <select
                  id="incident-status"
                  name="status"
                  value={selectedStatus}
                  onChange={(event) => {
                    setSelectedStatus(event.target.value)
                    setUpdateError('')
                    setUpdateMessage('')
                  }}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm outline-none focus:border-civic-500 focus:ring-2 focus:ring-civic-200"
                >
                  {!isAllowedIncidentStatus(incident.status) ? (
                    <option value="">Select a status</option>
                  ) : null}
                  {INCIDENT_STATUSES.map((status) => (
                    <option key={status.value} value={status.value}>
                      {status.label}
                    </option>
                  ))}
                </select>

                <Button
                  type="submit"
                  className="w-full"
                  disabled={
                    updating ||
                    !selectedStatus ||
                    selectedStatus === incident.status
                  }
                >
                  {updating ? 'Updating…' : 'Update status'}
                </Button>

                <p className="text-xs text-slate-500">
                  The backend validates the status transition and records an
                  audit row for status changes.
                </p>

                {updateError ? (
                  <p
                    className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700"
                    role="alert"
                  >
                    {updateError}
                  </p>
                ) : null}

                {updateMessage ? (
                  <p
                    className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800"
                    role="status"
                  >
                    {updateMessage}
                  </p>
                ) : null}
              </form>
            ) : (
              <p className="mt-4 text-sm text-slate-600">
                Your account has read-only access. Status updates require a
                dispatcher or administrator role.
              </p>
            )}
          </Card>
        </div>
      ) : null}
    </div>
  )
}
