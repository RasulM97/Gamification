import { useEffect, useRef, useState } from 'react'
import { LOCALES, useI18n, type DirectionPref } from '../i18n'

/* N3 §16/§17 — compact language + direction switcher.
   Language list shows native names (user-facing in their own script →
   dir="auto"); direction preference is independent of language (AUTO resolves
   from locale metadata). Applies immediately, persists to localStorage,
   no reload. */
export function LocaleSwitcher() {
  const { locale, setLocale, dirPref, setDirPref, t } = useI18n()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  const DIR_OPTS: DirectionPref[] = ['auto', 'ltr', 'rtl']

  return (
    <div className="bell" ref={ref}>
      <button
        className="bell-btn"
        onClick={() => setOpen((o) => !o)}
        title={t('settings.language')}
        aria-label={t('settings.language')}
        data-testid="locale-switcher"
        style={{ fontSize: 11, fontWeight: 600 }}
      >
        Aا
      </button>
      {open && (
        <div className="bell-pop" data-testid="locale-pop" style={{ width: 280 }}>
          <div className="bp-head">{t('settings.language')}</div>
          <div className="bp-list" style={{ maxHeight: 260 }}>
            <div className="user-pick" style={{ padding: 6 }}>
              {LOCALES.map((l) => (
                <button
                  key={l.code}
                  className={l.code === locale ? 'on' : ''}
                  onClick={() => setLocale(l.code)}
                  data-testid={`locale-${l.code}`}
                  lang={l.code}
                >
                  <span dir="auto" style={{ flex: 1, textAlign: 'start' }}>{l.nativeName}</span>
                  {l.code === locale && <span aria-hidden="true">✓</span>}
                </button>
              ))}
            </div>
          </div>
          <div className="bp-head" style={{ borderTop: '1px solid var(--rim-soft)' }}>{t('settings.direction')}</div>
          <div className="seg bp-tabs" data-testid="direction-seg" style={{ borderBottom: 0, marginBottom: 8 }}>
            {DIR_OPTS.map((p) => (
              <button
                key={p}
                className={dirPref === p ? 'on' : ''}
                onClick={() => setDirPref(p)}
                data-testid={`dir-${p}`}
              >
                {t(`settings.direction.${p}`)}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
