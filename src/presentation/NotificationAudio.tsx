import { useEffect, useRef, useState } from 'react'
import { useStore, useMe } from '../store'
import { useI18n } from '../i18n'
import type { Notice } from '../domain/model'

export function newAudibleNotices(notices: Notice[], seen: Set<string>, userId: string, muted: string[]) {
  return notices.some(n => n.userId === userId && !seen.has(n.id) && !n.read && !n.archived &&
    ['ACTION_REQUIRED', 'IMPORTANT'].includes(n.level) && !muted.includes(n.level))
}

export function NotificationAudio() {
  const { state } = useStore(), me = useMe(), { t } = useI18n()
  const key = `cve-sound:${state.companyId ?? 'demo'}:${me.id}`
  const [enabled, setEnabled] = useState(() => { try { return localStorage.getItem(key) !== 'off' } catch { return true } })
  const lastPlayed = useRef(-Infinity)
  const seen = useRef<Set<string> | null>(null), audio = useRef<AudioContext | null>(null), unlocked = useRef(false)
  useEffect(() => {
    const unlock = () => {
      try {
        audio.current ??= new AudioContext()
        void audio.current.resume().then(() => { unlocked.current = audio.current?.state === 'running' }).catch(() => {})
      } catch { /* unsupported audio must never affect work */ }
    }
    window.addEventListener('pointerdown', unlock); window.addEventListener('keydown', unlock)
    return () => { window.removeEventListener('pointerdown', unlock); window.removeEventListener('keydown', unlock); void audio.current?.close().catch(() => {}) }
  }, [])
  useEffect(() => {
    const incoming = state.notices.filter(n => n.userId === me.id)
    const play = seen.current !== null && newAudibleNotices(incoming, seen.current, me.id, state.notifMuted[me.id] ?? [])
    if (!seen.current) seen.current = new Set()
    incoming.forEach(n => seen.current!.add(n.id))
    if (!play || !enabled || !unlocked.current || !audio.current || Date.now() - lastPlayed.current < 1000) return
    lastPlayed.current = Date.now()
    // One short tone per delivery batch, regardless of notification count.
    try {
      const ctx = audio.current, osc = ctx.createOscillator(), gain = ctx.createGain()
      osc.type = 'sine'; osc.frequency.setValueAtTime(660, ctx.currentTime)
      osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.12)
      gain.gain.setValueAtTime(0.0001, ctx.currentTime)
      gain.gain.exponentialRampToValueAtTime(0.045, ctx.currentTime + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.25)
      osc.connect(gain); gain.connect(ctx.destination); osc.start(); osc.stop(ctx.currentTime + 0.27)
      osc.onended = () => { osc.disconnect(); gain.disconnect() }
    } catch { /* autoplay/platform failure is silent */ }
  }, [state.notices, state.notifMuted, me.id, enabled])
  return <button className="btn" aria-pressed={enabled} onClick={() => {
    setEnabled(!enabled); try { localStorage.setItem(key, enabled ? 'off' : 'on') } catch { /* session preference */ }
  }}>{t(enabled ? 'integrity.soundOn' : 'integrity.soundOff')}</button>
}
