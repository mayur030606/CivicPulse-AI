import Card from '../ui/Card.jsx'
import { PriorityBadge, StatusBadge } from '../ui/Badge.jsx'
import { formatDate } from '../../lib/format.js'
import { incidentToCard } from '../../lib/incidentsView.js'

export default function ComplaintCard({ incident, actions }) {
  const view = incidentToCard(incident)

  return (
    <Card className="transition-shadow hover:shadow-md">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-civic-600">
            {view.categoryLabel}
          </p>
          <p className="mt-2 text-xs font-medium uppercase tracking-wide text-slate-400">
            Tracking ID
          </p>
          <h2 className="font-mono text-base font-semibold text-slate-900">
            {view.trackingId || '—'}
          </h2>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge status={view.status} />
          <PriorityBadge priority={view.priority} />
        </div>
      </div>

      <p className="mt-3 whitespace-pre-line text-sm text-slate-600">
        {view.description || 'No description provided.'}
      </p>

      <dl className="mt-4 grid grid-cols-2 gap-2 border-t border-slate-100 pt-3 text-xs text-slate-500 sm:grid-cols-4">
        <div>
          <dt className="font-medium text-slate-400">Category</dt>
          <dd className="mt-0.5 text-slate-700">{view.categoryLabel}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-400">Severity</dt>
          <dd className="mt-0.5 text-slate-700">{view.severityLabel}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-400">Location</dt>
          <dd className="mt-0.5 text-slate-700">{view.coordinatesLabel}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-400">Reported</dt>
          <dd className="mt-0.5 text-slate-700">{formatDate(view.createdAt)}</dd>
        </div>
      </dl>

      {actions ? (
        <div className="mt-4 flex flex-wrap justify-end gap-2 border-t border-slate-100 pt-3">
          {actions}
        </div>
      ) : null}
    </Card>
  )
}
