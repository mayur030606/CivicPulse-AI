import {
  formatIncidentCoordinates,
  incidentCategoryLabel,
  incidentPriorityLabel,
  incidentSeverityLabel,
  incidentStatusLabel,
} from './incidentsView.js'
import { formatDate } from './format.js'

export const TRACKING_QUERY_PARAM = 'trackingId'

export function normalizeTrackingId(value) {
  return String(value ?? '').trim()
}

export function validateTrackingId(value) {
  const id = normalizeTrackingId(value)

  if (!id) return 'Enter a tracking ID.'
  if (id.length < 3) return 'Tracking IDs are at least 3 characters.'
  if (id.length > 50) return 'Tracking IDs are at most 50 characters.'

  return ''
}

export function trackingPath(trackingId) {
  const id = normalizeTrackingId(trackingId)

  if (!id) return '/tracking'

  return `/tracking?${TRACKING_QUERY_PARAM}=${encodeURIComponent(id)}`
}

export function mapTrackingResult(data) {
  const source = data ?? {}

  return {
    trackingId: source.tracking_id ?? '',
    category: source.category ?? '',
    categoryLabel: incidentCategoryLabel(source.category),
    status: source.status ?? '',
    statusLabel: incidentStatusLabel(source.status),
    severity: source.severity ?? '',
    severityLabel: incidentSeverityLabel(source.severity),
    priority: source.priority ?? '',
    priorityLabel: incidentPriorityLabel(source.priority),
    latitude: source.latitude,
    longitude: source.longitude,
    coordinatesLabel: formatIncidentCoordinates(
      source.latitude,
      source.longitude,
    ),
    createdAt: source.created_at,
    createdLabel: formatDate(source.created_at),
  }
}

export function trackingLookupState({
  loading = false,
  error = null,
  result = null,
} = {}) {
  if (loading) return 'loading'
  if (error) return error.status === 404 ? 'not-found' : 'error'
  if (result) return 'success'
  return 'idle'
}

export function describeTrackingError(error) {
  if (error?.status === 404) {
    return {
      title: 'Tracking ID not found',
      message: error.message || 'Report not found. Check the tracking ID.',
      guidance: 'Check the ID from your report submission and try again.',
    }
  }

  if (error?.status === 422) {
    return {
      title: 'Tracking ID is not valid',
      message: error.message || 'The tracking ID was rejected by the server.',
      guidance: 'Tracking IDs must be between 3 and 50 characters.',
    }
  }

  if (!error?.status) {
    return {
      title: 'Could not reach the server',
      message:
        error?.message || 'The tracking request did not reach the server.',
      guidance:
        'Check your connection and make sure the backend is running, then try again.',
    }
  }

  return {
    title: 'Could not look up the report',
    message: error?.message || 'The tracking service returned an error.',
    guidance: 'Please try again in a moment.',
  }
}
