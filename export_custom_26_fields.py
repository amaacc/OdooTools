import os
import sys
import json
import time
import re
import xmlrpc.client
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

def parse_vendor_info(raw_partner_str):
    if not raw_partner_str:
        return "", ""
    s = str(raw_partner_str).strip()
    m = re.match(r"^\[(.*?)\]\s*(.*)$", s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", s

def safe_execute_kw(models, db, uid, password, obj, method, args, kw=None, max_retries=5):
    if kw is None:
        kw = {}
    for attempt in range(1, max_retries + 1):
        try:
            return models.execute_kw(db, uid, password, obj, method, args, kw)
        except Exception as e:
            if attempt == max_retries:
                raise
            wait_time = attempt * 3
            print(f"Warning: Retry {attempt}/{max_retries} for {obj}.{method}: {e}. Waiting {wait_time}s...", flush=True)
            time.sleep(wait_time)

def run_export():
    config_path = r"c:\OdooDB\odoo_sync_config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    url = os.environ.get("ODOO_URL") or config.get("odoo_url")
    db = os.environ.get("ODOO_DB") or config.get("odoo_db")
    username = os.environ.get("ODOO_EMAIL") or config.get("odoo_email")
    password = os.environ.get("ODOO_PASSWORD") or config.get("default_password")

    t_total = time.time()

    print("==================================================", flush=True)
    print(" Exporting Storable POS Products with Showrooms  ", flush=True)
    print("==================================================", flush=True)

    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, username, password, {})
    if not uid:
        print("ERROR: Authentication failed!", flush=True)
        sys.exit(1)

    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

    # ─── STEP 1: Fetch filtered product IDs ──────────────────────────────────
    print("\nStep 1/6: Searching matching products (5 active filters)...", flush=True)
    t0 = time.time()
    domain = [
        ['active', '=', True],
        ['available_in_pos', '=', True],
        ['purchase_ok', '=', True],
        ['sale_ok', '=', True],
        ['detailed_type', '=', 'product']  # Storable products only
    ]
    product_ids = safe_execute_kw(models, db, uid, password, 'product.product', 'search', [domain])
    total_found = len(product_ids)
    print(f"Found {total_found} matching products in {round(time.time()-t0, 2)}s", flush=True)

    # ─── STEP 2: Fetch lookup maps (Taxes, Tags, Packaging, Pricelist) ───────
    print("\nStep 2/6: Fetching lookup maps (Taxes, Tags, Packaging, Shati Price)...", flush=True)
    t0 = time.time()

    taxes = safe_execute_kw(models, db, uid, password, 'account.tax', 'search_read', [[]], {'fields': ['id', 'name']})
    tax_map = {t['id']: t['name'] for t in taxes}

    tags = safe_execute_kw(models, db, uid, password, 'product.tag', 'search_read', [[]], {'fields': ['id', 'name']})
    tag_map = {t['id']: t['name'] for t in tags}

    # Packaging barcodes for filtered products
    pkgs = safe_execute_kw(
        models, db, uid, password, 'product.packaging', 'search_read',
        [[['product_id', 'in', product_ids], ['barcode', '!=', False]]],
        {'fields': ['product_id', 'barcode']}
    )
    pkg_map = {}
    for p in pkgs:
        pid = p['product_id'][0] if p.get('product_id') else None
        if pid:
            pkg_map.setdefault(pid, []).append(p['barcode'])

    # Shati Pricelist
    now_dt = datetime.now()
    shati_pl = safe_execute_kw(
        models, db, uid, password, 'product.pricelist', 'search_read',
        [[['name', '=', 'سعر الشاطئ']]],
        {'fields': ['id', 'name']}
    )
    shati_pl_id = shati_pl[0]['id'] if shati_pl else 28

    shati_items = safe_execute_kw(
        models, db, uid, password, 'product.pricelist.item', 'search_read',
        [[['pricelist_id', '=', shati_pl_id]]],
        {'fields': ['applied_on', 'compute_price', 'fixed_price', 'percent_price',
                   'product_tmpl_id', 'product_id', 'product_tag_ids', 'date_start', 'date_end']}
    )

    shati_variant_map = {}
    shati_tmpl_map = {}
    shati_tag_rules = []

    for it in shati_items:
        d_start = datetime.strptime(it['date_start'], '%Y-%m-%d %H:%M:%S') if it.get('date_start') else None
        d_end = datetime.strptime(it['date_end'], '%Y-%m-%d %H:%M:%S') if it.get('date_end') else None
        if d_start and now_dt < d_start:
            continue
        if d_end and now_dt > d_end:
            continue

        if it['applied_on'] == '0_product_variant' and it['product_id']:
            shati_variant_map[it['product_id'][0]] = float(it['fixed_price'])
        elif it['applied_on'] == '1_product' and it['product_tmpl_id']:
            shati_tmpl_map[it['product_tmpl_id'][0]] = float(it['fixed_price'])
        elif it['applied_on'] == '1_product_tag' and it['product_tag_ids']:
            for tag_id in it['product_tag_ids']:
                shati_tag_rules.append({
                    'tag_id': tag_id,
                    'compute_price': it['compute_price'],
                    'percent_price': float(it['percent_price']),
                    'fixed_price': float(it['fixed_price'])
                })

    print(f"Lookup maps & Shati Pricelist loaded in {round(time.time()-t0, 2)}s", flush=True)

    # ─── STEP 3: Setup Showrooms, Stock Quants, & Showroom Sales ─────────────
    print("\nStep 3/6: Fetching Showrooms list, Stock quants & POS Sales per showroom...", flush=True)
    t0 = time.time()

    # Discover active POS configurations & Showrooms
    pos_configs = safe_execute_kw(
        models, db, uid, password, 'pos.config', 'search_read',
        [[['active', '=', True]]],
        {'fields': ['id', 'name', 'picking_type_id']}
    )
    pts = safe_execute_kw(
        models, db, uid, password, 'stock.picking.type', 'read',
        [[c['picking_type_id'][0] for c in pos_configs if c.get('picking_type_id')]],
        {'fields': ['id', 'warehouse_id', 'default_location_src_id']}
    )
    pt_map = {t['id']: t for t in pts}

    wh_ids = list(set([pt_map[c['picking_type_id'][0]]['warehouse_id'][0] for c in pos_configs if c.get('picking_type_id') and pt_map.get(c['picking_type_id'][0], {}).get('warehouse_id')]))
    whs = safe_execute_kw(
        models, db, uid, password, 'stock.warehouse', 'read',
        [wh_ids],
        {'fields': ['id', 'name', 'code', 'lot_stock_id']}
    )

    showrooms = []
    for w in sorted(whs, key=lambda x: (x.get('code') or '', x.get('id'))):
        wid = w['id']
        cfg_ids = [c['id'] for c in pos_configs if c.get('picking_type_id') and pt_map.get(c['picking_type_id'][0], {}).get('warehouse_id') and pt_map[c['picking_type_id'][0]]['warehouse_id'][0] == wid]
        showrooms.append({
            'id': wid,
            'name': w['name'],
            'code': w.get('code') or '',
            'lot_stock_id': w['lot_stock_id'][0] if w.get('lot_stock_id') else None,
            'pos_config_ids': cfg_ids
        })

    print(f"Found {len(showrooms)} active showrooms with POS configs.", flush=True)

    # Fetch Stock Quants in bulk
    quants = safe_execute_kw(
        models, db, uid, password, 'stock.quant', 'search_read',
        [[['location_id.usage', '=', 'internal'], ['quantity', '!=', 0]]],
        {'fields': ['product_id', 'location_id', 'quantity']}
    )
    stock_map = {}
    for q in quants:
        if q.get('product_id') and q.get('location_id'):
            stock_map[(q['product_id'][0], q['location_id'][0])] = float(q.get('quantity') or 0.0)

    print(f"Stock map ready with {len(stock_map)} location-product entries.", flush=True)

    # Fetch POS Sales per showroom in parallel
    def fetch_showroom_sales(s):
        models_t = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        domain_s = [
            ['state', 'in', ['paid', 'done', 'invoiced']],
            ['config_id', 'in', s['pos_config_ids']]
        ]
        res = models_t.execute_kw(
            db, uid, password,
            'report.pos.order', 'read_group',
            [domain_s, ['product_id', 'product_qty:sum'], ['product_id']],
            {'lazy': False}
        )
        s_map = {}
        for r in res:
            if r.get('product_id'):
                s_map[r['product_id'][0]] = float(r.get('product_qty') or 0.0)
        return s['id'], s_map

    with ThreadPoolExecutor(max_workers=8) as executor:
        sales_results = list(executor.map(fetch_showroom_sales, showrooms))
    showroom_sales = dict(sales_results)

    print(f"Showroom stocks & sales ready in {round(time.time()-t0, 2)}s", flush=True)

    # ─── STEP 4: Fetch Vendor Info & Last Received Qty ────────────────────────
    print("\nStep 4/6: Fetching Vendor info & Last Received Qty...", flush=True)
    t0 = time.time()

    # Template IDs mapping
    tmpl_records = safe_execute_kw(
        models, db, uid, password, 'product.product', 'read',
        [product_ids],
        {'fields': ['id', 'product_tmpl_id']}
    )
    prod_to_tmpl = {}
    tmpl_ids = []
    for r in tmpl_records:
        pid = r['id']
        tid = r['product_tmpl_id'][0] if isinstance(r.get('product_tmpl_id'), (list, tuple)) else r.get('product_tmpl_id')
        prod_to_tmpl[pid] = tid
        if tid not in tmpl_ids:
            tmpl_ids.append(tid)

    # Vendor Info (product.supplierinfo)
    supplier_ids = safe_execute_kw(
        models, db, uid, password, 'product.supplierinfo', 'search',
        [[['product_tmpl_id', 'in', tmpl_ids]]],
        {'order': 'last_purchase_date desc, write_date desc, id desc'}
    )
    print(f"Found {len(supplier_ids)} supplier records.", flush=True)

    vendor_tmpl_map = {}
    sup_batch_size = 10000
    for j in range(0, len(supplier_ids), sup_batch_size):
        sup_chunk = supplier_ids[j:j + sup_batch_size]
        suppliers = safe_execute_kw(
            models, db, uid, password, 'product.supplierinfo', 'read',
            [sup_chunk],
            {'fields': ['product_tmpl_id', 'partner_id', 'price', 'discount', 'price_discounted', 'last_purchase_date', 'write_date']}
        )
        for s in suppliers:
            if not s.get('product_tmpl_id'):
                continue
            tid = s['product_tmpl_id'][0] if isinstance(s['product_tmpl_id'], (list, tuple)) else s['product_tmpl_id']
            p_val = float(s.get('price') or 0.0)
            dp_val = float(s.get('price_discounted') or 0.0)
            if (p_val > 0 or dp_val > 0) and tid not in vendor_tmpl_map:
                raw_p_name = s['partner_id'][1] if s.get('partner_id') else ''
                v_code, v_name = parse_vendor_info(raw_p_name)
                vendor_tmpl_map[tid] = {
                    'vendor_code': v_code,
                    'vendor_name': v_name,
                    'vendor_price': p_val,
                    'vendor_discount': float(s.get('discount') or 0.0),
                    'vendor_discounted_price': dp_val,
                    'vendor_last_purchase': str(s.get('last_purchase_date') or ''),
                    'vendor_last_updated': str(s.get('write_date') or '')
                }
        for s in suppliers:
            if not s.get('product_tmpl_id'):
                continue
            tid = s['product_tmpl_id'][0] if isinstance(s['product_tmpl_id'], (list, tuple)) else s['product_tmpl_id']
            if tid not in vendor_tmpl_map:
                raw_p_name = s['partner_id'][1] if s.get('partner_id') else ''
                v_code, v_name = parse_vendor_info(raw_p_name)
                vendor_tmpl_map[tid] = {
                    'vendor_code': v_code,
                    'vendor_name': v_name,
                    'vendor_price': float(s.get('price') or 0.0),
                    'vendor_discount': float(s.get('discount') or 0.0),
                    'vendor_discounted_price': float(s.get('price_discounted') or 0.0),
                    'vendor_last_purchase': str(s.get('last_purchase_date') or ''),
                    'vendor_last_updated': str(s.get('write_date') or '')
                }

    # Live Purchase Orders with value > 0 (excluding 0 / bonus)
    all_po_line_ids = safe_execute_kw(
        models, db, uid, password, 'purchase.order.line', 'search',
        [[['product_id', 'in', product_ids],
          ['order_id.state', 'in', ['purchase', 'done']],
          ['price_unit', '>', 0]]],
        {'order': 'date_approve desc, date_order desc, id desc'}
    )
    po_vendor_map = {}
    last_received_map = {}
    po_batch = 5000
    for j in range(0, len(all_po_line_ids), po_batch):
        po_chunk = all_po_line_ids[j:j + po_batch]
        po_lines = safe_execute_kw(
            models, db, uid, password, 'purchase.order.line', 'read',
            [po_chunk],
            {'fields': ['product_id', 'partner_id', 'price_unit', 'discount', 'date_approve', 'date_order', 'product_qty', 'qty_received']}
        )
        for line in po_lines:
            if not line.get('product_id'):
                continue
            pid = line['product_id'][0]
            if pid not in po_vendor_map:
                p_unit = float(line.get('price_unit') or 0.0)
                disc = float(line.get('discount') or 0.0)
                disc_p = round(p_unit * (1.0 - (disc / 100.0)), 4)
                dt = str(line.get('date_approve') or line.get('date_order') or '')
                raw_p_name = line['partner_id'][1] if line.get('partner_id') else ''
                v_code, v_name = parse_vendor_info(raw_p_name)
                qty_rcv = float(line.get('qty_received') or line.get('product_qty') or 0.0)
                po_vendor_map[pid] = {
                    'vendor_code': v_code,
                    'vendor_name': v_name,
                    'vendor_price': p_unit,
                    'vendor_discount': disc,
                    'vendor_discounted_price': disc_p,
                    'vendor_last_purchase': dt[:10] if dt else '',
                    'vendor_last_updated': dt[:10] if dt else '',
                    'last_received_qty': qty_rcv
                }
                last_received_map[pid] = qty_rcv

    print(f"Vendor & Purchase data ready in {round(time.time()-t0, 2)}s", flush=True)

    # ─── STEP 5: Fetch product records in batches & assemble rows ────────────
    print("\nStep 5/6: Fetching product data in batches...", flush=True)
    t0 = time.time()

    fields_to_read = [
        'id', 'product_tmpl_id', 'default_code', 'barcode', 'name', 'product_name_arabic',
        'standard_price', 'list_price', 'sales_price', 'pos_min_price', 'qty_available',
        'sales_count', 'product_tag_ids', 'x_studio_concatenated_tags',
        'uom_id', 'taxes_id', 'supplier_taxes_id'
    ]

    def parse_many2one(val):
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            return val[0], str(val[1])
        elif isinstance(val, (list, tuple)) and len(val) == 1:
            return val[0], ""
        elif isinstance(val, int):
            return val, ""
        return None, ""

    batch_size = 2000
    export_rows = []

    for i in range(0, total_found, batch_size):
        chunk_ids = product_ids[i:i + batch_size]
        chunk_num = (i // batch_size) + 1
        total_chunks = (total_found + batch_size - 1) // batch_size
        print(f"  Batch {chunk_num}/{total_chunks} ({len(chunk_ids)} records)...", flush=True)

        records = safe_execute_kw(
            models, db, uid, password, 'product.product', 'read',
            [chunk_ids],
            {'fields': fields_to_read}
        )

        for r in records:
            pid = r['id']
            tid = prod_to_tmpl.get(pid, 0)
            uom_id, uom_name = parse_many2one(r.get('uom_id'))

            cust_taxes = ", ".join([tax_map.get(t_id, str(t_id)) for t_id in (r.get('taxes_id') or [])])
            vend_taxes = ", ".join([tax_map.get(t_id, str(t_id)) for t_id in (r.get('supplier_taxes_id') or [])])
            pkg_barcodes = ", ".join(pkg_map.get(pid, []))

            tags_str = ", ".join([tag_map.get(t_id, str(t_id)) for t_id in (r.get('product_tag_ids') or [])])
            if not tags_str and r.get('x_studio_concatenated_tags'):
                tags_str = str(r.get('x_studio_concatenated_tags'))

            vinfo = po_vendor_map.get(pid) or vendor_tmpl_map.get(tid, {})
            sales_price = float(r.get('list_price') or 0.0)

            # Compute Shati Price
            shati_price = None
            if pid in shati_variant_map:
                shati_price = shati_variant_map[pid]
            elif tid in shati_tmpl_map:
                shati_price = shati_tmpl_map[tid]
            else:
                prod_tags = r.get('product_tag_ids') or []
                for tr in shati_tag_rules:
                    if tr['tag_id'] in prod_tags:
                        if tr['compute_price'] == 'percentage':
                            shati_price = round(sales_price * (1 - tr['percent_price'] / 100.0), 2)
                        elif tr['compute_price'] == 'fixed':
                            shati_price = tr['fixed_price']
                        break

            if shati_price is None or shati_price <= 0:
                shati_price = sales_price

            row = {
                "Internal Reference": r.get('default_code') or '',
                "Barcode": r.get('barcode') or '',
                "Product Packages/Barcode": pkg_barcodes,
                "Name": r.get('name') or '',
                "Product Name Arabic": r.get('product_name_arabic') or '',
                "Cost": float(r.get('standard_price') or 0.0),
                "Sales Price": sales_price,
                "Shati Price": float(shati_price),
                "SO Price": float(r.get('sales_price') or 0.0),
                "Pos Minimum Price": float(r.get('pos_min_price') or 0.0),
                "Quantity On Hand": float(r.get('qty_available') or 0.0),
                "Sold": float(r.get('sales_count') or 0.0),
                "Products/Tags": tags_str,
                "Products/Unit of Measure": uom_name,
                "Products/Customer Taxes": cust_taxes,
                "Products/Vendor Taxes": vend_taxes,
                "Vendor Code": vinfo.get('vendor_code', ''),
                "Vendor Name": vinfo.get('vendor_name', ''),
                "Vendors/Price": vinfo.get('vendor_price', 0.0),
                "Vendors/Discount (%)": round(float(vinfo.get('vendor_discount') or 0.0) / 100.0, 4),
                "Vendors/Discounted Price": vinfo.get('vendor_discounted_price', 0.0),
                "Vendors/Last Purchase": vinfo.get('vendor_last_purchase', ''),
                "Vendors/Last Updated on": vinfo.get('vendor_last_updated', ''),
                "Last Received Qty": last_received_map.get(pid, 0.0)
            }

            # Add Showroom On Hand & Sold columns sequentially
            for s in showrooms:
                s_name = s['name']
                lot_id = s['lot_stock_id']
                sh_id = s['id']

                on_hand = stock_map.get((pid, lot_id), 0.0)
                sold_qty = showroom_sales.get(sh_id, {}).get(pid, 0.0)

                row[f"{s_name} / On Hand"] = on_hand
                row[f"{s_name} / Sold"] = sold_qty

            export_rows.append(row)

    print(f"All batches processed in {round(time.time()-t0, 2)}s", flush=True)

    # ─── STEP 6: Export to Excel ONLY (No CSV) ───────────────────────────────
    print("\nStep 6/6: Saving Excel file...", flush=True)
    t0 = time.time()

    df = pd.DataFrame(export_rows)
    export_dir = r"c:\OdooDB\exports"
    os.makedirs(export_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_path = os.path.join(export_dir, "odoo_products_26_fields.xlsx")

    try:
        test_open = open(excel_path, 'a')
        test_open.close()
    except PermissionError:
        print(f"  Note: Excel file is open/locked, saving as timestamped version.", flush=True)
        excel_path = os.path.join(export_dir, f"odoo_products_26_fields_{timestamp}.xlsx")

    df.to_excel(excel_path, index=False, engine='openpyxl')
    print(f"  Excel saved in {round(time.time()-t0, 2)}s", flush=True)

    print("\n==================================================", flush=True)
    print("             EXPORT SUCCESSFUL!                   ", flush=True)
    print("==================================================", flush=True)
    print(f"Excel File   : {excel_path}", flush=True)
    print(f"Total Rows   : {len(df)}", flush=True)
    print(f"Total Columns: {len(df.columns)}", flush=True)
    print(f"Total Time   : {round(time.time()-t_total, 2)} seconds", flush=True)
    print("==================================================", flush=True)

if __name__ == "__main__":
    run_export()
