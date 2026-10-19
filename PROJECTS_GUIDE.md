# 🧭 دليل تنظيم وتقسيم محادثات مشاريع OdooDB
### شركة العصلي للتجارة (Al-Assali Trading Co.)
**المطور:** عبدالله الخطيب  
**الهدف:** تمكين المستخدم من إدارة المحادثات والمشاريع الفرعية بكفاءة عالية، بحيث تكون كل محادثة مركزة تماماً على برنامج محدد دون تشتيت السياق أو فقدان الذاكرة التاريخية للتطوير.

---

## 📌 فلسفة تنظيم المحادثات (Chat Organization Strategy)

يحتوي مجلد `c:\OdooDB` على **5 برامج رئيسية** متكاملة. للعمل بأعلى درجات الاحترافية مع مساعد الذكاء الاصطناعي وتجنب خلط الملفات، يُنصح دائماً **بفتح محادثة مستقلة لكل برنامج** واتباع التسميات التالية:

```
المحادثات في الواجهة (Chat Threads):
├── 📊 [OdooReportExporter] - مصدر التقارير والتراخيص
├── 🏬 [ShowroomChecker] - فاحص أرصدة المعارض
├── 🏷️ [PriceComparator] - التسعير ومراقبة المنافسين
├── 📱 [ShelfChecker] - تطبيق الأندرويد للهاند هيلد EDA51
└── 🖨️ [ShelfLabelPrinter] - طباعة استيكرات وملصقات الرف
```

---

## 🚀 نماذج البدء السريع لكل محادثة (Starter Prompts)

عندما تفتح محادثة جديدة للعمل على أي برنامج، **انسخ البرومبت السريع الخاص به** والصقه في أول رسالة. هذا البرومبت يوجه الذكاء الاصطناعي مباشرة لقراءة ملف المعمارية وملفات ذلك البرنامج حصرياً:

---

### المسار 1: محادثة [OdooReportExporter]
* **عنوان المحادثة المقترح:** `[OdooReportExporter] - مصدر التقارير الشامل والتراخيص`
* **الملفات المستهدفة:**
  - `c:\OdooDB\app_gui.py` (واجهة التقارير)
  - `c:\OdooDB\exporter_engine.py` (محرك التصدير)
  - `c:\OdooDB\pos_discount_engine.py` (خصومات نقاط البيع)
  - `c:\OdooDB\permissions.py` (الصلاحيات)
  - `c:\OdooDB\licensing.py` و `c:\OdooDB\keygen.py` (الترخيص)
  - `c:\OdooDB\build_standalone.py` (التجميع)
* **برومبت البدء السريع (انسخه كما هو):**
  > أهلاً بك! في هذه المحادثة سنعمل حصرياً على برنامج **OdooReportExporter** (مصدر تقارير أودو الشامل للأسعار والمخزون والتكاليف ونظام التراخيص والصلاحيات).
  > يرجى أولاً قراءة القسم رقم 3 ورقم 8 في ملف `c:\OdooDB\MASTER_SYSTEM_ARCHITECTURE.md` للتعرف على معمارية البرنامج وملفاته.
  > لاحظ أن ملف الواجهة الخاص بهذا البرنامج هو `c:\OdooDB\app_gui.py`. 
  > المطلوب الآن: [اكتب طلبك هنا...]

---

### المسار 2: محادثة [ShowroomChecker]
* **عنوان المحادثة المقترح:** `[ShowroomChecker] - فاحص أرصدة المعارض والمستودعات`
* **الملفات المستهدفة:**
  - `c:\OdooDB\showroom_checker.py` (الواجهة والمنطق)
  - `c:\OdooDB\showroom_config.py` (تصنيف الفروع)
  - `c:\OdooDB\ShowroomChecker.spec` (التجميع)
* **برومبت البدء السريع (انسخه كما هو):**
  > أهلاً بك! في هذه المحادثة سنعمل حصرياً على برنامج **ShowroomChecker** (فاحص ومعاين أرصدة الفروع والمعارض والمستودعات لكل صنف).
  > يرجى أولاً قراءة القسم رقم 4 في ملف `c:\OdooDB\MASTER_SYSTEM_ARCHITECTURE.md`.
  > الملفات الأساسية لهذا البرنامج هي `c:\OdooDB\showroom_checker.py` و `c:\OdooDB\showroom_config.py`.
  > المطلوب الآن: [اكتب طلبك هنا...]

---

### المسار 3: محادثة [PriceComparator]
* **عنوان المحادثة المقترح:** `[PriceComparator] - مساعد التسعير ومراقبة المنافسين`
* **الملفات المستهدفة:**
  - `c:\OdooDB\price_comparator_app.py` (الواجهة الرئيسية)
  - `c:\OdooDB\competitor_scraper.py` (محرك فحص 34 متجراً)
  - `c:\OdooDB\price_intelligence.py` (ذكاء التسعير والضرائب)
  - `c:\OdooDB\odoo_product_lookup.py` (جلب بيانات الصنف من أودو)
  - `c:\OdooDB\build_comparator.py` (سكربت التجميع)
* **برومبت البدء السريع (انسخه كما هو):**
  > أهلاً بك! في هذه المحادثة سنعمل حصرياً على برنامج **PriceComparator** (مساعد التسعير ومراقبة الـ 34 متجراً منافساً بالباركود وتحليل الضرائب وهوامش الأرباح).
  > يرجى أولاً قراءة القسم رقم 5 والقواعد الذهبية في `c:\OdooDB\MASTER_SYSTEM_ARCHITECTURE.md`.
  > تذكر دائماً: البحث يتم بالباركود فقط، ويجب الحفاظ على فلترة الأوزان والأعداد في `_strip_weights_and_units`.
  > المطلوب الآن: [اكتب طلبك هنا...]

---

### المسار 4: محادثة [ShelfChecker]
* **عنوان المحادثة المقترح:** `[ShelfChecker] - تطبيق الأندرويد لهاني ويل EDA51`
* **المسار المستهدف:** `c:\OdooDB\ShelfChecker\`
* **الملفات المستهدفة:**
  - `ShelfChecker/app/src/main/java/com/alassali/shelfchecker/MainActivity.kt`
  - `ShelfChecker/app/src/main/java/com/alassali/shelfchecker/ScannerHelper.kt`
  - `ShelfChecker/app/src/main/java/com/alassali/shelfchecker/PriceDatabase.kt`
  - `ShelfChecker/app/src/main/java/com/alassali/shelfchecker/OdooClient.kt`
  - `ShelfChecker/app/src/main/java/com/alassali/shelfchecker/SettingsManager.kt`
  - `c:\OdooDB\generate_device_key.py` (أداة ترخيص أجهزة أندرويد)
  - `c:\OdooDB\apk_server\server.py` (سيرفر التحديث المحلي)
* **برومبت البدء السريع (انسخه كما هو):**
  > أهلاً بك! في هذه المحادثة سنعمل حصرياً على مشروع تطبيق الأندرويد **ShelfChecker** المخصص لأجهزة ماسح الباركود Honeywell EDA51 بنظام Kotlin و Gradle.
  > يرجى قراءة القسم رقم 6 في ملف `c:\OdooDB\MASTER_SYSTEM_ARCHITECTURE.md`.
  > كافة ملفات التطبيق تقع داخل المجلد `c:\OdooDB\ShelfChecker\`.
  > المطلوب الآن: [اكتب طلبك هنا...]

---

### المسار 5: محادثة [ShelfLabelPrinter]
* **عنوان المحادثة المقترح:** `[ShelfLabelPrinter] - طباعة استيكرات وملصقات الأرفف`
* **المسار المستهدف:** `c:\OdooDB\ShelfLabelPrinter\`
* **الملفات المستهدفة:**
  - `ShelfLabelPrinter/label_renderer.py` (محرك رسم الملصق 60×40 مم)
  - `ShelfLabelPrinter/app_gui.py` (واجهة المعاينة والطباعة والاستيراد)
  - `ShelfLabelPrinter/arabic_shaper.py` (عزل الأرقام ومنع قلب الأرقام العربية)
  - `ShelfLabelPrinter/page_generator.py` (توزيع الملصقات على ورق A4)
  - `ShelfLabelPrinter/barcode_generator.py` (توليد باركود Code 128)
  - `ShelfLabelPrinter/label_model.py` (نموذج بيانات الصنف)
  - `ShelfLabelPrinter/build_exe.py` (سكربت التجميع المستقل)
* **برومبت البدء السريع (انسخه كما هو):**
  > أهلاً بك! في هذه المحادثة سنعمل حصرياً على برنامج **ShelfLabelPrinter** (نظام طباعة استيكرات الأرفف 60×40 مم على ورق A4).
  > يرجى أولاً قراءة القسم رقم 7 في ملف `c:\OdooDB\MASTER_SYSTEM_ARCHITECTURE.md`.
  > تذكر الثوابت: السعر من `list_price` شامل الضريبة تماماً بدون زيادة، توقيع المطور يظهر على واجهة البرنامج فقط وليس على الاستيكر، والأرقام في النص العربي معزولة الاتجاه.
  > المطلوب الآن: [اكتب طلبك هنا...]

---

### المسار 6: محادثة [OdooImport]
* **عنوان المحادثة المقترح:** `[OdooImport] - مُجهّز ومُدقّق استيراد أصناف أودو 17`
* **المسار المستهدف:** `c:\OdooDB\OdooImport\`
* **الملفات المستهدفة:**
  - `OdooImport/app_gui.py` (واجهة المستخدم الرسومية الفاخرة للتدقيق والتجهيز)
  - `OdooImport/import_engine.py` (محرك المعالجة، الحسابات، التنسيق، وتوليد ملف الإكسل والمقارنة)
  - `OdooImport/odoo_verifier.py` (محرك الفحص الحي عبر XML-RPC مع قاعدة أودو 17)
  - `OdooImport/config.json` (إعدادات الهامش، الضرائب، ومدى السيريال الآلي)
  - `OdooImport/AI_CONTEXT_HANDOVER.md` (الدليل المرجعي المعماري الشامل للأداة)
  - `OdooImport/build_standalone.py` (سكربت تجميع النسخة المستقلة)
* **برومبت البدء السريع (انسخه كما هو):**
  > أهلاً بك! في هذه المحادثة سنعمل حصرياً على برنامج **OdooItemImporter** (أداة تدقيق وتجهيز ملفات استيراد الأصناف لأودو 17 مع صفحة مقارنة الأصناف المسجلة).
  > يرجى أولاً قراءة القسم رقم 8 في ملف `c:\OdooDB\MASTER_SYSTEM_ARCHITECTURE.md` وقراءة ملف `c:\OdooDB\OdooImport\AI_CONTEXT_HANDOVER.md`.
  > تذكر الثوابت: معادلة هامش الربح الحقيقي `Cost / (1 - Margin)`، تقريب ربع الهللة للأعلى مع قاعدة إنقاص هللة للأعداد الصحيحة (مثل 100.00 تصبح 99.99)، والأصناف المكررة تولد في شيت منفصل للمقارنة.
  > المطلوب الآن: [اكتب طلبك هنا...]

---

## ⚠️ جدول منع تداخل وتشابه أسماء الملفات

| اسم الملف | أين يقع؟ | تابع لأي برنامج؟ | تنبيه هام |
| :--- | :--- | :--- | :--- |
| `app_gui.py` | `c:\OdooDB\` | **OdooReportExporter** | واجهة تصدير تقارير إكسل الشاملة من أودو |
| `app_gui.py` | `c:\OdooDB\ShelfLabelPrinter\` | **ShelfLabelPrinter** | واجهة فحص ومعاينة وطباعة استيكرات الرف |
| `app_gui.py` | `c:\OdooDB\OdooImport\` | **OdooItemImporter** | واجهة تجهيز وتدقيق ملفات الاستيراد لأودو 17 |
| `licensing.py` | `c:\OdooDB\` | **OdooReportExporter & PriceComparator** | محرك ترخيص أجهزة ويندوز |
| `generate_device_key.py` | `c:\OdooDB\` | **ShelfChecker (Android)** | أداة ترخيص أجهزة أندرويد هاني ويل |
| `config.json` | `c:\OdooDB\OdooImport\` | **OdooItemImporter** | إعدادات الضرائب والهوامش ومجالات الترقيم |

