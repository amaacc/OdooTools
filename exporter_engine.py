"""
exporter_engine.py — Optimized Odoo Report Engine
Designed by: عبدالله الخطيب (Abdullah Al-Khatib)

OPTIMIZATION STRATEGY:
  Phase 1 — Parallel global lookups (taxes, tags, packages, pricelist, showrooms)
  Phase 2 — Read product fields in batches → apply all filters in Python → get filtered list
  Phase 3 — Fetch vendor/PO/quant data ONLY for filtered products (huge speedup for small filters)
  Phase 4 — Build Excel with totals row and branch summary sheet
"""

import os
import time
import fnmatch
import xmlrpc.client
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from security import get_odoo_credentials
from permissions import load_permissions


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
    clean_items = [str(it).strip().lower() for it in items if it]
    if not clean_items:
        return False
    for pat in patterns:
        pc = pat.strip().lower()
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
            'id': wid, 'name': w['name'], 'code': w.get('code') or '',
            'lot_stock_id': w['lot_stock_id'][0] if w.get('lot_stock_id') else None,
            'pos_config_ids': cfg_ids
        })
    return showrooms


def get_all_product_tags():
    """Fetch all product tags for UI autocomplete."""
    try:
        url, db, username, password = get_odoo_credentials()
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        uid = common.authenticate(db, username, password, {})
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        tags = safe_execute_kw(models, db, uid, password, 'product.tag', 'search_read',
                               [[]], {'fields': ['id', 'name']})
        return sorted([t['name'] for t in tags if t.get('name')])
    except Exception:
        return []


def generate_report(
    selected_showroom_ids=None,
    column_options=None,
    sales_period="all",
    custom_date_from=None,
    custom_date_to=None,
    movement_filter="all",
    filter_internal_ref=None,
    filter_barcode=None,
    filter_name=None,
    filter_tags=None,
    output_path=None,
    progress_callback=None,
    is_cancelled=None
):
    # ── helpers ───────────────────────────────────────────────────────────────
    def notify(pct, msg):
        if progress_callback:
            progress_callback(pct, msg)
        print(f"[{pct:.0f}%] {msg}", flush=True)

    def chk():
        if is_cancelled and is_cancelled():
            raise InterruptedError("Cancelled by user.")

    t_start = time.time()
    permissions, _ = load_permissions()

    if column_options is None:
        column_options = {k: True for k in ('basic_info', 'pricing', 'totals', 'vendors', 'showrooms')}

    ref_pat = parse_tokens(filter_internal_ref)
    bc_pat  = parse_tokens(filter_barcode)
    nm_pat  = parse_tokens(filter_name)
    tg_pat  = parse_tokens(filter_tags)

    # ═════════════════════════════════════════════════════════════════════════
    # CONNECT
    # ═════════════════════════════════════════════════════════════════════════
    notify(2, "جاري الاتصال الآمن بنظام Odoo...")
    url, db, username, password = get_odoo_credentials()
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, username, password, {})
    if not uid:
        raise ConnectionError("فشل تسجيل الدخول إلى Odoo.")
    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
    chk()

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 1 — Parallel global lookups (thread-safe ServerProxy per task)
    # ═════════════════════════════════════════════════════════════════════════
    notify(5, "جاري تحميل جداول البيانات المساعدة بشكل متوازٍ...")

    def _fetch_taxes():
        m = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        t = safe_execute_kw(m, db, uid, password, 'account.tax', 'search_read',
                            [[]], {'fields': ['id', 'name']})
        return {x['id']: x['name'] for x in t}

    def _fetch_tags():
        m = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        t = safe_execute_kw(m, db, uid, password, 'product.tag', 'search_read',
                            [[]], {'fields': ['id', 'name']})
        return {x['id']: x['name'] for x in t}

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
    # PHASE 2 — Smart Odoo-side domain + Python wildcard post-filter
    # Push as much filtering as possible to Odoo to minimize data transfer
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
            stem = ref_pat[0].replace('*', '').replace('?', '')
            if stem:
                base_domain.append(['default_code', 'ilike', stem])
            need_python_ref = True

    if nm_pat:
        has_wc = any('*' in t or '?' in t for t in nm_pat)
        stem = nm_pat[0].replace('*', '').replace('?', '')
        if stem:
            base_domain += ['|', ['name', 'ilike', stem],
                                  ['product_name_arabic', 'ilike', stem]]
        if has_wc or len(nm_pat) > 1:
            need_python_name = True

    if bc_pat:
        stem = bc_pat[0].replace('*', '').replace('?', '')
        if stem:
            base_domain += ['|', ['barcode', 'ilike', stem],
                                  ['packaging_ids.barcode', 'ilike', stem]]
        need_python_bc = True  # always Python-check pkg barcodes & wildcards

    if tg_pat:
        stem = tg_pat[0].replace('*', '').replace('?', '')
        if stem:
            base_domain.append(['product_tag_ids.name', 'ilike', stem])
        need_python_tags = True

    all_product_ids = safe_execute_kw(models, db, uid, password,
                                      'product.product', 'search', [base_domain])
    total_all = len(all_product_ids)
    notify(15, f"الأصناف بعد فلتر Odoo: {total_all:,} — جاري قراءة التفاصيل...")
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

    # Read product data in batches and filter in memory
    BATCH = 3000
    filtered_records = []
    total_chunks = (total_all + BATCH - 1) // BATCH

    for idx in range(0, total_all, BATCH):
        chk()
        chunk_num = idx // BATCH + 1
        pct = 15 + (chunk_num / total_chunks) * 25
        notify(pct, f"قراءة وتصفية الدفعة {chunk_num}/{total_chunks}...")
        chunk_ids = all_product_ids[idx: idx + BATCH]
        records = safe_execute_kw(models, db, uid, password, 'product.product', 'read',
                                  [chunk_ids], {'fields': fields_to_read})
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

            # Only run Python checks for patterns that need wildcard refinement
            if need_python_ref  and not match_wildcards(code_val, ref_pat):   continue
            if need_python_bc   and not match_wildcards([barcode_val] + pkg_bc, bc_pat): continue
            if need_python_name and not match_wildcards([name_val, name_ar], nm_pat):    continue
            if need_python_tags and not match_wildcards(tag_names, tg_pat):    continue

            r['_pkg_bc']    = pkg_bc
            r['_tag_names'] = tag_names
            filtered_records.append(r)

    total_filtered = len(filtered_records)
    notify(42, f"نتيجة الفلتر: {total_filtered:,} صنف مطابق من أصل {total_all:,}")
    chk()

    if total_filtered == 0:
        raise ValueError("لم يتم العثور على أصناف تطابق الفلاتر المحددة.")

    filtered_product_ids = [r['id'] for r in filtered_records]
    # Build tmpl map
    prod_to_tmpl = {}
    filtered_tmpl_ids = []
    for r in filtered_records:
        pid = r['id']
        tid = r['product_tmpl_id'][0] if isinstance(r.get('product_tmpl_id'), (list, tuple)) else r.get('product_tmpl_id')
        prod_to_tmpl[pid] = tid
        if tid not in filtered_tmpl_ids:
            filtered_tmpl_ids.append(tid)

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 3 — Fetch vendor/PO/quant data ONLY for filtered products (FAST!)
    # ═════════════════════════════════════════════════════════════════════════
    notify(44, f"جاري جلب بيانات الموردين والمشتريات لـ {total_filtered:,} صنف فقط...")

    def _fetch_vendors():
        if not filtered_tmpl_ids:
            return {}
        m = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        # One call for all filtered templates (much faster than batching 75k)
        sup = safe_execute_kw(m, db, uid, password, 'product.supplierinfo', 'search_read',
                              [[['product_tmpl_id', 'in', filtered_tmpl_ids]]],
                              {'fields': ['product_tmpl_id', 'partner_id', 'price', 'discount',
                                          'price_discounted', 'last_purchase_date', 'write_date'],
                               'order': 'sequence asc, id asc'})
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
        # Use read_group for fast aggregation (1 call, no batching)
        groups = safe_execute_kw(m, db, uid, password, 'purchase.order.line', 'read_group',
                                 [[['product_id', 'in', filtered_product_ids],
                                   ['order_id.state', 'in', ['purchase', 'done']]]],
                                 {'fields': ['product_id', 'qty_received'],
                                  'groupby': ['product_id']})
        return {g['product_id'][0]: float(g.get('qty_received') or 0.0)
                for g in groups if g.get('product_id')}

    def _fetch_quants():
        # Only fetch quants for showroom locations + filtered products (not ALL internal locations)
        target_loc_ids = [s['lot_stock_id'] for s in target_showrooms if s.get('lot_stock_id')]
        if not target_loc_ids or not filtered_product_ids:
            return {}
        m = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        quants = safe_execute_kw(m, db, uid, password, 'stock.quant', 'search_read',
                                 [[['location_id', 'in', target_loc_ids],
                                   ['product_id', 'in', filtered_product_ids],
                                   ['quantity', '!=', 0]]],
                                 {'fields': ['product_id', 'location_id', 'quantity']})
        qmap = {}
        for q in quants:
            if q.get('product_id') and q.get('location_id'):
                qmap[(q['product_id'][0], q['location_id'][0])] = float(q.get('quantity') or 0.0)
        return qmap

    # POS sales date filter
    today = datetime.now()
    date_filter = []
    if sales_period == "last_30_days":
        date_filter.append(['date', '>=', (today - timedelta(days=30)).strftime('%Y-%m-%d 00:00:00')])
    elif sales_period == "last_60_days":
        date_filter.append(['date', '>=', (today - timedelta(days=60)).strftime('%Y-%m-%d 00:00:00')])
    elif sales_period == "last_90_days":
        date_filter.append(['date', '>=', (today - timedelta(days=90)).strftime('%Y-%m-%d 00:00:00')])
    elif sales_period == "this_year":
        date_filter.append(['date', '>=', f"{today.year}-01-01 00:00:00"])
    elif sales_period == "custom" and custom_date_from:
        date_filter.append(['date', '>=', f"{custom_date_from} 00:00:00"])
        if custom_date_to:
            date_filter.append(['date', '<=', f"{custom_date_to} 23:59:59"])

    def _fetch_pos_sales_for(s):
        models_t = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        dom = [['state', 'in', ['paid', 'done', 'invoiced']],
               ['config_id', 'in', s['pos_config_ids']]] + date_filter
        # Filter by filtered products for faster POS query
        if filtered_product_ids:
            dom.append(['product_id', 'in', filtered_product_ids])
        res = models_t.execute_kw(db, uid, password, 'report.pos.order', 'read_group',
                                  [dom, ['product_id', 'product_qty:sum'], ['product_id']],
                                  {'lazy': False})
        return s['id'], {r['product_id'][0]: float(r.get('product_qty') or 0.0)
                         for r in res if r.get('product_id')}

    # Run all Phase 3 fetches in parallel
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

    notify(70, f"اكتمل جلب البيانات. جاري بناء السجلات ({total_filtered:,} صنف)...")
    chk()

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 4 — Build rows
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

        cost        = float(r.get('standard_price') or 0.0)
        sales_price = float(r.get('list_price') or 0.0)
        so_price    = float(r.get('sales_price') or 0.0)
        pos_min     = float(r.get('pos_min_price') or 0.0)
        qty_oh      = float(r.get('qty_available') or 0.0)
        total_sold  = float(r.get('sales_count') or 0.0)

        # Shati price
        shati_price = shati_variant_map.get(pid) or shati_tmpl_map.get(tid)
        if shati_price is None:
            for tr in shati_tag_rules:
                if tr['tag_id'] in tag_ids:
                    if tr['compute_price'] == 'percentage':
                        shati_price = round(sales_price * (1 - tr['percent_price'] / 100.0), 2)
                    elif tr['compute_price'] == 'fixed':
                        shati_price = tr['fixed_price']
                    break
        if not shati_price or shati_price <= 0:
            shati_price = sales_price

        # Movement filter
        if movement_filter == "stagnant"    and not (qty_oh > 0 and total_sold == 0): continue
        if movement_filter == "fast_moving" and total_sold <= 0:                      continue
        if movement_filter == "low_stock"   and not (0 < qty_oh <= 5):                continue
        if movement_filter == "out_of_stock" and qty_oh > 0:                          continue

        vinfo = vendor_tmpl_map.get(tid, {})
        row = {}

        if column_options.get('basic_info', True):
            row["Internal Reference"]           = code_val
            row["Barcode"]                      = barcode_val
            row["Product Packages/Barcode"]     = pkg_str
            row["Name"]                         = name_val
            row["Product Name Arabic"]          = name_ar
            row["Products/Unit of Measure"]     = uom
            row["Products/Tags"]                = tags_str
            row["Products/Customer Taxes"]      = cust_taxes
            row["Products/Vendor Taxes"]        = vend_taxes

        if column_options.get('pricing', True):
            if permissions.get("Cost",              True): row["Cost"]              = cost
            if permissions.get("Sales Price",       True): row["Sales Price"]       = sales_price
            if permissions.get("Shati Price",       True): row["Shati Price"]       = float(shati_price)
            if permissions.get("SO Price",          True): row["SO Price"]          = so_price
            if permissions.get("Pos Minimum Price", True): row["Pos Minimum Price"] = pos_min

        if column_options.get('totals', True):
            if permissions.get("Quantity On Hand", True): row["Quantity On Hand"] = qty_oh
            if permissions.get("Sold",             True): row["Sold"]             = total_sold

        if column_options.get('vendors', True):
            if permissions.get("Vendors",                True): row["Vendors"]                = vinfo.get('vendor_name', '')
            if permissions.get("Vendors/Price",          True): row["Vendors/Price"]          = vinfo.get('vendor_price', 0.0)
            if permissions.get("Vendors/Discount (%)",   True): row["Vendors/Discount (%)"]   = vinfo.get('vendor_discount', 0.0)
            if permissions.get("Vendors/Discounted Price",True): row["Vendors/Discounted Price"] = vinfo.get('vendor_discounted_price', 0.0)
            if permissions.get("Vendors/Last Purchase",  True): row["Vendors/Last Purchase"]  = vinfo.get('vendor_last_purchase', '')
            if permissions.get("Vendors/Last Updated on",True): row["Vendors/Last Updated on"]= vinfo.get('vendor_last_updated', '')
            if permissions.get("Last Received Qty",      True): row["Last Received Qty"]      = last_received_map.get(pid, 0.0)

        if column_options.get('showrooms', True):
            sh_oh_total = 0.0
            sh_sl_total = 0.0
            for s in target_showrooms:
                s_id  = s['id']
                lot   = s['lot_stock_id']
                sh_oh = stock_map.get((pid, lot), 0.0) if lot else 0.0
                sh_sl = showroom_sales.get(s_id, {}).get(pid, 0.0)
                if permissions.get("Showrooms_OnHand", True):
                    row[f"{s['name']} / On Hand"] = sh_oh
                    sh_oh_total += sh_oh
                if permissions.get("Showrooms_Sold",   True):
                    row[f"{s['name']} / Sold"]    = sh_sl
                    sh_sl_total += sh_sl
                branch_summary[s_id]['total_on_hand']    += sh_oh
                branch_summary[s_id]['total_cost_value'] += sh_oh * cost if sh_oh > 0 else 0.0
                branch_summary[s_id]['total_sales_value']+= sh_oh * sales_price if sh_oh > 0 else 0.0
                branch_summary[s_id]['total_sold_units'] += sh_sl

            # Grand total summary columns (added after all showroom columns)
            if permissions.get("Showrooms_OnHand", True):
                row["إجمالي رصيد المعارض"] = sh_oh_total
            if permissions.get("Showrooms_Sold", True):
                row["إجمالي مبيعات المعارض"] = sh_sl_total

        # ── Smart Inventory Analytics & Supply Chain Suggestions ────────────
        if column_options.get('analytics', True):
            analysis_oh = sh_oh_total if column_options.get('showrooms', True) else qty_oh
            analysis_sl = sh_sl_total if column_options.get('showrooms', True) else total_sold
            monthly_sales = analysis_sl / 12.0

            # 1. Product Status
            if permissions.get("حالة الصنف", True):
                if analysis_oh <= 0:
                    if analysis_sl > 0:
                        item_status = "نفد المخزون"
                    else:
                        item_status = "غير متوفر"
                elif analysis_sl <= 0:
                    item_status = "راكد"
                else:
                    days_cover = (analysis_oh / analysis_sl) * 365.0
                    if days_cover <= 20 or (analysis_oh <= 5 and analysis_sl >= 10):
                        item_status = "قارب على النفاذ"
                    elif days_cover <= 60 or monthly_sales >= 15:
                        item_status = "سريع الحركة"
                    elif days_cover >= 180:
                        item_status = "فائض المخزون"
                    else:
                        item_status = "متوازن"
                row["حالة الصنف"] = item_status

            # 2. Suggested 60-Day Reorder Quantity (Target buffer: 2 months demand)
            if permissions.get("الطلب المقترح (60 يوم)", True):
                target_60d = monthly_sales * 2.0
                suggested_60d_qty = max(0.0, round(target_60d - analysis_oh))
                row["الطلب المقترح (60 يوم)"] = suggested_60d_qty

            # 3. Inter-branch transfer recommendations
            if permissions.get("توصيات المناقلة", True) and column_options.get('showrooms', True) and target_showrooms:
                deficits = []
                surpluses = []
                for s in target_showrooms:
                    s_id = s['id']
                    lot = s['lot_stock_id']
                    oh = stock_map.get((pid, lot), 0.0) if lot else 0.0
                    sl = showroom_sales.get(s_id, {}).get(pid, 0.0)
                    if oh <= 1 and sl > 0:
                        deficits.append((s['name'], oh, sl))
                    elif oh >= 4 and (sl == 0 or oh > (sl / 12.0) * 4):
                        surpluses.append((s['name'], oh, sl))

                if deficits and surpluses:
                    deficits.sort(key=lambda x: x[2], reverse=True)
                    surpluses.sort(key=lambda x: x[1], reverse=True)
                    for i in range(min(len(deficits), len(surpluses), 2)):
                        from_name = surpluses[i][0].replace("معرض ", "").replace("فرع ", "").strip()
                        to_name   = deficits[i][0].replace("معرض ", "").replace("فرع ", "").strip()
                        transfer_recs.append(f"من {from_name} إلى {to_name}")

                transfer_note = " | ".join(transfer_recs) if transfer_recs else "─"
                row["توصيات المناقلة"] = transfer_note

        export_rows.append(row)

    notify(82, f"تم بناء {len(export_rows):,} سجل. جاري توليد ملف Excel...")
    chk()

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 5 — Professional Excel with Custom Headers, Alignments & Formats
    # ═════════════════════════════════════════════════════════════════════════
    if not output_path:
        export_dir = r"c:\OdooDB\exports"
        os.makedirs(export_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(export_dir, f"odoo_report_{ts}.xlsx")

    # ── Color palette (print-friendly, soft tones) ─────────────────────────
    C_HDR_MAIN       = "2E75B6"   # Medium corporate blue
    C_HDR_SHOWROOM   = "1F4E79"   # Navy/slate blue (showroom merged name)
    C_HDR_SHOWROOM_L = "2E75B6"   # Blue (On Hand / Sold sub-headers)
    C_HDR_SUMMARY    = "833C0C"   # Soft warm terracotta (summary columns)
    C_ALT            = "F2F5F9"   # Very light ice/slate (alternating rows)
    C_TOTALS_BG      = "FFF2CC"   # Soft warm cream yellow
    C_TOTALS_FG      = "7F6000"   # Dark amber text
    C_WHITE          = "FFFFFF"
    C_BORDER         = "D9D9D9"   # Subtle clean grey border

    def _fill(color):
        return PatternFill("solid", fgColor=color)

    def _font(bold=False, color="000000", size=9, name="Segoe UI"):
        return Font(name=name, size=size, bold=bold, color=color)

    def _border(color=C_BORDER):
        s = Side(style='thin', color=color)
        return Border(left=s, right=s, top=s, bottom=s)

    ALIGN_CTR = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ALIGN_RT  = Alignment(horizontal="right",  vertical="center", wrap_text=False)
    ALIGN_LT  = Alignment(horizontal="left",   vertical="center", wrap_text=False)

    # ── Column Specifications ──────────────────────────────────────────────
    COLUMN_SPECS = {
        "Internal Reference": {
            "header": "Internal\nReference",
            "align": Alignment(horizontal="center", vertical="center", wrap_text=False),
            "num_format": "@",
            "total_type": "count",
            "width_mode": "data_len"
        },
        "Barcode": {
            "header": "Barcode",
            "align": Alignment(horizontal="center", vertical="center", wrap_text=False),
            "num_format": "@",
            "total_type": None,
            "width_mode": "data_len"
        },
        "Product Packages/Barcode": {
            "header": "Barcodes",
            "align": Alignment(horizontal="right", vertical="center", wrap_text=False),
            "num_format": "@",
            "total_type": None,
            "width_mode": "same_as_barcode"
        },
        "Name": {
            "header": "Name",
            "align": Alignment(horizontal="left", vertical="center", wrap_text=False),  # LTR left aligned
            "num_format": "@",
            "total_type": None,
            "width_mode": "data_len_capped"
        },
        "Product Name Arabic": {
            "header": "Product Name Arabic",
            "align": Alignment(horizontal="right", vertical="center", wrap_text=False),  # RTL right aligned
            "num_format": "@",
            "total_type": None,
            "width_mode": "data_len_capped"
        },
        "Products/Unit of Measure": {
            "header": "Unit",
            "align": Alignment(horizontal="center", vertical="center", wrap_text=False),
            "num_format": "@",
            "total_type": None,
            "width_mode": "auto"
        },
        "Products/Tags": {
            "header": "Products/Tags",
            "align": Alignment(horizontal="right", vertical="center", wrap_text=False),
            "num_format": "@",
            "total_type": None,
            "width_mode": "data_len_capped"
        },
        "Products/Customer Taxes": {
            "header": "Customer Taxes",
            "align": Alignment(horizontal="center", vertical="center", wrap_text=False),
            "num_format": "@",
            "total_type": None,
            "width_mode": "data_len"
        },
        "Products/Vendor Taxes": {
            "header": "Vendor Taxes",
            "align": Alignment(horizontal="center", vertical="center", wrap_text=False),
            "num_format": "@",
            "total_type": None,
            "width_mode": "data_len"
        },
        "Cost": {
            "header": "Cost",
            "align": Alignment(horizontal="right", vertical="center", wrap_text=False),
            "num_format": "#,##0.00",  # Comma style
            "total_type": None,
            "width_mode": "auto"
        },
        "Sales Price": {
            "header": "Price",
            "align": Alignment(horizontal="right", vertical="center", wrap_text=False),
            "num_format": "#,##0.00",  # Comma style
            "total_type": None,
            "width_mode": "auto"
        },
        "Shati Price": {
            "header": "Shati P",
            "align": Alignment(horizontal="right", vertical="center", wrap_text=False),
            "num_format": "#,##0.00",  # Comma style
            "total_type": None,
            "width_mode": "auto"
        },
        "SO Price": {
            "header": "SO Price",
            "align": Alignment(horizontal="right", vertical="center", wrap_text=False),
            "num_format": "#,##0.00",  # Comma style
            "total_type": None,
            "width_mode": "auto"
        },
        "Pos Minimum Price": {
            "header": "Min P",
            "align": Alignment(horizontal="right", vertical="center", wrap_text=False),
            "num_format": "#,##0.00",  # Comma style
            "total_type": None,
            "width_mode": "auto"
        },
        "Quantity On Hand": {
            "header": "QTY",
            "align": Alignment(horizontal="center", vertical="center", wrap_text=False),
            "num_format": "#,##0",
            "total_type": "sum",  # Has total sum
            "width_mode": "auto"
        },
        "Sold": {
            "header": "365\nSold",
            "align": Alignment(horizontal="center", vertical="center", wrap_text=False),
            "num_format": "#,##0",
            "total_type": "sum",  # Has total sum
            "width_mode": "data_len"
        },
        "Vendors": {
            "header": "Vendors",
            "align": Alignment(horizontal="right", vertical="center", wrap_text=False),
            "num_format": "@",
            "total_type": None,
            "width_mode": "data_len_capped"
        },
        "Vendors/Price": {
            "header": "Ven_P",
            "align": Alignment(horizontal="right", vertical="center", wrap_text=False),
            "num_format": "#,##0.00",  # Comma style
            "total_type": None,
            "width_mode": "auto"
        },
        "Vendors/Discount (%)": {
            "header": "Ven_D%",
            "align": Alignment(horizontal="right", vertical="center", wrap_text=False),
            "num_format": "#,##0.00",  # Comma style
            "total_type": None,
            "width_mode": "auto"
        },
        "Vendors/Discounted Price": {
            "header": "VenNet",
            "align": Alignment(horizontal="right", vertical="center", wrap_text=False),
            "num_format": "#,##0.00",  # Comma style
            "total_type": None,
            "width_mode": "auto"
        },
        "Vendors/Last Purchase": {
            "header": "Last Pur",
            "align": Alignment(horizontal="center", vertical="center", wrap_text=False),
            "num_format": "yyyy-mm-dd",  # Short Date
            "total_type": None,
            "width_mode": "auto",
            "is_date": True
        },
        "Vendors/Last Updated on": {
            "header": "LastUpDate",
            "align": Alignment(horizontal="center", vertical="center", wrap_text=False),
            "num_format": "yyyy-mm-dd",  # Short Date
            "total_type": None,
            "width_mode": "auto",
            "is_date": True
        },
        "Last Received Qty": {
            "header": "L_QTY",
            "align": Alignment(horizontal="center", vertical="center", wrap_text=False),
            "num_format": "#,##0",
            "total_type": "sum",
            "width_mode": "auto"
        },
        "حالة الصنف": {
            "header": "حالة الصنف",
            "align": Alignment(horizontal="center", vertical="center", wrap_text=False),
            "num_format": "@",
            "total_type": None,
            "width_mode": "auto"
        },
        "الطلب المقترح (60 يوم)": {
            "header": "الطلب المقترح\n(60 يوم)",
            "align": Alignment(horizontal="center", vertical="center", wrap_text=False),
            "num_format": "#,##0",
            "total_type": "sum",
            "width_mode": "auto"
        },
        "توصيات المناقلة": {
            "header": "توصيات\nالمناقلة",
            "align": Alignment(horizontal="center", vertical="center", wrap_text=False),
            "num_format": "@",
            "total_type": None,
            "width_mode": "data_len_capped"
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

    # ── Identify columns ───────────────────────────────────────────────────
    first_row_sample = export_rows[0] if export_rows else {}
    all_col_keys = list(first_row_sample.keys())

    SH_OH_SUFFIX = " / On Hand"
    SH_SL_SUFFIX = " / Sold"
    SUMMARY_COLS = ["إجمالي رصيد المعارض", "إجمالي مبيعات المعارض", "حالة الصنف", "الطلب المقترح (60 يوم)", "توصيات المناقلة"]

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

    # ── Create workbook ────────────────────────────────────────────────────
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "تفاصيل المنتجات والمعارض"
    ws.views.sheetView[0].rightToLeft = True
    # Freeze only the header rows (first unfrozen row is DATA_START_ROW)
    ws.freeze_panes = f"A{DATA_START_ROW}"

    col_key_to_excel_col = {}
    col_idx = 1

    # 1) Fixed columns
    for k in fixed_col_keys:
        col_key_to_excel_col[k] = col_idx
        spec = COLUMN_SPECS.get(k, {})
        hdr_text = spec.get("header", k)

        cell1 = ws.cell(row=1, column=col_idx, value=hdr_text)
        cell1.fill      = _fill(C_HDR_MAIN)
        cell1.font      = _font(bold=True, color=C_WHITE, size=9)
        cell1.alignment = ALIGN_CTR
        cell1.border    = _border()

        if USE_TWO_ROWS:
            cell2 = ws.cell(row=2, column=col_idx)
            cell2.fill   = _fill(C_HDR_MAIN)
            cell2.border = _border()
            ws.merge_cells(start_row=1, start_column=col_idx, end_row=2, end_column=col_idx)

        col_idx += 1

    # 2) Showroom pairs
    for sh_name, oh_key, sl_key in showroom_pairs:
        pair_cols = [c for c in [oh_key, sl_key] if c]
        pair_count = len(pair_cols)
        sh_start_col = col_idx

        # Row 1: showroom name
        cell_sh = ws.cell(row=1, column=sh_start_col, value=sh_name)
        cell_sh.fill      = _fill(C_HDR_SHOWROOM)
        cell_sh.font      = _font(bold=True, color=C_WHITE, size=9)
        cell_sh.alignment = ALIGN_CTR
        cell_sh.border    = _border()

        if USE_TWO_ROWS and pair_count == 2:
            cell_sh2 = ws.cell(row=1, column=sh_start_col + 1)
            cell_sh2.fill   = _fill(C_HDR_SHOWROOM)
            cell_sh2.border = _border()
            ws.merge_cells(start_row=1, start_column=sh_start_col,
                           end_row=1, end_column=sh_start_col + 1)

        # Row 2 sub-headers
        for sub_key in pair_cols:
            sub_label = "On Hand" if sub_key and sub_key.endswith(SH_OH_SUFFIX) else "Sold"
            col_key_to_excel_col[sub_key] = col_idx

            if USE_TWO_ROWS:
                cell2 = ws.cell(row=2, column=col_idx, value=sub_label)
                cell2.fill      = _fill(C_HDR_SHOWROOM_L)
                cell2.font      = _font(bold=True, color=C_WHITE, size=8)
                cell2.alignment = ALIGN_CTR
                cell2.border    = _border()

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
        elif "حالة" in k:
            label_top = "حالة الصنف"
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
        cell1.fill      = _fill(C_HDR_SUMMARY)
        cell1.font      = _font(bold=True, color=C_WHITE, size=9)
        cell1.alignment = ALIGN_CTR
        cell1.border    = _border()
        if USE_TWO_ROWS:
            cell2 = ws.cell(row=2, column=col_idx)
            cell2.fill   = _fill(C_HDR_SUMMARY)
            cell2.border = _border()
            ws.merge_cells(start_row=1, start_column=col_idx, end_row=2, end_column=col_idx)
        ws.column_dimensions[get_column_letter(col_idx)].width = col_w
        col_idx += 1

    total_excel_cols = col_idx - 1

    ws.row_dimensions[1].height = 28
    if USE_TWO_ROWS:
        ws.row_dimensions[2].height = 20

    # ── Column Widths Calculation ──────────────────────────────────────────
    barcode_col_width = 14
    for k in fixed_col_keys:
        spec = COLUMN_SPECS.get(k, {})
        wmode = spec.get("width_mode", "auto")
        col_letter = get_column_letter(col_key_to_excel_col[k])

        if k == "Barcode":
            data_lens = [len(str(r.get(k) or '')) for r in export_rows]
            max_l = max(data_lens) if data_lens else 10
            barcode_col_width = max(max_l + 3, 13)
            ws.column_dimensions[col_letter].width = barcode_col_width
        elif k == "Product Packages/Barcode":
            ws.column_dimensions[col_letter].width = barcode_col_width
        elif k == "Internal Reference":
            data_lens = [len(str(r.get(k) or '')) for r in export_rows]
            max_l = max(data_lens) if data_lens else 10
            ws.column_dimensions[col_letter].width = max(max_l + 3, 11)
        elif wmode == "data_len":
            data_lens = [len(str(r.get(k) or '')) for r in export_rows]
            max_l = max(data_lens) if data_lens else 8
            ws.column_dimensions[col_letter].width = max(max_l + 3, 10)
        elif wmode == "data_len_capped":
            data_lens = [len(str(r.get(k) or '')) for r in export_rows]
            max_l = max(data_lens) if data_lens else 15
            ws.column_dimensions[col_letter].width = min(max(max_l + 3, 15), 45)
        else:
            hdr_text = spec.get("header", k)
            max_line = max([len(line) for line in hdr_text.split('\n')]) if hdr_text else len(k)
            ws.column_dimensions[col_letter].width = max(max_line + 3, 10)

    # ── Write Data Rows ────────────────────────────────────────────────────
    for data_row_idx, row_data in enumerate(export_rows):
        excel_row = DATA_START_ROW + data_row_idx
        is_alt = (data_row_idx % 2 == 1)

        for k, ec in col_key_to_excel_col.items():
            spec = COLUMN_SPECS.get(k, {})
            is_date = spec.get("is_date", False)
            raw_val = row_data.get(k, "")
            val = _parse_cell_value(raw_val, is_date=is_date)

            cell = ws.cell(row=excel_row, column=ec, value=val)
            cell.border = _border()
            if is_alt:
                cell.fill = _fill(C_ALT)

            # Alignment & Number format & Status styling
            align = spec.get("align", ALIGN_CTR)
            cell.alignment = align

            if k == "حالة الصنف":
                if val == "نفد المخزون":
                    cell.font = _font(bold=True, color="C00000", size=9)
                elif val == "قارب على النفاذ":
                    cell.font = _font(bold=True, color="ED7D31", size=9)
                elif val == "سريع الحركة":
                    cell.font = _font(bold=True, color="385723", size=9)
                elif val == "راكد":
                    cell.font = _font(bold=True, color="7030A0", size=9)
                elif val == "فائض المخزون":
                    cell.font = _font(bold=True, color="2E75B6", size=9)
                else:
                    cell.font = _font(bold=False, color="333333", size=9)
            else:
                cell.font = _font(size=9)

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

        ws.row_dimensions[excel_row].height = 18

    # ── Write Totals Row ───────────────────────────────────────────────────
    n_data = len(export_rows)
    if n_data > 0:
        totals_excel_row = DATA_START_ROW + n_data

        # Determine which text column gets the "▶ الإجماليات" label
        label_col_key = None
        for cand in ["Product Name Arabic", "Name", "Internal Reference"]:
            if cand in col_key_to_excel_col and cand != "Internal Reference":
                label_col_key = cand
                break

        for k, ec in col_key_to_excel_col.items():
            spec = COLUMN_SPECS.get(k, {})
            ttype = spec.get("total_type")

            # Showroom and numeric summary columns sum
            if k.endswith(SH_OH_SUFFIX) or k.endswith(SH_SL_SUFFIX) or k in {"إجمالي رصيد المعارض", "إجمالي مبيعات المعارض", "الطلب المقترح (60 يوم)"}:
                ttype = "sum"

            cell = ws.cell(row=totals_excel_row, column=ec)
            cell.fill   = _fill(C_TOTALS_BG)
            cell.font   = _font(bold=True, color=C_TOTALS_FG, size=9)
            cell.border = _border(C_TOTALS_FG)

            if ttype == "count":
                cell.value = n_data
                cell.alignment = spec.get("align", ALIGN_CTR)
                cell.number_format = '#,##0'
            elif ttype == "sum":
                col_sum = sum(float(r.get(k) or 0) for r in export_rows
                              if isinstance(r.get(k), (int, float)))
                cell.value = col_sum
                cell.alignment = spec.get("align", ALIGN_CTR)
                if isinstance(col_sum, float) and col_sum != int(col_sum):
                    cell.number_format = '#,##0.00'
                else:
                    cell.number_format = '#,##0'
            elif k == label_col_key:
                cell.value = "▶ الإجماليات"
                cell.alignment = spec.get("align", ALIGN_CTR)
            else:
                cell.value = None
                cell.alignment = ALIGN_CTR

        ws.row_dimensions[totals_excel_row].height = 22

    # ── Branch summary sheet ───────────────────────────────────────────────
    ws2 = wb.create_sheet("مقارنة وتحليل المعارض")
    ws2.views.sheetView[0].rightToLeft = True
    ws2.freeze_panes = "A2"

    branch_rows = []
    total_sales_all = sum(b['total_sold_units'] for b in branch_summary.values()) or 1.0
    for s_id, b in sorted(branch_summary.items(), key=lambda x: x[1]['total_sold_units'], reverse=True):
        brow = {"كود المعرض": b['code'], "اسم المعرض": b['name']}
        if permissions.get("Showrooms_OnHand", True):
            brow["إجمالي كمية المخزون (On Hand)"] = b['total_on_hand']
        if permissions.get("Cost", True) and permissions.get("Showrooms_OnHand", True):
            brow["قيمة المخزون بالتكلفة"] = round(b['total_cost_value'], 2)
        if permissions.get("Sales Price", True) and permissions.get("Showrooms_OnHand", True):
            brow["قيمة المخزون بسعر البيع"] = round(b['total_sales_value'], 2)
        if permissions.get("Showrooms_Sold", True):
            brow["إجمالي المبيعات (Sold)"] = b['total_sold_units']
            brow["نسبة المساهمة (%)"] = round((b['total_sold_units'] / total_sales_all) * 100, 2)
        branch_rows.append(brow)

    if branch_rows:
        br_cols = list(branch_rows[0].keys())
        for ci, col_name in enumerate(br_cols, 1):
            c = ws2.cell(row=1, column=ci, value=col_name)
            c.fill = _fill(C_HDR_MAIN); c.font = _font(bold=True, color=C_WHITE, size=10)
            c.alignment = ALIGN_CTR; c.border = _border()
            ws2.column_dimensions[get_column_letter(ci)].width = max(len(col_name) + 2, 14)
        ws2.row_dimensions[1].height = 28

        for ri, brow in enumerate(branch_rows, 2):
            is_alt = (ri % 2 == 0)
            for ci, col_name in enumerate(br_cols, 1):
                val = brow.get(col_name, "")
                c = ws2.cell(row=ri, column=ci, value=val if val != "" else None)
                c.border = _border()
                c.font = _font(size=10)
                if is_alt:
                    c.fill = _fill(C_ALT)
                c.alignment = ALIGN_CTR if isinstance(val, (int, float)) else ALIGN_RT
                if isinstance(val, (int, float)):
                    c.number_format = '#,##0.00' if isinstance(val, float) and val != int(val) else '#,##0'
            ws2.row_dimensions[ri].height = 18

        br_totals_row = len(branch_rows) + 2
        for ci, col_name in enumerate(br_cols, 1):
            if col_name in {"كود المعرض", "اسم المعرض"}:
                val = "▶ الإجماليات" if ci == 2 else "─"
            elif col_name == "نسبة المساهمة (%)":
                val = 100.0
            else:
                val = sum(r.get(col_name, 0) for r in branch_rows if isinstance(r.get(col_name), (int, float)))
            c = ws2.cell(row=br_totals_row, column=ci, value=val)
            c.fill = _fill(C_TOTALS_BG); c.font = _font(bold=True, color=C_TOTALS_FG, size=10)
            c.alignment = ALIGN_CTR; c.border = _border(C_TOTALS_FG)
            if isinstance(val, (int, float)):
                c.number_format = '#,##0.00' if isinstance(val, float) and val != int(val) else '#,##0'
        ws2.row_dimensions[br_totals_row].height = 22

    wb.save(output_path)

    total_time = round(time.time() - t_start, 2)
    notify(100, f"✅ اكتمل التصدير في {total_time} ثانية!")

    return {
        'output_path':    output_path,
        'total_rows':     len(export_rows),
        'total_columns':  total_excel_cols,
        'total_branches': len(branch_rows),
        'total_time':     total_time
    }


if __name__ == "__main__":
    r = generate_report()
    print("Result:", r)

