import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { AUTH_STATUS, authErrorMessage, safeRedirectPath } from '../lib/auth.js'
import Button from '../components/ui/Button.jsx'
import Card from '../components/ui/Card.jsx'
import PageHeader from '../components/ui/PageHeader.jsx'

export default function LoginPage() {
  const { status, login, sessionExpired, clearSessionExpired } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const redirectTo = safeRedirectPath(location.state?.from, '/dashboard')

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (status === AUTH_STATUS.AUTHENTICATED) {
    return <Navigate to={redirectTo} replace />
  }

  async function handleSubmit(event) {
    event.preventDefault()

    const normalizedEmail = email.trim()
    if (!normalizedEmail || !password) {
      setError('Enter your staff email and password.')
      return
    }

    setSubmitting(true)
    setError('')
    clearSessionExpired()

    try {
      await login(normalizedEmail, password)
      navigate(redirectTo, { replace: true })
    } catch (requestError) {
      setError(authErrorMessage(requestError))
      setPassword('')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-lg space-y-6 py-6 sm:py-12">
      <PageHeader
        eyebrow="Staff access"
        title="Sign in"
        description="Use an administrator, dispatcher, or viewer account to access protected municipal data."
      />

      {sessionExpired ? (
        <div
          className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
          role="status"
        >
          Your session expired. Sign in again to continue where you left off.
        </div>
      ) : null}

      <Card>
        <form className="space-y-5" onSubmit={handleSubmit}>
          <div>
            <label
              htmlFor="login-email"
              className="block text-sm font-medium text-slate-700"
            >
              Email
            </label>
            <input
              id="login-email"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm shadow-sm outline-none focus:border-civic-500 focus:ring-2 focus:ring-civic-200"
            />
          </div>

          <div>
            <label
              htmlFor="login-password"
              className="block text-sm font-medium text-slate-700"
            >
              Password
            </label>
            <input
              id="login-password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm shadow-sm outline-none focus:border-civic-500 focus:ring-2 focus:ring-civic-200"
            />
          </div>

          {error ? (
            <p
              className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700"
              role="alert"
            >
              {error}
            </p>
          ) : null}

          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>
      </Card>

      <div className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-600 shadow-sm">
        <p className="font-medium text-slate-900">Citizen services</p>
        <p className="mt-1">
          Reporting and complaint tracking do not require a staff account.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button to="/report" variant="secondary" size="sm">
            Report an issue
          </Button>
          <Button to="/tracking" variant="ghost" size="sm">
            Track a complaint
          </Button>
          <Button to="/" variant="ghost" size="sm">
            Back to home
          </Button>
        </div>
      </div>
    </div>
  )
}
