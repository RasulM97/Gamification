import { useEffect, useRef, useState } from 'react'
import { useI18n } from '../i18n'

/** One readable alert lifetime; interaction pauses the remaining countdown. */
export function SystemToast({ message, onClose }: { message: string | null; onClose: () => void }) {
  const { t } = useI18n(), [hover, setHover] = useState(false), [focus, setFocus] = useState(false)
  const remaining = useRef(10000), close = useRef(onClose)
  close.current = onClose
  useEffect(() => { remaining.current = 10000 }, [message])
  useEffect(() => {
    if (!message || hover || focus) return
    const started = Date.now(), timer = setTimeout(() => close.current(), remaining.current)
    return () => { clearTimeout(timer); remaining.current = Math.max(0, remaining.current - (Date.now() - started)) }
  }, [message, hover, focus])
  if (!message) return null
  return <div className="panel system-toast" role="alert" onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
    onFocus={() => setFocus(true)} onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget)) setFocus(false) }}
    style={{ padding: 14, marginBlockEnd: 12, display: 'flex', gap: 12, alignItems: 'center', borderInlineStart: '3px solid var(--neg)' }}>
    <span style={{ flex: 1 }}>{message}</span><button className="btn" aria-label={t('common.close')} onClick={onClose}>{t('common.close')}</button>
  </div>
}
