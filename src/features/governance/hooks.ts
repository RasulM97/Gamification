/* Shared async-state hook for governance surfaces (Cohesion §6):
 * every panel gets the same loading / error / retry discipline. */
import { useCallback, useEffect, useRef, useState } from 'react'

export interface AsyncState<T> {
  /* error keeps the caught value (boolean-like truthiness preserved) so views
     can apply the F4 taxonomy: 403/409 authority/state rejections are final —
     no retry; anything else offers retry. */
  data: T | null; loading: boolean; error: unknown; reload: () => void
}

export function useGovData<T>(loader: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<unknown>(null)
  const generation = useRef(0)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const load = useCallback(loader, deps)
  const [loadedBy, setLoadedBy] = useState<(() => Promise<T>) | null>(null)
  const reload = useCallback(() => {
    const request = ++generation.current
    setLoading(true); setError(null); setData(null); setLoadedBy(() => load)
    load().then(value => {
      if (request !== generation.current) return
      setData(value); setLoading(false)
    }).catch(err => {
      if (request !== generation.current) return
      setError(err); setLoading(false)
    })
  }, [load])
  useEffect(() => { reload(); return () => { ++generation.current } }, [reload])
  return loadedBy === load ? { data, loading, error, reload }
    : { data: null, loading: true, error: null, reload }
}
