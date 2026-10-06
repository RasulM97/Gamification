"""One-off codegen: WS2 review-fix i18n keys across all 10 locales.

- ADDS: canonical event phrases, employee outcome statuses/next lines,
  policy-reason phrases, wallet outcomes title, notApprovedBy.
- REPLACES: manager consequence copy (approve no longer claims it pays).
- DELETES: the drifted internal.help.confirmed phrase (canonical type is
  internal.help.completed).

Preserves file order (json round-trip), CRLF line endings, and placeholder
parity (src/i18n/parity.test.ts enforces both).
"""
import json
from pathlib import Path

LOCALES = Path(__file__).resolve().parent.parent / 'src' / 'i18n' / 'locales'
ALL_LOCALES = ['en', 'zh-CN', 'ru', 'hi', 'fa', 'ar', 'he', 'tr', 'ko', 'ja']

ADD: dict[str, dict[str, str]] = {
  'provenance.event.github.pull_request.opened': {
    'en': 'An opened pull request', 'zh-CN': '打开的拉取请求', 'ru': 'Открытый pull request',
    'hi': 'खुला पुल रिक्वेस्ट', 'fa': 'یک پول ریکوئست باز شده', 'ar': 'طلب سحب مفتوح',
    'he': 'פול ריקווסט שנפתח', 'tr': 'Açılan bir pull request', 'ko': '열린 풀 리퀘스트',
    'ja': 'オープンされたプルリクエスト'},
  'provenance.event.github.pull_request.closed': {
    'en': 'A closed pull request', 'zh-CN': '已关闭的拉取请求', 'ru': 'Закрытый pull request',
    'hi': 'बंद पुल रिक्वेस्ट', 'fa': 'یک پول ریکوئست بسته شده', 'ar': 'طلب سحب مغلق',
    'he': 'פול ריקווסט שנסגר', 'tr': 'Kapatılan bir pull request', 'ko': '닫힌 풀 리퀘스트',
    'ja': 'クローズされたプルリクエスト'},
  'provenance.event.github.issue.opened': {
    'en': 'An opened issue', 'zh-CN': '打开的 Issue', 'ru': 'Открытый issue',
    'hi': 'खुला इश्यू', 'fa': 'یک ایشو باز شده', 'ar': 'مشكلة مفتوحة',
    'he': 'ישו שנפתח', 'tr': 'Açılan bir issue', 'ko': '열린 이슈',
    'ja': 'オープンされたイシュー'},
  'provenance.event.github.issue.closed': {
    'en': 'A closed issue', 'zh-CN': '已关闭的 Issue', 'ru': 'Закрытый issue',
    'hi': 'बंद इश्यू', 'fa': 'یک ایشو بسته شده', 'ar': 'مشكلة مغلقة',
    'he': 'ישו שנסגר', 'tr': 'Kapatılan bir issue', 'ko': '닫힌 이슈',
    'ja': 'クローズされたイシュー'},
  'provenance.event.internal.manager.recognition': {
    'en': 'Recognition from a manager', 'zh-CN': '来自经理的认可', 'ru': 'Признание от руководителя',
    'hi': 'मैनेजर की सराहना', 'fa': 'قدردانی از سوی مدیر', 'ar': 'تقدير من المدير',
    'he': 'הכרה מהמנהל', 'tr': 'Yöneticiden takdir', 'ko': '매니저의 인정',
    'ja': 'マネージャーからの称賛'},
  'provenance.event.internal.help.completed': {
    'en': 'Completed help for a colleague', 'zh-CN': '完成对同事的帮助', 'ru': 'Завершённая помощь коллеге',
    'hi': 'सहकर्मी की मदद पूरी हुई', 'fa': 'کمک تکمیل‌شده به همکار', 'ar': 'مساعدة مكتملة لزميل',
    'he': 'עזרה שהושלמה לעמית', 'tr': 'Bir iş arkadaşına tamamlanan yardım', 'ko': '동료를 도운 완료된 도움',
    'ja': '同僚への完了したヘルプ'},
  'provenance.status.AUTHORIZED_PENDING': {
    'en': 'Authorized', 'zh-CN': '已授权', 'ru': 'Разрешено',
    'hi': 'अधिकृत', 'fa': 'مجاز شده', 'ar': 'مصرَّح به',
    'he': 'מורשה', 'tr': 'Yetkilendirildi', 'ko': '발행 대기',
    'ja': '発行待ち'},
  'provenance.status.PENDING_REVIEW': {
    'en': 'In review', 'zh-CN': '审核中', 'ru': 'На проверке',
    'hi': 'समीक्षा में', 'fa': 'در حال بررسی', 'ar': 'قيد المراجعة',
    'he': 'בבדיקה', 'tr': 'İncelemede', 'ko': '검토 중',
    'ja': 'レビュー中'},
  'provenance.status.NOT_APPROVED': {
    'en': 'Not approved', 'zh-CN': '未获批准', 'ru': 'Не одобрено',
    'hi': 'स्वीकृत नहीं', 'fa': 'تأیید نشده', 'ar': 'لم يُعتمد',
    'he': 'לא אושר', 'tr': 'Onaylanmadı', 'ko': '승인되지 않음',
    'ja': '未承認'},
  'provenance.status.NOT_AUTHORIZED': {
    'en': 'Not authorized', 'zh-CN': '未获授权', 'ru': 'Не разрешено',
    'hi': 'अनधिकृत', 'fa': 'مجاز نیست', 'ar': 'غير مصرَّح',
    'he': 'לא מורשה', 'tr': 'Yetkisiz', 'ko': '허용되지 않음',
    'ja': '許可されていません'},
  'provenance.status.SAFEGUARDED': {
    'en': 'Safeguarded', 'zh-CN': '已防护', 'ru': 'Задержано защитой',
    'hi': 'सुरक्षा द्वारा रोका गया', 'fa': 'بازداشته‌شده توسط بررسی امنیتی', 'ar': 'محجوب بفحص الأمان',
    'he': 'נעצר בבדיקת בטיחות', 'tr': 'Güvenlik denetiminde tutuldu', 'ko': '보안 검사로 보류됨',
    'ja': '安全チェックで保留'},
  'provenance.policyReason.MATCHED_POLICY': {
    'en': 'A company policy applied.', 'zh-CN': '适用了一项公司政策。', 'ru': 'Применилась политика компании.',
    'hi': 'कंपनी की नीति लागू हुई।', 'fa': 'یک سیاست شرکت اعمال شد.', 'ar': 'طبّقت سياسة الشركة.',
    'he': 'מדיניות החברה חלה.', 'tr': 'Bir şirket politikası uygulandı.', 'ko': '회사 정책이 적용되었습니다.',
    'ja': '会社のポリシーが適用されました。'},
  'provenance.policyReason.DEFAULT_GOVERNANCE': {
    'en': 'The standard company policy applied.', 'zh-CN': '适用了公司标准政策。', 'ru': 'Применилась стандартная политика компании.',
    'hi': 'कंपनी की मानक नीति लागू हुई।', 'fa': 'سیاست استاندارد شرکت اعمال شد.', 'ar': 'طبّقت سياسة الشركة القياسية.',
    'he': 'מדיניות החברה הרגילה חלה.', 'tr': 'Standart şirket politikası uygulandı.', 'ko': '표준 회사 정책이 적용되었습니다.',
    'ja': '標準の会社ポリシーが適用されました。'},
  'provenance.nextFor.AUTHORIZED_PENDING': {
    'en': 'Nothing to do — it is authorized and will appear in your balance once issued.',
    'zh-CN': '无需操作——该激励已获授权，发放后将计入您的余额。',
    'ru': 'Ничего делать не нужно — вознаграждение разрешено и появится в балансе после выпуска.',
    'hi': 'कुछ करने की ज़रूरत नहीं — यह अधिकृत है और जारी होने पर आपके बैलेंस में दिखेगा।',
    'fa': 'کاری لازم نیست — این پاداش مجاز است و پس از صدور به موجودی شما اضافه می‌شود.',
    'ar': 'لا شيء عليك — الحافز مصرَّح به وسيظهر في رصيدك عند إصداره.',
    'he': 'אין מה לעשות — התמריץ מורשה ויופיע ביתרה לאחר ההנפקה.',
    'tr': 'Bir şey yapmanız gerekmez — yetkilendirildi ve düzenlendiğinde bakiyenize yansır.',
    'ko': '할 일이 없습니다 — 승인되었으며 발행되면 잔액에 반영됩니다.',
    'ja': '何もする必要はありません — 承認済みで、発行されると残高に反映されます。'},
  'provenance.nextFor.PENDING_REVIEW': {
    'en': 'A manager or administrator still needs to review this.',
    'zh-CN': '经理或管理员仍需审核此项。',
    'ru': 'Руководителю или администратору ещё предстоит проверить это.',
    'hi': 'मैनेजर या एडमिन को अभी इसकी समीक्षा करनी है।',
    'fa': 'مدیر یا سرپرست هنوز باید این مورد را بررسی کند.',
    'ar': 'ما زال على المدير أو المشرف مراجعة هذا.',
    'he': 'מנהל או מנהל מערכת עדיין צריך לבדוק זאת.',
    'tr': 'Bir yönetici veya yöneticinin bunu incelemesi gerekiyor.',
    'ko': '매니저 또는 관리자의 검토가 아직 필요합니다.',
    'ja': 'マネージャーまたは管理者によるレビューがまだ必要です。'},
  'provenance.nextFor.NOT_APPROVED': {
    'en': 'This incentive was not approved. Ask your manager if this looks wrong.',
    'zh-CN': '该激励未获批准。如有疑问，请咨询您的经理。',
    'ru': 'Вознаграждение не одобрено. Если это кажется ошибкой, спросите руководителя.',
    'hi': 'यह प्रोत्साहन स्वीकृत नहीं हुआ। अगर यह गलत लगे तो अपने मैनेजर से पूछें।',
    'fa': 'این پاداش تأیید نشد. اگر اشتباه به نظر می‌رسد، از مدیر خود بپرسید.',
    'ar': 'لم تتم الموافقة على هذا الحافز. اسأل مديرك إذا بدا هذا خطأ.',
    'he': 'התמריץ לא אושר. אם נראה שגוי, שאלו את המנהל.',
    'tr': 'Bu teşvik onaylanmadı. Yanlış görünüyorsa yöneticinize sorun.',
    'ko': '이 인센티브는 승인되지 않았습니다. 잘못된 것 같으면 매니저에게 문의하세요.',
    'ja': 'このインセンティブは承認されませんでした。誤りと思われる場合はマネージャーに確認してください。'},
  'provenance.nextFor.NOT_AUTHORIZED': {
    'en': 'Company policy does not allow this incentive.',
    'zh-CN': '公司政策不允许此项激励。',
    'ru': 'Политика компании не разрешает это вознаграждение.',
    'hi': 'कंपनी नीति इस प्रोत्साहन की अनुमति नहीं देती।',
    'fa': 'سیاست شرکت اجازه این پاداش را نمی‌دهد.',
    'ar': 'سياسة الشركة لا تسمح بهذا الحافز.',
    'he': 'מדיניות החברה לא מאפשרת את התמריץ הזה.',
    'tr': 'Şirket politikası bu teşvike izin vermiyor.',
    'ko': '회사 정책상 이 인센티브는 허용되지 않습니다.',
    'ja': '会社のポリシーによりこのインセンティブは許可されていません。'},
  'provenance.nextFor.SAFEGUARDED': {
    'en': 'Automatic safety checks held this incentive back. Ask your administrator if this looks wrong.',
    'zh-CN': '自动安全检查拦截了此项激励。如有疑问，请联系管理员。',
    'ru': 'Автоматические проверки безопасности задержали это вознаграждение. Если это кажется ошибкой, обратитесь к администратору.',
    'hi': 'स्वचालित सुरक्षा जांचों ने इस प्रोत्साहन को रोक दिया। अगर यह गलत लगे तो एडमिन से पूछें।',
    'fa': 'بررسی‌های خودکار امنیتی این پاداش را نگه داشته‌اند. اگر اشتباه به نظر می‌رسد، به سرپرست اطلاع دهید.',
    'ar': 'أوقفت فحوصات الأمان التلقائية هذا الحافز. اسأل المشرف إذا بدا هذا خطأ.',
    'he': 'בדיקות הבטיחות האוטומטיות עצרו את התמריץ. אם נראה שגוי, פנו למנהל המערכת.',
    'tr': 'Otomatik güvenlik denetimleri bu teşviki tuttu. Yanlış görünüyorsa yöneticinize sorun.',
    'ko': '자동 보안 검사가 이 인센티브를 보류했습니다. 잘못된 것 같으면 관리자에게 문의하세요.',
    'ja': '自動安全チェックによりこのインセンティブは保留されました。誤りと思われる場合は管理者に確認してください。'},
  'provenance.notApprovedBy': {
    'en': 'Not approved by {{name}}', 'zh-CN': '未获 {{name}} 批准', 'ru': 'Не одобрено пользователем {{name}}',
    'hi': '{{name}} ने स्वीकृत नहीं किया', 'fa': 'تأیید نشده توسط {{name}}', 'ar': 'لم يعتمد من {{name}}',
    'he': 'לא אושר על ידי {{name}}', 'tr': '{{name}} tarafından onaylanmadı', 'ko': '{{name}}이(가) 승인하지 않음',
    'ja': '{{name}} が承認しませんでした'},
  'wallet.outcomes': {
    'en': 'Incentive outcomes', 'zh-CN': '激励结果', 'ru': 'Исходы вознаграждений',
    'hi': 'प्रोत्साहन परिणाम', 'fa': 'نتایج پاداش‌ها', 'ar': 'نتائج الحوافز',
    'he': 'תוצאות תמריצים', 'tr': 'Teşvik sonuçları', 'ko': '인센티브 결과',
    'ja': 'インセンティブの結果'},
}

REPLACE: dict[str, dict[str, str]] = {
  # Truthful manager copy: approval authorizes; issuance is a separate admin step.
  'provenance.consequence.approve': {
    'en': 'Approving authorizes this incentive to move forward. It is only paid when an administrator issues it.',
    'zh-CN': '批准即授权此激励继续推进。只有在管理员发放后才会支付。',
    'ru': 'Одобрение разрешает движение вознаграждения дальше. Выплата произойдёт только после выпуска администратором.',
    'hi': 'स्वीकृत करने से यह प्रोत्साहन आगे बढ़ने के लिए अधिकृत होता है। भुगतान तभी होता है जब एडमिन इसे जारी करता है।',
    'fa': 'تأیید، این پاداش را برای ادامه مسیر مجاز می‌کند. پرداخت فقط زمانی انجام می‌شود که سرپرست آن را صادر کند.',
    'ar': 'الموافقة تخوّل هذا الحافز للمضي قدمًا. لا يُدفع إلا عندما يصدره المشرف.',
    'he': 'אישור מרשה לתמריץ להתקדם. התשלום מתבצע רק כאשר מנהל מערכת מנפיק אותו.',
    'tr': 'Onaylamak bu teşviğin ilerlemesine yetki verir. Ödeme yalnızca bir yönetici düzenlediğinde yapılır.',
    'ko': '승인하면 이 인센티브가 진행될 권한이 부여됩니다. 관리자가 발행해야만 지급됩니다.',
    'ja': '承認するとこのインセンティブの進行が許可されます。管理者が発行してはじめて支払われます。'},
  'provenance.consequence.reject': {
    'en': 'Rejecting stops this incentive — it will not be paid through this approval.',
    'zh-CN': '拒绝将阻止此激励——不会通过此次批准支付。',
    'ru': 'Отклонение останавливает это вознаграждение — по этому запросу оно не будет выплачено.',
    'hi': 'अस्वीकृत करने से यह प्रोत्साहन रुक जाता है — इस अनुमोदन के माध्यम से भुगतान नहीं होगा।',
    'fa': 'رد کردن این پاداش را متوقف می‌کند — از طریق این تأیید پرداخت نمی‌شود.',
    'ar': 'الرفض يوقف هذا الحافز — لن يُدفع من خلال هذه الموافقة.',
    'he': 'דחייה עוצרת את התמריץ — הוא לא ישולם דרך אישור זה.',
    'tr': 'Reddetmek bu teşviği durdurur — bu onay yoluyla ödenmez.',
    'ko': '거부하면 이 인센티브는 중단되며 이 승인을 통해 지급되지 않습니다.',
    'ja': '却下するとこのインセンティブは停止し、この承認経路では支払われません。'},
}

DELETE = ['provenance.event.internal.help.confirmed']

for table in (ADD, REPLACE):
    missing = [(k, loc) for k, tr in table.items() for loc in ALL_LOCALES if loc not in tr]
    assert not missing, f'missing translations: {missing[:5]}'

for loc in ALL_LOCALES:
    path = LOCALES / f'{loc}.json'
    data = json.loads(path.read_bytes().decode('utf-8'))
    added = replaced = 0
    for key, tr in ADD.items():
        if key in data:
            raise SystemExit(f'{loc}: key already exists: {key}')
        data[key] = tr[loc]
        added += 1
    for key, tr in REPLACE.items():
        if key not in data:
            raise SystemExit(f'{loc}: key to replace missing: {key}')
        data[key] = tr[loc]
        replaced += 1
    for key in DELETE:
        if data.pop(key, None) is not None:
            pass
    out = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    path.write_bytes(out.replace('\n', '\r\n').encode('utf-8'))
    print(f'{loc}: +{added} keys, {replaced} replaced, {len(DELETE)} deleted -> {len(data)} total')
print('done')
