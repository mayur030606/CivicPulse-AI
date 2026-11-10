import assert from 'node:assert/strict'
import test from 'node:test'

import {
  GEOLOCATION_OPTIONS,
  formatAccuracy,
  getGeolocationPermissionState,
  isGeolocationSupported,
  isSecureGeolocationContext,
  mapGeolocationError,
  normalizePosition,
  requestCurrentPosition,
  validateCoordinates,
} from '../src/lib/geolocation.js'

function geolocationStub({ position, error, throwError } = {}) {
  const calls = []

  return {
    calls,
    getCurrentPosition(success, failure, options) {
      calls.push({ success, failure, options })

      if (throwError) throw throwError
      if (error) {
        failure(error)
        return
      }

      success(position)
    },
  }
}

test('captures valid coordinates and accuracy', async () => {
  const geolocation = geolocationStub({
    position: {
      coords: {
        latitude: 23.0225,
        longitude: 72.5714,
        accuracy: 12.4,
      },
    },
  })

  const result = await requestCurrentPosition({
    geolocation,
    secureContext: true,
  })

  assert.deepEqual(result, {
    latitude: 23.0225,
    longitude: 72.5714,
    accuracy: 12.4,
  })
  assert.equal(geolocation.calls.length, 1)
  assert.deepEqual(geolocation.calls[0].options, GEOLOCATION_OPTIONS)
})

test('accepts valid zero coordinates and zero accuracy', async () => {
  const result = await requestCurrentPosition({
    geolocation: geolocationStub({
      position: {
        coords: { latitude: 0, longitude: 0, accuracy: 0 },
      },
    }),
    secureContext: true,
  })

  assert.deepEqual(result, {
    latitude: 0,
    longitude: 0,
    accuracy: 0,
  })
})

test('rejects invalid coordinates returned by the browser', async () => {
  const invalidCoordinates = [
    { latitude: 91, longitude: 0, accuracy: 10 },
    { latitude: 0, longitude: 181, accuracy: 10 },
    { latitude: Number.NaN, longitude: 0, accuracy: 10 },
    { latitude: 0, longitude: Number.POSITIVE_INFINITY, accuracy: 10 },
    { latitude: null, longitude: 0, accuracy: 10 },
    { latitude: '', longitude: 0, accuracy: 10 },
  ]

  for (const coords of invalidCoordinates) {
    await assert.rejects(
      () =>
        requestCurrentPosition({
          geolocation: geolocationStub({ position: { coords } }),
          secureContext: true,
        }),
      (error) => {
        assert.equal(error.code, 'invalid')
        return true
      },
    )
  }
})

test('maps permission denial to denied', async () => {
  await assert.rejects(
    () =>
      requestCurrentPosition({
        geolocation: geolocationStub({
          error: { code: 1, message: 'Permission denied' },
        }),
        secureContext: true,
      }),
    (error) => {
      assert.equal(error.code, 'denied')
      return true
    },
  )
})

test('maps an unavailable position to unavailable', async () => {
  await assert.rejects(
    () =>
      requestCurrentPosition({
        geolocation: geolocationStub({
          error: { code: 2, message: 'Position unavailable' },
        }),
        secureContext: true,
      }),
    (error) => {
      assert.equal(error.code, 'unavailable')
      return true
    },
  )
})

test('maps a location timeout to timeout', async () => {
  await assert.rejects(
    () =>
      requestCurrentPosition({
        geolocation: geolocationStub({
          error: { code: 3, message: 'Timeout' },
        }),
        secureContext: true,
      }),
    (error) => {
      assert.equal(error.code, 'timeout')
      return true
    },
  )
})

test('rejects when geolocation is unsupported', async () => {
  for (const geolocation of [null, {}, { getCurrentPosition: null }]) {
    await assert.rejects(
      () => requestCurrentPosition({ geolocation, secureContext: true }),
      (error) => {
        assert.equal(error.code, 'unsupported')
        return true
      },
    )
  }
})

test('rejects before requesting location in an insecure context', async () => {
  const geolocation = geolocationStub({
    position: {
      coords: { latitude: 23.0225, longitude: 72.5714, accuracy: 10 },
    },
  })

  await assert.rejects(
    () => requestCurrentPosition({ geolocation, secureContext: false }),
    (error) => {
      assert.equal(error.code, 'unavailable')
      return true
    },
  )
  assert.equal(geolocation.calls.length, 0)
})

test('maps synchronous geolocation failures to unavailable', async () => {
  await assert.rejects(
    () =>
      requestCurrentPosition({
        geolocation: geolocationStub({
          throwError: new Error('The browser refused the request.'),
        }),
        secureContext: true,
      }),
    (error) => {
      assert.equal(error.code, 'unavailable')
      return true
    },
  )
})

test('permission helper falls back when the Permissions API is unavailable', async () => {
  assert.equal(await getGeolocationPermissionState(undefined), 'unknown')
  assert.equal(await getGeolocationPermissionState({}), 'unknown')
  assert.equal(
    await getGeolocationPermissionState({ query: null }),
    'unknown',
  )
  assert.equal(
    await getGeolocationPermissionState({
      query: async () => {
        throw new Error('Permissions API unavailable')
      },
    }),
    'unknown',
  )
})

test('permission helper returns supported permission states', async () => {
  for (const state of ['granted', 'denied', 'prompt']) {
    assert.equal(
      await getGeolocationPermissionState({
        query: async () => ({ state }),
      }),
      state,
    )
  }

  assert.equal(
    await getGeolocationPermissionState({
      query: async () => ({ state: 'unknown-state' }),
    }),
    'unknown',
  )
})

test('coordinate validation accepts bounds and rejects non-finite values', () => {
  assert.deepEqual(validateCoordinates('-90', '180'), {
    latitude: -90,
    longitude: 180,
  })
  assert.deepEqual(validateCoordinates('0', '0'), {
    latitude: 0,
    longitude: 0,
  })
  assert.equal(validateCoordinates('90.1', '0'), null)
  assert.equal(validateCoordinates('0', '-180.1'), null)
  assert.equal(validateCoordinates('', '0'), null)
})

test('position normalization keeps optional accuracy separate from coordinates', () => {
  assert.deepEqual(
    normalizePosition({
      coords: { latitude: 0, longitude: 0, accuracy: undefined },
    }),
    { latitude: 0, longitude: 0, accuracy: null },
  )
  assert.equal(normalizePosition({ coords: {} }), null)
  assert.equal(normalizePosition(null), null)
})

test('accuracy formatting rounds finite non-negative values', () => {
  assert.equal(formatAccuracy(0), 0)
  assert.equal(formatAccuracy(12.6), 13)
  assert.equal(formatAccuracy(-1), null)
  assert.equal(formatAccuracy(null), null)
})

test('geolocation support and secure-context checks are defensive', () => {
  assert.equal(isGeolocationSupported(null), false)
  assert.equal(isGeolocationSupported({}), false)
  assert.equal(isGeolocationSupported({ getCurrentPosition: () => {} }), true)
  assert.equal(isSecureGeolocationContext(true), true)
  assert.equal(isSecureGeolocationContext(false), false)
  assert.equal(isSecureGeolocationContext(undefined), false)
})

test('browser error codes map to stable reasons', () => {
  assert.equal(mapGeolocationError({ code: 1 }), 'denied')
  assert.equal(mapGeolocationError({ code: 2 }), 'unavailable')
  assert.equal(mapGeolocationError({ code: 3 }), 'timeout')
  assert.equal(mapGeolocationError({ code: 'unsupported' }), 'unsupported')
  assert.equal(mapGeolocationError({ code: 99 }), 'unavailable')
})
