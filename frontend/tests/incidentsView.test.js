import assert from 'node:assert/strict'
import test from 'node:test'

import { INCIDENT_STATUSES } from '../src/lib/constants.js'
import { statusStyleKey } from '../src/lib/format.js'
import {
  formatIncidentCoordinates,
  incidentCategoryLabel,
  incidentFilterParams,
  incidentListState,
  incidentPriorityLabel,
  incidentStatusLabel,
  incidentToCard,
  isAllowedIncidentStatus,
} from '../src/lib/incidentsView.js'

test('incidentToCard maps only confirmed incident fields', () => {
  const view = incidentToCard({
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
  })

  assert.deepEqual(view, {
    id: 7,
    trackingId: 'CP-20261107-911B19',
    category: 'pothole',
    categoryLabel: 'Roads & potholes',
    description: 'Large pothole near the school gate.',
    severity: 'high',
    severityLabel: 'High',
    priority: 'critical',
    priorityLabel: 'Critical',
    status: 'In Progress',
    statusLabel: 'In Progress',
    latitude: 23.0225,
    longitude: 72.5714,
    coordinatesLabel: '23.02250, 72.57140',
    createdAt: '2026-11-07T22:00:28',
  })

  for (const field of ['title', 'address', 'language', 'reference_code']) {
    assert.equal(field in view, false)
  }
})

test('null priority and null coordinates use clear non-default labels', () => {
  const view = incidentToCard({
    category: 'other',
    description: null,
    severity: null,
    priority: null,
    status: null,
    latitude: null,
    longitude: null,
    created_at: null,
  })

  assert.equal(view.priority, '')
  assert.equal(view.priorityLabel, 'Not set')
  assert.equal(view.severityLabel, 'Not set')
  assert.equal(view.statusLabel, 'Unknown')
  assert.equal(view.coordinatesLabel, '—')
  assert.equal(view.description, '')
  assert.equal(incidentPriorityLabel(null), 'Not set')
})

test('zero coordinates are treated as valid locations', () => {
  assert.equal(formatIncidentCoordinates(0, 0), '0.00000, 0.00000')
  assert.equal(
    incidentToCard({ latitude: 0, longitude: 0 }).coordinatesLabel,
    '0.00000, 0.00000',
  )
})

test('canonical backend status strings produce readable labels and style keys', () => {
  const canonicalStatuses = ['Submitted', 'In Progress', 'Resolved', 'Closed']

  assert.deepEqual(
    INCIDENT_STATUSES.map((status) => status.value),
    canonicalStatuses,
  )

  for (const status of canonicalStatuses) {
    assert.equal(incidentStatusLabel(status), status)
    assert.equal(statusStyleKey(status), status.toLowerCase().replace(' ', '_'))
    assert.equal(isAllowedIncidentStatus(status), true)
  }

  // Snake_case is only a legacy display concern; it is not a valid API value.
  assert.equal(incidentStatusLabel('in_progress'), 'In Progress')
  assert.equal(statusStyleKey('in_progress'), 'in_progress')
  assert.equal(isAllowedIncidentStatus('in_progress'), false)
  assert.equal(isAllowedIncidentStatus('Cancelled'), false)
})

test('incident list state distinguishes loading, error, empty and list', () => {
  assert.equal(
    incidentListState({ loading: true, error: '', incidents: [] }),
    'loading',
  )
  assert.equal(
    incidentListState({ loading: false, error: 'Unavailable', incidents: [] }),
    'error',
  )
  assert.equal(
    incidentListState({ loading: false, error: '', incidents: [] }),
    'empty',
  )
  assert.equal(
    incidentListState({ loading: false, error: '', incidents: [{ id: 1 }] }),
    'list',
  )
})

test('filter params include only backend-supported incident filters', () => {
  assert.deepEqual(
    incidentFilterParams({
      category: 'pothole',
      status: 'Submitted',
      severity: 'high',
      priority: 'critical',
      search: 'unsupported',
    }),
    {
      category: 'pothole',
      status: 'Submitted',
      severity: 'high',
      priority: 'critical',
    },
  )

  assert.deepEqual(incidentFilterParams({}), {
    category: undefined,
    status: undefined,
    severity: undefined,
    priority: undefined,
  })
})

test('category labels use existing incident constants with a safe fallback', () => {
  assert.equal(incidentCategoryLabel('pothole'), 'Roads & potholes')
  assert.equal(incidentCategoryLabel('other'), 'Other')
  assert.equal(incidentCategoryLabel('unknown_category'), 'Unknown Category')
  assert.equal(incidentCategoryLabel(null), 'Uncategorised')
})
