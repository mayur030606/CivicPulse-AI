import assert from 'node:assert/strict'
import test from 'node:test'

import { INCIDENT_CATEGORIES } from '../src/lib/constants.js'
import {
  applyClassificationSuggestion,
  buildIncidentPayload,
  describeClassificationError,
  describeIncidentRequestError,
  validateIncidentForm,
} from '../src/lib/incidentForm.js'

const validForm = {
  category: 'pothole',
  description: 'Large pothole near the school gate.',
  language: 'hi',
  latitude: '23.0225',
  longitude: '72.5714',
}

test('incident categories match the backend classifier values', () => {
  assert.deepEqual(
    INCIDENT_CATEGORIES.map((category) => category.value),
    [
      'pothole',
      'garbage',
      'water_leakage',
      'streetlight',
      'drainage',
      'traffic_accident',
      'road_blockage',
      'other',
    ],
  )
})

test('valid form passes validation', () => {
  assert.deepEqual(validateIncidentForm(validForm), {})
})

test('category is required', () => {
  const errors = validateIncidentForm({ ...validForm, category: '' })
  assert.equal(errors.category, 'Choose a category.')
})

test('description is required and must not be blank', () => {
  const errors = validateIncidentForm({ ...validForm, description: '   ' })
  assert.equal(errors.description, 'Describe the issue before submitting.')
})

test('coordinates must be inside valid ranges', () => {
  const errors = validateIncidentForm({
    ...validForm,
    latitude: '91',
    longitude: '-181',
  })
  assert.equal(errors.latitude, 'Enter a latitude between -90 and 90.')
  assert.equal(errors.longitude, 'Enter a longitude between -180 and 180.')
})

test('payload contains only IncidentCreate fields', () => {
  const payload = buildIncidentPayload(validForm)

  assert.deepEqual(payload, {
    category: 'pothole',
    description: 'Large pothole near the school gate.',
    latitude: 23.0225,
    longitude: 72.5714,
  })
  assert.equal('language' in payload, false)
  assert.equal('title' in payload, false)
  assert.equal('address' in payload, false)
})

test('blank coordinates stay undefined so createIncident omits them', () => {
  const payload = buildIncidentPayload({
    ...validForm,
    latitude: '',
    longitude: '',
  })

  assert.equal(payload.latitude, undefined)
  assert.equal(payload.longitude, undefined)
})

test('valid zero coordinates are preserved in the payload', () => {
  const payload = buildIncidentPayload({
    ...validForm,
    latitude: '0',
    longitude: '0',
  })

  assert.equal(payload.latitude, 0)
  assert.equal(payload.longitude, 0)
})

test('422 errors map to a validation message', () => {
  const error = describeIncidentRequestError({
    status: 422,
    message: 'Input should be a valid number',
  })

  assert.equal(error.title, 'The report needs attention')
  assert.match(error.guidance, /Check the category/)
})

test('503 errors map to a service unavailable message', () => {
  const error = describeIncidentRequestError({
    status: 503,
    message: 'Service unavailable',
  })

  assert.equal(error.title, 'Incident service unavailable')
  assert.match(error.guidance, /wait a moment/)
})

test('network errors map to retry guidance', () => {
  const error = describeIncidentRequestError({
    status: undefined,
    message: 'Network Error',
  })

  assert.equal(error.title, 'Could not reach the server')
  assert.match(error.guidance, /internet connection/)
})

test('unexpected server errors map to a generic retry message', () => {
  const error = describeIncidentRequestError({
    status: 500,
    message: 'Internal Server Error',
  })

  assert.equal(error.title, 'Could not submit the report')
  assert.match(error.guidance, /try again/i)
})

test('payload includes citizen-selected severity and priority', () => {
  const payload = buildIncidentPayload({
    ...validForm,
    severity: 'critical',
    priority: 'high',
  })

  assert.equal(payload.severity, 'critical')
  assert.equal(payload.priority, 'high')
  assert.equal('language' in payload, false)
})

test('classification suggestion prefills untouched fields', () => {
  const form = {
    ...validForm,
    category: '',
    severity: '',
    priority: '',
  }
  const suggestion = {
    category: 'water_leakage',
    severity: 'high',
    priority: 'critical',
  }

  const next = applyClassificationSuggestion(form, suggestion, {
    category: false,
    severity: false,
    priority: false,
  })

  assert.equal(next.category, 'water_leakage')
  assert.equal(next.severity, 'high')
  assert.equal(next.priority, 'critical')
})

test('classification suggestion never overwrites citizen edits', () => {
  const form = {
    ...validForm,
    category: 'garbage',
    severity: 'low',
    priority: 'medium',
  }
  const suggestion = {
    category: 'pothole',
    severity: 'critical',
    priority: 'critical',
  }

  const next = applyClassificationSuggestion(form, suggestion, {
    category: true,
    severity: true,
    priority: true,
  })

  assert.equal(next.category, 'garbage')
  assert.equal(next.severity, 'low')
  assert.equal(next.priority, 'medium')
})

test('classification suggestion updates only untouched fields', () => {
  const form = {
    ...validForm,
    category: 'garbage',
    severity: '',
    priority: '',
  }
  const suggestion = {
    category: 'pothole',
    severity: 'high',
    priority: 'high',
  }

  const next = applyClassificationSuggestion(form, suggestion, {
    category: true,
    severity: false,
    priority: false,
  })

  assert.equal(next.category, 'garbage')
  assert.equal(next.severity, 'high')
  assert.equal(next.priority, 'high')
})

test('classification 422 is a non-blocking insufficient-detail warning', () => {
  const error = describeClassificationError({
    status: 422,
    message: 'Complaint text must not be empty.',
  })

  assert.equal(error.title, 'Not enough detail to classify')
  assert.match(error.guidance, /choose the category/i)
})

test('classification 502 reports triage unavailable with manual fallback', () => {
  const error = describeClassificationError({
    status: 502,
    message: 'Provider failed',
  })

  assert.equal(error.title, 'Triage unavailable')
  assert.match(error.guidance, /still submit/i)
})

test('classification 501 is handled defensively', () => {
  const error = describeClassificationError({
    status: 501,
    message: 'Not configured',
  })

  assert.equal(error.title, 'Triage not configured')
  assert.match(error.guidance, /manually/i)
})

test('classification network errors allow manual submission', () => {
  const error = describeClassificationError({
    status: undefined,
    message: 'Network Error',
  })

  assert.equal(error.title, 'Triage could not be reached')
  assert.match(error.guidance, /continue with manual/i)
})
