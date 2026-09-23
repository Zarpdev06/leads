import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Check, Mail, Sparkles, Target } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { api } from '../lib/api'
import { useApi } from '../hooks/useApi'
import { Button, Card, Checkbox, Input, Select, Spinner, Textarea, Toggle, toast } from '../components/ui'
import { number } from '../lib/format'

const STEPS = ['Basics', 'Audience', 'Message', 'Schedule', 'Review']

export default function CampaignNew() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    name: '', description: '',
    target_industries: [], target_states: '', target_cities: '',
    min_lead_score: '', require_website: false, require_phone: false,
    require_contact_person: false, exclude_replied: true, exclude_ever_contacted: false,
    template: '', use_ai_personalization: true, ai_instructions: '',
    recommended_service: '', subject: '',
    daily_limit: 90, send_window_start: '09:30', send_window_end: '17:30',
    follow_up_enabled: true, follow_up_sequence: '',
    from_name: '', from_email: '', reply_to: '',
  })

  const { data: templates } = useApi('/api/email/templates/', { params: { page_size: 100 } })
  const { data: industries } = useApi('/api/industries/tree/')
  const { data: services } = useApi('/api/services/', { params: { page_size: 100 } })
  const { data: sequences } = useApi('/api/follow-ups/sequences/', { params: { page_size: 100 } })
  const [audience, setAudience] = useState(null)

  const set = (key, value) => setForm((prev) => ({ ...prev, [key]: value }))

  const industriesFlat = []
  const walk = (nodes, depth = 0) => (nodes || []).forEach((node) => {
    industriesFlat.push({ id: node.id, label: `${'— '.repeat(depth)}${node.name}` })
    walk(node.children, depth + 1)
  })
  walk(industries)

  const create = async () => {
    setSaving(true)
    try {
      const payload = {
        ...form,
        target_industries: form.target_industries,
        target_states: form.target_states ? form.target_states.split(',').map((value) => value.trim()) : [],
        target_cities: form.target_cities ? form.target_cities.split(',').map((value) => value.trim()) : [],
        min_lead_score: form.min_lead_score === '' ? 0 : Number(form.min_lead_score),
        template: form.template || null,
        recommended_service: form.recommended_service || null,
        follow_up_sequence: form.follow_up_sequence || null,
      }
      const campaign = await api.post('/api/campaigns/', payload)
      toast('Campaign created', 'success')
      navigate(`/campaigns/${campaign.id}`)
    } catch (error) {
      toast('Could not create the campaign', 'error', error.data ? JSON.stringify(error.data) : error.message)
    } finally {
      setSaving(false)
    }
  }

  const next = async () => {
    if (step === 1) {
      // Preview the audience size before continuing.
      const payload = {
        target_industries: form.target_industries,
        target_states: form.target_states ? form.target_states.split(',').map((v) => v.trim()) : [],
        target_cities: form.target_cities ? form.target_cities.split(',').map((v) => v.trim()) : [],
        min_lead_score: form.min_lead_score === '' ? 0 : Number(form.min_lead_score),
        require_website: form.require_website,
        require_phone: form.require_phone,
        require_contact_person: form.require_contact_person,
        exclude_replied: form.exclude_replied,
        exclude_ever_contacted: form.exclude_ever_contacted,
        name: 'preview',
      }
      try {
        const draft = await api.post('/api/campaigns/', { ...payload, name: `preview-${Date.now()}` })
        const previewData = await api.get(`/api/campaigns/${draft.id}/audience/`)
        setAudience(previewData)
        await api.delete(`/api/campaigns/${draft.id}/`)
      } catch (error) {
        toast('Could not preview the audience', 'error', error.message)
      }
    }
    setStep((prev) => Math.min(prev + 1, STEPS.length - 1))
  }

  return (
    <div className="space-y-4">
      <button onClick={() => navigate('/campaigns')} className="text-xs text-slate-500 hover:underline">
        <ArrowLeft className="mr-1 inline h-3 w-3" /> Back to campaigns
      </button>

      <PageHeader title="New campaign" description={`Step ${step + 1} of ${STEPS.length}: ${STEPS[step]}`} />

      <div className="mb-4 flex gap-1">
        {STEPS.map((label, index) => (
          <div key={label} className="flex-1">
            <div className={`h-1.5 rounded-full ${index <= step ? 'bg-brand-600' : 'bg-slate-200 dark:bg-slate-800'}`} />
            <p className={`mt-1 text-xs ${index <= step ? 'font-medium text-brand-700 dark:text-brand-400' : 'text-slate-400'}`}>{label}</p>
          </div>
        ))}
      </div>

      <Card>
        {step === 0 && (
          <div className="space-y-4">
            <Input label="Campaign name" required value={form.name}
              onChange={(event) => set('name', event.target.value)}
              placeholder="Auto detailing - Dallas - Q4" />
            <Textarea label="Description" value={form.description}
              onChange={(event) => set('description', event.target.value)} />
            <div className="grid gap-4 sm:grid-cols-2">
              <Input label="From name" value={form.from_name}
                onChange={(event) => set('from_name', event.target.value)} hint="Leave empty to use the default" />
              <Input label="From email" value={form.from_email}
                onChange={(event) => set('from_email', event.target.value)} hint="Must be verified with your SMTP provider" />
              <Input label="Reply-to" value={form.reply_to}
                onChange={(event) => set('reply_to', event.target.value)} />
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-4">
            <div>
              <p className="label">Industries / niches</p>
              <div className="max-h-56 overflow-y-auto rounded-lg border border-slate-200 p-2 dark:border-slate-800">
                {industriesFlat.length === 0 && <Spinner />}
                {industriesFlat.map((industry) => (
                  <Checkbox key={industry.id} className="block py-0.5"
                    label={industry.label}
                    checked={form.target_industries.includes(industry.id)}
                    onChange={(checked) => set('target_industries', checked
                      ? [...form.target_industries, industry.id]
                      : form.target_industries.filter((id) => id !== industry.id))} />
                ))}
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Input label="States" value={form.target_states}
                onChange={(event) => set('target_states', event.target.value)}
                hint="Comma separated, e.g. TX, OK" />
              <Input label="Cities" value={form.target_cities}
                onChange={(event) => set('target_cities', event.target.value)}
                hint="Comma separated" />
              <Input label="Minimum score" type="number" value={form.min_lead_score}
                onChange={(event) => set('min_lead_score', event.target.value)} />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Checkbox label="Require a website" checked={form.require_website}
                onChange={(value) => set('require_website', value)} />
              <Checkbox label="Require a phone number" checked={form.require_phone}
                onChange={(value) => set('require_phone', value)} />
              <Checkbox label="Require a contact person" checked={form.require_contact_person}
                onChange={(value) => set('require_contact_person', value)} />
              <Checkbox label="Exclude leads that already replied" checked={form.exclude_replied}
                onChange={(value) => set('exclude_replied', value)} />
              <Checkbox label="Exclude leads contacted before" checked={form.exclude_ever_contacted}
                onChange={(value) => set('exclude_ever_contacted', value)} />
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <Select label="Email template" value={form.template}
              onChange={(event) => set('template', event.target.value)}
              options={[{ value: '', label: 'Choose a template…' },
                ...(templates?.results || []).map((row) => ({ value: row.id, label: row.name }))]} />
            <Input label="Subject (override)" value={form.subject}
              onChange={(event) => set('subject', event.target.value)}
              hint="Supports {{company_name}}, {{first_name}}, {{city}} …" />
            <Toggle label="Use AI personalization" checked={form.use_ai_personalization}
              onChange={(value) => set('use_ai_personalization', value)}
              hint="The AI writes from verified lead data only - it never invents facts." />
            <Textarea label="AI instructions" value={form.ai_instructions}
              onChange={(event) => set('ai_instructions', event.target.value)}
              hint="e.g. focus on missed calls and after-hours enquiries" />
            <Select label="Recommended service (optional)" value={form.recommended_service}
              onChange={(event) => set('recommended_service', event.target.value)}
              options={[{ value: '', label: 'Match per lead (rules + AI)' },
                ...(services?.results || []).map((row) => ({ value: row.id, label: row.name }))]} />
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-3">
              <Input label="Daily limit" type="number" max={100} value={form.daily_limit}
                onChange={(event) => set('daily_limit', Number(event.target.value))}
                hint="Capped by the SMTP limit and the safety cap" />
              <Input label="Send window start" value={form.send_window_start}
                onChange={(event) => set('send_window_start', event.target.value)} hint="HH:MM" />
              <Input label="Send window end" value={form.send_window_end}
                onChange={(event) => set('send_window_end', event.target.value)} hint="HH:MM" />
            </div>
            <Toggle label="Follow-ups" checked={form.follow_up_enabled}
              onChange={(value) => set('follow_up_enabled', value)}
              hint="Stops automatically on reply, unsubscribe, bounce or conversion" />
            <Select label="Follow-up sequence" value={form.follow_up_sequence}
              onChange={(event) => set('follow_up_sequence', event.target.value)}
              options={[{ value: '', label: 'Choose a sequence…' },
                ...(sequences?.results || []).map((row) => ({ value: row.id, label: row.name }))]} />
          </div>
        )}

        {step === 4 && (
          <div className="space-y-3 text-sm">
            <Summary label="Campaign" value={form.name || '—'} />
            <Summary label="Audience" value={
              audience ? `${number(audience.count)} leads match the criteria` : 'set on the Audience step'
            } />
            {audience && <Summary label="Estimated duration" value={`${audience.estimated_days} day(s) at ${form.daily_limit}/day`} />}
            <Summary label="Template" value={(templates?.results || []).find((row) => String(row.id) === form.template)?.name || '—'} />
            <Summary label="AI personalization" value={form.use_ai_personalization ? 'On' : 'Off'} />
            <Summary label="Daily limit" value={`${form.daily_limit} emails/day (09:30-17:30 window applied)`} />
            <Summary label="Follow-ups" value={form.follow_up_enabled ? 'Enabled' : 'Disabled'} />
            <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              Nothing is sent until you start the campaign. Every lead is re-checked for eligibility
              (valid email, not suppressed, not contacted recently) at send time, and the daily quota
              is enforced by the database - not by the UI.
            </p>
          </div>
        )}

        <div className="mt-5 flex justify-between">
          <Button variant="secondary" disabled={step === 0} onClick={() => setStep((prev) => prev - 1)}>
            <ArrowLeft className="h-4 w-4" /> Back
          </Button>
          {step < STEPS.length - 1 ? (
            <Button onClick={next}>Next <ArrowRight className="h-4 w-4" /></Button>
          ) : (
            <Button onClick={create} loading={saving}><Check className="h-4 w-4" /> Create campaign</Button>
          )}
        </div>
      </Card>
    </div>
  )
}

function Summary({ label, value }) {
  return (
    <div className="flex justify-between border-b border-slate-100 pb-2 dark:border-slate-800">
      <span className="text-slate-500 dark:text-slate-400">{label}</span>
      <span className="font-medium text-slate-800 dark:text-slate-100">{value}</span>
    </div>
  )
}
