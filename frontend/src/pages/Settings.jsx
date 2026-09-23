import { useState } from 'react'
import { Database, Save, Server, ShieldCheck } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { api } from '../lib/api'
import { useApi } from '../hooks/useApi'
import { useSettings } from '../context/SettingsContext'
import {
  Badge, Button, Card, Input, Select, Spinner, Toggle, toast,
} from '../components/ui'
import { titleCase } from '../lib/format'

const GROUPS = [
  { key: 'sending', label: 'Sending limits & schedule' },
  { key: 'email', label: 'Email & SMTP' },
  { key: 'ai', label: 'AI' },
  { key: 'scoring', label: 'Lead scoring' },
  { key: 'dedupe', label: 'Deduplication' },
  { key: 'imports', label: 'Imports' },
  { key: 'compliance', label: 'Compliance & branding' },
]

export default function Settings() {
  const { data, loading, refresh } = useApi('/api/settings/')
  const { refresh: refreshGlobal } = useSettings()
  const [values, setValues] = useState({})
  const [saving, setSaving] = useState(false)
  const [testTo, setTestTo] = useState('')

  const schema = data?.schema || []
  const stored = data?.values || {}

  const valueFor = (key, fallback) =>
    values[key] !== undefined ? values[key] : (stored[key] !== undefined ? stored[key] : fallback)

  const set = (key, value) => setValues((prev) => ({ ...prev, [key]: value }))

  const save = async () => {
    setSaving(true)
    try {
      const result = await api.patch('/api/settings/update/', values)
      Object.entries(result.notes || {}).forEach(([key, note]) => toast(`${key}: ${note}`, 'warning'))
      toast('Settings saved', 'success')
      setValues({})
      refresh()
      refreshGlobal()
    } catch (error) {
      toast('Could not save settings', 'error', error.message)
    } finally {
      setSaving(false)
    }
  }

  const sendTest = async () => {
    const result = await api.post('/api/email/smtp-test/', { to_email: testTo })
    toast(result.ok ? 'Test email sent' : 'Test failed', result.ok ? 'success' : 'error', result.detail)
  }

  const seed = async () => {
    const result = await api.post('/api/settings/seed/', {})
    toast('Reference data seeded', 'success',
      `${result.industries} industries · ${result.services} services · ${result.templates} templates`)
  }

  if (loading) return <div className="grid place-items-center py-16"><Spinner /></div>

  const smtp = data?.smtp || {}

  return (
    <div className="space-y-4">
      <PageHeader
        title="Settings"
        description="Limits, schedule, AI, scoring and compliance. SMTP credentials come from environment variables and are never stored here."
        actions={
          <>
            <Button variant="secondary" onClick={seed}><Database className="h-4 w-4" /> Seed reference data</Button>
            <Button onClick={save} loading={saving}><Save className="h-4 w-4" /> Save changes</Button>
          </>
        }
      />

      <Card>
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
          <Server className="h-4 w-4" /> SMTP status
        </h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Info label="Host" value={smtp.host || '—'} />
          <Info label="Port" value={smtp.port || '—'} />
          <Info label="Username" value={smtp.username || '—'} />
          <Info label="Password" value={smtp.password_set ? <Badge tone="green">set (encrypted env)</Badge> : <Badge tone="rose">missing</Badge>} />
          <Info label="TLS" value={smtp.use_tls ? 'Yes' : 'No'} />
          <Info label="From" value={smtp.from_email || '—'} />
          <Info label="Reply-to" value={smtp.reply_to || '—'} />
          <Info label="Backend" value={<span className="text-xs">{smtp.backend}</span>} />
        </div>
        <div className="mt-4 flex flex-wrap items-end gap-2">
          <Input className="w-64" label="Test recipient" value={testTo}
            onChange={(event) => setTestTo(event.target.value)} />
          <Button variant="secondary" onClick={sendTest} disabled={!testTo}>Send test email</Button>
        </div>
        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
          Credentials are read from <code>EMAIL_HOST</code>, <code>EMAIL_PORT</code>,
          {' '}<code>EMAIL_HOST_USER</code>, <code>EMAIL_HOST_PASSWORD</code>, <code>EMAIL_USE_TLS</code>
          {' '}and <code>DEFAULT_FROM_EMAIL</code>. They are never exposed through the API.
        </p>
      </Card>

      {GROUPS.map((group) => {
        const rows = schema.filter((row) => row.category === group.key)
        if (rows.length === 0) return null
        return (
          <Card key={group.key}>
            <h3 className="mb-3 text-sm font-semibold text-slate-900 dark:text-white">
              {group.label}
            </h3>
            <div className="grid gap-4 sm:grid-cols-2">
              {rows.map((row) => (
                <Field key={row.key} row={row}
                  value={valueFor(row.key, row.default)}
                  onChange={(value) => set(row.key, value)} />
              ))}
            </div>
          </Card>
        )
      })}

      <Card>
        <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
          <ShieldCheck className="h-4 w-4 text-emerald-500" /> Safety guarantees
        </h3>
        <ul className="list-inside list-disc space-y-1 text-sm text-slate-600 dark:text-slate-300">
          <li>Marketing limit ≤ SMTP limit ≤ absolute safety cap. The effective limit is the smallest of the three.</li>
          <li>Suppressed, unsubscribed and bounced addresses are blocked before any quota is consumed.</li>
          <li>GDPR/CAN-SPAM: every marketing email contains a working one-click unsubscribe link and your postal address.</li>
          <li>Leads are never emailed automatically based on score alone - a human starts every campaign.</li>
        </ul>
      </Card>
    </div>
  )
}

function Field({ row, value, onChange }) {
  if (row.is_secret) {
    return (
      <Input
        label={row.label || row.key}
        type="password"
        hint={row.description}
        value=""
        placeholder="•••••••• (stored encrypted)"
        onChange={(event) => onChange(event.target.value)}
      />
    )
  }
  if (typeof value === 'boolean') {
    return <Toggle label={row.label || row.key} hint={row.description} checked={Boolean(value)} onChange={onChange} />
  }
  if (row.key === 'sending.weekdays' || Array.isArray(value)) {
    return (
      <div>
        <p className="label">{row.label || row.key}</p>
        <div className="flex flex-wrap gap-2">
          {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((day, index) => {
            const selected = (value || []).includes(index + 1)
            return (
              <button key={day} type="button"
                onClick={() => onChange(selected
                  ? (value || []).filter((item) => item !== index + 1)
                  : [...(value || []), index + 1])}
                className={`rounded-lg border px-2.5 py-1 text-xs font-medium ${
                  selected
                    ? 'border-brand-600 bg-brand-50 text-brand-700 dark:bg-brand-950 dark:text-brand-300'
                    : 'border-slate-300 text-slate-600 dark:border-slate-700 dark:text-slate-300'}`}>
                {day}
              </button>
            )
          })}
        </div>
        {row.description && <p className="mt-1 text-xs text-slate-500">{row.description}</p>}
      </div>
    )
  }
  if (row.key === 'scoring.rules' || row.key === 'scoring.thresholds' || typeof value === 'object') {
    return (
      <div>
        <p className="label">{row.label || row.key}</p>
        <textarea
          className="input font-mono text-xs"
          rows={4}
          value={typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
          onChange={(event) => {
            try { onChange(JSON.parse(event.target.value)) }
            catch { onChange(event.target.value) }
          }}
        />
        <p className="mt-1 text-xs text-slate-500">{row.description || 'JSON'}</p>
      </div>
    )
  }
  return (
    <Input
      label={row.label || row.key}
      hint={row.description}
      value={value ?? ''}
      type={typeof value === 'number' ? 'number' : 'text'}
      onChange={(event) => onChange(
        typeof value === 'number' ? Number(event.target.value) : event.target.value)}
    />
  )
}

function Info({ label, value }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
      <p className="text-sm font-medium text-slate-800 dark:text-slate-100">{value}</p>
    </div>
  )
}
