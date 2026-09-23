import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft, Building2, Copy, Globe, Mail, MapPin, Merge, Phone, RefreshCw, Sparkles,
  Ban, ShieldOff, Play,
} from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { api } from '../lib/api'
import { useApi } from '../hooks/useApi'
import {
  Badge, Button, Card, EmptyState, Modal, Spinner, Tabs, Textarea, toast,
} from '../components/ui'
import { emailStatusColor, qualityColor, stageColor } from '../lib/colors'
import { dateTime, number, titleCase } from '../lib/format'

const TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'timeline', label: 'Timeline' },
  { key: 'emails', label: 'Emails' },
  { key: 'duplicates', label: 'Duplicates' },
  { key: 'raw', label: 'Raw source data' },
]

export default function LeadDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [tab, setTab] = useState('overview')
  const [duplicates, setDuplicates] = useState([])
  const [merging, setMerging] = useState(null)
  const [ai, setAi] = useState(null)
  const { data: lead, loading, refresh } = useApi(`/api/leads/${id}/`)
  const { data: timeline } = useApi(`/api/crm/leads/${id}/timeline/`, { skip: tab !== 'timeline' })
  const { data: emails } = useApi('/api/email/messages/', { params: { lead: id, page_size: 50 }, skip: tab !== 'emails' })

  const loadDuplicates = async () => {
    const data = await api.get(`/api/leads/${id}/duplicates/`)
    setDuplicates(data || [])
  }

  const generateAI = async () => {
    const data = await api.post('/api/ai/generate/', { lead_id: Number(id) })
    setAi(data)
    toast('AI personalization generated', 'success')
  }

  const merge = async (otherId, keepBoth = false) => {
    await api.post(`/api/leads/${id}/merge/`, { other_id: otherId, keep_both: keepBoth })
    toast('Leads merged', 'success')
    setMerging(null)
    refresh()
  }

  const enrich = async () => {
    const result = await api.post(`/api/leads/${id}/enrich/`, {})
    toast(`Enrichment: ${result.status}`, result.status === 'FOUND' ? 'success' : 'info')
    refresh()
  }

  const block = async () => {
    await api.post(`/api/leads/${id}/block/`, { reason: 'Blocked from the lead screen' })
    toast('Outreach stopped', 'warning')
    refresh()
  }

  if (loading) return <div className="grid place-items-center py-16"><Spinner /></div>
  if (!lead) return <Card><EmptyState icon={Building2} title="Lead not found" /></Card>

  const enriched = lead.enrichment_status

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-xs text-slate-500 hover:underline">
        <ArrowLeft className="mr-1 inline h-3 w-3" /> Back
      </button>

      <PageHeader
        title={lead.company_name || 'Unnamed company'}
        description={[lead.sub_industry_name || lead.industry_name, lead.city, lead.state].filter(Boolean).join(' · ')}
        actions={
          <>
            {lead.email_normalized && <Button variant="secondary" onClick={() => navigate('/email')}><Mail className="h-4 w-4" /> Email history</Button>}
            {!lead.email_normalized && lead.website_domain && (
              <Button variant="secondary" onClick={enrich}><Globe className="h-4 w-4" /> Find email on website</Button>
            )}
            <Button onClick={generateAI}><Sparkles className="h-4 w-4" /> Generate AI copy</Button>
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card padded={false}>
            <Tabs tabs={TABS} value={tab} onChange={(key) => {
              setTab(key)
              if (key === 'duplicates') loadDuplicates()
            }} />

            <div className="p-5">
              {tab === 'overview' && <Overview lead={lead} />}

              {tab === 'timeline' && (
                <ul className="space-y-3">
                  {(timeline?.timeline || []).map((item, index) => (
                    <li key={index} className="flex gap-3">
                      <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand-500" />
                      <div>
                        <p className="text-sm font-medium text-slate-800 dark:text-slate-100">{item.title}</p>
                        {item.description && <p className="text-xs text-slate-500 dark:text-slate-400">{item.description}</p>}
                        <p className="text-[11px] text-slate-400">{dateTime(item.at)} · {item.actor}</p>
                      </div>
                    </li>
                  ))}
                  {(timeline?.timeline || []).length === 0 && <p className="text-sm text-slate-500">No activity yet.</p>}
                </ul>
              )}

              {tab === 'emails' && (
                <div className="space-y-2">
                  {(emails?.results || []).map((message) => (
                    <div key={message.id} className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                      <div className="flex items-center justify-between gap-2">
                        <p className="truncate text-sm font-medium text-slate-800 dark:text-slate-100">{message.subject}</p>
                        <Badge tone={message.status === 'SENT' ? 'green' : message.status === 'FAILED' ? 'rose' : 'slate'}>
                          {titleCase(message.status)}
                        </Badge>
                      </div>
                      <p className="text-xs text-slate-500">{dateTime(message.sent_at || message.scheduled_at || message.created_at)}
                        {message.opened_at && ' · opened'} {message.replied_at && ' · replied'}</p>
                    </div>
                  ))}
                  {(emails?.results || []).length === 0 && <p className="text-sm text-slate-500">No emails sent to this lead.</p>}
                </div>
              )}

              {tab === 'duplicates' && (
                <div className="space-y-2">
                  {duplicates.length === 0 && <p className="text-sm text-slate-500">No duplicate candidates found.</p>}
                  {duplicates.map((match) => (
                    <div key={match.candidate_id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                      <div>
                        <Link to={`/leads/${match.candidate_id}`} className="font-medium text-slate-800 hover:underline dark:text-slate-100">
                          {match.company}
                        </Link>
                        <p className="text-xs text-slate-500">{match.email || 'no email'} · {match.method} · {match.confidence}% match</p>
                      </div>
                      <div className="flex gap-2">
                        <Button size="sm" variant="secondary" onClick={() => setMerging(match)}>
                          <Merge className="h-3.5 w-3.5" /> Merge
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {tab === 'raw' && (
                <pre className="max-h-96 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-100">
                  {JSON.stringify(lead.raw_data, null, 2)}
                </pre>
              )}
            </div>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <h3 className="mb-3 text-sm font-semibold text-slate-900 dark:text-white">Score & eligibility</h3>
            <div className="flex items-center gap-2">
              <span className="text-3xl font-semibold text-slate-900 dark:text-white">{lead.lead_score}</span>
              <Badge className={qualityColor[lead.lead_quality]}>{lead.quality_display}</Badge>
            </div>
            <dl className="mt-4 space-y-2 text-sm">
              <Row label="Pipeline stage" value={<span style={{ color: stageColor[lead.crm_stage] }}>{titleCase(lead.crm_stage)}</span>} />
              <Row label="Email status" value={<Badge className={emailStatusColor[lead.email_status]}>{titleCase(lead.email_status)}</Badge>} />
              <Row label="Times contacted" value={lead.times_contacted} />
              <Row label="Last contacted" value={dateTime(lead.last_contacted_at)} />
              <Row label="Next follow-up" value={dateTime(lead.next_follow_up_at)} />
              {lead.enrichment_status && (
                <Row label="Enrichment" value={titleCase(lead.enrichment_status)} />
              )}
            </dl>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button size="sm" variant="secondary" onClick={block}><Ban className="h-3.5 w-3.5" /> Block outreach</Button>
              <Link to={`/leads/${id}`} className="hidden" />
            </div>
          </Card>

          <Card>
            <h3 className="mb-3 text-sm font-semibold text-slate-900 dark:text-white">Contact details</h3>
            <ul className="space-y-2 text-sm">
              <li className="flex items-center gap-2 text-slate-700 dark:text-slate-300">
                <Mail className="h-4 w-4 text-slate-400" />
                {lead.email_normalized || 'No email'}
                {lead.email_is_role && <Badge tone="amber">role mailbox</Badge>}
              </li>
              <li className="flex items-center gap-2 text-slate-700 dark:text-slate-300">
                <Phone className="h-4 w-4 text-slate-400" /> {lead.phone || '—'}
              </li>
              <li className="flex items-center gap-2 text-slate-700 dark:text-slate-300">
                <Globe className="h-4 w-4 text-slate-400" />
                {lead.website_domain ? (
                  <a href={`https://${lead.website_domain}`} target="_blank" rel="noreferrer" className="link">{lead.website_domain}</a>
                ) : '—'}
              </li>
              <li className="flex items-center gap-2 text-slate-700 dark:text-slate-300">
                <MapPin className="h-4 w-4 text-slate-400" />
                {[lead.street_address, lead.city, lead.state, lead.zip_code].filter(Boolean).join(', ') || '—'}
              </li>
              <li className="flex items-center gap-2 text-slate-700 dark:text-slate-300">
                <Building2 className="h-4 w-4 text-slate-400" /> {lead.contact_name || '—'} {lead.job_title ? `· ${lead.job_title}` : ''}
              </li>
            </ul>
          </Card>

          {ai && (
            <Card>
              <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-white">AI personalization</h3>
              <p className="text-xs text-slate-500">{ai.provider} · {ai.model}</p>
              <p className="mt-2 text-sm font-medium text-slate-800 dark:text-slate-100">{ai.subject}</p>
              <div className="email-body mt-2 text-sm text-slate-600 dark:text-slate-300"
                dangerouslySetInnerHTML={{ __html: ai.body_html }} />
            </Card>
          )}
        </div>
      </div>

      <Modal open={Boolean(merging)} onClose={() => setMerging(null)}
        title="Merge duplicate lead"
        footer={
          <>
            <Button variant="secondary" onClick={() => merging && merge(merging.candidate_id, true)}>Keep both</Button>
            <Button onClick={() => merging && merge(merging.candidate_id, false)}>Merge into this lead</Button>
          </>
        }>
        {merging && (
          <div className="space-y-2 text-sm">
            <p>Merge <strong>{merging.company}</strong> into <strong>{lead.company_name}</strong>?</p>
            <p className="text-slate-500 dark:text-slate-400">
              The richest values are kept, all emails, campaigns and CRM activity move to this lead,
              and the source history of both records is preserved.
            </p>
            <p className="text-xs text-slate-500">Match: {merging.method} ({merging.confidence}% confidence)</p>
          </div>
        )}
      </Modal>
    </div>
  )
}

function Overview({ lead }) {
  return (
    <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
      <Field label="Company" value={lead.company_name} />
      <Field label="Contact" value={lead.contact_name} />
      <Field label="Job title" value={lead.job_title} />
      <Field label="Industry" value={lead.sub_industry?.name || lead.industry?.name} />
      <Field label="Email" value={lead.email} />
      <Field label="Phone" value={lead.phone} />
      <Field label="Website" value={lead.website} />
      <Field label="Employees" value={lead.employee_count} />
      <Field label="Source" value={lead.source_name || lead.source?.name} />
      <Field label="Source category" value={lead.source_category} />
      <Field label="Recommended service" value={lead.recommended_service_name} />
      <Field label="Notes" value={lead.notes} />
    </dl>
  )
}

function Field({ label, value }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-800 dark:text-slate-100">{value || '—'}</dd>
    </div>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="text-slate-800 dark:text-slate-100">{value}</dd>
    </div>
  )
}
