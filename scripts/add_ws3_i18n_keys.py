"""One-off codegen: WS3 attention/flow i18n keys across all 10 locales.

- ADDS: My Attention categories/kinds/states/actions, Team Flow sections and
  aggregate stat labels, nav.teamFlow, page.flow.subtitle.
- REPLACES: page.attention.subtitle and attention.emptyHint (the surface is
  no longer task-only — WS3 composes all authoritative domains).

Preserves file order (json round-trip), CRLF line endings, and placeholder
parity (src/i18n/parity.test.ts enforces both).
"""
import json
from pathlib import Path

LOCALES = Path(__file__).resolve().parent.parent / 'src' / 'i18n' / 'locales'
ALL_LOCALES = ['en', 'zh-CN', 'ru', 'hi', 'fa', 'ar', 'he', 'tr', 'ko', 'ja']

ADD: dict[str, dict[str, str]] = {
  'nav.teamFlow': {
    'en': 'Team Flow', 'zh-CN': '团队动态', 'ru': 'Поток команды', 'hi': 'टीम प्रवाह',
    'fa': 'جریان تیم', 'ar': 'تدفق الفريق', 'he': 'זרימת הצוות', 'tr': 'Ekip Akışı',
    'ko': '팀 플로우', 'ja': 'チームフロー'},
  'page.flow.subtitle': {
    'en': 'Interventions, blockers, and waiting decisions',
    'zh-CN': '需要介入的事项、阻塞与等待中的决定',
    'ru': 'Вмешательства, блокировки и ожидающие решения',
    'hi': 'हस्तक्षेप, रुकावटें और लंबित निर्णय',
    'fa': 'مداخله‌ها، گلوگاه‌ها و تصمیم‌های در انتظار',
    'ar': 'التدخلات والعوائق والقرارات المعلقة',
    'he': 'התערבויות, חסמים והחלטות ממתינות',
    'tr': 'Müdahaleler, engelleyiciler ve bekleyen kararlar',
    'ko': '개입, 차단 요소, 대기 중인 결정',
    'ja': '介入・ブロッカー・待機中の決定'},
  'attention.category.ACTION_REQUIRED': {
    'en': 'Needs your action', 'zh-CN': '需要你处理', 'ru': 'Требуется ваше действие',
    'hi': 'आपकी कार्रवाई चाहिए', 'fa': 'نیازمند اقدام شما', 'ar': 'يتطلب إجراءك',
    'he': 'דורש פעולה שלך', 'tr': 'Eyleminiz gerekiyor', 'ko': '조치가 필요합니다',
    'ja': '対応が必要'},
  'attention.category.WAITING': {
    'en': 'Waiting on others', 'zh-CN': '等待他人', 'ru': 'Ожидают других',
    'hi': 'दूसरों की प्रतीक्षा में', 'fa': 'در انتظار دیگران', 'ar': 'بانتظار الآخرين',
    'he': 'ממתין לאחרים', 'tr': 'Başkalarını bekliyor', 'ko': '다른 사람을 기다리는 중',
    'ja': '他の人を待機中'},
  'attention.category.RESOLVED_RECENTLY': {
    'en': 'Resolved recently', 'zh-CN': '最近已解决', 'ru': 'Недавно решено',
    'hi': 'हाल ही में हल', 'fa': 'اخیراً حل‌شده', 'ar': 'حُل مؤخرًا',
    'he': 'נפתר לאחרונה', 'tr': 'Yakında çözülen', 'ko': '최근 해결됨', 'ja': '最近解決'},
  'attention.category.INFORMATION': {
    'en': 'For your awareness', 'zh-CN': '供你了解', 'ru': 'К сведению',
    'hi': 'आपकी जानकारी के लिए', 'fa': 'برای اطلاع شما', 'ar': 'لاطلاعك',
    'he': 'לידיעתך', 'tr': 'Bilginize', 'ko': '참고 사항', 'ja': 'お知らせ'},
  'attention.kind.help.confirm': {
    'en': 'Help finished — confirm it is complete', 'zh-CN': '帮助已完成——请确认',
    'ru': 'Помощь завершена — подтвердите', 'hi': 'मदद पूरी हुई — पुष्टि करें',
    'fa': 'کمک تمام شد — تأیید کنید', 'ar': 'اكتملت المساعدة — أكّد الإتمام',
    'he': 'העזרה הסתיימה — אשר השלמה', 'tr': 'Yardım tamamlandı — onaylayın',
    'ko': '도움 완료 — 확인해 주세요', 'ja': 'ヘルプ完了 — 確認してください'},
  'attention.kind.help.waiting': {
    'en': 'Your help request', 'zh-CN': '你的帮助请求', 'ru': 'Ваш запрос о помощи',
    'hi': 'आपका मदद अनुरोध', 'fa': 'درخواست کمک شما', 'ar': 'طلب المساعدة الخاص بك',
    'he': 'בקשת העזרה שלך', 'tr': 'Yardım isteğiniz', 'ko': '내 도움 요청',
    'ja': 'あなたのヘルプリクエスト'},
  'attention.kind.help.resolved': {
    'en': 'Help request resolved', 'zh-CN': '帮助请求已解决', 'ru': 'Запрос о помощи решён',
    'hi': 'मदद अनुरोध हल हुआ', 'fa': 'درخواست کمک حل شد', 'ar': 'تم حل طلب المساعدة',
    'he': 'בקשת העזרה נפתרה', 'tr': 'Yardım isteği çözüldü', 'ko': '도움 요청 해결됨',
    'ja': 'ヘルプリクエスト解決済み'},
  'attention.kind.help.finish': {
    'en': 'You accepted this — mark it finished', 'zh-CN': '你已接受——完成后请标记',
    'ru': 'Вы приняли — отметьте завершение', 'hi': 'आपने स्वीकार किया — पूर्ण चिह्नित करें',
    'fa': 'پذیرفتید — اتمام را ثبت کنید', 'ar': 'قبلتَ هذا — ضع علامة الإتمام',
    'he': 'קיבלת — סמן כהושלם', 'tr': 'Kabul ettiniz — tamamlandı olarak işaretleyin',
    'ko': '수락함 — 완료로 표시하세요', 'ja': '受諾済み — 完了にしてください'},
  'attention.kind.help.awaitingConfirm': {
    'en': 'Waiting for the requester to confirm', 'zh-CN': '等待请求者确认',
    'ru': 'Ожидание подтверждения от автора', 'hi': 'अनुरोधकर्ता की पुष्टि की प्रतीक्षा',
    'fa': 'در انتظار تأیید درخواست‌کننده', 'ar': 'بانتظار تأكيد مقدم الطلب',
    'he': 'ממתין לאישור המבקש', 'tr': 'İstek sahibinin onayı bekleniyor',
    'ko': '요청자 확인 대기 중', 'ja': '依頼者の確認待ち'},
  'attention.kind.help.accept': {
    'en': 'Help requested — you can accept', 'zh-CN': '有人请求帮助——你可以接受',
    'ru': 'Запрошена помощь — вы можете принять', 'hi': 'मदद मांगी गई — आप स्वीकार कर सकते हैं',
    'fa': 'کمک درخواست شده — می‌توانید بپذیرید', 'ar': 'طلب مساعدة — يمكنك قبوله',
    'he': 'התבקשה עזרה — אפשר לקבל', 'tr': 'Yardım istendi — kabul edebilirsiniz',
    'ko': '도움 요청됨 — 수락할 수 있습니다', 'ja': 'ヘルプが求められています — 受諾できます'},
  'attention.kind.help.routed': {
    'en': 'Open help request — colleagues notified', 'zh-CN': '未解决的帮助请求——已通知同事',
    'ru': 'Открытый запрос — коллеги уведомлены', 'hi': 'खुला मदद अनुरोध — सहकर्मियों को सूचित',
    'fa': 'درخواست کمک باز — همکاران مطلع شدند', 'ar': 'طلب مساعدة مفتوح — تم إشعار الزملاء',
    'he': 'בקשת עזרה פתוחה — העמיתים עודכנו', 'tr': 'Açık yardım isteği — iş arkadaşları bilgilendirildi',
    'ko': '열린 도움 요청 — 동료에게 알림', 'ja': '未解決のヘルプ — 同僚に通知済み'},
  'attention.kind.help.unresolved': {
    'en': 'Help request with no available helper', 'zh-CN': '暂无可用帮助者的请求',
    'ru': 'Запрос без доступного помощника', 'hi': 'कोई उपलब्ध मददकर्ता नहीं',
    'fa': 'درخواست بدون کمک‌کننده در دسترس', 'ar': 'طلب بلا مساعد متاح',
    'he': 'בקשה ללא עוזר זמין', 'tr': 'Uygun yardımcısı olmayan istek',
    'ko': '가능한 도움자가 없는 요청', 'ja': '対応可能なヘルパーがいないリクエスト'},
  'attention.kind.help.escalated': {
    'en': 'Help request escalated — needs a manager', 'zh-CN': '帮助请求已升级——需要经理处理',
    'ru': 'Запрос эскалирован — нужен руководитель', 'hi': 'मदद अनुरोध एस्केलेट — मैनेजर चाहिए',
    'fa': 'درخواست کمک ارجاع شده — نیازمند مدیر', 'ar': 'طلب مساعدة مُصعّد — يحتاج مديرًا',
    'he': 'בקשת עזרה הועברה — נדרש מנהל', 'tr': 'Yardım isteği yükseltildi — yönetici gerekli',
    'ko': '에스컬레이션된 도움 요청 — 매니저 필요', 'ja': 'エスカレーションされたヘルプ — マネージャー対応'},
  'attention.kind.help.inProgress': {
    'en': 'Help in progress', 'zh-CN': '帮助进行中', 'ru': 'Помощь в процессе',
    'hi': 'मदद जारी', 'fa': 'کمک در حال انجام', 'ar': 'المساعدة جارية',
    'he': 'עזרה בתהליך', 'tr': 'Yardım sürüyor', 'ko': '도움 진행 중', 'ja': 'ヘルプ対応中'},
  'attention.kind.approval.decide': {
    'en': 'Incentive approval waiting for your decision', 'zh-CN': '激励审批等待你的决定',
    'ru': 'Заявка на поощрение ждёт вашего решения', 'hi': 'प्रोत्साहन अनुमोदन आपके निर्णय की प्रतीक्षा में',
    'fa': 'تأیید پاداش در انتظار تصمیم شما', 'ar': 'موافقة على حافز بانتظار قرارك',
    'he': 'אישור תמריץ ממתין להחלטתך', 'tr': 'Teşvik onayı kararınızı bekliyor',
    'ko': '인센티브 승인이 결정을 기다립니다', 'ja': 'インセンティブ承認があなたの決定待ち'},
  'attention.kind.incentive.waiting': {
    'en': 'Incentive outcome pending', 'zh-CN': '激励结果待处理', 'ru': 'Результат поощрения ожидается',
    'hi': 'प्रोत्साहन परिणाम लंबित', 'fa': 'نتیجه پاداش در انتظار', 'ar': 'نتيجة حافز معلقة',
    'he': 'תוצאת תמריץ ממתינה', 'tr': 'Teşvik sonucu beklemede', 'ko': '인센티브 결과 대기 중',
    'ja': 'インセンティブ結果待ち'},
  'attention.kind.incentive.outcome': {
    'en': 'Incentive outcome decided', 'zh-CN': '激励结果已确定', 'ru': 'Результат поощрения решён',
    'hi': 'प्रोत्साहन परिणाम तय', 'fa': 'نتیجه پاداش تعیین شد', 'ar': 'تم البت في نتيجة الحافز',
    'he': 'תוצאת התמריץ הוחלטה', 'tr': 'Teşvik sonucu belirlendi', 'ko': '인센티브 결과 확정',
    'ja': 'インセンティブ結果確定'},
  'attention.kind.appreciation.thanks': {
    'en': 'Thanks received', 'zh-CN': '收到感谢', 'ru': 'Получена благодарность',
    'hi': 'धन्यवाद प्राप्त', 'fa': 'تشکر دریافت شد', 'ar': 'شكر مستلم',
    'he': 'התקבלה תודה', 'tr': 'Teşekkür alındı', 'ko': '감사 받음', 'ja': '感謝を受け取りました'},
  'attention.kind.appreciation.recognition': {
    'en': 'Recognition received', 'zh-CN': '收到认可', 'ru': 'Получено признание',
    'hi': 'मान्यता प्राप्त', 'fa': 'قدردانی دریافت شد', 'ar': 'تقدير مستلم',
    'he': 'התקבלה הכרה', 'tr': 'Takdir alındı', 'ko': '인정 받음', 'ja': '称賛を受け取りました'},
  'attention.kind.task.rework': {
    'en': 'Task returned for rework', 'zh-CN': '任务被退回返工', 'ru': 'Задача возвращена на доработку',
    'hi': 'कार्य दोहराने के लिए लौटा', 'fa': 'کار برای بازنگری برگشت', 'ar': 'أُعيدت المهمة لإعادة العمل',
    'he': 'משימה הוחזרה לעבודה חוזרת', 'tr': 'Görev düzeltmeye döndü', 'ko': '재작업으로 반환된 작업',
    'ja': 'やり直しに戻されたタスク'},
  'attention.kind.task.assign': {
    'en': 'Task assigned to you', 'zh-CN': '分配给你的任务', 'ru': 'Задача назначена вам',
    'hi': 'कार्य आपको सौंपा गया', 'fa': 'کار به شما محول شد', 'ar': 'مهمة أُسندت إليك',
    'he': 'משימה הוקצתה לך', 'tr': 'Size atanan görev', 'ko': '나에게 할당된 작업',
    'ja': 'あなたに割り当てられたタスク'},
  'attention.state.ROUTED': {
    'en': 'colleagues notified', 'zh-CN': '已通知同事', 'ru': 'коллеги уведомлены',
    'hi': 'सहकर्मियों को सूचित', 'fa': 'همکاران مطلع شدند', 'ar': 'تم إشعار الزملاء',
    'he': 'העמיתים עודכנו', 'tr': 'iş arkadaşları bilgilendirildi', 'ko': '동료에게 알림',
    'ja': '同僚に通知済み'},
  'attention.state.UNRESOLVED': {
    'en': 'no helper found yet', 'zh-CN': '暂未找到帮助者', 'ru': 'помощник пока не найден',
    'hi': 'अभी कोई मददकर्ता नहीं', 'fa': 'هنوز کمک‌کننده‌ای یافت نشد', 'ar': 'لم يُعثر على مساعد بعد',
    'he': 'עוד לא נמצא עוזר', 'tr': 'henüz yardımcı bulunamadı', 'ko': '아직 도움자 없음',
    'ja': 'ヘルパー未割当'},
  'attention.state.ESCALATED': {
    'en': 'escalated to a manager', 'zh-CN': '已升级给经理', 'ru': 'эскалировано руководителю',
    'hi': 'मैनेजर को एस्केलेट किया गया', 'fa': 'به مدیر ارجاع شد', 'ar': 'صُعّد إلى مدير',
    'he': 'הועבר למנהל', 'tr': 'yöneticiye yükseltildi', 'ko': '매니저에게 에스컬레이션됨',
    'ja': 'マネージャーにエスカレーション'},
  'attention.state.ACCEPTED': {
    'en': 'accepted by a helper', 'zh-CN': '已有帮助者接受', 'ru': 'принято помощником',
    'hi': 'मददकर्ता ने स्वीकार किया', 'fa': 'توسط کمک‌کننده پذیرفته شد', 'ar': 'قبلها مساعد',
    'he': 'התקבלה על ידי עוזר', 'tr': 'bir yardımcı kabul etti', 'ko': '도움자가 수락함',
    'ja': 'ヘルパーが受諾'},
  'attention.action.confirm': {
    'en': 'Confirm', 'zh-CN': '确认', 'ru': 'Подтвердить', 'hi': 'पुष्टि करें',
    'fa': 'تأیید', 'ar': 'تأكيد', 'he': 'אישור', 'tr': 'Onayla', 'ko': '확인', 'ja': '確認'},
  'attention.action.finish': {
    'en': 'Finish', 'zh-CN': '完成', 'ru': 'Завершить', 'hi': 'पूर्ण करें',
    'fa': 'اتمام', 'ar': 'إتمام', 'he': 'סיום', 'tr': 'Tamamla', 'ko': '완료', 'ja': '完了'},
  'attention.action.accept': {
    'en': 'Accept', 'zh-CN': '接受', 'ru': 'Принять', 'hi': 'स्वीकार करें',
    'fa': 'پذیرفتن', 'ar': 'قبول', 'he': 'קבלה', 'tr': 'Kabul et', 'ko': '수락', 'ja': '受諾'},
  'attention.action.decide': {
    'en': 'Decide', 'zh-CN': '决定', 'ru': 'Решить', 'hi': 'निर्णय करें',
    'fa': 'تصمیم', 'ar': 'قرار', 'he': 'החלטה', 'tr': 'Karar ver', 'ko': '결정', 'ja': '決定'},
  'attention.action.review': {
    'en': 'Review', 'zh-CN': '查看', 'ru': 'Проверить', 'hi': 'समीक्षा',
    'fa': 'بررسی', 'ar': 'مراجعة', 'he': 'סקירה', 'tr': 'İncele', 'ko': '검토', 'ja': '確認'},
  'flow.waitingDecisions': {
    'en': 'Waiting decisions', 'zh-CN': '等待中的决定', 'ru': 'Ожидающие решения',
    'hi': 'लंबित निर्णय', 'fa': 'تصمیم‌های در انتظار', 'ar': 'قرارات معلقة',
    'he': 'החלטות ממתינות', 'tr': 'Bekleyen kararlar', 'ko': '대기 중인 결정', 'ja': '待機中の決定'},
  'flow.unresolvedHelp': {
    'en': 'Help & blockers', 'zh-CN': '帮助与阻塞', 'ru': 'Помощь и блокировки',
    'hi': 'मदद और रुकावटें', 'fa': 'کمک و گلوگاه‌ها', 'ar': 'المساعدة والعوائق',
    'he': 'עזרה וחסמים', 'tr': 'Yardım ve engelleyiciler', 'ko': '도움 및 차단 요소',
    'ja': 'ヘルプとブロッカー'},
  'flow.incentiveFlow': {
    'en': 'Incentive flow', 'zh-CN': '激励流转', 'ru': 'Движение поощрений',
    'hi': 'प्रोत्साहन प्रवाह', 'fa': 'جریان پاداش', 'ar': 'تدفق الحوافز',
    'he': 'זרימת תמריצים', 'tr': 'Teşvik akışı', 'ko': '인센티브 흐름', 'ja': 'インセンティブフロー'},
  'flow.resolvedRecently': {
    'en': 'Resolved recently', 'zh-CN': '最近已解决', 'ru': 'Недавно решено',
    'hi': 'हाल ही में हल', 'fa': 'اخیراً حل‌شده', 'ar': 'حُل مؤخرًا',
    'he': 'נפתר לאחרונה', 'tr': 'Yakında çözülen', 'ko': '최근 해결됨', 'ja': '最近解決'},
  'flow.noDecisions': {
    'en': 'No decisions waiting', 'zh-CN': '没有等待中的决定', 'ru': 'Нет ожидающих решений',
    'hi': 'कोई लंबित निर्णय नहीं', 'fa': 'تصمیمی در انتظار نیست', 'ar': 'لا قرارات معلقة',
    'he': 'אין החלטות ממתינות', 'tr': 'Bekleyen karar yok', 'ko': '대기 중인 결정 없음',
    'ja': '待機中の決定はありません'},
  'flow.noHelp': {
    'en': 'No unresolved help', 'zh-CN': '没有未解决的帮助', 'ru': 'Нет нерешённых запросов',
    'hi': 'कोई अनसुलझी मदद नहीं', 'fa': 'کمک حل‌ناشده‌ای نیست', 'ar': 'لا مساعدة عالقة',
    'he': 'אין בקשות עזרה פתוחות', 'tr': 'Çözülmemiş yardım yok', 'ko': '미해결 도움 없음',
    'ja': '未解決のヘルプはありません'},
  'flow.noResolved': {
    'en': 'Nothing resolved recently', 'zh-CN': '最近没有已解决的事项', 'ru': 'Недавно ничего не решено',
    'hi': 'हाल ही में कुछ हल नहीं हुआ', 'fa': 'اخیراً چیزی حل نشده', 'ar': 'لا شيء حُل مؤخرًا',
    'he': 'שום דבר לא נפתר לאחרונה', 'tr': 'Yakında çözülen bir şey yok', 'ko': '최근 해결된 항목 없음',
    'ja': '最近解決した項目はありません'},
  'flow.stat.issued': {
    'en': 'Issued', 'zh-CN': '已发放', 'ru': 'Выдано', 'hi': 'जारी',
    'fa': 'صادرشده', 'ar': 'صدر', 'he': 'הונפק', 'tr': 'Verildi', 'ko': '지급됨', 'ja': '発行済み'},
  'flow.stat.pending': {
    'en': 'Pending', 'zh-CN': '待处理', 'ru': 'Ожидает', 'hi': 'लंबित',
    'fa': 'در انتظار', 'ar': 'معلق', 'he': 'ממתין', 'tr': 'Bekliyor', 'ko': '대기 중', 'ja': '保留中'},
  'flow.stat.held': {
    'en': 'Held for review', 'zh-CN': '待复核', 'ru': 'На проверке', 'hi': 'समीक्षा में',
    'fa': 'در بازبینی', 'ar': 'قيد المراجعة', 'he': 'בבדיקה', 'tr': 'İncelemede',
    'ko': '검토 보류', 'ja': 'レビュー保留'},
  'flow.stat.rejected': {
    'en': 'Rejected', 'zh-CN': '已拒绝', 'ru': 'Отклонено', 'hi': 'अस्वीकृत',
    'fa': 'ردشده', 'ar': 'مرفوض', 'he': 'נדחה', 'tr': 'Reddedildi', 'ko': '거절됨', 'ja': '却下'},
  'flow.stat.safeguarded': {
    'en': 'Safeguarded', 'zh-CN': '已保护', 'ru': 'Защищено', 'hi': 'सुरक्षित',
    'fa': 'محافظت‌شده', 'ar': 'محمي', 'he': 'מוגן', 'tr': 'Korundu', 'ko': '보호됨', 'ja': '保護済み'},
  'flow.windowDays': {
    'en': 'Last {{{days}}} days', 'zh-CN': '最近 {{{days}}} 天', 'ru': 'Последние {{{days}}} дней',
    'hi': 'पिछले {{{days}}} दिन', 'fa': '{{{days}}} روز گذشته', 'ar': 'آخر {{{days}}} يومًا',
    'he': '{{{days}}} הימים האחרונים', 'tr': 'Son {{{days}}} gün', 'ko': '최근 {{days}}일',
    'ja': '過去 {{{days}}} 日'},
}

REPLACE: dict[str, dict[str, str]] = {
  'page.attention.subtitle': {
    'en': 'What needs you right now', 'zh-CN': '现在需要你的事项', 'ru': 'Что требует вашего внимания',
    'hi': 'अभी जो आपको चाहिए', 'fa': 'چیزی که هم‌اکنون به شما نیاز دارد', 'ar': 'ما يحتاجك الآن',
    'he': 'מה שצריך אותך כרגע', 'tr': 'Şu anda size ihtiyaç duyanlar', 'ko': '지금 내가 필요한 곳',
    'ja': '今あなたが必要なもの'},
  'attention.emptyHint': {
    'en': 'Only things that need you, wait on someone, or changed meaningfully appear here.',
    'zh-CN': '只有需要你处理、等待他人或有重要变化的事项才会出现在这里。',
    'ru': 'Здесь появляются только то, что требует вас, ожидает других или важно изменилось.',
    'hi': 'यहां केवल वही दिखता है जिसे आप चाहिए, जो किसी की प्रतीक्षा में है या जो अर्थपूर्ण रूप से बदला है।',
    'fa': 'فقط مواردی که به شما نیاز دارند، در انتظار کسی هستند یا معنادار تغییر کرده‌اند اینجا می‌آیند.',
    'ar': 'تظهر هنا فقط الأمور التي تحتاجك أو تنتظر غيرك أو تغيرت بشكل مهم.',
    'he': 'מופיעים כאן רק דברים שצריכים אותך, ממתינים למישהו או השתנו באופן משמעותי.',
    'tr': 'Yalnızca sizi gerektiren, birini bekleyen veya önemli ölçüde değişen şeyler burada görünür.',
    'ko': '내 조치가 필요하거나, 다른 사람을 기다리거나, 의미 있게 변경된 항목만 여기에 표시됩니다.',
    'ja': 'あなたの対応が必要なもの、誰かを待っているもの、重要な変化があったものだけがここに表示されます。'},
}

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
    out = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    path.write_bytes(out.replace('\n', '\r\n').encode('utf-8'))
    print(f'{loc}: +{added} keys, {replaced} replaced -> {len(data)} total')
print('done')
