import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, tokenStore } from '../lib/api'

const AuthContext = createContext(null)

const ROLES = { ADMIN: 'ADMIN', MANAGER: 'MANAGER', AGENT: 'AGENT', VIEWER: 'VIEWER' }

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  const loadUser = useCallback(async () => {
    try {
      const data = await api.get('/api/auth/me/')
      setUser(data)
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (tokenStore.access) loadUser()
    else setLoading(false)
  }, [loadUser])

  const login = useCallback(async (email, password) => {
    const data = await api.post('/api/auth/login/', { email, password })
    tokenStore.set({ access: data.access, refresh: data.refresh })
    setUser(data.user)
    return data.user
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.post('/api/auth/logout/', { refresh: tokenStore.refresh })
    } catch { /* ignore */ }
    tokenStore.clear()
    setUser(null)
  }, [])

  const value = useMemo(() => ({
    user,
    loading,
    login,
    logout,
    isAuthenticated: Boolean(user),
    canModify: user && user.role !== ROLES.VIEWER,
    isManager: user && [ROLES.ADMIN, ROLES.MANAGER].includes(user.role),
    isAdmin: user?.role === ROLES.ADMIN,
  }), [user, loading, login, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
