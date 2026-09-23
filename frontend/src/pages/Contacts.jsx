import { useState } from 'react'
import { Users } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { usePaginatedApi } from '../hooks/useApi'
import { useDebounced, Card, EmptyState, Pagination, SearchInput, TableSkeleton } from '../components/ui'

export default function Contacts() {
  const [search, setSearch] = useState('')
  const debounced = useDebounced(search)
  const list = usePaginatedApi('/api/contacts/', {
    pageSize: 25,
    params: { search: debounced || undefined },
  })

  return (
    <div className="space-y-4">
      <PageHeader title="Contacts"
        description="People attached to companies (separate from the lead record)." />
      <Card padded={false}>
        <div className="p-3"><SearchInput placeholder="Search name, email, phone…" value={search} onChange={setSearch} /></div>
        {list.loading ? <TableSkeleton rows={8} cols={6} /> : list.rows.length === 0 ? (
          <EmptyState icon={Users} title="No contacts yet" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-y border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/50">
                <tr>
                  <th className="table-th">Name</th>
                  <th className="table-th">Company</th>
                  <th className="table-th">Job title</th>
                  <th className="table-th">Email</th>
                  <th className="table-th">Phone</th>
                  <th className="table-th">Location</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {list.rows.map((contact) => (
                  <tr key={contact.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                    <td className="table-td font-medium text-slate-900 dark:text-white">{contact.full_name || '—'}</td>
                    <td className="table-td">{contact.company_name || '—'}</td>
                    <td className="table-td">{contact.job_title || '—'}</td>
                    <td className="table-td">{contact.email_normalized || '—'}</td>
                    <td className="table-td">{contact.phone || '—'}</td>
                    <td className="table-td">{[contact.city, contact.state].filter(Boolean).join(', ') || '—'}</td>
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
