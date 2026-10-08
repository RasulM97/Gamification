# Localization workflow and approved terminology

Canonical topic document at code baseline `f1600b580a540b55fbb8e62e1e7caa47962c313a`.
Authority: Source Code → DB/Migrations → Explicit Contracts → Graphify.
Phase-specific measurements below are historical evidence, not tests rerun by this sweep.

## Contents

- [workflow](#contract-localization-workflow)
- [CVE Localization UX Review v1.3](#contract-localization-cve-localization-ux-review-v1-3)

<a id="contract-localization-workflow"></a>
<a id="contract-localization-workflow-localization-workflow-n3"></a>
## Localization Workflow (N3)

How UI text flows from code to the 10 locales, and the rules every change must
keep. Runtime: `src/i18n/index.tsx` (zero-dependency internal layer, §3).
Resources: `src/i18n/locale-meta.json` + `src/i18n/locales/*.json` (§2).

<a id="contract-localization-workflow-supported-locales--fixed-set"></a>
### Supported locales — fixed set

`en, zh-CN, ru, hi, fa, ar, he, tr, ko, ja`. **Do not add locales** (§1).
`en` is the canonical fallback: every lookup resolves locale → en → the key
itself (dev-only console warning), so a missing translation can never crash
the UI (§22).

<a id="contract-localization-workflow-adding-or-changing-a-user-facing-string"></a>
### Adding or changing a user-facing string

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

<a id="contract-localization-workflow-locale-aware-formatting-1315"></a>
### Locale-aware formatting (§13–§15)

- Dates/times: `fmtDateL` / `fmtDateTimeL` (Intl.DateTimeFormat; en → en-GB).
- Relative times: `relTime` (translation keys `relative.*`, date past 6 days).
- Numbers, coin amounts, counts: `fmtNum` / `fmtInt`. Percents: `fmtPct`
  (input is 0–100, product convention). **No currency formatting** — Coins
  are a unit, rendered with the `Coin` component.
- Backend timestamps and stored values are never reformatted at rest;
  formatting is display-only.

<a id="contract-localization-workflow-direction-5-1719"></a>
### Direction (§5, §17–§19)

- Preference is independent of language: `auto` | `ltr` | `rtl`, stored in
  localStorage (`cve-direction`), applied as `dir=` on `<html>`.
- AUTO resolves from locale metadata: fa/ar/he → RTL, everything else → LTR.
- Never insert Unicode bidi control characters. Mixed-direction content uses
  `dir="auto"` and bidi-safe CSS (logical properties).
- Mirror only truly directional icons; layout is logical-property based.

<a id="contract-localization-workflow-the-translation-boundary-6--do-not-cross-it"></a>
### The translation boundary (§6) — do not cross it

Never translate, rewrite, or "fix" user-authored content: task titles and
descriptions, submission notes, decline/return/reject/cancel reasons, review
notes, handoff reasons, reward names and descriptions, category names, user
and company names, filenames, URLs. Render them verbatim inside
`dir="auto"` containers (`LinkText`, `ClampedText`, or an explicit
`dir="auto"` span). A locale switch must never mutate stored state — that is
tested (n3 case 22).

<a id="contract-localization-workflow-domain-enums-stay-canonical-8"></a>
### Domain enums stay canonical (§8)

`APPROVED`, `IN_PROGRESS`, `URGENT`, `EMPLOYEES`, `BOTH`, ledger types, etc.
remain language-neutral codes end to end. The UI maps codes to keys at render
time (`task.status.*`, `task.priority.*`, `wallet.type.*`, …). No translated
enum is ever stored; no API contract changes.

<a id="contract-localization-workflow-activity--notification-history-10-debt"></a>
### Activity & notification history (§10 debt)

Stored activity/notification prose is **append-only history and is never
rewritten**. Old human-readable strings render as-is in `dir="auto"`
containers. Display-only exception: the two governance strings the N2.3
engine writes verbatim are recognized at render time by `localizedHist()`
(src/ui.tsx) and shown through `activity.reward.executorsUpdated` /
`activity.reward.executorsClearedFallback`. New engine-generated user-facing
events should emit structured events that the UI renders through localized
templates; a backend redesign is explicitly out of scope.

<a id="contract-localization-workflow-demo--server-parity-7-25"></a>
### Demo ↔ server parity (§7, §25)

The i18n layer is shared by both runtimes; locales are statically bundled,
identical in demo and server. Demo mode still makes zero product API
requests. Language/direction preferences live only in the browser
(localStorage `cve-locale` / `cve-direction`); there is no backend
persistence and no DB migration (§4, §27).

<a id="contract-localization-workflow-translator-notes"></a>
### Translator notes

- Keep the approved per-locale terminology from the v1.3 UX pass
  (see the approved terminology section in this document): e.g. Coins → 积分币 / монеты /
  عملات / コイン / 코인; task pool/marketplace wording per locale.
- Buttons are actions, status labels are current states, help text is concise
  native guidance.
- Approved technical tokens stay as-is in every locale: CVE, URL, MB, API,
  JSON, JSONL, UAT, and formula fragments like `ceil(reward × % × 2) / 2`.


<a id="contract-localization-cve-localization-ux-review-v1-3"></a>
<a id="contract-localization-cve-localization-ux-review-v1-3-cve-localization-ux-review-v13"></a>
## CVE Localization UX Review v1.3

Contextual UX language pass for eight non-English locales. `en.json` remains the key source; the manually approved `fa.json` is unchanged.

<a id="contract-localization-cve-localization-ux-review-v1-3-zh-cn"></a>
### zh-CN
- Total keys: 344
- Contextual rewrites: 85
- English leakage: 0
- Placeholder validation: PASS
- JSON validation: PASS
- Key parity: PASS
- Major terminology decisions:
  - Task pool → 可领取任务 / 任务池, never a shopping marketplace
  - Redemption → 奖励申请; Fulfillment → 奖励发放
  - Claim task → 领取任务; Rework → 需要修改

<a id="contract-localization-cve-localization-ux-review-v1-3-ar"></a>
### ar
- Total keys: 344
- Contextual rewrites: 90
- English leakage: 0
- Placeholder validation: PASS
- JSON validation: PASS
- Key parity: PASS
- Major terminology decisions:
  - Task pool → المهام المتاحة
  - Redemption → طلب مكافأة; Fulfillment → تنفيذ المكافأة
  - Claim → استلام المهمة; Rework → يحتاج إلى تعديل

<a id="contract-localization-cve-localization-ux-review-v1-3-ja"></a>
### ja
- Total keys: 344
- Contextual rewrites: 87
- English leakage: 0
- Placeholder validation: PASS
- JSON validation: PASS
- Key parity: PASS
- Major terminology decisions:
  - Task pool → 受け取り可能なタスク
  - Redemption → リワード申請; Fulfillment → リワード提供
  - Claim → タスクを引き受ける; Rework → 修正が必要

<a id="contract-localization-cve-localization-ux-review-v1-3-tr"></a>
### tr
- Total keys: 344
- Contextual rewrites: 95
- English leakage: 0
- Placeholder validation: PASS
- JSON validation: PASS
- Key parity: PASS
- Major terminology decisions:
  - Task pool → Uygun görevler / görev havuzu
  - Redemption → Ödül talebi; Fulfillment → Ödülün teslimi
  - Claim → Görevi al; Rework → Düzenleme gerekiyor

<a id="contract-localization-cve-localization-ux-review-v1-3-ru"></a>
### ru
- Total keys: 344
- Contextual rewrites: 75
- English leakage: 0
- Placeholder validation: PASS
- JSON validation: PASS
- Key parity: PASS
- Major terminology decisions:
  - Task pool → Доступные задачи
  - Redemption → Запрос награды; Fulfillment → Выдача награды
  - Claim → Взять задачу; Rework → Требуется доработка

<a id="contract-localization-cve-localization-ux-review-v1-3-he"></a>
### he
- Total keys: 344
- Contextual rewrites: 105
- English leakage: 0
- Placeholder validation: PASS
- JSON validation: PASS
- Key parity: PASS
- Major terminology decisions:
  - Task pool → משימות זמינות
  - Redemption → בקשת פרס; Fulfillment → מסירת הפרס
  - Claim → לקחת משימה; Rework → נדרש תיקון

<a id="contract-localization-cve-localization-ux-review-v1-3-ko"></a>
### ko
- Total keys: 344
- Contextual rewrites: 85
- English leakage: 0
- Placeholder validation: PASS
- JSON validation: PASS
- Key parity: PASS
- Major terminology decisions:
  - Task pool → 가능한 작업 / 작업 풀
  - Redemption → 보상 신청; Fulfillment → 보상 지급
  - Claim → 작업 가져오기; Rework → 수정 필요

<a id="contract-localization-cve-localization-ux-review-v1-3-hi"></a>
### hi
- Total keys: 344
- Contextual rewrites: 106
- English leakage: 0
- Placeholder validation: PASS
- JSON validation: PASS
- Key parity: PASS
- Major terminology decisions:
  - Task pool → उपलब्ध टास्क / टास्क पूल
  - Redemption → रिवॉर्ड अनुरोध; Fulfillment → रिवॉर्ड डिलीवरी
  - Claim → टास्क लें; Rework → सुधार की ज़रूरत

<a id="contract-localization-cve-localization-ux-review-v1-3-unchanged-locales"></a>
### Unchanged locales
- en.json byte-for-byte unchanged: PASS
- fa.json byte-for-byte unchanged: PASS

<a id="contract-localization-cve-localization-ux-review-v1-3-qa-summary"></a>
### QA summary
- zh-CN: JSON=PASS, keys=PASS, placeholders=PASS, empty=0, English leakage=0, raw enum leakage=0, fallback prefixes=0
- ar: JSON=PASS, keys=PASS, placeholders=PASS, empty=0, English leakage=0, raw enum leakage=0, fallback prefixes=0
- ja: JSON=PASS, keys=PASS, placeholders=PASS, empty=0, English leakage=0, raw enum leakage=0, fallback prefixes=0
- tr: JSON=PASS, keys=PASS, placeholders=PASS, empty=0, English leakage=0, raw enum leakage=0, fallback prefixes=0
- ru: JSON=PASS, keys=PASS, placeholders=PASS, empty=0, English leakage=0, raw enum leakage=0, fallback prefixes=0
- he: JSON=PASS, keys=PASS, placeholders=PASS, empty=0, English leakage=0, raw enum leakage=0, fallback prefixes=0
- ko: JSON=PASS, keys=PASS, placeholders=PASS, empty=0, English leakage=0, raw enum leakage=0, fallback prefixes=0
- hi: JSON=PASS, keys=PASS, placeholders=PASS, empty=0, English leakage=0, raw enum leakage=0, fallback prefixes=0

<a id="history"></a>
## Historical localization evidence

The v1.1/v1.3 leakage and placeholder audits were PASS at their historical key sets; 344/348/779 counts do not describe the current dictionary. Key/placeholder parity is enforced against `src/i18n/locales/en.json` by `src/i18n/parity.test.ts`, not by an old report count. Historical JSON evidence and key manifest are retained for instruction compatibility. Approved terminology above is retained; use current dictionaries as source when counts or keys disagree.

Preserve user-authored content, language-neutral stored enums and original history. New generated events use structured parameters/localized presentation; old prose is not rewritten. N3.2 structured activity history is not a substitute for Canonical Event/economic provenance. Logical spacing, native RTL composition and isolated LTR values avoid bidi corruption. Run locale parity whenever adding UI strings.
