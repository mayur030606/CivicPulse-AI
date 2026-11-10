const CURRENT_YEAR = new Date().getFullYear()

export default function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 text-sm text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>© {CURRENT_YEAR} CivicPulse AI. Built for safer, cleaner cities.</p>
        <p className="text-xs">
          Scaffold build — AI services are not connected yet.
        </p>
      </div>
    </footer>
  )
}
