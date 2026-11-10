import apiClient from './client.js'

/**
 * Authenticate with the backend. The response body contains the staff user;
 * the session and CSRF values are set as cookies by the server.
 *
 * Credentials are never persisted in localStorage/sessionStorage and are never
 * logged by this module.
 */
export async function login(email, password) {
  const { data } = await apiClient.post('/auth/login', {
    email: String(email ?? '')
      .trim()
      .toLowerCase(),
    password: String(password ?? ''),
  })

  return data?.user ?? null
}

/**
 * Restore the current session from the HttpOnly cookie.
 */
export async function getCurrentUser() {
  const { data } = await apiClient.get('/auth/me')
  return data
}

/**
 * Revoke the current server-side session and clear both auth cookies. The
 * request interceptor attaches the CSRF header required by the backend.
 */
export async function logout() {
  await apiClient.post('/auth/logout')
}
