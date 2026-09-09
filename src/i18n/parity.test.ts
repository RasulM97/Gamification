/* N3 §23 — automated key-parity validation.
   Reads the locale resources FROM DISK (not the bundled imports) so this test
   fails the moment any locale file is edited into an inconsistent state:
   - every locale file is valid JSON
   - every locale has exactly the same key set as en (no missing, no extra)
   - no empty / whitespace-only values anywhere
   - placeholder parity: every value uses exactly the {{placeholders}} en uses
   - locale-meta covers exactly the 10 supported locales with en fallback
   Run as part of `npm test` — a broken locale file breaks the build gate. */
import { describe, expect, it } from 'vitest'

const EXPECTED_LOCALES = ['en', 'zh-CN', 'ru', 'hi', 'fa', 'ar', 'he', 'tr', 'ko', 'ja']

/* Raw file contents via the bundler — JSON.parse below validates each file,
   and an unparseable edit fails this test immediately. */
const RAW_LOCALES = import.meta.glob('./locales/*.json', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>
const RAW_META = import.meta.glob('./locale-meta.json', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>

function readJson(rel: string): Record<string, unknown> {
  const raw = RAW_LOCALES[`./${rel}`] ?? RAW_META[`./${rel}`]
  expect(raw, `${rel} must exist`).toBeTruthy()
  return JSON.parse(raw)
}

const placeholders = (s: string): string[] => (s.match(/\{\{\s*[\w.]+\s*\}\}/g) ?? []).sort()

describe('N3 §23 locale key parity', () => {
  const dicts: Record<string, Record<string, string>> = {}
  for (const code of EXPECTED_LOCALES) {
    dicts[code] = readJson(`locales/${code}.json`) as Record<string, string>
  }
  const enKeys = Object.keys(dicts.en).sort()

  it('all 10 locale files exist and are valid JSON dictionaries', () => {
    for (const code of EXPECTED_LOCALES) {
      expect(typeof dicts[code], code).toBe('object')
      expect(Object.keys(dicts[code]).length, code).toBeGreaterThan(0)
      for (const [k, v] of Object.entries(dicts[code])) {
        expect(typeof v, `${code}:${k}`).toBe('string')
      }
    }
  })

  it('every locale has exactly the en key set — no missing, no extra', () => {
    for (const code of EXPECTED_LOCALES) {
      const keys = Object.keys(dicts[code])
      const missing = enKeys.filter((k) => !(k in dicts[code]))
      const extra = keys.filter((k) => !(k in dicts.en))
      expect(missing, `${code} missing`).toEqual([])
      expect(extra, `${code} extra`).toEqual([])
      expect(keys.length, code).toBe(enKeys.length)
    }
  })

  it('no empty or whitespace-only values in any locale', () => {
    for (const code of EXPECTED_LOCALES) {
      for (const [k, v] of Object.entries(dicts[code])) {
        expect(v.trim().length, `${code}:${k}`).toBeGreaterThan(0)
      }
    }
  })

  it('placeholder parity — every value uses exactly the en placeholders', () => {
    for (const code of EXPECTED_LOCALES) {
      for (const k of enKeys) {
        expect(placeholders(dicts[code][k]), `${code}:${k}`).toEqual(placeholders(dicts.en[k]))
      }
    }
  })

  it('locale-meta covers exactly the 10 supported locales', () => {
    const meta = readJson('locale-meta.json') as Record<string, {
      code: string; nativeName: string; englishName: string;
      defaultDirection: string; supportedDirections: string[];
      intlLocale: string; fallback: string
    }>
    expect(Object.keys(meta).sort()).toEqual([...EXPECTED_LOCALES].sort())
    for (const code of EXPECTED_LOCALES) {
      const m = meta[code]
      expect(m.code, code).toBe(code)
      expect(m.nativeName.trim().length, code).toBeGreaterThan(0)
      expect(m.intlLocale.trim().length, code).toBeGreaterThan(0)
      expect(m.fallback, code).toBe('en')
      expect(m.supportedDirections, code).toContain('auto')
    }
    // §5 AUTO resolution: fa/ar/he default to RTL, everything else LTR
    for (const code of ['fa', 'ar', 'he']) expect(meta[code].defaultDirection, code).toBe('rtl')
    for (const code of ['en', 'zh-CN', 'ru', 'hi', 'tr', 'ko', 'ja']) expect(meta[code].defaultDirection, code).toBe('ltr')
  })
})
