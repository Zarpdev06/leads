import { createContext, useContext, useEffect, useState } from 'react'
import { api } from '../lib/api'

/**
 * Public configuration (never contains SMTP credentials - the backend masks
 * them). Used by the sidebar, capacity meter and Settings page.
 */
const SettingsContext = createContext({ values: {}, smtp: {}, loading: true, refresh: () => {} })

export function SettingsProvider({ children }) {
  const [state, setState] = useState({ values: {}, smtp: {}, loading: true })

  const refresh = async () => {
    try {
      const data = await api.get('/api/settings/')
      setState({ values: data.values || {}, smtp: data.smtp || {}, loading: false })
    } catch {
      setState((prev) => ({ ...prev, loading: false }))
    }
  }

  useEffect(() => { refresh() }, [])

  return (
    <SettingsContext.Provider value={{ ...state, refresh }}>{children}</SettingsContext.Provider>
  )
}

export const useSettings = () => useContext(SettingsContext)
