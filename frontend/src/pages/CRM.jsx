import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Briefcase, TrendingUp } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { api } from '../lib/api'
import { useApi } from '../hooks/useApi'
import { Badge, Button, Card, Modal, Select, Spinner, Textarea, toast } from '../components/ui'
import { currency, number, titleCase } from '../lib/format'
import { stageColor } from '../lib/colors'

const NEXT_STAGES = ['NEW', 'QUALIFIED', 'CONTACTED', 'REPLIED', 'MEETING_REQUESTED',
  'MEETING_SCHEDULED', 'PROPOSAL', 'NEGOTIATION', 'WON', 'LOST', 'DO_NOT_CONTACT']

export default function CRM() {
  const { data, loading, refresh } = useApi('/api/crm/pipeline/')
  const [moving, setMoving] = useState(null)
  const [stage, setStage] = useState('CONTACTED')
  const [note, setNote] = useState('')
  const [leads, setLeads] = useState([])

  const openStage = async (key) => {
    const response = await api.get(`/api/crm/pipeline/${key}/leads/`, { page_size: 50 })
    setLeads(response.results || [])
    setMoving({ key })
    setStage(key)
  }

  const move = async (leadId) => {
    await api.post(`/api/crm/leads/${leadId}/move/`, { stage, note })
    toast('Stage updated', 'success')
    setMoving(null)
    setNote('')
    refresh()
  }

  if (loading) return <div className="grid place-items-center py-16"><Spinner /></div>
  const stages = data?.stages || []
  const total = stages.reduce((sum, row) => sum + row.count, 0)
  const value = stages.reduce((sum, row) => sum + row.value, 0)

  return (
    <div className="space-y-4">
      <PageHeader
        title="CRM pipeline"
        description="Drag leads through the pipeline from anywhere - every change is written to the activity timeline."
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <Card>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Leads in pipeline</p>
          <p className="mt-1 text-2xl font-semibold text-slate-900 dark:text-white">{number(total)}</p>
        </Card>
        <Card>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Open pipeline value</p>
          <p className="mt-1 text-2xl font-semibold text-slate-900 dark:text-white">{currency(value)}</p>
        </Card>
        <Card>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Won</p>
          <p className="mt-1 text-2xl font-semibold text-emerald-600">
            {number(stages.find((row) => row.stage === 'WON')?.count || 0)}
          </p>
        </Card>
      </div>

      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
        {stages.map((stageRow) => (
          <button key={stageRow.stage} onClick={() => openStage(stageRow.stage)}
            className="card card-pad text-left transition hover:shadow-md">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full" style={{ background: stageRow.color }} />
              <p className="truncate text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
                {stageRow.label}
              </p>
            </div>
            <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{number(stageRow.count)}</p>
            {stageRow.value > 0 && <p className="text-xs text-slate-500">{currency(stageRow.value)}</p>}
          </button>
        ))}
      </div>

      <Modal open={Boolean(moving)} onClose={() => setMoving(null)} title={`${titleCase(moving?.key || '')} leads`} wide>
        {leads.length === 0 ? (
          <p className="text-sm text-slate-500">No leads in this stage.</p>
        ) : (
          <div className="space-y-2">
            {leads.map((lead) => (
              <div key={lead.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                <div className="min-w-0">
                  <Link to={`/leads/${lead.id}`} className="font-medium text-slate-900 hover:underline dark:text-white">
                    {lead.company_name}
                  </Link>
                  <p className="text-xs text-slate-500">{lead.email_normalized || 'no email'} · {lead.city || '—'}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={lead.lead_quality === 'HOT' ? 'rose' : lead.lead_quality === 'WARM' ? 'amber' : 'slate'}>
                    {lead.quality_display}
                  </Badge>
                  <Select value={stage} onChange={(event) => setStage(event.target.value)}
                    options={NEXT_STAGES.map((value) => ({ value, label: titleCase(value) }))} />
                  <Button size="sm" onClick={() => move(lead.id)}>
                    <Briefcase className="h-3.5 w-3.5" /> Move
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
        <div className="mt-4">
          <Textarea label="Note (optional)" value={note} onChange={(event) => setNote(event.target.value)}
            hint="Added to the activity timeline of the lead." />
        </div>
      </Modal>
    </div>
  )
}
