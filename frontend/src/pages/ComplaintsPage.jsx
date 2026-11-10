import { useEffect, useState } from 'react'
import { listIncidents } from '../api/incidents.js'
import AccessDenied from '../components/auth/AccessDenied.jsx'
import StaffSignInRequired from '../components/auth/StaffSignInRequired.jsx'
import ComplaintCard from '../components/complaints/ComplaintCard.jsx'
import Button from '../components/ui/Button.jsx'
import EmptyState from '../components/ui/EmptyState.jsx'
import PageHeader from '../components/ui/PageHeader.jsx'
import Spinner from '../components/ui/Spinner.jsx'
import { useAuth } from '../context/AuthContext.jsx'
import {
  INCIDENT_CATEGORIES,
  INCIDENT_STATUSES,
  PRIORITIES,
  SEVERITIES,
} from '../lib/constants.js'
import { incidentFilterParams, incidentListState } from '../lib/incidentsView.js'
import { requestErrorKind, requestErrorMessage } from '../lib/requestState.js'
import {
  STAFF_ROLES,
  accessStateForRoles,
} from '../lib/routeAccess.js'

const initialFilters = {
  category: '',
  status: '',
  severity: '',
  priority: '',
}

function FilterSelect({
  id,
  label,
  name,
  value,
  onChange,
  options,
  allLabel,
}) {
  return (
    <label htmlFor={id} className="text-sm font-medium text-slate-700">
      <span className="mb-1 block">{label}</span>
      <select
        id={id}
        name={name}
        value={value}
        onChange={onChange}
        className="w-full min-w-[150px] rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm outline-none focus:border-civic-500 focus:ring-2 focus:ring-civic-200"
      >
        <option value="">{allLabel}</option>
        {options.map((item) => (
          <option key={item.value} value={item.value}>
            {item.label}
          </option>
        ))}
      </select>
    </label>
  )
}

function ComplaintsDirectory() {
  const [incidents, setIncidents] = useState([])
  const [filters, setFilters] = useState(initialFilters)
  const [reloadKey, setReloadKey] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    listIncidents(incidentFilterParams(filters))
      .then((data) => {
        if (cancelled) return
        setIncidents(Array.isArray(data) ? data : [])
        setError(null)
      })
      .catch((requestError) => {
        if (cancelled) return
        setError(requestError)
        setIncidents([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [filters, reloadKey])

  function handleFilterChange(event) {
    const { name, value } = event.target
    setLoading(true)
    setFilters((current) => ({ ...current, [name]: value }))
  }

  function refresh() {
    setLoading(true)
    setError(null)
    setReloadKey((key) => key + 1)
  }

  function clearFilters() {
    setLoading(true)
    setFilters(initialFilters)
  }

  const viewState = incidentListState({ loading, error, incidents })
  const errorKind = requestErrorKind(error)
  const filtersActive = Object.values(filters).some(Boolean)

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Citizen reports"
        title="Complaints"
        description="Live incident reports from the CivicPulse API."
        actions={
          <Button to="/report" size="sm">
            New report
          </Button>
        }
      />

      <div className="flex flex-wrap items-end gap-3">
        <FilterSelect
          id="category-filter"
          label="Category"
          name="category"
          value={filters.category}
          onChange={handleFilterChange}
          options={INCIDENT_CATEGORIES}
          allLabel="All categories"
        />
        <FilterSelect
          id="status-filter"
          label="Status"
          name="status"
          value={filters.status}
          onChange={handleFilterChange}
          options={INCIDENT_STATUSES}
          allLabel="All statuses"
        />
        <FilterSelect
          id="severity-filter"
          label="Severity"
          name="severity"
          value={filters.severity}
          onChange={handleFilterChange}
          options={SEVERITIES}
          allLabel="All severities"
        />
        <FilterSelect
          id="priority-filter"
          label="Priority"
          name="priority"
          value={filters.priority}
          onChange={handleFilterChange}
          options={PRIORITIES}
          allLabel="All priorities"
        />
        <Button variant="ghost" size="sm" onClick={refresh}>
          Refresh
        </Button>
      </div>

      {viewState === 'loading' ? <Spinner label="Loading incidents…" /> : null}

      {viewState === 'error' && errorKind === 'forbidden' ? (
        <AccessDenied
          compact
          title="Complaint directory unavailable"
          description="The backend denied incident access for this account."
        />
      ) : null}

      {viewState === 'error' && errorKind === 'unauthorized' ? (
        <EmptyState
          title="Session expired"
          description={requestErrorMessage(error)}
          action={<Button to="/login">Sign in again</Button>}
        />
      ) : null}

      {viewState === 'error' &&
      errorKind !== 'forbidden' &&
      errorKind !== 'unauthorized' ? (
        <EmptyState
          title="Could not load incidents"
          description={requestErrorMessage(
            error,
            'Unable to load incidents. Make sure the backend is running and try again.',
          )}
          action={<Button onClick={refresh}>Try again</Button>}
        />
      ) : null}

      {viewState === 'empty' ? (
        <EmptyState
          title={
            filtersActive
              ? 'No incidents match these filters'
              : 'No incidents yet'
          }
          description={
            filtersActive
              ? 'Try changing or clearing the category, status, severity, or priority filters.'
              : 'Submit the first report to see it appear here.'
          }
          action={
            filtersActive ? (
              <Button variant="secondary" onClick={clearFilters}>
                Clear filters
              </Button>
            ) : (
              <Button to="/report">Report an issue</Button>
            )
          }
        />
      ) : null}

      {viewState === 'list' ? (
        <div className="space-y-3">
          <p className="text-xs text-slate-500">
            {incidents.length} incident{incidents.length === 1 ? '' : 's'}
          </p>
          {incidents.map((incident) => (
            <ComplaintCard key={incident.id} incident={incident} />
          ))}
        </div>
      ) : null}
    </div>
  )
}

export default function ComplaintsPage() {
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
        title="Complaint directory"
        description="Live incident records are restricted to signed-in municipal staff. Citizens can report an issue or track a complaint by ID."
      />
    )
  }

  if (access === 'forbidden') {
    return (
      <AccessDenied
        title="Complaint directory unavailable"
        description="Your account does not have permission to view incident records."
      />
    )
  }

  return <ComplaintsDirectory />
}
