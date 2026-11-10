import apiClient from './client.js'

/**
 * Look up a public incident status by its tracking ID.
 *
 * The backend also trims and uppercases the ID. The frontend trims it before
 * validation and encodes it so spaces or URL characters stay in one path
 * segment. The response is returned unchanged because it is a public-safe
 * subset of the incident record.
 */
export async function getTracking(trackingId) {
  const id = String(trackingId ?? '').trim()

  if (!id) {
    throw new Error('Tracking ID is required.')
  }

  const { data } = await apiClient.get(`/tracking/${encodeURIComponent(id)}`)
  return data
}
