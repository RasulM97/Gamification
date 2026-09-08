# Strict Untranslated / English Leakage Check — v1.1

Acceptance criterion: **0 suspicious English leakage remaining** in every non-English locale.

The validation rejects:

- exact English fallback values;
- localized fallback wrappers such as `系统：...`, `سیستم: ...`, `النظام: ...`, `システム: ...`, and equivalents;
- raw canonical enums used as translated display values;
- unapproved Latin/English tokens in non-Latin locales after removing runtime placeholders;
- suspicious overlap with English source wording in Turkish;
- empty translations;
- placeholder drift;
- key-set drift.

Approved technical tokens: `CVE`, `URL`, `MB`, `API`, `JSON`, `JSONL`, `UAT`.

Result: **PASS** — all nine non-English locales have zero remaining leakage under the strict scan.
