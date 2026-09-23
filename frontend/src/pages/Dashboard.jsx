import {
  AlertTriangle, BarChart3, Building2, CheckCircle2, Mail, Reply, Send, TrendingUp, Trophy,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import PageHeader from '../components/PageHeader'
import { Badge, Button, Card, EmptyState, ProgressBar, StatCard, TableSkeleton } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { useSettings } from '../context/SettingsContext'
import { dateTime, number, percent } from '../lib/format'
import { stageColor } from '../lib/colors'

const PIE_COLORS = ['#3454f5', '#0ea5e9', '#22c55e', '#f59e0b', '#ef4444', '#94a3b8']

export default function Dashboard() {
  const { data, loading, error, refresh } = useApi('/api/dashboard/summary/')
  const { values } = useSettings()

  if (loading) return <div className="space-y-4"><TableSkeleton rows={4} cols={4} /><TableSkeleton rows={8} /></div>
  if (error) return <Card><p className="text-sm text-rose-600">{error}</p></Card>

  const overview = data?.overview || {}
  const capacity = data?.capacity || {}
  const funnel = data?.funnel || []
  const quality = data?.lead_quality || []
  const daily = data?.daily_outreach || []
  const activity = data?.recent_activity || []

  return (
    <div className="space-y-5">
      <PageHeader
        title="Dashboard"
        description="Pipeline health, sending capacity and today's outreach activity."
        actions={
          <Button variant="secondary" onClick={refresh}>Refresh</Button>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total leads" value={number(overview.total_leads)} icon={Building2}
          hint={`${number(overview.valid_emails)} with a valid email`} />
        <StatCard label="Qualified" value={number(overview.qualified_leads)} tone="green" icon={TrendingUp}
          hint={`${number(overview.hot_leads)} HOT leads`} />
        <StatCard label="Emails sent today" value={number(overview.emails_sent_today)} tone="brand" icon={Send}
          hint={`${number(overview.remaining_capacity)} remaining today`} />
        <StatCard label="Won" value={number(overview.won)} tone="amber" icon={Trophy}
          hint={`${percent(overview.conversion_rate)} conversion · ${number(overview.replies)} replies`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Outreach (last 14 days)</h2>
            <Link to="/analytics" className="link text-xs">Analytics →</Link>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={daily} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="sent" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3454f5" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#3454f5" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(value) => value.slice(5)} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Area type="monotone" dataKey="sent" name="Sent" stroke="#3454f5" fill="url(#sent)" />
                <Area type="monotone" dataKey="opened" name="Opened" stroke="#0ea5e9" fillOpacity={0} />
                <Area type="monotone" dataKey="replied" name="Replied" stroke="#22c55e" fillOpacity={0} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <h2 className="mb-4 text-sm font-semibold text-slate-900 dark:text-white">Daily sending capacity</h2>
          <p className="text-3xl font-semibold tracking-tight text-slate-900 dark:text-white">
            {capacity.sent ?? 0}
            <span className="text-base font-normal text-slate-400"> / {capacity.limit ?? 90}</span>
          </p>
          <ProgressBar
            className="mt-3"
            value={capacity.sent || 0}
            max={capacity.limit || 90}
            tone={(capacity.sent || 0) / (capacity.limit || 90) > 0.85 ? 'bg-amber-500' : 'bg-brand-600'}
          />
          <dl className="mt-4 space-y-2 text-sm">
            <Row label="Marketing limit" value={values?.['sending.daily_marketing_limit'] ?? 90} />
            <Row label="SMTP limit" value={values?.['sending.smtp_daily_limit'] ?? 100} />
            <Row label="Safety cap" value={capacity.hard_cap ?? 90} />
            <Row label="Suppressed addresses" value={number(overview.suppressed)} />
          </dl>
          <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
            The platform never exceeds the smallest of the three limits.
          </p>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <h2 className="mb-4 text-sm font-semibold text-slate-900 dark:text-white">Pipeline funnel</h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={funnel} layout="vertical" margin={{ left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="stage" tick={{ fontSize: 11 }} width={90} />
                <Tooltip />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {funnel.map((entry, index) => (
                    <Cell key={entry.stage} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <h2 className="mb-4 text-sm font-semibold text-slate-900 dark:text-white">Lead quality</h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={quality} dataKey="count" nameKey="quality" innerRadius={45} outerRadius={80} paddingAngle={2}>
                  {quality.map((entry, index) => (
                    <Cell key={entry.key} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <h2 className="mb-3 text-sm font-semibold text-slate-900 dark:text-white">Recent activity</h2>
          {activity.length === 0 ? (
            <EmptyState icon={Mail} title="No emails yet"
              description="Create a campaign to start outreach." />
          ) : (
            <ul className="divide-y divide-slate-200 text-sm dark:divide-slate-800">
              {activity.map((item) => (
                <li key={item.id} className="py-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate font-medium text-slate-800 dark:text-slate-100">{item.company || item.to}</p>
                    <Badge tone={item.status === 'SENT' ? 'green' : item.status === 'FAILED' ? 'rose' : 'slate'}>
                      {item.status}
                    </Badge>
                  </div>
                  <p className="truncate text-xs text-slate-500 dark:text-slate-400">{item.subject}</p>
                  <p className="text-[11px] text-slate-400">{dateTime(item.sent_at || item.created_at)}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Missing emails" value={number(overview.missing_emails)} tone="slate" icon={AlertTriangle}
          hint="Import them and enrich from their website" to="/leads/missing-email" />
        <StatCard label="Invalid emails" value={number(overview.invalid_emails)} tone="rose" icon={AlertTriangle}
          hint="Never emailed" />
        <StatCard label="Replies" value={number(overview.replies)} tone="green" icon={Reply}
          hint={`${percent(overview.reply_rate)} of today's sends`} />
        <StatCard label="Pipeline value" value={`$${number(Math.round(overview.pipeline_value || 0))}`}
          tone="brand" icon={BarChart3} hint={`${number(overview.proposals)} proposals open`} />
      </div>
    </div>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="font-medium text-slate-800 dark:text-slate-100">{value}</dd>
    </div>
  )
}
