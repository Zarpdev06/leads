import { useState } from 'react'
import { Building2 } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { usePaginatedApi } from '../hooks/useApi'
import { useDebounced, Card, EmptyState, Pagination, SearchInput, TableSkeleton } from '../components/ui'
import { number } from '../lib/format'

export default function Companies() {
  const [search, setSearch] = useState('')
  const debounced = useDebounced(search)
  const list = usePaginatedApi('/api/companies/', {
    pageSize: 25,
    params: { search: debounced || undefined, ordering: 'name' },
  })

  return (
    <div className="space-y-4">
      <PageHeader title="Companies"
        description="De-duplicated businesses created from your imports." />
      <Card padded={false}>
        <div className="p-3"><SearchInput placeholder="Search company, domain, city…" value={search} onChange={setSearch} /></div>
        {list.loading ? <TableSkeleton rows={8} cols={6} /> : list.rows.length === 0 ? (
          <EmptyState icon={Building2} title="No companies yet" description="Import a dataset to create companies." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-y border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/50">
                <tr>
                  <th className="table-th">Company</th>
                  <th className="table-th">Website</th>
                  <th className="table-th">Phone</th>
                  <th className="table-th">Location</th>
                  <th className="table-th">Industry</th>
                  <th className="table-th">Leads</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {list.rows.map((company) => (
                  <tr key={company.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                    <td className="table-td font-medium text-slate-900 dark:text-white">{company.name}</td>
                    <td className="table-td">
                      {company.domain ? <a href={`https://${company.domain}`} target="_blank" rel="noreferrer" className="link">{company.domain}</a> : '—'}
                    </td>
                    <td className="table-td">{company.phone || '—'}</td>
                    <td className="table-td">{[company.city, company.state].filter(Boolean).join(', ') || '—'}</td>
                    <td className="table-td">{company.sub_industry_name || company.industry_name || '—'}</td>
                    <td className="table-td">{number(company.leads_count || 0)}</td>
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
