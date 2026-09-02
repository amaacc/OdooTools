# دليل استخدام نظام مزامنة منتجات Odoo 17 Enterprise إلى قاعدة بيانات DuckDB

أهلاً بك! يهدف هذا المشروح إلى تقديم آلية سريعة، خفيفة، ومعزولة تماماً لسحب كافة منتجات شركة Odoo 17 Enterprise وتخزينها محلياً في قاعدة بيانات **DuckDB** مع تحديث تزايدي يومي أوتوماتيكي.

---

## 📁 محتويات مجلد المشروح (`c:\OdooDB`)

1. **`odoo_duckdb_sync.py`**: السكربت البرمجي الرئيسي بلغة Python لمزامنة البيانات من Odoo إلى DuckDB.
2. **`odoo_sync_config.json`**: ملف الإعدادات والمسارات وقائمة الحقول المسحوبة.
3. **`odoo_products.duckdb`**: قاعدة البيانات المحلية التي تحتوي على جدول المنتجات `products` وجدول السجلات `sync_log`.
4. **`run_sync.bat`**: ملف تشغيلي بنقرة واحدة لتشغيل المزامنة يدوياً في أي وقت.
5. **`schedule_daily_sync.ps1`**: سكربت PowerShell لجدولة المزامنة تلقائياً يومياً الساعة 02:00 صباحاً في Windows Task Scheduler.

---

## 🚀 كيفية التشغيل والتحقق

### 1. المزامنة اليدوية المباشرة
يمكنك تشغيل المزامنة في أي وقت بأحد الطرق التالية:
- النقر المزدوج على ملف **`run_sync.bat`**.
- أو فتح موجه الأوامر (CMD/PowerShell) وتنفيذ:
  ```cmd
  cd c:\OdooDB
  python odoo_duckdb_sync.py
  ```

### 2. تفعيل المزامنة اليومية التلقائية
لجدولة السكربت ليعمل يومياً الساعة 2:00 صباحاً تلقائياً في خلفية Windows:
- اضغط بزر الفأرة الأيمن على `schedule_daily_sync.ps1` واختر **Run with PowerShell** (أو شغّله كمدير).

---

## 📊 التعامل مع قاعدة البيانات (`odoo_products.duckdb`)

### الاستعلام عن البيانات بـ Python:
```python
import duckdb

# الاتصال بقاعدة البيانات
con = duckdb.connect(r"c:\OdooDB\odoo_products.duckdb")

# عرض إجمالي المنتجات
total = con.execute("SELECT COUNT(*) FROM products").fetchone()[0]
print(f"Total products: {total}")

# استعلام عن أول 5 منتجات
df = con.execute("SELECT id, default_code, name, product_name_arabic, list_price, standard_price, qty_available FROM products LIMIT 5").df()
print(df)

con.close()
```

### الاستعلام من خلال Power BI / Excel / Access / SQL Tools:
- يمكنك استخدام **DuckDB CLI** أو **DuckDB ODBC Driver** للاتصال المباشر بملف `c:\OdooDB\odoo_products.duckdb`.
- كما يمكنك التصدير إلى CSV أو Parquet في أي وقت باستعلام SQL بسيط داخل DuckDB:
  ```sql
  COPY products TO 'c:\OdooDB\products_export.csv' (HEADER, DELIMITER ',');
  ```

---

## ⚙️ آلية المزامنة التزايدية (Incremental Sync)
- **في المرة الأولى**: يقوم النظام بعمل **Full Sync** لسحب جميع المنتجات المخزنة في Odoo (~81,000 منتج).
- **في المرات القادمة**: يقرأ السكربت أحدث تاريخ تعديل (`write_date`) مخزن في DuckDB، ويستعلم Odoo فقط عن المنتجات التي تم إنشاؤها أو تعديلها بعد ذلك التاريخ، مما يجعل التحديث اليومي يستغرق بضع ثوانٍ فقط!
