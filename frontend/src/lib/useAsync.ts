import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'

interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: string | null
  reload: () => void
  setData: (d: T) => void
}

/** Runs `fn` on mount and whenever `deps` change. Returns data/loading/error + reload. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [nonce, setNonce] = useState(0)

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fn, deps)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    run()
      .then((res) => {
        if (active) setData(res)
      })
      .catch((e: unknown) => {
        if (!active) return
        setError(e instanceof ApiError ? e.message : 'Не удалось загрузить данные')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [run, nonce])

  const reload = useCallback(() => setNonce((n) => n + 1), [])
  return { data, loading, error, reload, setData }
}
