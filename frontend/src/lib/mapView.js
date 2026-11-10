import {
  incidentCategoryLabel,
  incidentPriorityLabel,
  incidentSeverityLabel,
  incidentStatusLabel,
} from './incidentsView.js'

const SEVERITY_COLORS = {
  low: '#0ea5e9',
  medium: '#f59e0b',
  high: '#f97316',
  critical: '#e11d48',
}

export const UNKNOWN_SEVERITY_COLOR = '#64748b'

function toCoordinate(value, min, max) {
  if (value == null) return null
  if (typeof value !== 'number' && typeof value !== 'string') return null
  if (typeof value === 'string' && value.trim() === '') return null

  const number = Number(value)
  if (!Number.isFinite(number) || number < min || number > max) return null

  return number
}

export function incidentCoordinates(incident = {}) {
  const latitude = toCoordinate(incident?.latitude, -90, 90)
  const longitude = toCoordinate(incident?.longitude, -180, 180)

  if (latitude == null || longitude == null) return null

  return { latitude, longitude }
}

export function hasValidCoordinates(incident = {}) {
  return incidentCoordinates(incident) !== null
}

export function incidentSeverityColor(severity) {
  if (severity == null) return UNKNOWN_SEVERITY_COLOR

  const key = String(severity).trim().toLowerCase()
  if (!key) return UNKNOWN_SEVERITY_COLOR

  return SEVERITY_COLORS[key] || UNKNOWN_SEVERITY_COLOR
}

export function mapIncidentToMarker(incident = {}) {
  const coordinates = incidentCoordinates(incident)
  if (!coordinates) return null

  return {
    id: incident.id,
    trackingId: incident.tracking_id ?? '',
    category: incident.category ?? '',
    categoryLabel: incidentCategoryLabel(incident.category),
    description: incident.description ?? '',
    severity: incident.severity ?? '',
    severityLabel: incidentSeverityLabel(incident.severity),
    severityColor: incidentSeverityColor(incident.severity),
    priority: incident.priority ?? '',
    priorityLabel: incidentPriorityLabel(incident.priority),
    status: incident.status ?? '',
    statusLabel: incidentStatusLabel(incident.status),
    latitude: coordinates.latitude,
    longitude: coordinates.longitude,
    createdAt: incident.created_at,
  }
}

export function mappedIncidentMarkers(incidents = []) {
  if (!Array.isArray(incidents)) return []

  return incidents.map((incident) => mapIncidentToMarker(incident)).filter(Boolean)
}

export function missingLocationCount(incidents = []) {
  if (!Array.isArray(incidents)) return 0

  return incidents.filter((incident) => !hasValidCoordinates(incident)).length
}

export function mapPageState({
  loading = false,
  error = '',
  incidents = [],
} = {}) {
  if (loading) return 'loading'
  if (error) return 'error'
  if (!Array.isArray(incidents) || incidents.length === 0) return 'empty'
  if (!incidents.some((incident) => hasValidCoordinates(incident))) {
    return 'no-location'
  }
  return 'ready'
}
