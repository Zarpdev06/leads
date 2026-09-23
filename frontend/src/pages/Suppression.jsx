import { useState } from 'react'
import { Filter, Plus, ShieldOff } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { api } from '../lib/api'
import { usePaginatedApi } from '../hooks/useApi'
import {
  Badge, Button, Card, EmptyState, Input, Modal, Pagination, Select, TableSkeleton, Textarea, toast,
} from '../components/ui'
import { dateTime, titleCase } from '../lib/format'

const REASONS = ['UNSUBSCRIBED', 'BOUNCED', 'COMPLAINT', 'MANUAL_BLOCK', 'DO_NOT_CONTACT',
  'INVALID', 'IMPORT']

export default function Suppression() {
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({ email: '', reason: 'MANUAL_BLOCK', note: '' })
  const [bulk, setBulk] = useState('')
  const list = usePaginatedApi('/api/suppression/', { pageSize: 25 })

  const add = async () => {
    await api.post('/api/suppression/', form)
    toast('Address suppressed', 'success')
    setShowAdd(false)
    setForm({ email: '', reason: 'MANUAL_BLOCK', note: '' })
    list.refresh()
  }

  const addBulk = async () => {
    const emails = bulk.split(/[\n,;\s]+/).map((value) => value.trim()).filter(Boolean)
    const result = await api.post('/api/suppression/bulk_add/', { emails, reason: 'MANUAL_BLOCK' })
    toast(`${result.added} addresses suppressed`, 'success', `${result.skipped} invalid`)
    setBulk('')
    setShowAdd(false)
    list.refresh()
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Suppression list"
        description="Addresses that must never receive another marketing email. Checked before the daily quota is consumed."
        actions={<Button onClick={() => setShowAdd(true)}><Plus className="h-4 w-4" /> Add address</Button>}
      />

      <Card padded={false}>
        {list.loading ? <TableSkeleton rows={8} cols={6} /> : list.rows.length === 0 ? (
          <EmptyState icon={ShieldOff} title="The suppression list is empty"
            description="Addresses are added automatically when someone unsubscribes or an email bounces." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-y border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/50">
                <tr>
                  <th className="table-th">Email</th>
                  <th className="table-th">Reason</th>
                  <th className="table-th">Source</th>
                  <th className="table-th">Note</th>
                  <th className="table-th">Added</th>
                  <th className="table-th">Active</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {list.rows.map((row) => (
                  <tr key={row.id}>
                    <td className="table-td font-medium text-slate-900 dark:text-white">{row.email_normalized}</td>
                    <td className="table-td"><Badge tone="rose">{row.reason_display}</Badge></td>
                    <td className="table-td">{row.source}</td>
                    <td className="table-td max-w-[240px] truncate text-xs text-slate-500">{row.note || '—'}</td>
                    <td className="table-td text-xs text-slate-500">{dateTime(row.created_at)}</td>
                    <td className="table-td">{row.is_active ? 'Yes' : 'No'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pagination page={list.page} totalPages={list.totalPages} total={list.count}
              pageSize={25} onPage={list.setPage} />
          </div>
        )}
      </Card>

      <Modal open={showAdd} onClose={() => setShowAdd(false)} title="Add to suppression list"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowAdd(false)}>Cancel</Button>
            <Button onClick={add}>Add</Button>
          </>
        }>
        <div className="space-y-3">
          <Input label="Email address" type="email" value={form.email}
            onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))} />
          <Select label="Reason" value={form.reason}
            onChange={(event) => setForm((prev) => ({ ...prev, reason: event.target.value }))}
            options={REASONS.map((value) => ({ value, label: titleCase(value) }))} />
          <Textarea label="Note" value={form.note}
            onChange={(event) => setForm((prev) => ({ ...prev, note: event.target.value }))} />
          <div>
            <p className="label">Or paste many addresses</p>
            <Textarea rows={3} value={bulk} onChange={(event) => setBulk(event.target.value)}
              hint="One per line, or comma separated" />
            <Button size="sm" variant="secondary" className="mt-2" onClick={addBulk}>Add all</Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
