# Implementation Notes — v1.1

## Mandatory future-feature rule

Whenever Kimi or another implementation agent adds a production feature:

- New hard-coded production UI strings are not allowed.
- Add the English localization key first.
- Add the same key to all nine non-English locale files before delivery.
- Missing-key tests must fail delivery.
- User-authored content remains untouched and should be rendered with `dir="auto"` where mixed-language content is possible.
- Domain/database enums remain canonical language-neutral values; localization maps only their display labels.

## Direction

Language and layout direction are separate settings. `AUTO` defaults to RTL for `fa`, `ar`, and `he`; all locales support manual `auto`, `ltr`, and `rtl` selection.

## Date and number formatting

Translation files contain wording around dates, not formatted dates. Use the locale metadata with `Intl.DateTimeFormat`, `Intl.NumberFormat`, and `Intl.RelativeTimeFormat` during implementation.

## User-authored content safety

Do not localize: `task.title`, `task.description`, `submission.note`, `handoff.reason`, `review.note`, `reward.name`, `reward.description`, custom category/organization names, profile/company names, file names, or URLs.

## Placeholders

Only identifiers verified against current runtime interpolation are retained. See `placeholder-audit.md`. Never translate placeholder identifiers.
