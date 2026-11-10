import assert from 'node:assert/strict'
import test from 'node:test'

import {
  UNKNOWN_SEVERITY_COLOR,
  hasValidCoordinates,
  incidentCoordinates,
  incidentSeverityColor,
  mapIncidentToMarker,
  mapPageState,
  mappedIncidentMarkers,
  missingLocationCount,
} from '../src/lib/mapView.js'

test('coordinate validation rejects missing and out-of-range values', () => {
  assert.equal(
    hasValidCoordinates({ latitude: 23.0225, longitude: 72.5714 }),
    true,
  )

  for (const incident of [
    {},
    { latitude: null, longitude: 72.5714 },
    { latitude: 23.0225, longitude: null },
    { latitude: undefined, longitude: 72.5714 },
    { latitude: '', longitude: 72.5714 },
    { latitude: '   ', longitude: 72.5714 },
    { latitude: Number.NaN, longitude: 72.5714 },
    { latitude: 91, longitude: 72.5714 },
    { latitude: -91, longitude: 72.5714 },
    { latitude: 23.0225, longitude: 181 },
    { latitude: 23.0225, longitude: -181 },
    { latitude: true, longitude: 72.5714 },
  ]) {
    assert.equal(hasValidCoordinates(incident), false)
  }
})

test('zero coordinates are valid map locations', () => {
  assert.equal(hasValidCoordinates({ latitude: 0, longitude: 0 }), true)
  assert.deepEqual(incidentCoordinates({ latitude: 0, longitude: 0 }), {
    latitude: 0,
    longitude: 0,
  })

  const marker = mapIncidentToMarker({
    id: 1,
    tracking_id: 'CP-ZERO',
    latitude: 0,
    longitude: 0,
  })

  assert.equal(marker.latitude, 0)
  assert.equal(marker.longitude, 0)
})

test('missing coordinates are excluded and counted', () => {
  assert.equal(
    mapIncidentToMarker({ latitude: null, longitude: null }),
    null,
  )

  const incidents = [
    { id: 1, latitude: 0, longitude: 0 },
    { id: 2, latitude: null, longitude: null },
    { id: 3, latitude: 23.0225, longitude: 72.5714 },
    { id: 4, latitude: 23.0225, longitude: undefined },
  ]

  assert.equal(mappedIncidentMarkers(incidents).length, 2)
  assert.equal(missingLocationCount(incidents), 2)
  assert.equal(
    mapPageState({ incidents: [{ id: 1, latitude: null, longitude: null }] }),
    'no-location',
  )
})

test('incident markers contain only confirmed backend fields', () => {
  const marker = mapIncidentToMarker({
    id: 7,
    tracking_id: 'CP-20261107-911B19',
    category: 'pothole',
    description: 'Large pothole near the school gate.',
    severity: 'high',
    priority: 'critical',
    status: 'In Progress',
    latitude: 23.0225,
    longitude: 72.5714,
    created_at: '2026-11-07T22:00:28',
    title: 'not returned by the backend',
    address: 'not returned by the backend',
    incidentType: 'not returned by the backend',
  })

  assert.deepEqual(marker, {
    id: 7,
    trackingId: 'CP-20261107-911B19',
    category: 'pothole',
    categoryLabel: 'Roads & potholes',
    description: 'Large pothole near the school gate.',
    severity: 'high',
    severityLabel: 'High',
    severityColor: '#f97316',
    priority: 'critical',
    priorityLabel: 'Critical',
    status: 'In Progress',
    statusLabel: 'In Progress',
    latitude: 23.0225,
    longitude: 72.5714,
    createdAt: '2026-11-07T22:00:28',
  })

  for (const field of ['title', 'address', 'incidentType', 'reference_code']) {
    assert.equal(field in marker, false)
  }
})

test('null and unknown incident values use safe marker labels', () => {
  const nullMarker = mapIncidentToMarker({
    id: 8,
    tracking_id: null,
    category: null,
    description: null,
    severity: null,
    priority: null,
    status: null,
    latitude: 23.0225,
    longitude: 72.5714,
  })

  assert.equal(nullMarker.trackingId, '')
  assert.equal(nullMarker.categoryLabel, 'Uncategorised')
  assert.equal(nullMarker.severityLabel, 'Not set')
  assert.equal(nullMarker.priorityLabel, 'Not set')
  assert.equal(nullMarker.statusLabel, 'Unknown')
  assert.equal(nullMarker.severityColor, UNKNOWN_SEVERITY_COLOR)
  assert.equal(nullMarker.description, '')

  const unknownMarker = mapIncidentToMarker({
    id: 9,
    category: 'mystery_category',
    severity: 'urgent',
    priority: 'urgent',
    status: 'Pending Review',
    latitude: 23.0225,
    longitude: 72.5714,
  })

  assert.equal(unknownMarker.categoryLabel, 'Mystery Category')
  assert.equal(unknownMarker.severityLabel, 'Urgent')
  assert.equal(unknownMarker.priorityLabel, 'Urgent')
  assert.equal(unknownMarker.statusLabel, 'Pending Review')
  assert.equal(unknownMarker.severityColor, UNKNOWN_SEVERITY_COLOR)
  assert.equal(incidentSeverityColor('HIGH'), '#f97316')
})

test('mapPageState distinguishes loading, error, empty, no-location and ready', () => {
  assert.equal(
    mapPageState({ loading: true, error: 'ignored', incidents: [] }),
    'loading',
  )
  assert.equal(
    mapPageState({ loading: false, error: 'Unavailable', incidents: [] }),
    'error',
  )
  assert.equal(
    mapPageState({ loading: false, error: '', incidents: [] }),
    'empty',
  )
  assert.equal(
    mapPageState({
      loading: false,
      error: '',
      incidents: [{ id: 1, latitude: null, longitude: null }],
    }),
    'no-location',
  )
  assert.equal(
    mapPageState({
      loading: false,
      error: '',
      incidents: [{ id: 1, latitude: 0, longitude: 0 }],
    }),
    'ready',
  )
})
