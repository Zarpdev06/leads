import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Download, Filter, Mail, Plus, RefreshCw, Sparkles, Trash2, Upload } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { api } from '../lib/api'
import { useApi, usePaginatedApi } from '../hooks/useApi'
import { useDebounced, Badge, Button, Card, Checkbox, EmptyState, Input, Modal, Pagination,
  SearchInput, Select, TableSkeleton, toast } from '../components/ui'
import { emailStatusColor, qualityColor } from '../lib/colors'
import { dateTime, number, titleCase } from '../lib/format'

const STATUSES = ['NEW', 'VALID', 'INVALID', 'MISSING_EMAIL', 'CONTACTED', 'REPLIED',
  'UNSUBSCRIBED', 'SUPPRESSED', 'ARCHIVED']

export default function Leads() {
  const [search, setSearch] = useState('')
  const [state, setState] = useState('')
  const [hasEmail, setHasEmail] = useState('')
  const [quality, setQuality] = useState('')
  const [source, setSource] = useState('')
  const [campaignId, setCampaignId] = useState('')
  const [showFilters, setShowFilters] = useState(false)
  const [showAddToCampaign, setShowAddToCampaign] = useState(false)
  const debouncedSearch = useDebounced(search)

  const list = usePaginatedApi('/api/leads/', {
    pageSize: 25,
    params: {
      search: debouncedSearch || undefined,
      state: state || undefined,
      has_email: hasEmail || undefined,
      quality: quality || undefined,
      source: source || undefined,
      ordering: '-created_at',
    },
  })

  const { data: stats } = useApi('/api/leads/stats/', {
    params: {
      state: state || undefined,
      has_email: hasEmail || undefined,
      quality: quality || undefined,
    },
  })
  const { data: campaignsData } = useApi('/api/campaigns/', { params: { page_size: 100 } })
  const { data: sourcesData } = useApi('/api/sources/', { params: { page_size: 100 } })

  const campaigns = campaignsData?.results || []
  const sources = sourcesData?.results || []

  const exportCsv = async () => {
    const response = await fetch('/api/leads/export/?state=' + state, {
      headers: { Authorization: `Bearer ${localStorage.getItem('leads.access')}` },
    })
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'leads_export.csv'
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const bulkRescore = async () => {
    await api.post('/api/leads/bulk-rescore/', { ids: list.selected.length ? list.selected : undefined })
    toast('Rescoring complete', 'success')
    list.refresh()
  }

  const bulkArchive = async () => {
    await api.post('/api/leads/bulk-archive/', { ids: list.selected })
    toast(`${list.selected.length} leads archived`, 'success')
    list.setSelected([])
    list.refresh()
  }

  const addToCampaign = async (campaign) => {
    await api.post('/api/leads/bulk-add-campaign/', { ids: list.selected, campaign_id: campaign })
    toast(`Added ${list.selected.length} leads to campaign`, 'success')
    setShowAddToCampaign(false)
    list.setSelected([])
    list.refresh()
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Leads"
        description="Every imported record. Filtering, sorting and pagination happen on the server."
        actions={
          <>
            <Button variant="secondary" onClick={exportCsv}><Download className="h-4 w-4" /> Export CSV</Button>
            <Link to="/imports" className="btn-primary"><Upload className="h-4 w-4" /> Import data</Link>
          </>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <MiniStat label="Matching" value={stats?.total ?? '—'} />
        <MiniStat label="With email" value={stats?.with_email ?? '—'} tone="text-emerald-600" />
        <MiniStat label="Without email" value={stats?.without_email ?? '—'} tone="text-amber-600" />
        <MiniStat label="Invalid email" value={stats?.invalid_email ?? '—'} tone="text-rose-600" />
        <MiniStat label="Suppressed" value={stats?.suppressed ?? '—'} tone="text-purple-600" />
      </div>

      <Card padded={false}>
        <div className="flex flex-wrap items-center gap-2 p-3">
          <SearchInput className="min-w-[240px] flex-1" placeholder="Search company, contact, email, city…"
            value={search} onChange={setSearch} />
          <Button variant="secondary" onClick={() => setShowFilters((prev) => !prev)}>
            <Filter className="h-4 w-4" /> Filters
          </Button>
          <Button variant="secondary" onClick={list.refresh}><RefreshCw className="h-4 w-4" /></Button>
        </div>

        {showFilters && (
          <div className="grid gap-3 border-t border-slate-200 p-3 sm:grid-cols-2 lg:grid-cols-5 dark:border-slate-800">
            <Input label="State" placeholder="e.g. TX" value={state}
              onChange={(event) => setState(event.target.value.toUpperCase().slice(0, 30))} />
            <Select label="Email" value={hasEmail}
              onChange={(event) => setHasEmail(event.target.value)}
              options={[{ value: '', label: 'Any' }, { value: 'true', label: 'Has email' }, { value: 'false', label: 'No email' }]} />
            <Select label="Quality" value={quality}
              onChange={(event) => setQuality(event.target.value)}
              options={[{ value: '', label: 'Any' }, ...['HOT', 'WARM', 'COLD', 'UNQUALIFIED'].map((value) => ({ value, label: titleCase(value) }))]} />
            <Select label="Source" value={source}
              onChange={(event) => setSource(event.target.value)}
              options={[{ value: '', label: 'All sources' }, ...sources.map((row) => ({ value: row.id, label: row.name }))]} />
            <div className="flex items-end">
              <Button variant="ghost" onClick={() => { setState(''); setHasEmail(''); setQuality(''); setSource(''); setSearch('') }}>
                Clear filters
              </Button>
            </div>
          </div>
        )}

        {list.selected.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 border-t border-slate-200 bg-brand-50/60 px-3 py-2 text-sm dark:border-slate-800 dark:bg-brand-950/40">
            <span className="font-medium text-brand-800 dark:text-brand-200">{list.selected.length} selected</span>
            <Button size="sm" variant="secondary" onClick={() => setShowAddToCampaign(true)}>
              <Mail className="h-3.5 w-3.5" /> Add to campaign
            </Button>
            <Button size="sm" variant="secondary" onClick={bulkRescore}>
              <Sparkles className="h-3.5 w-3.5" /> Rescore
            </Button>
            <Button size="sm" variant="danger" onClick={bulkArchive}>
              <Trash2 className="h-3.5 w-3.5" /> Archive
            </Button>
            <button className="ml-auto text-xs text-slate-500 hover:underline" onClick={() => list.setSelected([])}>Clear</button>
          </div>
        )}

        {list.loading ? <TableSkeleton rows={10} cols={7} /> : list.rows.length === 0 ? (
          <EmptyState icon={Filter} title="No leads match these filters"
            description="Try clearing the filters or import a new dataset."
            action={<Link to="/imports" className="btn-primary"><Plus className="h-4 w-4" /> Import data</Link>} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-y border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/50">
                <tr>
                  <th className="table-th w-8">
                    <Checkbox checked={list.allSelected} onChange={list.toggleAll} label="" />
                  </th>
                  <th className="table-th">Company</th>
                  <th className="table-th">Contact</th>
                  <th className="table-th">Email</th>
                  <th className="table-th">Location</th>
                  <th className="table-th">Industry</th>
                  <th className="table-th">Score</th>
                  <th className="table-th">Status</th>
                  <th className="table-th">Imported</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {list.rows.map((lead) => (
                  <tr key={lead.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                    <td className="table-td"><Checkbox checked={list.selected.includes(lead.id)} onChange={() => list.toggle(lead.id)} label="" /></td>
                    <td className="table-td">
                      <Link to={`/leads/${lead.id}`} className="font-medium text-slate-900 hover:underline dark:text-white">
                        {lead.company_name || '—'}
                      </Link>
                      {lead.is_duplicate && <Badge className="ml-1.5" tone="amber">dup</Badge>}
                    </td>
                    <td className="table-td">{lead.contact_name || '—'}</td>
                    <td className="table-td">
                      <div className="flex items-center gap-1.5">
                        <span className="max-w-[200px] truncate">{lead.email_normalized || lead.email || '—'}</span>
                        <Badge className={emailStatusColor[lead.email_status]}>{titleCase(lead.email_status)}</Badge>
                      </div>
                    </td>
                    <td className="table-td">{[lead.city, lead.state].filter(Boolean).join(', ') || '—'}</td>
                    <td className="table-td">{lead.sub_industry_name || lead.industry_name || '—'}</td>
                    <td className="table-td">
                      <span className="font-medium">{lead.lead_score}</span>
                      <Badge className={`ml-1.5 ${qualityColor[lead.lead_quality]}`}>{lead.quality_display}</Badge>
                    </td>
                    <td className="table-td">{titleCase(lead.lead_status)}</td>
                    <td className="table-td text-xs text-slate-500">{dateTime(lead.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pagination page={list.page} totalPages={list.totalPages} total={list.count}
          pageSize={25} onPage={list.setPage} />
      </Card>

      <Modal open={showAddToCampaign} onClose={() => setShowAddToCampaign(false)}
        title="Add selected leads to a campaign">
        <p className="mb-3 text-sm text-slate-500 dark:text-slate-400">
          {list.selected.length} lead(s) will be added. Leads that fail the eligibility checks
          (invalid email, suppressed, contacted too recently) are skipped automatically at send time.
        </p>
        <div className="space-y-2">
          {campaigns.map((campaign) => (
            <button key={campaign.id} onClick={() => addToCampaign(campaign.id)}
              className="flex w-full items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-left text-sm hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">
              <span className="font-medium text-slate-800 dark:text-slate-100">{campaign.name}</span>
              <Badge tone="slate">{titleCase(campaign.status)}</Badge>
            </button>
          ))}
          {campaigns.length === 0 && (
            <EmptyState icon={Mail} title="No campaigns yet"
              description="Create a campaign first, then add leads to it."
              action={<Link to="/campaigns/new" className="btn-primary btn-sm">New campaign</Link>} />
          )}
        </div>
      </Modal>
    </div>
  )
}

function MiniStat({ label, value, tone = 'text-slate-900 dark:text-white' }) {
  return (
    <Card>
      <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
      <p className={`mt-1 text-xl font-semibold ${tone}`}>{typeof value === 'number' ? number(value) : value}</p>
    </Card>
  )
}
