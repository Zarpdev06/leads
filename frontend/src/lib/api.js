/**
 * API client.
 *
 * * JWT access token in localStorage, refresh handled transparently
 * * every endpoint is a relative URL (`/api/...`) so the Vite dev proxy and
 *   nginx resolve the backend - the browser never sees a host name
 * * credentials never appear here: the backend never returns them
 */
const ACCESS_KEY = 'leads.access'
const REFRESH_KEY = 'leads.refresh'

export const tokenStore = {
  get access() { return localStorage.getItem(ACCESS_KEY) },
  get refresh() { return localStorage.getItem(REFRESH_KEY) },
  set({ access, refresh }) {
    if (access) localStorage.setItem(ACCESS_KEY, access)
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh)
  },
  clear() { localStorage.removeItem(ACCESS_KEY); localStorage.removeItem(REFRESH_KEY) },
}

class ApiError extends Error {
  constructor(message, status, data) {
    super(message)
    this.status = status
    this.data = data
  }
}

async function refreshAccessToken() {
  const refresh = tokenStore.refresh
  if (!refresh) throw new ApiError('Not authenticated', 401)
  const response = await fetch('/api/auth/refresh/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  })
  if (!response.ok) {
    tokenStore.clear()
    throw new ApiError('Session expired', 401)
  }
  const data = await response.json()
  tokenStore.set({ access: data.access })
  return data.access
}

async function request(path, { method = 'GET', body, params, headers = {}, raw = false, isForm = false } = {}, retry = true) {
  let url = path
  if (params) {
    const search = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === '') return
      if (Array.isArray(value)) value.forEach((item) => search.append(key, item))
      else search.append(key, value)
    })
    const query = search.toString()
    if (query) url += (url.includes('?') ? '&' : '?') + query
  }

  const options = { method, headers: { ...headers } }
  if (body !== undefined) {
    if (isForm) options.body = body
    else {
      options.headers['Content-Type'] = 'application/json'
      options.body = JSON.stringify(body)
    }
  }
  const token = tokenStore.access
  if (token) options.headers.Authorization = `Bearer ${token}`

  let response = await fetch(url, options)

  if (response.status === 401 && retry && tokenStore.refresh) {
    try {
      const access = await refreshAccessToken()
      options.headers.Authorization = `Bearer ${access}`
      response = await fetch(url, options)
    } catch (error) {
      throw error
    }
  }

  if (!response.ok) {
    let message = `Request failed (${response.status})`
    let data = null
    try {
      data = await response.json()
      message = data?.detail || data?.message
        || (typeof data === 'object' && Object.values(data)[0]?.[0])
        || message
    } catch { /* non-JSON error body */ }
    throw new ApiError(message, response.status, data)
  }
  if (raw) return response
  if (response.status === 204) return null
  return response.json()
}

export const api = {
  get: (path, params) => request(path, { params }),
  post: (path, body) => request(path, { method: 'POST', body }),
  patch: (path, body) => request(path, { method: 'PATCH', body }),
  put: (path, body) => request(path, { method: 'PUT', body }),
  delete: (path) => request(path, { method: 'DELETE' }),
  upload: (path, formData) => request(path, { method: 'POST', body: formData, isForm: true }),
}

export { ApiError }
