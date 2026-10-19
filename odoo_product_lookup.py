"""
odoo_product_lookup.py — Fast Targeted Product & Pricing Lookup for Odoo
Designed by: عبدالله الخطيب (Abdullah Al-Khatib)
Part of: Odoo Price Comparator & Competitor Intelligence Suite
"""

import xmlrpc.client
import time
from security import get_odoo_credentials


def get_odoo_connection():
    """Establish and return xmlrpc connection objects (models, db, uid, password)."""
    url, db, username, password = get_odoo_credentials()
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, username, password, {})
    if not uid:
        raise ConnectionError("فشل تسجيل الدخول إلى نظام Odoo، يرجى التحقق من بيانات الاتصال.")
    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
    return models, db, uid, password


def lookup_product_by_barcode_or_code(query_term):
    """
    Search Odoo for a single product by:
    1. Primary barcode (product.product.barcode)
    2. Packaging barcode (product.packaging.barcode)
    3. Internal reference (product.product.default_code)
    4. Fuzzy/partial barcode or code match

    Returns detailed dictionary with:
    - Internal reference & barcodes (primary + packaging)
    - Arabic and English names
    - Standard cost & retail list price
    - Net last purchase price after discount from purchase.order.line
    - Last vendor name & purchase date
    - On-hand stock quantity
    """
    q = str(query_term or '').strip()
    if not q:
        return {'success': False, 'error': 'يرجى إدخال أو مسح الباركود أولاً.'}

    models, db, uid, password = get_odoo_connection()

    prod_id = None
    matched_by = "barcode"

    def _safe_execute_kw(model, method, args, kwargs=None, retries=2):
        for attempt in range(retries + 1):
            try:
                return models.execute_kw(db, uid, password, model, method, args, kwargs or {})
            except Exception as exc:
                if attempt == retries:
                    raise exc
                time.sleep(0.6)

    # 1. Search primary barcode
    try:
        p_ids = _safe_execute_kw('product.product', 'search', [[['barcode', '=', q]]], {'limit': 1})
        if p_ids:
            prod_id = p_ids[0]
            matched_by = "باركود أساسي"
    except Exception:
        pass

    # 2. Search packaging barcodes if not found
    if not prod_id:
        try:
            pkg_ids = _safe_execute_kw('product.packaging', 'search_read',
                                       [[['barcode', '=', q]]],
                                       {'fields': ['product_id', 'barcode', 'name', 'qty'], 'limit': 1})
            if pkg_ids and pkg_ids[0].get('product_id'):
                p_item = pkg_ids[0]['product_id']
                prod_id = p_item[0] if isinstance(p_item, (list, tuple)) else p_item
                matched_by = f"باركود تعبئة ({pkg_ids[0].get('name') or 'عبوة'})"
        except Exception:
            pass

    # 3. Search internal reference (default_code) if not found
    if not prod_id:
        try:
            p_ids = _safe_execute_kw('product.product', 'search',
                                     [[['default_code', '=', q]]], {'limit': 1})
            if p_ids:
                prod_id = p_ids[0]
                matched_by = "كود الصنف الداخلي"
        except Exception:
            pass

    # 4. Partial / ILIKE search as fallback
    if not prod_id:
        try:
            p_ids = _safe_execute_kw('product.product', 'search',
                                     [['|', ['barcode', 'ilike', q], ['default_code', 'ilike', q]]],
                                     {'limit': 1})
            if p_ids:
                prod_id = p_ids[0]
                matched_by = "مطابقة جزئية"
        except Exception:
            pass

    if not prod_id:
        return {
            'success': False,
            'error': f'لم يتم العثور على أي صنف مطابق للباركود أو الكود: ({q}) في Odoo.'
        }

    # Fetch product details
    fields_to_read = [
        'id', 'product_tmpl_id', 'default_code', 'barcode',
        'name', 'product_name_arabic', 'standard_price', 'list_price',
        'qty_available', 'uom_id', 'taxes_id'
    ]
    p_data_list = []
    try:
        p_data_list = _safe_execute_kw('product.product', 'read',
                                       [[prod_id]], {'fields': fields_to_read})
    except Exception as e:
        return {'success': False, 'error': f'تعذر الاتصال بـ Odoo لقراءة الصنف: {e}'}

    if not p_data_list:
        return {'success': False, 'error': 'تعذر قراءة بيانات الصنف من Odoo.'}

    p = p_data_list[0]
    tmpl_id = p['product_tmpl_id'][0] if p.get('product_tmpl_id') else prod_id

    # Fetch and determine customer tax status (خاضع للضريبة أم معفى)
    is_taxable = False
    tax_rate = 0.0
    tax_name = "معفى من الضريبة (0%)"
    tax_price_include = True
    try:
        tax_ids = p.get('taxes_id') or []
        if tax_ids:
            taxes_data = models.execute_kw(db, uid, password, 'account.tax', 'read',
                                           [tax_ids], {'fields': ['name', 'amount', 'price_include']})
            if taxes_data:
                rates = [float(t.get('amount') or 0.0) for t in taxes_data]
                max_rate = max(rates) if rates else 0.0
                if max_rate > 0:
                    is_taxable = True
                    tax_rate = max_rate
                    tax_name = f"خاضع للضريبة ({max_rate:.0f}% VAT)"
                tax_price_include = taxes_data[0].get('price_include', True)
    except Exception:
        pass

    # Fetch all packaging barcodes for this product
    packaging_barcodes = []
    try:
        pkgs = models.execute_kw(db, uid, password, 'product.packaging', 'search_read',
                                 [[['product_id', '=', prod_id], ['barcode', '!=', False]]],
                                 {'fields': ['name', 'barcode', 'qty']})
        for pkg in pkgs:
            packaging_barcodes.append({
                'name': pkg.get('name') or '',
                'barcode': str(pkg.get('barcode') or ''),
                'qty': float(pkg.get('qty') or 1.0)
            })
    except Exception:
        pass

    # Fetch last purchase order line (Purchase Order Line)
    vendor_name = ""
    vendor_code = ""
    last_unit_price = 0.0
    last_discount = 0.0
    net_last_purchase_price = 0.0
    last_purchase_date = ""
    last_received_qty = 0.0

    try:
        po_lines = models.execute_kw(db, uid, password, 'purchase.order.line', 'search_read',
                                     [[['product_id', '=', prod_id],
                                       ['state', 'in', ['purchase', 'done']],
                                       ['price_unit', '>', 0]]],
                                     {'fields': ['order_id', 'partner_id', 'price_unit', 'discount',
                                                 'date_approve', 'date_order', 'qty_received', 'product_qty'],
                                      'order': 'date_approve desc, date_order desc, id desc',
                                      'limit': 1})
        if po_lines:
            line = po_lines[0]
            partner = line.get('partner_id')
            if partner and isinstance(partner, (list, tuple)):
                vendor_name = partner[1]
                vendor_code = str(partner[0])
            last_unit_price = float(line.get('price_unit') or 0.0)
            last_discount = float(line.get('discount') or 0.0)
            net_last_purchase_price = round(last_unit_price * (1.0 - (last_discount / 100.0)), 4)
            dt_raw = str(line.get('date_approve') or line.get('date_order') or '')
            last_purchase_date = dt_raw[:10] if dt_raw else ''
            last_received_qty = float(line.get('qty_received') or line.get('product_qty') or 0.0)
    except Exception:
        pass

    # Fallback to product.supplierinfo if no PO line found
    if not vendor_name:
        try:
            sups = models.execute_kw(db, uid, password, 'product.supplierinfo', 'search_read',
                                     [[['product_tmpl_id', '=', tmpl_id]]],
                                     {'fields': ['partner_id', 'price', 'discount', 'price_discounted',
                                                 'last_purchase_date', 'write_date'],
                                      'order': 'last_purchase_date desc, write_date desc, id desc',
                                      'limit': 1})
            if sups:
                sup = sups[0]
                partner = sup.get('partner_id')
                if partner and isinstance(partner, (list, tuple)):
                    vendor_name = partner[1]
                    vendor_code = str(partner[0])
                p_val = float(sup.get('price') or 0.0)
                dp_val = float(sup.get('price_discounted') or 0.0)
                d_val = float(sup.get('discount') or 0.0)
                last_unit_price = p_val
                last_discount = d_val
                if dp_val > 0:
                    net_last_purchase_price = dp_val
                elif p_val > 0:
                    net_last_purchase_price = round(p_val * (1.0 - (d_val / 100.0)), 4)
                dt_raw = str(sup.get('last_purchase_date') or sup.get('write_date') or '')
                last_purchase_date = dt_raw[:10] if dt_raw else ''
        except Exception:
            pass

    # Clean names
    name_en = str(p.get('name') or '').strip()
    name_ar = str(p.get('product_name_arabic') or '').strip()
    primary_bc = str(p.get('barcode') or '').strip()
    default_code = str(p.get('default_code') or '').strip()

    def _is_gtin(b):
        s = str(b or '').strip()
        return s.isdigit() and len(s) in (8, 12, 13, 14)

    all_barcodes = []
    if primary_bc and _is_gtin(primary_bc):
        all_barcodes.append(primary_bc)
    elif primary_bc:
        # Fallback if primary is non-standard but primary
        all_barcodes.append(primary_bc)

    for pkg in packaging_barcodes:
        bc_val = str(pkg.get('barcode') or '').strip()
        if _is_gtin(bc_val) and bc_val not in all_barcodes:
            all_barcodes.append(bc_val)

    uom_name = p['uom_id'][1] if p.get('uom_id') and isinstance(p['uom_id'], (list, tuple)) else 'حبة'

    return {
        'success': True,
        'matched_by': matched_by,
        'id': prod_id,
        'tmpl_id': tmpl_id,
        'default_code': default_code,
        'primary_barcode': primary_bc,
        'packaging_barcodes': packaging_barcodes,
        'all_barcodes': all_barcodes,
        'name_en': name_en,
        'name_ar': name_ar,
        'cost_price': float(p.get('standard_price') or 0.0),
        'retail_price': float(p.get('list_price') or 0.0),
        'qty_available': float(p.get('qty_available') or 0.0),
        'uom_name': uom_name,
        'vendor_name': vendor_name,
        'vendor_code': vendor_code,
        'last_purchase_unit_price': last_unit_price,
        'last_purchase_discount': last_discount,
        'net_last_purchase_price': net_last_purchase_price,
        'last_purchase_date': last_purchase_date,
        'last_received_qty': last_received_qty,
        'is_taxable': is_taxable,
        'tax_rate': tax_rate,
        'tax_name': tax_name,
        'tax_price_include': tax_price_include,
    }
