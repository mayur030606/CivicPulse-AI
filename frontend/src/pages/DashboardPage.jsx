import { useEffect, useState } from 'react'
import { getAdminOverview } from '../api/admin.js'
import { getReportSummary } from '../api/reports.js'
import AccessDenied from '../components/auth/AccessDenied.jsx'
import Button from '../components/ui/Button.jsx'
import Card from '../components/ui/Card.jsx'
import EmptyState from '../components/ui/EmptyState.jsx'
import PageHeader from '../components/ui/PageHeader.jsx'
import Spinner from '../components/ui/Spinner.jsx'
import { useAuth } from '../context/AuthContext.jsx'
import {
  adminOverviewState,
  mapAdminOverview,
} from '../lib/adminOverviewView.js'
import {
  categoryBarPercent,
  dashboardState,
  mapDashboardSummary,
  maxGroupCount,
} from '../lib/dashboardView.js'
import { formatDate, formatLabel } from '../lib/format.js'
import { requestErrorKind, requestErrorMessage } from '../lib/requestState.js'
import {
  canAccessAdminOverview,
  canAccessReports,
} from '../lib/routeAccess.js'

const unavailableMetrics = [
  {
    label: 'Open complaints',
    reason:
      'The summary returns raw status groups, not a defined open/resolved split.',
  },
  {
    label: 'Resolved this week',
    reason: 'The summary does not return time-windowed resolution counts.',
  },
  {
    label: 'Average response time',
    reason: 'The summary does not return response-time data.',
  },
  {
    label: 'Recent activity',
    reason: 'The summary returns aggregates only, not an activity feed.',
  },
]

function MetricCard({ label, value, hint }) {
  return (
    <Card>
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p className="mt-2 text-3xl font-bold text-slate-900">{value}</p>
      {hint ? <p className="mt-1 text-xs text-slate-400">{hint}</p> : null}
    </Card>
  )
}

function GroupCard({ title, groups }) {
  return (
    <Card>
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {title}
      </p>
      {groups.length === 0 ? (
        <p className="mt-2 text-sm text-slate-400">No data available</p>
      ) : (
        <ul className="mt-2 space-y-1.5">
          {groups.map((group, index) => (
            <li
              key={`${group.value}-${index}`}
              className="flex items-baseline justify-between gap-3 text-sm"
            >
              <span className="truncate text-slate-600">{group.label}</span>
              <span className="font-semibold text-slate-900">{group.count}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function CategoryCard({ groups }) {
  const max = maxGroupCount(groups)

  return (
    <Card>
      <h2 className="text-sm font-semibold text-slate-900">
        Incidents by category
      </h2>
      <p className="mt-1 text-sm text-slate-500">
        Category counts returned by the reports summary endpoint.
      </p>

      {groups.length === 0 ? (
        <p className="mt-6 text-sm text-slate-400">
          No category data available.
        </p>
      ) : (
        <div className="mt-6 space-y-3">
          {groups.map((group, index) => {
            const percent = categoryBarPercent(group.count, max)

            return (
              <div key={`${group.value}-${index}`}>
                <div className="flex justify-between text-xs text-slate-500">
                  <span>{group.label}</span>
                  <span>{group.count}</span>
                </div>
                <div className="mt-1 h-2 rounded-full bg-slate-100">
                  <div
                    className="h-2 rounded-full bg-civic-500"
                    style={{ width: `${percent}%` }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}

function UnavailableMetricsCard() {
  return (
    <Card>
      <h2 className="text-sm font-semibold text-slate-900">
        Unavailable metrics
      </h2>
      <p className="mt-1 text-sm text-slate-500">
        These dashboard metrics are not provided by the reports summary
        endpoint.
      </p>

      <ul className="mt-4 space-y-3">
        {unavailableMetrics.map((metric) => (
          <li
            key={metric.label}
            className="rounded-lg bg-slate-50 px-3 py-2.5"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-medium text-slate-700">
                {metric.label}
              </span>
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Unavailable
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-500">{metric.reason}</p>
          </li>
        ))}
      </ul>
    </Card>
  )
}

function ServicesCard({ services }) {
  return (
    <Card>
      <h2 className="text-sm font-semibold text-slate-900">Service status</h2>
      <p className="mt-1 text-sm text-slate-500">
        Configuration and implementation flags returned by the admin overview.
      </p>

      {services.length === 0 ? (
        <p className="mt-6 text-sm text-slate-400">
          No service status was returned.
        </p>
      ) : (
        <ul className="mt-4 space-y-3">
          {services.map((service, index) => (
            <li
              key={`${service.name}-${index}`}
              className="rounded-lg border border-slate-200 px-3 py-2.5"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-medium text-slate-800">
                  {service.name || 'Unnamed service'}
                </span>
                <div className="flex flex-wrap gap-1.5">
                  <span
                    className={
                      service.configured
                        ? 'rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700'
                        : 'rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600'
                    }
                  >
                    {service.configured ? 'Configured' : 'Not configured'}
                  </span>
                  <span
                    className={
                      service.implemented
                        ? 'rounded-full bg-civic-50 px-2 py-0.5 text-xs font-semibold text-civic-700'
                        : 'rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600'
                    }
                  >
                    {service.implemented ? 'Implemented' : 'Not implemented'}
                  </span>
                </div>
              </div>
              {service.note ? (
                <p className="mt-1 text-xs text-slate-500">{service.note}</p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function DataError({ error, title, onRetry }) {
  const kind = requestErrorKind(error)

  if (kind === 'forbidden') {
    return (
      <AccessDenied
        compact
        title="Access denied"
        description="The backend denied this request for your role."
      />
    )
  }

  if (kind === 'unauthorized') {
    return (
      <EmptyState
        title="Session expired"
        description={requestErrorMessage(error)}
        action={<Button to="/login">Sign in again</Button>}
      />
    )
  }

  return (
    <EmptyState
      title={title}
      description={requestErrorMessage(error, 'Unable to load dashboard data.')}
      action={<Button onClick={onRetry}>Try again</Button>}
    />
  )
}

function AdminOverviewSection({ overview, loading, error, onRetry }) {
  const state = adminOverviewState({ loading, error, overview })
  const view = mapAdminOverview(overview ?? {})

  return (
    <section className="space-y-4" aria-labelledby="admin-overview-heading">
      <div>
        <h2
          id="admin-overview-heading"
          className="text-lg font-semibold text-slate-900"
        >
          Administrator overview
        </h2>
        <p className="mt-1 text-sm text-slate-500">
          Aggregate counts and service status from the admin overview endpoint.
        </p>
      </div>

      {state === 'loading' ? <Spinner label="Loading admin overview…" /> : null}

      {state === 'error' ? (
        <DataError
          error={error}
          title="Could not load the administrator overview"
          onRetry={onRetry}
        />
      ) : null}

      {state === 'empty' ? (
        <EmptyState
          title="No administrator overview available"
          description="The admin overview endpoint did not return a payload."
          action={<Button onClick={onRetry}>Try again</Button>}
        />
      ) : null}

      {state === 'ready' ? (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <MetricCard
              label="Incidents"
              value={view.incidentsTotal}
              hint="Rows in the incidents table"
            />
            <MetricCard
              label="Citizen reports"
              value={view.citizenReportsTotal}
              hint="Rows in citizen_reports"
            />
            <MetricCard
              label="Incident images"
              value={view.incidentImagesTotal}
              hint="Rows in incident_images"
            />
            <MetricCard
              label="Status changes"
              value={view.statusHistoryTotal}
              hint="Rows in status_history"
            />
            <MetricCard
              label="Departments"
              value={view.departmentsTotal}
              hint="Rows in departments"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <GroupCard
              title="Incident status (admin overview)"
              groups={view.incidentsByStatus}
            />
            <ServicesCard services={view.services} />
          </div>
        </div>
      ) : null}
    </section>
  )
}

function ReportSummarySection({ summary, loading, error, onRetry }) {
  const state = dashboardState({ loading, error, summary })
  const view = mapDashboardSummary(summary ?? {})

  return (
    <section className="space-y-4" aria-labelledby="report-summary-heading">
      <div>
        <h2
          id="report-summary-heading"
          className="text-lg font-semibold text-slate-900"
        >
          Incident reports
        </h2>
        <p className="mt-1 text-sm text-slate-500">
          Aggregate totals from the reports summary endpoint.
        </p>
      </div>

      {state === 'loading' ? <Spinner label="Loading report summary…" /> : null}

      {state === 'error' ? (
        <DataError
          error={error}
          title="Could not load the report summary"
          onRetry={onRetry}
        />
      ) : null}

      {state === 'empty' ? (
        <EmptyState
          title="No incidents yet"
          description="The reports summary is empty. Once incidents are submitted, status, priority, severity and category totals will appear here."
          action={<Button to="/report">Report an issue</Button>}
        />
      ) : null}

      {state === 'ready' ? (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              label="Total incidents"
              value={view.total}
              hint="All reports in the summary"
            />
            <GroupCard title="Status" groups={view.byStatus} />
            <GroupCard title="Priority" groups={view.byPriority} />
            <GroupCard title="Severity" groups={view.bySeverity} />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <CategoryCard groups={view.byCategory} />
            <UnavailableMetricsCard />
          </div>
        </div>
      ) : null}
    </section>
  )
}

function AccountCard({ user }) {
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Signed in as
          </p>
          <h2 className="mt-1 text-lg font-semibold text-slate-900">
            {user?.email || 'Staff account'}
          </h2>
        </div>
        <span className="rounded-full bg-civic-50 px-2.5 py-0.5 text-xs font-semibold text-civic-700 ring-1 ring-inset ring-civic-200">
          {formatLabel(user?.role, 'Staff')}
        </span>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-slate-100 pt-4 text-xs text-slate-500 sm:grid-cols-5">
        <div>
          <dt className="font-medium text-slate-400">Account ID</dt>
          <dd className="mt-0.5 text-slate-700">{user?.id ?? '—'}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-400">Role</dt>
          <dd className="mt-0.5 text-slate-700">
            {formatLabel(user?.role, 'Staff')}
          </dd>
        </div>
        <div>
          <dt className="font-medium text-slate-400">Status</dt>
          <dd className="mt-0.5 text-slate-700">
            {user?.is_active ? 'Active' : 'Inactive'}
          </dd>
        </div>
        <div>
          <dt className="font-medium text-slate-400">Created</dt>
          <dd className="mt-0.5 text-slate-700">
            {formatDate(user?.created_at)}
          </dd>
        </div>
        <div>
          <dt className="font-medium text-slate-400">Last sign-in</dt>
          <dd className="mt-0.5 text-slate-700">
            {formatDate(user?.last_login_at)}
          </dd>
        </div>
      </dl>
    </Card>
  )
}

function ViewerAccessCard() {
  return (
    <Card className="border-amber-200 bg-amber-50">
      <h2 className="text-sm font-semibold text-amber-950">
        Read-only viewer account
      </h2>
      <p className="mt-2 max-w-3xl text-sm text-amber-900">
        The API permits viewer accounts to access their own account details
        only. Incident records, report aggregates and the administrator
        overview remain restricted to dispatcher and administrator roles.
      </p>
    </Card>
  )
}

export default function DashboardPage() {
  const { user } = useAuth()
  const reportsAllowed = canAccessReports(user)
  const adminAllowed = canAccessAdminOverview(user)
  const isViewer = user?.role === 'viewer'

  const [summary, setSummary] = useState(null)
  const [summaryLoading, setSummaryLoading] = useState(reportsAllowed)
  const [summaryError, setSummaryError] = useState(null)

  const [overview, setOverview] = useState(null)
  const [overviewLoading, setOverviewLoading] = useState(adminAllowed)
  const [overviewError, setOverviewError] = useState(null)

  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false

    if (!reportsAllowed) {
      setSummary(null)
      setSummaryError(null)
      setSummaryLoading(false)
      return () => {
        cancelled = true
      }
    }

    setSummaryLoading(true)
    setSummaryError(null)

    getReportSummary()
      .then((data) => {
        if (cancelled) return
        setSummary(data ?? null)
        setSummaryError(null)
      })
      .catch((requestError) => {
        if (cancelled) return
        setSummary(null)
        setSummaryError(requestError)
      })
      .finally(() => {
        if (!cancelled) setSummaryLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [reportsAllowed, reloadKey])

  useEffect(() => {
    let cancelled = false

    if (!adminAllowed) {
      setOverview(null)
      setOverviewError(null)
      setOverviewLoading(false)
      return () => {
        cancelled = true
      }
    }

    setOverviewLoading(true)
    setOverviewError(null)

    getAdminOverview()
      .then((data) => {
        if (cancelled) return
        setOverview(data ?? null)
        setOverviewError(null)
      })
      .catch((requestError) => {
        if (cancelled) return
        setOverview(null)
        setOverviewError(requestError)
      })
      .finally(() => {
        if (!cancelled) setOverviewLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [adminAllowed, reloadKey])

  function refresh() {
    setReloadKey((key) => key + 1)
  }

  const title = isViewer
    ? 'Staff account'
    : user?.role === 'admin'
      ? 'City operations dashboard'
      : 'Dispatch dashboard'

  const description = isViewer
    ? 'Your read-only staff account and the information your role is permitted to access.'
    : user?.role === 'admin'
      ? 'Administrator overview and aggregate incident reports from the protected API.'
      : 'Aggregate incident reports available to dispatcher accounts.'

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Staff operations"
        title={title}
        description={description}
        actions={
          reportsAllowed || adminAllowed ? (
            <Button variant="secondary" size="sm" onClick={refresh}>
              Refresh
            </Button>
          ) : null
        }
      />

      <AccountCard user={user} />

      {isViewer ? <ViewerAccessCard /> : null}

      {adminAllowed ? (
        <AdminOverviewSection
          overview={overview}
          loading={overviewLoading}
          error={overviewError}
          onRetry={refresh}
        />
      ) : null}

      {reportsAllowed ? (
        <ReportSummarySection
          summary={summary}
          loading={summaryLoading}
          error={summaryError}
          onRetry={refresh}
        />
      ) : null}
    </div>
  )
}
