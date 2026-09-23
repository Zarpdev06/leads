import { useState } from 'react'
import { BarChart3, Gauge, Mail, Plus, Save, Send, Server, TestTube } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { api } from '../lib/api'
import { useApi, usePolling } from '../hooks/useApi'
import {
  Badge, Button, Card, EmptyState, Input, Modal, Pagination, ProgressBar, Select, Spinner, Tabs,
  TableSkeleton, Textarea, Toggle, toast,
} from '../components/ui'
import { dateTime, number, percent, titleCase } from '../lib/format'
import { statusColor } from '../lib/colors'

const TABS = [
  { key: 'usage', label: 'Daily usage & quota' },
  { key: 'queue', label: 'Send queue' },
  { key: 'sent', label: 'Sent' },
  { key: 'failed', label: 'Failed' },
  { key: 'templates', label: 'Templates' },
]

export default function Email() {
  const [tab, setTab] = useState('usage')
  const [page, setPage] = useState(1)
  const [testTo, setTestTo] = useState('')
  const [showTest, setShowTest] = useState(false)

  const { data: usage, refresh: refreshUsage } = useApi('/api/email-usage/')
  const { data: templates, refresh: refreshTemplates } = useApi('/api/email/templates/', {
    params: { page_size: 100 },
    skip: tab !== 'templates',
  })
  const { data: variables } = useApi('/api/email/templates/variables/', { skip: tab !== 'templates' })
  const [editing, setEditing] = useState(null)
  const [preview, setPreview] = useState(null)
  const { data: messages, loading, refresh } = useApi('/api/email/messages/', {
    params: {
      page,
      page_size: 25,
      status: tab === 'sent' ? 'SENT' : tab === 'failed' ? 'FAILED' : undefined,
      ordering: '-created_at',
    },
    skip: tab === 'usage' || tab === 'templates',
  })

  usePolling(refreshUsage, 20000, tab === 'usage')

  const today = usage?.today || {}
  const saveTemplate = async () => {
    const payload = {
      name: editing.name,
      category: editing.category,
      subject: editing.subject,
      preheader: editing.preheader || '',
      body_html: editing.body_html,
      is_active: editing.is_active ?? true,
    }
    if (editing.id) await api.patch(`/api/email/templates/${editing.id}/`, payload)
    else await api.post('/api/email/templates/', payload)
    toast('Template saved', 'success')
    setEditing(null)
    refreshTemplates()
  }

  const renderPreview = async () => {
    const data = await api.post('/api/email/templates/render_preview/', {
      template_id: editing?.id,
    })
    setPreview(data)
  }

  const sendTest = async () => {
    const result = await api.post('/api/email/smtp-test/', { to_email: testTo })
    if (result.ok) toast('Test email sent', 'success', result.detail)
    else toast('Test failed', 'error', result.detail)
    setShowTest(false)
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Email"
        description="SMTP sending, the daily quota, and every message the platform has produced."
        actions={
          <>
            <Button variant="secondary" onClick={() => setShowTest(true)}>
              <TestTube className="h-4 w-4" /> Send SMTP test
            </Button>
            <Button variant="secondary" onClick={async () => {
              const result = await api.post('/api/email/messages/run_queue/', {})
              toast(`Queue run: ${result.sent} sent`, 'success')
              refresh(); refreshUsage()
            }}><Send className="h-4 w-4" /> Run queue now</Button>
          </>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <div className="flex items-center justify-between">
            <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Sent today</p>
            <Gauge className="h-4 w-4 text-slate-400" />
          </div>
          <p className="mt-1 text-2xl font-semibold text-slate-900 dark:text-white">
            {today.sent ?? 0}<span className="text-base font-normal text-slate-400"> / {today.limit ?? 90}</span>
          </p>
          <ProgressBar className="mt-2" value={today.sent || 0} max={today.limit || 90} />
        </Card>
        <Stat icon={Mail} label="Remaining today" value={today.remaining ?? 0} />
        <Stat icon={Server} label="SMTP limit" value={usage?.smtp_limit ?? 100}
          hint={`Safety cap: ${usage?.hard_cap ?? 90}`} />
        <Stat icon={BarChart3} label="Failed today" value={today.failed ?? 0}
          hint={`${today.bounced ?? 0} bounced`} />
      </div>

      <Card padded={false}>
        <Tabs tabs={TABS} value={tab} onChange={setTab} />

        {tab === 'usage' && (
          <div className="p-5">
            <h3 className="mb-3 text-sm font-semibold text-slate-900 dark:text-white">Capacity for the next 7 days</h3>
            <div className="grid gap-3 sm:grid-cols-4 lg:grid-cols-7">
              {(usage?.capacity_next_days || []).map((day) => (
                <div key={day.date} className="rounded-lg border border-slate-200 p-3 text-center dark:border-slate-800">
                  <p className="text-xs text-slate-500 dark:text-slate-400">{day.date.slice(5)}</p>
                  <p className="mt-1 text-lg font-semibold text-slate-900 dark:text-white">{day.remaining}</p>
                  <p className="text-[11px] text-slate-400">of {day.limit}</p>
                </div>
              ))}
            </div>

            <h3 className="mb-3 mt-6 text-sm font-semibold text-slate-900 dark:text-white">Recent days</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-y border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/50">
                  <tr>
                    <th className="table-th">Date</th>
                    <th className="table-th">Sent</th>
                    <th className="table-th">Failed</th>
                    <th className="table-th">Bounced</th>
                    <th className="table-th">Skipped</th>
                    <th className="table-th">Limit</th>
                    <th className="table-th">Utilisation</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                  {(usage?.history || []).map((row) => (
                    <tr key={row.date}>
                      <td className="table-td">{row.date}</td>
                      <td className="table-td">{row.sent_count}</td>
                      <td className="table-td">{row.failed_count}</td>
                      <td className="table-td">{row.bounced_count}</td>
                      <td className="table-td">{row.skipped_count}</td>
                      <td className="table-td">{row.limit}</td>
                      <td className="table-td">
                        <ProgressBar value={row.sent_count} max={row.limit} />
                      </td>
                    </tr>
                  ))}
                  {(usage?.history || []).length === 0 && (
                    <tr><td className="table-td" colSpan={7}>No usage recorded yet.</td></tr>
                  )}
                </tbody>
              </table>
            </div>

            <p className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              The counter is a single database row per day. Each worker reserves a slot with a
              conditional <code>UPDATE … WHERE sent_count &lt; limit</code>, so the number of emails
              sent in a day can never exceed the limit - no matter how many workers run in parallel.
            </p>
          </div>
        )}

        {tab !== 'usage' && (
          <>
            {loading ? <TableSkeleton rows={8} cols={6} /> : (messages?.results || []).length === 0 ? (
              <EmptyState icon={Mail} title="Nothing here" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="border-y border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/50">
                    <tr>
                      <th className="table-th">To</th>
                      <th className="table-th">Subject</th>
                      <th className="table-th">Campaign</th>
                      <th className="table-th">Step</th>
                      <th className="table-th">Status</th>
                      <th className="table-th">Scheduled / sent</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                    {(messages?.results || []).map((message) => (
                      <tr key={message.id}>
                        <td className="table-td">{message.to_email}</td>
                        <td className="table-td max-w-[280px] truncate">{message.subject}</td>
                        <td className="table-td">{message.campaign_name || '—'}</td>
                        <td className="table-td">{message.step_number}</td>
                        <td className="table-td">
                          <Badge className={statusColor[message.status]}>{titleCase(message.status)}</Badge>
                          {message.attempt_count > 1 && <span className="ml-1 text-xs text-slate-400">×{message.attempt_count}</span>}
                        </td>
                        <td className="table-td text-xs text-slate-500">
                          {dateTime(message.sent_at || message.scheduled_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <Pagination page={page} totalPages={messages?.total_pages || 1}
                  total={messages?.count || 0} pageSize={25} onPage={setPage} />
              </div>
            )}
          </>
        )}

        {tab === 'templates' && (
          <div className="p-5">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Templates use <code>{'{{variable}}'}</code> placeholders. Unknown values are
                replaced with a sensible fallback, and the unsubscribe link is always appended.
              </p>
              <Button onClick={() => setEditing({ name: '', category: 'COLD_OUTREACH',
                subject: '', body_html: '<p>Hi {{first_name}},\u003c/p><p>...\u003c/p>', is_active: true })}>
                <Plus className="h-4 w-4" /> New template
              </Button>
            </div>

            <div className="grid gap-3 lg:grid-cols-2">
              {(templates?.results || []).map((template) => (
                <div key={template.id} className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-medium text-slate-900 dark:text-white">{template.name}</p>
                      <p className="text-xs text-slate-500">{template.subject}</p>
                    </div>
                    <Badge tone={template.is_active ? 'green' : 'slate'}>
                      {template.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {(template.detected_variables || []).slice(0, 8).map((variable) => (
                      <code key={variable} className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] dark:bg-slate-800">
                        {`{{${variable}}}`}
                      </code>
                    ))}
                  </div>
                  <div className="mt-3 flex gap-2">
                    <Button size="sm" variant="secondary" onClick={() => setEditing(template)}>Edit</Button>
                    <Button size="sm" variant="ghost" onClick={async () => {
                      await api.post(`/api/email/templates/${template.id}/duplicate/`, {})
                      refreshTemplates()
                    }}>Duplicate</Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>

      <Modal open={Boolean(editing)} onClose={() => setEditing(null)} title={editing?.id ? 'Edit template' : 'New template'} wide
        footer={
          <>
            <Button variant="secondary" onClick={renderPreview}>Preview</Button>
            <Button onClick={saveTemplate}><Save className="h-4 w-4" /> Save</Button>
          </>
        }>
        {editing && (
          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <Input label="Name" value={editing.name || ''}
                onChange={(event) => setEditing((prev) => ({ ...prev, name: event.target.value }))} />
              <Select label="Category" value={editing.category || 'COLD_OUTREACH'}
                onChange={(event) => setEditing((prev) => ({ ...prev, category: event.target.value }))}
                options={['COLD_OUTREACH', 'FOLLOW_UP', 'MEETING', 'PROPOSAL', 'RE_ENGAGE', 'CUSTOM']
                  .map((value) => ({ value, label: titleCase(value) }))} />
            </div>
            <Input label="Subject" value={editing.subject || ''}
              onChange={(event) => setEditing((prev) => ({ ...prev, subject: event.target.value }))} />
            <Input label="Preheader" value={editing.preheader || ''}
              onChange={(event) => setEditing((prev) => ({ ...prev, preheader: event.target.value }))} />
            <Textarea label="Body (HTML)" rows={10} value={editing.body_html || ''}
              onChange={(event) => setEditing((prev) => ({ ...prev, body_html: event.target.value }))} />
            <Toggle label="Active" checked={editing.is_active ?? true}
              onChange={(value) => setEditing((prev) => ({ ...prev, is_active: value }))} />
            {variables && (
              <div>
                <p className="label">Available variables</p>
                <div className="flex flex-wrap gap-1">
                  {variables.map((variable) => (
                    <code key={variable.name} className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] dark:bg-slate-800"
                      title={variable.description}>
                      {`{{${variable.name}}}`}
                    </code>
                  ))}
                </div>
              </div>
            )}
            {preview && (
              <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                <p className="text-sm font-medium text-slate-900 dark:text-white">{preview.subject}</p>
                <div className="email-body mt-2 text-sm"
                  dangerouslySetInnerHTML={{ __html: preview.body_html }} />
              </div>
            )}
          </div>
        )}
      </Modal>

      <Modal open={showTest} onClose={() => setShowTest(false)} title="Send an SMTP test email"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowTest(false)}>Cancel</Button>
            <Button onClick={sendTest}>Send test</Button>
          </>
        }>
        <Input label="Recipient" type="email" required value={testTo}
          onChange={(event) => setTestTo(event.target.value)}
          hint="Transactional test - it does not consume the daily marketing quota." />
      </Modal>
    </div>
  )
}

function Stat({ icon: Icon, label, value, hint }) {
  return (
    <Card>
      <div className="flex items-center justify-between">
        <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
        <Icon className="h-4 w-4 text-slate-400" />
      </div>
      <p className="mt-1 text-2xl font-semibold text-slate-900 dark:text-white">{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
    </Card>
  )
}
