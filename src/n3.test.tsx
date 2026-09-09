// @vitest-environment jsdom
/* Phase N3 — Internationalization & Localization Integration (§28 matrix).
     LOCALE      1–5    default en, switching, persistence, invalid stored, switcher lists 10
     DIRECTION   6–12   AUTO resolution, LTR/RTL overrides, root attribute, persistence, invalid
     TRANSLATION 13–18  interpolation, fail-safe params, unknown key, en fallback, tActive, no-provider hook
     USER CONTENT 19–24 byte-identical user content, dir="auto", no state mutation, history prose
     FORMATTING  25–28  numbers, percents, dates, relative times via Intl
     FALLBACK    29–30  unknown key → safe key + dev warning, never crash; garbage locale → en
     RTL         31–34  root dir, locale switch back, direction independent of language, bidi content
     LINKS       35–37  linkifier intact under localization, bidi-safe link text
     PARITY      38–40  bundled key sets identical, placeholder parity, meta covers the 10 locales
   File-level parity (valid JSON on disk, no empties) lives in src/i18n/parity.test.ts (§23). */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, createElement as h, isValidElement } from 'react'
import type { ReactElement, ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import type { Root } from 'react-dom/client'
import { StoreProvider, useStore } from './store'
import type { State } from './domain/engine'
import { seed } from './domain/engine'
import {
  FALLBACK_LOCALE, I18nProvider, LOCALES, currentLocale, fmtDateL, fmtInt, fmtPct,
  intlLocaleOf, localeMeta, readStoredDirection, readStoredLocale, relTime,
  resolveDirection, setActiveLocale, tActive, translate, useI18n,
} from './i18n'
import { LinkText, linkifyText, localizedHist } from './ui'
import { LocaleSwitcher } from './components/LocaleSwitcher'
import { TasksView } from './views/Tasks'
import meta from './i18n/locale-meta.json'
import enDict from './i18n/locales/en.json'
import zhDict from './i18n/locales/zh-CN.json'
import ruDict from './i18n/locales/ru.json'
import hiDict from './i18n/locales/hi.json'
import faDict from './i18n/locales/fa.json'
import arDict from './i18n/locales/ar.json'
import heDict from './i18n/locales/he.json'
import trDict from './i18n/locales/tr.json'
import koDict from './i18n/locales/ko.json'
import jaDict from './i18n/locales/ja.json'

const DICTS: Record<string, Record<string, string>> = {
  'zh-CN': zhDict, ru: ruDict, hi: hiDict, fa: faDict, ar: arDict,
  he: heDict, tr: trDict, ko: koDict, ja: jaDict,
}
const EN: Record<string, string> = enDict

;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true

const META = meta as unknown as Record<string, { nativeName: string; defaultDirection: string }>
const ME_KEY = 'cve-demo-me-v1'
const persona = (id: string) => localStorage.setItem(ME_KEY, id)

let host: HTMLDivElement
let root: Root | null = null
async function render(node: ReactNode, withI18n = false) {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => {
    root!.render(h(StoreProvider, null, withI18n ? h(I18nProvider, null, node) : node))
  })
}

let stateRef: () => State = () => seed()
function Capture() {
  const { state } = useStore()
  stateRef = () => state
  return null
}

beforeEach(() => {
  localStorage.clear()
  setActiveLocale('en')
  stateRef = () => seed()
})
afterEach(async () => {
  if (root) await act(async () => root!.unmount())
  host?.remove()
  root = null
  document.documentElement.lang = ''
  document.documentElement.dir = ''
  vi.restoreAllMocks()
})

const anchors = (text: string) =>
  linkifyText(text)
    .filter((n): n is ReactElement => isValidElement(n))
    .map((n) => ({ href: String((n.props as { href?: string }).href), text: String((n.props as { children?: unknown }).children) }))

describe('N3 §28 · LOCALE (1–5)', () => {
  it('1 · default locale is en when nothing is stored', () => {
    expect(readStoredLocale()).toBe('en')
    expect(currentLocale()).toBe('en')
    expect(FALLBACK_LOCALE).toBe('en')
  })

  it('2 · setLocale switches translations immediately, no reload', async () => {
    function Probe() {
      const { locale, setLocale, t } = useI18n()
      return h('div', null,
        h('span', { 'data-testid': 'loc' }, locale),
        h('span', { 'data-testid': 'label' }, t('nav.overview')),
        h('button', { 'data-testid': 'go-zh', onClick: () => setLocale('zh-CN') }, 'zh'),
      )
    }
    await render(h(Probe), true)
    expect(host.querySelector('[data-testid=label]')!.textContent).toBe('Overview')
    await act(async () => { (host.querySelector('[data-testid=go-zh]') as HTMLButtonElement).click() })
    expect(host.querySelector('[data-testid=loc]')!.textContent).toBe('zh-CN')
    expect(host.querySelector('[data-testid=label]')!.textContent).toBe('概览')
  })

  it('3 · locale persists to localStorage and is picked up by a fresh provider', async () => {
    function Probe() {
      const { setLocale } = useI18n()
      return h('button', { 'data-testid': 'go-ru', onClick: () => setLocale('ru') }, 'ru')
    }
    await render(h(Probe), true)
    await act(async () => { (host.querySelector('[data-testid=go-ru]') as HTMLButtonElement).click() })
    expect(localStorage.getItem('cve-locale')).toBe('ru')
    await act(async () => root!.unmount())
    host.remove()
    expect(readStoredLocale()).toBe('ru')
    await render(h(Probe), true)
    expect(document.documentElement.lang).toBe('ru')
  })

  it('4 · invalid stored locale falls back to en', () => {
    localStorage.setItem('cve-locale', 'xx-NOPE')
    expect(readStoredLocale()).toBe('en')
    localStorage.setItem('cve-locale', '{"evil":true}')
    expect(readStoredLocale()).toBe('en')
  })

  it('5 · switcher lists all 10 locales with their native names', async () => {
    await render(h(LocaleSwitcher), true)
    await act(async () => { (host.querySelector('[data-testid=locale-switcher]') as HTMLButtonElement).click() })
    const buttons = [...host.querySelectorAll('[data-testid^=locale-]')]
      .filter((b) => (b as HTMLElement).dataset.testid !== 'locale-switcher' && (b as HTMLElement).dataset.testid !== 'locale-pop')
    expect(buttons.length).toBe(10)
    for (const code of Object.keys(META)) {
      const btn = host.querySelector(`[data-testid="locale-${code}"]`)
      expect(btn, code).toBeTruthy()
      expect(btn!.textContent).toContain(META[code].nativeName)
      expect(btn!.getAttribute('lang')).toBe(code)
    }
    // direction switcher is colocated (§17)
    expect(host.querySelector('[data-testid=direction-seg]')).toBeTruthy()
    for (const p of ['auto', 'ltr', 'rtl']) expect(host.querySelector(`[data-testid=dir-${p}]`)).toBeTruthy()
  })
})

describe('N3 §28 · DIRECTION (6–12)', () => {
  it('6 · AUTO resolves fa/ar/he to RTL', () => {
    for (const code of ['fa', 'ar', 'he']) expect(resolveDirection(code, 'auto'), code).toBe('rtl')
  })

  it('7 · AUTO resolves en/zh-CN/ru/hi/tr/ko/ja to LTR', () => {
    for (const code of ['en', 'zh-CN', 'ru', 'hi', 'tr', 'ko', 'ja']) expect(resolveDirection(code, 'auto'), code).toBe('ltr')
  })

  it('8 · explicit LTR overrides an RTL locale', () => {
    for (const code of ['fa', 'ar', 'he']) expect(resolveDirection(code, 'ltr'), code).toBe('ltr')
  })

  it('9 · explicit RTL overrides an LTR locale', () => {
    expect(resolveDirection('en', 'rtl')).toBe('rtl')
    expect(resolveDirection('ja', 'rtl')).toBe('rtl')
  })

  it('10 · provider applies lang + dir at the document root', async () => {
    localStorage.setItem('cve-locale', 'he')
    await render(h('div', null, 'x'), true)
    expect(document.documentElement.lang).toBe('he')
    expect(document.documentElement.dir).toBe('rtl')
  })

  it('11 · direction preference persists and survives a locale switch', async () => {
    function Probe() {
      const { setLocale, setDirPref } = useI18n()
      return h('div', null,
        h('button', { 'data-testid': 'rtl', onClick: () => setDirPref('rtl') }, 'rtl'),
        h('button', { 'data-testid': 'zh', onClick: () => setLocale('zh-CN') }, 'zh'),
      )
    }
    await render(h(Probe), true)
    await act(async () => { (host.querySelector('[data-testid=rtl]') as HTMLButtonElement).click() })
    expect(localStorage.getItem('cve-direction')).toBe('rtl')
    expect(document.documentElement.dir).toBe('rtl')
    await act(async () => { (host.querySelector('[data-testid=zh]') as HTMLButtonElement).click() })
    expect(document.documentElement.dir).toBe('rtl') // pref wins over zh-CN's LTR default
    expect(readStoredDirection()).toBe('rtl')
  })

  it('12 · invalid stored direction falls back to auto', () => {
    localStorage.setItem('cve-direction', 'sideways')
    expect(readStoredDirection()).toBe('auto')
  })
})

describe('N3 §28 · TRANSLATION (13–18)', () => {
  it('13 · interpolation replaces {{placeholders}} with values', () => {
    expect(translate('en', 'overview.peopleCount', { count: 7 })).toBe('7 people')
    expect(translate('zh-CN', 'overview.peopleCount', { count: 7 })).toBe(translate('zh-CN', 'overview.peopleCount', { count: 7 }))
    expect(translate('zh-CN', 'overview.peopleCount', { count: 7 })).toContain('7')
  })

  it('14 · missing interpolation values fail safe — no crash, no raw moustache', () => {
    const out = translate('en', 'task.drawerSub', { cycle: 2 }) // time + name missing
    expect(out).not.toContain('{{')
    expect(out).toContain('2')
    expect(() => translate('fa', 'task.drawerSub')).not.toThrow()
  })

  it('15 · unknown key returns the key itself', () => {
    expect(translate('en', 'no.such.key')).toBe('no.such.key')
    expect(translate('ko', 'no.such.key')).toBe('no.such.key')
  })

  it('16 · unsupported locale falls back to en values', () => {
    expect(translate('fr', 'common.you')).toBe(translate('en', 'common.you'))
    expect(translate('ru', 'common.you')).not.toBe(translate('en', 'common.you')) // real translation served
  })

  it('17 · tActive follows the module-level active locale', () => {
    setActiveLocale('ja')
    expect(tActive('settings.language')).toBe(translate('ja', 'settings.language'))
    setActiveLocale('en')
    expect(tActive('settings.language')).toBe('Language')
  })

  it('18 · useI18n works without a provider (no crash, active-locale output)', async () => {
    setActiveLocale('tr')
    function Bare() { const { t } = useI18n(); return h('span', null, t('nav.overview')) }
    await render(h(Bare)) // no I18nProvider
    expect(host.textContent).toBe(translate('tr', 'nav.overview'))
  })
})

describe('N3 §28 · USER CONTENT (19–24)', () => {
  it('19 · task titles render byte-identical under any locale', async () => {
    localStorage.setItem('cve-locale', 'fa')
    persona('u-marcus')
    await render(h(TasksView, { scope: 'all', onOpen: () => {}, onCreate: () => {} }), true)
    expect(document.documentElement.dir).toBe('rtl')
    expect(host.textContent).toContain('Urgent inventory recount — Warehouse B') // user-authored, never translated
  })

  it('20 · user content containers carry dir="auto"', async () => {
    persona('u-marcus')
    await render(h(TasksView, { scope: 'all', onOpen: () => {}, onCreate: () => {} }), true)
    const title = [...host.querySelectorAll('span.t')].find((el) => el.textContent === 'Urgent inventory recount — Warehouse B')
    expect(title?.getAttribute('dir')).toBe('auto')
  })

  it('21 · user names render byte-identical in an RTL locale', async () => {
    localStorage.setItem('cve-locale', 'ar')
    persona('u-marcus')
    await render(h(TasksView, { scope: 'all', onOpen: () => {}, onCreate: () => {} }), true)
    expect(host.textContent).toContain('Marcus Webb')
  })

  it('22 · switching locale never mutates stored state', async () => {
    persona('u-marcus')
    await render(h('div', null, h(Capture), h(LocaleSwitcher)), true)
    const before = JSON.stringify(stateRef())
    await act(async () => { (host.querySelector('[data-testid=locale-switcher]') as HTMLButtonElement).click() })
    await act(async () => { (host.querySelector('[data-testid="locale-he"]') as HTMLButtonElement).click() })
    expect(JSON.stringify(stateRef())).toBe(before)
  })

  it('23 · filenames and mixed-script text pass through LinkText byte-identical', async () => {
    const text = 'variance-report-signed.pdf — ملف عربي — ファイル.pdf'
    await render(h(LinkText, { text }))
    expect(host.textContent).toBe(text)
    expect(host.querySelector('span')!.getAttribute('dir')).toBe('auto')
  })

  it('24 · stored activity prose passes through; only the two N2.3 engine strings localize', () => {
    setActiveLocale('zh-CN')
    expect(localizedHist('fulfillment executors updated')).toBe(translate('zh-CN', 'activity.reward.executorsUpdated'))
    expect(localizedHist('fulfillment executors cleared — management fallback applies'))
      .toBe(translate('zh-CN', 'activity.reward.executorsClearedFallback'))
    const custom = 'Priya wrote this reason herself — 手動メモ'
    expect(localizedHist(custom)).toBe(custom) // untouched
    setActiveLocale('en')
    expect(localizedHist('fulfillment executors updated')).toBe('Fulfillment executors updated')
  })
})

describe('N3 §28 · FORMATTING (25–28)', () => {
  it('25 · numbers are grouped per locale (Intl.NumberFormat)', () => {
    expect(fmtInt(1234, 'en')).toBe('1,234') // en → en-GB
    expect(fmtInt(1234, 'ar')).not.toBe('1,234')
    expect(fmtInt(1234, 'ar')).toBe(new Intl.NumberFormat(intlLocaleOf('ar'), { maximumFractionDigits: 0 }).format(1234))
    expect(fmtInt(1234567, 'en')).toBe('1,234,567')
  })

  it('26 · percents render via Intl percent style', () => {
    expect(fmtPct(45, 'en')).toBe('45%')
    expect(fmtPct(45, 'ar')).toContain('٪')
    expect(fmtPct(100, 'zh-CN')).toContain('100')
  })

  it('27 · dates render via Intl.DateTimeFormat (en → en-GB “1 Oct 2026”)', () => {
    const ts = Date.UTC(2026, 9, 1, 12) // midday — TZ-safe
    expect(fmtDateL(ts, 'en')).toBe('1 Oct 2026')
    expect(fmtDateL(ts, 'ar')).not.toBe('1 Oct 2026')
    expect(fmtDateL(ts, 'ja')).toBe(new Intl.DateTimeFormat('ja-JP', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(ts)))
  })

  it('28 · relative times use the translation keys per locale', () => {
    const now = Date.UTC(2026, 9, 1, 12)
    expect(relTime(now - 5 * 60_000, 'en', now)).toBe('5m ago')
    expect(relTime(now - 5 * 60_000, 'zh-CN', now)).toBe('5 分钟前')
    expect(relTime(now - 3 * 3_600_000, 'ru', now)).toContain('3')
    expect(relTime(now - 30 * 86_400_000, 'en', now)).toBe(fmtDateL(now - 30 * 86_400_000, 'en')) // old → date
  })
})

describe('N3 §28 · FALLBACK (29–30)', () => {
  it('29 · unknown key never crashes — safe key out, dev console warning', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(translate('en', 'totally.unknown.key')).toBe('totally.unknown.key')
    expect(warn).toHaveBeenCalled()
    expect(warn.mock.calls[0][0]).toContain('[i18n]')
  })

  it('30 · garbage locale input resolves to en everywhere', () => {
    setActiveLocale('klingon')
    expect(currentLocale()).toBe('en')
    expect(tActive('nav.overview')).toBe('Overview')
    expect(localeMeta('klingon').code).toBe('en')
    expect(intlLocaleOf('klingon')).toBe(intlLocaleOf('en'))
  })
})

describe('N3 §28 · RTL (31–34)', () => {
  it('31 · Hebrew AUTO puts dir="rtl" on the root', async () => {
    localStorage.setItem('cve-locale', 'he')
    await render(h('div', null, 'x'), true)
    expect(document.documentElement.dir).toBe('rtl')
  })

  it('32 · switching back to English restores dir="ltr"', async () => {
    localStorage.setItem('cve-locale', 'he')
    function Probe() {
      const { setLocale } = useI18n()
      return h('button', { 'data-testid': 'en', onClick: () => setLocale('en') }, 'en')
    }
    await render(h(Probe), true)
    expect(document.documentElement.dir).toBe('rtl')
    await act(async () => { (host.querySelector('[data-testid=en]') as HTMLButtonElement).click() })
    expect(document.documentElement.dir).toBe('ltr')
    expect(document.documentElement.lang).toBe('en')
  })

  it('33 · direction is independent of language — English UI in RTL', async () => {
    localStorage.setItem('cve-locale', 'en')
    localStorage.setItem('cve-direction', 'rtl')
    function Probe() { const { t } = useI18n(); return h('span', null, t('nav.overview')) }
    await render(h(Probe), true)
    expect(document.documentElement.dir).toBe('rtl')
    expect(host.textContent).toBe('Overview') // English text, RTL shell
  })

  it('34 · user content keeps dir="auto" inside an RTL root', async () => {
    localStorage.setItem('cve-locale', 'ar')
    await render(h(LinkText, { text: 'English task title inside Arabic UI' }), true)
    expect(document.documentElement.dir).toBe('rtl')
    const span = host.querySelector('span[dir="auto"]')
    expect(span).toBeTruthy()
    expect(span!.textContent).toBe('English task title inside Arabic UI')
  })
})

describe('N3 §28 · LINKS (35–37)', () => {
  it('35 · linkifier still linkifies www. URLs inside localized rendering', async () => {
    await render(h(LinkText, { text: 'docs at www.example.com/guide.' }))
    const a = host.querySelector('a')
    expect(a?.getAttribute('href')).toBe('https://www.example.com/guide')
  })

  it('36 · bare domains linkified; dotted non-URLs untouched', () => {
    expect(anchors('see example.com for details')).toEqual([{ href: 'https://example.com', text: 'example.com' }])
    for (const t of ['bumped to v1.2.3 today', 'open file.py then note.txt']) expect(anchors(t)).toEqual([])
  })

  it('37 · links inside RTL text stay bidi-safe and clickable', async () => {
    await render(h(LinkText, { text: 'راجع https://example.com/تقرير للتفاصيل' }))
    const a = host.querySelector('a')
    expect(a).toBeTruthy()
    expect(a!.getAttribute('href')).toContain('https://example.com/')
    expect(host.querySelector('span')!.getAttribute('dir')).toBe('auto')
    expect(host.textContent).toBe('راجع https://example.com/تقرير للتفاصيل')
  })
})

describe('N3 §28 · PARITY (38–40)', () => {
  it('38 · all 10 bundled dictionaries expose the identical key set', () => {
    for (const [code, dict] of Object.entries(DICTS)) {
      expect(Object.keys(dict).sort(), code).toEqual(Object.keys(EN).sort())
    }
  })

  it('39 · placeholder parity across all bundles', () => {
    const ph = (s: string) => (s.match(/\{\{\s*[\w.]+\s*\}\}/g) ?? []).sort()
    for (const [code, dict] of Object.entries(DICTS)) {
      for (const k of Object.keys(EN)) expect(ph(dict[k]), `${code}:${k}`).toEqual(ph(EN[k]))
    }
  })

  it('40 · locale metadata covers exactly the 10 supported locales, en fallback', () => {
    expect(LOCALES.map((l) => l.code).sort()).toEqual(['ar', 'en', 'fa', 'he', 'hi', 'ja', 'ko', 'ru', 'tr', 'zh-CN'])
    for (const l of LOCALES) {
      expect((l as { fallback?: string }).fallback ?? 'en').toBe('en')
      expect(['ltr', 'rtl']).toContain(l.defaultDirection)
    }
    expect(LOCALES.filter((l) => l.defaultDirection === 'rtl').map((l) => l.code).sort()).toEqual(['ar', 'fa', 'he'])
  })
})
