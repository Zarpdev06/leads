/** Small, dependency-free UI primitives. */
import { useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import { AlertTriangle, CheckCircle2, Info, Loader2, X, XCircle } from 'lucide-react'

export function Card({ className, children, padded = true, ...rest }) {
  return (
    <div className={clsx('card', padded && 'card-pad', className)} {...rest}>{children}</div>
  )
}

export function StatCard({ label, value, hint, icon: Icon, tone = 'brand', to }) {
  const tones = {
    brand: 'bg-brand-50 text-brand-600 dark:bg-brand-950 dark:text-brand-400',
    green: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400',
    amber: 'bg-amber-50 text-amber-600 dark:bg-amber-950 dark:text-amber-400',
    rose: 'bg-rose-50 text-rose-600 dark:bg-rose-950 dark:text-rose-400',
    slate: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
  }
  const content = (
    <Card className="flex items-start justify-between gap-3">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
        <p className="mt-1.5 text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">{value}</p>
        {hint && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
      </div>
      {Icon && (
        <span className={clsx('rounded-lg p-2', tones[tone])}>
          <Icon className="h-5 w-5" />
        </span>
      )}
    </Card>
  )
  if (to) return <a href={to} className="block transition hover:opacity-90">{content}</a>
  return content
}

export function Badge({ children, className, tone = 'slate' }) {
  const tones = {
    slate: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
    green: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300',
    amber: 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300',
    rose: 'bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300',
    brand: 'bg-brand-100 text-brand-700 dark:bg-brand-950 dark:text-brand-300',
  }
  return <span className={clsx('chip', tones[tone] || tones.slate, className)}>{children}</span>
}

export function Button({ className, variant = 'primary', size, loading, children, ...rest }) {
  const variants = {
    primary: 'btn-primary', secondary: 'btn-secondary', ghost: 'btn-ghost', danger: 'btn-danger',
  }
  return (
    <button
      className={clsx(variants[variant], size === 'sm' && 'btn-sm', className)}
      disabled={loading || rest.disabled}
      {...rest}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  )
}

export function Input({ label, hint, error, className, ...rest }) {
  return (
    <div className={className}>
      {label && <label className="label">{label}</label>}
      <input className={clsx('input', error && 'border-rose-500')} {...rest} />
      {error && <p className="mt-1 text-xs text-rose-600">{error}</p>}
      {hint && !error && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
    </div>
  )
}

export function Select({ label, hint, error, className, options = [], children, ...rest }) {
  return (
    <div className={className}>
      {label && <label className="label">{label}</label>}
      <select className={clsx('input', error && 'border-rose-500')} {...rest}>
        {children ||
          options.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
      </select>
      {hint && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
    </div>
  )
}

export function Textarea({ label, hint, className, ...rest }) {
  return (
    <div className={className}>
      {label && <label className="label">{label}</label>}
      <textarea rows={4} className="input" {...rest} />
      {hint && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
    </div>
  )
}

export function Toggle({ checked, onChange, label, hint }) {
  return (
    <label className="flex items-start gap-3">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={clsx(
          'relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition',
          checked ? 'bg-brand-600' : 'bg-slate-300 dark:bg-slate-700',
        )}
      >
        <span
          className={clsx(
            'absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition',
            checked ? 'left-4' : 'left-0.5',
          )}
        />
      </button>
      <span>
        <span className="block text-sm font-medium text-slate-700 dark:text-slate-200">{label}</span>
        {hint && <span className="block text-xs text-slate-500 dark:text-slate-400">{hint}</span>}
      </span>
    </label>
  )
}

export function Checkbox({ checked, onChange, label, className }) {
  return (
    <label className={clsx('inline-flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300', className)}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500 dark:border-slate-600 dark:bg-slate-800"
      />
      {label}
    </label>
  )
}

export function Modal({ open, onClose, title, children, footer, wide }) {
  useEffect(() => {
    const onKey = (event) => { if (event.key === 'Escape') onClose?.() }
    if (open) document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4 pt-16 backdrop-blur-sm">
      <div className={clsx('w-full animate-fade-in rounded-xl bg-white shadow-xl dark:bg-slate-900', wide ? 'max-w-4xl' : 'max-w-lg')}>
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3.5 dark:border-slate-800">
          <h3 className="text-base font-semibold text-slate-900 dark:text-white">{title}</h3>
          <button onClick={onClose} className="rounded p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-3 dark:border-slate-800">
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}

export function Spinner({ className }) {
  return <Loader2 className={clsx('h-5 w-5 animate-spin text-brand-600', className)} />
}

export function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center py-14 text-center">
      {Icon && (
        <span className="mb-3 rounded-full bg-slate-100 p-3 text-slate-400 dark:bg-slate-800">
          <Icon className="h-6 w-6" />
        </span>
      )}
      <h3 className="text-sm font-semibold text-slate-900 dark:text-white">{title}</h3>
      {description && <p className="mt-1 max-w-md text-sm text-slate-500 dark:text-slate-400">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ProgressBar({ value, max, tone = 'bg-brand-600', className, label }) {
  const pct = max ? Math.min(100, Math.round((value / max) * 100)) : 0
  return (
    <div className={className}>
      {label && (
        <div className="mb-1 flex justify-between text-xs text-slate-500 dark:text-slate-400">
          <span>{label}</span><span>{pct}%</span>
        </div>
      )}
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
        <div className={clsx('h-2 rounded-full transition-all', tone)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-slate-200 dark:border-slate-800">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          onClick={() => onChange(tab.key)}
          className={clsx(
            'whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition',
            value === tab.key
              ? 'border-brand-600 text-brand-700 dark:text-brand-400'
              : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400',
          )}
        >
          {tab.label}
          {tab.count !== undefined && (
            <span className="ml-1.5 rounded-full bg-slate-100 px-1.5 py-0.5 text-xs dark:bg-slate-800">
              {tab.count}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}

export function Pagination({ page, totalPages, onPage, total, pageSize }) {
  if (!totalPages || totalPages <= 1) return null
  const from = (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 px-4 py-3 dark:border-slate-800">
      <p className="text-xs text-slate-500 dark:text-slate-400">
        Showing {from.toLocaleString()}–{to.toLocaleString()} of {Number(total).toLocaleString()}
      </p>
      <div className="flex items-center gap-1">
        <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>Prev</Button>
        <span className="px-2 text-xs text-slate-500 dark:text-slate-400">Page {page} of {totalPages}</span>
        <Button size="sm" variant="secondary" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>Next</Button>
      </div>
    </div>
  )
}

export function SearchInput({ value, onChange, placeholder = 'Search…', className }) {
  return (
    <div className={clsx('relative', className)}>
      <input
        className="input pl-9"
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <svg className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <circle cx="11" cy="11" r="7" strokeWidth="2" />
        <path d="m20 20-3.5-3.5" strokeWidth="2" strokeLinecap="round" />
      </svg>
    </div>
  )
}

export function TableSkeleton({ rows = 8, cols = 6 }) {
  return (
    <div className="animate-pulse divide-y divide-slate-200 dark:divide-slate-800">
      {Array.from({ length: rows }).map((_, row) => (
        <div key={row} className="flex gap-4 px-4 py-3">
          {Array.from({ length: cols }).map((_, col) => (
            <div key={col} className="h-4 flex-1 rounded bg-slate-200 dark:bg-slate-800" />
          ))}
        </div>
      ))}
    </div>
  )
}

/* ------------------------------ toasts ------------------------------ */
let toastId = 0
const listeners = new Set()

export function toast(message, type = 'info', detail) {
  const item = { id: ++toastId, message, type, detail }
  listeners.forEach((listener) => listener((items) => [...items, item]))
  setTimeout(() => {
    listeners.forEach((listener) => listener((items) => items.filter((row) => row.id !== item.id)))
  }, 5000)
}

export function Toaster() {
  const [items, setItems] = useState([])
  useEffect(() => {
    listeners.add(setItems)
    return () => listeners.delete(setItems)
  }, [])
  const icons = {
    success: <CheckCircle2 className="h-5 w-5 text-emerald-500" />,
    error: <XCircle className="h-5 w-5 text-rose-500" />,
    warning: <AlertTriangle className="h-5 w-5 text-amber-500" />,
    info: <Info className="h-5 w-5 text-brand-500" />,
  }
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-80 flex-col gap-2">
      {items.map((item) => (
        <div key={item.id} className="pointer-events-auto flex gap-2 rounded-lg border border-slate-200 bg-white p-3 shadow-lg dark:border-slate-700 dark:bg-slate-800">
          {icons[item.type] || icons.info}
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-slate-900 dark:text-white">{item.message}</p>
            {item.detail && <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{item.detail}</p>}
          </div>
        </div>
      ))}
    </div>
  )
}

export function useDebounced(value, delay = 350) {
  const [debounced, setDebounced] = useState(value)
  const first = useRef(true)
  useEffect(() => {
    if (first.current) { first.current = false; return undefined }
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}
