# CVE Localization UX Review v1.3

Contextual UX language pass for eight non-English locales. `en.json` remains the key source; the manually approved `fa.json` is unchanged.

## zh-CN
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

## ar
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

## ja
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

## tr
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

## ru
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

## he
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

## ko
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

## hi
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

## Unchanged locales
- en.json byte-for-byte unchanged: PASS
- fa.json byte-for-byte unchanged: PASS

## QA summary
- zh-CN: JSON=PASS, keys=PASS, placeholders=PASS, empty=0, English leakage=0, raw enum leakage=0, fallback prefixes=0
- ar: JSON=PASS, keys=PASS, placeholders=PASS, empty=0, English leakage=0, raw enum leakage=0, fallback prefixes=0
- ja: JSON=PASS, keys=PASS, placeholders=PASS, empty=0, English leakage=0, raw enum leakage=0, fallback prefixes=0
- tr: JSON=PASS, keys=PASS, placeholders=PASS, empty=0, English leakage=0, raw enum leakage=0, fallback prefixes=0
- ru: JSON=PASS, keys=PASS, placeholders=PASS, empty=0, English leakage=0, raw enum leakage=0, fallback prefixes=0
- he: JSON=PASS, keys=PASS, placeholders=PASS, empty=0, English leakage=0, raw enum leakage=0, fallback prefixes=0
- ko: JSON=PASS, keys=PASS, placeholders=PASS, empty=0, English leakage=0, raw enum leakage=0, fallback prefixes=0
- hi: JSON=PASS, keys=PASS, placeholders=PASS, empty=0, English leakage=0, raw enum leakage=0, fallback prefixes=0
