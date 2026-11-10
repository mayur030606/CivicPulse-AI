export function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

export function formatCoordinate(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  return number.toFixed(5)
}

export function formatLabel(value, fallback = '—') {
  if (value == null || value === '') return fallback

  return String(value)
    .trim()
    .replaceAll('_', ' ')
    .replace(/\s+/g, ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase())
}

export function formatStatusLabel(status) {
  return formatLabel(status, 'Unknown')
}

export function statusStyleKey(status) {
  return String(status ?? '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '_')
}
