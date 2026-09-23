import { useState } from 'react'
import { Activity } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { usePaginatedApi } from '../hooks/useApi'
import { Card, EmptyState, Pagination, SearchInput, TableSkeleton } from '../components/ui'
import { dateTime, titleCase } from '../lib/format'

export default function AuditLogs() {
  const [search, setSearch] = useState('')
  const list = usePaginatedApi('/api/audit-logs/', { pageSize: 25, params: { search: search || undefined } })

  return (
    <div className="space-y-4">
      <PageHeader title="Audit log"
        description="Every configuration change, merge, suppression and import - who did what, and when." />

      <Card padded={false}>
        <div className="p-3">
          <SearchInput placeholder="Search action, entity or description…" value={search} onChange={setSearch} />
        </div>
        {list.loading ? <TableSkeleton rows={10} cols={5} /> : list.rows.length === 0 ? (
          <EmptyState icon={Activity} title="No audit entries" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-y border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/50">
                <tr>
                  <th className="table-th">When</th>
                  <th className="table-th">Action</th>
                  <th className="table-th">Actor</th>
                  <th className="table-th">Entity</th>
                  <th className="table-th">Description</th>
                  <th className="table-th">IP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {list.rows.map((row) => (
                  <tr key={row.id}>
                    <td className="table-td text-xs text-slate-500">{dateTime(row.created_at)}</td>
                    <td className="table-td font-medium text-slate-900 dark:text-white">{titleCase(row.action)}</td>
                    <td className="table-td">{row.actor_email || 'system'}</td>
                    <td className="table-td text-xs">{row.entity_type} #{row.entity_id ?? '—'}</td>
                    <td className="table-td max-w-[320px] truncate text-xs text-slate-500">{row.description}</td>
                    <td className="table-td text-xs text-slate-400">{row.ip_address || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pagination page={list.page} totalPages={list.totalPages} total={list.count}
              pageSize={25} onPage={list.setPage} />
          </div>
        )}
      </Card>
    </div>
  )
}
