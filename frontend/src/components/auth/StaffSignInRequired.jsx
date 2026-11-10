import { useLocation } from 'react-router-dom'
import Button from '../ui/Button.jsx'
import Card from '../ui/Card.jsx'
import PageHeader from '../ui/PageHeader.jsx'

export default function StaffSignInRequired({
  title = 'Staff access required',
  description = 'This information is restricted to signed-in municipal staff.',
}) {
  const location = useLocation()
  const from = `${location.pathname}${location.search}${location.hash}`

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Protected information" title={title} description={description} />

      <Card>
        <h2 className="text-lg font-semibold text-slate-900">
          Sign in with a staff account
        </h2>
        <p className="mt-2 max-w-2xl text-sm text-slate-600">
          Incident records are protected by role-based access control. Citizens
          can still report a new issue or track an existing complaint without an
          account.
        </p>
        <div className="mt-5 flex flex-wrap gap-2">
          <Button to="/login" state={{ from }}>
            Staff sign in
          </Button>
          <Button to="/tracking" variant="secondary">
            Track a complaint
          </Button>
          <Button to="/report" variant="ghost">
            Report an issue
          </Button>
        </div>
      </Card>
    </div>
  )
}
