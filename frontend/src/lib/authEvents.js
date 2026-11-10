/**
 * Browser-wide authentication events.
 *
 * The Axios client emits this event when a protected request returns 401 so
 * the auth provider can clear its in-memory session and let the route guards
 * redirect to the login page. Session tokens are never stored in browser
 * storage; the HttpOnly cookie remains the source of truth.
 */
export const AUTH_UNAUTHORIZED_EVENT = 'civicpulse:auth-unauthorized'

export function notifyUnauthorized() {
  if (
    typeof window !== 'undefined' &&
    typeof window.dispatchEvent === 'function'
  ) {
    window.dispatchEvent(new Event(AUTH_UNAUTHORIZED_EVENT))
  }
}
