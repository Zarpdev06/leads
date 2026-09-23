import { useEffect, useState } from 'react'
import { CheckCircle2, Loader2 } from 'lucide-react'
import { api } from '../lib/api'
import { Button, Card } from '../components/ui'

export default function Unsubscribe() {
  const [state, setState] = useState({ loading: true, data: null, done: false, error: null })

  const token = window.location.pathname.split('/').filter(Boolean).pop()

  useEffect(() => {
    api.get(`/api/unsubscribe/${token}/`)
      .then((data) => setState({ loading: false, data, done: false, error: null }))
      .catch((error) => setState({ loading: false, data: null, done: false, error: error.message }))
  }, [token])

  const confirm = async () => {
    const result = await api.post(`/api/unsubscribe/${token}/`, {})
    setState((prev) => ({ ...prev, done: result.unsubscribed, data: prev.data }))
  }

  return (
    <div className="grid min-h-screen place-items-center bg-slate-100 px-4 dark:bg-slate-950">
      <Card className="w-full max-w-md text-center">
        {state.loading && <Loader2 className="mx-auto h-6 w-6 animate-spin text-brand-600" />}

        {state.error && (
          <>
            <h1 className="text-lg font-semibold text-slate-900 dark:text-white">Link not valid</h1>
            <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
              This unsubscribe link could not be found. If you keep receiving unwanted email, please
              reply asking us to remove you.
            </p>
          </>
        )}

        {state.data && !state.done && (
          <>
            <h1 className="text-lg font-semibold text-slate-900 dark:text-white">Unsubscribe</h1>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
              Remove <strong>{state.data.email}</strong>
              {state.data.company ? ` (${state.data.company})` : ''} from all future marketing emails?
            </p>
            {state.data.subject && (
              <p className="mt-1 text-xs text-slate-500">Last email: “{state.data.subject}”</p>
            )}
            <Button className="mt-5 w-full" onClick={confirm}>Yes, unsubscribe me</Button>
            {state.data.already_unsubscribed && (
              <p className="mt-2 text-xs text-slate-500">You were already unsubscribed from this message.</p>
            )}
          </>
        )}

        {state.done && (
          <>
            <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-500" />
            <h1 className="mt-3 text-lg font-semibold text-slate-900 dark:text-white">You are unsubscribed</h1>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
              This address has been added to our suppression list and will not receive any further
              marketing email. Transactional messages (such as invoices) are not affected.
            </p>
          </>
        )}
      </Card>
    </div>
  )
}
