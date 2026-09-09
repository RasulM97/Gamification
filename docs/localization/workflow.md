# Localization Workflow (N3)

How UI text flows from code to the 10 locales, and the rules every change must
keep. Runtime: `src/i18n/index.tsx` (zero-dependency internal layer, §3).
Resources: `src/i18n/locale-meta.json` + `src/i18n/locales/*.json` (§2).

## Supported locales — fixed set

`en, zh-CN, ru, hi, fa, ar, he, tr, ko, ja`. **Do not add locales** (§1).
`en` is the canonical fallback: every lookup resolves locale → en → the key
itself (dev-only console warning), so a missing translation can never crash
the UI (§22).

## Adding or changing a user-facing string

1. **Never hard-code a production string in a localized surface.** Add a flat
   dotted key (`section.subsection.name`) to `src/i18n/locales/en.json` first.
2. Add the same key to all 9 other locale files. Keep every file valid JSON,
   2-space indent, keys sorted, trailing newline.
3. **Placeholder parity is mandatory.** If the en value contains
   `{{name}}`, every locale must contain exactly `{{name}}` — never renamed,
   never reordered into a different token, never dropped (§11). Interpolation
   fails safe (missing value renders empty + dev warning).
4. Update `docs/localization/key-manifest.json` (totalKeys + sorted key list).
5. Run the guards — they **fail** on any break (§23):
   - `src/i18n/parity.test.ts` — valid JSON, identical key sets, no empty
     values, placeholder parity, meta covers exactly the 10 locales.
   - `src/n3.test.tsx` cases 38–40 — bundled-dictionary parity.
6. Use the key via `const { t } = useI18n()` → `t('your.key')`. Inside views
   that map over tasks, alias the translator (`tr`) so it is not shadowed by
   a task named `t`. Non-React helpers use `tActive(...)` / `translate(...)`.

## Locale-aware formatting (§13–§15)

- Dates/times: `fmtDateL` / `fmtDateTimeL` (Intl.DateTimeFormat; en → en-GB).
- Relative times: `relTime` (translation keys `relative.*`, date past 6 days).
- Numbers, coin amounts, counts: `fmtNum` / `fmtInt`. Percents: `fmtPct`
  (input is 0–100, product convention). **No currency formatting** — Coins
  are a unit, rendered with the `Coin` component.
- Backend timestamps and stored values are never reformatted at rest;
  formatting is display-only.

## Direction (§5, §17–§19)

- Preference is independent of language: `auto` | `ltr` | `rtl`, stored in
  localStorage (`cve-direction`), applied as `dir=` on `<html>`.
- AUTO resolves from locale metadata: fa/ar/he → RTL, everything else → LTR.
- Never insert Unicode bidi control characters. Mixed-direction content uses
  `dir="auto"` and bidi-safe CSS (logical properties).
- Mirror only truly directional icons; layout is logical-property based.

## The translation boundary (§6) — do not cross it

Never translate, rewrite, or "fix" user-authored content: task titles and
descriptions, submission notes, decline/return/reject/cancel reasons, review
notes, handoff reasons, reward names and descriptions, category names, user
and company names, filenames, URLs. Render them verbatim inside
`dir="auto"` containers (`LinkText`, `ClampedText`, or an explicit
`dir="auto"` span). A locale switch must never mutate stored state — that is
tested (n3 case 22).

## Domain enums stay canonical (§8)

`APPROVED`, `IN_PROGRESS`, `URGENT`, `EMPLOYEES`, `BOTH`, ledger types, etc.
remain language-neutral codes end to end. The UI maps codes to keys at render
time (`task.status.*`, `task.priority.*`, `wallet.type.*`, …). No translated
enum is ever stored; no API contract changes.

## Activity & notification history (§10 debt)

Stored activity/notification prose is **append-only history and is never
rewritten**. Old human-readable strings render as-is in `dir="auto"`
containers. Display-only exception: the two governance strings the N2.3
engine writes verbatim are recognized at render time by `localizedHist()`
(src/ui.tsx) and shown through `activity.reward.executorsUpdated` /
`activity.reward.executorsClearedFallback`. New engine-generated user-facing
events should emit structured events that the UI renders through localized
templates; a backend redesign is explicitly out of scope.

## Demo ↔ server parity (§7, §25)

The i18n layer is shared by both runtimes; locales are statically bundled,
identical in demo and server. Demo mode still makes zero product API
requests. Language/direction preferences live only in the browser
(localStorage `cve-locale` / `cve-direction`); there is no backend
persistence and no DB migration (§4, §27).

## Translator notes

- Keep the approved per-locale terminology from the v1.3 UX pass
  (see `CVE_Localization_UX_Review_v1.3.md`): e.g. Coins → 积分币 / монеты /
  عملات / コイン / 코인; task pool/marketplace wording per locale.
- Buttons are actions, status labels are current states, help text is concise
  native guidance.
- Approved technical tokens stay as-is in every locale: CVE, URL, MB, API,
  JSON, JSONL, UAT, and formula fragments like `ceil(reward × % × 2) / 2`.
