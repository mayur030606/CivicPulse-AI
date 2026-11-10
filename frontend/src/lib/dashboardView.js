import {
  incidentCategoryLabel,
  incidentPriorityLabel,
  incidentSeverityLabel,
  incidentStatusLabel,
} from './incidentsView.js'
import { formatLabel } from './format.js'

const MISSING_GROUP_VALUES = new Set(['none', 'null', 'undefined'])

const MISSING_LABELS = {
  category: 'Uncategorised',
  status: 'Unknown',
  priority: 'Not set',
  severity: 'Not set',
}

function isMissingGroupValue(value) {
  if (value == null) return true

  const normalized = String(value).trim()
  return normalized === '' || MISSING_GROUP_VALUES.has(normalized.toLowerCase())
}

function toCount(value) {
  const count = Number(value)
  if (!Number.isFinite(count) || count < 0) return 0
  return Math.trunc(count)
}

function groupLabel(dimension, value) {
  if (isMissingGroupValue(value)) return MISSING_LABELS[dimension]

  switch (dimension) {
    case 'category':
      return incidentCategoryLabel(value)
    case 'status':
      return incidentStatusLabel(value)
    case 'priority':
      return incidentPriorityLabel(value)
    case 'severity':
      return incidentSeverityLabel(value)
    default:
      return formatLabel(value)
  }
}

function mapGroups(groups, dimension) {
  if (!Array.isArray(groups)) return []

  return groups.map((group) => {
    const rawValue = group?.value

    return {
      value: rawValue == null ? '' : String(rawValue),
      label: groupLabel(dimension, rawValue),
      count: toCount(group?.count),
    }
  })
}

export function mapGroupCounts(groups, dimension) {
  return mapGroups(groups, dimension)
}

export function mapDashboardSummary(summary = {}) {
  return {
    total: toCount(summary?.total),
    byStatus: mapGroups(summary?.by_status, 'status'),
    byPriority: mapGroups(summary?.by_priority, 'priority'),
    bySeverity: mapGroups(summary?.by_severity, 'severity'),
    byCategory: mapGroups(summary?.by_category, 'category'),
  }
}

export function dashboardState({
  loading = false,
  error = '',
  summary = null,
} = {}) {
  if (loading) return 'loading'
  if (error) return 'error'
  if (!summary || toCount(summary.total) === 0) return 'empty'
  return 'ready'
}

export function maxGroupCount(groups = []) {
  if (!Array.isArray(groups) || groups.length === 0) return 0
  return groups.reduce((max, group) => Math.max(max, toCount(group?.count)), 0)
}

export function categoryBarPercent(count, max) {
  const safeMax = Number(max)
  if (!Number.isFinite(safeMax) || safeMax <= 0) return 0
  return Math.max(0, Math.min(100, (toCount(count) / safeMax) * 100))
}
