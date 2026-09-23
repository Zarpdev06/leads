import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Key, Sparkles, Wand2 } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { api } from '../lib/api'
import { useApi } from '../hooks/useApi'
import { Badge, Button, Card, Input, Modal, Spinner, Textarea, Toggle, toast } from '../components/ui'
import { dateTime, titleCase } from '../lib/format'

export default function AI() {
  const { data, loading, refresh } = useApi('/api/ai/')
  const [leadId, setLeadId] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [providerForm, setProviderForm] = useState(null)

  const generate = async () => {
    setBusy(true)
    try {
      const data2 = await api.post('/api/ai/generate/', { lead_id: Number(leadId) })
      setResult(data2)
    } catch (error) {
      toast('Generation failed', 'error', error.message)
    } finally {
      setBusy(false)
    }
  }

  const saveProvider = async () => {
    if (!providerForm) return
    await api.patch(`/api/ai/providers/${providerForm.id}/`, {
      model: providerForm.model, base_url: providerForm.base_url,
      is_active: providerForm.is_active, api_key: providerForm.api_key || undefined,
    })
    toast('Provider saved', 'success')
    setProviderForm(null)
    refresh()
  }

  const testProvider = async (id) => {
    const result = await api.post(`/api/ai/providers/${id}/test/`, {})
    toast(result.ok ? 'Connection OK' : 'Connection failed', result.ok ? 'success' : 'error', result.message)
    refresh()
  }

  if (loading) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-4">
      <PageHeader
        title="AI personalization"
        description="Generate subject lines, opening sentences and value propositions from verified lead data only."
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <h3 className="mb-3 text-sm font-semibold text-slate-900 dark:text-white">Active provider</h3>
          <p className="text-2xl font-semibold text-slate-900 dark:text-white">{titleCase(data?.active_provider || 'rules')}</p>
          <p className="text-xs text-slate-500">{data?.model || 'default model'}</p>
          <dl className="mt-3 space-y-1 text-sm">
            <Row label="AI enabled" value={data?.enabled ? 'Yes' : 'No'} />
            <Row label="API key" value={data?.has_api_key ? <Badge tone="green">configured</Badge> : <Badge tone="amber">not configured</Badge>} />
            <Row label="Brand voice" value={data?.brand_voice || '—'} />
            <Row label="Fact checking" value={data?.safety_strict ? 'Strict' : 'Standard'} />
            <Row label="Generated" value={data?.stats?.generated ?? 0} />
            <Row label="Rejected by safety" value={data?.stats?.rejected ?? 0} />
          </dl>
        </Card>

        <Card className="lg:col-span-2">
          <h3 className="mb-3 text-sm font-semibold text-slate-900 dark:text-white">Providers</h3>
          <div className="space-y-2">
            {(data?.providers || []).map((provider) => {
              const configured = (data?.configured_providers || []).find((row) => row.provider === provider.key)
              return (
                <div key={provider.key} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                  <div>
                    <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                      {provider.label}
                      {provider.key === data?.active_provider && <Badge className="ml-2" tone="brand">active</Badge>}
                    </p>
                    <p className="text-xs text-slate-500">
                      {configured?.model || 'default model'}
                      {provider.requires_api_key && (configured?.has_key ? ' · key set' : ' · no key')}
                      {configured?.last_test_ok !== null && configured?.last_test_ok !== undefined &&
                        ` · last test ${configured.last_test_ok ? 'ok' : 'failed'}`}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="secondary" onClick={() => testProvider(configured?.id || 0)}
                      disabled={!configured}>Test</Button>
                    <Button size="sm" variant="secondary" onClick={() => setProviderForm({
                      id: configured?.id, provider: provider.key, model: configured?.model || '',
                      base_url: configured?.base_url || '', is_active: configured?.is_active ?? true,
                      api_key: '',
                    })}>
                      <Key className="h-3.5 w-3.5" /> Configure
                    </Button>
                  </div>
                </div>
              )
            })}
          </div>
          <p className="mt-3 text-xs text-slate-500">
            Without an API key the platform uses the deterministic rule-based provider, which is
            offline, free and never invents facts.
          </p>
        </Card>
      </div>

      <Card>
        <h3 className="mb-3 text-sm font-semibold text-slate-900 dark:text-white">Try it on a lead</h3>
        <div className="flex flex-wrap items-end gap-2">
          <Input className="w-40" label="Lead ID" value={leadId}
            onChange={(event) => setLeadId(event.target.value.replace(/\D/g, ''))}
            hint={<Link to="/leads" className="link">Find a lead</Link>} />
          <Button onClick={generate} loading={busy}><Wand2 className="h-4 w-4" /> Generate</Button>
        </div>

        {result && (
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
              <p className="text-xs uppercase tracking-wide text-slate-500">Subject</p>
              <p className="text-sm font-medium text-slate-900 dark:text-white">{result.subject}</p>
              <p className="mt-3 text-xs uppercase tracking-wide text-slate-500">Opening sentence</p>
              <p className="text-sm text-slate-700 dark:text-slate-300">{result.opening_sentence}</p>
              <p className="mt-3 text-xs uppercase tracking-wide text-slate-500">Personalization</p>
              <p className="text-sm text-slate-700 dark:text-slate-300">{result.personalization}</p>
              <p className="mt-3 text-xs uppercase tracking-wide text-slate-500">Value proposition</p>
              <p className="text-sm text-slate-700 dark:text-slate-300">{result.value_proposition}</p>
              <p className="mt-3 text-xs uppercase tracking-wide text-slate-500">Call to action</p>
              <p className="text-sm text-slate-700 dark:text-slate-300">{result.cta}</p>
              <p className="mt-3 text-xs text-slate-400">
                {result.provider} · {result.model} · recommended service: {result.recommended_service}
              </p>
            </div>
            <div>
              <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">Email body</p>
              <div className="email-body rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-800"
                dangerouslySetInnerHTML={{ __html: result.body_html }} />
            </div>
          </div>
        )}
      </Card>

      <Card>
        <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
          <AlertTriangle className="h-4 w-4 text-amber-500" /> Safety rules
        </h3>
        <ul className="list-inside list-disc space-y-1 text-sm text-slate-600 dark:text-slate-300">
          <li>The AI receives only verified lead fields (business name, industry, city, state, website, contact).</li>
          <li>Every generated email is checked for invented revenue, employee counts, clients, awards, ratings, locations, services or technologies.</li>
          <li>Any number that is not present in the lead data causes the output to be rejected.</li>
          <li>Rejected output is replaced by the facts-only version - the recipient never sees an invented claim.</li>
        </ul>
      </Card>

      <Modal open={Boolean(providerForm)} onClose={() => setProviderForm(null)}
        title={`Configure ${providerForm?.provider}`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setProviderForm(null)}>Cancel</Button>
            <Button onClick={saveProvider}>Save</Button>
          </>
        }>
        {providerForm && (
          <div className="space-y-3">
            <Input label="Model" value={providerForm.model}
              onChange={(event) => setProviderForm((prev) => ({ ...prev, model: event.target.value }))}
              hint="Leave empty to use the provider default" />
            <Input label="Base URL" value={providerForm.base_url}
              onChange={(event) => setProviderForm((prev) => ({ ...prev, base_url: event.target.value }))}
              hint="Only needed for OpenAI-compatible or local endpoints" />
            <Input label="API key" type="password" value={providerForm.api_key}
              onChange={(event) => setProviderForm((prev) => ({ ...prev, api_key: event.target.value }))}
              hint="Stored encrypted; never returned by the API or shown in the UI" />
            <Toggle label="Active" checked={providerForm.is_active}
              onChange={(value) => setProviderForm((prev) => ({ ...prev, is_active: value }))} />
          </div>
        )}
      </Modal>
    </div>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="text-slate-800 dark:text-slate-100">{value}</dd>
    </div>
  )
}
