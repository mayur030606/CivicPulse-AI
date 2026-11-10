import assert from 'node:assert/strict'
import test from 'node:test'

import { formatDate } from '../src/lib/format.js'
import {
  describeTrackingError,
  mapTrackingResult,
  normalizeTrackingId,
  trackingLookupState,
  trackingPath,
  validateTrackingId,
} from '../src/lib/trackingView.js'

const liveTracking = {
  tracking_id: 'CP-20261107-911B19',
  category: 'other',
  status: 'Submitted',
  severity: 'low',
  priority: 'low',
  latitude: null,
  longitude: null,
  created_at: '2026-11-07T22:00:28',
}

test('tracking ID validation accepts trimmed IDs and rejects empty or invalid lengths', () => {
  for (const value of ['', '   ', null, undefined]) {
    assert.equal(validateTrackingId(value), 'Enter a tracking ID.')
  }

  assert.equal(validateTrackingId('ab'), 'Tracking IDs are at least 3 characters.')
  assert.equal(
    validateTrackingId('a'.repeat(51)),
    'Tracking IDs are at most 50 characters.',
  )
  assert.equal(validateTrackingId('abc'), '')
  assert.equal(validateTrackingId(' CP-20261107-911B19 '), '')
  assert.equal(normalizeTrackingId('  CP-20261107-911B19  '), 'CP-20261107-911B19')
})

test('trackingPath encodes only the backend-returned tracking ID', () => {
  assert.equal(
    trackingPath('CP-20261107-911B19'),
    '/tracking?trackingId=CP-20261107-911B19',
  )
  assert.equal(
    trackingPath(' CP 2026/07?x=1 '),
    '/tracking?trackingId=CP%202026%2F07%3Fx%3D1',
  )
  assert.equal(trackingPath(''), '/tracking')
  assert.equal(trackingPath(null), '/tracking')
})

test('mapTrackingResult maps only confirmed tracking response fields', () => {
  const view = mapTrackingResult(liveTracking)

  assert.deepEqual(Object.keys(view).sort(), [
    'category',
    'categoryLabel',
    'coordinatesLabel',
    'createdAt',
    'createdLabel',
    'latitude',
    'longitude',
    'priority',
    'priorityLabel',
    'severity',
    'severityLabel',
    'status',
    'statusLabel',
    'trackingId',
  ])
  assert.equal(view.trackingId, 'CP-20261107-911B19')
  assert.equal(view.category, 'other')
  assert.equal(view.categoryLabel, 'Other')
  assert.equal(view.status, 'Submitted')
  assert.equal(view.statusLabel, 'Submitted')
  assert.equal(view.severity, 'low')
  assert.equal(view.severityLabel, 'Low')
  assert.equal(view.priority, 'low')
  assert.equal(view.priorityLabel, 'Low')
  assert.equal(view.latitude, null)
  assert.equal(view.longitude, null)
  assert.equal(view.coordinatesLabel, '—')
  assert.equal(view.createdAt, '2026-11-07T22:00:28')
  assert.equal(view.createdLabel, formatDate(liveTracking.created_at))

  for (const field of [
    'description',
    'title',
    'address',
    'language',
    'department',
    'timeline',
    'status_history',
  ]) {
    assert.equal(field in view, false)
  }
})

test('null and unknown tracking values map to safe labels', () => {
  const nullView = mapTrackingResult({
    tracking_id: null,
    category: null,
    status: null,
    severity: null,
    priority: null,
    latitude: null,
    longitude: null,
    created_at: null,
  })

  assert.equal(nullView.trackingId, '')
  assert.equal(nullView.categoryLabel, 'Uncategorised')
  assert.equal(nullView.statusLabel, 'Unknown')
  assert.equal(nullView.severityLabel, 'Not set')
  assert.equal(nullView.priorityLabel, 'Not set')
  assert.equal(nullView.coordinatesLabel, '—')
  assert.equal(nullView.createdLabel, '—')

  const unknownView = mapTrackingResult({
    tracking_id: 'CP-UNKNOWN',
    category: 'mystery_category',
    status: 'Pending Review',
    severity: 'urgent',
    priority: 'urgent',
  })

  assert.equal(unknownView.categoryLabel, 'Mystery Category')
  assert.equal(unknownView.statusLabel, 'Pending Review')
  assert.equal(unknownView.severityLabel, 'Urgent')
  assert.equal(unknownView.priorityLabel, 'Urgent')
})

test('zero coordinates remain valid in tracking results', () => {
  const view = mapTrackingResult({
    tracking_id: 'CP-ZERO',
    category: 'other',
    latitude: 0,
    longitude: 0,
    created_at: null,
  })

  assert.equal(view.latitude, 0)
  assert.equal(view.longitude, 0)
  assert.equal(view.coordinatesLabel, '0.00000, 0.00000')
  assert.equal(view.createdLabel, '—')
})

test('trackingLookupState distinguishes idle, loading, success, not-found and error', () => {
  assert.equal(trackingLookupState(), 'idle')
  assert.equal(
    trackingLookupState({
      loading: true,
      error: { status: 404 },
      result: liveTracking,
    }),
    'loading',
  )
  assert.equal(
    trackingLookupState({
      loading: false,
      error: { status: 404 },
      result: null,
    }),
    'not-found',
  )
  assert.equal(
    trackingLookupState({
      loading: false,
      error: { status: 500 },
      result: null,
    }),
    'error',
  )
  assert.equal(
    trackingLookupState({
      loading: false,
      error: null,
      result: liveTracking,
    }),
    'success',
  )
  assert.equal(
    trackingLookupState({ loading: false, error: null, result: null }),
    'idle',
  )
})

test('describeTrackingError maps not-found, validation, network and server errors', () => {
  const notFound = describeTrackingError({
    status: 404,
    message: 'Report not found. Check the tracking ID.',
  })
  assert.equal(notFound.title, 'Tracking ID not found')
  assert.equal(notFound.message, 'Report not found. Check the tracking ID.')
  assert.match(notFound.guidance, /Check the ID/)

  const invalid = describeTrackingError({
    status: 422,
    message: 'Invalid tracking ID.',
  })
  assert.equal(invalid.title, 'Tracking ID is not valid')
  assert.equal(invalid.message, 'Invalid tracking ID.')

  const network = describeTrackingError(new Error('Network Error'))
  assert.equal(network.title, 'Could not reach the server')
  assert.equal(network.message, 'Network Error')

  const server = describeTrackingError({ status: 500, message: 'Boom' })
  assert.equal(server.title, 'Could not look up the report')
  assert.equal(server.message, 'Boom')
})
