"""One-off codegen: inject the WS1 (selective push + Slack intake) keys into all 10 locales.

Adds every new key with a real translation per locale, preserving file order
(new keys appended before the closing brace) and CRLF line endings.
Placeholders ({{requesterName}} etc.) are byte-identical across locales —
src/i18n/parity.test.ts enforces key and placeholder parity.
"""
import json
from pathlib import Path

LOCALES = Path(__file__).resolve().parent.parent / 'src' / 'i18n' / 'locales'

KEYS: dict[str, dict[str, str]] = {}

def add(key: str, **loc: str) -> None:
    KEYS[key] = loc

add('event.helpRouted',
    en='{{requesterName}} needs help in {{scopeName}}: {{title}}',
    **{'zh-CN': '{{requesterName}}在{{scopeName}}中需要帮助：{{title}}',
       'ru': '{{requesterName}} нужна помощь ({{scopeName}}): {{title}}',
       'ar': '{{requesterName}} يحتاج إلى مساعدة في {{scopeName}}: {{title}}',
       'fa': '{{requesterName}} در {{scopeName}} به کمک نیاز دارد: {{title}}',
       'he': '{{requesterName}} זקוק/ה לעזרה ב{{scopeName}}: {{title}}',
       'hi': '{{requesterName}} को {{scopeName}} में सहायता चाहिए: {{title}}',
       'ja': '{{requesterName}}さんが{{scopeName}}でヘルプを求めています: {{title}}',
       'ko': '{{requesterName}}님이 {{scopeName}}에서 도움을 요청했습니다: {{title}}',
       'tr': '{{requesterName}}, {{scopeName}} kapsamında yardım istiyor: {{title}}'})

add('event.helpEscalated',
    en='Escalated: {{requesterName}} still needs help in {{scopeName}}: {{title}}',
    **{'zh-CN': '已升级：{{requesterName}}在{{scopeName}}中仍需要帮助：{{title}}',
       'ru': 'Эскалация: {{requesterName}} всё ещё нужна помощь ({{scopeName}}): {{title}}',
       'ar': 'تم التصعيد: {{requesterName}} ما زال يحتاج إلى مساعدة في {{scopeName}}: {{title}}',
       'fa': 'ارجاع فوری: {{requesterName}} هنوز در {{scopeName}} به کمک نیاز دارد: {{title}}',
       'he': 'הסלמה: {{requesterName}} עדיין זקוק/ה לעזרה ב{{scopeName}}: {{title}}',
       'hi': 'एस्केलेट किया गया: {{requesterName}} को {{scopeName}} में अभी भी सहायता चाहिए: {{title}}',
       'ja': 'エスカレーション: {{requesterName}}さんが{{scopeName}}でまだヘルプを必要としています: {{title}}',
       'ko': '에스컬레이션됨: {{requesterName}}님이 {{scopeName}}에서 아직 도움이 필요합니다: {{title}}',
       'tr': 'Yükseltildi: {{requesterName}} hâlâ {{scopeName}} kapsamında yardım bekliyor: {{title}}'})

add('event.helpRoutingUnresolved',
    en='No one is available for your help request yet: {{title}}',
    **{'zh-CN': '暂时没有人可以处理您的帮助请求：{{title}}',
       'ru': 'Пока некому откликнуться на ваш запрос помощи: {{title}}',
       'ar': 'لا يوجد أحد متاح لطلب المساعدة الخاص بك حالياً: {{title}}',
       'fa': 'فعلاً کسی برای درخواست کمک شما در دسترس نیست: {{title}}',
       'he': 'כרגע אין אף אחד זמין לבקשת העזרה שלך: {{title}}',
       'hi': 'आपके सहायता अनुरोध के लिए अभी कोई उपलब्ध नहीं है: {{title}}',
       'ja': '現在、ヘルプ依頼に対応できる人がいません: {{title}}',
       'ko': '현재 도움 요청을 받을 수 있는 사람이 없습니다: {{title}}',
       'tr': 'Yardım isteğiniz için şu anda uygun kimse yok: {{title}}'})

add('event.approvalRequested',
    en='An incentive for {{subjectName}} needs your approval.',
    **{'zh-CN': '{{subjectName}}的一笔奖励需要您的审批。',
       'ru': 'Поощрение для {{subjectName}} ожидает вашего одобрения.',
       'ar': 'مكافأة لـ{{subjectName}} تحتاج إلى موافقتك.',
       'fa': 'یک پاداش برای {{subjectName}} نیاز به تأیید شما دارد.',
       'he': 'תמריץ עבור {{subjectName}} ממתין לאישורך.',
       'hi': '{{subjectName}} के लिए एक इन्सेंटिव आपके अनुमोदन की प्रतीक्षा में है।',
       'ja': '{{subjectName}}さんへのインセンティブが承認待ちです。',
       'ko': '{{subjectName}}님의 인센티브가 승인을 기다리고 있습니다.',
       'tr': '{{subjectName}} için bir teşvik onayınızı bekliyor.'})

add('people.help.routing.ROUTED',
    en='Routed', **{'zh-CN': '已送达', 'ru': 'Доставлено', 'ar': 'تم التوجيه', 'fa': 'هدایت شد',
                    'he': 'נותב', 'hi': 'रूट किया गया', 'ja': 'ルーティング済み', 'ko': '전달됨', 'tr': 'Yönlendirildi'})

add('people.help.routing.UNRESOLVED',
    en='Awaiting recipients', **{'zh-CN': '等待接收人', 'ru': 'Ожидает получателей', 'ar': 'بانتظار المستلمين',
                                  'fa': 'در انتظار گیرندگان', 'he': 'ממתין לנמענים', 'hi': 'प्राप्तकर्ताओं की प्रतीक्षा में',
                                  'ja': '受信者待ち', 'ko': '수신자 대기 중', 'tr': 'Alıcı bekleniyor'})

add('people.help.routing.ESCALATED',
    en='Escalated', **{'zh-CN': '已升级', 'ru': 'Эскалировано', 'ar': 'تم التصعيد', 'fa': 'ارجاع فوری شد',
                       'he': 'הוסלם', 'hi': 'एस्केलेट किया गया', 'ja': 'エスカレーション済み', 'ko': '에스컬레이션됨',
                       'tr': 'Yükseltildi'})

add('capabilities.SLACK_CONNECTOR',
    en='Slack connector', **{'zh-CN': 'Slack 连接器', 'ru': 'Подключение Slack', 'ar': 'موصّل Slack', 'fa': 'اتصال Slack',
                             'he': 'חיבור Slack', 'hi': 'Slack कनेक्टर', 'ja': 'Slack コネクタ', 'ko': 'Slack 커넥터',
                             'tr': 'Slack bağlayıcısı'})

add('capabilities.SLACK_CONNECTOR.description',
    en='Let people ask for help, give thanks and recognize colleagues from a connected Slack workspace.',
    **{'zh-CN': '允许成员在已连接的 Slack 工作区中请求帮助、表达感谢和表彰同事。',
       'ru': 'Позволяет просить помощь, благодарить и отмечать коллег из подключённого пространства Slack.',
       'ar': 'يتيح طلب المساعدة وتوجيه الشكر وتقدير الزملاء من مساحة عمل Slack متصلة.',
       'fa': 'امکان درخواست کمک، تشکر و قدردانی از همکاران را از فضای کاری Slack متصل فراهم می‌کند.',
       'he': 'מאפשר לבקש עזרה, להודות ולהכיר בתרומת עמיתים מסביבת עבודה מחוברת של Slack.',
       'hi': 'कनेक्टेड Slack वर्कस्पेस से सहायता माँगने, धन्यवाद देने और सहकर्मियों को पहचानने की अनुमति देता है।',
       'ja': '接続された Slack ワークスペースからヘルプ依頼、感謝、表彰を行えるようにします。',
       'ko': '연결된 Slack 워크스페이스에서 도움 요청, 감사, 인정을 할 수 있게 합니다.',
       'tr': 'Bağlı bir Slack çalışma alanından yardım isteme, teşekkür etme ve takdir etmeyi sağlar.'})

add('integrations.slack.title',
    en='Slack', **{'zh-CN': 'Slack', 'ru': 'Slack', 'ar': 'Slack', 'fa': 'Slack', 'he': 'Slack',
                   'hi': 'Slack', 'ja': 'Slack', 'ko': 'Slack', 'tr': 'Slack'})

add('integrations.slack.teamId',
    en='Slack team ID', **{'zh-CN': 'Slack 团队 ID', 'ru': 'ID команды Slack', 'ar': 'معرّف فريق Slack',
                           'fa': 'شناسه تیم Slack', 'he': 'מזהה צוות Slack', 'hi': 'Slack टीम ID',
                           'ja': 'Slack チーム ID', 'ko': 'Slack 팀 ID', 'tr': 'Slack ekip kimliği'})

add('integrations.slack.create',
    en='Connect Slack workspace',
    **{'zh-CN': '连接 Slack 工作区', 'ru': 'Подключить пространство Slack', 'ar': 'ربط مساحة عمل Slack',
       'fa': 'اتصال فضای کاری Slack', 'he': 'חיבור סביבת עבודה של Slack', 'hi': 'Slack वर्कस्पेस कनेक्ट करें',
       'ja': 'Slack ワークスペースを接続', 'ko': 'Slack 워크스페이스 연결', 'tr': 'Slack çalışma alanı bağla'})

add('integrations.slack.commandPath',
    en='Command URL', **{'zh-CN': '命令 URL', 'ru': 'URL команд', 'ar': 'رابط الأوامر', 'fa': 'نشانی فرمان',
                         'he': 'כתובת פקודות', 'hi': 'कमांड URL', 'ja': 'コマンド URL', 'ko': '명령 URL', 'tr': 'Komut URL’si'})

add('integrations.slack.secretOnce',
    en='Signing secret (shown once — store it in your Slack app):',
    **{'zh-CN': '签名密钥（仅显示一次——请保存到您的 Slack 应用中）：',
       'ru': 'Секрет подписи (показывается один раз — сохраните его в приложении Slack):',
       'ar': 'سر التوقيع (يظهر مرة واحدة — احفظه في تطبيق Slack):',
       'fa': 'رمز امضا (فقط یک بار نمایش داده می‌شود — آن را در برنامه Slack ذخیره کنید):',
       'he': 'סוד חתימה (מוצג פעם אחת — שמור אותו באפליקציית Slack):',
       'hi': 'साइनिंग सीक्रेट (केवल एक बार दिखाया जाता है — इसे अपने Slack ऐप में सहेजें):',
       'ja': '署名シークレット（一度だけ表示されます — Slack アプリに保存してください）:',
       'ko': '서명 시크릿(한 번만 표시됨 — Slack 앱에 저장하세요):',
       'tr': 'İmza sırrı (yalnızca bir kez gösterilir — Slack uygulamanıza kaydedin):'})

add('integrations.slack.hint',
    en='Slash commands /cve-help, /cve-thanks and /cve-recognize post to this URL.',
    **{'zh-CN': '斜杠命令 /cve-help、/cve-thanks 和 /cve-recognize 会发送到此 URL。',
       'ru': 'Слэш-команды /cve-help, /cve-thanks и /cve-recognize отправляются на этот URL.',
       'ar': 'أوامر Slash ‏/cve-help و/cve-thanks و/cve-recognize ترسل إلى هذا الرابط.',
       'fa': 'دستورهای اسلش ‎/cve-help، ‎/cve-thanks و ‎/cve-recognize به این نشانی ارسال می‌شوند.',
       'he': 'פקודות הסלאש ‎/cve-help, ‎/cve-thanks ו־‎/cve-recognize נשלחות לכתובת זו.',
       'hi': 'स्लैश कमांड /cve-help, /cve-thanks और /cve-recognize इस URL पर पोस्ट होते हैं।',
       'ja': 'スラッシュコマンド /cve-help、/cve-thanks、/cve-recognize はこの URL に送信されます。',
       'ko': '슬래시 명령 /cve-help, /cve-thanks, /cve-recognize가 이 URL로 전송됩니다.',
       'tr': '/cve-help, /cve-thanks ve /cve-recognize eğik çizgi komutları bu URL’ye gönderilir.'})

add('integrations.action.rotate',
    en='Rotate secret', **{'zh-CN': '轮换密钥', 'ru': 'Сменить секрет', 'ar': 'تدوير السر', 'fa': 'چرخش رمز',
                           'he': 'החלפת סוד', 'hi': 'सीक्रेट बदलें', 'ja': 'シークレットをローテーション',
                           'ko': '시크릿 교체', 'tr': 'Sırrı döndür'})

add('integrations.slack.workspaceName',
    en='Workspace name', **{'zh-CN': '工作区名称', 'ru': 'Название пространства', 'ar': 'اسم مساحة العمل',
                            'fa': 'نام فضای کاری', 'he': 'שם סביבת העבודה', 'hi': 'वर्कस्पेस का नाम',
                            'ja': 'ワークスペース名', 'ko': '워크스페이스 이름', 'tr': 'Çalışma alanı adı'})


def main() -> None:
    for path in sorted(LOCALES.glob('*.json')):
        locale = path.stem
        data = json.loads(path.read_text(encoding='utf-8'))
        added = 0
        for key, texts in KEYS.items():
            if key in data:
                continue
            data[key] = texts[locale]
            added += 1
        # Keep original line endings (these files use \r\r\n in the repo).
        raw = path.read_bytes()
        newline = b'\r\r\n' if b'\r\r\n' in raw else (b'\r\n' if b'\r\n' in raw else b'\n')
        out = json.dumps(data, ensure_ascii=False, indent=2)
        # json.dumps adds no trailing newline; match repo style (single trailing NL).
        payload = (out + '\n').encode('utf-8')
        if newline != b'\n':
            payload = payload.replace(b'\n', newline)
        path.write_bytes(payload)
        print(f'{locale}: +{added} keys')


if __name__ == '__main__':
    main()
