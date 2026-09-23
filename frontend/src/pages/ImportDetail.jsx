import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle, ArrowLeft, CheckCircle2, Database, Loader2, Play, RefreshCw, Save, XCircle,
} from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { api } from '../lib/api'
import { useApi, usePolling } from '../hooks/useApi'
import {
  Badge, Button, Card, Checkbox, ProgressBar, Select, Spinner, Tabs, toast,
} from '../components/ui'
import { bytes, dateTime, number, percent } from '../lib/format'

const TABS = [
  { key: 'mapping', label: '1 · Column mapping' },
  { key: 'preview', label: '2 · Preview & stats' },
  { key: 'process', label: '3 · Import' },
]

export default function ImportDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [tab, setTab] = useState('mapping')
  const [mapping, setMapping] = useState({})
  const [fields, setFields] = useState([])
  const [options, setOptions] = useState({
    import_valid_only: false,
    skip_invalid_emails: false,
    import_rows_without_email: true,
    update_existing: false,
    run_dedupe: true,
    rescore: true,
    chunk_size: 1000,
  })
  const { data: importFile, loading, refresh } = useApi(`/api/imports/${id}/`)
  const { data: preview } = useApi(`/api/imports/${id}/preview/`, { skip: tab !== 'preview' })
  const { data: jobs, refresh: refreshJobs } = useApi('/api/imports/jobs/', {
    params: { import_file: id, page_size: 5 },
  })

  const job = jobs?.results?.[0]
  const running = job && ['PENDING', 'PROCESSING'].includes(job.status)

  usePolling(() => {
    if (running) { refreshJobs(); refresh() }
  }, 3000, Boolean(running))

  useEffect(() => {
    if (importFile) {
      setMapping(importFile.column_mapping || importFile.detected_mapping || {})
      setFields(importFile.mapping_suggestions?.length
        ? [] : [])
    }
  }, [importFile?.id])

  if (loading) return <div className="grid place-items-center py-16"><Spinner /></div>
  if (!importFile) return <Card><p className="p-6 text-sm text-rose-600">Import file not found.</p></Card>

  const suggestions = importFile.mapping_suggestions || []
  const headers = importFile.headers || []
  const fieldOptions = (importFile.mapping_suggestions || []).length
    ? [] : []

  const saveMapping = async () => {
    await api.patch(`/api/imports/${id}/`, { column_mapping: mapping })
    toast('Mapping saved', 'success')
    setTab('preview')
  }

  const startImport = async () => {
    const result = await api.post(`/api/imports/${id}/process/`, options)
    toast('Import started', 'success')
    setTab('process')
    setTimeout(() => refreshJobs(), 1500)
    return result
  }

  const targetFields = Array.from(new Set([
    'company_name', 'contact_name', 'first_name', 'last_name', 'job_title', 'email', 'phone',
    'mobile', 'phone_type', 'website', 'street_address', 'city', 'state', 'zip_code', 'country',
    'employee_count', 'industry', 'sub_industry', 'linkedin_url', 'revenue', 'notes', 'tags',
    'source_category', 'source_city',
  ]))

  return (
    <div className="space-y-4">
      <button onClick={() => navigate('/imports')} className="text-xs text-slate-500 hover:underline">
        <ArrowLeft className="mr-1 inline h-3 w-3" /> Back to imports
      </button>

      <PageHeader
        title={importFile.original_name}
        description={`${importFile.file_type} · ${bytes(importFile.size_bytes)} · ${number(importFile.total_rows)} rows detected`}
        actions={
          <Badge tone={importFile.status === 'FAILED' ? 'rose' : importFile.status === 'COMPLETED' ? 'green' : 'brand'}>
            {importFile.status}
          </Badge>
        }
      />

      <Card padded={false}>
        <Tabs tabs={TABS} value={tab} onChange={setTab} />

        {tab === 'mapping' && (
          <div className="p-5">
            <p className="mb-4 text-sm text-slate-500 dark:text-slate-400">
              Columns were matched automatically. Adjust anything that looks wrong - the mapping is
              saved with the file and reused for the next file from the same source.
            </p>
            {importFile.available_sheets?.length > 1 && (
              <div className="mb-4">
                <Select label="Worksheet" value={importFile.sheet_name || ''}
                  onChange={async (event) => {
                    await api.patch(`/api/imports/${id}/`, { sheet_name: event.target.value,
                      column_mapping: mapping })
                    await api.post(`/api/imports/${id}/reanalyze/`, {})
                    refresh()
                  }}
                  options={importFile.available_sheets.map((sheet) => ({ value: sheet, label: sheet }))} />
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="border-y border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/50">
                  <tr>
                    <th className="table-th">Source column</th>
                    <th className="table-th">Example value</th>
                    <th className="table-th">Maps to</th>
                    <th className="table-th">Detection</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                  {headers.map((header) => {
                    const suggestion = suggestions.find((row) => row.source_column === header)
                    const sample = importFile.sample_rows?.[0]?.[header] || ''
                    return (
                      <tr key={header}>
                        <td className="table-td font-medium text-slate-900 dark:text-white">{header}</td>
                        <td className="table-td max-w-[240px] truncate text-slate-500">{String(sample).slice(0, 60) || '—'}</td>
                        <td className="table-td">
                          <select
                            className="input"
                            value={mapping[header] || ''}
                            onChange={(event) =>
                              setMapping((prev) => ({ ...prev, [header]: event.target.value || undefined }))}
                          >
                            <option value="">— Do not import —</option>
                            {targetFields.map((field) => (
                              <option key={field} value={field}>{field}</option>
                            ))}
                          </select>
                        </td>
                        <td className="table-td">
                          {suggestion?.target_field ? (
                            <span className="flex items-center gap-1.5 text-xs">
                              <Badge tone={suggestion.confidence >= 0.9 ? 'green' : suggestion.confidence >= 0.7 ? 'amber' : 'slate'}>
                                {Math.round(suggestion.confidence * 100)}%
                              </Badge>
                              <span className="text-slate-500">{suggestion.method}</span>
                            </span>
                          ) : (
                            <span className="text-xs text-slate-400">not detected</span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            <div className="mt-4 flex justify-end gap-2">
              <Button variant="secondary" onClick={async () => {
                await api.post(`/api/imports/${id}/reanalyze/`, {})
                refresh()
                toast('Columns re-detected', 'success')
              }}><RefreshCw className="h-4 w-4" /> Re-detect</Button>
              <Button onClick={saveMapping}><Save className="h-4 w-4" /> Save mapping & continue</Button>
            </div>
          </div>
        )}

        {tab === 'preview' && (
          <div className="p-5">
            {!preview ? <Spinner /> : (
              <>
                <div className="mb-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
                  <StatBox label="Total rows" value={number(preview.stats.rows)} icon={Database} />
                  <StatBox label="Valid" value={number(preview.stats.rows - preview.stats.invalid)} tone="text-emerald-600" icon={CheckCircle2} />
                  <StatBox label="Invalid" value={number(preview.stats.invalid)} tone="text-rose-600" icon={XCircle} />
                  <StatBox label="With email" value={number(preview.stats.with_email)} tone="text-emerald-600" icon={CheckCircle2} />
                  <StatBox label="Without email" value={number(preview.stats.without_email)} tone="text-amber-600" icon={AlertTriangle} />
                  <StatBox label="Duplicates" value={number(preview.stats.duplicates)} tone="text-amber-600" icon={AlertTriangle} />
                </div>

                <p className="mb-2 text-sm text-slate-500 dark:text-slate-400">
                  First {Math.min(50, preview.preview.length)} rows after normalization:
                </p>
                <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50 dark:bg-slate-800/50">
                      <tr>
                        <th className="table-th">Company</th>
                        <th className="table-th">Contact</th>
                        <th className="table-th">Email</th>
                        <th className="table-th">Phone</th>
                        <th className="table-th">Website</th>
                        <th className="table-th">Location</th>
                        <th className="table-th">Issues</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                      {preview.preview.map((row, index) => (
                        <tr key={index} className={row.errors?.length ? 'bg-rose-50/50 dark:bg-rose-950/20' : ''}>
                          <td className="table-td">{row.company_name || '—'}</td>
                          <td className="table-td">{row.contact_name || '—'}</td>
                          <td className="table-td">{row.email || '—'}</td>
                          <td className="table-td">{row.phone || '—'}</td>
                          <td className="table-td">{row.website || '—'}</td>
                          <td className="table-td">{[row.city, row.state].filter(Boolean).join(', ') || '—'}</td>
                          <td className="table-td text-xs text-rose-600">
                            {row.errors?.map((error) => error.message).join('; ') || ''}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="mt-4 flex justify-end">
                  <Button onClick={() => setTab('process')}>Continue to import →</Button>
                </div>
              </>
            )}
          </div>
        )}

        {tab === 'process' && (
          <div className="p-5">
            <div className="max-w-xl space-y-3">
              <Checkbox label="Import valid rows only (skip rows with errors)"
                checked={options.import_valid_only}
                onChange={(value) => setOptions((prev) => ({ ...prev, import_valid_only: value }))} />
              <Checkbox label="Skip rows with an invalid email"
                checked={options.skip_invalid_emails}
                onChange={(value) => setOptions((prev) => ({ ...prev, skip_invalid_emails: value }))} />
              <Checkbox label="Import rows without an email (Missing Email Leads)"
                checked={options.import_rows_without_email}
                onChange={(value) => setOptions((prev) => ({ ...prev, import_rows_without_email: value }))} />
              <Checkbox label="Update existing records with new information"
                checked={options.update_existing}
                onChange={(value) => setOptions((prev) => ({ ...prev, update_existing: value }))} />
              <Checkbox label="Run duplicate detection after the import"
                checked={options.run_dedupe}
                onChange={(value) => setOptions((prev) => ({ ...prev, run_dedupe: value }))} />
              <Checkbox label="Re-score imported leads"
                checked={options.rescore}
                onChange={(value) => setOptions((prev) => ({ ...prev, rescore: value }))} />

              <Select label="Chunk size" value={options.chunk_size}
                onChange={(event) => setOptions((prev) => ({ ...prev, chunk_size: Number(event.target.value) }))}
                options={[500, 1000, 2500, 5000].map((value) => ({ value, label: `${value} rows per batch` }))} />

              {job && (
                <Card className="bg-slate-50 dark:bg-slate-800/40">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                      Job #{job.id} · {job.status}
                    </p>
                    {running && <Loader2 className="h-4 w-4 animate-spin text-brand-600" />}
                  </div>
                  <ProgressBar className="mt-2" value={job.processed_rows} max={Math.max(job.total_rows, 1)} />
                  {job.total_rows > 0 && (
                    <p className="mt-2 text-xs text-slate-500">
                      {number(job.processed_rows)} / {number(job.total_rows)} rows
                      {' '}({Math.round((job.processed_rows / Math.max(job.total_rows, 1)) * 100)}%)
                    </p>
                  )}
                  <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
                    <Stat label="Created" value={number(job.created_rows)} />
                    <Stat label="Skipped" value={number(job.skipped_rows)} />
                    <Stat label="Duplicates" value={number(job.duplicate_rows)} />
                    <Stat label="Invalid" value={number(job.invalid_rows)} />
                    <Stat label="With email" value={number(job.rows_with_email)} />
                    <Stat label="Without email" value={number(job.rows_without_email)} />
                  </dl>
                  {job.error_message && (
                    <p className="mt-2 rounded bg-rose-50 p-2 text-xs text-rose-700 dark:bg-rose-950 dark:text-rose-300">
                      {job.error_message}
                    </p>
                  )}
                </Card>
              )}

              <div className="flex gap-2 pt-2">
                <Button onClick={startImport} disabled={running}>
                  {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  {running ? 'Importing…' : 'Start import'}
                </Button>
                <Link to="/leads" className="btn-secondary">View imported leads</Link>
              </div>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}

function StatBox({ label, value, icon: Icon, tone = 'text-slate-900 dark:text-white' }) {
  return (
    <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
      <div className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {Icon && <Icon className="h-3.5 w-3.5" />} {label}
      </div>
      <p className={`mt-1 text-lg font-semibold ${tone}`}>{value}</p>
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="flex justify-between">
      <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="font-medium text-slate-800 dark:text-slate-100">{value}</dd>
    </div>
  )
}
