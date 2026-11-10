import Spinner from '../ui/Spinner.jsx'

export default function AuthLoadingScreen({
  label = 'Checking your session…',
}) {
  return (
    <div className="mx-auto flex min-h-[40vh] max-w-md items-center justify-center">
      <Spinner label={label} />
    </div>
  )
}
