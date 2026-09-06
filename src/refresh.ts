/* N2.1-F — lightweight server-mode state refresh.
 *
 * The smallest stable synchronization for the MVP: no WebSockets, no SSE,
 * no optimistic economy state. Three triggers, all routed through the
 * store's serialized queue (so a refresh can never overlap or overwrite an
 * in-flight mutation — responses apply in request order):
 *
 *   1. authoritative refetch after mutations   (already guaranteed by the
 *      adapter: every mutation returns the full bootstrap state)
 *   2. refetch when the window regains focus / the tab becomes visible
 *   3. a light periodic refetch while the tab is visible
 *
 * DEMO mode never starts this loop — the demo runtime is fully local.
 * This module is pure and injectable so the timing/visibility behavior is
 * unit-testable with fake timers. */

export interface RefreshLoopOptions {
  /** Enqueue an authoritative bootstrap refetch (must be serialized). */
  refresh: () => void
  /** Periodic interval while visible. Default 8s — inside the 5–10s MVP band. */
  intervalMs?: number
  /** Minimum gap between any two refreshes (focus + interval storms). */
  minGapMs?: number
  /** Injectable for tests. */
  win?: Pick<Window, 'addEventListener' | 'removeEventListener'>
  doc?: Pick<Document, 'visibilityState' | 'addEventListener' | 'removeEventListener'>
  setIntervalFn?: typeof setInterval
  clearIntervalFn?: typeof clearInterval
  now?: () => number
}

/** Starts the loop; returns the stop function. */
export function startRefreshLoop(opts: RefreshLoopOptions): () => void {
  const {
    refresh, intervalMs = 8_000, minGapMs = 1_000,
    win = window, doc = document,
    setIntervalFn = setInterval, clearIntervalFn = clearInterval,
    now = Date.now,
  } = opts

  let last = 0
  const tick = () => {
    /* Pause while hidden — no polling storm from background tabs. */
    if (doc.visibilityState !== 'visible') return
    const t = now()
    if (t - last < minGapMs) return
    last = t
    refresh()
  }

  const onFocus = () => tick()
  const onVisible = () => { if (doc.visibilityState === 'visible') tick() }

  const iv = setIntervalFn(tick, intervalMs)
  win.addEventListener('focus', onFocus)
  doc.addEventListener('visibilitychange', onVisible)

  return () => {
    clearIntervalFn(iv)
    win.removeEventListener('focus', onFocus)
    doc.removeEventListener('visibilitychange', onVisible)
  }
}
