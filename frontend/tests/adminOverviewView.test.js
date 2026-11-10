import assert from 'node:assert/strict'
import test from 'node:test'

import {
  adminOverviewState,
  mapAdminOverview,
} from '../src/lib/adminOverviewView.js'

const overview = {
  incidents_total: 6,
  citizen_reports_total: 2,
  incident_images_total: 0,
  status_history_total: 3,
  departments_total: 1,
  incidents_by_status: [
    { value: 'Submitted', count: 5 },
    { value: 'In Progress', count: 1 },
  ],
  services: [
    {
      name: 'database',
      configured: true,
      implemented: true,
      note: 'Connected',
      unexpected: 'ignored',
    },
  ],
  response_time: 12,
}

test('mapAdminOverview maps only admin overview fields', () => {
  const view = mapAdminOverview(overview)

  assert.deepEqual(view, {
    incidentsTotal: 6,
    citizenReportsTotal: 2,
    incidentImagesTotal: 0,
    statusHistoryTotal: 3,
    departmentsTotal: 1,
    incidentsByStatus: [
      { value: 'Submitted', label: 'Submitted', count: 5 },
      { value: 'In Progress', label: 'In Progress', count: 1 },
    ],
    services: [
      {
        name: 'database',
        configured: true,
        implemented: true,
        note: 'Connected',
      },
    ],
  })

  assert.deepEqual(Object.keys(view).sort(), [
    'citizenReportsTotal',
    'departmentsTotal',
    'incidentImagesTotal',
    'incidentsByStatus',
    'incidentsTotal',
    'services',
    'statusHistoryTotal',
  ])
})

test('mapAdminOverview handles missing and malformed counts safely', () => {
  const view = mapAdminOverview({
    incidents_total: 'not-a-number',
    citizen_reports_total: -1,
    incidents_by_status: 'invalid',
    services: null,
  })

  assert.equal(view.incidentsTotal, 0)
  assert.equal(view.citizenReportsTotal, 0)
  assert.deepEqual(view.incidentsByStatus, [])
  assert.deepEqual(view.services, [])
})

test('adminOverviewState distinguishes loading, error, empty and ready', () => {
  assert.equal(adminOverviewState({ loading: true }), 'loading')
  assert.equal(adminOverviewState({ error: new Error('nope') }), 'error')
  assert.equal(adminOverviewState({ overview: null }), 'empty')
  assert.equal(adminOverviewState({ overview }), 'ready')
})
