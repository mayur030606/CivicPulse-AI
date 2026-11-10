import { cx } from '../../lib/cx'
import { PRIORITY_STYLES, STATUS_STYLES } from '../../lib/constants'
import { formatLabel, formatStatusLabel, statusStyleKey } from '../../lib/format.js'

const NEUTRAL_BADGE_STYLE = 'bg-slate-50 text-slate-500 ring-slate-200'

function Badge({ className, children }) {
  return (
    <span
      className={cx(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset',
        className,
      )}
    >
      {children}
    </span>
  )
}

export function StatusBadge({ status }) {
  const hasStatus = status != null && String(status).trim() !== ''
  const style = hasStatus
    ? STATUS_STYLES[statusStyleKey(status)] || NEUTRAL_BADGE_STYLE
    : NEUTRAL_BADGE_STYLE

  return <Badge className={style}>{formatStatusLabel(status)}</Badge>
}

export function PriorityBadge({ priority }) {
  const hasPriority = priority != null && String(priority).trim() !== ''
  const key = String(priority ?? '')
    .trim()
    .toLowerCase()
  const style = hasPriority
    ? PRIORITY_STYLES[key] || NEUTRAL_BADGE_STYLE
    : NEUTRAL_BADGE_STYLE

  return <Badge className={style}>{formatLabel(priority, 'Not set')}</Badge>
}
