"""
pos_discount_engine.py — High-Performance POS Discounted Sales & Vendor Compensation Report Engine
Designed by: عبدالله الخطيب (Abdullah Al-Khatib)
Version: v1.03 (Executive Pro BI Edition)

FEATURES IN v1.03:
  1. Executive KPI Dashboard Sheet (📊 لوحة المؤشرات) with top financial KPI cards, Top 5 claimed items, & showroom breakdown.
  2. Official Print-Ready Vendor Claim Form Sheet (📄 كشف مطالبة معتمد) with company letterhead, logo, and 3 formal signature blocks.
  3. Product Rollup Summary Sheet (📦 ملخص الأصناف) aggregating each product into a single concise row.
  4. Detailed POS Transactions Sheet (🧾 تفاصيل الحركات) with Dynamic SUBTOTAL(9) totals, refund highlight, and Data Bars.
  5. Optional Per-Showroom Tabs (🏢 المعارض) for multi-branch distribution.
  6. Direct High-Fidelity PDF Export of the Claim Form via native Excel COM automation.
  7. Official Company Profile & Logo integration from company_profile.py.
"""

import os
import sys
import time
import fnmatch
import xmlrpc.client
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import DataBarRule
from openpyxl.drawing.image import Image as OpenpyxlImage

from security import get_odoo_credentials
from exporter_engine import get_active_showrooms, get_all_product_tags, safe_execute_kw, match_wildcards, parse_tokens
from company_profile import load_company_profile


def export_claim_to_pdf(excel_path, pdf_path, sheet_name="📄 كشف مطالبة معتمد"):
    """
    Exports a specific worksheet from the generated Excel workbook to a PDF file
    using native Microsoft Excel COM automation.
    """
    try:
        import win32com.client
        import pythoncom
        pythoncom.CoInitialize()
        excel = win32com.client.DispatchEx('Excel.Application')
        excel.Visible = False
        excel.DisplayAlerts = False
        abs_excel = os.path.abspath(excel_path)
        abs_pdf = os.path.abspath(pdf_path)

        wb = excel.Workbooks.Open(abs_excel)
        target_sheet = None
        for s in wb.Sheets:
            if s.Name == sheet_name:
                target_sheet = s
                break
        if not target_sheet:
            target_sheet = wb.Sheets(1)

        # 0 = xlTypePDF
        target_sheet.ExportAsFixedFormat(0, abs_pdf)
        wb.Close(False)
        excel.Quit()
        return abs_pdf
    except Exception as e:
        print(f"Warning: PDF export failed: {e}")
        return None


def generate_pos_discount_report(
    filter_internal_ref=None,
    filter_barcode=None,
    filter_name=None,
    filter_tags=None,
    selected_showroom_ids=None,
    sales_period="all",
    custom_date_from=None,
    custom_date_to=None,
    include_showroom_col=False,
    include_all_sales=False,
    include_pro_sheets=True,
    include_showroom_sheets=False,
    export_claim_pdf=False,
    output_path=None,
    progress_callback=None,
    cancel_check_callback=None,
    is_cancelled=None,
    **kwargs
):
    """
    High-performance export function for detailed POS discounted sales and supplier compensation claims.
    """
    t_start = time.time()

    def notify(pct, text):
        if progress_callback:
            try:
                progress_callback(pct, text)
            except Exception:
                pass

    def chk():
        if cancel_check_callback and cancel_check_callback():
            raise InterruptedError("تم إلغاء عملية التصدير من قبل المستخدم.")
        if is_cancelled and is_cancelled():
            raise InterruptedError("تم إلغاء عملية التصدير من قبل المستخدم.")

    notify(2, "جاري التحقق من إعدادات الاتصال وفلاتر البحث...")
    chk()

    creds = get_odoo_credentials()
    if not creds:
        raise ValueError("بيانات الاتصال بقاعدة بيانات Odoo غير متوفرة.")

    url, db, username, password = creds

    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, username, password, {})
    if not uid:
        raise ConnectionError("فشل تسجيل الدخول إلى خادم Odoo.")

    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 1 — Parameter & Domain Resolution
    # ═════════════════════════════════════════════════════════════════════════
    notify(5, "جاري تحديد نطاق الفلاتر والفترة الزمنية...")
    chk()

    # 1. Date Range Domain
    date_filter = []
    period_title = "كافة الفترات"
    now_ksa = datetime.now()

    if sales_period == "today":
        start_ksa = now_ksa.replace(hour=0, minute=0, second=0, microsecond=0)
        end_ksa = now_ksa.replace(hour=23, minute=59, second=59, microsecond=999999)
        start_utc = start_ksa - timedelta(hours=3)
        end_utc = end_ksa - timedelta(hours=3)
        date_filter = [
            ['order_id.date_order', '>=', start_utc.strftime("%Y-%m-%d %H:%M:%S")],
            ['order_id.date_order', '<=', end_utc.strftime("%Y-%m-%d %H:%M:%S")]
        ]
        period_title = f"اليوم ({start_ksa.strftime('%Y-%m-%d')})"

    elif sales_period == "7d":
        start_ksa = (now_ksa - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = start_ksa - timedelta(hours=3)
        date_filter = [['order_id.date_order', '>=', start_utc.strftime("%Y-%m-%d %H:%M:%S")]]
        period_title = "آخر 7 أيام"

    elif sales_period in ("30d", "last_30_days"):
        start_ksa = (now_ksa - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = start_ksa - timedelta(hours=3)
        date_filter = [['order_id.date_order', '>=', start_utc.strftime("%Y-%m-%d %H:%M:%S")]]
        period_title = "آخر 30 يوماً"

    elif sales_period in ("60d", "last_60_days"):
        start_ksa = (now_ksa - timedelta(days=60)).replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = start_ksa - timedelta(hours=3)
        date_filter = [['order_id.date_order', '>=', start_utc.strftime("%Y-%m-%d %H:%M:%S")]]
        period_title = "آخر 60 يوماً"

    elif sales_period in ("90d", "last_90_days"):
        start_ksa = (now_ksa - timedelta(days=90)).replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = start_ksa - timedelta(hours=3)
        date_filter = [['order_id.date_order', '>=', start_utc.strftime("%Y-%m-%d %H:%M:%S")]]
        period_title = "آخر 90 يوماً"

    elif sales_period in ("180d", "last_180_days"):
        start_ksa = (now_ksa - timedelta(days=180)).replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = start_ksa - timedelta(hours=3)
        date_filter = [['order_id.date_order', '>=', start_utc.strftime("%Y-%m-%d %H:%M:%S")]]
        period_title = "آخر 180 يوماً"

    elif sales_period in ("365d", "last_365_days"):
        start_ksa = (now_ksa - timedelta(days=365)).replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = start_ksa - timedelta(hours=3)
        date_filter = [['order_id.date_order', '>=', start_utc.strftime("%Y-%m-%d %H:%M:%S")]]
        period_title = "آخر 365 يوماً"

    elif sales_period == "this_year":
        start_ksa = datetime(now_ksa.year, 1, 1, 0, 0, 0)
        start_utc = start_ksa - timedelta(hours=3)
        date_filter = [['order_id.date_order', '>=', start_utc.strftime("%Y-%m-%d %H:%M:%S")]]
        period_title = f"العام الحالي ({now_ksa.year})"

    elif sales_period == "custom":
        if custom_date_from:
            try:
                dt_f = datetime.strptime(custom_date_from.strip(), "%Y-%m-%d") - timedelta(hours=3)
                date_filter.append(['order_id.date_order', '>=', dt_f.strftime("%Y-%m-%d %H:%M:%S")])
            except Exception:
                pass
        if custom_date_to:
            try:
                dt_t = (datetime.strptime(custom_date_to.strip(), "%Y-%m-%d") + timedelta(days=1)) - timedelta(hours=3) - timedelta(seconds=1)
                date_filter.append(['order_id.date_order', '<=', dt_t.strftime("%Y-%m-%d %H:%M:%S")])
            except Exception:
                pass
        period_title = f"من {custom_date_from or 'البداية'} إلى {custom_date_to or 'اليوم'}"

    # 2. Showrooms to POS Config ID Mapping
    all_showrooms = get_active_showrooms()
    showroom_dict = {s['id']: s['name'] for s in all_showrooms}
    stock_wh_ids = list(showroom_dict.keys())

    pos_configs = safe_execute_kw(
        models, db, uid, password, 'pos.config', 'search_read',
        [[['picking_type_id.warehouse_id', 'in', stock_wh_ids]]],
        {'fields': ['id', 'name', 'picking_type_id']}
    )

    config_to_sh_name = {}
    config_to_wh_id = {}
    for cfg in pos_configs:
        pt = cfg.get('picking_type_id')
        if pt:
            pt_id = pt[0] if isinstance(pt, (list, tuple)) else pt
            wh_info = safe_execute_kw(models, db, uid, password, 'stock.picking.type', 'read',
                                     [[pt_id]], {'fields': ['warehouse_id']})
            if wh_info and wh_info[0].get('warehouse_id'):
                wh_id = wh_info[0]['warehouse_id'][0]
                sh_name = showroom_dict.get(wh_id, cfg.get('name'))
                config_to_sh_name[cfg['id']] = sh_name
                config_to_wh_id[cfg['id']] = wh_id

    # Filter by selected showrooms
    selected_config_ids = []
    if selected_showroom_ids:
        selected_wh_set = set(selected_showroom_ids)
        for cfg_id, wh_id in config_to_wh_id.items():
            if wh_id in selected_wh_set:
                selected_config_ids.append(cfg_id)
        showroom_label = f"{len(selected_showroom_ids)} معارض محددة"
    else:
        selected_config_ids = list(config_to_sh_name.keys())
        showroom_label = "كافة المعارض والفروع"

    # 3. Product & Tag Filtering Pre-flight
    matched_product_ids = None
    has_prod_filter = any([filter_internal_ref, filter_barcode, filter_name, filter_tags])

    ref_tokens = parse_tokens(filter_internal_ref)
    bc_tokens = parse_tokens(filter_barcode)
    name_tokens = parse_tokens(filter_name)
    tg_tokens = parse_tokens(filter_tags)

    if has_prod_filter:
        notify(7, "جاري تصفية وتحديد الأصناف والوسوم المطلوبة...")
        chk()

        p_dom = []

        # A. Tags Filter
        matched_tag_ids = set()
        if tg_tokens:
            all_tags = get_all_product_tags()
            for tg in all_tags:
                tname = tg['name']
                if match_wildcards(tname, tg_tokens):
                    matched_tag_ids.add(tg['id'])
            if matched_tag_ids:
                p_dom.append(['product_tag_ids', 'in', list(matched_tag_ids)])
            else:
                notify(100, "لم يتم العثور على أي وسوم تطابق الإدخال.")
                raise ValueError("لم يتم العثور على أي وسوم تطابق الإدخال.")

        # B. Internal Reference
        if ref_tokens:
            stems = [t.replace('*', '').replace('?', '').strip() for t in ref_tokens if t.strip()]
            if stems:
                if len(stems) == 1:
                    p_dom.append(['default_code', 'ilike', stems[0]])
                else:
                    for _ in range(len(stems) - 1):
                        p_dom.append('|')
                    for s in stems:
                        p_dom.append(['default_code', 'ilike', s])

        # C. Barcode
        if bc_tokens:
            stems = [t.replace('*', '').replace('?', '').strip() for t in bc_tokens if t.strip()]
            if stems:
                clauses = []
                for s in stems:
                    clauses.append(['|', ['barcode', 'ilike', s], ['packaging_ids.barcode', 'ilike', s]])
                if len(clauses) == 1:
                    p_dom.extend(clauses[0])
                else:
                    for _ in range(len(clauses) - 1):
                        p_dom.append('|')
                    for cl in clauses:
                        p_dom.extend(cl)

        # D. Product Name (Arabic OR English)
        if name_tokens:
            stems = [t.replace('*', '').replace('?', '').strip() for t in name_tokens if t.strip()]
            if stems:
                clauses = []
                for s in stems:
                    clauses.append(['|', ['name', 'ilike', s], ['product_name_arabic', 'ilike', s]])
                if len(clauses) == 1:
                    p_dom.extend(clauses[0])
                else:
                    for _ in range(len(clauses) - 1):
                        p_dom.append('|')
                    for cl in clauses:
                        p_dom.extend(cl)

        # Query product candidates
        p_fields = ['id', 'default_code', 'barcode', 'name', 'product_name_arabic', 'product_tag_ids']
        found_products = safe_execute_kw(models, db, uid, password, 'product.product', 'search_read',
                                        [p_dom], {'fields': p_fields})

        cand_pids = [p['id'] for p in found_products]
        pkg_map = {}
        if bc_tokens and cand_pids:
            for i in range(0, len(cand_pids), 5000):
                batch_pids = cand_pids[i:i + 5000]
                pkgs = safe_execute_kw(models, db, uid, password, 'product.packaging', 'search_read',
                                       [[['product_id', 'in', batch_pids], ['barcode', '!=', False]]],
                                       {'fields': ['product_id', 'barcode']})
                for pkg in pkgs:
                    pid = pkg['product_id'][0] if pkg.get('product_id') else None
                    if pid:
                        pkg_map.setdefault(pid, []).append(pkg['barcode'])

        filtered_pids = []
        for p in found_products:
            code_val = str(p.get('default_code') or '')
            barcode_val = str(p.get('barcode') or '')
            pkg_bcs = pkg_map.get(p['id'], [])
            name_en = str(p.get('name') or '')
            name_ar = str(p.get('product_name_arabic') or '')
            p_tags = p.get('product_tag_ids') or []

            if ref_tokens and not match_wildcards(code_val, ref_tokens):
                continue
            if bc_tokens and not match_wildcards([barcode_val] + pkg_bcs, bc_tokens):
                continue
            if name_tokens and not match_wildcards([name_en, name_ar], name_tokens):
                continue
            if tg_tokens and matched_tag_ids:
                if not any(tid in matched_tag_ids for tid in p_tags):
                    continue

            filtered_pids.append(p['id'])

        matched_product_ids = filtered_pids
        if not matched_product_ids:
            notify(100, "لم يتم العثور على أي أصناف تطابق الفلاتر المحددة.")
            raise ValueError("لم يتم العثور على أي أصناف تطابق الفلاتر المحددة.")

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 2 — Multi-Threaded Chunk Retrieval of Lines
    # ═════════════════════════════════════════════════════════════════════════
    line_domain = [
        ['order_id.state', 'in', ['paid', 'done', 'invoiced']]
    ]
    if not include_all_sales:
        line_domain.append(['discount', '!=', 0])
    line_domain += date_filter

    if selected_config_ids and len(selected_config_ids) < len(config_to_sh_name):
        line_domain.append(['order_id.config_id', 'in', selected_config_ids])

    if matched_product_ids is not None:
        if len(matched_product_ids) <= 10000:
            line_domain.append(['product_id', 'in', matched_product_ids])

    mode_text = "حركات المبيعات" if include_all_sales else "حركات المبيعات المخصومة"
    notify(10, f"جاري احتساب إجمالي {mode_text} في نقاط البيع...")
    chk()

    total_lines = safe_execute_kw(models, db, uid, password, 'pos.order.line', 'search_count', [line_domain])

    if total_lines == 0:
        err_msg = f"لم يتم العثور على أي {mode_text} للفلاتر المحددة."
        notify(100, err_msg)
        raise ValueError(err_msg)

    if total_lines > 1000000:
        err_msg = f"عدد الحركات المطابقة ({total_lines:,}) يتجاوز سعة ملف إكسيل (1,048,576 سطر). يرجى تضييق نطاق البحث باختيار فترة زمنية أو أصناف أو معارض محددة."
        notify(100, err_msg)
        raise ValueError(err_msg)

    mode_hrakat = "حركة بيع" if include_all_sales else "حركة مخصومة"
    notify(15, f"تم العثور على {total_lines:,} {mode_hrakat}. جاري جلب تفاصيل السطور بالتوازي...")
    chk()

    CHUNK_SIZE = 5000
    line_fields = ['id', 'order_id', 'product_id', 'qty', 'price_unit', 'discount', 'price_subtotal_incl']

    def _fetch_line_chunk(offset_val, limit_val):
        m_local = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        return safe_execute_kw(m_local, db, uid, password, 'pos.order.line', 'search_read',
                               [line_domain],
                               {'fields': line_fields, 'offset': offset_val, 'limit': limit_val, 'order': 'id asc'})

    offsets = list(range(0, total_lines, CHUNK_SIZE))
    all_lines = []
    completed_chunks = 0

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_fetch_line_chunk, off, CHUNK_SIZE): off for off in offsets}
        for fut in futures:
            chk()
            res_chunk = fut.result()
            all_lines.extend(res_chunk)
            completed_chunks += 1
            pct = 15 + int((completed_chunks / len(offsets)) * 40)
            notify(pct, f"تم جلب {len(all_lines):,} من أصل {total_lines:,} سطر...")

    chk()

    # In-memory post-filter if matched_product_ids was too large for Odoo domain
    if matched_product_ids is not None and len(matched_product_ids) > 10000:
        target_pids = set(matched_product_ids)
        all_lines = [l for l in all_lines if l['product_id'] and l['product_id'][0] in target_pids]
        if not all_lines:
            notify(100, "لم يتم العثور على حركات مبيعات تطابق الأصناف المحددة.")
            raise ValueError("لم يتم العثور على حركات مبيعات تطابق الأصناف المحددة.")

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 3 — Concurrent Bulk Batch Caching of Orders & Products
    # ═════════════════════════════════════════════════════════════════════════
    notify(58, "جاري استخراج بيانات الفواتير والأصناف والباركود...")
    chk()

    unique_order_ids = list({l['order_id'][0] for l in all_lines if l.get('order_id')})
    unique_product_ids = list({l['product_id'][0] for l in all_lines if l.get('product_id')})

    BATCH_SIZE = 3000

    def _fetch_order_batch(b_ids):
        m_local = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        return safe_execute_kw(m_local, db, uid, password, 'pos.order', 'read',
                               [b_ids], {'fields': ['name', 'pos_reference', 'date_order', 'account_move', 'config_id']})

    def _fetch_product_batch(b_ids):
        m_local = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        return safe_execute_kw(m_local, db, uid, password, 'product.product', 'read',
                               [b_ids], {'fields': ['default_code', 'barcode', 'name', 'product_name_arabic', 'packaging_ids']})

    order_batches = [unique_order_ids[i:i + BATCH_SIZE] for i in range(0, len(unique_order_ids), BATCH_SIZE)]
    product_batches = [unique_product_ids[i:i + BATCH_SIZE] for i in range(0, len(unique_product_ids), BATCH_SIZE)]

    orders_map = {}
    products_map = {}

    with ThreadPoolExecutor(max_workers=8) as executor:
        f_orders = [executor.submit(_fetch_order_batch, b) for b in order_batches]
        f_prods = [executor.submit(_fetch_product_batch, b) for b in product_batches]

        for fut in f_orders:
            for o in fut.result():
                orders_map[o['id']] = o

        for fut in f_prods:
            for p in fut.result():
                products_map[p['id']] = p

    # Fetch packaging barcodes for the unique products to enrich reports
    all_pkg_ids = []
    for p in products_map.values():
        if p.get('packaging_ids'):
            all_pkg_ids.extend(p['packaging_ids'])

    pkg_barcodes_by_prod = {}
    if all_pkg_ids:
        pkg_batches = [all_pkg_ids[i:i + 3000] for i in range(0, len(all_pkg_ids), 3000)]
        for pb in pkg_batches:
            pkgs = safe_execute_kw(models, db, uid, password, 'product.packaging', 'read',
                                   [pb], {'fields': ['product_id', 'barcode']})
            for pkg in pkgs:
                if pkg.get('product_id') and pkg.get('barcode'):
                    pid = pkg['product_id'][0]
                    pkg_barcodes_by_prod.setdefault(pid, []).append(pkg['barcode'])

    notify(70, "جاري معالجة التواريخ والتوقيت المحلي وحساب الإحصائيات المالية...")
    chk()

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 4 — Vectorized In-Memory Row Construction & Analytics Rollup
    # ═════════════════════════════════════════════════════════════════════════
    report_rows = []
    product_rollup = {}
    showroom_rollup = {}
    unique_invoices_set = set()

    for line in all_lines:
        if not line.get('order_id') or not line.get('product_id'):
            continue

        oid = line['order_id'][0]
        pid = line['product_id'][0]
        order = orders_map.get(oid, {})
        product = products_map.get(pid, {})

        # Invoice number
        inv_num = ''
        if order.get('account_move') and order['account_move']:
            inv_num = str(order['account_move'][1]).split(' ')[0]
        if not inv_num:
            inv_num = order.get('pos_reference') or order.get('name') or ''
        if inv_num:
            unique_invoices_set.add(inv_num)

        # Date & Time (UTC+3)
        date_raw = order.get('date_order') or ''
        date_str = ''
        time_str = ''
        sort_key_dt = datetime.min
        if date_raw:
            try:
                dt_utc = datetime.strptime(date_raw, "%Y-%m-%d %H:%M:%S")
                dt_ksa = dt_utc + timedelta(hours=3)
                date_str = dt_ksa.strftime("%Y-%m-%d")
                time_str = dt_ksa.strftime("%H:%M:%S")
                sort_key_dt = dt_ksa
            except Exception:
                date_str = date_raw[:10]
                time_str = date_raw[11:19]

        code = str(product.get('default_code') or '')
        barcode = str(product.get('barcode') or '')
        name_en = str(product.get('name') or '')
        name_ar = str(product.get('product_name_arabic') or name_en)
        pkg_bcs = ", ".join(pkg_barcodes_by_prod.get(pid, []))

        qty = float(line.get('qty') or 0.0)
        price_unit = float(line.get('price_unit') or 0.0)
        discount_val = float(line.get('discount') or 0.0)
        subtotal_incl = float(line.get('price_subtotal_incl') or 0.0)

        # Compensation claim amount (amount discounted)
        compensation = round((qty * price_unit) - subtotal_incl, 2)
        if not include_all_sales and compensation < 0 and qty > 0:
            compensation = 0.0

        sh_name = 'معرض غير محدد'
        cfg_tuple = order.get('config_id')
        if cfg_tuple and isinstance(cfg_tuple, (list, tuple)):
            sh_name = config_to_sh_name.get(cfg_tuple[0], cfg_tuple[1])

        row_dict = {
            'sort_key': sort_key_dt,
            'invoice_no': inv_num,
            'showroom': sh_name,
            'date': date_str,
            'time': time_str,
            'product_id': pid,
            'default_code': code,
            'barcode': barcode,
            'packaging_barcodes': pkg_bcs,
            'product_name': name_en,
            'product_name_ar': name_ar,
            'qty': qty,
            'price_unit': price_unit,
            'discount': discount_val / 100.0,
            'subtotal_incl': subtotal_incl,
            'compensation': compensation,
        }
        report_rows.append(row_dict)

        # ── Product Rollup Aggregation ──
        prod_key = (code, barcode)
        if prod_key not in product_rollup:
            product_rollup[prod_key] = {
                'code': code,
                'barcode': barcode,
                'pkg_barcodes': pkg_bcs,
                'name_ar': name_ar,
                'name_en': name_en,
                'qty': 0.0,
                'sales': 0.0,
                'compensation': 0.0,
                'sum_unit_prices': 0.0,
                'line_count': 0,
            }
        pr = product_rollup[prod_key]
        pr['qty'] += qty
        pr['sales'] += subtotal_incl
        pr['compensation'] += compensation
        pr['sum_unit_prices'] += price_unit
        pr['line_count'] += 1

        # ── Showroom Rollup Aggregation ──
        if sh_name not in showroom_rollup:
            showroom_rollup[sh_name] = {
                'name': sh_name,
                'transactions': 0,
                'qty': 0.0,
                'sales': 0.0,
                'compensation': 0.0,
            }
        sr = showroom_rollup[sh_name]
        sr['transactions'] += 1
        sr['qty'] += qty
        sr['sales'] += subtotal_incl
        sr['compensation'] += compensation

    # Sort detailed transactions descending by date & time
    report_rows.sort(key=lambda x: x['sort_key'], reverse=True)

    # Key Totals
    total_sales_amount = sum(r['subtotal_incl'] for r in report_rows)
    total_compensation_amount = sum(r['compensation'] for r in report_rows)
    total_qty_count = sum(r['qty'] for r in report_rows)
    distinct_invoices_count = len(unique_invoices_set)
    overall_avg_discount = (total_compensation_amount / (total_sales_amount + total_compensation_amount) * 100.0) if (total_sales_amount + total_compensation_amount) > 0 else 0.0

    # Top 5 Claimed Products
    sorted_prods = sorted(product_rollup.values(), key=lambda p: p['compensation'], reverse=True)
    top_5_products = sorted_prods[:5]
    top_product_name = sorted_prods[0]['name_ar'] if sorted_prods else "-"
    top_product_comp = sorted_prods[0]['compensation'] if sorted_prods else 0.0

    notify(80, "جاري بناء وتنسيق أوراق العمل ولوحة المؤشرات التفاعلية...")
    chk()

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 5 — Advanced Multi-Tab Excel Generation (BI Executive Edition)
    # ═════════════════════════════════════════════════════════════════════════
    company_info = load_company_profile()
    wb = openpyxl.Workbook()

    # Palette tokens
    C_NAVY_DARK   = "1B365D"   # #1B365D
    C_BLUE_HDR    = "1E40AF"   # #1E40AF
    C_GOLD        = "D4A017"   # #D4A017
    C_GOLD_LIGHT  = "FEF3C7"   # #FEF3C7
    C_SLATE_BG    = "F8FAFC"   # #F8FAFC
    C_CARD_BLUE   = "EFF6FF"   # #EFF6FF
    C_CARD_GREEN  = "F0FDF4"   # #F0FDF4
    C_CARD_AMBER  = "FFFBEB"   # #FFFBEB
    C_CARD_PURPLE = "F5F3FF"   # #F5F3FF
    C_CARD_SKY    = "F0F9FF"   # #F0F9FF
    C_REFUND_BG   = "FEE2E2"   # Soft Pink for Returns
    C_REFUND_FG   = "991B1B"   # Dark Red Text
    C_HIDC_BG     = "FEF9C3"   # Soft Yellow for High Discount
    C_HIDC_FG     = "854D0E"   # Dark Amber Text
    C_BORDER_GRAY = "CBD5E1"   # #CBD5E1

    font_base      = Font(name="Segoe UI", size=10)
    font_bold      = Font(name="Segoe UI", size=10, bold=True)
    font_title_lg  = Font(name="Segoe UI", size=15, bold=True, color="FFFFFF")
    font_sub_info  = Font(name="Segoe UI", size=9, color="334155")
    font_comp_val  = Font(name="Segoe UI", size=10, bold=True, color="991B1B")
    font_totals    = Font(name="Segoe UI", size=10, bold=True, color="0F172A")
    font_hdr       = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    font_refund    = Font(name="Segoe UI", size=10, color=C_REFUND_FG, bold=True)
    font_hidc      = Font(name="Segoe UI", size=10, color=C_HIDC_FG, bold=True)

    fill_navy      = PatternFill(start_color=C_NAVY_DARK, end_color=C_NAVY_DARK, fill_type="solid")
    fill_blue_hdr  = PatternFill(start_color=C_BLUE_HDR, end_color=C_BLUE_HDR, fill_type="solid")
    fill_gold_tot  = PatternFill(start_color=C_GOLD_LIGHT, end_color=C_GOLD_LIGHT, fill_type="solid")
    fill_zebra     = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    fill_refund    = PatternFill(start_color=C_REFUND_BG, end_color=C_REFUND_BG, fill_type="solid")
    fill_hidc      = PatternFill(start_color=C_HIDC_BG, end_color=C_HIDC_BG, fill_type="solid")

    s_border_thin  = Side(style='thin', color=C_BORDER_GRAY)
    border_all     = Border(left=s_border_thin, right=s_border_thin, top=s_border_thin, bottom=s_border_thin)
    s_tot_top      = Side(style='thin', color="475569")
    s_tot_bot      = Side(style='double', color="0F172A")
    border_totals  = Border(left=s_border_thin, right=s_border_thin, top=s_tot_top, bottom=s_tot_bot)

    align_ctr      = Alignment(horizontal="center", vertical="center")
    align_rt       = Alignment(horizontal="right",  vertical="center")
    align_lt       = Alignment(horizontal="left",   vertical="center")
    align_hdr      = Alignment(horizontal="center", vertical="center", wrap_text=True)

    export_time_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Helper: insert company logo
    def _try_insert_logo(ws, cell_coord="A2", max_w=140, max_h=55):
        logo_file = company_info.get("logo_path")
        if logo_file and os.path.exists(logo_file):
            try:
                img = OpenpyxlImage(logo_file)
                # Keep aspect ratio
                orig_w, orig_h = img.width, img.height
                ratio = min(max_w / orig_w, max_h / orig_h)
                img.width = int(orig_w * ratio)
                img.height = int(orig_h * ratio)
                ws.add_image(img, cell_coord)
            except Exception as e:
                print(f"Image insert warning: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # SHEET 1: 📊 لوحة المؤشرات التنفيذية (Dashboard)
    # ─────────────────────────────────────────────────────────────────────────
    if include_pro_sheets:
        ws_dash = wb.active
        ws_dash.title = "📊 لوحة المؤشرات"
        ws_dash.views.sheetView[0].rightToLeft = True
        ws_dash.sheet_properties.tabColor = "1E40AF"

        # Banner Header (Rows 2-4)
        ws_dash.merge_cells("A2:L2")
        c_title = ws_dash.cell(row=2, column=1, value=f"📊 لوحة مؤشرات مبيعات وخصومات نقاط البيع — {company_info.get('name_ar')}")
        c_title.font = font_title_lg
        c_title.fill = fill_navy
        c_title.alignment = align_ctr
        ws_dash.row_dimensions[2].height = 36

        ws_dash.merge_cells("A3:L3")
        c_sub = ws_dash.cell(row=3, column=1, value=f"الفترة: {period_title}   |   المعارض: {showroom_label}   |   الرقم الضريبي: {company_info.get('tax_id')}   |   تاريخ الإصدار: {export_time_str}")
        c_sub.font = Font(name="Segoe UI", size=9, bold=True, color="475569")
        c_sub.fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
        c_sub.alignment = align_ctr
        ws_dash.row_dimensions[3].height = 24

        _try_insert_logo(ws_dash, "A2")

        # ── Top 5 KPI Cards (Rows 5 to 7) ──
        kpi_cards = [
            ("💰 إجمالي المبيعات (شامل الضريبة)", f"{total_sales_amount:,.2f} ر.س", "مبيعات نقدية وآجلة مسددة", C_CARD_BLUE, "2563EB"),
            ("🎁 إجمالي التعويض المطلوب", f"{total_compensation_amount:,.2f} ر.س", "مبالغ الخصومات المطالب بها", C_CARD_GREEN, "16A34A"),
            ("📊 متوسط نسبة الخصم", f"{overall_avg_discount:.1f}%", "معدل الخصم الإجمالي للفترة", C_CARD_AMBER, "D97706"),
            ("🧾 إجمالي حركات البيع", f"{len(report_rows):,} حركة", "أسطر فواتير نقاط البيع", C_CARD_PURPLE, "7C3AED"),
            ("🔢 عدد الفواتير الفريدة", f"{distinct_invoices_count:,} فاتورة", "فواتير صادرة ومسددة", C_CARD_SKY, "0284C7"),
        ]

        card_col_ranges = [("A", "B"), ("C", "D"), ("F", "G"), ("I", "J"), ("K", "L")]
        # Note: adjust ranges nicely across cols A through L
        card_cols = [(1, 2), (3, 4), (6, 7), (8, 9), (11, 12)]

        for idx, (title_k, val_k, note_k, bg_k, fg_k) in enumerate(kpi_cards):
            c_start, c_end = card_cols[idx]
            fill_k = PatternFill(start_color=bg_k, end_color=bg_k, fill_type="solid")
            s_box = Side(style='medium', color=fg_k)
            border_k = Border(left=s_box, right=s_box, top=s_box, bottom=s_box)

            ws_dash.merge_cells(start_row=5, start_column=c_start, end_row=5, end_column=c_end)
            ws_dash.merge_cells(start_row=6, start_column=c_start, end_row=6, end_column=c_end)
            ws_dash.merge_cells(start_row=7, start_column=c_start, end_row=7, end_column=c_end)

            c_t = ws_dash.cell(row=5, column=c_start, value=title_k)
            c_t.font = Font(name="Segoe UI", size=9, bold=True, color="334155")
            c_t.fill = fill_k
            c_t.alignment = align_ctr

            c_v = ws_dash.cell(row=6, column=c_start, value=val_k)
            c_v.font = Font(name="Segoe UI", size=13, bold=True, color=fg_k)
            c_v.fill = fill_k
            c_v.alignment = align_ctr

            c_n = ws_dash.cell(row=7, column=c_start, value=note_k)
            c_n.font = Font(name="Segoe UI", size=8, color="64748B")
            c_n.fill = fill_k
            c_n.alignment = align_ctr

            for r_i in range(5, 8):
                for c_i in range(c_start, c_end + 1):
                    ws_dash.cell(row=r_i, column=c_i).border = border_k

        ws_dash.row_dimensions[5].height = 20
        ws_dash.row_dimensions[6].height = 26
        ws_dash.row_dimensions[7].height = 18
        ws_dash.row_dimensions[8].height = 12

        # ── Section 2: Top 5 Claimed Products & Showroom Breakdown ──
        # Left Side Table: Top 5 Products (Cols A to E)
        ws_dash.merge_cells("A10:E10")
        c_sec1 = ws_dash.cell(row=10, column=1, value="🏆 أعلى 5 أصناف طلباً للتعويض من الموردين")
        c_sec1.font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        c_sec1.fill = fill_blue_hdr
        c_sec1.alignment = align_rt

        top5_hdrs = [("م", 5), ("كود الصنف", 14), ("اسم الصنف بالعربي", 28), ("الكمية المباعة", 14), ("التعويض المطلوب (ر.س)", 18)]
        for col_i, (h_txt, w) in enumerate(top5_hdrs, 1):
            cell = ws_dash.cell(row=11, column=col_i, value=h_txt)
            cell.font = font_bold
            cell.fill = PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")
            cell.alignment = align_ctr
            cell.border = border_all
            ws_dash.column_dimensions[get_column_letter(col_i)].width = w

        for idx, tp in enumerate(top_5_products, 1):
            r_idx = 11 + idx
            ws_dash.cell(row=r_idx, column=1, value=idx).alignment = align_ctr
            ws_dash.cell(row=r_idx, column=2, value=tp['code']).alignment = align_ctr
            ws_dash.cell(row=r_idx, column=3, value=tp['name_ar']).alignment = align_rt
            c_q = ws_dash.cell(row=r_idx, column=4, value=tp['qty'])
            c_q.alignment = align_ctr
            c_q.number_format = "#,##0.00"
            c_c = ws_dash.cell(row=r_idx, column=5, value=tp['compensation'])
            c_c.alignment = align_rt
            c_c.font = font_comp_val
            c_c.number_format = "#,##0.00"
            for c_i in range(1, 6):
                ws_dash.cell(row=r_idx, column=c_i).border = border_all
            ws_dash.row_dimensions[r_idx].height = 20

        # Right Side Table: Showroom Breakdown (Cols G to L)
        ws_dash.merge_cells("G10:L10")
        c_sec2 = ws_dash.cell(row=10, column=7, value="🏢 توزيع المبيعات والخصومات حسب المعارض والفروع")
        c_sec2.font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        c_sec2.fill = fill_navy
        c_sec2.alignment = align_rt

        sh_hdrs = [("م", 5), ("المعرض / الفرع", 22), ("عدد الحركات", 12), ("الكميات المباعة", 14), ("إجمالي المبيعات", 18), ("التعويض المطلوب", 18)]
        for col_i, (h_txt, w) in enumerate(sh_hdrs, 7):
            cell = ws_dash.cell(row=11, column=col_i, value=h_txt)
            cell.font = font_bold
            cell.fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
            cell.alignment = align_ctr
            cell.border = border_all
            ws_dash.column_dimensions[get_column_letter(col_i)].width = w

        sorted_showrooms = sorted(showroom_rollup.values(), key=lambda s: s['compensation'], reverse=True)
        sh_start_r = 12
        for idx, sh in enumerate(sorted_showrooms, 1):
            r_idx = 11 + idx
            ws_dash.cell(row=r_idx, column=7, value=idx).alignment = align_ctr
            ws_dash.cell(row=r_idx, column=8, value=sh['name']).alignment = align_rt
            c_cnt = ws_dash.cell(row=r_idx, column=9, value=sh['transactions'])
            c_cnt.alignment = align_ctr
            c_cnt.number_format = "#,##0"
            c_q = ws_dash.cell(row=r_idx, column=10, value=sh['qty'])
            c_q.alignment = align_ctr
            c_q.number_format = "#,##0.00"
            c_s = ws_dash.cell(row=r_idx, column=11, value=sh['sales'])
            c_s.alignment = align_rt
            c_s.number_format = "#,##0.00"
            c_c = ws_dash.cell(row=r_idx, column=12, value=sh['compensation'])
            c_c.alignment = align_rt
            c_c.font = font_comp_val
            c_c.number_format = "#,##0.00"
            for c_i in range(7, 13):
                ws_dash.cell(row=r_idx, column=c_i).border = border_all
            ws_dash.row_dimensions[r_idx].height = 20

        sh_end_r = 11 + len(sorted_showrooms)
        # Showrooms Totals Row
        tot_sh_r = sh_end_r + 1
        ws_dash.merge_cells(f"G{tot_sh_r}:H{tot_sh_r}")
        c_lbl = ws_dash.cell(row=tot_sh_r, column=7, value="▶ الإجمالي العام")
        c_lbl.font = font_totals
        c_lbl.fill = fill_gold_tot
        c_lbl.alignment = align_ctr
        for c_i in range(7, 9):
            ws_dash.cell(row=tot_sh_r, column=c_i).border = border_totals
            ws_dash.cell(row=tot_sh_r, column=c_i).fill = fill_gold_tot

        for c_idx, col_let in [(9, 'I'), (10, 'J'), (11, 'K'), (12, 'L')]:
            c_tot = ws_dash.cell(row=tot_sh_r, column=c_idx, value=f"=SUBTOTAL(9, {col_let}{sh_start_r}:{col_let}{sh_end_r})")
            c_tot.font = font_totals
            c_tot.fill = fill_gold_tot
            c_tot.border = border_totals
            c_tot.number_format = "#,##0.00" if c_idx > 9 else "#,##0"
            c_tot.alignment = align_rt if c_idx >= 11 else align_ctr
        ws_dash.row_dimensions[tot_sh_r].height = 22

    # ─────────────────────────────────────────────────────────────────────────
    # SHEET 2: 📄 كشف مطالبة معتمد (Official Print/PDF Ready Claim Form)
    # ─────────────────────────────────────────────────────────────────────────
    if include_pro_sheets:
        ws_claim = wb.create_sheet(title="📄 كشف مطالبة معتمد")
        ws_claim.views.sheetView[0].rightToLeft = True
        ws_claim.sheet_properties.tabColor = "059669"

        # Formal Company Letterhead Banner (Rows 2 to 4)
        ws_claim.merge_cells("A2:J2")
        c_head = ws_claim.cell(row=2, column=1, value=f"{company_info.get('name_ar')} — كشف مطالبة تعويض عن خصومات وعروض ترويجية")
        c_head.font = font_title_lg
        c_head.fill = fill_navy
        c_head.alignment = align_ctr
        ws_claim.row_dimensions[2].height = 34

        ws_claim.merge_cells("A3:J3")
        c_info2 = ws_claim.cell(row=3, column=1, value=f"الفترة: {period_title}   |   المعارض: {showroom_label}   |   السجل التجاري: {company_info.get('cr_number')}   |   الرقم الضريبي: {company_info.get('tax_id')}   |   تاريخ الإصدار: {export_time_str}")
        c_info2.font = Font(name="Segoe UI", size=9, bold=True, color="334155")
        c_info2.fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
        c_info2.alignment = align_ctr
        ws_claim.row_dimensions[3].height = 22

        _try_insert_logo(ws_claim, "A2")

        # Table Headers (Row 5)
        claim_hdrs = [
            ("م", 6, "@", align_ctr),
            ("كود الصنف", 16, "@", align_ctr),
            ("باركود الصنف", 18, "@", align_ctr),
            ("اسم الصنف بالعربي", 30, "@", align_rt),
            ("اسم الصنف بالإنجليزي", 30, "@", align_lt),
            ("الكمية المباعة", 14, "#,##0.00", align_ctr),
            ("متوسط سعر البيع", 16, "#,##0.00", align_rt),
            ("إجمالي المبيعات (شامل الضريبة)", 22, "#,##0.00", align_rt),
            ("متوسط الخصم", 14, "0.0%", align_ctr),
            ("إجمالي التعويض المطلوب من المورد", 26, "#,##0.00", align_rt),
        ]

        for c_idx, (h_txt, w, _, a) in enumerate(claim_hdrs, 1):
            cell = ws_claim.cell(row=5, column=c_idx, value=h_txt)
            cell.font = font_hdr
            cell.fill = fill_blue_hdr
            cell.alignment = align_hdr
            cell.border = border_all
            ws_claim.column_dimensions[get_column_letter(c_idx)].width = w
        ws_claim.row_dimensions[5].height = 28

        # Stream aggregated products
        claim_start_r = 6
        for idx, p_item in enumerate(sorted_prods, 1):
            r_idx = claim_start_r + idx - 1
            avg_price = (p_item['sum_unit_prices'] / p_item['line_count']) if p_item['line_count'] > 0 else 0.0
            avg_disc = (p_item['compensation'] / (p_item['sales'] + p_item['compensation'])) if (p_item['sales'] + p_item['compensation']) > 0 else 0.0

            ws_claim.cell(row=r_idx, column=1, value=idx).alignment = align_ctr
            ws_claim.cell(row=r_idx, column=2, value=p_item['code']).alignment = align_ctr
            ws_claim.cell(row=r_idx, column=3, value=p_item['barcode']).alignment = align_ctr
            ws_claim.cell(row=r_idx, column=4, value=p_item['name_ar']).alignment = align_rt
            ws_claim.cell(row=r_idx, column=5, value=p_item['name_en']).alignment = align_lt

            c_q = ws_claim.cell(row=r_idx, column=6, value=p_item['qty'])
            c_q.alignment = align_ctr
            c_q.number_format = "#,##0.00"

            c_p = ws_claim.cell(row=r_idx, column=7, value=avg_price)
            c_p.alignment = align_rt
            c_p.number_format = "#,##0.00"

            c_s = ws_claim.cell(row=r_idx, column=8, value=p_item['sales'])
            c_s.alignment = align_rt
            c_s.number_format = "#,##0.00"

            c_d = ws_claim.cell(row=r_idx, column=9, value=avg_disc)
            c_d.alignment = align_ctr
            c_d.number_format = "0.0%"

            c_c = ws_claim.cell(row=r_idx, column=10, value=p_item['compensation'])
            c_c.alignment = align_rt
            c_c.font = font_comp_val
            c_c.number_format = "#,##0.00"

            row_fill_c = fill_zebra if (idx % 2 == 1) else None
            for c_i in range(1, 11):
                cell_item = ws_claim.cell(row=r_idx, column=c_i)
                cell_item.border = border_all
                if row_fill_c:
                    cell_item.fill = row_fill_c
            ws_claim.row_dimensions[r_idx].height = 20

        claim_end_r = claim_start_r + len(sorted_prods) - 1

        # Claim Totals Row
        claim_tot_r = claim_end_r + 1
        ws_claim.merge_cells(f"A{claim_tot_r}:E{claim_tot_r}")
        c_tot_lbl = ws_claim.cell(row=claim_tot_r, column=1, value="▶ الإجمالي العام للمطالبة")
        c_tot_lbl.font = font_totals
        c_tot_lbl.fill = fill_gold_tot
        c_tot_lbl.alignment = align_ctr
        for c_i in range(1, 6):
            ws_claim.cell(row=claim_tot_r, column=c_i).border = border_totals
            ws_claim.cell(row=claim_tot_r, column=c_i).fill = fill_gold_tot

        # Qty Sum
        c_q_tot = ws_claim.cell(row=claim_tot_r, column=6, value=f"=SUBTOTAL(9, F{claim_start_r}:F{claim_end_r})")
        c_q_tot.font = font_totals
        c_q_tot.fill = fill_gold_tot
        c_q_tot.alignment = align_ctr
        c_q_tot.number_format = "#,##0.00"
        c_q_tot.border = border_totals

        # Dash for Unit Price
        c_p_tot = ws_claim.cell(row=claim_tot_r, column=7, value="-")
        c_p_tot.font = font_totals
        c_p_tot.fill = fill_gold_tot
        c_p_tot.alignment = align_ctr
        c_p_tot.border = border_totals

        # Sales Sum
        c_s_tot = ws_claim.cell(row=claim_tot_r, column=8, value=f"=SUBTOTAL(9, H{claim_start_r}:H{claim_end_r})")
        c_s_tot.font = font_totals
        c_s_tot.fill = fill_gold_tot
        c_s_tot.alignment = align_rt
        c_s_tot.number_format = "#,##0.00"
        c_s_tot.border = border_totals

        # Dash for avg discount
        c_d_tot = ws_claim.cell(row=claim_tot_r, column=9, value="-")
        c_d_tot.font = font_totals
        c_d_tot.fill = fill_gold_tot
        c_d_tot.alignment = align_ctr
        c_d_tot.border = border_totals

        # Compensation Sum
        c_c_tot = ws_claim.cell(row=claim_tot_r, column=10, value=f"=SUBTOTAL(9, J{claim_start_r}:J{claim_end_r})")
        c_c_tot.font = font_totals
        c_c_tot.fill = fill_gold_tot
        c_c_tot.alignment = align_rt
        c_c_tot.number_format = "#,##0.00"
        c_c_tot.border = border_totals
        ws_claim.row_dimensions[claim_tot_r].height = 24

        # ── Formal Signatures & Approvals Block ──
        sig_r_start = claim_tot_r + 3
        sig_boxes = [
            ("إعداد وتجهيز التقرير", "إدارة المشتريات والتسويق", 1, 3),
            ("مراجعة ومطابقة الفواتير", "قسم الحسابات والمالية", 4, 6),
            ("اعتماد وموافقة الصرف", "الإدارة المالية / المدير العام", 8, 10),
        ]

        for s_title, s_dept, sc, ec in sig_boxes:
            ws_claim.merge_cells(start_row=sig_r_start, start_column=sc, end_row=sig_r_start, end_column=ec)
            c_st = ws_claim.cell(row=sig_r_start, column=sc, value=f"📌 {s_title} — ({s_dept})")
            c_st.font = Font(name="Segoe UI", size=10, bold=True, color="1E3A8A")
            c_st.alignment = align_ctr
            c_st.fill = PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")

            # Signature lines
            lines_meta = [
                ("الاسم:", sig_r_start + 1),
                ("التوقيع:", sig_r_start + 2),
                ("التاريخ:       /      / 202 م", sig_r_start + 3),
            ]
            for l_lbl, lr in lines_meta:
                ws_claim.merge_cells(start_row=lr, start_column=sc, end_row=lr, end_column=ec)
                c_l = ws_claim.cell(row=lr, column=sc, value=f"  {l_lbl}")
                c_l.font = font_base
                c_l.alignment = align_rt

            # Outer border for signature box
            s_box_sig = Side(style='thin', color="3B82F6")
            for r_i in range(sig_r_start, sig_r_start + 4):
                for c_i in range(sc, ec + 1):
                    t_b = s_box_sig if r_i == sig_r_start else None
                    b_b = s_box_sig if r_i == sig_r_start + 3 else None
                    l_b = s_box_sig if c_i == sc else None
                    r_b = s_box_sig if c_i == ec else None
                    ws_claim.cell(row=r_i, column=c_i).border = Border(top=t_b, bottom=b_b, left=l_b, right=r_b)

        ws_claim.freeze_panes = "A6"
        ws_claim.auto_filter.ref = f"A5:J{claim_end_r}"

        # Page setup for printing
        ws_claim.page_setup.orientation = ws_claim.ORIENTATION_LANDSCAPE
        ws_claim.page_setup.paperSize = ws_claim.PAPERSIZE_A4
        ws_claim.sheet_properties.pageSetUpPr.fitToPage = True
        ws_claim.page_setup.fitToWidth = 1
        ws_claim.page_setup.fitToHeight = 0

    # ─────────────────────────────────────────────────────────────────────────
    # SHEET 3: 📦 ملخص الأصناف التجميعي (Product Rollup)
    # ─────────────────────────────────────────────────────────────────────────
    if include_pro_sheets:
        ws_roll = wb.create_sheet(title="📦 ملخص الأصناف")
        ws_roll.views.sheetView[0].rightToLeft = True
        ws_roll.sheet_properties.tabColor = "D97706"

        ws_roll.merge_cells("A2:I2")
        c_rt = ws_roll.cell(row=2, column=1, value=f"📦 ملخص مبيعات وخصومات الأصناف التجميعي — {period_title}")
        c_rt.font = font_title_lg
        c_rt.fill = PatternFill(start_color="92400E", end_color="92400E", fill_type="solid")
        c_rt.alignment = align_ctr
        ws_roll.row_dimensions[2].height = 32

        roll_hdrs = [
            ("م", 6),
            ("كود الصنف", 16),
            ("باركود الصنف", 18),
            ("باركودات العبوات والكراتين", 24),
            ("اسم الصنف بالعربي", 28),
            ("اسم الصنف بالإنجليزي", 28),
            ("إجمالي الكمية المباعة", 16),
            ("إجمالي المبيعات شامل الضريبة", 22),
            ("إجمالي التعويض المطلوب", 22),
        ]

        for c_idx, (h_txt, w) in enumerate(roll_hdrs, 1):
            cell = ws_roll.cell(row=4, column=c_idx, value=h_txt)
            cell.font = font_hdr
            cell.fill = PatternFill(start_color="B45309", end_color="B45309", fill_type="solid")
            cell.alignment = align_hdr
            cell.border = border_all
            ws_roll.column_dimensions[get_column_letter(c_idx)].width = w
        ws_roll.row_dimensions[4].height = 26

        r_start = 5
        for idx, p_item in enumerate(sorted_prods, 1):
            r_idx = r_start + idx - 1
            ws_roll.cell(row=r_idx, column=1, value=idx).alignment = align_ctr
            ws_roll.cell(row=r_idx, column=2, value=p_item['code']).alignment = align_ctr
            ws_roll.cell(row=r_idx, column=3, value=p_item['barcode']).alignment = align_ctr
            ws_roll.cell(row=r_idx, column=4, value=p_item['pkg_barcodes']).alignment = align_ctr
            ws_roll.cell(row=r_idx, column=5, value=p_item['name_ar']).alignment = align_rt
            ws_roll.cell(row=r_idx, column=6, value=p_item['name_en']).alignment = align_lt

            c_q = ws_roll.cell(row=r_idx, column=7, value=p_item['qty'])
            c_q.alignment = align_ctr
            c_q.number_format = "#,##0.00"

            c_s = ws_roll.cell(row=r_idx, column=8, value=p_item['sales'])
            c_s.alignment = align_rt
            c_s.number_format = "#,##0.00"

            c_c = ws_roll.cell(row=r_idx, column=9, value=p_item['compensation'])
            c_c.alignment = align_rt
            c_c.font = font_comp_val
            c_c.number_format = "#,##0.00"

            row_fill_r = fill_zebra if (idx % 2 == 1) else None
            for c_i in range(1, 10):
                cell_item = ws_roll.cell(row=r_idx, column=c_i)
                cell_item.border = border_all
                if row_fill_r:
                    cell_item.fill = row_fill_r
            ws_roll.row_dimensions[r_idx].height = 20

        r_end = r_start + len(sorted_prods) - 1
        tot_r_roll = r_end + 1

        ws_roll.merge_cells(f"A{tot_r_roll}:F{tot_r_roll}")
        c_tot_r = ws_roll.cell(row=tot_r_roll, column=1, value="▶ الإجمالي العام للأصناف")
        c_tot_r.font = font_totals
        c_tot_r.fill = fill_gold_tot
        c_tot_r.alignment = align_ctr
        for c_i in range(1, 7):
            ws_roll.cell(row=tot_r_roll, column=c_i).border = border_totals
            ws_roll.cell(row=tot_r_roll, column=c_i).fill = fill_gold_tot

        # Qty Sum
        c_rq_tot = ws_roll.cell(row=tot_r_roll, column=7, value=f"=SUBTOTAL(9, G{r_start}:G{r_end})")
        c_rq_tot.font = font_totals
        c_rq_tot.fill = fill_gold_tot
        c_rq_tot.alignment = align_ctr
        c_rq_tot.number_format = "#,##0.00"
        c_rq_tot.border = border_totals

        # Sales Sum
        c_rs_tot = ws_roll.cell(row=tot_r_roll, column=8, value=f"=SUBTOTAL(9, H{r_start}:H{r_end})")
        c_rs_tot.font = font_totals
        c_rs_tot.fill = fill_gold_tot
        c_rs_tot.alignment = align_rt
        c_rs_tot.number_format = "#,##0.00"
        c_rs_tot.border = border_totals

        # Compensation Sum
        c_rc_tot = ws_roll.cell(row=tot_r_roll, column=9, value=f"=SUBTOTAL(9, I{r_start}:I{r_end})")
        c_rc_tot.font = font_totals
        c_rc_tot.fill = fill_gold_tot
        c_rc_tot.alignment = align_rt
        c_rc_tot.number_format = "#,##0.00"
        c_rc_tot.border = border_totals

        ws_roll.freeze_panes = "A5"
        ws_roll.auto_filter.ref = f"A4:I{r_end}"

    # ─────────────────────────────────────────────────────────────────────────
    # SHEET 4: 🧾 تفاصيل الحركات (Detailed POS Transactions Log)
    # ─────────────────────────────────────────────────────────────────────────
    if include_pro_sheets:
        ws_trans = wb.create_sheet(title="🧾 تفاصيل الحركات")
    else:
        ws_trans = wb.active
        ws_trans.title = "🧾 تفاصيل الحركات"

    ws_trans.views.sheetView[0].rightToLeft = True
    ws_trans.sheet_properties.tabColor = "475569"

    # Column configuration
    if include_showroom_col:
        headers = [
            ("رقم الفاتورة", 22, "@", align_ctr, font_base),
            ("المعرض / الفرع", 20, "@", align_ctr, font_base),
            ("تاريخ الفاتورة", 14, "yyyy-mm-dd", align_ctr, font_base),
            ("وقت الفاتورة", 12, "hh:mm:ss", align_ctr, font_base),
            ("رقم الصنف", 18, "@", align_ctr, font_bold),
            ("باركود الصنف", 18, "@", align_ctr, font_base),
            ("اسم الصنف الانجليزي", 36, "@", align_lt, font_base),
            ("الكمية المباعة في الفاتورة", 16, "#,##0.00", align_ctr, font_base),
            ("السعر قبل الخصم في الفاتورة شامل الضريبة", 22, "#,##0.00", align_rt, font_base),
            ("الخصم في الفاتورة", 14, "0.0%", align_ctr, font_base),
            ("الاجمالي بعد الخصم شامل الضريبة", 22, "#,##0.00", align_rt, font_base),
            ("التعويض المطلوب من المورد وهو عبارة عن المبلغ المخصوم", 26, "#,##0.00", align_rt, font_comp_val),
        ]
        col_qty_idx = 8
        col_subtot_idx = 11
        col_comp_idx = 12
    else:
        headers = [
            ("رقم الفاتورة", 22, "@", align_ctr, font_base),
            ("تاريخ الفاتورة", 14, "yyyy-mm-dd", align_ctr, font_base),
            ("وقت الفاتورة", 12, "hh:mm:ss", align_ctr, font_base),
            ("رقم الصنف", 18, "@", align_ctr, font_bold),
            ("باركود الصنف", 18, "@", align_ctr, font_base),
            ("اسم الصنف الانجليزي", 36, "@", align_lt, font_base),
            ("الكمية المباعة في الفاتورة", 16, "#,##0.00", align_ctr, font_base),
            ("السعر قبل الخصم في الفاتورة شامل الضريبة", 22, "#,##0.00", align_rt, font_base),
            ("الخصم في الفاتورة", 14, "0.0%", align_ctr, font_base),
            ("الاجمالي بعد الخصم شامل الضريبة", 22, "#,##0.00", align_rt, font_base),
            ("التعويض المطلوب من المورد وهو عبارة عن المبلغ المخصوم", 26, "#,##0.00", align_rt, font_comp_val),
        ]
        col_qty_idx = 7
        col_subtot_idx = 10
        col_comp_idx = 11

    num_cols = len(headers)
    last_col_letter = get_column_letter(num_cols)

    # Title Banner
    ws_trans.merge_cells(f"A2:{last_col_letter}2")
    report_title_mode = "مبيعات نقاط البيع (كافة الحركات)" if include_all_sales else "مبيعات وخصومات نقاط البيع (الحركات المخصومة)"
    c_title = ws_trans.cell(row=2, column=1, value=f"🧾 تقرير تفاصيل {report_title_mode} — {period_title}")
    c_title.font = font_title_lg
    c_title.fill = fill_navy
    c_title.alignment = align_ctr
    ws_trans.row_dimensions[2].height = 34

    # Subtitle
    ws_trans.merge_cells(f"A3:{last_col_letter}3")
    hrakat_lbl = "عدد الحركات" if include_all_sales else "عدد الحركات المخصومة"
    info_text = f"الفترة: {period_title}  |  المعارض: {showroom_label}  |  {hrakat_lbl}: {len(report_rows):,} حركة  |  تاريخ التصدير: {export_time_str}"
    c_info = ws_trans.cell(row=3, column=1, value=info_text)
    c_info.font = Font(name="Segoe UI", size=9, bold=True, color="334155")
    c_info.fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    c_info.alignment = align_ctr
    ws_trans.row_dimensions[3].height = 22

    # Headers (Row 5)
    for col_idx, (hdr_text, col_w, _, _, _) in enumerate(headers, 1):
        cell = ws_trans.cell(row=5, column=col_idx, value=hdr_text)
        cell.font = font_hdr
        cell.fill = fill_blue_hdr
        cell.alignment = align_hdr
        cell.border = border_all
        ws_trans.column_dimensions[get_column_letter(col_idx)].width = col_w
    ws_trans.row_dimensions[5].height = 30

    # Stream Transactions
    start_trans_row = 6
    for idx, r in enumerate(report_rows):
        if include_showroom_col:
            row_vals = [
                r['invoice_no'],
                r['showroom'],
                r['date'],
                r['time'],
                r['default_code'],
                r['barcode'],
                r['product_name'],
                r['qty'],
                r['price_unit'],
                r['discount'],
                r['subtotal_incl'],
                r['compensation'],
            ]
        else:
            row_vals = [
                r['invoice_no'],
                r['date'],
                r['time'],
                r['default_code'],
                r['barcode'],
                r['product_name'],
                r['qty'],
                r['price_unit'],
                r['discount'],
                r['subtotal_incl'],
                r['compensation'],
            ]
        ws_trans.append(row_vals)

    end_trans_row = start_trans_row + len(report_rows) - 1

    # Formatting in batch & Smart Conditional Highlighting
    for row_idx in range(start_trans_row, end_trans_row + 1):
        r_item = report_rows[row_idx - start_trans_row]
        is_refund = (r_item['qty'] < 0 or r_item['compensation'] < 0)
        is_high_discount = (r_item['discount'] >= 0.30 and not is_refund)

        row_fill = None
        if is_refund:
            row_fill = fill_refund
        elif is_high_discount:
            row_fill = fill_hidc
        elif row_idx % 2 == 1:
            row_fill = fill_zebra

        ws_trans.row_dimensions[row_idx].height = 20

        for col_idx, (_, _, num_fmt, alignment, c_font) in enumerate(headers, 1):
            cell = ws_trans.cell(row=row_idx, column=col_idx)
            if is_refund:
                cell.font = font_refund
            elif is_high_discount and col_idx == (col_subtot_idx - 1): # discount col
                cell.font = font_hidc
            else:
                cell.font = c_font

            cell.alignment = alignment
            cell.number_format = num_fmt
            cell.border = border_all
            if row_fill:
                cell.fill = row_fill

    # Data Bars on Compensation column
    col_comp_letter = get_column_letter(col_comp_idx)
    rule_databar = DataBarRule(start_type='num', start_value=0, end_type='max', color="60A5FA", showValue="None")
    ws_trans.conditional_formatting.add(f"{col_comp_letter}{start_trans_row}:{col_comp_letter}{end_trans_row}", rule_databar)

    # Dynamic Totals Row
    tot_row = end_trans_row + 1
    ws_trans.row_dimensions[tot_row].height = 24

    col_qty_letter = get_column_letter(col_qty_idx)
    col_subtot_letter = get_column_letter(col_subtot_idx)

    for c_i in range(1, col_qty_idx):
        c = ws_trans.cell(row=tot_row, column=c_i)
        c.fill = fill_gold_tot
        c.border = border_totals
        c.font = font_totals
        if c_i == 1:
            c.value = "▶ الإجمالي العام"
            c.alignment = align_ctr

    # Sum for Qty (Dynamic)
    c_qty_tot = ws_trans.cell(row=tot_row, column=col_qty_idx, value=f"=SUBTOTAL(9, {col_qty_letter}{start_trans_row}:{col_qty_letter}{end_trans_row})")
    c_qty_tot.fill = fill_gold_tot
    c_qty_tot.font = font_totals
    c_qty_tot.alignment = align_ctr
    c_qty_tot.number_format = "#,##0.00"
    c_qty_tot.border = border_totals

    for c_i in range(col_qty_idx + 1, col_subtot_idx):
        c = ws_trans.cell(row=tot_row, column=c_i, value="-")
        c.fill = fill_gold_tot
        c.font = font_totals
        c.alignment = align_ctr
        c.border = border_totals

    # Sum for Subtotal (Dynamic)
    c_subtot = ws_trans.cell(row=tot_row, column=col_subtot_idx, value=f"=SUBTOTAL(9, {col_subtot_letter}{start_trans_row}:{col_subtot_letter}{end_trans_row})")
    c_subtot.fill = fill_gold_tot
    c_subtot.font = font_totals
    c_subtot.alignment = align_rt
    c_subtot.number_format = "#,##0.00"
    c_subtot.border = border_totals

    # Sum for Compensation (Dynamic)
    c_comp = ws_trans.cell(row=tot_row, column=col_comp_idx, value=f"=SUBTOTAL(9, {col_comp_letter}{start_trans_row}:{col_comp_letter}{end_trans_row})")
    c_comp.fill = fill_gold_tot
    c_comp.font = font_totals
    c_comp.alignment = align_rt
    c_comp.number_format = "#,##0.00"
    c_comp.border = border_totals

    ws_trans.freeze_panes = "A6"
    ws_trans.auto_filter.ref = f"A5:{last_col_letter}{end_trans_row}"

    # ─────────────────────────────────────────────────────────────────────────
    # OPTIONAL: Per-Showroom Separate Tabs
    # ─────────────────────────────────────────────────────────────────────────
    if include_showroom_sheets:
        notify(88, "جاري إنشاء أوراق عمل مستقلة لكل معرض...")
        chk()

        rows_by_sh = {}
        for r in report_rows:
            sh_k = r.get('showroom') or 'عام'
            rows_by_sh.setdefault(sh_k, []).append(r)

        for sh_name_tab, sh_rows in sorted(rows_by_sh.items()):
            # Excel sheet names max 31 chars and no invalid chars
            safe_sheet_name = sh_name_tab[:28].replace(':', '_').replace('/', '_').replace('\\', '_').replace('?', '_').replace('*', '_').replace('[', '_').replace(']', '_')
            tab_name = f"🏢 {safe_sheet_name}"[:31]

            ws_sh = wb.create_sheet(title=tab_name)
            ws_sh.views.sheetView[0].rightToLeft = True

            ws_sh.merge_cells(f"A2:{last_col_letter}2")
            c_sh_t = ws_sh.cell(row=2, column=1, value=f"🏢 مبيعات نقطة بيع: {sh_name_tab} — {period_title}")
            c_sh_t.font = font_title_lg
            c_sh_t.fill = fill_navy
            c_sh_t.alignment = align_ctr
            ws_sh.row_dimensions[2].height = 32

            for col_idx, (hdr_text, col_w, _, _, _) in enumerate(headers, 1):
                cell = ws_sh.cell(row=4, column=col_idx, value=hdr_text)
                cell.font = font_hdr
                cell.fill = fill_blue_hdr
                cell.alignment = align_hdr
                cell.border = border_all
                ws_sh.column_dimensions[get_column_letter(col_idx)].width = col_w
            ws_sh.row_dimensions[4].height = 28

            sh_start_row = 5
            for r in sh_rows:
                if include_showroom_col:
                    r_vals = [r['invoice_no'], r['showroom'], r['date'], r['time'], r['default_code'], r['barcode'], r['product_name'], r['qty'], r['price_unit'], r['discount'], r['subtotal_incl'], r['compensation']]
                else:
                    r_vals = [r['invoice_no'], r['date'], r['time'], r['default_code'], r['barcode'], r['product_name'], r['qty'], r['price_unit'], r['discount'], r['subtotal_incl'], r['compensation']]
                ws_sh.append(r_vals)

            sh_end_row = sh_start_row + len(sh_rows) - 1
            for r_i in range(sh_start_row, sh_end_row + 1):
                ws_sh.row_dimensions[r_i].height = 20
                for c_i, (_, _, num_fmt, alignment, c_font) in enumerate(headers, 1):
                    cell = ws_sh.cell(row=r_i, column=c_i)
                    cell.font = c_font
                    cell.alignment = alignment
                    cell.number_format = num_fmt
                    cell.border = border_all

            # Showroom dynamic totals
            sh_tot_row = sh_end_row + 1
            for c_i in range(1, col_qty_idx):
                c = ws_sh.cell(row=sh_tot_row, column=c_i)
                c.fill = fill_gold_tot
                c.border = border_totals
                c.font = font_totals
                if c_i == 1:
                    c.value = "▶ إجمالي المعرض"
                    c.alignment = align_ctr

            c_q_s = ws_sh.cell(row=sh_tot_row, column=col_qty_idx, value=f"=SUBTOTAL(9, {col_qty_letter}{sh_start_row}:{col_qty_letter}{sh_end_row})")
            c_q_s.fill = fill_gold_tot
            c_q_s.font = font_totals
            c_q_s.alignment = align_ctr
            c_q_s.number_format = "#,##0.00"
            c_q_s.border = border_totals

            for c_i in range(col_qty_idx + 1, col_subtot_idx):
                c = ws_sh.cell(row=sh_tot_row, column=c_i, value="-")
                c.fill = fill_gold_tot
                c.font = font_totals
                c.alignment = align_ctr
                c.border = border_totals

            c_s_s = ws_sh.cell(row=sh_tot_row, column=col_subtot_idx, value=f"=SUBTOTAL(9, {col_subtot_letter}{sh_start_row}:{col_subtot_letter}{sh_end_row})")
            c_s_s.fill = fill_gold_tot
            c_s_s.font = font_totals
            c_s_s.alignment = align_rt
            c_s_s.number_format = "#,##0.00"
            c_s_s.border = border_totals

            c_c_s = ws_sh.cell(row=sh_tot_row, column=col_comp_idx, value=f"=SUBTOTAL(9, {col_comp_letter}{sh_start_row}:{col_comp_letter}{sh_end_row})")
            c_c_s.fill = fill_gold_tot
            c_c_s.font = font_totals
            c_c_s.alignment = align_rt
            c_c_s.number_format = "#,##0.00"
            c_c_s.border = border_totals

            ws_sh.freeze_panes = "A5"
            ws_sh.auto_filter.ref = f"A4:{last_col_letter}{sh_end_row}"

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 6 — Save Excel & Optional PDF Export
    # ═════════════════════════════════════════════════════════════════════════
    notify(94, "جاري حفظ مصنف Excel الشامل على القرص...")
    chk()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    wb.save(output_path)

    pdf_file_path = None
    if export_claim_pdf and include_pro_sheets:
        notify(97, "جاري تصدير كشف المطالبة المعتمد كملف PDF رسمي...")
        chk()
        base_no_ext = os.path.splitext(output_path)[0]
        pdf_file_path = f"{base_no_ext}_كشف_مطالبة_رسمي.pdf"
        res_pdf = export_claim_to_pdf(output_path, pdf_file_path, sheet_name="📄 كشف مطالبة معتمد")
        if not res_pdf:
            pdf_file_path = None

    elapsed = round(time.time() - t_start, 2)
    notify(100, f"✅ اكتمل التصدير بنجاح! تم تصدير {len(report_rows):,} حركة في {elapsed} ثانية.")

    return {
        'success': True,
        'output_path': output_path,
        'pdf_path': pdf_file_path,
        'total_records': len(report_rows),
        'total_rows': len(report_rows),
        'total_columns': num_cols,
        'total_time': elapsed,
        'elapsed_seconds': elapsed,
        'total_sales': total_sales_amount,
        'total_compensation': total_compensation_amount,
        'total_qty': total_qty_count,
        'distinct_invoices': distinct_invoices_count,
        'distinct_products': len(product_rollup),
        'top_product_name': top_product_name,
        'top_product_comp': top_product_comp,
    }
