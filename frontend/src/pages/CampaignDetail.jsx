import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Eye, Mail, Pause, Play, RefreshCw, Send, Users, X } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { api } from '../lib/api'
import { useApi, usePolling } from '../hooks/useApi'
import {
  Badge, Button, Card, EmptyState, Pagination, ProgressBar, Spinner, Tabs, toast,
} from '../components/ui'
import { dateTime, number, percent, titleCase } from '../lib/format'
import { statusColor } from '../lib/colors'

const TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'leads', label: 'Leads' },
  { key: 'emails', label: 'Emails' },
  { key: 'preview', label: 'Email preview' },
]

export default function CampaignDetail() {
  const { id } = useParams()
  const [tab, setTab] = useState('overview')
  const [preview, setPreview] = useState(null)

  const { data: campaign, loading, refresh } = useApi(`/api/campaigns/${id}/`)
  const { data: stats } = useApi(`/api/campaigns/${id}/stats/`)
  const { data: leads } = useApi(`/api/campaigns/${id}/leads/`, { params: { page_size: 25 }, skip: tab !== 'leads' })
  const { data: emails } = useApi('/api/email/messages/', { params: { campaign: id, page_size: 50 }, skip: tab !== 'emails' })

  usePolling(refresh, 8000, campaign?.status === 'RUNNING')

  const loadPreview = async () => {
    const data = await api.get(`/api/campaigns/${id}/preview_email/`)
    setPreview(data)
  }

  const act = async (action) => {
    await api.post(`/api/campaigns/${id}/${action}/`, {})
    toast(`Campaign ${action}ed`, 'success')
    refresh()
  }

  if (loading) return <div className="grid place-items-center py-16"><Spinner /></div>
  if (!campaign) return <Card><p className="p-6 text-sm text-rose-600">Campaign not found.</p></Card>

  return (
    <div className="space-y-4">
      <Link to="/campaigns" className="text-xs text-slate-500 hover:underline">
        <ArrowLeft className="mr-1 inline h-3 w-3" /> Back to campaigns
      </Link>

      <PageHeader
        title={campaign.name}
        description={campaign.description}
        actions={
          <>
            {campaign.status === 'RUNNING' ? (
              <Button variant="secondary" onClick={() => act('pause')}><Pause className="h-4 w-4" /> Pause</Button>
            ) : ['DRAFT', 'PAUSED', 'READY'].includes(campaign.status) ? (
              <Button onClick={() => act('start')}><Play className="h-4 w-4" /> Start campaign</Button>
            ) : null}
            {['RUNNING', 'PAUSED'].includes(campaign.status) && (
              <Button variant="danger" onClick={() => act('cancel')}><X className="h-4 w-4" /> Stop</Button>
            )}
            <Button variant="secondary" onClick={() => act('dispatch')}><RefreshCw className="h-4 w-4" /> Dispatch queue</Button>
          </>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <Metric label="Selected" value={stats?.selected ?? campaign.total_selected} icon={Users} />
        <Metric label="Queued" value={stats?.queued ?? campaign.total_queued} icon={Mail} />
        <Metric label="Sent" value={stats?.sent ?? campaign.total_sent} icon={Send} tone="text-emerald-600" />
        <Metric label="Opened" value={stats?.opened ?? campaign.total_opened} icon={Eye} />
        <Metric label="Replied" value={stats?.replied ?? campaign.total_replied} icon={Mail} tone="text-emerald-600" />
        <Metric label="Bounced" value={stats?.bounced ?? campaign.total_bounced} icon={X} tone="text-rose-600" />
      </div>

      <Card padded={false}>
        <Tabs tabs={TABS} value={tab} onChange={(key) => { setTab(key); if (key === 'preview') loadPreview() }} />

        {tab === 'overview' && (
          <div className="grid gap-6 p-5 lg:grid-cols-2">
            <div>
              <h3 className="mb-3 text-sm font-semibold text-slate-900 dark:text-white">Performance</h3>
              <dl className="space-y-2 text-sm">
                <Row label="Status" value={<Badge className={statusColor[campaign.status]}>{titleCase(campaign.status)}</Badge>} />
                <Row label="Reply rate" value={percent(stats?.reply_rate || campaign.reply_rate || 0)} />
                <Row label="Open rate" value={percent(stats?.open_rate || campaign.open_rate || 0)} />
                <Row label="Failed" value={number(stats?.failed || 0)} />
                <Row label="Unsubscribed" value={number(stats?.unsubscribed || 0)} />
                <Row label="Daily limit" value={campaign.daily_limit} />
                <Row label="Send window" value={`${campaign.send_window_start} – ${campaign.send_window_end}`} />
                <Row label="Template" value={campaign.template_name || '—'} />
                <Row label="Recommended service" value={campaign.service_name || 'matched per lead'} />
                <Row label="AI personalization" value={campaign.use_ai_personalization ? 'Enabled' : 'Disabled'} />
                <Row label="Follow-ups" value={campaign.sequence_name || '—'} />
                <Row label="Last dispatched" value={dateTime(campaign.last_dispatched_at)} />
              </dl>
            </div>
            <div>
              <h3 className="mb-3 text-sm font-semibold text-slate-900 dark:text-white">Audience</h3>
              <dl className="space-y-2 text-sm">
                <Row label="Industries" value={campaign.target_industry_names?.join(', ') || 'All'} />
                <Row label="States" value={campaign.target_states?.join(', ') || 'All'} />
                <Row label="Cities" value={campaign.target_cities?.join(', ') || 'All'} />
                <Row label="Sources" value={campaign.source_names?.join(', ') || 'All'} />
                <Row label="Minimum score" value={campaign.min_lead_score} />
                <Row label="Require website" value={campaign.require_website ? 'Yes' : 'No'} />
                <Row label="Require phone" value={campaign.require_phone ? 'Yes' : 'No'} />
                <Row label="Require contact person" value={campaign.require_contact_person ? 'Yes' : 'No'} />
                <Row label="Exclude replies" value={campaign.exclude_replied ? 'Yes' : 'No'} />
              </dl>
              {stats?.by_step?.length > 0 && (
                <>
                  <h3 className="mb-2 mt-4 text-sm font-semibold text-slate-900 dark:text-white">By step</h3>
                  {stats.by_step.map((row) => (
                    <ProgressBar key={row.step_number} className="mb-2"
                      value={row.count} max={stats.selected || 1}
                      label={`Step ${row.step_number}: ${row.count}`} />
                  ))}
                </>
              )}
            </div>
          </div>
        )}

        {tab === 'leads' && (
          <div className="p-5">
            {(leads?.results || []).length === 0 ? (
              <EmptyState icon={Users} title="No leads in this campaign yet" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="border-y border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/50">
                    <tr>
                      <th className="table-th">Company</th>
                      <th className="table-th">Email</th>
                      <th className="table-th">Location</th>
                      <th className="table-th">Score</th>
                      <th className="table-th">Status</th>
                      <th className="table-th">Scheduled</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                    {(leads?.results || []).map((row) => (
                      <tr key={row.id}>
                        <td className="table-td"><Link to={`/leads/${row.lead}`} className="link">{row.company_name}</Link></td>
                        <td className="table-td">{row.email}</td>
                        <td className="table-td">{[row.city, row.state].filter(Boolean).join(', ')}</td>
                        <td className="table-td">{row.score}</td>
                        <td className="table-td"><Badge className={statusColor[row.status]}>{titleCase(row.status)}</Badge></td>
                        <td className="table-td text-xs text-slate-500">{dateTime(row.scheduled_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {tab === 'emails' && (
          <div className="space-y-2 p-5">
            {(emails?.results || []).length === 0 && <EmptyState icon={Mail} title="No messages yet" />}
            {(emails?.results || []).map((message) => (
              <div key={message.id} className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                    {message.to_email} · {message.subject}
                  </p>
                  <Badge className={statusColor[message.status]}>{titleCase(message.status)}</Badge>
                </div>
                <p className="text-xs text-slate-500">
                  Step {message.step_number} · scheduled {dateTime(message.scheduled_at)}
                  {message.sent_at && ` · sent ${dateTime(message.sent_at)}`}
                  {message.opened_at && ' · opened'}
                  {message.replied_at && ' · replied'}
                  {message.is_ai_generated && ' · AI personalised'}
                </p>
                {message.status === 'FAILED' && (
                  <p className="mt-1 text-xs text-rose-600">Retry {message.attempt_count} · {message.last_error?.slice(0, 120)}</p>
                )}
              </div>
            ))}
          </div>
        )}

        {tab === 'preview' && (
          <div className="p-5">
            {!preview ? <Spinner /> : (
              <div className="space-y-3">
                <div className="rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-800">
                  <Row label="To" value={preview.to} />
                  <Row label="From" value={preview.from} />
                  <Row label="Subject" value={preview.subject} />
                  <Row label="Recommended service" value={preview.recommended_service} />
                  <Row label="AI" value={preview.is_ai_generated ? `Yes (${preview.ai_provider})` : 'No'} />
                </div>
                <div className="email-body rounded-lg border border-slate-200 p-4 text-sm dark:border-slate-800"
                  dangerouslySetInnerHTML={{ __html: preview.body_html }} />
                <p className="text-xs text-slate-500">
                  This is the real email for lead #{preview.lead_id}, including tracking and the
                  unsubscribe link.
                </p>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  )
}

function Metric({ label, value, icon: Icon, tone = 'text-slate-900 dark:text-white' }) {
  return (
    <Card>
      <div className="flex items-center justify-between">
        <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
        {Icon && <Icon className="h-3.5 w-3.5 text-slate-400" />}
      </div>
      <p className={`mt-1 text-xl font-semibold ${tone}`}>{number(value)}</p>
    </Card>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-4 py-0.5 text-sm">
      <span className="text-slate-500 dark:text-slate-400">{label}</span>
      <span className="text-right font-medium text-slate-800 dark:text-slate-100">{value}</span>
    </div>
  )
}
