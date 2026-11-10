import apiClient from './client.js'

/**
 * Fields accepted by the backend ``IncidentCreate`` schema. Unknown keys are
 * dropped so callers cannot accidentally send fields the API does not accept.
 * The tracking ID is always generated server-side and is never forwarded.
 */
const INCIDENT_CREATE_FIELDS = [
  'category',
  'description',
  'severity',
  'priority',
  'latitude',
  'longitude',
  'status',
]

/**
 * Fields accepted by the backend ``IncidentUpdate`` schema. Status values are
 * still validated by the API; the frontend only exposes the confirmed
 * workflow values in its select control.
 */
const INCIDENT_UPDATE_FIELDS = [
  'category',
  'description',
  'severity',
  'priority',
  'status',
]

function pickDefined(source, fields) {
  return fields.reduce((result, field) => {
    if (source[field] !== undefined) {
      result[field] = source[field]
    }
    return result
  }, {})
}

export async function listIncidents({
  category,
  incidentType,
  status,
  severity,
  priority,
  limit = 100,
  offset,
} = {}) {
  const { data } = await apiClient.get('/incidents', {
    params: {
      // The backend filter is ``category``. Keep ``incidentType`` as a
      // backwards-compatible alias for existing callers, but never send the
      // unsupported ``incident_type`` query parameter.
      category: category ?? incidentType,
      status,
      severity,
      priority,
      limit,
      offset,
    },
  })
  return data
}

export async function createIncident(payload = {}) {
  const body = pickDefined(payload, INCIDENT_CREATE_FIELDS)
  const { data } = await apiClient.post('/incidents', body)
  return data
}

export async function getIncident(incidentId) {
  const { data } = await apiClient.get(`/incidents/${incidentId}`)
  return data
}

export async function updateIncident(incidentId, payload = {}) {
  const body = pickDefined(payload, INCIDENT_UPDATE_FIELDS)
  // The shared Axios interceptor adds the CSRF header for PATCH requests.
  const { data } = await apiClient.patch(`/incidents/${incidentId}`, body)
  return data
}
