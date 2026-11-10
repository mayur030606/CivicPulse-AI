import assert from 'node:assert/strict'
import test from 'node:test'

import apiClient, {
  CSRF_HEADER_NAME,
  csrfHeadersForRequest,
  getCookieValue,
} from '../src/api/client.js'
import {
  getIncident,
  listIncidents,
  updateIncident,
} from '../src/api/incidents.js'

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

test('listIncidents sends only confirmed staff filters', async () => {
  const mock = mockMethod('get', () => ({ data: [] }))

  try {
    await listIncidents({
      category: 'pothole',
      status: 'In Progress',
      severity: 'high',
      priority: 'critical',
      limit: 25,
      offset: 10,
      search: 'unsupported',
    })

    assert.deepEqual(mock.calls, [
      [
        '/incidents',
        {
          params: {
            category: 'pothole',
            status: 'In Progress',
            severity: 'high',
            priority: 'critical',
            limit: 25,
            offset: 10,
          },
        },
      ],
    ])
  } finally {
    mock.restore()
  }
})

test('getIncident calls the protected detail endpoint', async () => {
  const mock = mockMethod('get', () => ({ data: { id: 7 } }))

  try {
    const result = await getIncident(7)

    assert.deepEqual(mock.calls, [['/incidents/7']])
    assert.deepEqual(result, { id: 7 })
  } finally {
    mock.restore()
  }
})

test('updateIncident sends only IncidentUpdate fields', async () => {
  const mock = mockMethod('patch', () => ({ data: { id: 7 } }))

  try {
    await updateIncident(7, {
      status: 'Resolved',
      category: 'pothole',
      latitude: 23.02,
      unsupported: true,
    })

    assert.deepEqual(mock.calls, [
      [
        '/incidents/7',
        {
          status: 'Resolved',
          category: 'pothole',
        },
      ],
    ])
  } finally {
    mock.restore()
  }
})

test('cookie parsing finds the CSRF token and ignores similar names', () => {
  const cookies =
    'other=1; civicpulse_csrf=token%2Bvalue; mycivicpulse_csrf=wrong'

  assert.equal(getCookieValue('civicpulse_csrf', cookies), 'token+value')
  assert.deepEqual(csrfHeadersForRequest('patch', cookies), {
    [CSRF_HEADER_NAME]: 'token+value',
  })
  assert.deepEqual(csrfHeadersForRequest('get', cookies), {})
  assert.deepEqual(csrfHeadersForRequest('patch', ''), {})
})

test('authenticated PATCH requests include credentials and the CSRF header', async () => {
  const originalAdapter = apiClient.defaults.adapter
  const originalDocument = globalThis.document
  let capturedConfig = null

  globalThis.document = { cookie: 'civicpulse_csrf=csrf-test-token' }
  apiClient.defaults.adapter = async (config) => {
    capturedConfig = config
    return {
      data: { id: 7, status: 'In Progress' },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
    }
  }

  try {
    await updateIncident(7, { status: 'In Progress' })

    assert.equal(capturedConfig.method, 'patch')
    assert.equal(capturedConfig.withCredentials, true)
    assert.equal(
      capturedConfig.headers.get(CSRF_HEADER_NAME),
      'csrf-test-token',
    )
  } finally {
    apiClient.defaults.adapter = originalAdapter
    if (originalDocument === undefined) {
      delete globalThis.document
    } else {
      globalThis.document = originalDocument
    }
  }
})
