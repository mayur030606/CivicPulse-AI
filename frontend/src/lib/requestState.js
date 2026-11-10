import {
  isForbiddenError,
  isNotFoundError,
  isUnauthorizedError,
} from './auth.js'

export function requestErrorKind(error) {
  if (!error) return 'none'
  if (isUnauthorizedError(error)) return 'unauthorized'
  if (isForbiddenError(error)) return 'forbidden'
  if (isNotFoundError(error)) return 'not-found'
  return 'error'
}

export function requestErrorMessage(error, fallback = 'Unable to load data.') {
  if (!error) return ''

  if (isUnauthorizedError(error)) {
    return 'Your session expired. Sign in again to continue.'
  }
  if (isForbiddenError(error)) {
    return 'Your account does not have permission to access this data.'
  }
  if (isNotFoundError(error)) {
    return 'The requested record was not found.'
  }
  if (error.status === 422) {
    return 'The request was rejected. Check the values and try again.'
  }
  if (error.status === 429) {
    return 'Too many requests. Wait a moment and try again.'
  }
  if (error.status >= 500) {
    return 'The service is temporarily unavailable. Try again.'
  }
  if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
    return 'The request timed out. Try again.'
  }
  if (error.status == null) {
    return 'Unable to reach the server. Check the connection and try again.'
  }

  const message = typeof error.message === 'string' ? error.message.trim() : ''
  return message || fallback
}
