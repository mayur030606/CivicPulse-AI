import {
  INCIDENT_CATEGORIES,
  INCIDENT_STATUSES,
  PRIORITIES,
  SEVERITIES,
} from './constants.js'
import { formatCoordinate, formatLabel, formatStatusLabel } from './format.js'

const CATEGORY_LABELS = new Map(
  INCIDENT_CATEGORIES.map(({ value, label }) => [value, label]),
)
const SEVERITY_LABELS = new Map(
  SEVERITIES.map(({ value, label }) => [value, label]),
)
const PRIORITY_LABELS = new Map(
  PRIORITIES.map(({ value, label }) => [value, label]),
)

function labelFromMap(labels, value, fallback) {
  if (value == null || value === '') return fallback

  const key = String(value).trim().toLowerCase()
  return labels.get(key) ?? formatLabel(value)
}

export function incidentCategoryLabel(category) {
  return labelFromMap(CATEGORY_LABELS, category, 'Uncategorised')
}

export function incidentSeverityLabel(severity) {
  return labelFromMap(SEVERITY_LABELS, severity, 'Not set')
}

export function incidentPriorityLabel(priority) {
  return labelFromMap(PRIORITY_LABELS, priority, 'Not set')
}

export function incidentStatusLabel(status) {
  return formatStatusLabel(status)
}

export function isAllowedIncidentStatus(status) {
  return INCIDENT_STATUSES.some((option) => option.value === status)
}

export function formatIncidentCoordinates(latitude, longitude) {
  if (
    latitude == null ||
    longitude == null ||
    latitude === '' ||
    longitude === ''
  ) {
    return '—'
  }

  const lat = Number(latitude)
  const lng = Number(longitude)

  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return '—'

  return `${formatCoordinate(lat)}, ${formatCoordinate(lng)}`
}

export function incidentToCard(incident = {}) {
  return {
    id: incident.id,
    trackingId: incident.tracking_id ?? '',
    category: incident.category ?? '',
    categoryLabel: incidentCategoryLabel(incident.category),
    description: incident.description ?? '',
    severity: incident.severity ?? '',
    severityLabel: incidentSeverityLabel(incident.severity),
    priority: incident.priority ?? '',
    priorityLabel: incidentPriorityLabel(incident.priority),
    status: incident.status ?? '',
    statusLabel: incidentStatusLabel(incident.status),
    latitude: incident.latitude,
    longitude: incident.longitude,
    coordinatesLabel: formatIncidentCoordinates(
      incident.latitude,
      incident.longitude,
    ),
    createdAt: incident.created_at,
  }
}

export function incidentListState({
  loading = false,
  error = '',
  incidents = [],
} = {}) {
  if (loading) return 'loading'
  if (error) return 'error'
  if (!Array.isArray(incidents) || incidents.length === 0) return 'empty'
  return 'list'
}

export function incidentFilterParams({
  category,
  status,
  severity,
  priority,
} = {}) {
  return {
    category: category || undefined,
    status: status || undefined,
    severity: severity || undefined,
    priority: priority || undefined,
  }
}
