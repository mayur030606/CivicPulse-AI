import Button from '../components/ui/Button.jsx'

export default function NotFoundPage() {
  return (
    <div className="mx-auto max-w-lg py-20 text-center">
      <p className="font-mono text-sm font-semibold text-civic-600">404</p>
      <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-900">
        Page not found
      </h1>
      <p className="mt-3 text-sm text-slate-600">
        The page you are looking for does not exist or has moved.
      </p>
      <div className="mt-6">
        <Button to="/">Back to home</Button>
      </div>
    </div>
  )
}
