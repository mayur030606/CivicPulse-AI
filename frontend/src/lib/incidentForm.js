/**
 * Pure helpers for the citizen incident form. Keeping validation, payload
 * construction and error mapping here makes the form behavior testable without
 * a browser or a backend.
 */

export function validateIncidentForm(form) {
  const errors = {}

  if (!form.category) {
    errors.category = 'Choose a category.'
  }

  if (!form.description.trim()) {
    errors.description = 'Describe the issue before submitting.'
  }

  if (form.latitude !== '') {
    const latitude = Number(form.latitude)
    if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90) {
      errors.latitude = 'Enter a latitude between -90 and 90.'
    }
  }

  if (form.longitude !== '') {
    const longitude = Number(form.longitude)
    if (!Number.isFinite(longitude) || longitude < -180 || longitude > 180) {
      errors.longitude = 'Enter a longitude between -180 and 180.'
    }
  }

  return errors
}

export function buildIncidentPayload(form) {
  return {
    category: form.category,
    description: form.description.trim(),
    ...(form.severity ? { severity: form.severity } : {}),
    ...(form.priority ? { priority: form.priority } : {}),
    latitude: form.latitude === '' ? undefined : Number(form.latitude),
    longitude: form.longitude === '' ? undefined : Number(form.longitude),
  }
}

/**
 * Apply a classifier suggestion without overwriting fields the citizen has
 * already edited. ``touched`` is a map of field name to boolean.
 */
export function applyClassificationSuggestion(form, suggestion, touched = {}) {
  if (!suggestion) return form

  const next = { ...form }

  if (!touched.category && suggestion.category) {
    next.category = suggestion.category
  }
  if (!touched.severity && suggestion.severity) {
    next.severity = suggestion.severity
  }
  if (!touched.priority && suggestion.priority) {
    next.priority = suggestion.priority
  }

  return next
}

export function describeClassificationError(requestError) {
  if (requestError.status === 422) {
    return {
      title: 'Not enough detail to classify',
      message:
        requestError.message || 'The description could not be classified.',
      guidance:
        'Add a little more detail, or choose the category, severity and priority manually.',
    }
  }

  if (requestError.status === 502) {
    return {
      title: 'Triage unavailable',
      message:
        requestError.message || 'The rule-based classification service is unavailable.',
      guidance:
        'You can still submit the report by choosing the category, severity and priority manually.',
    }
  }

  if (requestError.status === 501) {
    return {
      title: 'Triage not configured',
      message:
        requestError.message || 'The classification service is not available in this environment.',
      guidance:
        'You can still submit the report by choosing the category, severity and priority manually.',
    }
  }

  if (!requestError.status) {
    return {
      title: 'Triage could not be reached',
      message:
        requestError.message || 'The classification request did not reach the server.',
      guidance:
        'Check your connection, or continue with manual category, severity and priority selections.',
    }
  }

  return {
    title: 'Triage unavailable',
    message: requestError.message || 'The classification service returned an error.',
    guidance:
      'You can still submit the report by choosing the category, severity and priority manually.',
  }
}

export function describeIncidentRequestError(requestError) {
  if (requestError.status === 422) {
    return {
      title: 'The report needs attention',
      message:
        requestError.message || 'The backend rejected one or more fields.',
      guidance:
        'Check the category, severity, priority, description length and coordinates, then submit again.',
    }
  }

  if (requestError.status === 503) {
    return {
      title: 'Incident service unavailable',
      message:
        requestError.message || 'The incident service is temporarily unavailable.',
      guidance:
        'Please wait a moment and try again. Your report has not been submitted.',
    }
  }

  if (!requestError.status) {
    return {
      title: 'Could not reach the server',
      message: requestError.message || 'The request did not reach the incident API.',
      guidance:
        'Check your internet connection and make sure the backend is running, then retry.',
    }
  }

  return {
    title: 'Could not submit the report',
    message: requestError.message || 'The server returned an unexpected error.',
    guidance: 'Please try again. If the problem continues, contact the civic helpline.',
  }
}
