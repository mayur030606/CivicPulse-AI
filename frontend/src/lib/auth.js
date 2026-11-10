/**
 * Authentication and authorization primitives shared by the UI.
 *
 * The backend remains authoritative. These helpers only control navigation,
 * forms and presentation so the interface does not offer actions the API
 * would reject. Session tokens are intentionally never stored here.
 */

export const AUTH_STATUS = Object.freeze({
  LOADING: 'loading',
  AUTHENTICATED: 'authenticated',
  ANONYMOUS: 'anonymous',
})

export const USER_ROLES = Object.freeze(['admin', 'dispatcher', 'viewer'])
export const STAFF_ROLES = Object.freeze(['admin', 'dispatcher'])
export const ADMIN_ROLES = Object.freeze(['admin'])
export const AUTHENTICATED_ROLES = USER_ROLES

export function initialAuthState() {
  return {
    status: AUTH_STATUS.LOADING,
    user: null,
    sessionExpired: false,
    error: '',
  }
}

/**
 * Normalize a user returned by `/auth/me` or `/auth/login`. Unknown roles are
 * rejected so a malformed response can never grant staff UI access.
 */
export function normalizeUser(user) {
  if (!user || typeof user !== 'object') return null

  const role = String(user.role ?? '')
    .trim()
    .toLowerCase()

  if (!USER_ROLES.includes(role)) return null

  return { ...user, role }
}

export function hasAnyRole(user, roles) {
  if (!user || !Array.isArray(roles) || roles.length === 0) return false
  return roles.includes(user.role)
}

export function authReducer(state, action) {
  switch (action?.type) {
    case 'restore_succeeded':
    case 'login_succeeded': {
      const user = normalizeUser(action.user)
      if (!user) {
        return {
          status: AUTH_STATUS.ANONYMOUS,
          user: null,
          sessionExpired: false,
          error: 'The server returned an unsupported account response.',
        }
      }

      return {
        status: AUTH_STATUS.AUTHENTICATED,
        user,
        sessionExpired: false,
        error: '',
      }
    }

    case 'restore_failed':
      return {
        status: AUTH_STATUS.ANONYMOUS,
        user: null,
        sessionExpired: false,
        error: String(action.error || ''),
      }

    case 'logout_succeeded':
      return {
        status: AUTH_STATUS.ANONYMOUS,
        user: null,
        sessionExpired: false,
        error: '',
      }

    case 'session_expired':
      if (state.status !== AUTH_STATUS.AUTHENTICATED) return state
      return {
        status: AUTH_STATUS.ANONYMOUS,
        user: null,
        sessionExpired: true,
        error: '',
      }

    case 'clear_session_expired':
      return { ...state, sessionExpired: false }

    default:
      return state
  }
}

export function isUnauthorizedError(error) {
  return error?.status === 401
}

export function isForbiddenError(error) {
  return error?.status === 403
}

export function isNotFoundError(error) {
  return error?.status === 404
}

/**
 * Convert an API error into a short, non-sensitive authentication message.
 * The backend deliberately returns a generic 401 for failed logins.
 */
export function authErrorMessage(
  error,
  fallback = 'Sign in failed. Please try again.',
) {
  if (!error) return fallback

  if (error.status === 401) return 'Email or password is incorrect.'
  if (error.status === 403) {
    return 'You do not have permission to sign in with this account.'
  }
  if (error.status === 429) {
    return 'Too many sign-in attempts. Try again in a little while.'
  }
  if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
    return 'The sign-in request timed out. Try again.'
  }
  if (error.status == null) {
    return 'Unable to reach the server. Check that the backend is running and try again.'
  }

  const message = typeof error.message === 'string' ? error.message.trim() : ''
  return message || fallback
}

/**
 * Only allow same-origin, internal redirect targets. This prevents an
 * attacker-supplied `from` state from becoming an open redirect after login.
 */
export function safeRedirectPath(value, fallback = '/dashboard') {
  if (typeof value !== 'string') return fallback

  const path = value.trim()
  if (!path.startsWith('/')) return fallback
  if (path.startsWith('//') || path.startsWith('/\\')) return fallback
  if (path === '/login' || path.startsWith('/login?') || path.startsWith('/login#')) {
    return fallback
  }

  return path
}
