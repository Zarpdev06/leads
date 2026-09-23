import { useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { BarChart3, TrendingUp } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { useApi } from '../hooks/useApi'
import { Card, Select, Spinner, StatCard } from '../components/ui'
import { number, percent } from '../lib/format'

const COLORS = ['#3454f5', '#0ea5e9', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#94a3b8']

export default function Analytics() {
  const [days, setDays] = useState(30)
  const { data, loading } = useApi('/api/analytics/', { params: { days } })

  if (loading) return <div className="grid place-items-center py-16"><Spinner /></div>
  const overview = data?.overview || {}
  const rates = data?.rates || {}

  return (
    <div className="space-y-4">
      <PageHeader
        title="Analytics"
        description="Outreach performance, industry and location breakdowns, funnel and data quality."
        actions={
          <Select value={days} onChange={(event) => setDays(Number(event.target.value))}
            options={[7, 30, 60, 90].map((value) => ({ value, label: `Last ${value} days` }))} />
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Emails sent" value={number(rates.sent || 0)} icon={BarChart3} />
        <StatCard label="Reply rate" value={percent(rates.reply_rate || 0)} tone="green" icon={TrendingUp} />
        <StatCard label="Open rate" value={percent(rates.open_rate || 0)} tone="brand" icon={TrendingUp} />
        <StatCard label="Bounce rate" value={percent(rates.bounce_rate || 0)} tone="rose" icon={TrendingUp} />
      </div>

      <Card>
        <h2 className="mb-4 text-sm font-semibold text-slate-900 dark:text-white">Outreach over time</h2>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data?.daily_outreach || []} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(value) => String(value).slice(5)} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="sent" stroke="#3454f5" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="opened" stroke="#0ea5e9" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="clicked" stroke="#8b5cf6" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="replied" stroke="#22c55e" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="bounced" stroke="#ef4444" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="mb-4 text-sm font-semibold text-slate-900 dark:text-white">Performance by industry</h2>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data?.industries || []} layout="vertical" margin={{ left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="industry" width={130} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="sent" fill="#3454f5" radius={[0, 4, 4, 0]} />
                <Bar dataKey="replied" fill="#22c55e" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <h2 className="mb-4 text-sm font-semibold text-slate-900 dark:text-white">Performance by location</h2>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data?.locations || []} layout="vertical" margin={{ left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="location" width={130} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="sent" fill="#0ea5e9" radius={[0, 4, 4, 0]} />
                <Bar dataKey="replied" fill="#22c55e" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <h2 className="mb-4 text-sm font-semibold text-slate-900 dark:text-white">Funnel</h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={data?.funnel || []} dataKey="count" nameKey="stage" innerRadius={45} outerRadius={80}>
                  {(data?.funnel || []).map((entry, index) => (
                    <Cell key={entry.stage} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <h2 className="mb-4 text-sm font-semibold text-slate-900 dark:text-white">Service interest</h2>
          <div className="space-y-2">
            {(data?.services || []).map((row) => (
              <div key={row.service} className="flex items-center justify-between gap-2 text-sm">
                <span className="truncate text-slate-700 dark:text-slate-300">{row.service}</span>
                <span className="shrink-0 text-slate-500">{row.sent} sent · {percent(row.reply_rate)} replies</span>
              </div>
            ))}
            {(data?.services || []).length === 0 && <p className="text-sm text-slate-500">No data yet.</p>}
          </div>
        </Card>

        <Card>
          <h2 className="mb-4 text-sm font-semibold text-slate-900 dark:text-white">AI vs template</h2>
          <div className="space-y-3 text-sm">
            {['ai', 'template'].map((key) => {
              const row = data?.ai_vs_template?.[key] || {}
              return (
                <div key={key} className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                  <p className="font-medium capitalize text-slate-800 dark:text-slate-100">{key}</p>
                  <p className="text-xs text-slate-500">
                    {number(row.sent || 0)} sent · {percent(row.open_rate || 0)} opened · {percent(row.reply_rate || 0)} replied
                  </p>
                </div>
              )
            })}
          </div>
        </Card>
      </div>

      <Card padded={false}>
        <div className="border-b border-slate-200 px-4 py-3 dark:border-slate-800">
          <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Data quality by source</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/50">
              <tr>
                <th className="table-th">Source</th>
                <th className="table-th">Category</th>
                <th className="table-th">Total</th>
                <th className="table-th">With email</th>
                <th className="table-th">Without email</th>
                <th className="table-th">Invalid</th>
                <th className="table-th">Duplicates</th>
                <th className="table-th">Missing company</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              {(data?.sources || []).map((row) => (
                <tr key={row.source_id}>
                  <td className="table-td font-medium text-slate-900 dark:text-white">{row.source}</td>
                  <td className="table-td">{row.category || '—'}</td>
                  <td className="table-td">{number(row.total)}</td>
                  <td className="table-td text-emerald-600">{number(row.with_email)}</td>
                  <td className="table-td text-amber-600">{number(row.without_email)}</td>
                  <td className="table-td text-rose-600">{number(row.invalid_email)}</td>
                  <td className="table-td">{number(row.duplicates)}</td>
                  <td className="table-td">{number(row.missing_company)}</td>
                </tr>
              ))}
              {(data?.sources || []).length === 0 && (
                <tr><td className="table-td" colSpan={8}>No imports yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
