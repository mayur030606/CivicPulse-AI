import apiClient from './client.js'

/**
 * Fetch the administrator-only operational overview.
 *
 * The response contains aggregate counts and service status only. Callers
 * should display exactly the fields returned by the backend.
 */
export async function getAdminOverview() {
  const { data } = await apiClient.get('/admin/overview')
  return data
}
