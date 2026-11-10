import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext.jsx'
import { AUTH_STATUS } from '../../lib/auth.js'
import { cx } from '../../lib/cx'
import { formatLabel } from '../../lib/format.js'
import { requestErrorMessage } from '../../lib/requestState.js'
import {
  citizenNavigationFor,
  staffNavigationFor,
} from '../../lib/routeAccess.js'
import Button from '../ui/Button.jsx'

function navClass({ isActive }, mobile = false) {
  if (mobile) {
    return cx(
      'whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium',
      isActive ? 'bg-civic-50 text-civic-700' : 'text-slate-600',
    )
  }

  return cx(
    'rounded-lg px-3 py-2 text-sm font-medium transition-colors',
    isActive
      ? 'bg-civic-50 text-civic-700'
      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
  )
}

export default function Navbar() {
  const { status, user, logout } = useAuth()
  const navigate = useNavigate()
  const [loggingOut, setLoggingOut] = useState(false)
  const [logoutError, setLogoutError] = useState('')

  const authenticated = status === AUTH_STATUS.AUTHENTICATED
  const links = authenticated
    ? [
        ...citizenNavigationFor(user, { authenticated: true }),
        ...staffNavigationFor(user),
      ]
    : citizenNavigationFor(null)

  async function handleLogout() {
    setLoggingOut(true)
    setLogoutError('')

    try {
      await logout()
      navigate('/login', { replace: true })
    } catch (error) {
      setLogoutError(requestErrorMessage(error, 'Could not sign out. Try again.'))
    } finally {
      setLoggingOut(false)
    }
  }

  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-3 px-4 sm:px-6">
        <NavLink to="/" className="flex items-center gap-2.5">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-civic-600 text-white">
            <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden="true">
              <path
                d="M3 12h4l2.2-6 4.2 12 2.3-6H21"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
          <span className="hidden text-base font-bold tracking-tight text-slate-900 sm:inline">
            CivicPulse <span className="text-civic-600">AI</span>
          </span>
        </NavLink>

        <nav className="hidden items-center gap-1 md:flex" aria-label="Main">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={(state) => navClass(state)}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          {authenticated ? (
            <>
              <div className="hidden text-right leading-tight lg:block">
                <p className="max-w-48 truncate text-xs font-medium text-slate-700">
                  {user?.email}
                </p>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-civic-600">
                  {formatLabel(user?.role, 'Staff')}
                </p>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={handleLogout}
                disabled={loggingOut}
              >
                {loggingOut ? 'Signing out…' : 'Sign out'}
              </Button>
            </>
          ) : (
            <Button to="/login" variant="secondary" size="sm">
              Staff sign in
            </Button>
          )}

          <Button to="/report" size="sm" className="hidden sm:inline-flex">
            Report an issue
          </Button>
        </div>
      </div>

      {logoutError ? (
        <div
          className="border-t border-rose-100 bg-rose-50 px-4 py-2 text-sm text-rose-700 sm:px-6"
          role="alert"
        >
          {logoutError}
        </div>
      ) : null}

      <nav
        className="flex gap-1 overflow-x-auto border-t border-slate-100 px-4 py-2 md:hidden"
        aria-label="Mobile"
      >
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            className={(state) => navClass(state, true)}
          >
            {link.label}
          </NavLink>
        ))}
      </nav>
    </header>
  )
}
