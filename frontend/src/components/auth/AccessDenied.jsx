import Button from '../ui/Button.jsx'
import Card from '../ui/Card.jsx'

export default function AccessDenied({
  title = 'Access denied',
  description = 'Your account does not have permission to view this page.',
  compact = false,
}) {
  return (
    <div className={compact ? '' : 'mx-auto max-w-lg py-12'}>
      <Card className="text-center">
        <p className="font-mono text-sm font-semibold text-rose-600">403</p>
        <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900">
          {title}
        </h1>
        <p className="mt-3 text-sm text-slate-600">{description}</p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <Button to="/dashboard">Go to dashboard</Button>
          <Button to="/" variant="secondary">
            Back to home
          </Button>
        </div>
      </Card>
    </div>
  )
}
