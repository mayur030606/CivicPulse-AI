import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext.jsx'
import { AUTH_STATUS, safeRedirectPath } from '../../lib/auth.js'
import AuthLoadingScreen from './AuthLoadingScreen.jsx'

export default function PublicOnlyRoute({ children }) {
  const { status } = useAuth()
  const location = useLocation()

  if (status === AUTH_STATUS.LOADING) {
    return <AuthLoadingScreen />
  }

  if (status === AUTH_STATUS.AUTHENTICATED) {
    return (
      <Navigate
        to={safeRedirectPath(location.state?.from, '/dashboard')}
        replace
      />
    )
  }

  return children
}
