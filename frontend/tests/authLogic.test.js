import assert from 'node:assert/strict'
import test from 'node:test'

import {
  AUTH_STATUS,
  authErrorMessage,
  authReducer,
  hasAnyRole,
  initialAuthState,
  normalizeUser,
  safeRedirectPath,
} from '../src/lib/auth.js'

const admin = {
  id: 1,
  email: 'admin@example.org',
  role: 'admin',
  is_active: true,
}

test('normalizeUser accepts known roles and rejects unsupported ones', () => {
  assert.deepEqual(normalizeUser({ ...admin, role: ' ADMIN ' }), {
    ...admin,
    role: 'admin',
  })
  assert.equal(normalizeUser({ ...admin, role: 'superuser' }), null)
  assert.equal(normalizeUser(null), null)
})

test('restoring an authenticated session clears the loading state', () => {
  const state = authReducer(initialAuthState(), {
    type: 'restore_succeeded',
    user: admin,
  })

  assert.equal(state.status, AUTH_STATUS.AUTHENTICATED)
  assert.deepEqual(state.user, admin)
  assert.equal(state.sessionExpired, false)
})

test('a failed restoration becomes anonymous without an expiry message', () => {
  const state = authReducer(initialAuthState(), {
    type: 'restore_failed',
    error: '',
  })

  assert.equal(state.status, AUTH_STATUS.ANONYMOUS)
  assert.equal(state.user, null)
  assert.equal(state.sessionExpired, false)
})

test('a failed login leaves the auth state anonymous', () => {
  const anonymous = authReducer(initialAuthState(), {
    type: 'restore_failed',
    error: '',
  })
  const state = authReducer(anonymous, {
    type: 'login_failed',
    error: 'Invalid email or password.',
  })

  assert.equal(state.status, AUTH_STATUS.ANONYMOUS)
  assert.equal(state.user, null)
})

test('session expiry clears an authenticated user and sets a notice', () => {
  const authenticated = authReducer(initialAuthState(), {
    type: 'login_succeeded',
    user: admin,
  })
  const expired = authReducer(authenticated, { type: 'session_expired' })

  assert.equal(expired.status, AUTH_STATUS.ANONYMOUS)
  assert.equal(expired.user, null)
  assert.equal(expired.sessionExpired, true)
})

test('session expiry is ignored before authentication', () => {
  const initial = initialAuthState()
  const state = authReducer(initial, { type: 'session_expired' })

  assert.equal(state, initial)
})

test('logout clears the in-memory session', () => {
  const authenticated = authReducer(initialAuthState(), {
    type: 'login_succeeded',
    user: admin,
  })
  const state = authReducer(authenticated, { type: 'logout_succeeded' })

  assert.equal(state.status, AUTH_STATUS.ANONYMOUS)
  assert.equal(state.user, null)
  assert.equal(state.sessionExpired, false)
})

test('role checks are exact and fail closed', () => {
  assert.equal(hasAnyRole(admin, ['admin', 'dispatcher']), true)
  assert.equal(hasAnyRole({ ...admin, role: 'viewer' }, ['admin']), false)
  assert.equal(hasAnyRole(null, ['admin']), false)
  assert.equal(hasAnyRole(admin, []), false)
})

test('authentication errors preserve a generic 401 message', () => {
  assert.equal(
    authErrorMessage({ status: 401, message: 'leaked detail' }),
    'Email or password is incorrect.',
  )
  assert.equal(
    authErrorMessage({ status: 403, message: 'Forbidden' }),
    'You do not have permission to sign in with this account.',
  )
  assert.match(
    authErrorMessage({ status: null, message: 'Network Error' }),
    /Unable to reach the server/,
  )
})

test('safeRedirectPath blocks external and login redirects', () => {
  assert.equal(safeRedirectPath('/incidents/7?tab=status'), '/incidents/7?tab=status')
  assert.equal(safeRedirectPath('https://evil.example'), '/dashboard')
  assert.equal(safeRedirectPath('//evil.example'), '/dashboard')
  assert.equal(safeRedirectPath('/login'), '/dashboard')
  assert.equal(safeRedirectPath('/login?from=/x'), '/dashboard')
  assert.equal(safeRedirectPath(undefined), '/dashboard')
})
