export const number = (value) =>
  typeof value === 'number' ? value.toLocaleString('en-US') : (value ?? 0).toLocaleString?.() ?? '0'

export const percent = (value, digits = 1) =>
  `${Number(value || 0).toFixed(digits)}%`

export const currency = (value) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(Number(value || 0))

export const bytes = (value) => {
  const size = Number(value || 0)
  if (size < 1024) return `${size} B`
  if (size < 1024 ** 2) return `${(size / 1024).toFixed(0)} KB`
  if (size < 1024 ** 3) return `${(size / 1024 ** 2).toFixed(1)} MB`
  return `${(size / 1024 ** 3).toFixed(2)} GB`
}

export function relativeTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  const seconds = Math.round((Date.now() - date.getTime()) / 1000)
  if (Number.isNaN(seconds)) return '—'
  const units = [
    ['y', 31536000], ['mo', 2592000], ['d', 86400], ['h', 3600], ['m', 60],
  ]
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return `${Math.round(seconds / size)}${unit} ago`
  }
  return 'just now'
}

export function dateTime(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export function dateOnly(value) {
  if (!value) return '—'
  return new Date(value).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
}

export const titleCase = (value = '') =>
  String(value).replace(/_/g, ' ').replace(/\w\S*/g, (word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
