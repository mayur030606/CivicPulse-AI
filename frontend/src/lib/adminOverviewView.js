import { mapGroupCounts } from './dashboardView.js'

function toCount(value) {
  const count = Number(value)
  if (!Number.isFinite(count) || count < 0) return 0
  return Math.trunc(count)
}

function mapService(service = {}) {
  return {
    name: String(service?.name ?? ''),
    configured: Boolean(service?.configured),
    implemented: Boolean(service?.implemented),
    note: String(service?.note ?? ''),
  }
}

/**
 * Map only the fields returned by `GET /api/v1/admin/overview`.
 *
 * The admin overview intentionally contains aggregate counts and service
 * status only. Do not add response times, trends, or other invented metrics.
 */
export function mapAdminOverview(overview = {}) {
  const source = overview && typeof overview === 'object' ? overview : {}

  return {
    incidentsTotal: toCount(source.incidents_total),
    citizenReportsTotal: toCount(source.citizen_reports_total),
    incidentImagesTotal: toCount(source.incident_images_total),
    statusHistoryTotal: toCount(source.status_history_total),
    departmentsTotal: toCount(source.departments_total),
    incidentsByStatus: mapGroupCounts(source.incidents_by_status, 'status'),
    services: Array.isArray(source.services)
      ? source.services.map(mapService)
      : [],
  }
}

export function adminOverviewState({
  loading = false,
  error = null,
  overview = null,
} = {}) {
  if (loading) return 'loading'
  if (error) return 'error'
  if (!overview) return 'empty'
  return 'ready'
}
