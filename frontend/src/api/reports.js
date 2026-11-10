import apiClient from './client.js'

/**
 * Fetch incident aggregates from the confirmed reports summary endpoint.
 *
 * The backend returns ``total`` plus ``by_status``, ``by_priority``,
 * ``by_severity`` and ``by_category`` group counts. This helper intentionally
 * returns the response unchanged so callers do not depend on invented fields.
 */
export async function getReportSummary() {
  const { data } = await apiClient.get('/reports/summary')
  return data
}
