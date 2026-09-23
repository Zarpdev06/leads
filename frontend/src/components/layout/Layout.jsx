import { useEffect, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import clsx from 'clsx'
import {
  Activity, BarChart3, Bell, Building2, Database, Filter, Gauge, Inbox, LayoutDashboard,
  LogOut, Mail, Menu, Moon, Repeat, Search, Server, Settings, Sparkles, Sun, Users,
  UserX, FileText, Workflow, X,
} from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { useSettings } from '../../context/SettingsContext'
import { api } from '../../lib/api'

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/leads', label: 'Leads', icon: Database },
  { to: '/leads/missing-email', label: 'Missing Email Leads', icon: UserX },
  { to: '/companies', label: 'Companies', icon: Building2 },
  { to: '/contacts', label: 'Contacts', icon: Users },
  { to: '/imports', label: 'Imports', icon: Inbox },
  { to: '/campaigns', label: 'Campaigns', icon: Mail },
  { to: '/follow-ups', label: 'Follow-ups', icon: Repeat },
  { to: '/email', label: 'Email', icon: Mail },
  { to: '/crm', label: 'CRM', icon: Workflow },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/ai', label: 'AI', icon: Sparkles, manager: true },
  { to: '/suppression', label: 'Suppression', icon: Filter },
  { to: '/settings', label: 'Settings', icon: Settings, manager: true },
  { to: '/audit-logs', label: 'Audit Log', icon: Activity, admin: true },
]

export default function Layout({ children }) {
  const { user, logout, isManager, isAdmin } = useAuth()
  const { smtp } = useSettings()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [theme, setTheme] = useState(() => localStorage.getItem('leads.theme') || 'light')
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle('dark', theme === 'dark')
    localStorage.setItem('leads.theme', theme)
  }, [theme])

  useEffect(() => { setSidebarOpen(false) }, [location.pathname])

  useEffect(() => {
    if (query.length < 2) { setResults([]); return undefined }
    const timer = setTimeout(async () => {
      try {
        const data = await api.get('/api/search/', { q: query })
        setResults(data.results || [])
      } catch { setResults([]) }
    }, 300)
    return () => clearTimeout(timer)
  }, [query])

  const items = NAV.filter((item) => (!item.manager || isManager) && (!item.admin || isAdmin))

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      {/* Sidebar */}
      <aside className={clsx(
        'fixed inset-y-0 left-0 z-40 w-64 transform border-r border-slate-200 bg-white transition-transform dark:border-slate-800 dark:bg-slate-900',
        sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
      )}>
        <div className="flex h-16 items-center gap-2 border-b border-slate-200 px-5 dark:border-slate-800">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600 text-white">
            <Gauge className="h-4 w-4" />
          </span>
          <div className="leading-tight">
            <p className="text-sm font-semibold text-slate-900 dark:text-white">Lead Intelligence</p>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">Outreach & CRM</p>
          </div>
          <button className="ml-auto lg:hidden" onClick={() => setSidebarOpen(false)}>
            <X className="h-4 w-4 text-slate-500" />
          </button>
        </div>

        <nav className="flex h-[calc(100vh-4rem)] flex-col justify-between overflow-y-auto p-3">
          <div className="space-y-0.5">
            {items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => clsx(
                  'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition',
                  isActive
                    ? 'bg-brand-50 text-brand-700 dark:bg-brand-950 dark:text-brand-300'
                    : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800',
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </NavLink>
            ))}
          </div>

          <div className="space-y-2 border-t border-slate-200 pt-3 dark:border-slate-800">
            <div className={clsx(
              'rounded-lg px-3 py-2 text-xs',
              smtp?.configured
                ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300'
                : 'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300',
            )}>
              <div className="flex items-center gap-1.5 font-medium">
                <Server className="h-3.5 w-3.5" />
                SMTP {smtp?.configured ? 'configured' : 'not configured'}
              </div>
              {smtp?.host && <p className="mt-0.5 truncate opacity-80">{smtp.host}:{smtp.port}</p>}
            </div>
            <div className="flex items-center gap-2 px-2">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-slate-800 dark:text-slate-200">{user?.full_name || user?.email}</p>
                <p className="text-xs uppercase text-slate-500">{user?.role}</p>
              </div>
              <button onClick={logout} title="Sign out" className="rounded p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800">
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
        </nav>
      </aside>

      {/* Main */}
      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-slate-200 bg-white/90 px-4 backdrop-blur dark:border-slate-800 dark:bg-slate-900/90">
          <button className="lg:hidden" onClick={() => setSidebarOpen(true)}>
            <Menu className="h-5 w-5 text-slate-600 dark:text-slate-300" />
          </button>

          <div className="relative max-w-md flex-1">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <input
                className="input pl-9"
                placeholder="Search companies, contacts, emails…"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
            {results.length > 0 && (
              <div className="absolute mt-1 w-full overflow-hidden rounded-lg border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-800">
                {results.slice(0, 8).map((result) => (
                  <button
                    key={`${result.type}-${result.id}`}
                    onClick={() => { navigate(`/leads/${result.id}`); setQuery(''); setResults([]) }}
                    className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-slate-50 dark:hover:bg-slate-700"
                  >
                    <span className="truncate text-slate-800 dark:text-slate-100">{result.title}</span>
                    <span className="ml-2 shrink-0 text-xs text-slate-400">{result.subtitle}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
            title="Toggle theme"
          >
            {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
          <a href="/admin/" target="_blank" rel="noreferrer" className="btn-secondary btn-sm hidden sm:inline-flex">
            <FileText className="h-3.5 w-3.5" /> Django Admin
          </a>
        </header>

        <main className="p-4 lg:p-6">{children}</main>
      </div>

      {sidebarOpen && (
        <div className="fixed inset-0 z-30 bg-slate-900/40 lg:hidden" onClick={() => setSidebarOpen(false)} />
      )}
    </div>
  )
}
