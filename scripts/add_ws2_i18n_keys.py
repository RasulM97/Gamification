"""One-off codegen: inject the WS2 provenance + Admin IA keys into all 10 locales.

Same mechanics as add_i18n_keys.py: every key gets a real translation per
locale, placeholders ({{name}} etc.) stay byte-identical across locales,
files are written with indent=2 and CRLF endings. Two operations:
  ADDED   — new keys (error if the key already exists)
  UPDATED — business-language renames of existing labels (error if missing)
src/i18n/parity.test.ts enforces key and placeholder parity.
"""
import json
from pathlib import Path

LOCALES = Path(__file__).resolve().parent.parent / 'src' / 'i18n' / 'locales'
ALL_LOCALES = ['en', 'zh-CN', 'ru', 'hi', 'fa', 'ar', 'he', 'tr', 'ko', 'ja']

# key -> {locale: text}
ADDED: dict[str, dict[str, str]] = {}
UPDATED: dict[str, dict[str, str]] = {}


def add(key: str, **loc: str) -> None:
    ADDED[key] = loc


def update(key: str, **loc: str) -> None:
    UPDATED[key] = loc


# ── English (canonical) ─────────────────────────────────────────────────────
EN = {
  'provenance.event.github.pull_request.merged': 'A merged pull request',
  'provenance.event.internal.help.confirmed': 'Confirmed help to a colleague',
  'provenance.event.internal.peer.thanks': 'A thank-you from a colleague',
  'provenance.event.unknown': 'Recorded activity',
  'provenance.drawer.title': 'About this incentive',
  'provenance.walletWhy': 'Why?',
  'provenance.noData': 'Details are not available for this entry.',
  'provenance.status.ISSUED': 'Paid',
  'provenance.status.REVERSED': 'Reversed',
  'provenance.what': 'What happened',
  'provenance.why': 'Why',
  'provenance.result': 'Result',
  'provenance.next': 'What this means',
  'provenance.rule': 'Rule',
  'provenance.approvedBy': 'Approved by {{name}}',
  'provenance.reversedNote': 'Reversed: {{reason}}',
  'provenance.reversalReason.SOURCE_REVERTED': 'the source was reverted',
  'provenance.reversalReason.INVALIDATED': 'the payout was invalidated',
  'provenance.reversalReason.ADMIN_CORRECTION': 'an administrator correction',
  'provenance.reversalReason.DUPLICATE_EXTERNAL_OUTCOME': 'a duplicate external outcome',
  'provenance.noApprovalNeeded': 'No approval was required.',
  'provenance.next.issued': 'Nothing to do — the Coins are in your balance.',
  'provenance.next.reversed': 'The Coins were returned. Ask your administrator if this looks wrong.',
  'provenance.context.title': 'Approval context',
  'provenance.whyNeeded': 'Why your decision is needed',
  'provenance.whyNeeded.POLICY': 'Company policy requires approval for this incentive.',
  'provenance.whyNeeded.INCENTIVE_SAFETY': 'Automatic safety checks flagged this incentive for human review.',
  'provenance.yourAuthority': 'Your authority: {{role}}',
  'provenance.evidence': 'Evidence',
  'provenance.safety.CLEAR': 'Passed automatic safety checks',
  'provenance.safety.OBSERVE': 'Under automatic observation',
  'provenance.safety.REQUIRE_REVIEW': 'Flagged by automatic safety checks',
  'provenance.safety.SUPPRESS_INCENTIVE': 'Held back by automatic safety checks',
  'provenance.consequence': 'Consequence',
  'provenance.consequence.approve': 'Approving pays {{coins}} Coins to {{name}}.',
  'provenance.consequence.reject': 'Rejecting means no payout.',
  'provenance.consequence.executed': 'This decision was already executed — see the payout history.',
  'provenance.summary.title': 'Summary',
  'provenance.technical': 'Technical detail',
  'admin.section.organization': 'Organization',
  'admin.section.configuration': 'Configuration',
  'admin.section.audit': 'Audit & economics',
  'admin.section.development': 'Development',
  'admin.audit.note': 'Full history:',
}
for k, v in EN.items():
    add(k, en=v)

UPDATED_EN = {
  'page.admin.subtitle': 'Organization, configuration and audit — the company control plane',
  'page.incentives.subtitle': 'Approvals, reward rules, policies and safety of the incentive pipeline',
  'incentives.tab.rules': 'Reward rules',
  'incentives.tab.policies': 'Payout policies',
  'incentives.tab.safety': 'Safety checks',
  'incentives.tab.shadow': 'What-if preview',
}
for k, v in UPDATED_EN.items():
    update(k, en=v)

# ── 中文（简体） ─────────────────────────────────────────────────────────────
ZH = {
  'provenance.event.github.pull_request.merged': '一个已合并的拉取请求',
  'provenance.event.internal.help.confirmed': '已确认的同事帮助',
  'provenance.event.internal.peer.thanks': '来自同事的感谢',
  'provenance.event.unknown': '已记录的活动',
  'provenance.drawer.title': '关于这笔激励',
  'provenance.walletWhy': '为什么？',
  'provenance.noData': '此条目暂无详细信息。',
  'provenance.status.ISSUED': '已发放',
  'provenance.status.REVERSED': '已撤销',
  'provenance.what': '发生了什么',
  'provenance.why': '原因',
  'provenance.result': '结果',
  'provenance.next': '这意味着什么',
  'provenance.rule': '规则',
  'provenance.approvedBy': '由 {{name}} 批准',
  'provenance.reversedNote': '已撤销：{{reason}}',
  'provenance.reversalReason.SOURCE_REVERTED': '来源已被回退',
  'provenance.reversalReason.INVALIDATED': '该笔发放已失效',
  'provenance.reversalReason.ADMIN_CORRECTION': '管理员更正',
  'provenance.reversalReason.DUPLICATE_EXTERNAL_OUTCOME': '外部结果重复',
  'provenance.noApprovalNeeded': '无需审批。',
  'provenance.next.issued': '无需操作——Coins 已在您的余额中。',
  'provenance.next.reversed': 'Coins 已被退回。如有疑问请联系管理员。',
  'provenance.context.title': '审批背景',
  'provenance.whyNeeded': '为什么需要您的决定',
  'provenance.whyNeeded.POLICY': '公司政策要求这笔激励经过审批。',
  'provenance.whyNeeded.INCENTIVE_SAFETY': '自动安全检查将此激励标记为需要人工复核。',
  'provenance.yourAuthority': '您的权限：{{role}}',
  'provenance.evidence': '依据',
  'provenance.safety.CLEAR': '已通过自动安全检查',
  'provenance.safety.OBSERVE': '处于自动观察中',
  'provenance.safety.REQUIRE_REVIEW': '被自动安全检查标记',
  'provenance.safety.SUPPRESS_INCENTIVE': '被自动安全检查暂缓',
  'provenance.consequence': '后果',
  'provenance.consequence.approve': '批准将向 {{name}} 支付 {{coins}} Coins。',
  'provenance.consequence.reject': '拒绝则不会发放。',
  'provenance.consequence.executed': '该决定已执行——请查看发放历史。',
  'provenance.summary.title': '摘要',
  'provenance.technical': '技术细节',
  'admin.section.organization': '组织',
  'admin.section.configuration': '配置',
  'admin.section.audit': '审计与经济',
  'admin.section.development': '开发',
  'admin.audit.note': '完整历史：',
}
for k, v in ZH.items():
    ADDED[k]['zh-CN'] = v

ZH_UP = {
  'page.admin.subtitle': '组织、配置与审计——公司控制面板',
  'page.incentives.subtitle': '激励流水线的审批、奖励规则、政策与安全',
  'incentives.tab.rules': '奖励规则',
  'incentives.tab.policies': '发放政策',
  'incentives.tab.safety': '安全检查',
  'incentives.tab.shadow': '模拟预览',
}
for k, v in ZH_UP.items():
    UPDATED[k]['zh-CN'] = v

# ── Русский ──────────────────────────────────────────────────────────────────
RU = {
  'provenance.event.github.pull_request.merged': 'Слитый pull-запрос',
  'provenance.event.internal.help.confirmed': 'Подтверждённая помощь коллеге',
  'provenance.event.internal.peer.thanks': 'Благодарность от коллеги',
  'provenance.event.unknown': 'Записанное событие',
  'provenance.drawer.title': 'Об этом поощрении',
  'provenance.walletWhy': 'Почему?',
  'provenance.noData': 'Для этой записи нет подробностей.',
  'provenance.status.ISSUED': 'Выплачено',
  'provenance.status.REVERSED': 'Отменено',
  'provenance.what': 'Что произошло',
  'provenance.why': 'Почему',
  'provenance.result': 'Результат',
  'provenance.next': 'Что это значит',
  'provenance.rule': 'Правило',
  'provenance.approvedBy': 'Одобрил(а): {{name}}',
  'provenance.reversedNote': 'Отменено: {{reason}}',
  'provenance.reversalReason.SOURCE_REVERTED': 'источник был отменён',
  'provenance.reversalReason.INVALIDATED': 'выплата аннулирована',
  'provenance.reversalReason.ADMIN_CORRECTION': 'корректировка администратора',
  'provenance.reversalReason.DUPLICATE_EXTERNAL_OUTCOME': 'дублирующий внешний результат',
  'provenance.noApprovalNeeded': 'Одобрение не требовалось.',
  'provenance.next.issued': 'Ничего делать не нужно — монеты уже на вашем балансе.',
  'provenance.next.reversed': 'Монеты возвращены. Если это ошибка, обратитесь к администратору.',
  'provenance.context.title': 'Контекст решения',
  'provenance.whyNeeded': 'Почему нужно ваше решение',
  'provenance.whyNeeded.POLICY': 'Политика компании требует одобрения этого поощрения.',
  'provenance.whyNeeded.INCENTIVE_SAFETY': 'Автоматические проверки отметили это поощрение для ручной проверки.',
  'provenance.yourAuthority': 'Ваши полномочия: {{role}}',
  'provenance.evidence': 'Основания',
  'provenance.safety.CLEAR': 'Автоматические проверки пройдены',
  'provenance.safety.OBSERVE': 'Под автоматическим наблюдением',
  'provenance.safety.REQUIRE_REVIEW': 'Отмечено автоматическими проверками',
  'provenance.safety.SUPPRESS_INCENTIVE': 'Приостановлено автоматическими проверками',
  'provenance.consequence': 'Последствия',
  'provenance.consequence.approve': 'Одобрение выплатит {{coins}} монет пользователю {{name}}.',
  'provenance.consequence.reject': 'Отклонение означает отсутствие выплаты.',
  'provenance.consequence.executed': 'Решение уже исполнено — см. историю выплат.',
  'provenance.summary.title': 'Кратко',
  'provenance.technical': 'Технические детали',
  'admin.section.organization': 'Организация',
  'admin.section.configuration': 'Настройки',
  'admin.section.audit': 'Аудит и экономика',
  'admin.section.development': 'Разработка',
  'admin.audit.note': 'Полная история:',
}
for k, v in RU.items():
    ADDED[k]['ru'] = v

RU_UP = {
  'page.admin.subtitle': 'Организация, настройки и аудит — панель управления компанией',
  'page.incentives.subtitle': 'Одобрения, правила вознаграждения, политики и безопасность конвейера поощрений',
  'incentives.tab.rules': 'Правила вознаграждения',
  'incentives.tab.policies': 'Политики выплат',
  'incentives.tab.safety': 'Проверки безопасности',
  'incentives.tab.shadow': 'Пробный просмотр',
}
for k, v in RU_UP.items():
    UPDATED[k]['ru'] = v

# ── हिन्दी ───────────────────────────────────────────────────────────────────
HI = {
  'provenance.event.github.pull_request.merged': 'एक मर्ज किया गया पुल अनुरोध',
  'provenance.event.internal.help.confirmed': 'सहकर्मी की पुष्टि की गई मदद',
  'provenance.event.internal.peer.thanks': 'सहकर्मी का धन्यवाद',
  'provenance.event.unknown': 'दर्ज गतिविधि',
  'provenance.drawer.title': 'इस प्रोत्साहन के बारे में',
  'provenance.walletWhy': 'क्यों?',
  'provenance.noData': 'इस प्रविष्टि के लिए विवरण उपलब्ध नहीं है।',
  'provenance.status.ISSUED': 'भुगतान किया गया',
  'provenance.status.REVERSED': 'रद्द किया गया',
  'provenance.what': 'क्या हुआ',
  'provenance.why': 'क्यों',
  'provenance.result': 'परिणाम',
  'provenance.next': 'इसका मतलब',
  'provenance.rule': 'नियम',
  'provenance.approvedBy': '{{name}} द्वारा स्वीकृत',
  'provenance.reversedNote': 'रद्द किया गया: {{reason}}',
  'provenance.reversalReason.SOURCE_REVERTED': 'स्रोत वापस लिया गया',
  'provenance.reversalReason.INVALIDATED': 'भुगतान अमान्य किया गया',
  'provenance.reversalReason.ADMIN_CORRECTION': 'प्रशासक सुधार',
  'provenance.reversalReason.DUPLICATE_EXTERNAL_OUTCOME': 'डुप्लिकेट बाहरी परिणाम',
  'provenance.noApprovalNeeded': 'किसी स्वीकृति की आवश्यकता नहीं थी।',
  'provenance.next.issued': 'कुछ करने की ज़रूरत नहीं — Coins आपके बैलेंस में हैं।',
  'provenance.next.reversed': 'Coins वापस कर दिए गए। यदि यह गलत लगे तो अपने प्रशासक से पूछें।',
  'provenance.context.title': 'स्वीकृति संदर्भ',
  'provenance.whyNeeded': 'आपके निर्णय की आवश्यकता क्यों है',
  'provenance.whyNeeded.POLICY': 'कंपनी नीति के अनुसार इस प्रोत्साहन के लिए स्वीकृति आवश्यक है।',
  'provenance.whyNeeded.INCENTIVE_SAFETY': 'स्वचालित सुरक्षा जाँचों ने इस प्रोत्साहन को मानव समीक्षा के लिए चिह्नित किया।',
  'provenance.yourAuthority': 'आपका अधिकार: {{role}}',
  'provenance.evidence': 'आधार',
  'provenance.safety.CLEAR': 'स्वचालित सुरक्षा जाँचें पास',
  'provenance.safety.OBSERVE': 'स्वचालित निगरानी में',
  'provenance.safety.REQUIRE_REVIEW': 'स्वचालित सुरक्षा जाँचों द्वारा चिह्नित',
  'provenance.safety.SUPPRESS_INCENTIVE': 'स्वचालित सुरक्षा जाँचों द्वारा रोका गया',
  'provenance.consequence': 'परिणाम',
  'provenance.consequence.approve': 'स्वीकृत करने पर {{name}} को {{coins}} Coins मिलेंगे।',
  'provenance.consequence.reject': 'अस्वीकार करने पर कोई भुगतान नहीं होगा।',
  'provenance.consequence.executed': 'यह निर्णय पहले ही लागू हो चुका है — भुगतान इतिहास देखें।',
  'provenance.summary.title': 'सारांश',
  'provenance.technical': 'तकनीकी विवरण',
  'admin.section.organization': 'संगठन',
  'admin.section.configuration': 'कॉन्फ़िगरेशन',
  'admin.section.audit': 'ऑडिट और अर्थव्यवस्था',
  'admin.section.development': 'विकास',
  'admin.audit.note': 'पूरा इतिहास:',
}
for k, v in HI.items():
    ADDED[k]['hi'] = v

HI_UP = {
  'page.admin.subtitle': 'संगठन, कॉन्फ़िगरेशन और ऑडिट — कंपनी कंट्रोल प्लेन',
  'page.incentives.subtitle': 'प्रोत्साहन पाइपलाइन की स्वीकृतियाँ, इनाम नियम, नीतियाँ और सुरक्षा',
  'incentives.tab.rules': 'इनाम नियम',
  'incentives.tab.policies': 'भुगतान नीतियाँ',
  'incentives.tab.safety': 'सुरक्षा जाँचें',
  'incentives.tab.shadow': 'पूर्वावलोकन (प्रयोगात्मक)',
}
for k, v in HI_UP.items():
    UPDATED[k]['hi'] = v

# ── فارسی ────────────────────────────────────────────────────────────────────
FA = {
  'provenance.event.github.pull_request.merged': 'یک درخواست ادغام ادغام‌شده',
  'provenance.event.internal.help.confirmed': 'کمک تأییدشده به یک همکار',
  'provenance.event.internal.peer.thanks': 'تشکر از یک همکار',
  'provenance.event.unknown': 'فعالیت ثبت‌شده',
  'provenance.drawer.title': 'درباره این پاداش',
  'provenance.walletWhy': 'چرا؟',
  'provenance.noData': 'جزئیاتی برای این مورد در دسترس نیست.',
  'provenance.status.ISSUED': 'پرداخت شده',
  'provenance.status.REVERSED': 'برگردانده شده',
  'provenance.what': 'چه اتفاقی افتاد',
  'provenance.why': 'چرا',
  'provenance.result': 'نتیجه',
  'provenance.next': 'یعنی چه',
  'provenance.rule': 'قانون',
  'provenance.approvedBy': 'تأیید شده توسط {{name}}',
  'provenance.reversedNote': 'برگردانده شد: {{reason}}',
  'provenance.reversalReason.SOURCE_REVERTED': 'منبع برگردانده شد',
  'provenance.reversalReason.INVALIDATED': 'پرداخت باطل شد',
  'provenance.reversalReason.ADMIN_CORRECTION': 'اصلاحیه مدیر',
  'provenance.reversalReason.DUPLICATE_EXTERNAL_OUTCOME': 'نتیجه خارجی تکراری',
  'provenance.noApprovalNeeded': 'تأییدی لازم نبود.',
  'provenance.next.issued': 'کاری لازم نیست — سکه‌ها در موجودی شماست.',
  'provenance.next.reversed': 'سکه‌ها برگردانده شدند. اگر اشتباه به نظر می‌رسد، از مدیر بپرسید.',
  'provenance.context.title': 'زمینه تأیید',
  'provenance.whyNeeded': 'چرا تصمیم شما لازم است',
  'provenance.whyNeeded.POLICY': 'خط‌مشی شرکت برای این پاداش تأیید می‌خواهد.',
  'provenance.whyNeeded.INCENTIVE_SAFETY': 'بررسی‌های خودکار ایمنی این پاداش را برای بازبینی انسانی علامت‌گذاری کرده‌اند.',
  'provenance.yourAuthority': 'اختیار شما: {{role}}',
  'provenance.evidence': 'شواهد',
  'provenance.safety.CLEAR': 'بررسی‌های خودکار ایمنی را گذرانده',
  'provenance.safety.OBSERVE': 'تحت نظارت خودکار',
  'provenance.safety.REQUIRE_REVIEW': 'توسط بررسی‌های خودکار علامت‌گذاری شده',
  'provenance.safety.SUPPRESS_INCENTIVE': 'توسط بررسی‌های خودکار متوقف شده',
  'provenance.consequence': 'پیامد',
  'provenance.consequence.approve': 'تأیید، {{coins}} سکه به {{name}} می‌پردازد.',
  'provenance.consequence.reject': 'رد کردن یعنی هیچ پرداختی انجام نمی‌شود.',
  'provenance.consequence.executed': 'این تصمیم قبلاً اجرا شده است — تاریخچه پرداخت را ببینید.',
  'provenance.summary.title': 'خلاصه',
  'provenance.technical': 'جزئیات فنی',
  'admin.section.organization': 'سازمان',
  'admin.section.configuration': 'پیکربندی',
  'admin.section.audit': 'حسابرسی و اقتصاد',
  'admin.section.development': 'توسعه',
  'admin.audit.note': 'تاریخچه کامل:',
}
for k, v in FA.items():
    ADDED[k]['fa'] = v

FA_UP = {
  'page.admin.subtitle': 'سازمان، پیکربندی و حسابرسی — صفحه کنترل شرکت',
  'page.incentives.subtitle': 'تأییدها، قوانین پاداش، خط‌مشی‌ها و ایمنی خط لوله انگیزشی',
  'incentives.tab.rules': 'قوانین پاداش',
  'incentives.tab.policies': 'خط‌مشی‌های پرداخت',
  'incentives.tab.safety': 'بررسی‌های ایمنی',
  'incentives.tab.shadow': 'پیش‌نمایش آزمایشی',
}
for k, v in FA_UP.items():
    UPDATED[k]['fa'] = v

# ── العربية ──────────────────────────────────────────────────────────────────
AR = {
  'provenance.event.github.pull_request.merged': 'طلب سحب تم دمجه',
  'provenance.event.internal.help.confirmed': 'مساعدة مؤكدة لزميل',
  'provenance.event.internal.peer.thanks': 'شكر من زميل',
  'provenance.event.unknown': 'نشاط مسجل',
  'provenance.drawer.title': 'حول هذا الحافز',
  'provenance.walletWhy': 'لماذا؟',
  'provenance.noData': 'لا تتوفر تفاصيل لهذا القيد.',
  'provenance.status.ISSUED': 'مدفوع',
  'provenance.status.REVERSED': 'معكوس',
  'provenance.what': 'ماذا حدث',
  'provenance.why': 'لماذا',
  'provenance.result': 'النتيجة',
  'provenance.next': 'ماذا يعني هذا',
  'provenance.rule': 'القاعدة',
  'provenance.approvedBy': 'اعتُمد بواسطة {{name}}',
  'provenance.reversedNote': 'تم عكسه: {{reason}}',
  'provenance.reversalReason.SOURCE_REVERTED': 'تم التراجع عن المصدر',
  'provenance.reversalReason.INVALIDATED': 'تم إبطال الدفعة',
  'provenance.reversalReason.ADMIN_CORRECTION': 'تصحيح من المسؤول',
  'provenance.reversalReason.DUPLICATE_EXTERNAL_OUTCOME': 'نتيجة خارجية مكررة',
  'provenance.noApprovalNeeded': 'لم تكن هناك حاجة إلى اعتماد.',
  'provenance.next.issued': 'لا شيء مطلوب — العملات في رصيدك.',
  'provenance.next.reversed': 'تمت إعادة العملات. اسأل المسؤول إذا بدا ذلك خاطئًا.',
  'provenance.context.title': 'سياق الاعتماد',
  'provenance.whyNeeded': 'لماذا نحتاج قرارك',
  'provenance.whyNeeded.POLICY': 'تتطلب سياسة الشركة اعتماد هذا الحافز.',
  'provenance.whyNeeded.INCENTIVE_SAFETY': 'وضعت فحوصات السلامة التلقائية علامة على هذا الحافز للمراجعة البشرية.',
  'provenance.yourAuthority': 'صلاحيتك: {{role}}',
  'provenance.evidence': 'الأدلة',
  'provenance.safety.CLEAR': 'اجتاز فحوصات السلامة التلقائية',
  'provenance.safety.OBSERVE': 'تحت المراقبة التلقائية',
  'provenance.safety.REQUIRE_REVIEW': 'مُعلَّم من فحوصات السلامة التلقائية',
  'provenance.safety.SUPPRESS_INCENTIVE': 'أوقفته فحوصات السلامة التلقائية',
  'provenance.consequence': 'النتيجة المترتبة',
  'provenance.consequence.approve': 'الاعتماد يدفع {{coins}} عملة إلى {{name}}.',
  'provenance.consequence.reject': 'الرفض يعني عدم الدفع.',
  'provenance.consequence.executed': 'تم تنفيذ هذا القرار بالفعل — راجع سجل الدفعات.',
  'provenance.summary.title': 'الملخص',
  'provenance.technical': 'التفاصيل التقنية',
  'admin.section.organization': 'المؤسسة',
  'admin.section.configuration': 'الإعدادات',
  'admin.section.audit': 'التدقيق والاقتصاد',
  'admin.section.development': 'التطوير',
  'admin.audit.note': 'السجل الكامل:',
}
for k, v in AR.items():
    ADDED[k]['ar'] = v

AR_UP = {
  'page.admin.subtitle': 'المؤسسة والإعدادات والتدقيق — لوحة تحكم الشركة',
  'page.incentives.subtitle': 'اعتمادات وقواعد المكافآت وسياسات وسلامة خط الحوافز',
  'incentives.tab.rules': 'قواعد المكافآت',
  'incentives.tab.policies': 'سياسات الدفع',
  'incentives.tab.safety': 'فحوصات السلامة',
  'incentives.tab.shadow': 'معاينة تجريبية',
}
for k, v in AR_UP.items():
    UPDATED[k]['ar'] = v

# ── עברית ────────────────────────────────────────────────────────────────────
HE = {
  'provenance.event.github.pull_request.merged': 'בקשת משיכה שמוזגה',
  'provenance.event.internal.help.confirmed': 'עזרה מאושרת לעמית',
  'provenance.event.internal.peer.thanks': 'תודה מעמית',
  'provenance.event.unknown': 'פעילות מתועדת',
  'provenance.drawer.title': 'על התמריץ הזה',
  'provenance.walletWhy': 'למה?',
  'provenance.noData': 'אין פרטים זמינים לרשומה זו.',
  'provenance.status.ISSUED': 'שולם',
  'provenance.status.REVERSED': 'בוטל',
  'provenance.what': 'מה קרה',
  'provenance.why': 'למה',
  'provenance.result': 'תוצאה',
  'provenance.next': 'מה זה אומר',
  'provenance.rule': 'כלל',
  'provenance.approvedBy': 'אושר על ידי {{name}}',
  'provenance.reversedNote': 'בוטל: {{reason}}',
  'provenance.reversalReason.SOURCE_REVERTED': 'המקור בוטל',
  'provenance.reversalReason.INVALIDATED': 'התשלום בוטל',
  'provenance.reversalReason.ADMIN_CORRECTION': 'תיקון של מנהל',
  'provenance.reversalReason.DUPLICATE_EXTERNAL_OUTCOME': 'תוצאה חיצונית כפולה',
  'provenance.noApprovalNeeded': 'לא נדרש אישור.',
  'provenance.next.issued': 'אין מה לעשות — המטבעות ביתרה שלך.',
  'provenance.next.reversed': 'המטבעות הוחזרו. אם נראה שגוי, פנה למנהל.',
  'provenance.context.title': 'הקשר האישור',
  'provenance.whyNeeded': 'למה נדרשת ההחלטה שלך',
  'provenance.whyNeeded.POLICY': 'מדיניות החברה דורשת אישור לתמריץ זה.',
  'provenance.whyNeeded.INCENTIVE_SAFETY': 'בדיקות הבטיחות האוטומטיות סימנו תמריץ זה לבדיקה אנושית.',
  'provenance.yourAuthority': 'הסמכות שלך: {{role}}',
  'provenance.evidence': 'ראיות',
  'provenance.safety.CLEAR': 'עבר את בדיקות הבטיחות האוטומטיות',
  'provenance.safety.OBSERVE': 'בתצפית אוטומטית',
  'provenance.safety.REQUIRE_REVIEW': 'סומן על ידי בדיקות הבטיחות האוטומטיות',
  'provenance.safety.SUPPRESS_INCENTIVE': 'נעצר על ידי בדיקות הבטיחות האוטומטיות',
  'provenance.consequence': 'תוצאה',
  'provenance.consequence.approve': 'אישור ישלם {{coins}} מטבעות ל{{name}}.',
  'provenance.consequence.reject': 'דחייה משמעותה ללא תשלום.',
  'provenance.consequence.executed': 'ההחלטה כבר בוצעה — ראה היסטוריית תשלומים.',
  'provenance.summary.title': 'תקציר',
  'provenance.technical': 'פרטים טכניים',
  'admin.section.organization': 'ארגון',
  'admin.section.configuration': 'תצורה',
  'admin.section.audit': 'ביקורת וכלכלה',
  'admin.section.development': 'פיתוח',
  'admin.audit.note': 'היסטוריה מלאה:',
}
for k, v in HE.items():
    ADDED[k]['he'] = v

HE_UP = {
  'page.admin.subtitle': 'ארגון, תצורה וביקורת — מישור הבקרה של החברה',
  'page.incentives.subtitle': 'אישורים, כללי תגמול, מדיניות ובטיחות של צינור התמריצים',
  'incentives.tab.rules': 'כללי תגמול',
  'incentives.tab.policies': 'מדיניות תשלומים',
  'incentives.tab.safety': 'בדיקות בטיחות',
  'incentives.tab.shadow': 'תצוגה מקדימה ניסיונית',
}
for k, v in HE_UP.items():
    UPDATED[k]['he'] = v

# ── Türkçe ───────────────────────────────────────────────────────────────────
TR = {
  'provenance.event.github.pull_request.merged': 'Birleştirilmiş bir pull request',
  'provenance.event.internal.help.confirmed': 'Bir iş arkadaşına onaylanmış yardım',
  'provenance.event.internal.peer.thanks': 'Bir iş arkadaşından teşekkür',
  'provenance.event.unknown': 'Kaydedilen etkinlik',
  'provenance.drawer.title': 'Bu teşvik hakkında',
  'provenance.walletWhy': 'Neden?',
  'provenance.noData': 'Bu kayıt için ayrıntı yok.',
  'provenance.status.ISSUED': 'Ödendi',
  'provenance.status.REVERSED': 'Geri alındı',
  'provenance.what': 'Ne oldu',
  'provenance.why': 'Neden',
  'provenance.result': 'Sonuç',
  'provenance.next': 'Bu ne anlama geliyor',
  'provenance.rule': 'Kural',
  'provenance.approvedBy': '{{name}} tarafından onaylandı',
  'provenance.reversedNote': 'Geri alındı: {{reason}}',
  'provenance.reversalReason.SOURCE_REVERTED': 'kaynak geri alındı',
  'provenance.reversalReason.INVALIDATED': 'ödeme geçersiz kılındı',
  'provenance.reversalReason.ADMIN_CORRECTION': 'yönetici düzeltmesi',
  'provenance.reversalReason.DUPLICATE_EXTERNAL_OUTCOME': 'yinelenen dış sonuç',
  'provenance.noApprovalNeeded': 'Onay gerekmedi.',
  'provenance.next.issued': 'Yapılacak bir şey yok — Coinler bakiyenizde.',
  'provenance.next.reversed': 'Coinler iade edildi. Yanlış görünüyorsa yöneticinize sorun.',
  'provenance.context.title': 'Onay bağlamı',
  'provenance.whyNeeded': 'Kararınız neden gerekli',
  'provenance.whyNeeded.POLICY': 'Şirket politikası bu teşvik için onay gerektiriyor.',
  'provenance.whyNeeded.INCENTIVE_SAFETY': 'Otomatik güvenlik denetimleri bu teşviki insan incelemesi için işaretledi.',
  'provenance.yourAuthority': 'Yetkiniz: {{role}}',
  'provenance.evidence': 'Kanıt',
  'provenance.safety.CLEAR': 'Otomatik güvenlik denetimlerinden geçti',
  'provenance.safety.OBSERVE': 'Otomatik gözlem altında',
  'provenance.safety.REQUIRE_REVIEW': 'Otomatik güvenlik denetimleri tarafından işaretlendi',
  'provenance.safety.SUPPRESS_INCENTIVE': 'Otomatik güvenlik denetimleri tarafından tutuldu',
  'provenance.consequence': 'Sonuç',
  'provenance.consequence.approve': 'Onaylamak {{name}} kullanıcısına {{coins}} Coin öder.',
  'provenance.consequence.reject': 'Reddetmek ödeme yapılmaması demektir.',
  'provenance.consequence.executed': 'Bu karar zaten uygulandı — ödeme geçmişine bakın.',
  'provenance.summary.title': 'Özet',
  'provenance.technical': 'Teknik ayrıntı',
  'admin.section.organization': 'Organizasyon',
  'admin.section.configuration': 'Yapılandırma',
  'admin.section.audit': 'Denetim ve ekonomi',
  'admin.section.development': 'Geliştirme',
  'admin.audit.note': 'Tam geçmiş:',
}
for k, v in TR.items():
    ADDED[k]['tr'] = v

TR_UP = {
  'page.admin.subtitle': 'Organizasyon, yapılandırma ve denetim — şirket kontrol paneli',
  'page.incentives.subtitle': 'Teşvik hattının onayları, ödül kuralları, politikaları ve güvenliği',
  'incentives.tab.rules': 'Ödül kuralları',
  'incentives.tab.policies': 'Ödeme politikaları',
  'incentives.tab.safety': 'Güvenlik denetimleri',
  'incentives.tab.shadow': 'Deneme önizlemesi',
}
for k, v in TR_UP.items():
    UPDATED[k]['tr'] = v

# ── 한국어 ───────────────────────────────────────────────────────────────────
KO = {
  'provenance.event.github.pull_request.merged': '병합된 풀 리퀘스트',
  'provenance.event.internal.help.confirmed': '동료에게 확인된 도움',
  'provenance.event.internal.peer.thanks': '동료의 감사',
  'provenance.event.unknown': '기록된 활동',
  'provenance.drawer.title': '이 인센티브 정보',
  'provenance.walletWhy': '왜?',
  'provenance.noData': '이 항목에 대한 세부 정보가 없습니다.',
  'provenance.status.ISSUED': '지급됨',
  'provenance.status.REVERSED': '취소됨',
  'provenance.what': '무슨 일이 있었나요',
  'provenance.why': '이유',
  'provenance.result': '결과',
  'provenance.next': '의미',
  'provenance.rule': '규칙',
  'provenance.approvedBy': '{{name}} 님이 승인',
  'provenance.reversedNote': '취소됨: {{reason}}',
  'provenance.reversalReason.SOURCE_REVERTED': '원본이 되돌려짐',
  'provenance.reversalReason.INVALIDATED': '지급이 무효화됨',
  'provenance.reversalReason.ADMIN_CORRECTION': '관리자 정정',
  'provenance.reversalReason.DUPLICATE_EXTERNAL_OUTCOME': '중복된 외부 결과',
  'provenance.noApprovalNeeded': '승인이 필요하지 않았습니다.',
  'provenance.next.issued': '할 일이 없습니다 — 코인이 잔액에 있습니다.',
  'provenance.next.reversed': '코인이 반환되었습니다. 잘못된 것 같으면 관리자에게 문의하세요.',
  'provenance.context.title': '승인 맥락',
  'provenance.whyNeeded': '결정이 필요한 이유',
  'provenance.whyNeeded.POLICY': '회사 정책상 이 인센티브는 승인이 필요합니다.',
  'provenance.whyNeeded.INCENTIVE_SAFETY': '자동 안전 검사가 이 인센티브를 사람 검토 대상으로 표시했습니다.',
  'provenance.yourAuthority': '내 권한: {{role}}',
  'provenance.evidence': '근거',
  'provenance.safety.CLEAR': '자동 안전 검사 통과',
  'provenance.safety.OBSERVE': '자동 관찰 중',
  'provenance.safety.REQUIRE_REVIEW': '자동 안전 검사에 의해 표시됨',
  'provenance.safety.SUPPRESS_INCENTIVE': '자동 안전 검사에 의해 보류됨',
  'provenance.consequence': '결과',
  'provenance.consequence.approve': '승인하면 {{name}} 님에게 {{coins}} 코인이 지급됩니다.',
  'provenance.consequence.reject': '거절하면 지급되지 않습니다.',
  'provenance.consequence.executed': '이미 실행된 결정입니다 — 지급 내역을 확인하세요.',
  'provenance.summary.title': '요약',
  'provenance.technical': '기술 세부 정보',
  'admin.section.organization': '조직',
  'admin.section.configuration': '구성',
  'admin.section.audit': '감사 및 경제',
  'admin.section.development': '개발',
  'admin.audit.note': '전체 기록:',
}
for k, v in KO.items():
    ADDED[k]['ko'] = v

KO_UP = {
  'page.admin.subtitle': '조직, 구성 및 감사 — 회사 컨트롤 플레인',
  'page.incentives.subtitle': '인센티브 파이프라인의 승인, 보상 규칙, 정책 및 안전',
  'incentives.tab.rules': '보상 규칙',
  'incentives.tab.policies': '지급 정책',
  'incentives.tab.safety': '안전 검사',
  'incentives.tab.shadow': '시뮬레이션 미리보기',
}
for k, v in KO_UP.items():
    UPDATED[k]['ko'] = v

# ── 日本語 ───────────────────────────────────────────────────────────────────
JA = {
  'provenance.event.github.pull_request.merged': 'マージされたプルリクエスト',
  'provenance.event.internal.help.confirmed': '同僚への確認済みのヘルプ',
  'provenance.event.internal.peer.thanks': '同僚からの感謝',
  'provenance.event.unknown': '記録されたアクティビティ',
  'provenance.drawer.title': 'このインセンティブについて',
  'provenance.walletWhy': 'なぜ？',
  'provenance.noData': 'このエントリの詳細はありません。',
  'provenance.status.ISSUED': '支払い済み',
  'provenance.status.REVERSED': '取り消し済み',
  'provenance.what': '何が起きたか',
  'provenance.why': '理由',
  'provenance.result': '結果',
  'provenance.next': '意味すること',
  'provenance.rule': 'ルール',
  'provenance.approvedBy': '{{name}} が承認',
  'provenance.reversedNote': '取り消し：{{reason}}',
  'provenance.reversalReason.SOURCE_REVERTED': 'ソースが取り消されました',
  'provenance.reversalReason.INVALIDATED': '支払いが無効になりました',
  'provenance.reversalReason.ADMIN_CORRECTION': '管理者による修正',
  'provenance.reversalReason.DUPLICATE_EXTERNAL_OUTCOME': '外部結果の重複',
  'provenance.noApprovalNeeded': '承認は不要でした。',
  'provenance.next.issued': '対応は不要です — コインは残高にあります。',
  'provenance.next.reversed': 'コインは返却されました。不審な場合は管理者に確認してください。',
  'provenance.context.title': '承認のコンテキスト',
  'provenance.whyNeeded': 'あなたの決定が必要な理由',
  'provenance.whyNeeded.POLICY': '会社のポリシーによりこのインセンティブには承認が必要です。',
  'provenance.whyNeeded.INCENTIVE_SAFETY': '自動安全チェックにより、このインセンティブは人的レビュー対象になりました。',
  'provenance.yourAuthority': 'あなたの権限：{{role}}',
  'provenance.evidence': '根拠',
  'provenance.safety.CLEAR': '自動安全チェックに合格',
  'provenance.safety.OBSERVE': '自動観察中',
  'provenance.safety.REQUIRE_REVIEW': '自動安全チェックによりフラグ付け',
  'provenance.safety.SUPPRESS_INCENTIVE': '自動安全チェックにより保留',
  'provenance.consequence': '結果',
  'provenance.consequence.approve': '承認すると {{name}} に {{coins}} コインが支払われます。',
  'provenance.consequence.reject': '却下すると支払われません。',
  'provenance.consequence.executed': 'この決定はすでに実行されています — 支払い履歴をご覧ください。',
  'provenance.summary.title': '概要',
  'provenance.technical': '技術的詳細',
  'admin.section.organization': '組織',
  'admin.section.configuration': '設定',
  'admin.section.audit': '監査と経済',
  'admin.section.development': '開発',
  'admin.audit.note': '完全な履歴：',
}
for k, v in JA.items():
    ADDED[k]['ja'] = v

JA_UP = {
  'page.admin.subtitle': '組織・設定・監査 — 会社のコントロールプレーン',
  'page.incentives.subtitle': 'インセンティブパイプラインの承認・報酬ルール・ポリシー・安全性',
  'incentives.tab.rules': '報酬ルール',
  'incentives.tab.policies': '支払いポリシー',
  'incentives.tab.safety': '安全チェック',
  'incentives.tab.shadow': 'what-if プレビュー',
}
for k, v in JA_UP.items():
    UPDATED[k]['ja'] = v

# ── writer ───────────────────────────────────────────────────────────────────
missing = [(k, loc) for k, tr in ADDED.items() for loc in ALL_LOCALES if loc not in tr]
missing += [(k, loc) for k, tr in UPDATED.items() for loc in ALL_LOCALES if loc not in tr]
assert not missing, f'missing translations: {missing[:5]}'

for loc in ALL_LOCALES:
    path = LOCALES / f'{loc}.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    added = updated = 0
    for key, tr in ADDED.items():
        if key in data:
            raise SystemExit(f'{loc}: key already exists: {key}')
        data[key] = tr[loc]
        added += 1
    for key, tr in UPDATED.items():
        if key not in data:
            raise SystemExit(f'{loc}: key missing for update: {key}')
        data[key] = tr[loc]
        updated += 1
    out = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    path.write_text(out.replace('\n', '\r\n'), encoding='utf-8')
    print(f'{loc}: +{added} added, ~{updated} updated -> {len(data)} total')
print('done')
