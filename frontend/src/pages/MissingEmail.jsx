import { useState } from 'react'
import { Globe, Loader2, Search, Sparkles } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { api } from '../lib/api'
import { usePaginatedApi } from '../hooks/useApi'
import { useDebounced, Badge, Button, Card, EmptyState, Pagination, SearchInput, TableSkeleton, toast } from '../components/ui'
import { dateTime, number, titleCase } from '../lib/format'

const ENRICHMENT_TONE = {
  NOT_PROCESSED: 'slate', PROCESSING: 'brand', FOUND: 'green',
  NOT_FOUND: 'amber', FAILED: 'rose', SKIPPED: 'slate',
}

export default function MissingEmail() {
  const [search, setSearch] = useState('')
  const [hasWebsite, setHasWebsite] = useState('true')
  const debounced = useDebounced(search)
  const list = usePaginatedApi('/api/leads/missing-email/', {
    pageSize: 25,
    params: { search: debounced || undefined, has_website: hasWebsite || undefined },
  })
  const [busy, setBusy] = useState(null)

  const enrichOne = async (id) => {
    setBusy(id)
    try {
      const result = await api.post(`/api/leads/${id}/enrich/`, {})
      toast(result.status === 'FOUND' ? 'Email found on the business website' : 'No public email found',
        result.status === 'FOUND' ? 'success' : 'info',
        result.status === 'FOUND' ? result.found?.[0] : result.detail)
      list.refresh()
    } catch (error) {
      toast('Enrichment failed', 'error', error.message)
    } finally {
      setBusy(null)
    }
  }

  const enrichMany = async () => {
    const ids = list.selected.length ? list.selected : undefined
    const result = await api.post('/api/leads/bulk-enrich/', { ids, limit: 50 })
    toast(`${result.queued} leads queued for enrichment`, 'success')
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Missing email leads"
        description="Imported records without an email address. They are never emailed and never guessed - you can look for a publicly listed address on their website instead."
        actions={
          <Button variant="secondary" onClick={enrichMany} disabled={list.selected.length === 0}>
            <Sparkles className="h-4 w-4" /> Enrich selected ({list.selected.length})
          </Button>
        }
      />

      <Card padded={false}>
        <div className="flex flex-wrap items-center gap-2 p-3">
          <SearchInput className="min-w-[240px] flex-1" placeholder="Search company, contact, city…"
            value={search} onChange={setSearch} />
          <select className="input w-48" value={hasWebsite} onChange={(event) => setHasWebsite(event.target.value)}>
            <option value="">Any</option>
            <option value="true">Has website</option>
            <option value="false">No website</option>
          </select>
          <Button variant="secondary" onClick={list.refresh}>Refresh</Button>
        </div>

        {list.loading ? <TableSkeleton rows={8} cols={6} /> : list.rows.length === 0 ? (
          <EmptyState icon={Globe} title="No leads without an email"
            description="Every imported record has an email address." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-y border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/50">
                <tr>
                  <th className="table-th w-8"><input type="checkbox"
                    checked={list.allSelected} onChange={list.toggleAll}
                    className="h-4 w-4 rounded border-slate-300 text-brand-600" /></th>
                  <th className="table-th">Company</th>
                  <th className="table-th">Phone</th>
                  <th className="table-th">Website</th>
                  <th className="table-th">Location</th>
                  <th className="table-th">Industry</th>
                  <th className="table-th">Enrichment</th>
                  <th className="table-th" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {list.rows.map((lead) => (
                  <tr key={lead.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                    <td className="table-td"><input type="checkbox" checked={list.selected.includes(lead.id)}
                      onChange={() => list.toggle(lead.id)} className="h-4 w-4 rounded border-slate-300 text-brand-600" /></td>
                    <td className="table-td font-medium text-slate-900 dark:text-white">{lead.company_name}</td>
                    <td className="table-td">{lead.phone || '—'}</td>
                    <td className="table-td">
                      {lead.website ? (
                        <a href={`https://${lead.website}`} target="_blank" rel="noreferrer" className="link">{lead.website}</a>
                      ) : '—'}
                    </td>
                    <td className="table-td">{[lead.city, lead.state].filter(Boolean).join(', ') || '—'}</td>
                    <td className="table-td">{lead.industry || '—'}</td>
                    <td className="table-td">
                      <Badge tone={ENRICHMENT_TONE[lead.enrichment_status] || 'slate'}>
                        {titleCase(lead.enrichment_status)}
                      </Badge>
                    </td>
                    <td className="table-td text-right">
                      {lead.website && (
                        <Button size="sm" variant="secondary" disabled={busy === lead.id} onClick={() => enrichOne(lead.id)}>
                          {busy === lead.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
                          Find email
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pagination page={list.page} totalPages={list.totalPages} total={list.count}
          pageSize={25} onPage={list.setPage} />
      </Card>
    </div>
  )
}
