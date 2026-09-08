# CVE Localization Pack v1.3

Canonical localization resources for Corporate Virtual Economy (CVE), repaired against the current `main` branch vocabulary.

## Coverage

- 10 locales: en, zh-CN, ru, hi, fa, ar, he, tr, ko, ja
- 344 canonical translation keys per locale
- English (`en.json`) is the source-of-truth key set
- Default RTL locales: fa, ar, he
- Direction remains independent from language and supports `auto`, `ltr`, and `rtl`

## Translation boundary

Only system-owned UI text is localized. User-authored content must remain exactly as entered, including task titles/descriptions, submission text, handoff/review notes, reward names/descriptions, custom category/organization names, user/company names, file names, and URLs.

## Backend/domain boundary

Canonical backend values such as `APPROVED`, `IN_PROGRESS`, `URGENT`, `EMPLOYEES`, and `BOTH` remain language-neutral internal codes. Locale files contain translated display labels only.

## v1.3 repair guarantees

- No localized `System:`-style fallback prefixes
- No raw English UI sentence fallback in non-English locales
- No raw backend enum display values in non-English locales
- Identical key sets across all 10 locales
- Placeholder parity with English and runtime audit against repository usage
- No empty values
- Strict English-leakage scan: 0 remaining for all 9 non-English locales, except approved technical tokens (`CVE`, `URL`, `MB`, `API`, `JSON`, `JSONL`, `UAT`)

See `validation/untranslated-check.md`, `validation/placeholder-audit.md`, and `validation/implementation-notes.md`.


## v1.3 UX language quality pass

Version 1.2 reviews the nine non-English locales by product workflow rather than by English source order. Marketplace terminology was localized as a shared pool of open work rather than a commercial marketplace. Buttons were rewritten as actions, status labels as current states, and help text as concise native guidance. User-authored content, backend enums, business rules, and runtime placeholders remain unchanged.

## N2.3 localization resource update

Added four Reward fulfillment workflow strings to all 10 locales:

- `reward.fulfillment.managementFallback`
- `reward.fulfillment.approvedBy`
- `activity.reward.executorsUpdated`
- `activity.reward.executorsClearedFallback`

All prior reviewed translation values were preserved. Canonical key count: **348**.
