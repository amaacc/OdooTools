"""
exporter_engine.py — High-Performance Multi-Threaded Odoo Report Engine
Designed by: عبدالله الخطيب (Abdullah Al-Khatib)
Version: v1.02 (High-Performance Turbo Edition)

OPTIMIZATION ARCHITECTURE:
  Phase 1 — Parallel global lookups (taxes, tags, packages, pricelist, showrooms)
  Phase 2 — Multi-threaded concurrent batch retrieval & in-memory Python filtering
  Phase 3 — Adaptive smart auxiliary fetching (chunked parallel queries / zero-timeout server aggregations)
  Phase 4 — Instant vectorized dictionary row construction & movement filtering
  Phase 5 — High-speed Excel streaming with pre-allocated styling, progress heartbeats & RTL layout
"""

import os
import time
import fnmatch
import xmlrpc.client
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from security import get_odoo_credentials
from permissions import load_permissions
from showroom_config import get_showroom_category, load_showroom_types


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def safe_execute_kw(models, db, uid, password, obj, method, args, kw=None, max_retries=4):
    if kw is None:
        kw = {}
    for attempt in range(1, max_retries + 1):
        try:
            return models.execute_kw(db, uid, password, obj, method, args, kw)
        except Exception as e:
            if attempt == max_retries:
                raise
            time.sleep(attempt * 1.5)


def match_wildcards(text_or_list, patterns):
    """Match against wildcard/partial patterns. Returns True if any pattern matches any item."""
    if not patterns:
        return True
    items = text_or_list if isinstance(text_or_list, (list, tuple, set)) else [text_or_list]
    clean_items = [" ".join(str(it).strip().lower().split()) for it in items if it]
    if not clean_items:
        return False
    for pat in patterns:
        pc = " ".join(str(pat).strip().lower().split())
        if not pc:
            continue
        is_wc = '*' in pc or '?' in pc
        for item in clean_items:
            if is_wc:
                if fnmatch.fnmatch(item, pc):
                    return True
            else:
                if pc in item:
                    return True
    return False


def parse_tokens(s):
    """Split comma-separated filter string into list of tokens."""
    if not s:
        return []
    return [t.strip() for t in s.split(',') if t.strip()]


# ─────────────────────────────────────────────────────────────────────────────
# Public API — called by GUI
# ─────────────────────────────────────────────────────────────────────────────

def get_active_showrooms():
    """Returns list of active POS showrooms with their stock location IDs."""
    url, db, username, password = get_odoo_credentials()
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, username, password, {})
    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

    configs = safe_execute_kw(models, db, uid, password, 'pos.config', 'search_read',
                              [[['active', '=', True]]],
                              {'fields': ['id', 'name', 'picking_type_id']})
    pt_ids = [c['picking_type_id'][0] for c in configs if c.get('picking_type_id')]
    pts = safe_execute_kw(models, db, uid, password, 'stock.picking.type', 'read',
                          [pt_ids], {'fields': ['id', 'warehouse_id']})
    pt_map = {t['id']: t for t in pts}

    wh_ids = list(set(
        pt_map[c['picking_type_id'][0]]['warehouse_id'][0]
        for c in configs
        if c.get('picking_type_id') and pt_map.get(c['picking_type_id'][0], {}).get('warehouse_id')
    ))
    whs = safe_execute_kw(models, db, uid, password, 'stock.warehouse', 'read',
                          [wh_ids], {'fields': ['id', 'name', 'code', 'lot_stock_id']})

    showrooms = []
    for w in sorted(whs, key=lambda x: (x.get('code') or '', x.get('id'))):
        wid = w['id']
        cfg_ids = [
            c['id'] for c in configs
            if c.get('picking_type_id')
            and pt_map.get(c['picking_type_id'][0], {}).get('warehouse_id')
            and pt_map[c['picking_type_id'][0]]['warehouse_id'][0] == wid
        ]
        showrooms.append({
            'id': wid,
            'name': w['name'],
            'code': w.get('code') or '',
            'lot_stock_id': w['lot_stock_id'][0] if w.get('lot_stock_id') else None,
            'pos_config_ids': cfg_ids
        })
    return showrooms


def get_all_product_tags():
    """Returns list of distinct product tags from Odoo."""
    url, db, username, password = get_odoo_credentials()
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, username, password, {})
    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

    tags = safe_execute_kw(models, db, uid, password, 'product.tag', 'search_read',
                           [[]], {'fields': ['id', 'name'], 'order': 'name asc'})
    return [{'id': t['id'], 'name': t['name']} for t in tags if t.get('name')]


def _build_methodology_sheet(wb):
    """
    Builds a beautifully formatted RTL documentation sheet:
    '📘 دليل ومنهجية الحسابات'
    Explaining calculation formulas, logic, Odoo data sources, and practical guidance.
    """
    ws = wb.create_sheet(title="📘 دليل ومنهجية الحسابات")
    ws.views.sheetView[0].rightToLeft = True

    C_HDR_MAIN    = "1F4E79"   # Dark Navy
    C_HDR_SUB     = "2E75B6"   # Soft Blue
    C_BG_LIGHT    = "F8FAFC"
    C_BG_ALT      = "F1F5F9"
    C_BORDER      = "CBD5E1"
    C_TEXT_DARK   = "0F172A"
    C_TEXT_MUTED  = "475569"
    C_NOTE_BG     = "EFF6FF"
    C_NOTE_BORDER = "3B82F6"

    fill_title = PatternFill("solid", fgColor=C_HDR_MAIN)
    fill_desc  = PatternFill("solid", fgColor=C_BG_LIGHT)
    fill_th    = PatternFill("solid", fgColor=C_HDR_SUB)
    fill_alt   = PatternFill("solid", fgColor=C_BG_ALT)
    fill_white = PatternFill("solid", fgColor="FFFFFF")
    fill_note  = PatternFill("solid", fgColor=C_NOTE_BG)

    font_title = Font(name="Segoe UI", size=13, bold=True, color="FFFFFF")
    font_desc  = Font(name="Segoe UI", size=9.5, color=C_TEXT_MUTED)
    font_th    = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    font_field = Font(name="Segoe UI", size=9.5, bold=True, color="1E3A8A")
    font_dept  = Font(name="Segoe UI", size=9, bold=True, color="0F766E")
    font_body  = Font(name="Segoe UI", size=9, color=C_TEXT_DARK)
    font_code  = Font(name="Consolas", size=8.5, color="7C2D12")
    font_note  = Font(name="Segoe UI", size=9.5, bold=True, color="1E40AF")

    s_border = Side(style="thin", color=C_BORDER)
    border_cell = Border(left=s_border, right=s_border, top=s_border, bottom=s_border)
    s_note = Side(style="medium", color=C_NOTE_BORDER)
    border_note = Border(left=s_note, right=s_note, top=s_note, bottom=s_note)

    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    align_right  = Alignment(horizontal="right",  vertical="center", wrap_text=True)

    # 1. Title Banner (Row 2)
    ws.merge_cells("A2:E2")
    c_title = ws.cell(row=2, column=1, value="📘 دليل ومنهجية الحسابات والمعايير التحليلية للتقرير")
    c_title.font = font_title
    c_title.fill = fill_title
    c_title.alignment = align_center
    ws.row_dimensions[2].height = 36

    # 2. Subtitle / Description (Row 3)
    ws.merge_cells("A3:E3")
    c_desc = ws.cell(row=3, column=1, value="يوضح هذا الدليل الأسس والمعادلات الرياضية لجميع مؤشرات وأعمدة التقرير، ومصادر بياناتها من نظام Odoo، مع توجيهات تنفيذية لكيفية استثمارها في قرارات المشتريات والمبيعات والمخزون.")
    c_desc.font = font_desc
    c_desc.fill = fill_desc
    c_desc.alignment = align_center
    ws.row_dimensions[3].height = 26

    # 3. Table Headers (Row 5)
    headers = [
        ("المعيار / الحقل في التقرير", 26),
        ("القسم المعني", 20),
        ("المعادلة وآلية الحساب", 44),
        ("مصدر البيانات في Odoo", 30),
        ("دلالة المؤشر والتوجيه التنفيذي", 52),
    ]

    for col_idx, (hdr_text, width) in enumerate(headers, 1):
        cell = ws.cell(row=5, column=col_idx, value=hdr_text)
        cell.font = font_th
        cell.fill = fill_th
        cell.alignment = align_center
        cell.border = border_cell
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    ws.row_dimensions[5].height = 28

    # 4. Data Rows (10 Topics)
    data = [
        (
            "نسبة هامش الربح\nMargin (%)",
            "المشتريات والمالية",
            "((سعر البيع - سعر التكلفة) / سعر البيع) × 100\nتُحسب بالمعادلة المباشرة وتُنسق كنسبة مئوية بدقة 0.0%",
            "product.product:\n• list_price (سعر البيع)\n• standard_price (سعر التكلفة)",
            "يقيس صافي ربحية الصنف. يفيد المشتريات في مراجعة أسعار الشراء مع الموردين، ويفيد المبيعات في تجنب تقديم خصومات تخفض الهامش عن الحد الأدنى المستهدف للربحية."
        ),
        (
            "أيام التغطية\nDays of Inventory (DOI)",
            "المخزون والمشتريات",
            "إجمالي الرصيد القابل للبيع ÷ معدل المبيعات اليومية (365d Sold ÷ 365).\n• إذا كان الرصيد = 0 يُعرض (0).\n• إذا توفر مخزون دون مبيعات يُعرض (999) كدلالة على الركود.",
            "• stock.quant (المخزون المتوفر)\n• pos.order.line (مبيعات السنة)",
            "يقيس عدد الأيام التي يكفيها الرصيد الحالي:\n• أقل من 30 يوماً: خطر نفاد وشيك يتطلب الشراء الفوري.\n• 30 إلى 90 يوماً: مخزون مثالي ومتوازن.\n• أكثر من 120 يوماً: تضخم مخزون وركود يستوجب التخفيض أو المناقلة."
        ),
        (
            "حالة الصنف\nMovement Status",
            "المشتريات والمبيعات والمستودعات",
            "تصنيف ديناميكي بناءً على الرصيد ومعدل الحركة وأيام التغطية:\n• نفاذ مخزون (Out of Stock): رصيد 0 مع حركة سابقة.\n• قاربت على النفاذ (Low Stock): رصيد متوفر وتغطية ≤ 30 يوم.\n• راكد (Stagnant): مخزون بلا مبيعات أو تغطية ≥ 180 يوم.\n• سريع الحركة (Fast Moving): مبيعات عالية وتغطية منتظمة.\n• فائض (Surplus): تغطية > 120 يوم.\n• متوازن (Balanced): تغطية بين 30 و 120 يوم.",
            "مؤشر مركب من:\n• stock.quant\n• pos.order.line\n• DOI المحسوب",
            "يوفر توجيهاً فورياً لفرق العمل:\n• الأصناف النافذة أو القاربة على النفاذ: أولوية قصوى للمشتريات.\n• الأصناف الراكدة والفائضة: إيقاف الشراء فوراً وتنشيط العروض الترويجية أو نقلها لفروع أكثر حركة لتفادي تجميد السيولة."
        ),
        (
            "تصنيف باريتو\nPareto (ABC)",
            "الإدارة العليا والمشتريات",
            "تطبيق قانون باريتو (80/15/5) على الإيرادات البيعية الإجمالية (365d Sold × Price):\n• الفئة (A): الأصناف الذهبية التي تمثل أول 80% من إجمالي الإيرادات.\n• الفئة (B): الأصناف التي تمثل الـ 15% التالية (80% إلى 95%).\n• الفئة (C): الأصناف التي تمثل آخر 5% من الإيرادات أو صفرية المبيعات.",
            "تحليل تراكمي للمبيعات:\n• pos.order.line\n• product.template.list_price",
            "توجيه التركيز الإداري والاستثماري:\n• فئة A: متابعة يومية وشراء مستمر؛ انقطاعها يعني فقدان معظم المبيعات.\n• فئة B: مراجعة دورية منتظمة.\n• فئة C: تقنين الشراء والرقابة الصارمة لتجنب تجميد رأس المال في أصناف هامشية."
        ),
        (
            "الطلب المقترح (60 يوم)\nSuggested PO (60d)",
            "قسم المشتريات والتخطيط",
            "الاحتياج المتوقع لـ 60 يوماً مطروحاً منه الرصيد الحالي والبضاعة بالطريق:\nMAX(0, (معدل البيع اليومي × 60) - (المخزون المتوفر + Incoming))\nالنتيجة تكون (0) في حال كان المخزون كافياً لـ 60 يوماً.",
            "• pos.order.line (المبيعات)\n• stock.quant (المخزون المتوفر)\n• purchase.order.line (بضاعة بالطريق Incoming)",
            "توصية توريد آلية علمية تكفي استهلاك شهرين قادمين، وتمنع كلاً من نفاد البضائع أو تكدسها فوق الحاجة التشغيلية."
        ),
        (
            "قيمة الطلب المقترح\nSuggested PO Value",
            "المشتريات والمالية وإدارة الميزانية",
            "الطلب المقترح (60 يوم) × سعر الشراء الصافي من المورد (Vendor Price).\nيحتوي التقرير على معادلة جمع تلقائي =SUM في صف الإجمالي لمعرفة التكلفة الإجمالية للطلبية.",
            "• كمية الطلب المقترح المحسوبة\n• purchase.order.line (آخر سعر شراء)\n• product.supplierinfo",
            "تقدير دقيق لحجم السيولة النقدية والميزانية المطلوبة لإصدار أوامر التوريد للمورد، مما يسهل التخطيط المالي وتوزيع الاعتمادات المالية."
        ),
        (
            "توصيات المناقلة الذكية\nShowroom Transfers",
            "إدارة التوزيع وسلاسل الإمداد",
            "خوارزمية ذكية تقارن رصيد ومبيعات كل معرض:\n• إذا كان لدى فرع رصيد فائض (تغطية > 60 يوم) وفرع آخر لديه عجز (رصيد = 0 أو تغطية < 15 يوم وله مبيعات).\n• تُحسب الكمية بدقة وتُعرض بصيغة: من [الفرع] ([الكمية]) إلى [الفرع].",
            "تحليل تفصيلي لمواقع المعارض:\n• stock.location\n• stock.quant\n• pos.order.line لكل معرض",
            "استغلال المخزون الحالي بالكامل بين المعارض دون الحاجة لشراء بضاعة إضافية، وتلبية طلبات العملاء في الفروع المتعطشة عبر النقل الداخلي السريع."
        ),
        (
            "تصنيف المعارض وفروع العناية\nShowrooms & Care Branches",
            "إدارة العمليات والمبيعات",
            "تقسيم منافذ البيع إلى نوعين رئيسيين:\n1. معارض بيع عادية (Showrooms).\n2. مراكز وفروع عناية (Care Branches) مثل: الصفاء، الطائف، الحمدانية، سوق الشاطئ.\nتتميز فروع العناية بلون فيروزي فاتح مميز في رؤوس الأعمدة والملخصات.",
            "ملف تهيئة المعارض الداخلي:\n• showroom_config.json\nمع إمكانية تعديل نوع أي فرع من شاشة الإعدادات بالبرنامج.",
            "تسهيل التمييز البصري الفوري ومقارنة حجم حركة البضائع بين معارض التجزئة ومراكز العناية، وتخصيص سياسات التوزيع حسب طبيعة الفرع."
        ),
        (
            "مستويات الأسعار وخصم المورد\nPricing Tiers & Vendor Discounts",
            "المبيعات والمشتريات وإدارة التسعير",
            "تتبع دورة التسعير الكاملة للصنف:\n• سعر المورد الأساسي (Vendor Price).\n• سعر الشراء المخفض بعد الخصم الممنوح (Discounted Price).\n• سعر بيع التجزئة (Sales Price).\n• سعر الجملة وسعر التكلفة.",
            "• purchase.order.line (سعر وخصم أمر الشراء الأخير)\n• product.supplierinfo (قائمة أسعار الموردين)\n• product.template",
            "مراقبة التزام الموردين بنسب الخصومات المتفق عليها، وضمان الحفاظ على هامش ربح آمن عند تطبيق أسعار الجملة أو الخصومات الترويجية."
        ),
        (
            "مطابقة مخزون المعارض والمستودع\nPOS vs Warehouse Stock",
            "إدارة الجرد والمستودعات والرقابة",
            "مقارنة الرصيد المتوفر في صالات المعارض (إجمالي رصيد المعارض) مع الرصيد الكلي العام للشركة (Quantity On Hand).\nالفرق بينهما يمثل المخزون المتواجد في المستودع المركزي أو بضائع تحت الفحص والاستلام.",
            "• stock.quant المربوطة بمواقع نقاط البيع (POS Locations)\n• إجمالي رصيد الشركة الكلي (Company On Hand)",
            "كشف أي تكدس للبضائع في المستودعات المركزية دون توزيعها على المعارض، وسرعة اكتشاف الفروقات الجردية بين النظام والواقع الفعلي."
        ),
    ]

    for r_idx, row_data in enumerate(data, 6):
        row_fill = fill_white if r_idx % 2 == 0 else fill_alt
        field_text, dept_text, formula_text, source_text, guide_text = row_data

        cells = [
            (1, field_text, font_field, align_center),
            (2, dept_text, font_dept, align_center),
            (3, formula_text, font_body, align_right),
            (4, source_text, font_code, align_right),
            (5, guide_text, font_body, align_right),
        ]

        for c_idx, val, c_font, c_align in cells:
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            cell.font = c_font
            cell.fill = row_fill
            cell.alignment = c_align
            cell.border = border_cell

        lines_count = max(
            field_text.count("\n") + 1,
            formula_text.count("\n") + 1,
            source_text.count("\n") + 1,
            guide_text.count("\n") + 1 + len(guide_text) // 45
        )
        ws.row_dimensions[r_idx].height = max(52, lines_count * 18)

    # 5. Bottom Note Card
    note_row = len(data) + 7
    ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=5)
    c_note = ws.cell(row=note_row, column=1, value="💡 ملاحظة إدارية: يتم احتساب وتحديث كافة هذه المؤشرات والمعادلات لحظياً ومباشرة من قاعدة بيانات Odoo أثناء التصدير لتقديم أدق صورة واقعية تدعم اتخاذ قرارات الشراء والتوزيع الفورية.")
    c_note.font = font_note
    c_note.fill = fill_note
    c_note.alignment = align_right
    c_note.border = border_note
    ws.row_dimensions[note_row].height = 32

    ws.freeze_panes = "A6"


def generate_report(
    filter_internal_ref=None,
    filter_barcode=None,
    filter_name=None,
    filter_tags=None,
    selected_showroom_ids=None,
    sales_period="all",
    custom_date_from=None,
    custom_date_to=None,
    movement_filter="all",
    column_options=None,
    output_path=None,
    include_methodology_guide=False,
    progress_callback=None,
    cancel_check_callback=None,
    is_cancelled=None,
    **kwargs
):
    """
    Main export function with high-performance parallel pipelines.
    """
    t_start = time.time()

    if column_options is None:
        column_options = {
            'basic_info': True,
            'pricing': True,
            'totals': True,
            'vendors': True,
            'showrooms': True,
            'analytics': True
        }

    permissions, _ = load_permissions()

    def notify(pct, text):
        if progress_callback:
            progress_callback(pct, text)

    def chk():
        if cancel_check_callback and cancel_check_callback():
            raise InterruptedError("تم إلغاء التصدير من قبل المستخدم.")
        if is_cancelled and is_cancelled():
            raise InterruptedError("تم إلغاء التصدير من قبل المستخدم.")

    notify(2, "جاري الاتصال الآمن بنظام Odoo...")
    chk()

    url, db, username, password = get_odoo_credentials()
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, username, password, {})
    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

    ref_pat = parse_tokens(filter_internal_ref)
    bc_pat  = parse_tokens(filter_barcode)
    nm_pat  = parse_tokens(filter_name)
    tg_pat  = parse_tokens(filter_tags)

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 1 — Parallel Global Lookups
    # ═════════════════════════════════════════════════════════════════════════
    notify(5, "جاري تحميل جداول البيانات المساعدة بشكل متوازٍ...")

    def _fetch_taxes():
        m = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        taxes = safe_execute_kw(m, db, uid, password, 'account.tax', 'search_read',
                                [[]], {'fields': ['id', 'name']})
        return {t['id']: t['name'] for t in taxes}

    def _fetch_tags():
        m = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        tags = safe_execute_kw(m, db, uid, password, 'product.tag', 'search_read',
                               [[]], {'fields': ['id', 'name']})
        return {t['id']: t['name'] for t in tags}

    def _fetch_packages():
        m = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        pkgs = safe_execute_kw(m, db, uid, password, 'product.packaging', 'search_read',
                               [[['barcode', '!=', False]]],
                               {'fields': ['product_id', 'barcode']})
        pkg_map = {}
        for p in pkgs:
            pid = p['product_id'][0] if p.get('product_id') else None
            if pid:
                pkg_map.setdefault(pid, []).append(p['barcode'])
        return pkg_map

    def _fetch_shati():
        m = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        now_dt = datetime.now()
        pl = safe_execute_kw(m, db, uid, password, 'product.pricelist', 'search_read',
                             [[['name', '=', 'سعر الشاطئ']]], {'fields': ['id']})
        pl_id = pl[0]['id'] if pl else 28
        items = safe_execute_kw(m, db, uid, password, 'product.pricelist.item', 'search_read',
                                [[['pricelist_id', '=', pl_id]]],
                                {'fields': ['applied_on', 'compute_price', 'fixed_price',
                                            'percent_price', 'product_tmpl_id', 'product_id',
                                            'product_tag_ids', 'date_start', 'date_end']})
        v_map, t_map, tag_rules = {}, {}, []
        for it in items:
            ds = datetime.strptime(it['date_start'], '%Y-%m-%d %H:%M:%S') if it.get('date_start') else None
            de = datetime.strptime(it['date_end'], '%Y-%m-%d %H:%M:%S') if it.get('date_end') else None
            if ds and now_dt < ds: continue
            if de and now_dt > de: continue
            if it['applied_on'] == '0_product_variant' and it['product_id']:
                v_map[it['product_id'][0]] = float(it['fixed_price'])
            elif it['applied_on'] == '1_product' and it['product_tmpl_id']:
                t_map[it['product_tmpl_id'][0]] = float(it['fixed_price'])
            elif it['applied_on'] == '1_product_tag' and it['product_tag_ids']:
                for tid in it['product_tag_ids']:
                    tag_rules.append({'tag_id': tid, 'compute_price': it['compute_price'],
                                      'percent_price': float(it['percent_price']),
                                      'fixed_price': float(it['fixed_price'])})
        return v_map, t_map, tag_rules

    def _fetch_showrooms():
        return get_active_showrooms()

    with ThreadPoolExecutor(max_workers=5) as ex:
        f_taxes    = ex.submit(_fetch_taxes)
        f_tags     = ex.submit(_fetch_tags)
        f_packages = ex.submit(_fetch_packages)
        f_shati    = ex.submit(_fetch_shati)
        f_showrooms = ex.submit(_fetch_showrooms)

    tax_map  = f_taxes.result()
    tag_map  = f_tags.result()
    pkg_map  = f_packages.result()
    shati_variant_map, shati_tmpl_map, shati_tag_rules = f_shati.result()
    all_showrooms = f_showrooms.result()
    chk()

    if selected_showroom_ids is not None:
        target_showrooms = [s for s in all_showrooms if s['id'] in selected_showroom_ids]
    else:
        target_showrooms = all_showrooms

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 2 — Parallel Concurrent Batch Retrieval & In-Memory Filtering
    # ═════════════════════════════════════════════════════════════════════════
    notify(12, "جاري بناء فلاتر البحث وإرسالها لـ Odoo...")

    base_domain = [
        ['active', '=', True],
        ['available_in_pos', '=', True],
        ['purchase_ok', '=', True],
        ['sale_ok', '=', True],
        ['detailed_type', '=', 'product']
    ]

    need_python_ref  = False
    need_python_bc   = False
    need_python_name = False
    need_python_tags = False

    if ref_pat:
        no_wc = [t for t in ref_pat if '*' not in t and '?' not in t]
        has_wc = [t for t in ref_pat if '*' in t or '?' in t]
        if no_wc and not has_wc:
            base_domain.append(['default_code', 'in', no_wc])
        else:
            stems = [t.replace('*', '').replace('?', '').strip() for t in ref_pat if t.strip()]
            if len(stems) == 1:
                base_domain.append(['default_code', 'ilike', stems[0]])
            elif len(stems) > 1:
                for _ in range(len(stems) - 1):
                    base_domain.append('|')
                for s in stems:
                    base_domain.append(['default_code', 'ilike', s])
            need_python_ref = True

    if nm_pat:
        has_wc = any('*' in t or '?' in t for t in nm_pat)
        stems = [t.replace('*', '').replace('?', '').strip() for t in nm_pat if t.strip()]
        if stems:
            clauses = []
            for s in stems:
                clauses.append(['|', ['name', 'ilike', s], ['product_name_arabic', 'ilike', s]])
            if len(clauses) == 1:
                base_domain.extend(clauses[0])
            else:
                for _ in range(len(clauses) - 1):
                    base_domain.append('|')
                for cl in clauses:
                    base_domain.extend(cl)
        if has_wc or len(nm_pat) > 1:
            need_python_name = True

    if bc_pat:
        stems = [t.replace('*', '').replace('?', '').strip() for t in bc_pat if t.strip()]
        if stems:
            clauses = []
            for s in stems:
                clauses.append(['|', ['barcode', 'ilike', s], ['packaging_ids.barcode', 'ilike', s]])
            if len(clauses) == 1:
                base_domain.extend(clauses[0])
            else:
                for _ in range(len(clauses) - 1):
                    base_domain.append('|')
                for cl in clauses:
                    base_domain.extend(cl)
        need_python_bc = True

    if tg_pat:
        # Match against loaded tag_map from Phase 1 to get all matching tag IDs
        matched_tag_ids = [
            tid for tid, tname in tag_map.items()
            if match_wildcards(tname, tg_pat)
        ]
        if matched_tag_ids:
            base_domain.append(['product_tag_ids', 'in', matched_tag_ids])
        else:
            stems = [t.replace('*', '').replace('?', '').strip() for t in tg_pat if t.strip()]
            if len(stems) == 1:
                base_domain.append(['product_tag_ids.name', 'ilike', stems[0]])
            elif len(stems) > 1:
                for _ in range(len(stems) - 1):
                    base_domain.append('|')
                for s in stems:
                    base_domain.append(['product_tag_ids.name', 'ilike', s])
        need_python_tags = True

    all_product_ids = safe_execute_kw(models, db, uid, password,
                                      'product.product', 'search', [base_domain])
    total_all = len(all_product_ids)
    notify(15, f"الأصناف بعد فلتر Odoo: {total_all:,} — جاري قراءة التفاصيل بالتوازي...")
    chk()

    fields_to_read = [
        'id', 'product_tmpl_id', 'default_code', 'barcode', 'name', 'product_name_arabic',
        'standard_price', 'list_price', 'sales_price', 'pos_min_price',
        'qty_available', 'sales_count',
        'product_tag_ids', 'x_studio_concatenated_tags',
        'uom_id', 'taxes_id', 'supplier_taxes_id'
    ]

    def _parse_m2o(val):
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            return val[0], str(val[1])
        return None, ""

    BATCH = 3500
    chunk_list = [all_product_ids[idx: idx + BATCH] for idx in range(0, total_all, BATCH)]
    total_chunks = len(chunk_list)

    def _read_and_filter_chunk(arg):
        chunk_idx, chunk_ids = arg
        m = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        records = safe_execute_kw(m, db, uid, password, 'product.product', 'read',
                                  [chunk_ids], {'fields': fields_to_read})
        chunk_filtered = []
        for r in records:
            pid = r['id']
            code_val    = str(r.get('default_code') or '')
            barcode_val = str(r.get('barcode') or '')
            pkg_bc      = pkg_map.get(pid, [])
            name_val    = str(r.get('name') or '')
            name_ar     = str(r.get('product_name_arabic') or '')
            tag_ids     = r.get('product_tag_ids') or []
            tag_names   = [tag_map.get(t, '') for t in tag_ids if tag_map.get(t)]
            if r.get('x_studio_concatenated_tags'):
                tag_names.append(str(r['x_studio_concatenated_tags']))

            if need_python_ref  and not match_wildcards(code_val, ref_pat):   continue
            if need_python_bc   and not match_wildcards([barcode_val] + pkg_bc, bc_pat): continue
            if need_python_name and not match_wildcards([name_val, name_ar], nm_pat):    continue
            if need_python_tags and not match_wildcards(tag_names, tg_pat):    continue

            r['_pkg_bc']    = pkg_bc
            r['_tag_names'] = tag_names
            chunk_filtered.append(r)
        return chunk_idx, chunk_filtered

    filtered_records = []
    completed_chunks = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = [ex.submit(_read_and_filter_chunk, (i, ch)) for i, ch in enumerate(chunk_list)]
        for f in futures:
            chk()
            _, c_filtered = f.result()
            filtered_records.extend(c_filtered)
            completed_chunks += 1
            pct = 15 + (completed_chunks / max(total_chunks, 1)) * 27
            notify(pct, f"قراءة وتصفية الدفعات الموازية: {completed_chunks}/{total_chunks}...")

    total_filtered = len(filtered_records)
    notify(42, f"نتيجة الفلتر: {total_filtered:,} صنف مطابق من أصل {total_all:,}")
    chk()

    if total_filtered == 0:
        raise ValueError("لم يتم العثور على أصناف تطابق الفلاتر المحددة.")

    filtered_product_ids = [r['id'] for r in filtered_records]
    prod_to_tmpl = {}
    filtered_tmpl_ids = []
    for r in filtered_records:
        pid = r['id']
        tid = r['product_tmpl_id'][0] if isinstance(r.get('product_tmpl_id'), (list, tuple)) else r.get('product_tmpl_id')
        prod_to_tmpl[pid] = tid
        if tid not in filtered_tmpl_ids:
            filtered_tmpl_ids.append(tid)

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 3 — Multi-threaded Adaptive Auxiliary Queries
    # ═════════════════════════════════════════════════════════════════════════
    notify(44, f"جاري جلب بيانات الموردين والمخزون والمبيعات بالتوازي لـ {total_filtered:,} صنف...")

    def _fetch_vendors():
        if not filtered_tmpl_ids:
            return {}
        if len(filtered_tmpl_ids) <= 2500:
            m = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
            sup = safe_execute_kw(m, db, uid, password, 'product.supplierinfo', 'search_read',
                                  [[['product_tmpl_id', 'in', filtered_tmpl_ids]]],
                                  {'fields': ['product_tmpl_id', 'partner_id', 'price', 'discount',
                                              'price_discounted', 'last_purchase_date', 'write_date'],
                                   'order': 'sequence asc, id asc'})
        else:
            def _get_sup_chunk(chunk):
                mt = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
                return safe_execute_kw(mt, db, uid, password, 'product.supplierinfo', 'search_read',
                                       [[['product_tmpl_id', 'in', chunk]]],
                                       {'fields': ['product_tmpl_id', 'partner_id', 'price', 'discount',
                                                   'price_discounted', 'last_purchase_date', 'write_date'],
                                        'order': 'sequence asc, id asc'})
            chunks = [filtered_tmpl_ids[i:i+2500] for i in range(0, len(filtered_tmpl_ids), 2500)]
            sup = []
            with ThreadPoolExecutor(max_workers=6) as ex:
                for chunk_res in ex.map(_get_sup_chunk, chunks):
                    sup.extend(chunk_res)

        vmap = {}
        for s in sup:
            if not s.get('product_tmpl_id'):
                continue
            tid = s['product_tmpl_id'][0] if isinstance(s['product_tmpl_id'], (list, tuple)) else s['product_tmpl_id']
            if tid not in vmap:
                vmap[tid] = {
                    'vendor_name':            s['partner_id'][1] if s.get('partner_id') else '',
                    'vendor_price':           float(s.get('price') or 0.0),
                    'vendor_discount':        float(s.get('discount') or 0.0),
                    'vendor_discounted_price':float(s.get('price_discounted') or 0.0),
                    'vendor_last_purchase':   str(s.get('last_purchase_date') or ''),
                    'vendor_last_updated':    str(s.get('write_date') or ''),
                }
        return vmap

    def _fetch_last_received():
        if not filtered_product_ids:
            return {}
        m = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        dom = [['order_id.state', 'in', ['purchase', 'done']]]
        if len(filtered_product_ids) <= 2500:
            dom.append(['product_id', 'in', filtered_product_ids])
        groups = safe_execute_kw(m, db, uid, password, 'purchase.order.line', 'read_group',
                                 [dom],
                                 {'fields': ['product_id', 'qty_received'],
                                  'groupby': ['product_id']})
        return {g['product_id'][0]: float(g.get('qty_received') or 0.0)
                for g in groups if g.get('product_id')}

    def _fetch_quants():
        target_loc_ids = [s['lot_stock_id'] for s in target_showrooms if s.get('lot_stock_id')]
        if not target_loc_ids or not filtered_product_ids:
            return {}
        m = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        dom = [['location_id', 'in', target_loc_ids], ['quantity', '!=', 0]]
        if len(filtered_product_ids) <= 2500:
            dom.append(['product_id', 'in', filtered_product_ids])
        quants = safe_execute_kw(m, db, uid, password, 'stock.quant', 'search_read',
                                 [dom],
                                 {'fields': ['product_id', 'location_id', 'quantity']})
        qmap = {}
        for q in quants:
            if q.get('product_id') and q.get('location_id'):
                qmap[(q['product_id'][0], q['location_id'][0])] = float(q.get('quantity') or 0.0)
        return qmap

    today = datetime.now()
    date_filter = []
    period_days = 365
    if sales_period == "last_30_days":
        date_filter.append(['date', '>=', (today - timedelta(days=30)).strftime('%Y-%m-%d 00:00:00')])
        period_days = 30
    elif sales_period == "last_60_days":
        date_filter.append(['date', '>=', (today - timedelta(days=60)).strftime('%Y-%m-%d 00:00:00')])
        period_days = 60
    elif sales_period == "last_90_days":
        date_filter.append(['date', '>=', (today - timedelta(days=90)).strftime('%Y-%m-%d 00:00:00')])
        period_days = 90
    elif sales_period == "this_year":
        date_filter.append(['date', '>=', f"{today.year}-01-01 00:00:00"])
        period_days = max(1, (today - datetime(today.year, 1, 1)).days)
    elif sales_period == "custom" and custom_date_from:
        date_filter.append(['date', '>=', f"{custom_date_from} 00:00:00"])
        if custom_date_to:
            date_filter.append(['date', '<=', f"{custom_date_to} 23:59:59"])
            try:
                d1 = datetime.strptime(custom_date_from, "%Y-%m-%d")
                d2 = datetime.strptime(custom_date_to, "%Y-%m-%d")
                period_days = max(1, (d2 - d1).days + 1)
            except Exception:
                period_days = 30
        else:
            try:
                d1 = datetime.strptime(custom_date_from, "%Y-%m-%d")
                period_days = max(1, (today - d1).days + 1)
            except Exception:
                period_days = 30

    def _fetch_pos_sales_for(s):
        models_t = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        dom = [['state', 'in', ['paid', 'done', 'invoiced']],
               ['config_id', 'in', s['pos_config_ids']]] + date_filter
        if len(filtered_product_ids) <= 2500:
            dom.append(['product_id', 'in', filtered_product_ids])
        res = models_t.execute_kw(db, uid, password, 'report.pos.order', 'read_group',
                                  [dom, ['product_id', 'product_qty:sum'], ['product_id']],
                                  {'lazy': False})
        return s['id'], {r['product_id'][0]: float(r.get('product_qty') or 0.0)
                         for r in res if r.get('product_id')}

    with ThreadPoolExecutor(max_workers=6 + len(target_showrooms)) as ex:
        f_vendors  = ex.submit(_fetch_vendors)
        f_last_rcv = ex.submit(_fetch_last_received)
        f_quants   = ex.submit(_fetch_quants)
        pos_futures = {ex.submit(_fetch_pos_sales_for, s): s['id'] for s in target_showrooms}

    vendor_tmpl_map   = f_vendors.result()
    last_received_map = f_last_rcv.result()
    stock_map         = f_quants.result()

    showroom_sales = {}
    for fut, sid in pos_futures.items():
        _, smap = fut.result()
        showroom_sales[sid] = smap

    notify(70, f"اكتمل جلب البيانات بنجاح. جاري تجهيز مصفوفة السجلات ({total_filtered:,} صنف)...")
    chk()

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 4 — Fast In-Memory Row Construction
    # ═════════════════════════════════════════════════════════════════════════
    branch_summary = {
        s['id']: {'code': s['code'], 'name': s['name'],
                  'total_on_hand': 0.0, 'total_cost_value': 0.0,
                  'total_sales_value': 0.0, 'total_sold_units': 0.0}
        for s in target_showrooms
    }

    export_rows = []
    for r in filtered_records:
        chk()
        pid    = r['id']
        tid    = prod_to_tmpl.get(pid, 0)
        _, uom = _parse_m2o(r.get('uom_id'))

        code_val    = str(r.get('default_code') or '')
        barcode_val = str(r.get('barcode') or '')
        pkg_bc      = r.get('_pkg_bc', [])
        name_val    = str(r.get('name') or '')
        name_ar     = str(r.get('product_name_arabic') or '')
        tag_ids     = r.get('product_tag_ids') or []
        tag_names   = r.get('_tag_names', [])

        cust_taxes  = ", ".join([tax_map.get(t, str(t)) for t in (r.get('taxes_id') or [])])
        vend_taxes  = ", ".join([tax_map.get(t, str(t)) for t in (r.get('supplier_taxes_id') or [])])
        pkg_str     = ", ".join(pkg_bc)
        tags_str    = ", ".join(tag_names)

        cost_val   = float(r.get('standard_price') or 0.0)
        price_val  = float(r.get('list_price') or 0.0)
        so_p_val   = float(r.get('sales_price') or 0.0)
        min_p_val  = float(r.get('pos_min_price') or 0.0)

        shati_val = 0.0
        if pid in shati_variant_map:
            shati_val = shati_variant_map[pid]
        elif tid in shati_tmpl_map:
            shati_val = shati_tmpl_map[tid]
        else:
            for rule in shati_tag_rules:
                if rule['tag_id'] in tag_ids:
                    cp = rule['compute_price']
                    if cp == 'fixed':
                        shati_val = rule['fixed_price']
                    elif cp == 'percentage':
                        shati_val = round(price_val * (1.0 - rule['percent_price'] / 100.0), 2)
                    break
            else:
                shati_val = price_val

        qty_oh     = float(r.get('qty_available') or 0.0)
        total_sold = float(r.get('sales_count') or 0.0)

        v_info = vendor_tmpl_map.get(tid, {})
        last_rcv_qty = last_received_map.get(pid, 0.0)

        # Showroom stock & sales calculation
        sh_oh_total = 0.0
        sh_sl_total = 0.0
        sh_row_dict = {}

        if column_options.get('showrooms', True):
            for s in target_showrooms:
                s_id = s['id']
                lot  = s['lot_stock_id']
                sh_oh = stock_map.get((pid, lot), 0.0) if lot else 0.0
                sh_sl = showroom_sales.get(s_id, {}).get(pid, 0.0)

                sh_oh_total += sh_oh
                sh_sl_total += sh_sl

                branch_summary[s_id]['total_on_hand']     += sh_oh
                branch_summary[s_id]['total_cost_value']  += (sh_oh * cost_val)
                branch_summary[s_id]['total_sales_value'] += (sh_sl * price_val)
                branch_summary[s_id]['total_sold_units']  += sh_sl

                s_name = s['name']
                if permissions.get("Showrooms_OnHand", True):
                    sh_row_dict[f"{s_name} / On Hand"] = sh_oh
                if permissions.get("Showrooms_Sold", True):
                    sh_row_dict[f"{s_name} / Sold"] = sh_sl

        # Calculate analytics values
        analysis_oh = sh_oh_total if column_options.get('showrooms', True) else qty_oh
        analysis_sl = sh_sl_total if column_options.get('showrooms', True) else total_sold
        monthly_sales = (analysis_sl / (period_days / 30.0)) if period_days > 0 else (analysis_sl / 12.0)
        daily_sales = (analysis_sl / float(period_days)) if period_days > 0 else 0.0
        margin_val = round(((price_val - cost_val) / price_val), 4) if price_val > 0 else 0.0

        if analysis_oh <= 0:
            days_cover = 0
            if analysis_sl > 0:
                item_status = "نفد المخزون"
            else:
                item_status = "غير متوفر"
        elif analysis_sl <= 0:
            days_cover = 999
            item_status = "راكد"
        else:
            days_cover = round(analysis_oh / daily_sales) if daily_sales > 0 else 999
            if days_cover <= 20 or (analysis_oh <= 5 and analysis_sl >= 10):
                item_status = "قارب على النفاذ"
            elif days_cover <= 60 or monthly_sales >= 15:
                item_status = "سريع الحركة"
            elif days_cover >= 180:
                item_status = "فائض المخزون"
            else:
                item_status = "متوازن"

        # Movement filter check
        if movement_filter == "fast_moving":
            if not (item_status == "سريع الحركة" or monthly_sales >= 15 or total_sold >= 15):
                continue
        elif movement_filter == "stagnant":
            if not (item_status == "راكد" or total_sold <= 0):
                continue
        elif movement_filter == "low_stock":
            if not (item_status in ("نفد المخزون", "قارب على النفاذ") or (qty_oh <= 5 and total_sold > 0)):
                continue

        row = {}
        if column_options.get('basic_info', True):
            row["Internal Reference"] = code_val
            row["Barcode"] = barcode_val
            row["Product Packages/Barcode"] = pkg_str
            row["Name"] = name_val
            row["Product Name Arabic"] = name_ar
            row["Products/Unit of Measure"] = uom
            row["Products/Tags"] = tags_str
            row["Products/Customer Taxes"] = cust_taxes
            row["Products/Vendor Taxes"] = vend_taxes

        if column_options.get('pricing', True):
            if permissions.get("Cost", True):
                row["Cost"] = cost_val
            if permissions.get("Sales Price", True):
                row["Sales Price"] = price_val
            if permissions.get("هامش الربح (%)", True):
                row["هامش الربح (%)"] = margin_val
            if permissions.get("Shati Price", True):
                row["Shati Price"] = shati_val
            if permissions.get("SO Price", True):
                row["SO Price"] = so_p_val
            if permissions.get("Pos Minimum Price", True):
                row["Pos Minimum Price"] = min_p_val

        if column_options.get('totals', True):
            if permissions.get("Quantity On Hand", True):
                row["Quantity On Hand"] = qty_oh
            if permissions.get("365d Sold", True) or permissions.get("Sold", True):
                row["365d Sold"] = total_sold

        if column_options.get('vendors', True):
            if permissions.get("Vendors", True):
                row["Vendors"] = v_info.get('vendor_name', '')
            if permissions.get("Vendors/Price", True):
                row["Vendors/Price"] = v_info.get('vendor_price', 0.0)
            if permissions.get("Vendors/Discount (%)", True):
                row["Vendors/Discount (%)"] = v_info.get('vendor_discount', 0.0)
            if permissions.get("Vendors/Discounted Price", True):
                row["Vendors/Discounted Price"] = v_info.get('vendor_discounted_price', 0.0)
            if permissions.get("Vendors/Last Purchase", True):
                row["Vendors/Last Purchase"] = v_info.get('vendor_last_purchase', '')
            if permissions.get("Vendors/Last Updated on", True):
                row["Vendors/Last Updated on"] = v_info.get('vendor_last_updated', '')
            if permissions.get("Last Received Qty", True):
                row["Last Received Qty"] = last_rcv_qty

        if column_options.get('showrooms', True):
            row.update(sh_row_dict)
            if permissions.get("Showrooms_OnHand", True):
                row["إجمالي رصيد المعارض"] = sh_oh_total
            if permissions.get("Showrooms_Sold", True):
                row["إجمالي مبيعات المعارض"] = sh_sl_total

        # ── Smart Inventory Analytics & Supply Chain Suggestions ────────────
        if column_options.get('analytics', True):
            if permissions.get("أيام التغطية", True):
                row["أيام التغطية"] = days_cover

            if permissions.get("حالة الصنف", True):
                row["حالة الصنف"] = item_status

            target_60d = monthly_sales * 2.0
            suggested_60d_qty = max(0.0, round(target_60d - analysis_oh))

            if permissions.get("الطلب المقترح (60 يوم)", True):
                row["الطلب المقترح (60 يوم)"] = suggested_60d_qty

            if permissions.get("قيمة الطلب المقترح", True):
                if v_info.get('vendor_discounted_price') and float(v_info['vendor_discounted_price']) > 0:
                    buy_p = float(v_info['vendor_discounted_price'])
                elif v_info.get('vendor_price') and float(v_info['vendor_price']) > 0:
                    buy_p = float(v_info['vendor_price'])
                else:
                    buy_p = float(cost_val)
                suggested_val = round(suggested_60d_qty * buy_p, 2)
                row["قيمة الطلب المقترح"] = suggested_val

            if permissions.get("تصنيف ABC", True):
                row["تصنيف ABC"] = "C"

            if permissions.get("توصيات المناقلة", True) and column_options.get('showrooms', True) and target_showrooms:
                transfer_recs = []
                deficits = []
                surpluses = []
                for s in target_showrooms:
                    s_id = s['id']
                    lot = s['lot_stock_id']
                    oh = stock_map.get((pid, lot), 0.0) if lot else 0.0
                    sl = showroom_sales.get(s_id, {}).get(pid, 0.0)
                    sh_monthly = (sl / (period_days / 30.0)) if period_days > 0 else (sl / 12.0)
                    if oh <= 1 and sl > 0:
                        needed_qty = max(1.0, round(sh_monthly - oh))
                        deficits.append((s['name'], oh, sl, needed_qty))
                    elif oh >= 3:
                        keep_buffer = max(1.0, round(sh_monthly * 1.5))
                        surplus_qty = max(0.0, oh - keep_buffer)
                        if surplus_qty >= 1.0:
                            surpluses.append((s['name'], oh, sl, surplus_qty))

                if deficits and surpluses:
                    deficits.sort(key=lambda x: x[2], reverse=True)
                    surpluses.sort(key=lambda x: x[3], reverse=True)
                    for i in range(min(len(deficits), len(surpluses), 2)):
                        from_name = surpluses[i][0].replace("معرض ", "").replace("فرع ", "").strip()
                        to_name   = deficits[i][0].replace("معرض ", "").replace("فرع ", "").strip()
                        transfer_qty = int(max(1, min(deficits[i][3], surpluses[i][3])))
                        transfer_recs.append(f"من {from_name} ({transfer_qty}) إلى {to_name}")

                transfer_note = " | ".join(transfer_recs) if transfer_recs else "─"
                row["توصيات المناقلة"] = transfer_note

        row['_revenue'] = (analysis_sl * price_val) if price_val > 0 else (analysis_sl * cost_val)
        export_rows.append(row)

    # ── Post-process: Pareto ABC Classification across all exported products ──
    if column_options.get('analytics', True) and permissions.get("تصنيف ABC", True) and export_rows:
        total_rev = sum(r.get('_revenue', 0.0) for r in export_rows)
        if total_rev > 0:
            indexed_revs = sorted(enumerate(export_rows), key=lambda x: x[1].get('_revenue', 0.0), reverse=True)
            cum_rev = 0.0
            for idx, r in indexed_revs:
                rev = r.get('_revenue', 0.0)
                if rev <= 0:
                    r["تصنيف ABC"] = "C"
                else:
                    cum_rev += rev
                    cum_pct = (cum_rev / total_rev) * 100.0
                    if cum_pct <= 80.0:
                        r["تصنيف ABC"] = "A"
                    elif cum_pct <= 95.0:
                        r["تصنيف ABC"] = "B"
                    else:
                        r["تصنيف ABC"] = "C"
        else:
            for r in export_rows:
                r["تصنيف ABC"] = "C"

    # Clean temporary helper key
    for r in export_rows:
        r.pop('_revenue', None)

    n_data = len(export_rows)
    notify(80, f"تم بناء {n_data:,} سجل. جاري إنشاء وتنسيق ملف Excel...")
    chk()

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 5 — High-Performance Fast Excel Generation
    # ═════════════════════════════════════════════════════════════════════════
    if not output_path:
        export_dir = r"c:\OdooDB\exports"
        os.makedirs(export_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(export_dir, f"odoo_report_{ts}.xlsx")

    custom_types_map = load_showroom_types()
    sh_code_map = {s['name']: s.get('code', '') for s in all_showrooms}

    C_HDR_MAIN       = "2E75B6"
    C_HDR_SHOWROOM   = "1F4E79"
    C_HDR_SHOWROOM_L = "2E75B6"
    C_HDR_CARE       = "179B9B"   # Vibrant soft turquoise / فيروزي فاتح
    C_HDR_CARE_L     = "2AA49C"   # Light turquoise sub-header
    C_CARE_ROW_BG    = "E6F7F6"
    C_HDR_SUMMARY    = "833C0C"
    C_ALT            = "F2F5F9"
    C_TOTALS_BG      = "FFF2CC"
    C_TOTALS_FG      = "7F6000"
    C_WHITE          = "FFFFFF"
    C_BORDER         = "D9D9D9"

    FILL_HDR_MAIN     = PatternFill("solid", fgColor=C_HDR_MAIN)
    FILL_HDR_SHOWROOM = PatternFill("solid", fgColor=C_HDR_SHOWROOM)
    FILL_HDR_SUB      = PatternFill("solid", fgColor=C_HDR_SHOWROOM_L)
    FILL_HDR_CARE     = PatternFill("solid", fgColor=C_HDR_CARE)
    FILL_HDR_CARE_SUB = PatternFill("solid", fgColor=C_HDR_CARE_L)
    FILL_CARE_ROW     = PatternFill("solid", fgColor=C_CARE_ROW_BG)
    FILL_HDR_SUMMARY  = PatternFill("solid", fgColor=C_HDR_SUMMARY)
    FILL_ALT          = PatternFill("solid", fgColor=C_ALT)
    FILL_TOTALS       = PatternFill("solid", fgColor=C_TOTALS_BG)

    FONT_HDR_WHITE    = Font(name="Segoe UI", size=9, bold=True, color=C_WHITE)
    FONT_HDR_SUB      = Font(name="Segoe UI", size=8, bold=True, color=C_WHITE)
    FONT_DEFAULT      = Font(name="Segoe UI", size=9)
    FONT_TOTALS       = Font(name="Segoe UI", size=9, bold=True, color=C_TOTALS_FG)

    FONT_STATUS_OUT   = Font(name="Segoe UI", size=9, bold=True, color="C00000")
    FONT_STATUS_LOW   = Font(name="Segoe UI", size=9, bold=True, color="ED7D31")
    FONT_STATUS_FAST  = Font(name="Segoe UI", size=9, bold=True, color="385723")
    FONT_STATUS_SLOW  = Font(name="Segoe UI", size=9, bold=True, color="7030A0")
    FONT_STATUS_SURP  = Font(name="Segoe UI", size=9, bold=True, color="2E75B6")
    FONT_STATUS_BAL   = Font(name="Segoe UI", size=9, bold=False, color="333333")

    s_border = Side(style='thin', color=C_BORDER)
    BORDER_DATA = Border(left=s_border, right=s_border, top=s_border, bottom=s_border)
    s_totals = Side(style='thin', color=C_TOTALS_FG)
    BORDER_TOTALS = Border(left=s_totals, right=s_totals, top=s_totals, bottom=s_totals)

    ALIGN_CTR = Alignment(horizontal="center", vertical="center", wrap_text=False)
    ALIGN_HDR = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ALIGN_RT  = Alignment(horizontal="right",  vertical="center", wrap_text=False)
    ALIGN_LT  = Alignment(horizontal="left",   vertical="center", wrap_text=False)

    COLUMN_SPECS = {
        "Internal Reference": {
            "header": "Internal\nReference", "align": ALIGN_CTR, "num_format": "@", "total_type": "count", "width_mode": "data_len"
        },
        "Barcode": {
            "header": "Barcode", "align": ALIGN_CTR, "num_format": "@", "total_type": None, "width_mode": "data_len"
        },
        "Product Packages/Barcode": {
            "header": "Barcodes", "align": ALIGN_RT, "num_format": "@", "total_type": None, "width_mode": "same_as_barcode"
        },
        "Name": {
            "header": "Name", "align": ALIGN_LT, "num_format": "@", "total_type": None, "width_mode": "data_len_capped"
        },
        "Product Name Arabic": {
            "header": "Product Name Arabic", "align": ALIGN_RT, "num_format": "@", "total_type": None, "width_mode": "data_len_capped"
        },
        "Products/Unit of Measure": {
            "header": "Unit", "align": ALIGN_CTR, "num_format": "@", "total_type": None, "width_mode": "auto"
        },
        "Products/Tags": {
            "header": "Products/Tags", "align": ALIGN_RT, "num_format": "@", "total_type": None, "width_mode": "data_len_capped"
        },
        "Products/Customer Taxes": {
            "header": "Customer Taxes", "align": ALIGN_CTR, "num_format": "@", "total_type": None, "width_mode": "data_len"
        },
        "Products/Vendor Taxes": {
            "header": "Vendor Taxes", "align": ALIGN_CTR, "num_format": "@", "total_type": None, "width_mode": "data_len"
        },
        "Cost": {
            "header": "Cost", "align": ALIGN_RT, "num_format": "#,##0.00", "total_type": None, "width_mode": "auto"
        },
        "Sales Price": {
            "header": "Price", "align": ALIGN_RT, "num_format": "#,##0.00", "total_type": None, "width_mode": "auto"
        },
        "هامش الربح (%)": {
            "header": "Margin\n(%)", "align": ALIGN_CTR, "num_format": "0.0%", "total_type": None, "width_mode": "auto"
        },
        "Shati Price": {
            "header": "Shati P", "align": ALIGN_RT, "num_format": "#,##0.00", "total_type": None, "width_mode": "auto"
        },
        "SO Price": {
            "header": "SO Price", "align": ALIGN_RT, "num_format": "#,##0.00", "total_type": None, "width_mode": "auto"
        },
        "Pos Minimum Price": {
            "header": "Min P", "align": ALIGN_RT, "num_format": "#,##0.00", "total_type": None, "width_mode": "auto"
        },
        "Quantity On Hand": {
            "header": "Quantity\nOn Hand", "align": ALIGN_CTR, "num_format": "#,##0", "total_type": "sum", "width_mode": "auto"
        },
        "365d Sold": {
            "header": "365d\nSold", "align": ALIGN_CTR, "num_format": "#,##0", "total_type": "sum", "width_mode": "auto"
        },
        "Sold": {
            "header": "365d\nSold", "align": ALIGN_CTR, "num_format": "#,##0", "total_type": "sum", "width_mode": "auto"
        },
        "Vendors": {
            "header": "Vendor", "align": ALIGN_LT, "num_format": "@", "total_type": None, "width_mode": "data_len_capped"
        },
        "Vendors/Price": {
            "header": "Vendor\nPrice", "align": ALIGN_RT, "num_format": "#,##0.00", "total_type": None, "width_mode": "auto"
        },
        "Vendors/Discount (%)": {
            "header": "Discount\n(%)", "align": ALIGN_CTR, "num_format": "0.00%", "total_type": None, "width_mode": "auto"
        },
        "Vendors/Discounted Price": {
            "header": "Discounted\nPrice", "align": ALIGN_RT, "num_format": "#,##0.00", "total_type": None, "width_mode": "auto"
        },
        "Vendors/Last Purchase": {
            "header": "Last\nPurchase", "align": ALIGN_CTR, "num_format": "yyyy-mm-dd", "total_type": None, "width_mode": "auto", "is_date": True
        },
        "Vendors/Last Updated on": {
            "header": "Last\nUpdated", "align": ALIGN_CTR, "num_format": "yyyy-mm-dd", "total_type": None, "width_mode": "auto", "is_date": True
        },
        "Last Received Qty": {
            "header": "Last Qty\nReceived", "align": ALIGN_CTR, "num_format": "#,##0", "total_type": "sum", "width_mode": "auto"
        },
        "إجمالي رصيد المعارض": {
            "header": "إجمالي رصيد\nالمعارض", "align": ALIGN_CTR, "num_format": "#,##0", "total_type": "sum", "width_mode": "auto"
        },
        "إجمالي مبيعات المعارض": {
            "header": "إجمالي مبيعات\nالمعارض", "align": ALIGN_CTR, "num_format": "#,##0", "total_type": "sum", "width_mode": "auto"
        },
        "تصنيف ABC": {
            "header": "تصنيف\nABC", "align": ALIGN_CTR, "num_format": "@", "total_type": None, "width_mode": "auto"
        },
        "أيام التغطية": {
            "header": "أيام التغطية\n(DOI)", "align": ALIGN_CTR, "num_format": "#,##0", "total_type": None, "width_mode": "auto"
        },
        "حالة الصنف": {
            "header": "حالة الصنف", "align": ALIGN_CTR, "num_format": "@", "total_type": None, "width_mode": "auto"
        },
        "الطلب المقترح (60 يوم)": {
            "header": "الطلب المقترح\n(60 يوم)", "align": ALIGN_CTR, "num_format": "#,##0", "total_type": "sum", "width_mode": "auto"
        },
        "قيمة الطلب المقترح": {
            "header": "قيمة الطلب\nالمقترح (ريال)", "align": ALIGN_RT, "num_format": "#,##0.00", "total_type": "sum", "width_mode": "auto"
        },
        "توصيات المناقلة": {
            "header": "توصيات\nالمناقلة", "align": ALIGN_CTR, "num_format": "@", "total_type": None, "width_mode": "data_len_capped"
        },
    }

    def _parse_cell_value(val, is_date=False):
        if val is None or val == "":
            return None
        if is_date:
            s = str(val).strip()
            if len(s) >= 10:
                try:
                    return datetime.strptime(s[:10], '%Y-%m-%d').date()
                except Exception:
                    return s[:10]
            return s
        return val

    first_row_sample = export_rows[0] if export_rows else {}
    all_col_keys = list(first_row_sample.keys())

    SH_OH_SUFFIX = " / On Hand"
    SH_SL_SUFFIX = " / Sold"
    SUMMARY_COLS = ["إجمالي رصيد المعارض", "إجمالي مبيعات المعارض", "تصنيف ABC", "أيام التغطية", "حالة الصنف", "الطلب المقترح (60 يوم)", "قيمة الطلب المقترح", "توصيات المناقلة"]

    fixed_col_keys = [k for k in all_col_keys
                      if not k.endswith(SH_OH_SUFFIX) and not k.endswith(SH_SL_SUFFIX)
                      and k not in SUMMARY_COLS]

    showroom_pairs = []
    seen_sh = set()
    for k in all_col_keys:
        if k.endswith(SH_OH_SUFFIX):
            sh_name = k[:-len(SH_OH_SUFFIX)]
            if sh_name not in seen_sh:
                seen_sh.add(sh_name)
                oh_key = k
                sl_key = f"{sh_name}{SH_SL_SUFFIX}"
                has_oh = oh_key in first_row_sample
                has_sl = sl_key in first_row_sample
                showroom_pairs.append((sh_name, oh_key if has_oh else None, sl_key if has_sl else None))
        elif k.endswith(SH_SL_SUFFIX):
            sh_name = k[:-len(SH_SL_SUFFIX)]
            if sh_name not in seen_sh:
                seen_sh.add(sh_name)
                showroom_pairs.append((sh_name, None, k))

    summary_col_keys = [k for k in all_col_keys if k in SUMMARY_COLS]

    USE_TWO_ROWS = bool(showroom_pairs)
    HEADER_ROWS = 2 if USE_TWO_ROWS else 1
    DATA_START_ROW = HEADER_ROWS + 1

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "تفاصيل المنتجات والمعارض"
    ws.views.sheetView[0].rightToLeft = True
    ws.freeze_panes = f"A{DATA_START_ROW}"

    col_key_to_excel_col = {}
    col_idx = 1

    # 1) Fixed columns
    for k in fixed_col_keys:
        col_key_to_excel_col[k] = col_idx
        spec = COLUMN_SPECS.get(k, {})
        hdr_text = spec.get("header", k)

        cell1 = ws.cell(row=1, column=col_idx, value=hdr_text)
        cell1.fill      = FILL_HDR_MAIN
        cell1.font      = FONT_HDR_WHITE
        cell1.alignment = ALIGN_HDR
        cell1.border    = BORDER_DATA

        if USE_TWO_ROWS:
            cell2 = ws.cell(row=2, column=col_idx)
            cell2.fill   = FILL_HDR_MAIN
            cell2.alignment = ALIGN_HDR
            cell2.border = BORDER_DATA
            ws.merge_cells(start_row=1, start_column=col_idx, end_row=2, end_column=col_idx)

        col_idx += 1

    # 2) Showroom pairs
    for sh_name, oh_key, sl_key in showroom_pairs:
        pair_cols = [c for c in [oh_key, sl_key] if c]
        pair_count = len(pair_cols)
        sh_start_col = col_idx

        sh_code = sh_code_map.get(sh_name, '')
        is_care = (get_showroom_category(sh_code, sh_name, custom_types_map) == 'care')

        fill_sh  = FILL_HDR_CARE if is_care else FILL_HDR_SHOWROOM
        fill_sub = FILL_HDR_CARE_SUB if is_care else FILL_HDR_SUB

        cell_sh = ws.cell(row=1, column=sh_start_col, value=sh_name)
        cell_sh.fill      = fill_sh
        cell_sh.font      = FONT_HDR_WHITE
        cell_sh.alignment = ALIGN_HDR
        cell_sh.border    = BORDER_DATA

        if USE_TWO_ROWS and pair_count == 2:
            cell_sh2 = ws.cell(row=1, column=sh_start_col + 1)
            cell_sh2.fill   = fill_sh
            cell_sh2.alignment = ALIGN_HDR
            cell_sh2.border = BORDER_DATA
            ws.merge_cells(start_row=1, start_column=sh_start_col,
                           end_row=1, end_column=sh_start_col + 1)

        for sub_key in pair_cols:
            sub_label = "On Hand" if sub_key and sub_key.endswith(SH_OH_SUFFIX) else "Sold"
            col_key_to_excel_col[sub_key] = col_idx

            if USE_TWO_ROWS:
                cell2 = ws.cell(row=2, column=col_idx, value=sub_label)
                cell2.fill      = fill_sub
                cell2.font      = FONT_HDR_SUB
                cell2.alignment = ALIGN_HDR
                cell2.border    = BORDER_DATA

            ws.column_dimensions[get_column_letter(col_idx)].width = 9
            col_idx += 1

    # 3) Summary & Analytics columns
    for k in summary_col_keys:
        col_key_to_excel_col[k] = col_idx
        if "رصيد" in k:
            label_top = "إجمالي رصيد\nالمعارض"
            col_w = 14
        elif "مبيعات" in k:
            label_top = "إجمالي مبيعات\nالمعارض"
            col_w = 14
        elif "ABC" in k or "تصنيف" in k:
            label_top = "تصنيف\nABC"
            col_w = 10
        elif "تغطية" in k or "أيام" in k:
            label_top = "أيام التغطية\n(DOI)"
            col_w = 12
        elif "حالة" in k:
            label_top = "حالة الصنف"
            col_w = 15
        elif "قيمة" in k:
            label_top = "قيمة الطلب\nالمقترح (ريال)"
            col_w = 15
        elif "مقترح" in k:
            label_top = "الطلب المقترح\n(60 يوم)"
            col_w = 14
        elif "مناقلة" in k:
            label_top = "توصيات\nالمناقلة"
            col_w = 28
        else:
            label_top = k
            col_w = 14

        cell1 = ws.cell(row=1, column=col_idx, value=label_top)
        cell1.fill      = FILL_HDR_SUMMARY
        cell1.font      = FONT_HDR_WHITE
        cell1.alignment = ALIGN_HDR
        cell1.border    = BORDER_DATA
        if USE_TWO_ROWS:
            cell2 = ws.cell(row=2, column=col_idx)
            cell2.fill   = FILL_HDR_SUMMARY
            cell2.alignment = ALIGN_HDR
            cell2.border = BORDER_DATA
            ws.merge_cells(start_row=1, start_column=col_idx, end_row=2, end_column=col_idx)
        ws.column_dimensions[get_column_letter(col_idx)].width = col_w
        col_idx += 1

    total_excel_cols = col_idx - 1

    ws.row_dimensions[1].height = 28
    if USE_TWO_ROWS:
        ws.row_dimensions[2].height = 20

    # ── Fast Column Widths (Sample first 500 rows) ─────────────────────────
    sample_rows = export_rows[:500] if export_rows else []
    barcode_col_width = 14
    for k in fixed_col_keys:
        spec = COLUMN_SPECS.get(k, {})
        wmode = spec.get("width_mode", "auto")
        col_letter = get_column_letter(col_key_to_excel_col[k])

        if k == "Barcode":
            data_lens = [len(str(r.get(k) or '')) for r in sample_rows]
            max_l = max(data_lens) if data_lens else 10
            barcode_col_width = max(max_l + 3, 13)
            ws.column_dimensions[col_letter].width = barcode_col_width
        elif k == "Product Packages/Barcode":
            ws.column_dimensions[col_letter].width = barcode_col_width
        elif k == "Internal Reference":
            data_lens = [len(str(r.get(k) or '')) for r in sample_rows]
            max_l = max(data_lens) if data_lens else 10
            ws.column_dimensions[col_letter].width = max(max_l + 3, 11)
        elif wmode == "data_len":
            data_lens = [len(str(r.get(k) or '')) for r in sample_rows]
            max_l = max(data_lens) if data_lens else 8
            ws.column_dimensions[col_letter].width = max(max_l + 3, 10)
        elif wmode == "data_len_capped":
            data_lens = [len(str(r.get(k) or '')) for r in sample_rows]
            max_l = max(data_lens) if data_lens else 15
            ws.column_dimensions[col_letter].width = min(max(max_l + 3, 15), 45)
        else:
            hdr_text = spec.get("header", k)
            max_line = max([len(line) for line in hdr_text.split('\n')]) if hdr_text else len(k)
            ws.column_dimensions[col_letter].width = max(max_line + 3, 10)

    # ── Fast Write Data Rows ───────────────────────────────────────────────
    ordered_keys = list(col_key_to_excel_col.keys())
    ordered_specs = [COLUMN_SPECS.get(k, {}) for k in ordered_keys]

    for data_row_idx, row_data in enumerate(export_rows):
        if data_row_idx % 2500 == 0:
            chk()
            pct = 80 + int((data_row_idx / max(n_data, 1)) * 16)
            notify(pct, f"كتابة صفوف Excel: {data_row_idx:,}/{n_data:,}...")

        is_alt = (data_row_idx % 2 == 1)
        row_fill = FILL_ALT if is_alt else None

        row_vals = []
        for k, spec in zip(ordered_keys, ordered_specs):
            is_date = spec.get("is_date", False)
            raw_val = row_data.get(k, "")
            val = _parse_cell_value(raw_val, is_date=is_date)
            row_vals.append(val)

        ws.append(row_vals)
        excel_row = DATA_START_ROW + data_row_idx

        for c_idx, (k, spec, val) in enumerate(zip(ordered_keys, ordered_specs, row_vals), 1):
            cell = ws.cell(row=excel_row, column=c_idx)
            cell.border = BORDER_DATA
            if row_fill:
                cell.fill = row_fill

            align = spec.get("align", ALIGN_CTR)
            cell.alignment = align

            if k == "حالة الصنف":
                if val == "نفد المخزون":
                    cell.font = FONT_STATUS_OUT
                elif val == "قارب على النفاذ":
                    cell.font = FONT_STATUS_LOW
                elif val == "سريع الحركة":
                    cell.font = FONT_STATUS_FAST
                elif val == "راكد":
                    cell.font = FONT_STATUS_SLOW
                elif val == "فائض المخزون":
                    cell.font = FONT_STATUS_SURP
                else:
                    cell.font = FONT_STATUS_BAL
            elif k == "تصنيف ABC":
                if val == "A":
                    cell.font = Font(name="Segoe UI", size=10, bold=True, color="1E7E34")
                elif val == "B":
                    cell.font = Font(name="Segoe UI", size=10, bold=True, color="0056B3")
                else:
                    cell.font = Font(name="Segoe UI", size=9, bold=False, color="6C757D")
            else:
                cell.font = FONT_DEFAULT

            is_date = spec.get("is_date", False)
            if is_date:
                cell.number_format = 'yyyy-mm-dd'
            elif isinstance(val, (int, float)):
                nfmt = spec.get("num_format")
                if nfmt:
                    cell.number_format = nfmt
                elif isinstance(val, float) and val != int(val):
                    cell.number_format = '#,##0.00'
                else:
                    cell.number_format = '#,##0'

    # ── Write Totals Row ───────────────────────────────────────────────────
    if n_data > 0:
        totals_excel_row = DATA_START_ROW + n_data

        label_col_key = None
        for cand in ["Product Name Arabic", "Name", "Internal Reference"]:
            if cand in col_key_to_excel_col and cand != "Internal Reference":
                label_col_key = cand
                break

        for k, ec in col_key_to_excel_col.items():
            spec = COLUMN_SPECS.get(k, {})
            ttype = spec.get("total_type")

            if k.endswith(SH_OH_SUFFIX) or k.endswith(SH_SL_SUFFIX) or k in {"إجمالي رصيد المعارض", "إجمالي مبيعات المعارض", "الطلب المقترح (60 يوم)", "قيمة الطلب المقترح"}:
                ttype = "sum"

            cell = ws.cell(row=totals_excel_row, column=ec)
            cell.fill   = FILL_TOTALS
            cell.font   = FONT_TOTALS
            cell.border = BORDER_TOTALS

            align = spec.get("align", ALIGN_CTR)
            cell.alignment = align

            col_let = get_column_letter(ec)
            r_start = DATA_START_ROW
            r_end   = DATA_START_ROW + n_data - 1

            if k == label_col_key:
                cell.value = "▶ الإجماليات"
                cell.alignment = ALIGN_RT
            elif k == "Internal Reference":
                cell.value = f'=SUBTOTAL(103, {col_let}{r_start}:{col_let}{r_end})'
                cell.number_format = '#,##0'
            elif ttype == "sum":
                cell.value = f'=SUBTOTAL(9, {col_let}{r_start}:{col_let}{r_end})'
                nfmt = spec.get("num_format", "#,##0")
                cell.number_format = nfmt
            else:
                cell.value = None

        ws.row_dimensions[totals_excel_row].height = 22

    # ── Sheet 2: Branch Summary ────────────────────────────────────────────
    if column_options.get('showrooms', True) and target_showrooms:
        ws2 = wb.create_sheet(title="ملخص المعارض والفروع")
        ws2.views.sheetView[0].rightToLeft = True

        hdr2 = ["كود الفرع", "اسم المعرض / الفرع", "تصنيف الفرع", "إجمالي الرصيد (قطع)",
                "قيمة المخزون بالتكلفة (ر.س)", "قيمة المبيعات بالبيع (ر.س)", "إجمالي المبيعات (قطع)"]
        for c_i, h_text in enumerate(hdr2, 1):
            c = ws2.cell(row=1, column=c_i, value=h_text)
            c.fill      = FILL_HDR_MAIN
            c.font      = FONT_HDR_WHITE
            c.alignment = ALIGN_CTR
            c.border    = BORDER_DATA

        ws2.row_dimensions[1].height = 26

        s_rows = sorted(branch_summary.values(), key=lambda x: x['total_on_hand'], reverse=True)
        for r_i, s_data in enumerate(s_rows, 2):
            is_alt = (r_i % 2 == 1)
            is_care = (get_showroom_category(s_data['code'], s_data['name'], custom_types_map) == 'care')
            type_label = "🌿 عناية" if is_care else "🏬 معارض"
            row_fill = FILL_CARE_ROW if is_care else (FILL_ALT if is_alt else None)

            vals = [
                (s_data['code'], ALIGN_CTR, "@"),
                (s_data['name'], ALIGN_RT, "@"),
                (type_label, ALIGN_CTR, "@"),
                (s_data['total_on_hand'], ALIGN_CTR, "#,##0"),
                (s_data['total_cost_value'], ALIGN_RT, "#,##0.00"),
                (s_data['total_sales_value'], ALIGN_RT, "#,##0.00"),
                (s_data['total_sold_units'], ALIGN_CTR, "#,##0"),
            ]
            for c_i, (v, align, nfmt) in enumerate(vals, 1):
                c = ws2.cell(row=r_i, column=c_i, value=v)
                c.font = FONT_DEFAULT
                c.alignment = align
                c.number_format = nfmt
                c.border = BORDER_DATA
                if row_fill:
                    c.fill = row_fill
            ws2.row_dimensions[r_i].height = 18

        last_r = len(s_rows) + 1
        tot_r  = last_r + 1
        tot_cells = [
            (1, "▶ الإجمالي العام", ALIGN_CTR, "@", False),
            (2, "", ALIGN_RT, "@", False),
            (3, "", ALIGN_CTR, "@", False),
            (4, f"=SUBTOTAL(9, D2:D{last_r})", ALIGN_CTR, "#,##0", True),
            (5, f"=SUBTOTAL(9, E2:E{last_r})", ALIGN_RT, "#,##0.00", True),
            (6, f"=SUBTOTAL(9, F2:F{last_r})", ALIGN_RT, "#,##0.00", True),
            (7, f"=SUBTOTAL(9, G2:G{last_r})", ALIGN_CTR, "#,##0", True),
        ]
        for c_i, v, align, nfmt, is_formula in tot_cells:
            c = ws2.cell(row=tot_r, column=c_i, value=v)
            c.fill   = FILL_TOTALS
            c.font   = FONT_TOTALS
            c.alignment = align
            c.number_format = nfmt
            c.border = BORDER_TOTALS

        ws2.row_dimensions[tot_r].height = 22
        col_w2 = [14, 28, 16, 20, 26, 26, 20]
        for c_i, w in enumerate(col_w2, 1):
            ws2.column_dimensions[get_column_letter(c_i)].width = w

    if include_methodology_guide:
        notify(97, "جاري إعداد دليل ومنهجية الحسابات...")
        chk()
        _build_methodology_sheet(wb)

    notify(98, "جاري حفظ ملف Excel النهائي...")
    chk()
    wb.save(output_path)

    elapsed = round(time.time() - t_start, 2)
    notify(100, f"✅ اكتمل التصدير بنجاح! تم تصدير {n_data:,} صنف في {elapsed} ثانية.")

    return {
        'success': True,
        'output_path': output_path,
        'total_records': n_data,
        'total_rows': n_data,
        'total_columns': total_excel_cols,
        'total_time': elapsed,
        'elapsed_seconds': elapsed
    }
