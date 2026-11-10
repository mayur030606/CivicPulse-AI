import assert from 'node:assert/strict'
import test from 'node:test'

import {
  categoryBarPercent,
  dashboardState,
  mapDashboardSummary,
  maxGroupCount,
} from '../src/lib/dashboardView.js'

const liveSummary = {
  total: 2,
  by_status: [{ value: 'Submitted', count: 2 }],
  by_priority: [{ value: 'low', count: 2 }],
  by_severity: [{ value: 'low', count: 2 }],
  by_category: [
    { value: 'pothole', count: 1 },
    { value: 'other', count: 1 },
  ],
}

test('mapDashboardSummary maps the confirmed reports summary fields', () => {
  const view = mapDashboardSummary(liveSummary)

  assert.deepEqual(view, {
    total: 2,
    byStatus: [{ value: 'Submitted', label: 'Submitted', count: 2 }],
    byPriority: [{ value: 'low', label: 'Low', count: 2 }],
    bySeverity: [{ value: 'low', label: 'Low', count: 2 }],
    byCategory: [
      { value: 'pothole', label: 'Roads & potholes', count: 1 },
      { value: 'other', label: 'Other', count: 1 },
    ],
  })

  assert.deepEqual(Object.keys(view).sort(), [
    'byCategory',
    'byPriority',
    'bySeverity',
    'byStatus',
    'total',
  ])
})

test('null and unknown group values map to safe labels', () => {
  const view = mapDashboardSummary({
    total: 9,
    by_status: [
      { value: null, count: 1 },
      { value: 'None', count: 1 },
      { value: 'Pending Review', count: 2 },
      { value: 'in_progress', count: 1 },
    ],
    by_priority: [
      { value: 'urgent', count: 2 },
      { value: '', count: 1 },
    ],
    by_severity: [
      { value: 'unknown', count: 2 },
      { value: 'None', count: 1 },
    ],
    by_category: [
      { value: null, count: 1 },
      { value: 'None', count: 1 },
      { value: 'mystery_category', count: 3 },
    ],
  })

  assert.deepEqual(
    view.byStatus.map((group) => group.label),
    ['Unknown', 'Unknown', 'Pending Review', 'In Progress'],
  )
  assert.deepEqual(
    view.byPriority.map((group) => group.label),
    ['Urgent', 'Not set'],
  )
  assert.deepEqual(
    view.bySeverity.map((group) => group.label),
    ['Unknown', 'Not set'],
  )
  assert.deepEqual(
    view.byCategory.map((group) => group.label),
    ['Uncategorised', 'Uncategorised', 'Mystery Category'],
  )
})

test('missing or malformed summary groups do not throw', () => {
  const view = mapDashboardSummary({
    total: null,
    by_status: null,
    by_priority: undefined,
    by_severity: {},
    by_category: [],
  })

  assert.deepEqual(view, {
    total: 0,
    byStatus: [],
    byPriority: [],
    bySeverity: [],
    byCategory: [],
  })
})

test('dashboardState distinguishes loading, error, empty and ready', () => {
  assert.equal(
    dashboardState({ loading: true, error: 'ignored', summary: liveSummary }),
    'loading',
  )
  assert.equal(
    dashboardState({ loading: false, error: 'Unavailable', summary: null }),
    'error',
  )
  assert.equal(
    dashboardState({ loading: false, error: '', summary: null }),
    'empty',
  )
  assert.equal(
    dashboardState({
      loading: false,
      error: '',
      summary: { total: 0 },
    }),
    'empty',
  )
  assert.equal(
    dashboardState({ loading: false, error: '', summary: liveSummary }),
    'ready',
  )
})

test('category bar helpers handle zero and clamp safely', () => {
  assert.equal(maxGroupCount([{ count: 1 }, { count: 4 }]), 4)
  assert.equal(maxGroupCount([]), 0)
  assert.equal(categoryBarPercent(2, 4), 50)
  assert.equal(categoryBarPercent(1, 0), 0)
  assert.equal(categoryBarPercent(5, 4), 100)
})
