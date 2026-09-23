import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Gauge, Loader2, Lock } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { Card, Button, Input } from '../components/ui'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      await login(email, password)
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setError(err.message || 'Unable to sign in')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-slate-100 px-4 dark:bg-slate-950">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand-600 text-white"><Gauge className="h-5 w-5" /></span>
          <div className="leading-tight">
            <p className="text-base font-semibold text-slate-900 dark:text-white">Lead Intelligence</p>
            <p className="text-xs text-slate-500 dark:text-slate-400">Outreach & CRM platform</p>
          </div>
        </div>
        <Card>
          <form onSubmit={submit} className="space-y-4">
            <Input
              label="Email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@company.com"
            />
            <Input
              label="Password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="••••••••"
            />
            {error && (
              <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-300">{error}</p>
            )}
            <Button type="submit" className="w-full" loading={loading}>
              {!loading && <Lock className="h-4 w-4" />} Sign in
            </Button>
          </form>
        </Card>
        <p className="mt-4 text-center text-xs text-slate-500 dark:text-slate-400">
          Default administrator is created with <code>python manage.py bootstrap_admin</code>
        </p>
      </div>
    </div>
  )
}
