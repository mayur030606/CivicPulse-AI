/**
 * Browser geolocation helpers.
 *
 * These helpers deliberately do not guess a location. They only normalize
 * coordinates returned by the browser and expose a small, testable surface for
 * the report form.
 */

export const GEOLOCATION_OPTIONS = Object.freeze({
  enableHighAccuracy: true,
  timeout: 10000,
  maximumAge: 60000,
})

export class GeolocationError extends Error {
  constructor(code, message, cause) {
    super(message)
    this.name = 'GeolocationError'
    this.code = code
    this.cause = cause
  }
}

function finiteCoordinate(value, min, max) {
  if (value == null || value === '') return null
  if (typeof value !== 'number' && typeof value !== 'string') return null
  if (typeof value === 'string' && value.trim() === '') return null

  const number = Number(value)
  if (!Number.isFinite(number) || number < min || number > max) return null

  return number
}

export function validateCoordinates(latitude, longitude) {
  const lat = finiteCoordinate(latitude, -90, 90)
  const lng = finiteCoordinate(longitude, -180, 180)

  if (lat == null || lng == null) return null

  return { latitude: lat, longitude: lng }
}

export function normalizePosition(position) {
  const coords = position?.coords
  if (!coords) return null

  const coordinates = validateCoordinates(coords.latitude, coords.longitude)
  if (!coordinates) return null

  const accuracy =
    typeof coords.accuracy === 'number' &&
    Number.isFinite(coords.accuracy) &&
    coords.accuracy >= 0
      ? coords.accuracy
      : null

  return { ...coordinates, accuracy }
}

export function formatAccuracy(accuracy) {
  if (
    typeof accuracy !== 'number' ||
    !Number.isFinite(accuracy) ||
    accuracy < 0
  ) {
    return null
  }

  return Math.round(accuracy)
}

export function mapGeolocationError(error) {
  const code = error?.code

  if (code === 1 || code === 'PERMISSION_DENIED' || code === 'denied') {
    return 'denied'
  }
  if (code === 2 || code === 'POSITION_UNAVAILABLE' || code === 'unavailable') {
    return 'unavailable'
  }
  if (code === 3 || code === 'TIMEOUT' || code === 'timeout') {
    return 'timeout'
  }
  if (code === 'unsupported') {
    return 'unsupported'
  }

  return 'unavailable'
}

export function isSecureGeolocationContext(
  secureContext = globalThis.isSecureContext,
) {
  return secureContext === true
}

export function isGeolocationSupported(
  geolocation = globalThis.navigator?.geolocation,
) {
  return Boolean(
    geolocation && typeof geolocation.getCurrentPosition === 'function',
  )
}

/**
 * Return ``granted``, ``denied``, ``prompt`` or ``unknown``.
 *
 * The Permissions API is not available in every browser, and querying it can
 * throw. In either case, callers should treat the state as unknown and avoid
 * automatically prompting for permission.
 */
export async function getGeolocationPermissionState(
  permissions = globalThis.navigator?.permissions,
) {
  if (!permissions || typeof permissions.query !== 'function') {
    return 'unknown'
  }

  try {
    const status = await permissions.query({ name: 'geolocation' })
    if (
      status?.state === 'granted' ||
      status?.state === 'denied' ||
      status?.state === 'prompt'
    ) {
      return status.state
    }
  } catch {
    return 'unknown'
  }

  return 'unknown'
}

export function requestCurrentPosition({
  geolocation = globalThis.navigator?.geolocation,
  secureContext = globalThis.isSecureContext,
  options = {},
} = {}) {
  if (!isSecureGeolocationContext(secureContext)) {
    return Promise.reject(
      new GeolocationError(
        'unavailable',
        'Location requires HTTPS or localhost.',
      ),
    )
  }

  if (!isGeolocationSupported(geolocation)) {
    return Promise.reject(
      new GeolocationError(
        'unsupported',
        'Geolocation is not available in this browser.',
      ),
    )
  }

  return new Promise((resolve, reject) => {
    try {
      geolocation.getCurrentPosition(
        (position) => {
          const normalized = normalizePosition(position)
          if (!normalized) {
            reject(
              new GeolocationError(
                'invalid',
                'The browser returned invalid coordinates.',
              ),
            )
            return
          }

          resolve(normalized)
        },
        (error) => {
          const code = mapGeolocationError(error)
          reject(
            new GeolocationError(
              code,
              error?.message || 'Unable to read the current location.',
              error,
            ),
          )
        },
        { ...GEOLOCATION_OPTIONS, ...options },
      )
    } catch (error) {
      reject(
        new GeolocationError(
          'unavailable',
          error?.message || 'Unable to request the current location.',
          error,
        ),
      )
    }
  })
}
