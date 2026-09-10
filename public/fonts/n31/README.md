# N3.1 script fonts

Vendored from the `@fontsource-variable` packages listed below, version **5.3.0**.
Each package includes its SIL Open Font License in this directory. Reproduce with
`node scripts/n31-fonts.mjs` (network needed only when vendoring).

| Family | WOFF2 files | Bytes |
| --- | ---: | ---: |
| Vazirmatn | 3 | 102,692 |
| Noto Sans Arabic | 5 | 251,492 |
| Noto Sans Hebrew | 5 | 46,416 |
| Noto Sans Devanagari | 3 | 160,428 |
| Noto Sans SC | 101 | 4,516,508 |
| Noto Sans JP | 124 | 5,223,320 |
| Noto Sans KR | 124 | 3,519,780 |
| Total | 365 | 13,820,636 |

These are normal-style variable weight fonts, not separate weight files. No
italic or separate static weights were added. CJK fonts are split into Unicode
subsets to keep individual transfers small. `src/styles/fonts.css` retains the
upstream Unicode ranges: the browser requests only subsets needed by displayed
glyphs in the selected family. All 365 files are **not** downloaded on page load.
The full CJK repertoire remains available for authored content and future UI
strings. `font-display: swap` provides readable fallback during transfer.

Selection uses the existing root `lang`, independently of `dir`; no React font
loader and no runtime Google Fonts or Fontsource connection is required.
Geist and Geist Mono remain the Latin defaults already in the repository.

Upstream package metadata: `https://registry.npmjs.org/@fontsource-variable/<package>/5.3.0`
where package is `vazirmatn`, `noto-sans-arabic`, `noto-sans-hebrew`,
`noto-sans-devanagari`, `noto-sans-sc`, `noto-sans-jp`, or `noto-sans-kr`.
