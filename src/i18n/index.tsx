// ─────────────────────────────────────────────────────────────────────────────
// CVE i18n runtime — minimal internal translation utility (N3).
//
// - 10 locales, statically bundled from src/i18n/locales/*.json (no runtime fetch).
// - en is the canonical fallback (locale → en → key itself, never undefined).
// - Interpolation uses {{name}} placeholders; missing values fail safe ('').
// - Direction preference (auto/ltr/rtl) is independent of language; AUTO resolves
//   from locale-meta defaultDirection (fa/ar/he → rtl).
// - Module-level `activeLocale` lets non-React helpers (ui.tsx) localize without
//   changing their signatures; the provider keeps it in sync.
// - No user-authored content passes through here — this layer translates
//   system-owned UI strings only.
// ─────────────────────────────────────────────────────────────────────────────
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { I18N_DEV } from './dev';
import meta from './locale-meta.json';
import en from './locales/en.json';
import zhCN from './locales/zh-CN.json';
import ru from './locales/ru.json';
import hi from './locales/hi.json';
import fa from './locales/fa.json';
import ar from './locales/ar.json';
import he from './locales/he.json';
import tr from './locales/tr.json';
import ko from './locales/ko.json';
import ja from './locales/ja.json';

export type Direction = 'ltr' | 'rtl';
export type DirectionPref = 'auto' | 'ltr' | 'rtl';

export interface LocaleMeta {
  code: string;
  nativeName: string;
  englishName: string;
  defaultDirection: Direction;
  supportedDirections: DirectionPref[];
  intlLocale: string;
}

type Dict = Record<string, string>;

// locale-meta.json is keyed by locale code; each entry carries fallback: "en".
const META = meta as unknown as Record<string, LocaleMeta>;
export const LOCALES: LocaleMeta[] = Object.values(META);
export const FALLBACK_LOCALE = 'en';

const META_BY_CODE: Record<string, LocaleMeta> = Object.fromEntries(LOCALES.map((l) => [l.code, l]));

const BUNDLES: Record<string, Dict> = {
  en: en as Dict,
  'zh-CN': zhCN as Dict,
  ru: ru as Dict,
  hi: hi as Dict,
  fa: fa as Dict,
  ar: ar as Dict,
  he: he as Dict,
  tr: tr as Dict,
  ko: ko as Dict,
  ja: ja as Dict,
};

const LOCALE_KEY = 'cve-locale';
const DIRECTION_KEY = 'cve-direction';

function storageGet(key: string): string | null {
  try {
    return typeof localStorage !== 'undefined' ? localStorage.getItem(key) : null;
  } catch {
    return null;
  }
}

function storageSet(key: string, value: string): void {
  try {
    if (typeof localStorage !== 'undefined') localStorage.setItem(key, value);
  } catch {
    /* storage unavailable — session-only preference */
  }
}

export function isSupportedLocale(code: string | null | undefined): code is string {
  return !!code && code in BUNDLES;
}

export function readStoredLocale(): string {
  const stored = storageGet(LOCALE_KEY);
  return isSupportedLocale(stored) ? stored : FALLBACK_LOCALE;
}

export function readStoredDirection(): DirectionPref {
  const stored = storageGet(DIRECTION_KEY);
  return stored === 'ltr' || stored === 'rtl' || stored === 'auto' ? stored : 'auto';
}

export function localeMeta(code: string): LocaleMeta {
  return META_BY_CODE[code] ?? META_BY_CODE[FALLBACK_LOCALE];
}

export function intlLocaleOf(code: string): string {
  return localeMeta(code).intlLocale;
}

export function resolveDirection(locale: string, pref: DirectionPref): Direction {
  if (pref === 'ltr' || pref === 'rtl') return pref;
  return localeMeta(locale).defaultDirection;
}

// Module-level active locale — read by non-React formatting helpers (ui.tsx).
// Initialised from storage so output is correct even before the provider mounts.
let activeLocale: string = readStoredLocale();

export function currentLocale(): string {
  return activeLocale;
}

function devWarn(message: string): void {
  try {
    if (I18N_DEV) console.warn(`[i18n] ${message}`);
  } catch {
    /* non-Vite environment */
  }
}

const PLACEHOLDER = /\{\{\s*([\w.]+)\s*\}\}/g;

export function interpolate(template: string, params?: Record<string, string | number>): string {
  if (!params) return template;
  return template.replace(PLACEHOLDER, (raw, name: string) => {
    const value = params[name];
    if (value === undefined || value === null) {
      devWarn(`missing value for placeholder "${name}" in "${template}"`);
      return '';
    }
    return String(value);
  });
}

/** Core translation: requested locale → en fallback → the key itself. Never throws. */
export function translate(locale: string, key: string, params?: Record<string, string | number>): string {
  const dict = BUNDLES[locale] ?? BUNDLES[FALLBACK_LOCALE];
  let template = dict[key];
  if (template === undefined && locale !== FALLBACK_LOCALE) {
    template = BUNDLES[FALLBACK_LOCALE][key];
    if (template !== undefined) devWarn(`missing key "${key}" for locale "${locale}" — used en fallback`);
  }
  if (template === undefined) {
    devWarn(`unknown key "${key}"`);
    return key;
  }
  return interpolate(template, params);
}

/** translate() bound to the module-level active locale (for non-React helpers). */
export function tActive(key: string, params?: Record<string, string | number>): string {
  return translate(activeLocale, key, params);
}

// ── Locale-aware formatting helpers (module-level; bound to active locale) ─────

export function fmtNum(n: number, locale: string = activeLocale): string {
  return new Intl.NumberFormat(intlLocaleOf(locale), { maximumFractionDigits: 1 }).format(n);
}

export function fmtInt(n: number, locale: string = activeLocale): string {
  return new Intl.NumberFormat(intlLocaleOf(locale), { maximumFractionDigits: 0 }).format(n);
}

/** p is 0–100 (product convention); rendered via Intl percent style. */
export function fmtPct(p: number, locale: string = activeLocale): string {
  return new Intl.NumberFormat(intlLocaleOf(locale), { style: 'percent', maximumFractionDigits: 0 }).format(p / 100);
}

export function fmtDateL(d: Date | number | string, locale: string = activeLocale): string {
  return new Intl.DateTimeFormat(intlLocaleOf(locale), { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(d));
}

export function fmtDateTimeL(d: Date | number | string, locale: string = activeLocale): string {
  return new Intl.DateTimeFormat(intlLocaleOf(locale), {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(d));
}

/** Relative time for recent timestamps; falls back to a locale date past 6 days. */
export function relTime(ts: number, locale: string = activeLocale, now: number = Date.now()): string {
  const s = Math.max(1, Math.round((now - ts) / 1000));
  if (s < 60) return translate(locale, 'relative.secondsAgo', { count: s });
  const m = Math.round(s / 60);
  if (m < 60) return translate(locale, 'relative.minutesAgo', { count: m });
  const h = Math.round(m / 60);
  if (h < 24) return translate(locale, 'relative.hoursAgo', { count: h });
  const d = Math.round(h / 24);
  if (d < 7) return translate(locale, 'relative.daysAgo', { count: d });
  return fmtDateL(ts, locale);
}

// ── React integration ─────────────────────────────────────────────────────────

export interface I18n {
  locale: string;
  setLocale: (code: string) => void;
  dirPref: DirectionPref;
  setDirPref: (pref: DirectionPref) => void;
  direction: Direction;
  t: (key: string, params?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18n | null>(null);

function applyDocumentAttrs(locale: string, direction: Direction): void {
  try {
    if (typeof document !== 'undefined') {
      document.documentElement.lang = locale;
      document.documentElement.dir = direction;
    }
  } catch {
    /* non-DOM environment */
  }
}

export function setActiveLocale(code: string): void {
  activeLocale = isSupportedLocale(code) ? code : FALLBACK_LOCALE;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<string>(readStoredLocale);
  const [dirPref, setDirPrefState] = useState<DirectionPref>(readStoredDirection);
  const direction = resolveDirection(locale, dirPref);

  /* Sync the module-level active locale DURING render: tActive-bound helpers
     (ago, localizedHist, fmtDay…) read it inside the same render pass — an
     effect would leave them one render stale after a locale switch. */
  setActiveLocale(locale);

  useEffect(() => {
    applyDocumentAttrs(locale, direction);
  }, [locale, direction]);

  const setLocale = useCallback((code: string) => {
    const next = isSupportedLocale(code) ? code : FALLBACK_LOCALE;
    storageSet(LOCALE_KEY, next);
    setLocaleState(next);
  }, []);

  const setDirPref = useCallback((pref: DirectionPref) => {
    storageSet(DIRECTION_KEY, pref);
    setDirPrefState(pref);
  }, []);

  const t = useCallback((key: string, params?: Record<string, string | number>) => translate(locale, key, params), [locale]);

  const value = useMemo<I18n>(
    () => ({ locale, setLocale, dirPref, setDirPref, direction, t }),
    [locale, setLocale, dirPref, setDirPref, direction, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

/**
 * useI18n — works with or without a provider. Without one (legacy tests,
 * non-React callers) it falls back to the module-level active locale so output
 * stays correct instead of crashing.
 */
export function useI18n(): I18n {
  const ctx = useContext(I18nContext);
  const t = useCallback((key: string, params?: Record<string, string | number>) => translate(activeLocale, key, params), []);
  return useMemo<I18n>(() => {
    if (ctx) return ctx;
    return {
      locale: activeLocale,
      setLocale: (code: string) => {
        const next = isSupportedLocale(code) ? code : FALLBACK_LOCALE;
        storageSet(LOCALE_KEY, next);
        setActiveLocale(next);
        applyDocumentAttrs(next, resolveDirection(next, readStoredDirection()));
      },
      dirPref: readStoredDirection(),
      setDirPref: (pref: DirectionPref) => {
        storageSet(DIRECTION_KEY, pref);
        applyDocumentAttrs(activeLocale, resolveDirection(activeLocale, pref));
      },
      direction: resolveDirection(activeLocale, readStoredDirection()),
      t,
    };
  }, [ctx, t]);
}
