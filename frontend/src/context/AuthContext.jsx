import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
} from 'react'
import {
  getCurrentUser as getCurrentUserRequest,
  login as loginRequest,
  logout as logoutRequest,
} from '../api/auth.js'
import {
  AUTH_STATUS,
  authReducer,
  initialAuthState,
  isUnauthorizedError,
  normalizeUser,
} from '../lib/auth.js'
import { AUTH_UNAUTHORIZED_EVENT } from '../lib/authEvents.js'
import { requestErrorMessage } from '../lib/requestState.js'

export const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [state, dispatch] = useReducer(authReducer, undefined, initialAuthState)

  useEffect(() => {
    let active = true

    getCurrentUserRequest()
      .then((user) => {
        if (active) dispatch({ type: 'restore_succeeded', user })
      })
      .catch((error) => {
        if (!active) return
        dispatch({
          type: 'restore_failed',
          error: isUnauthorizedError(error)
            ? ''
            : requestErrorMessage(error, 'Unable to restore the session.'),
        })
      })

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    function handleUnauthorized() {
      dispatch({ type: 'session_expired' })
    }

    if (typeof window !== 'undefined') {
      window.addEventListener(AUTH_UNAUTHORIZED_EVENT, handleUnauthorized)
    }

    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, handleUnauthorized)
      }
    }
  }, [])

  const login = useCallback(async (email, password) => {
    const user = normalizeUser(await loginRequest(email, password))
    if (!user) {
      throw new Error('The server returned an unsupported account response.')
    }

    dispatch({ type: 'login_succeeded', user })
    return user
  }, [])

  const logout = useCallback(async () => {
    try {
      await logoutRequest()
      dispatch({ type: 'logout_succeeded' })
    } catch (error) {
      // An expired session is already unusable; clear the local state so the
      // guard can send the user back to the login page.
      if (isUnauthorizedError(error)) {
        dispatch({ type: 'logout_succeeded' })
        return
      }
      throw error
    }
  }, [])

  const clearSessionExpired = useCallback(() => {
    dispatch({ type: 'clear_session_expired' })
  }, [])

  const value = useMemo(
    () => ({
      ...state,
      isAuthenticated: state.status === AUTH_STATUS.AUTHENTICATED,
      isLoading: state.status === AUTH_STATUS.LOADING,
      login,
      logout,
      clearSessionExpired,
    }),
    [state, login, logout, clearSessionExpired],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider.')
  }
  return context
}
