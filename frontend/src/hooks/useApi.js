import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'

/** Fetch once (with loading/error state) and expose a manual refresh. */
export function useApi(path, { params, deps = [], skip = false } = {}) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(!skip)
  const key = JSON.stringify(params || {})

  const load = useCallback(async () => {
    if (!path || skip) return
    setLoading(true)
    try {
      const result = await api.get(path, params)
      setData(result)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, key, skip])

  useEffect(() => { load() }, [load, ...deps])

  return { data, error, loading, refresh: load, setData }
}

/** Server-side paginated list: {results, count, total_pages}. */
export function usePaginatedApi(path, { pageSize = 25, params = {} } = {}) {
  const [page, setPage] = useState(1)
  const [rows, setRows] = useState([])
  const [count, setCount] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState([])
  const queryKey = JSON.stringify(params)

  const load = useCallback(async () => {
    if (!path) return
    setLoading(true)
    try {
      const result = await api.get(path, { page, page_size: pageSize, ...params })
      setRows(result.results ?? result)
      setCount(result.count ?? (result.results ?? result).length)
      setTotalPages(result.total_pages ?? 1)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, page, pageSize, queryKey])

  useEffect(() => { load() }, [load])
  useEffect(() => { setPage(1); setSelected([]) }, [queryKey])
  useEffect(() => { setSelected([]) }, [page])

  const allSelected = rows.length > 0 && selected.length === rows.length
  const toggleAll = () => setSelected(allSelected ? [] : rows.map((row) => row.id))
  const toggle = (id) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((row) => row !== id) : [...prev, id]))

  return {
    rows, count, totalPages, page, setPage, loading, error, refresh: load,
    selected, setSelected, toggle, toggleAll, allSelected, setRows,
  }
}

/** Poll an endpoint every `interval` ms while `active` is true. */
export function usePolling(callback, interval = 5000, active = true) {
  const saved = useRef(callback)
  useEffect(() => { saved.current = callback }, [callback])
  useEffect(() => {
    if (!active) return undefined
    const timer = setInterval(() => saved.current(), interval)
    return () => clearInterval(timer)
  }, [interval, active])
}
