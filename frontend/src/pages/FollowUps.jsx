import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Ban, CalendarClock, Repeat } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { api } from '../lib/api'
import { useApi } from '../hooks/useApi'
import { Badge, Button, Card, EmptyState, TableSkeleton, toast } from '../components/ui'
import { dateTime, number, titleCase } from '../lib/format'

export default function FollowUps() {
  const [days, setDays] = useState(7)
  const { data, loading, refresh } = useApi('/api/follow-ups/upcoming/', { params: { days } })
  const [sequenceState, setSequenceState] = useState({})

  const stop = async (campaignLeadId) => {
    await api.post(`/api/campaign-leads/${campaignLeadId}/stop/`, { reason: 'Stopped manually' })
    toast('Follow-ups stopped for this lead', 'success')
    refresh()
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Follow-ups"
        description="Automatic follow-ups stop on reply, unsubscribe, bounce, conversion, or when you stop them manually."
        actions={
          <select className="input w-40" value={days} onChange={(event) => setDays(Number(event.target.value))}>
            <option value={1}>Next 24 hours</option>
            <option value={7}>Next 7 days</option>
            <option value={30}>Next 30 days</option>
          </select>
        }
      />

      <Card padded={false}>
        {loading ? <TableSkeleton rows={6} cols={5} /> : (data || []).length === 0 ? (
          <EmptyState icon={Repeat} title="No follow-ups scheduled"
            description="Follow-ups appear here once a campaign has sent its first emails." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-y border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/50">
                <tr>
                  <th className="table-th">Company</th>
                  <th className="table-th">Email</th>
                  <th className="table-th">Campaign</th>
                  <th className="table-th">Step</th>
                  <th className="table-th">Next follow-up</th>
                  <th className="table-th" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {(data || []).map((row) => (
                  <tr key={row.id}>
                    <td className="table-td"><Link to={`/leads/${row.lead_id}`} className="link">{row.company}</Link></td>
                    <td className="table-td">{row.email}</td>
                    <td className="table-td">
                      <Link to={`/campaigns/${row.campaign_id}`} className="link">{row.campaign}</Link>
                    </td>
                    <td className="table-td"><Badge tone="brand">Step {row.step}</Badge></td>
                    <td className="table-td">{dateTime(row.next_follow_up_at)}</td>
                    <td className="table-td text-right">
                      <Button size="sm" variant="secondary" onClick={() => stop(row.id)}>
                        <Ban className="h-3.5 w-3.5" /> Stop
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card>
        <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-white">
          <CalendarClock className="mr-1.5 inline h-4 w-4" /> How follow-ups work
        </h3>
        <ul className="list-inside list-disc space-y-1 text-sm text-slate-600 dark:text-slate-300">
          <li>The default sequence sends on day 0, then +3, +7 and +14 days.</li>
          <li>Sequences are configurable per campaign in <code>Follow-up sequences</code>.</li>
          <li>Each step is skipped when the lead replied, unsubscribed, bounced, converted, or was blocked.</li>
          <li>The unique (campaign lead, step) constraint means a retried worker can never send a duplicate.</li>
        </ul>
      </Card>
    </div>
  )
}
