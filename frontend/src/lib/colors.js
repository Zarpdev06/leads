/** Status colours shared by every table/badge in the app. */
export const qualityColor = {
  HOT: 'bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300',
  WARM: 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300',
  COLD: 'bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-300',
  UNQUALIFIED: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
}

export const emailStatusColor = {
  VALID: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300',
  INVALID: 'bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300',
  BOUNCED: 'bg-rose-200 text-rose-800 dark:bg-rose-900 dark:text-rose-200',
  RISKY: 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300',
  MISSING: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
  UNSUBSCRIBED: 'bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300',
  SUPPRESSED: 'bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300',
  UNVERIFIED: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
}

export const statusColor = {
  RUNNING: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300',
  DRAFT: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
  PAUSED: 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300',
  COMPLETED: 'bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-300',
  CANCELLED: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
  SENT: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300',
  QUEUED: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
  FAILED: 'bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300',
  BOUNCED: 'bg-rose-200 text-rose-800 dark:bg-rose-900 dark:text-rose-200',
  SKIPPED: 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300',
  PROCESSING: 'bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-300',
}

export const stageColor = {
  NEW: '#64748b', QUALIFIED: '#0ea5e9', CONTACTED: '#6366f1', REPLIED: '#22c55e',
  MEETING_REQUESTED: '#14b8a6', MEETING_SCHEDULED: '#06b6d4', PROPOSAL: '#f59e0b',
  NEGOTIATION: '#f97316', WON: '#16a34a', LOST: '#ef4444', DO_NOT_CONTACT: '#991b1b',
}
