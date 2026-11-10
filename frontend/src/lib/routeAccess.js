/**
 * Route and feature access rules for the staff-facing interface.
 *
 * These checks make the UI coherent; they are not a security boundary. Every
 * protected request still goes through the backend role and CSRF checks.
 */

import {
  ADMIN_ROLES,
  AUTH_STATUS,
  AUTHENTICATED_ROLES,
  STAFF_ROLES,
  hasAnyRole,
  safeRedirectPath,
} from './auth.js'

export { ADMIN_ROLES, AUTHENTICATED_ROLES, STAFF_ROLES }

/**
 * Citizen-facing routes that must remain available without a staff session.
 * `/complaints` and `/map` are listed here because their URLs are preserved,
 * but their protected data is not fetched until a staff role is present.
 */
export const PUBLIC_ROUTE_PATHS = Object.freeze([
  '/',
  '/report',
  '/tracking',
  '/complaints',
  '/map',
  '/login',
])

function normalizePathname(value) {
  const pathname = String(value || '/').split(/[?#]/, 1)[0]
  const normalized = pathname.replace(/\/+$/, '')
  return normalized || '/'
}

/**
 * Return the roles required by a protected path, or `null` for a public path.
 */
export function routeAccessFor(pathname) {
  const path = normalizePathname(pathname)

  if (path === '/dashboard') {
    return { roles: AUTHENTICATED_ROLES }
  }

  if (path === '/incidents' || path.startsWith('/incidents/')) {
    return { roles: STAFF_ROLES }
  }

  return null
}

export function canAccessRoute(user, pathname) {
  const rule = routeAccessFor(pathname)
  if (!rule) return true
  return hasAnyRole(user, rule.roles)
}

/**
 * Decide how a route guard should respond.
 *
 * - `loading`: session restoration is still in progress
 * - `redirect`: send the visitor to the login page and remember `from`
 * - `forbidden`: show the 403 access-denied screen
 * - `allow`: render the route
 */
export function routeGuardDecision({
  status,
  user,
  roles,
  pathname,
  from,
} = {}) {
  if (status === AUTH_STATUS.LOADING) return { type: 'loading' }

  const requiredRoles = roles ?? routeAccessFor(pathname)?.roles ?? null
  const redirectFrom = safeRedirectPath(from || pathname, '/dashboard')

  // Public paths do not need a session. This keeps the guard helper usable for
  // the preserved citizen routes without hiding them from anonymous visitors.
  if (!requiredRoles) return { type: 'allow' }

  if (status !== AUTH_STATUS.AUTHENTICATED || !user) {
    return {
      type: 'redirect',
      to: '/login',
      from: redirectFrom,
    }
  }

  if (requiredRoles && !hasAnyRole(user, requiredRoles)) {
    return { type: 'forbidden' }
  }

  return { type: 'allow' }
}

/**
 * Access state for a page that loads protected staff data outside a route
 * guard (for example the preserved `/complaints` and `/map` URLs).
 */
export function accessStateForRoles({ status, user, roles = STAFF_ROLES } = {}) {
  if (status === AUTH_STATUS.LOADING) return 'loading'
  if (status !== AUTH_STATUS.AUTHENTICATED || !user) return 'sign-in'
  if (!hasAnyRole(user, roles)) return 'forbidden'
  return 'allowed'
}

export function canAccessReports(user) {
  return hasAnyRole(user, STAFF_ROLES)
}

export function canAccessAdminOverview(user) {
  return hasAnyRole(user, ADMIN_ROLES)
}

export function canUpdateIncidentStatus(user) {
  return hasAnyRole(user, STAFF_ROLES)
}

/**
 * Citizen-facing navigation. Anonymous visitors can discover the protected
 * complaint/map URLs and are prompted to sign in, while authenticated viewer
 * accounts do not see links the backend would reject with 403.
 */
export function citizenNavigationFor(user, { authenticated = false } = {}) {
  const links = [
    { to: '/', label: 'Home', end: true },
    { to: '/report', label: 'Report' },
    { to: '/tracking', label: 'Track' },
  ]

  if (!authenticated || canAccessReports(user)) {
    links.push(
      { to: '/complaints', label: 'Complaints' },
      { to: '/map', label: 'Map' },
    )
  }

  return links
}

export function staffNavigationFor(user) {
  if (!user) return []

  const links = [{ to: '/dashboard', label: 'Dashboard' }]
  if (canUpdateIncidentStatus(user)) {
    links.push({ to: '/incidents', label: 'Incidents' })
  }
  return links
}
