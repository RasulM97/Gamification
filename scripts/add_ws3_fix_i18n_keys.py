"""One-off codegen: WS3 review-fix i18n key — separates CURRENT state from
RECENT flow in Team Flow's incentive panel. Appends `flow.current` to all 10
locales, preserving file order (json round-trip), CRLF endings, and
placeholder parity (src/i18n/parity.test.ts enforces both)."""
import json
from pathlib import Path

LOCALES = Path(__file__).resolve().parent.parent / 'src' / 'i18n' / 'locales'

ADD: dict[str, dict[str, str]] = {
  'flow.current': {
    'en': 'Right now', 'zh-CN': '当前状态', 'ru': 'Сейчас', 'hi': 'अभी',
    'fa': 'اکنون', 'ar': 'الآن', 'he': 'כרגע', 'tr': 'Şu an',
    'ko': '현재', 'ja': '現在'},
}

for loc, path in sorted((p.stem, p) for p in LOCALES.glob('*.json')):
    data = json.loads(path.read_bytes().decode('utf-8'))
    for key, tr in ADD.items():
        if loc not in tr:
            raise SystemExit(f'{loc}: missing translation for {key}')
        if key in data:
            raise SystemExit(f'{loc}: key already exists: {key}')
        data[key] = tr[loc]
    out = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    path.write_bytes(out.replace('\n', '\r\n').encode('utf-8'))
    print(f'{loc}: +{len(ADD)} keys -> {len(data)} total')
print('done')
