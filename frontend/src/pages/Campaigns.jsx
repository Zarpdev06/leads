import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Mail, Pause, Play, Plus, X } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { api } from '../lib/api'
import { useApi } from '../hooks/useApi'
import { Badge, Button, Card, EmptyState, Modal, TableSkeleton, toast } from '../components/ui'
import { number, percent, relativeTime, titleCase } from '../lib/format'

const STATUS_TONE = {
  RUNNING: 'green', DRAFT: 'slate', PAUSED: 'amber', COMPLETED: 'brand', CANCELLED: 'slate',
}

export default function Campaigns() {
  const { data, loading, refresh } = useApi('/api/campaigns/', { params: { page_size: 100 } })
  const { data: dashboard } = useApi('/api/campaigns/dashboard/')
  const [confirm, setConfirm] = useState(null)

  const act = async (campaign, action) => {
    await api.post(`/api/campaigns/${campaign.id}/${action}/`, {})
    toast(`Campaign ${action}ed`, 'success')
    setConfirm(null)
    refresh()
  }

  const campaigns = data?.results || []

  return (
    <div className="space-y-4">
      <PageHeader
        title="Campaigns"
        description="An audience, a message and a schedule. Every send is checked against the eligibility rules and the daily quota."
        actions={<Link to="/campaigns/new" className="btn-primary"><Plus className="h-4 w-4" /> New campaign</Link>}
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <MiniStat label="Campaigns" value={dashboard?.total ?? '—'} />
        <MiniStat label="Running" value={dashboard?.running ?? '—'} tone="text-emerald-600" />
        <MiniStat label="Drafts" value={dashboard?.draft ?? '—'} />
        <MiniStat label="Completed" value={dashboard?.completed ?? '—'} />
        <MiniStat label="Daily limit" value={dashboard?.daily_limit ?? 90} tone="text-brand-600" />
      </div>

      <Card padded={false}>
        {loading ? <TableSkeleton rows={6} cols={7} /> : campaigns.length === 0 ? (
          <EmptyState icon={Mail} title="No campaigns yet"
            description="Create a campaign to start outreach to your imported leads."
            action={<Link to="/campaigns/new" className="btn-primary"><Plus className="h-4 w-4" /> New campaign</Link>} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-y border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/50">
                <tr>
                  <th className="table-th">Campaign</th>
                  <th className="table-th">Status</th>
                  <th className="table-th">Selected</th>
                  <th className="table-th">Sent</th>
                  <th className="table-th">Opened</th>
                  <th className="table-th">Replied</th>
                  <th className="table-th">Reply rate</th>
                  <th className="table-th" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {campaigns.map((campaign) => (
                  <tr key={campaign.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                    <td className="table-td">
                      <Link to={`/campaigns/${campaign.id}`} className="font-medium text-slate-900 hover:underline dark:text-white">
                        {campaign.name}
                      </Link>
                      <p className="text-xs text-slate-500">
                        {campaign.template_name || 'no template'} · created {relativeTime(campaign.created_at)}
                      </p>
                    </td>
                    <td className="table-td"><Badge tone={STATUS_TONE[campaign.status]}>{titleCase(campaign.status)}</Badge></td>
                    <td className="table-td">{number(campaign.total_selected)}</td>
                    <td className="table-td">{number(campaign.total_sent)}</td>
                    <td className="table-td">{number(campaign.total_opened)}</td>
                    <td className="table-td">{number(campaign.total_replied)}</td>
                    <td className="table-td">{percent(campaign.reply_rate || 0)}</td>
                    <td className="table-td text-right">
                      {campaign.status === 'RUNNING' ? (
                        <Button size="sm" variant="secondary" onClick={() => act(campaign, 'pause')}>
                          <Pause className="h-3.5 w-3.5" /> Pause
                        </Button>
                      ) : ['DRAFT', 'PAUSED', 'READY'].includes(campaign.status) ? (
                        <Button size="sm" variant="secondary" onClick={() => act(campaign, 'start')}>
                          <Play className="h-3.5 w-3.5" /> Start
                        </Button>
                      ) : null}
                      {['RUNNING', 'PAUSED'].includes(campaign.status) && (
                        <Button size="sm" variant="ghost" className="ml-1" onClick={() => setConfirm(campaign)}>
                          <X className="h-3.5 w-3.5" /> Stop
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal open={Boolean(confirm)} onClose={() => setConfirm(null)} title="Stop this campaign?"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirm(null)}>Keep running</Button>
            <Button variant="danger" onClick={() => confirm && act(confirm, 'cancel')}>Stop & cancel queued emails</Button>
          </>
        }>
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Queued and scheduled messages for <strong>{confirm?.name}</strong> will be cancelled.
          Emails already sent cannot be recalled.
        </p>
      </Modal>
    </div>
  )
}

function MiniStat({ label, value, tone = 'text-slate-900 dark:text-white' }) {
  return (
    <Card>
      <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
      <p className={`mt-1 text-xl font-semibold ${tone}`}>{value}</p>
    </Card>
  )
}
