"""
pos_discount_engine.py — High-Performance POS Discounted Sales & Vendor Compensation Report Engine
Designed by: عبدالله الخطيب (Abdullah Al-Khatib)
Version: v1.02 (Ultra-Fast Turbo Edition)

OPTIMIZATION ARCHITECTURE:
  Phase 1 — Parameter & domain resolution (Timezone UTC+3 conversion, Showrooms POS config mapping, Product/Tag filters)
  Phase 2 — Multi-threaded concurrent chunked retrieval of pos.order.line records (discount != 0)
  Phase 3 — Concurrent bulk batch caching of unique orders and unique products
  Phase 4 — Instant in-memory vectorized row construction, sorting, and compensation calculations
  Phase 5 — High-speed streaming Excel generation via ws.append with professional RTL styling, formulas & auto-filters
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

from security import get_odoo_credentials
from exporter_engine import get_active_showrooms, get_all_product_tags, safe_execute_kw, match_wildcards, parse_tokens


# ─────────────────────────────────────────────────────────────────────────────
# Core Generator Function
# ─────────────────────────────────────────────────────────────────────────────

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
    output_path=None,
    progress_callback=None,
    cancel_check_callback=None,
    is_cancelled=None,
    **kwargs
):
    """
    High-performance export function for detailed POS discounted sales and supplier compensation claims.
    Filters exclusively for transactions with discounts (discount != 0), both sales and returns.
    """
    t_start = time.time()

    def notify(pct, text):
        if progress_callback:
            try:
                progress_callback(pct, text)
            except Exception:
                pass

    def chk():
        if is_cancelled and is_cancelled():
            raise InterruptedError("تم إلغاء عملية التصدير بواسطة المستخدم.")
        if cancel_check_callback and cancel_check_callback():
            raise InterruptedError("تم إلغاء عملية التصدير بواسطة المستخدم.")

    if not output_path:
        d_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        output_path = os.path.join(desktop, f"تقرير_مبيعات_الخصومات_{d_str}.xlsx")

    notify(2, "جاري الاتصال بنظام Odoo وتهيئة فلاتر التقرير...")
    chk()

    url, db, username, password = get_odoo_credentials()
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, username, password, {})
    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 1 — Filter & Parameter Resolution
    # ═════════════════════════════════════════════════════════════════════════

    # 1. Showrooms & POS configs
    all_showrooms = get_active_showrooms()
    config_to_sh_name = {}
    for s in all_showrooms:
        for cfg_id in s.get('pos_config_ids', []):
            config_to_sh_name[cfg_id] = s['name']

    target_showrooms = all_showrooms
    if selected_showroom_ids:
        s_set = set(selected_showroom_ids)
        target_showrooms = [s for s in all_showrooms if s['id'] in s_set]

    selected_config_ids = []
    for s in target_showrooms:
        selected_config_ids.extend(s.get('pos_config_ids', []))
    selected_config_ids = list(set(selected_config_ids))

    if len(target_showrooms) == len(all_showrooms):
        showroom_label = f"كافة المعارض والفروع ({len(all_showrooms)} فرعاً)"
    else:
        showroom_label = f"{len(target_showrooms)} معارض مختارة (" + "، ".join(s['name'] for s in target_showrooms[:3]) + ("..." if len(target_showrooms) > 3 else "") + ")"

    # 2. Date period resolution (converting KSA time UTC+3 to Odoo UTC)
    date_filter = []
    period_title = "إجمالي كافة الفترات"
    now_ksa = datetime.now()

    if sales_period == "last_30_days":
        start_ksa = (now_ksa - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = start_ksa - timedelta(hours=3)
        date_filter = [['order_id.date_order', '>=', start_utc.strftime("%Y-%m-%d %H:%M:%S")]]
        period_title = "آخر 30 يوماً"
    elif sales_period == "last_60_days":
        start_ksa = (now_ksa - timedelta(days=60)).replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = start_ksa - timedelta(hours=3)
        date_filter = [['order_id.date_order', '>=', start_utc.strftime("%Y-%m-%d %H:%M:%S")]]
        period_title = "آخر 60 يوماً"
    elif sales_period == "last_90_days":
        start_ksa = (now_ksa - timedelta(days=90)).replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = start_ksa - timedelta(hours=3)
        date_filter = [['order_id.date_order', '>=', start_utc.strftime("%Y-%m-%d %H:%M:%S")]]
        period_title = "آخر 90 يوماً"
    elif sales_period == "this_year":
        start_ksa = datetime(now_ksa.year, 1, 1, 0, 0, 0)
        start_utc = start_ksa - timedelta(hours=3)
        date_filter = [['order_id.date_order', '>=', start_utc.strftime("%Y-%m-%d %H:%M:%S")]]
        period_title = f"العام الحالي ({now_ksa.year})"
    elif sales_period == "custom":
        d_from = custom_date_from or now_ksa.strftime("%Y-%m-%d")
        d_to = custom_date_to or now_ksa.strftime("%Y-%m-%d")
        try:
            start_ksa = datetime.strptime(d_from, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
            end_ksa = datetime.strptime(d_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            start_utc = start_ksa - timedelta(hours=3)
            end_utc = end_ksa - timedelta(hours=3)
            date_filter = [
                ['order_id.date_order', '>=', start_utc.strftime("%Y-%m-%d %H:%M:%S")],
                ['order_id.date_order', '<=', end_utc.strftime("%Y-%m-%d %H:%M:%S")]
            ]
            period_title = f"من {d_from} إلى {d_to}"
        except Exception:
            date_filter = []
            period_title = "فترة مخصصة غير محددة"

    notify(5, "جاري فحص فلاتر الأصناف والمطابقة...")
    chk()

    # 3. Product & Tag filtering
    matched_product_ids = None
    has_product_filter = bool(filter_internal_ref or filter_barcode or filter_name or filter_tags)

    if has_product_filter:
        p_dom = [['sale_ok', '=', True]]

        # Tags filter
        if filter_tags:
            all_tags_list = get_all_product_tags()
            tag_name_map = {t['name'].strip().lower(): t['id'] for t in all_tags_list}
            matched_tag_ids = [tag_name_map[t.strip().lower()] for t in filter_tags if t.strip().lower() in tag_name_map]
            if matched_tag_ids:
                p_dom.append(['product_tag_ids', 'in', matched_tag_ids])

        # Query products
        p_fields = ['id', 'default_code', 'barcode', 'name']
        found_products = safe_execute_kw(models, db, uid, password, 'product.product', 'search_read',
                                        [p_dom], {'fields': p_fields})

        # Apply internal reference, barcode, and name filters in-memory with wildcards
        ref_tokens = parse_tokens(filter_internal_ref)
        bc_tokens = parse_tokens(filter_barcode)
        name_tokens = parse_tokens(filter_name)

        filtered_pids = []
        for p in found_products:
            if ref_tokens and not match_wildcards(p.get('default_code') or '', ref_tokens):
                continue
            if bc_tokens and not match_wildcards(p.get('barcode') or '', bc_tokens):
                continue
            if name_tokens and not match_wildcards(p.get('name') or '', name_tokens):
                continue
            filtered_pids.append(p['id'])

        matched_product_ids = filtered_pids
        if not matched_product_ids:
            notify(100, "لم يتم العثور على أي أصناف تطابق الفلاتر المحددة.")
            raise ValueError("لم يتم العثور على أي أصناف تطابق الفلاتر المحددة.")

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 2 — Multi-Threaded Chunk Retrieval of Discounted Lines
    # ═════════════════════════════════════════════════════════════════════════
    line_domain = [
        ['discount', '!=', 0],
        ['order_id.state', 'in', ['paid', 'done', 'invoiced']]
    ]
    line_domain += date_filter

    if selected_config_ids and len(selected_config_ids) < len(config_to_sh_name):
        line_domain.append(['order_id.config_id', 'in', selected_config_ids])

    if matched_product_ids is not None:
        if len(matched_product_ids) <= 3000:
            line_domain.append(['product_id', 'in', matched_product_ids])

    notify(10, "جاري احتساب إجمالي حركات المبيعات المخصومة في نقاط البيع...")
    chk()

    total_lines = safe_execute_kw(models, db, uid, password, 'pos.order.line', 'search_count', [line_domain])

    if total_lines == 0:
        notify(100, "لم يتم العثور على أي حركات مبيعات تحتوي على خصومات للفلاتر المحددة.")
        raise ValueError("لم يتم العثور على أي حركات مبيعات تحتوي على خصومات للفلاتر المحددة.")

    notify(15, f"تم العثور على {total_lines:,} حركة مخصومة. جاري جلب تفاصيل السطور بالتوازي...")
    chk()

    CHUNK_SIZE = 5000
    line_fields = ['order_id', 'product_id', 'qty', 'price_unit', 'discount', 'price_subtotal_incl']

    def _fetch_line_chunk(offset, limit):
        m_local = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        return safe_execute_kw(m_local, db, uid, password, 'pos.order.line', 'search_read',
                               [line_domain],
                               {'fields': line_fields, 'offset': offset, 'limit': limit, 'order': 'id asc'})

    chunks = [(off, min(CHUNK_SIZE, total_lines - off)) for off in range(0, total_lines, CHUNK_SIZE)]
    all_lines = []
    completed_chunks = 0

    max_line_workers = min(8, len(chunks)) if len(chunks) > 1 else 1
    with ThreadPoolExecutor(max_workers=max_line_workers) as executor:
        futures = [executor.submit(_fetch_line_chunk, off, lim) for off, lim in chunks]
        for fut in futures:
            chk()
            chunk_res = fut.result()
            all_lines.extend(chunk_res)
            completed_chunks += 1
            pct = 15 + int(35 * (completed_chunks / len(chunks)))
            notify(pct, f"تم استخراج {len(all_lines):,} من أصل {total_lines:,} حركة مخصومة...")

    # If matched_product_ids was too large to put in domain, filter in memory now
    if matched_product_ids is not None and len(matched_product_ids) > 3000:
        p_set = set(matched_product_ids)
        all_lines = [l for l in all_lines if l.get('product_id') and l['product_id'][0] in p_set]

    if not all_lines:
        notify(100, "لم تطابق أي حركة مخصومة فلاتر الأصناف المحددة.")
        return {
            'success': True,
            'output_path': None,
            'total_records': 0,
            'total_time': round(time.time() - t_start, 2)
        }

    notify(55, f"اكتمل جلب السطور ({len(all_lines):,} حركة). جاري استرجاع بيانات الفواتير والمنتجات...")
    chk()

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 3 — Bulk Caching of Unique Orders and Unique Products
    # ═════════════════════════════════════════════════════════════════════════
    unique_order_ids = list(set(l['order_id'][0] for l in all_lines if l.get('order_id')))
    unique_product_ids = list(set(l['product_id'][0] for l in all_lines if l.get('product_id')))

    BATCH_SIZE = 3000

    def _fetch_order_batch(b_ids):
        m_local = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        return safe_execute_kw(m_local, db, uid, password, 'pos.order', 'read',
                               [b_ids], {'fields': ['name', 'pos_reference', 'date_order', 'account_move', 'config_id']})

    def _fetch_product_batch(b_ids):
        m_local = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        return safe_execute_kw(m_local, db, uid, password, 'product.product', 'read',
                               [b_ids], {'fields': ['default_code', 'barcode', 'name']})

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

    notify(70, "جاري معالجة التواريخ والتوقيت المحلي وحساب مبالغ التعويض...")
    chk()

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 4 — Vectorized In-Memory Row Construction
    # ═════════════════════════════════════════════════════════════════════════
    report_rows = []

    for line in all_lines:
        order = orders_map.get(line['order_id'][0], {})
        product = products_map.get(line['product_id'][0], {})

        # 1. Official Invoice number or POS reference
        inv_num = ''
        if order.get('account_move') and order['account_move']:
            inv_num = str(order['account_move'][1]).split(' ')[0]
        if not inv_num:
            inv_num = order.get('pos_reference') or order.get('name') or ''

        # 2 & 3. Date & Time in KSA local time (UTC+3)
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

        # 4, 5, 6. Product details
        code = product.get('default_code') or ''
        barcode = product.get('barcode') or ''
        prod_name = product.get('name') or ''

        # 7, 8, 9, 10, 11. Quantities & Financials
        qty = float(line.get('qty') or 0.0)
        price_unit = float(line.get('price_unit') or 0.0)
        discount = float(line.get('discount') or 0.0)
        subtotal_incl = float(line.get('price_subtotal_incl') or 0.0)

        # Compensation claim amount (amount discounted)
        # = (Qty * Unit Price) - Subtotal Incl Tax
        compensation = round((qty * price_unit) - subtotal_incl, 2)

        sh_name = ''
        if include_showroom_col:
            cfg_tuple = order.get('config_id')
            if cfg_tuple and isinstance(cfg_tuple, (list, tuple)):
                sh_name = config_to_sh_name.get(cfg_tuple[0], cfg_tuple[1])

        report_rows.append({
            'sort_key': sort_key_dt,
            'invoice_no': inv_num,
            'showroom': sh_name,
            'date': date_str,
            'time': time_str,
            'default_code': code,
            'barcode': barcode,
            'product_name': prod_name,
            'qty': qty,
            'price_unit': price_unit,
            'discount': discount / 100.0,   # stored as fraction for 0.0% formatting
            'subtotal_incl': subtotal_incl,
            'compensation': compensation,
        })

    # Sort chronologically ascending by Date and Time
    report_rows.sort(key=lambda r: r['sort_key'])

    notify(80, f"جاري إنشاء وتنسيق مصنف Excel المتقدم ({len(report_rows):,} سجل)...")
    chk()

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 5 — Professional Excel Streaming & Styling
    # ═════════════════════════════════════════════════════════════════════════
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "تفاصيل مبيعات وخصومات الفواتير"
    ws.views.sheetView[0].rightToLeft = True

    # Color Palette
    C_NAVY_DARK   = "1F4E79"
    C_BLUE_HDR    = "2E75B6"
    C_BG_ALT      = "F8FAFC"
    C_WHITE       = "FFFFFF"
    C_TOTALS_BG   = "FFF2CC"
    C_TOTALS_FG   = "7F6000"
    C_BORDER      = "D9D9D9"
    C_CODE_FG     = "1E3A8A"
    C_COMP_FG     = "166534"

    fill_title   = PatternFill("solid", fgColor=C_NAVY_DARK)
    fill_info    = PatternFill("solid", fgColor="F1F5F9")
    fill_hdr     = PatternFill("solid", fgColor=C_BLUE_HDR)
    fill_alt     = PatternFill("solid", fgColor=C_BG_ALT)
    fill_totals  = PatternFill("solid", fgColor=C_TOTALS_BG)

    font_title   = Font(name="Segoe UI", size=13, bold=True, color="FFFFFF")
    font_info    = Font(name="Segoe UI", size=9.5, color="334155")
    font_hdr     = Font(name="Segoe UI", size=9.5, bold=True, color="FFFFFF")
    font_body    = Font(name="Segoe UI", size=9)
    font_code    = Font(name="Segoe UI", size=9, bold=True, color=C_CODE_FG)
    font_comp    = Font(name="Segoe UI", size=9.5, bold=True, color=C_COMP_FG)
    font_totals  = Font(name="Segoe UI", size=10, bold=True, color=C_TOTALS_FG)

    s_border     = Side(style='thin', color=C_BORDER)
    border_cell  = Border(left=s_border, right=s_border, top=s_border, bottom=s_border)
    s_top_tot    = Side(style='thin', color=C_TOTALS_FG)
    s_bot_tot    = Side(style='double', color=C_TOTALS_FG)
    border_tot   = Border(left=s_top_tot, right=s_top_tot, top=s_top_tot, bottom=s_bot_tot)

    align_center = Alignment(horizontal="center", vertical="center", wrap_text=False)
    align_left   = Alignment(horizontal="left",   vertical="center", wrap_text=False)
    align_right  = Alignment(horizontal="right",  vertical="center", wrap_text=False)
    align_hdr    = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Column configuration
    if include_showroom_col:
        headers = [
            ("رقم الفاتورة", 22, "@", align_center, font_body),
            ("المعرض / الفرع", 20, "@", align_center, font_body),
            ("تاريخ الفاتورة", 14, "yyyy-mm-dd", align_center, font_body),
            ("وقت الفاتورة", 12, "hh:mm:ss", align_center, font_body),
            ("رقم الصنف", 18, "@", align_center, font_code),
            ("باركود الصنف", 18, "@", align_center, font_body),
            ("اسم الصنف الانجليزي", 38, "@", align_left, font_body),
            ("الكمية المباعة في الفاتورة", 16, "#,##0.00", align_center, font_body),
            ("السعر قبل الخصم في الفاتورة شامل الضريبة", 22, "#,##0.00", align_right, font_body),
            ("الخصم في الفاتورة", 14, "0.0%", align_center, font_body),
            ("الاجمالي بعد الخصم شامل الضريبة", 22, "#,##0.00", align_right, font_body),
            ("التعويض المطلوب من المورد وهو عبارة عن المبلغ المخصوم", 26, "#,##0.00", align_right, font_comp),
        ]
        col_qty_idx = 8
        col_subtot_idx = 11
        col_comp_idx = 12
    else:
        headers = [
            ("رقم الفاتورة", 22, "@", align_center, font_body),
            ("تاريخ الفاتورة", 14, "yyyy-mm-dd", align_center, font_body),
            ("وقت الفاتورة", 12, "hh:mm:ss", align_center, font_body),
            ("رقم الصنف", 18, "@", align_center, font_code),
            ("باركود الصنف", 18, "@", align_center, font_body),
            ("اسم الصنف الانجليزي", 38, "@", align_left, font_body),
            ("الكمية المباعة في الفاتورة", 16, "#,##0.00", align_center, font_body),
            ("السعر قبل الخصم في الفاتورة شامل الضريبة", 22, "#,##0.00", align_right, font_body),
            ("الخصم في الفاتورة", 14, "0.0%", align_center, font_body),
            ("الاجمالي بعد الخصم شامل الضريبة", 22, "#,##0.00", align_right, font_body),
            ("التعويض المطلوب من المورد وهو عبارة عن المبلغ المخصوم", 26, "#,##0.00", align_right, font_comp),
        ]
        col_qty_idx = 7
        col_subtot_idx = 10
        col_comp_idx = 11

    num_cols = len(headers)
    last_col_letter = get_column_letter(num_cols)

    # 1. Title Banner (Row 2)
    ws.merge_cells(f"A2:{last_col_letter}2")
    c_title = ws.cell(row=2, column=1, value=f"🧾 تقرير تفاصيل مبيعات وخصومات نقاط البيع — {period_title}")
    c_title.font = font_title
    c_title.fill = fill_title
    c_title.alignment = align_center
    ws.row_dimensions[2].height = 34

    # 2. Metadata Information Subtitle (Row 3)
    ws.merge_cells(f"A3:{last_col_letter}3")
    export_time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    info_text = f"الفترة: {period_title}  |  المعارض: {showroom_label}  |  عدد الحركات المخصومة: {len(report_rows):,} حركة  |  تاريخ التصدير: {export_time_str}"
    c_info = ws.cell(row=3, column=1, value=info_text)
    c_info.font = font_info
    c_info.fill = fill_info
    c_info.alignment = align_center
    ws.row_dimensions[3].height = 24

    ws.row_dimensions[4].height = 8

    # 3. Table Headers (Row 5)
    for col_idx, (hdr_text, col_w, _, _, _) in enumerate(headers, 1):
        cell = ws.cell(row=5, column=col_idx, value=hdr_text)
        cell.font = font_hdr
        cell.fill = fill_hdr
        cell.alignment = align_hdr
        cell.border = border_cell
        ws.column_dimensions[get_column_letter(col_idx)].width = col_w
    ws.row_dimensions[5].height = 32

    # 4. Stream Data Rows
    start_data_row = 6
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
        ws.append(row_vals)

    end_data_row = start_data_row + len(report_rows) - 1

    # Apply cell styles and formats in batch
    for row_idx in range(start_data_row, end_data_row + 1):
        is_alt = (row_idx % 2 == 1)
        row_fill = fill_alt if is_alt else None
        ws.row_dimensions[row_idx].height = 20

        for col_idx, (_, _, num_fmt, alignment, c_font) in enumerate(headers, 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = c_font
            cell.alignment = alignment
            cell.number_format = num_fmt
            cell.border = border_cell
            if row_fill:
                cell.fill = row_fill

    # 5. Totals Row at the bottom
    tot_row = end_data_row + 1
    ws.row_dimensions[tot_row].height = 24

    col_qty_letter = get_column_letter(col_qty_idx)
    col_subtot_letter = get_column_letter(col_subtot_idx)
    col_comp_letter = get_column_letter(col_comp_idx)

    # Empty cells up to Qty
    for c_i in range(1, col_qty_idx):
        c = ws.cell(row=tot_row, column=c_i)
        c.fill = fill_totals
        c.border = border_tot
        c.font = font_totals
        if c_i == 1:
            c.value = "▶ الإجمالي العام"
            c.alignment = align_center

    # Sum for Qty
    c_qty_tot = ws.cell(row=tot_row, column=col_qty_idx, value=f"=SUM({col_qty_letter}{start_data_row}:{col_qty_letter}{end_data_row})")
    c_qty_tot.fill = fill_totals
    c_qty_tot.font = font_totals
    c_qty_tot.alignment = align_center
    c_qty_tot.number_format = "#,##0.00"
    c_qty_tot.border = border_tot

    # Empty for price_unit and discount
    for c_i in range(col_qty_idx + 1, col_subtot_idx):
        c = ws.cell(row=tot_row, column=c_i, value="-")
        c.fill = fill_totals
        c.font = font_totals
        c.alignment = align_center
        c.border = border_tot

    # Sum for Subtotal
    c_subtot = ws.cell(row=tot_row, column=col_subtot_idx, value=f"=SUM({col_subtot_letter}{start_data_row}:{col_subtot_letter}{end_data_row})")
    c_subtot.fill = fill_totals
    c_subtot.font = font_totals
    c_subtot.alignment = align_right
    c_subtot.number_format = "#,##0.00"
    c_subtot.border = border_tot

    # Sum for Compensation
    c_comp = ws.cell(row=tot_row, column=col_comp_idx, value=f"=SUM({col_comp_letter}{start_data_row}:{col_comp_letter}{end_data_row})")
    c_comp.fill = fill_totals
    c_comp.font = font_totals
    c_comp.alignment = align_right
    c_comp.number_format = "#,##0.00"
    c_comp.border = border_tot

    # 6. Freeze panes below headers and enable auto-filter
    ws.freeze_panes = "A6"
    ws.auto_filter.ref = f"A5:{last_col_letter}{end_data_row}"

    notify(95, "جاري حفظ ملف Excel النهائي على القرص...")
    chk()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    wb.save(output_path)

    elapsed = round(time.time() - t_start, 2)
    notify(100, f"✅ اكتمل التصدير بنجاح! تم تصدير {len(report_rows):,} حركة خصم في {elapsed} ثانية.")

    return {
        'success': True,
        'output_path': output_path,
        'total_records': len(report_rows),
        'total_rows': len(report_rows),
        'total_columns': num_cols,
        'total_time': elapsed,
        'elapsed_seconds': elapsed
    }
