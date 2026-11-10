import assert from 'node:assert/strict'
import test from 'node:test'

import { AUTH_STATUS } from '../src/lib/auth.js'
import {
  PUBLIC_ROUTE_PATHS,
  accessStateForRoles,
  canAccessAdminOverview,
  canAccessReports,
  canAccessRoute,
  canUpdateIncidentStatus,
  citizenNavigationFor,
  routeGuardDecision,
  staffNavigationFor,
} from '../src/lib/routeAccess.js'

const admin = { id: 1, email: 'admin@example.org', role: 'admin' }
const dispatcher = { id: 2, email: 'dispatch@example.org', role: 'dispatcher' }
const viewer = { id: 3, email: 'viewer@example.org', role: 'viewer' }

test('citizen routes remain public', () => {
  assert.deepEqual(
    PUBLIC_ROUTE_PATHS.filter((path) =>
      ['/report', '/tracking', '/complaints', '/map'].includes(path),
    ),
    ['/report', '/tracking', '/complaints', '/map'],
  )

  for (const path of PUBLIC_ROUTE_PATHS) {
    assert.equal(
      routeGuardDecision({
        status: AUTH_STATUS.ANONYMOUS,
        user: null,
        pathname: path,
      }).type,
      'allow',
    )
  }
})

test('anonymous visitors are redirected from staff pages to login', () => {
  for (const pathname of ['/dashboard', '/incidents', '/incidents/12']) {
    const decision = routeGuardDecision({
      status: AUTH_STATUS.ANONYMOUS,
      user: null,
      pathname,
    })

    assert.equal(decision.type, 'redirect')
    assert.equal(decision.to, '/login')
    assert.equal(decision.from, pathname)
  }
})

test('role-based route access follows the backend permissions', () => {
  assert.equal(canAccessRoute(admin, '/dashboard'), true)
  assert.equal(canAccessRoute(dispatcher, '/dashboard'), true)
  assert.equal(canAccessRoute(viewer, '/dashboard'), true)

  assert.equal(canAccessRoute(admin, '/incidents'), true)
  assert.equal(canAccessRoute(dispatcher, '/incidents/4'), true)
  assert.equal(canAccessRoute(viewer, '/incidents'), false)
  assert.equal(canAccessRoute(viewer, '/incidents/4'), false)

  assert.equal(canAccessReports(admin), true)
  assert.equal(canAccessReports(dispatcher), true)
  assert.equal(canAccessReports(viewer), false)
  assert.equal(canAccessAdminOverview(admin), true)
  assert.equal(canAccessAdminOverview(dispatcher), false)
})

test('viewer accounts cannot update incident status', () => {
  assert.equal(canUpdateIncidentStatus(admin), true)
  assert.equal(canUpdateIncidentStatus(dispatcher), true)
  assert.equal(canUpdateIncidentStatus(viewer), false)
  assert.equal(canUpdateIncidentStatus(null), false)
})

test('route guards show loading and forbidden states', () => {
  assert.deepEqual(
    routeGuardDecision({ status: AUTH_STATUS.LOADING, user: null }),
    { type: 'loading' },
  )

  assert.deepEqual(
    routeGuardDecision({
      status: AUTH_STATUS.AUTHENTICATED,
      user: viewer,
      pathname: '/incidents/9',
    }),
    { type: 'forbidden' },
  )

  assert.deepEqual(
    routeGuardDecision({
      status: AUTH_STATUS.AUTHENTICATED,
      user: dispatcher,
      pathname: '/incidents/9',
    }),
    { type: 'allow' },
  )
})

test('protected data views distinguish sign-in, forbidden and allowed', () => {
  assert.equal(
    accessStateForRoles({ status: AUTH_STATUS.LOADING, user: null }),
    'loading',
  )
  assert.equal(
    accessStateForRoles({ status: AUTH_STATUS.ANONYMOUS, user: null }),
    'sign-in',
  )
  assert.equal(
    accessStateForRoles({
      status: AUTH_STATUS.AUTHENTICATED,
      user: viewer,
    }),
    'forbidden',
  )
  assert.equal(
    accessStateForRoles({
      status: AUTH_STATUS.AUTHENTICATED,
      user: dispatcher,
    }),
    'allowed',
  )
})

test('citizen navigation hides staff-only data links from viewers', () => {
  const paths = (links) => links.map((link) => link.to)

  assert.deepEqual(paths(citizenNavigationFor(null)), [
    '/',
    '/report',
    '/tracking',
    '/complaints',
    '/map',
  ])
  assert.deepEqual(
    paths(citizenNavigationFor(admin, { authenticated: true })),
    ['/', '/report', '/tracking', '/complaints', '/map'],
  )
  assert.deepEqual(
    paths(citizenNavigationFor(dispatcher, { authenticated: true })),
    ['/', '/report', '/tracking', '/complaints', '/map'],
  )
  assert.deepEqual(
    paths(citizenNavigationFor(viewer, { authenticated: true })),
    ['/', '/report', '/tracking'],
  )
})

test('staff navigation hides incident management from viewers', () => {
  assert.deepEqual(staffNavigationFor(admin), [
    { to: '/dashboard', label: 'Dashboard' },
    { to: '/incidents', label: 'Incidents' },
  ])
  assert.deepEqual(staffNavigationFor(viewer), [
    { to: '/dashboard', label: 'Dashboard' },
  ])
  assert.deepEqual(staffNavigationFor(null), [])
})
