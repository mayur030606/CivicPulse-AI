import axios from 'axios'
import { notifyUnauthorized } from '../lib/authEvents.js'

/**
 * Shared Axios instance for both public citizen and authenticated staff APIs.
 *
 * Authentication is cookie-based. `withCredentials` is required when the
 * frontend and API are on different origins, and the browser sends the
 * HttpOnly session cookie automatically. The non-HttpOnly CSRF cookie is
 * echoed in the `X-CSRF-Token` header for unsafe methods.
 *
 * These names mirror backend/app/core/config.py. Keep them in sync with the
 * backend deployment.
 */
export const CSRF_COOKIE_NAME = 'civicpulse_csrf'
export const CSRF_HEADER_NAME = 'X-CSRF-Token'

const UNSAFE_METHODS = new Set(['post', 'put', 'patch', 'delete'])
const AUTH_PROBE_PATHS = ['/auth/login', '/auth/me']

function currentCookieString() {
  return typeof document !== 'undefined' ? document.cookie : ''
}

function isUnsafeMethod(method) {
  return UNSAFE_METHODS.has(String(method || 'get').trim().toLowerCase())
}

/**
 * Read a cookie by name from a cookie string. This is exported so the CSRF
 * behaviour can be tested without a browser.
 */
export function getCookieValue(name, cookieString = currentCookieString()) {
  if (!name || !cookieString) return ''

  const prefix = `${name}=`
  for (const part of String(cookieString).split(';')) {
    const trimmed = part.trim()
    if (!trimmed.startsWith(prefix)) continue

    const rawValue = trimmed.slice(prefix.length)
    try {
      return decodeURIComponent(rawValue)
    } catch {
      return rawValue
    }
  }

  return ''
}

export function csrfTokenFromCookie(cookieString = currentCookieString()) {
  return getCookieValue(CSRF_COOKIE_NAME, cookieString)
}

/**
 * Build the CSRF header for a request. Safe methods never carry it.
 */
export function csrfHeadersForRequest(
  method,
  cookieString = currentCookieString(),
) {
  if (!isUnsafeMethod(method)) return {}

  const token = csrfTokenFromCookie(cookieString)
  return token ? { [CSRF_HEADER_NAME]: token } : {}
}

function setHeader(config, name, value) {
  if (typeof config.headers?.set === 'function') {
    config.headers.set(name, value)
    return
  }

  config.headers = { ...(config.headers || {}), [name]: value }
}

/**
 * The Axios instance used by every API module. In development the Vite proxy
 * forwards `/api` to FastAPI, so the default relative base URL works without
 * CORS. Set VITE_API_BASE_URL to point at a deployed backend (for example
 * https://api.example.org/api/v1).
 */
const apiClient = axios.create({
  baseURL: import.meta.env?.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

/**
 * The default JSON content type above is correct for object bodies, but it
 * makes Axios serialize FormData as JSON. Remove it for uploads so the
 * browser/runtime can add the multipart boundary itself.
 *
 * The same interceptor attaches the CSRF token to authenticated writes. The
 * token is read at request time so login/logout and session expiry are handled
 * without storing credentials in JavaScript.
 */
apiClient.interceptors.request.use((config) => {
  const isFormData =
    typeof FormData !== 'undefined' && config.data instanceof FormData

  if (isFormData) {
    if (typeof config.headers?.set === 'function') {
      config.headers.set('Content-Type', null)
    } else if (config.headers) {
      config.headers['Content-Type'] = null
      delete config.headers['content-type']
    }
  }

  const csrfHeaders = csrfHeadersForRequest(config.method)
  for (const [name, value] of Object.entries(csrfHeaders)) {
    setHeader(config, name, value)
  }

  return config
})

/**
 * Build per-request config for a multipart/form-data upload.
 *
 * A FormData body is enough on its own; use this helper when the request also
 * needs custom headers or other Axios options (for example upload progress).
 */
export function multipartConfig(config = {}) {
  const { headers, ...rest } = config

  return {
    ...rest,
    headers: {
      ...headers,
      // Null removes the shared JSON header; the request interceptor also
      // handles plain FormData calls that do not use this helper.
      'Content-Type': null,
    },
  }
}

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error.response?.data?.detail
    const message =
      typeof detail === 'string'
        ? detail
        : detail?.[0]?.msg || error.message || 'Request failed'
    const requestError = new Error(message)
    // Preserve response metadata so callers can distinguish validation (422),
    // authentication (401), authorization (403), service availability (503)
    // and network failures without re-parsing text.
    requestError.status = error.response?.status
    requestError.code = error.code
    requestError.detail = detail

    const url = String(error.config?.url || '')
    const isAuthProbe = AUTH_PROBE_PATHS.some((path) => url.endsWith(path))
    if (requestError.status === 401 && !isAuthProbe) {
      notifyUnauthorized()
    }

    return Promise.reject(requestError)
  },
)

export default apiClient
