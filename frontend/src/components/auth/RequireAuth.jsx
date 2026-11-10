import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext.jsx'
import { routeGuardDecision } from '../../lib/routeAccess.js'
import AccessDenied from './AccessDenied.jsx'
import AuthLoadingScreen from './AuthLoadingScreen.jsx'

/**
 * Route guard for authenticated staff areas.
 *
 * The guard improves the user experience by redirecting anonymous visitors
 * and showing a 403 screen for insufficient roles. The backend repeats both
 * checks on every protected request.
 */
export default function RequireAuth({ roles, children }) {
  const { status, user } = useAuth()
  const location = useLocation()
  const from = `${location.pathname}${location.search}${location.hash}`

  const decision = routeGuardDecision({
    status,
    user,
    roles,
    pathname: location.pathname,
    from,
  })

  if (decision.type === 'loading') return <AuthLoadingScreen />

  if (decision.type === 'redirect') {
    return <Navigate to={decision.to} replace state={{ from: decision.from }} />
  }

  if (decision.type === 'forbidden') {
    return (
      <AccessDenied
        title="Access denied"
        description="Your account does not have the role required for this staff page. The backend API enforces the same restriction."
      />
    )
  }

  return children ?? <Outlet />
}
