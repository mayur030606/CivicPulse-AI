import assert from 'node:assert/strict'
import test from 'node:test'

import apiClient from '../src/api/client.js'
import { getCurrentUser, login, logout } from '../src/api/auth.js'

function mockMethod(method, handler) {
  const original = apiClient[method]
  const calls = []

  apiClient[method] = async (...args) => {
    calls.push(args)
    return handler(...args)
  }

  return {
    calls,
    restore() {
      apiClient[method] = original
    },
  }
}

test('login posts normalized credentials and returns the user', async () => {
  const user = {
    id: 4,
    email: 'dispatcher@example.org',
    role: 'dispatcher',
    is_active: true,
  }
  const mock = mockMethod('post', () => ({ data: { user } }))

  try {
    const result = await login('  Dispatcher@Example.org ', 'correct horse')

    assert.deepEqual(mock.calls, [
      [
        '/auth/login',
        {
          email: 'dispatcher@example.org',
          password: 'correct horse',
        },
      ],
    ])
    assert.deepEqual(result, user)
  } finally {
    mock.restore()
  }
})

test('login failure rejects without returning a user', async () => {
  const failure = Object.assign(new Error('Invalid email or password.'), {
    status: 401,
  })
  const mock = mockMethod('post', () => Promise.reject(failure))

  try {
    await assert.rejects(() => login('staff@example.org', 'wrong'), /Invalid/)
  } finally {
    mock.restore()
  }
})

test('session restoration calls GET /auth/me', async () => {
  const user = {
    id: 1,
    email: 'admin@example.org',
    role: 'admin',
    is_active: true,
  }
  const mock = mockMethod('get', () => ({ data: user }))

  try {
    const result = await getCurrentUser()

    assert.deepEqual(mock.calls, [['/auth/me']])
    assert.deepEqual(result, user)
  } finally {
    mock.restore()
  }
})

test('logout posts to the revocation endpoint', async () => {
  const mock = mockMethod('post', () => ({ data: null }))

  try {
    await logout()

    assert.deepEqual(mock.calls, [['/auth/logout']])
  } finally {
    mock.restore()
  }
})

async function captureRequest(run) {
  const originalAdapter = apiClient.defaults.adapter
  const originalDocument = globalThis.document
  let capturedConfig = null

  globalThis.document = { cookie: 'civicpulse_csrf=csrf-test-token' }
  apiClient.defaults.adapter = async (config) => {
    capturedConfig = config
    return {
      data: null,
      status: 204,
      statusText: 'No Content',
      headers: {},
      config,
    }
  }

  try {
    await run()
    return capturedConfig
  } finally {
    apiClient.defaults.adapter = originalAdapter
    if (originalDocument === undefined) {
      delete globalThis.document
    } else {
      globalThis.document = originalDocument
    }
  }
}

test('logout sends credentials and the CSRF header', async () => {
  const config = await captureRequest(() => logout())

  assert.equal(config.method, 'post')
  assert.equal(config.url, '/auth/logout')
  assert.equal(config.withCredentials, true)
  assert.equal(config.headers.get('X-CSRF-Token'), 'csrf-test-token')
})

test('session restoration sends cookies without a CSRF header', async () => {
  const config = await captureRequest(() => getCurrentUser())

  assert.equal(config.method, 'get')
  assert.equal(config.url, '/auth/me')
  assert.equal(config.withCredentials, true)
  assert.equal(config.headers.get('X-CSRF-Token'), undefined)
})
