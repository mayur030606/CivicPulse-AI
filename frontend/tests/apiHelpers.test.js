import assert from 'node:assert/strict'
import test from 'node:test'

import apiClient from '../src/api/client.js'
import { createIncident } from '../src/api/incidents.js'
import { getReportSummary } from '../src/api/reports.js'
import { getTracking } from '../src/api/tracking.js'

function mockGet(handler) {
  const originalGet = apiClient.get
  const calls = []

  apiClient.get = async (...args) => {
    calls.push(args)
    return handler(...args)
  }

  return {
    calls,
    restore() {
      apiClient.get = originalGet
    },
  }
}

function mockPost(handler) {
  const originalPost = apiClient.post
  const calls = []

  apiClient.post = async (...args) => {
    calls.push(args)
    return handler(...args)
  }

  return {
    calls,
    restore() {
      apiClient.post = originalPost
    },
  }
}

test('getReportSummary calls the confirmed summary endpoint', async () => {
  const summary = {
    total: 2,
    by_status: [{ value: 'Submitted', count: 2 }],
    by_priority: [{ value: 'low', count: 2 }],
    by_severity: [{ value: 'low', count: 2 }],
    by_category: [
      { value: 'pothole', count: 1 },
      { value: 'other', count: 1 },
    ],
  }
  const mock = mockGet(() => ({ data: summary }))

  try {
    const result = await getReportSummary()

    assert.deepEqual(mock.calls, [['/reports/summary']])
    assert.deepEqual(result, summary)
  } finally {
    mock.restore()
  }
})

test('getTracking calls the confirmed tracking endpoint', async () => {
  const tracking = {
    tracking_id: 'CP-20261107-911B19',
    category: 'other',
    status: 'Submitted',
    severity: 'low',
    priority: 'low',
    latitude: null,
    longitude: null,
    created_at: '2026-11-07T22:00:28',
  }
  const mock = mockGet(() => ({ data: tracking }))

  try {
    const result = await getTracking('CP-20261107-911B19')

    assert.deepEqual(mock.calls, [['/tracking/CP-20261107-911B19']])
    assert.deepEqual(result, tracking)
    assert.equal('description' in result, false)
    assert.equal('title' in result, false)
    assert.equal('address' in result, false)
    assert.equal('language' in result, false)
  } finally {
    mock.restore()
  }
})

test('getTracking trims and URL-encodes the tracking ID', async () => {
  const tracking = {
    tracking_id: 'CP 2026/07?x=1',
    category: 'other',
  }
  const mock = mockGet(() => ({ data: tracking }))

  try {
    const result = await getTracking('  CP 2026/07?x=1  ')

    assert.deepEqual(mock.calls, [
      ['/tracking/CP%202026%2F07%3Fx%3D1'],
    ])
    assert.deepEqual(result, tracking)
  } finally {
    mock.restore()
  }
})

test('getTracking rejects an empty tracking ID before requesting', async () => {
  const mock = mockGet(() => ({ data: {} }))

  try {
    for (const value of ['', '   ', null, undefined]) {
      await assert.rejects(
        () => getTracking(value),
        /Tracking ID is required\./,
      )
    }

    assert.equal(mock.calls.length, 0)
  } finally {
    mock.restore()
  }
})

test('createIncident forwards coordinates and omits blank coordinates', async () => {
  const mock = mockPost(() => ({
    data: { tracking_id: 'CP-20261107-TEST01' },
  }))

  try {
    await createIncident({
      category: 'pothole',
      description: 'Large pothole near the school gate.',
      latitude: 0,
      longitude: 0,
    })

    await createIncident({
      category: 'other',
      description: 'No coordinates supplied.',
    })

    assert.deepEqual(mock.calls, [
      [
        '/incidents',
        {
          category: 'pothole',
          description: 'Large pothole near the school gate.',
          latitude: 0,
          longitude: 0,
        },
      ],
      [
        '/incidents',
        {
          category: 'other',
          description: 'No coordinates supplied.',
        },
      ],
    ])
  } finally {
    mock.restore()
  }
})

test('createIncident never forwards a client-supplied tracking_id', async () => {
  const mock = mockPost(() => ({
    data: { tracking_id: 'CP-20261107-SERVER' },
  }))

  try {
    await createIncident({
      category: 'pothole',
      description: 'Large pothole near the school gate.',
      tracking_id: 'CP-CLIENT-OVERRIDE',
    })

    assert.deepEqual(mock.calls, [
      [
        '/incidents',
        {
          category: 'pothole',
          description: 'Large pothole near the school gate.',
        },
      ],
    ])
  } finally {
    mock.restore()
  }
})
