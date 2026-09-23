import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { CheckCircle2, Clock, FileSpreadsheet, Loader2, UploadCloud, XCircle } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { api } from '../lib/api'
import { useApi, usePolling } from '../hooks/useApi'
import { Badge, Button, Card, EmptyState, Modal, TableSkeleton, toast } from '../components/ui'
import { bytes, dateTime, number, percent, relativeTime, titleCase } from '../lib/format'

const STATUS_TONE = {
  COMPLETED: 'green', PROCESSING: 'brand', PENDING: 'slate', FAILED: 'rose',
  CANCELLED: 'slate', PARTIAL: 'amber',
}

export default function Imports() {
  const navigate = useNavigate()
  const fileInput = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [showSourceModal, setShowSourceModal] = useState(false)
  const [pendingFile, setPendingFile] = useState(null)
  const [source, setSource] = useState({ source_name: '', category: '', city: '', state: '' })

  const { data: overview } = useApi('/api/imports/overview/')
  const { data: files, loading, refresh } = useApi('/api/imports/', { params: { page_size: 20 } })
  const { data: jobs } = useApi('/api/imports/jobs/', { params: { page_size: 10 } })

  usePolling(() => {
    const running = (jobs?.results || []).some((job) => ['PENDING', 'PROCESSING'].includes(job.status))
    if (running) refresh()
  }, 4000)

  const upload = async (file, extra = {}) => {
    const formData = new FormData()
    formData.append('file', file)
    Object.entries(extra).forEach(([key, value]) => {
      if (value !== undefined && value !== null && key !== 'file') formData.append(key, value)
    })
    setUploading(true)
    try {
      const result = await api.upload('/api/imports/upload/', formData)
      toast('File uploaded - review the column mapping', 'success')
      navigate(`/imports/${result.id}`)
    } catch (error) {
      toast('Upload failed', 'error', error.message)
    } finally {
      setUploading(false)
      setPendingFile(null)
      setShowSourceModal(false)
    }
  }

  const onDrop = (event) => {
    event.preventDefault()
    setDragging(false)
    const file = event.dataTransfer.files?.[0]
    if (!file) return
    if (file.size > 5 * 1024 * 1024) {
      // Large files: ask for source details so the row count stays manageable.
      setPendingFile(file)
      setShowSourceModal(true)
      return
    }
    upload(file, { source_name: file.name })
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Data imports"
        description="Upload CSV or XLSX files from any source. Columns are auto-mapped, duplicates detected, and rows are streamed in chunks - files of any size are supported."
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MiniStat label="Files uploaded" value={overview?.files ?? '—'} />
        <MiniStat label="Imports running" value={overview?.jobs_running ?? '—'} />
        <MiniStat label="Sources" value={overview?.sources ?? '—'} />
        <MiniStat label="Rows imported" value={number(overview?.rows_imported ?? 0)} />
      </div>

      <Card
        padded={false}
        className="transition"
        onDragOver={(event) => { event.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <div className="flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center"
          style={{ borderColor: dragging ? '#3454f5' : undefined }}>
          {uploading ? (
            <>
              <Loader2 className="h-8 w-8 animate-spin text-brand-600" />
              <p className="text-sm font-medium text-slate-700 dark:text-slate-200">Analyzing file…</p>
            </>
          ) : (
            <>
              <UploadCloud className="h-9 w-9 text-slate-400" />
              <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                Drag & drop a CSV or XLSX file here
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Max {overview?.max_file_mb ?? 500} MB · streamed in chunks of {overview?.chunk_size ?? 1000} rows
              </p>
              <Button className="mt-2" onClick={() => fileInput.current?.click()}>Choose file</Button>
              <input
                ref={fileInput}
                type="file"
                accept=".csv,.tsv,.txt,.xlsx,.xlsm"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  if (!file) return
                  if (file.size > 5 * 1024 * 1024) { setPendingFile(file); setShowSourceModal(true) }
                  else upload(file, { source_name: file.name })
                  event.target.value = ''
                }}
              />
            </>
          )}
        </div>
      </Card>

      <Card padded={false}>
        <div className="border-b border-slate-200 px-4 py-3 dark:border-slate-800">
          <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Import history</h2>
        </div>
        {loading ? <TableSkeleton rows={6} cols={6} /> : (jobs?.results || []).length === 0 ? (
          <EmptyState icon={FileSpreadsheet} title="No imports yet"
            description="Upload your first dataset to get started." />
        ) : (
          <div className="divide-y divide-slate-200 dark:divide-slate-800">
            {(jobs?.results || []).map((job) => (
              <div key={job.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <Link to={`/imports/${job.import_file}`} className="truncate text-sm font-medium text-slate-900 hover:underline dark:text-white">
                    {job.file_name}
                  </Link>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    {job.source_name ? `${job.source_name} · ` : ''}
                    {number(job.created_rows)} created · {number(job.skipped_rows)} skipped · {number(job.duplicate_rows)} duplicates
                  </p>
                </div>
                <Badge tone={STATUS_TONE[job.status]}>{titleCase(job.status)}</Badge>
                <span className="text-xs text-slate-400">{relativeTime(job.created_at)}</span>
                {['PENDING', 'PROCESSING'].includes(job.status) && (
                  <Button size="sm" variant="secondary" onClick={async () => {
                    await api.post(`/api/imports/jobs/${job.id}/cancel/`, {})
                    refresh()
                  }}>Cancel</Button>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      <Modal open={showSourceModal} onClose={() => setShowSourceModal(false)}
        title="Describe this dataset"
        footer={
          <>
            <Button variant="secondary" onClick={() => { setShowSourceModal(false); setPendingFile(null) }}>Cancel</Button>
            <Button onClick={() => upload(pendingFile, source)}>Upload & analyze</Button>
          </>
        }>
        <p className="mb-3 text-sm text-slate-500 dark:text-slate-400">
          {pendingFile?.name} ({bytes(pendingFile?.size)}). These details are stored on the source and
          help the importer classify industries automatically.
        </p>
        <div className="space-y-3">
          <label className="block">
            <span className="label">Source name</span>
            <input className="input" value={source.source_name}
              onChange={(event) => setSource((prev) => ({ ...prev, source_name: event.target.value }))}
              placeholder="82 Million USA - Public Contacts File 01" />
          </label>
          <label className="block">
            <span className="label">Category</span>
            <input className="input" value={source.category}
              onChange={(event) => setSource((prev) => ({ ...prev, category: event.target.value }))}
              placeholder="Public Contacts / Scraped / Purchased" />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="label">City</span>
              <input className="input" value={source.city}
                onChange={(event) => setSource((prev) => ({ ...prev, city: event.target.value }))} />
            </label>
            <label className="block">
              <span className="label">State</span>
              <input className="input" value={source.state}
                onChange={(event) => setSource((prev) => ({ ...prev, state: event.target.value }))} />
            </label>
          </div>
        </div>
      </Modal>
    </div>
  )
}

function MiniStat({ label, value }) {
  return (
    <Card>
      <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-1 text-xl font-semibold text-slate-900 dark:text-white">{value}</p>
    </Card>
  )
}
