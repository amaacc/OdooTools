"""
purchase_report_engine.py — Intelligent Procurement, Replenishment & Vendor Analytics Engine for Odoo
Designed & Developed by: عبدالله الخطيب (Abdullah Al-Khatib)

Provides a comprehensive 6-in-1 Purchasing & Supply Chain Suite inside OdooReportExporter:
  1. 📊 لوحة قيادة المشتريات (Executive Procurement KPI Dashboard)
  2. 🛒 ما يجب شراؤه - خطة الاحتياج والتوريد الذكي (Smart Replenishment Plan with Live Excel Formulas)
  3. 🧾 ما تم شراؤه - سجل المشتريات والاستلامات الفعلي (Historical Purchases, Receiving & Bonus Audit)
  4. 🤝 تقييم وأداء الموردين (Vendor Performance Scorecard, Fill Rate % & Spend Share)
  5. 📈 رقابة تغير أسعار الشراء (Purchase Price Variance, Cost Creep & Margin Erosion Alerts)
  6. 🚚 طلبيات مفتوحة بالطريق (Open POs & Pending Backorders Follow-up Tracker)
  7. 📄 طلب شراء رسمي معتمد (Official Print-Ready RFQ/PO Sheet + On-Demand PDF Export)
"""

import os
import time
import xmlrpc.client
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import DataBarRule
from openpyxl.drawing.image import Image as OpenpyxlImage

from security import get_odoo_credentials
from permissions import load_permissions
from company_profile import load_company_profile, get_default_logo_path
from exporter_engine import (
    get_active_showrooms,
    get_all_warehouses,
    safe_execute_kw,
    match_wildcards,
    parse_tokens,
    _resolve_matched_vendor_ids,
)


def get_all_vendors():
    """
    Returns a sorted list of distinct active vendors [{'id': id, 'name': name}]
    from confirmed purchase orders and product supplierinfo records in Odoo.
    """
    creds = get_odoo_credentials()
    if not creds:
        return []
    url, db, username, password = creds
    try:
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        uid = common.authenticate(db, username, password, {})
        if not uid:
            return []
        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        po_v = safe_execute_kw(
            models, db, uid, password, "purchase.order", "read_group",
            [[["state", "in", ["purchase", "done"]]]],
            {"fields": ["partner_id"], "groupby": ["partner_id"]}
        ) or []
        sup_v = safe_execute_kw(
            models, db, uid, password, "product.supplierinfo", "read_group",
            [[]],
            {"fields": ["partner_id"], "groupby": ["partner_id"]}
        ) or []

        v_map = {}
        for g in po_v + sup_v:
            p = g.get("partner_id")
            if isinstance(p, (list, tuple)) and len(p) >= 2 and p[1]:
                v_map[p[0]] = str(p[1]).strip()

        return [{"id": vid, "name": vname} for vid, vname in sorted(v_map.items(), key=lambda x: x[1].lower())]
    except Exception:
        return []


def export_sheet_to_pdf(excel_path, pdf_path, sheet_name="📄 طلب شراء معتمد"):
    """
    Exports the official Purchase Order / RFQ worksheet to a print-ready PDF file
    using native Microsoft Excel COM automation (only invoked on-demand).
    """
    try:
        import win32com.client
        import pythoncom
        pythoncom.CoInitialize()
        excel = win32com.client.DispatchEx("Excel.Application")
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


def _parse_m2o(val):
    if isinstance(val, (list, tuple)) and len(val) >= 2:
        return val[0], str(val[1]).strip()
    return None, ""


def _resolve_period_dates(sales_period, custom_date_from=None, custom_date_to=None):
    """
    Returns (date_from_str, date_to_str, period_days, period_label_ar)
    """
    today = datetime.now()
    date_from_str = None
    date_to_str = None
    period_days = 365
    period_label = "جميع الفترات"

    if sales_period == "last_30_days":
        date_from_str = (today - timedelta(days=30)).strftime("%Y-%m-%d 00:00:00")
        period_days = 30
        period_label = "آخر 30 يوماً"
    elif sales_period == "last_60_days":
        date_from_str = (today - timedelta(days=60)).strftime("%Y-%m-%d 00:00:00")
        period_days = 60
        period_label = "آخر 60 يوماً"
    elif sales_period == "last_90_days":
        date_from_str = (today - timedelta(days=90)).strftime("%Y-%m-%d 00:00:00")
        period_days = 90
        period_label = "آخر 90 يوماً"
    elif sales_period in ("last_180_days", "180d"):
        date_from_str = (today - timedelta(days=180)).strftime("%Y-%m-%d 00:00:00")
        period_days = 180
        period_label = "آخر 180 يوماً"
    elif sales_period in ("last_365_days", "365d"):
        date_from_str = (today - timedelta(days=365)).strftime("%Y-%m-%d 00:00:00")
        period_days = 365
        period_label = "آخر 365 يوماً"
    elif sales_period == "this_year":
        date_from_str = f"{today.year}-01-01 00:00:00"
        period_days = max(1, (today - datetime(today.year, 1, 1)).days + 1)
        period_label = f"العام الحالي ({today.year})"
    elif sales_period == "custom" and custom_date_from:
        date_from_str = f"{custom_date_from} 00:00:00"
        if custom_date_to:
            date_to_str = f"{custom_date_to} 23:59:59"
            try:
                d1 = datetime.strptime(custom_date_from, "%Y-%m-%d")
                d2 = datetime.strptime(custom_date_to, "%Y-%m-%d")
                period_days = max(1, (d2 - d1).days + 1)
            except Exception:
                period_days = 30
            period_label = f"من {custom_date_from} إلى {custom_date_to}"
        else:
            try:
                d1 = datetime.strptime(custom_date_from, "%Y-%m-%d")
                period_days = max(1, (today - d1).days + 1)
            except Exception:
                period_days = 30
            period_label = f"من {custom_date_from} حتى اليوم"

    return date_from_str, date_to_str, period_days, period_label


def generate_purchase_intelligence_report(
    report_mode="comprehensive",       # "comprehensive", "what_to_buy", "what_was_bought"
    coverage_days=60,                  # Target days of inventory coverage (30, 60, 90, 120)
    deduct_open_pos=True,              # Deduct unreceived quantities on open POs from Net Need
    deduct_internal_surplus=True,      # Deduct warehouse stock / cross-branch surplus before buying
    include_vendor_scorecard=True,     # Include Vendor Scorecard & Price Variance sheets
    only_needed_items=False,           # In "What to Buy", show only items with Net Need > 0 or urgent alerts
    export_rfq_pdf=False,              # On-demand ONLY: export official PDF Purchase Order
    filter_internal_ref=None,
    filter_barcode=None,
    filter_name=None,
    filter_tags=None,
    filter_vendors=None,
    selected_showroom_ids=None,
    selected_warehouse_ids=None,
    sales_period="this_year",
    custom_date_from=None,
    custom_date_to=None,
    purchase_period="this_year",
    purchase_date_from=None,
    purchase_date_to=None,
    output_path=None,
    progress_callback=None,
    is_cancelled=None,
    **kwargs
):
    """
    Main orchestrator for the Smart Purchasing & Supply Chain Intelligence Suite.
    """
    t_start = time.time()
    if "purchase_mode" in kwargs:
        report_mode = kwargs["purchase_mode"]
    if "deduct_open_po" in kwargs:
        deduct_open_pos = kwargs["deduct_open_po"]
    if "deduct_warehouse_surplus" in kwargs:
        deduct_internal_surplus = kwargs["deduct_warehouse_surplus"]
    permissions, _ = load_permissions()
    allow_price_variance = (
        kwargs.get("include_price_variance", True)
        and permissions.get("Purchase_Price_Variance", True)
        and permissions.get("Cost", True)
    )

    def notify(pct, text):
        if progress_callback:
            try:
                progress_callback(pct, text)
            except Exception:
                pass

    def chk():
        if is_cancelled and is_cancelled():
            raise InterruptedError("تم إلغاء عملية التصدير من قبل المستخدم.")

    notify(2, "جاري الاتصال بقاعدة بيانات Odoo والتحقق من الصلاحيات...")
    chk()

    creds = get_odoo_credentials()
    if not creds:
        raise ValueError("بيانات الاتصال بقاعدة بيانات Odoo غير متوفرة.")
    url, db, username, password = creds

    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, username, password, {})
    if not uid:
        raise ConnectionError("فشل تسجيل الدخول إلى خادم Odoo.")

    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

    date_from_str, date_to_str, period_days, period_label = _resolve_period_dates(
        sales_period, custom_date_from, custom_date_to
    )
    if not purchase_period or purchase_period == "same_as_sales":
        p_date_from_str, p_date_to_str, p_period_days, p_period_label = (
            date_from_str, date_to_str, period_days, period_label
        )
    else:
        p_date_from_str, p_date_to_str, p_period_days, p_period_label = _resolve_period_dates(
            purchase_period, purchase_date_from, purchase_date_to
        )
    coverage_days = max(7, int(coverage_days or 60))

    ref_pat = parse_tokens(filter_internal_ref)
    bc_pat  = parse_tokens(filter_barcode)
    nm_pat  = parse_tokens(filter_name)
    tg_pat  = parse_tokens(filter_tags)
    vn_pat  = parse_tokens(filter_vendors)

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 1 — Parallel Global Metadata Lookups
    # ═════════════════════════════════════════════════════════════════════════
    notify(6, "جاري جلب بيانات المعارض والمستودعات والوسوم بالتوازي...")
    chk()

    def _fetch_tags():
        m = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        tags = safe_execute_kw(m, db, uid, password, "product.tag", "search_read",
                               [[]], {"fields": ["id", "name"]})
        return {t["id"]: t["name"] for t in tags}

    def _fetch_packages():
        m = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        pkgs = safe_execute_kw(m, db, uid, password, "product.packaging", "search_read",
                               [[["barcode", "!=", False]]],
                               {"fields": ["product_id", "barcode"]})
        pmap = {}
        for p in pkgs:
            if p.get("product_id") and p.get("barcode"):
                pid = p["product_id"][0]
                pmap.setdefault(pid, []).append(str(p["barcode"]))
        return pmap

    with ThreadPoolExecutor(max_workers=4) as ex:
        f_tags = ex.submit(_fetch_tags)
        f_pkgs = ex.submit(_fetch_packages)
        f_sh   = ex.submit(get_active_showrooms)

    tag_map = f_tags.result()
    pkg_map = f_pkgs.result()
    all_showrooms = f_sh.result()

    sh_wh_ids = {s["id"] for s in all_showrooms}
    try:
        all_warehouses = get_all_warehouses(exclude_showroom_ids=sh_wh_ids)
    except Exception:
        all_warehouses = []

    if selected_showroom_ids is not None:
        sel_set = set(selected_showroom_ids)
        target_showrooms = [s for s in all_showrooms if s["id"] in sel_set]
    else:
        target_showrooms = all_showrooms

    if selected_warehouse_ids is not None:
        sel_wh_set = set(selected_warehouse_ids)
        target_warehouses = [w for w in all_warehouses if w["id"] in sel_wh_set]
    else:
        target_warehouses = all_warehouses

    chk()

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 2 — Product Filtering & Reading
    # ═════════════════════════════════════════════════════════════════════════
    notify(14, "جاري البحث عن الأصناف المطابقة للفلاتر في Odoo...")

    base_domain = [["active", "=", True], ["sale_ok", "=", True]]
    need_python_ref  = bool(ref_pat)
    need_python_bc   = bool(bc_pat)
    need_python_name = bool(nm_pat)
    need_python_tags = bool(tg_pat)

    if ref_pat:
        stems = [p.replace("*", "").replace("?", "") for p in ref_pat if p.replace("*", "").replace("?", "")]
        if stems and len(stems) == len(ref_pat):
            if len(stems) == 1:
                base_domain.append(["default_code", "ilike", stems[0]])
            else:
                base_domain.extend(["|"] * (len(stems) - 1))
                for s in stems:
                    base_domain.append(["default_code", "ilike", s])

    if nm_pat:
        stems = [p.replace("*", "").replace("?", "") for p in nm_pat if p.replace("*", "").replace("?", "")]
        if stems and len(stems) == len(nm_pat):
            clauses = []
            for s in stems:
                clauses.append(["name", "ilike", s])
                clauses.append(["product_name_arabic", "ilike", s])
            base_domain.extend(["|"] * (len(clauses) - 1))
            base_domain.extend(clauses)

    if tg_pat:
        matched_tag_ids = [tid for tid, tname in tag_map.items() if match_wildcards(tname, tg_pat)]
        if matched_tag_ids:
            base_domain.append(["product_tag_ids", "in", matched_tag_ids])

    if vn_pat:
        matched_v_ids = _resolve_matched_vendor_ids(models, db, uid, password, vn_pat)
        if not matched_v_ids:
            base_domain.append(["id", "=", -1])
        elif len(matched_v_ids) <= 200:
            sup_rows = safe_execute_kw(
                models, db, uid, password, "product.supplierinfo", "search_read",
                [[["partner_id", "in", matched_v_ids]]],
                {"fields": ["product_tmpl_id", "product_id"], "limit": 50000}
            ) or []
            v_tmpl_ids = set()
            v_prod_ids = set()
            for sr in sup_rows:
                tid = sr["product_tmpl_id"][0] if isinstance(sr.get("product_tmpl_id"), (list, tuple)) else sr.get("product_tmpl_id")
                pid = sr["product_id"][0] if isinstance(sr.get("product_id"), (list, tuple)) else sr.get("product_id")
                if tid:
                    v_tmpl_ids.add(tid)
                if pid:
                    v_prod_ids.add(pid)
            po_ids = safe_execute_kw(
                models, db, uid, password, "purchase.order", "search",
                [[["partner_id", "in", matched_v_ids], ["state", "in", ["purchase", "done", "sent", "draft"]]]]
            ) or []
            if po_ids:
                pol_rows = safe_execute_kw(
                    models, db, uid, password, "purchase.order.line", "search_read",
                    [[["order_id", "in", po_ids]]],
                    {"fields": ["product_id"], "limit": 50000}
                ) or []
                for pr in pol_rows:
                    pid = pr["product_id"][0] if isinstance(pr.get("product_id"), (list, tuple)) else None
                    if pid:
                        v_prod_ids.add(pid)
            if v_tmpl_ids and v_prod_ids:
                base_domain.extend(["|", ["product_tmpl_id", "in", list(v_tmpl_ids)], ["id", "in", list(v_prod_ids)]])
            elif v_tmpl_ids:
                base_domain.append(["product_tmpl_id", "in", list(v_tmpl_ids)])
            elif v_prod_ids:
                base_domain.append(["id", "in", list(v_prod_ids)])
            else:
                base_domain.append(["id", "=", -1])

    all_product_ids = safe_execute_kw(models, db, uid, password, "product.product", "search", [base_domain])
    total_all = len(all_product_ids)
    notify(20, f"تم العثور على {total_all:,} صنف أولي — جاري قراءة بيانات الأصناف بالتوازي...")
    chk()

    fields_to_read = [
        "id", "product_tmpl_id", "default_code", "barcode", "name", "product_name_arabic",
        "standard_price", "list_price", "qty_available", "sales_count",
        "product_tag_ids", "x_studio_concatenated_tags", "categ_id", "uom_id"
    ]

    BATCH = 3500
    chunk_list = [all_product_ids[idx: idx + BATCH] for idx in range(0, total_all, BATCH)]

    def _read_chunk(chunk_ids):
        m = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        records = safe_execute_kw(m, db, uid, password, "product.product", "read",
                                  [chunk_ids], {"fields": fields_to_read})
        out = []
        for r in records:
            pid = r["id"]
            code_val    = str(r.get("default_code") or "")
            barcode_val = str(r.get("barcode") or "")
            pkg_bc      = pkg_map.get(pid, [])
            name_val    = str(r.get("name") or "")
            name_ar     = str(r.get("product_name_arabic") or "")
            tag_ids     = r.get("product_tag_ids") or []
            tag_names   = [tag_map.get(t, "") for t in tag_ids if tag_map.get(t)]
            if r.get("x_studio_concatenated_tags"):
                tag_names.append(str(r["x_studio_concatenated_tags"]))

            if need_python_ref  and not match_wildcards(code_val, ref_pat): continue
            if need_python_bc   and not match_wildcards([barcode_val] + pkg_bc, bc_pat): continue
            if need_python_name and not match_wildcards([name_val, name_ar], nm_pat): continue
            if need_python_tags and not match_wildcards(tag_names, tg_pat): continue

            r["_pkg_bc"] = pkg_bc
            r["_tag_names"] = tag_names
            out.append(r)
        return out

    filtered_records = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for res_chunk in ex.map(_read_chunk, chunk_list):
            chk()
            filtered_records.extend(res_chunk)

    if not filtered_records:
        raise ValueError("لم يتم العثور على أي أصناف تطابق الفلاتر المحددة.")

    product_ById = {r["id"]: r for r in filtered_records}
    filtered_product_ids = list(product_ById.keys())
    prod_to_tmpl = {}
    filtered_tmpl_ids = []
    for r in filtered_records:
        pid = r["id"]
        tid = r["product_tmpl_id"][0] if isinstance(r.get("product_tmpl_id"), (list, tuple)) else r.get("product_tmpl_id")
        prod_to_tmpl[pid] = tid
        if tid and tid not in filtered_tmpl_ids:
            filtered_tmpl_ids.append(tid)

    notify(35, f"اكتملت تصفية {len(filtered_product_ids):,} صنف. جاري جلب أوامر الشراء والموردين والمخزون...")
    chk()

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 3 — Parallel Purchase Lines, Supplierinfo, Quants & POS Sales
    # ═════════════════════════════════════════════════════════════════════════
    pol_fields = [
        "order_id", "product_id", "partner_id", "date_approve", "date_order", "state",
        "product_qty", "qty_received", "qty_invoiced", "price_unit", "discount",
        "price_subtotal", "price_tax", "price_total", "product_uom"
    ]

    def _fetch_all_confirmed_pol():
        """
        Fetches confirmed/done purchase.order.line records for the filtered products
        to build:
          1. Period Purchases Log (What Was Bought)
          2. Latest & Previous Purchase History per Product (for Price Variance & Vendor Info)
          3. Open In-Transit PO lines (where qty_received < product_qty)
        """
        if not filtered_product_ids:
            return [], {}

        def _get_pol_chunk(chunk):
            mt = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
            return safe_execute_kw(
                mt, db, uid, password, "purchase.order.line", "search_read",
                [[["product_id", "in", chunk], ["state", "in", ["purchase", "done"]]]],
                {"fields": pol_fields, "order": "date_approve desc, date_order desc, id desc"}
            ) or []

        if len(filtered_product_ids) <= 2000:
            lines = _get_pol_chunk(filtered_product_ids)
        else:
            chunks = [filtered_product_ids[i:i + 2000] for i in range(0, len(filtered_product_ids), 2000)]
            lines = []
            with ThreadPoolExecutor(max_workers=6) as ex:
                for ch_res in ex.map(_get_pol_chunk, chunks):
                    lines.extend(ch_res)

        # Fetch PO header info (partner_ref, invoice_status, date_approve) for distinct order_ids
        order_ids = list({
            l["order_id"][0] for l in lines
            if isinstance(l.get("order_id"), (list, tuple)) and l["order_id"]
        })
        po_header_map = {}
        if order_ids:
            po_chunks = [order_ids[i:i + 2000] for i in range(0, len(order_ids), 2000)]
            for pch in po_chunks:
                mt = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
                pos = safe_execute_kw(
                    mt, db, uid, password, "purchase.order", "read",
                    [pch],
                    {"fields": ["id", "name", "partner_ref", "date_approve", "date_order", "state", "invoice_status"]}
                ) or []
                for po in pos:
                    po_header_map[po["id"]] = po

        return lines, po_header_map

    def _fetch_supplierinfo():
        if not filtered_tmpl_ids:
            return {}

        def _get_sup_chunk(chunk):
            mt = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
            return safe_execute_kw(
                mt, db, uid, password, "product.supplierinfo", "search_read",
                [[["product_tmpl_id", "in", chunk]]],
                {"fields": ["product_tmpl_id", "partner_id", "price", "discount",
                            "price_discounted", "last_purchase_date", "write_date"],
                 "order": "last_purchase_date desc, write_date desc, id desc"}
            ) or []

        if len(filtered_tmpl_ids) <= 2500:
            sup = _get_sup_chunk(filtered_tmpl_ids)
        else:
            chunks = [filtered_tmpl_ids[i:i + 2500] for i in range(0, len(filtered_tmpl_ids), 2500)]
            sup = []
            with ThreadPoolExecutor(max_workers=6) as ex:
                for ch_res in ex.map(_get_sup_chunk, chunks):
                    sup.extend(ch_res)

        vmap = {}
        for s in sup:
            if not s.get("product_tmpl_id"):
                continue
            vname = s["partner_id"][1] if isinstance(s.get("partner_id"), (list, tuple)) else ""
            if vn_pat and not match_wildcards(vname, vn_pat):
                continue
            tid = s["product_tmpl_id"][0] if isinstance(s["product_tmpl_id"], (list, tuple)) else s["product_tmpl_id"]
            p_val = float(s.get("price") or 0.0)
            dp_val = float(s.get("price_discounted") or 0.0)
            if (p_val > 0 or dp_val > 0) and tid not in vmap:
                vmap[tid] = {
                    "vendor_id":              s["partner_id"][0] if isinstance(s.get("partner_id"), (list, tuple)) else None,
                    "vendor_name":            vname,
                    "vendor_price":           p_val,
                    "vendor_discount":        float(s.get("discount") or 0.0),
                    "vendor_discounted_price": dp_val if dp_val > 0 else round(p_val * (1.0 - float(s.get("discount") or 0.0) / 100.0), 4),
                    "vendor_last_purchase":   str(s.get("last_purchase_date") or "")[:10],
                }
        for s in sup:
            if not s.get("product_tmpl_id"):
                continue
            vname = s["partner_id"][1] if isinstance(s.get("partner_id"), (list, tuple)) else ""
            if vn_pat and not match_wildcards(vname, vn_pat):
                continue
            tid = s["product_tmpl_id"][0] if isinstance(s["product_tmpl_id"], (list, tuple)) else s["product_tmpl_id"]
            if tid not in vmap:
                vmap[tid] = {
                    "vendor_id":              s["partner_id"][0] if isinstance(s.get("partner_id"), (list, tuple)) else None,
                    "vendor_name":            vname,
                    "vendor_price":           float(s.get("price") or 0.0),
                    "vendor_discount":        float(s.get("discount") or 0.0),
                    "vendor_discounted_price": float(s.get("price_discounted") or 0.0),
                    "vendor_last_purchase":   str(s.get("last_purchase_date") or "")[:10],
                }
        return vmap

    def _fetch_quants():
        loc_ids = [s["lot_stock_id"] for s in target_showrooms if s.get("lot_stock_id")]
        loc_ids += [w["lot_stock_id"] for w in target_warehouses if w.get("lot_stock_id")]
        if not loc_ids or not filtered_product_ids:
            return {}
        m = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        dom = [["location_id", "in", loc_ids], ["quantity", "!=", 0]]
        if len(filtered_product_ids) <= 2500:
            dom.append(["product_id", "in", filtered_product_ids])
        quants = safe_execute_kw(m, db, uid, password, "stock.quant", "search_read",
                                 [dom], {"fields": ["product_id", "location_id", "quantity"]}) or []
        qmap = {}
        for q in quants:
            if q.get("product_id") and q.get("location_id"):
                qmap[(q["product_id"][0], q["location_id"][0])] = float(q.get("quantity") or 0.0)
        return qmap

    pos_date_filter = []
    if date_from_str:
        pos_date_filter.append(["date", ">=", date_from_str])
    if date_to_str:
        pos_date_filter.append(["date", "<=", date_to_str])

    def _fetch_pos_sales_for(s):
        mt = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        dom = [["state", "in", ["paid", "done", "invoiced"]],
               ["config_id", "in", s["pos_config_ids"]]] + pos_date_filter
        if len(filtered_product_ids) <= 2500:
            dom.append(["product_id", "in", filtered_product_ids])
        res = mt.execute_kw(db, uid, password, "report.pos.order", "read_group",
                            [dom, ["product_id", "product_qty:sum"], ["product_id"]],
                            {"lazy": False})
        return s["id"], {r["product_id"][0]: float(r.get("product_qty") or 0.0)
                         for r in res if r.get("product_id")}

    with ThreadPoolExecutor(max_workers=8 + len(target_showrooms)) as ex:
        f_pol    = ex.submit(_fetch_all_confirmed_pol)
        f_sup    = ex.submit(_fetch_supplierinfo)
        f_quants = ex.submit(_fetch_quants)
        pos_futs = {ex.submit(_fetch_pos_sales_for, s): s["id"] for s in target_showrooms}

    all_pol_lines, po_header_map = f_pol.result()
    vendor_tmpl_map = f_sup.result()
    stock_map = f_quants.result()

    showroom_sales = {}
    for fut, sid in pos_futs.items():
        _, smap = fut.result()
        showroom_sales[sid] = smap

    notify(65, "اكتمل جلب البيانات من Odoo. جاري تحليل المشتريات والاحتياج وتقييم الموردين...")
    chk()

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 4 — Process Purchase History, Open POs, Price Variance & Vendor Stats
    # ═════════════════════════════════════════════════════════════════════════
    # Structures per product:
    # - po_history_by_pid[pid]: list of non-zero purchase lines ordered newest first
    # - open_po_qty_by_pid[pid]: total pending unreceived qty on recent confirmed POs
    # - open_po_rows: detailed list of unreceived PO lines
    # - period_purchase_rows: detailed list of PO lines falling within [date_from_str, date_to_str]
    # - vendor_stats[vendor_name]: aggregated metrics for Vendor Scorecard
    po_history_by_pid = {}
    open_po_qty_by_pid = {}
    open_po_rows = []
    period_purchase_rows = []
    vendor_stats = {}

    today_dt = datetime.now()

    for l in all_pol_lines:
        pid, _ = _parse_m2o(l.get("product_id"))
        if not pid or pid not in product_ById:
            continue
        prod = product_ById[pid]
        order_id, order_name = _parse_m2o(l.get("order_id"))
        po_hdr = po_header_map.get(order_id, {})
        if not order_name:
            order_name = po_hdr.get("name", f"PO#{order_id}")
        partner_ref = str(po_hdr.get("partner_ref") or "")

        _, vendor_name = _parse_m2o(l.get("partner_id"))
        if not vendor_name:
            vendor_name = "مورد غير محدد"

        # If vendor filter is active, check if this line's vendor matches
        line_vendor_matches = True
        if vn_pat and not match_wildcards(vendor_name, vn_pat):
            line_vendor_matches = False

        dt_raw = str(l.get("date_approve") or l.get("date_order") or po_hdr.get("date_approve") or po_hdr.get("date_order") or "")
        dt_day = dt_raw[:10] if len(dt_raw) >= 10 else ""

        p_qty   = float(l.get("product_qty") or 0.0)
        r_qty   = float(l.get("qty_received") or 0.0)
        inv_qty = float(l.get("qty_invoiced") or 0.0)
        pend_qty = max(0.0, round(p_qty - r_qty, 2))

        price_u  = float(l.get("price_unit") or 0.0)
        disc_pct = float(l.get("discount") or 0.0)
        net_u    = round(price_u * (1.0 - disc_pct / 100.0), 4)
        sub_val  = float(l.get("price_subtotal") or 0.0)
        tax_val  = float(l.get("price_tax") or 0.0)
        tot_val  = float(l.get("price_total") or (sub_val + tax_val))

        is_bonus = (p_qty > 0 and (price_u <= 0.0001 or disc_pct >= 99.9 or net_u <= 0.0001))

        # Record non-bonus purchase history for product cost/variance tracking
        if not is_bonus and net_u > 0:
            po_history_by_pid.setdefault(pid, []).append({
                "order_name": order_name,
                "date": dt_day,
                "vendor_name": vendor_name,
                "price_unit": price_u,
                "discount": disc_pct,
                "net_price": net_u,
                "product_qty": p_qty,
                "qty_received": r_qty,
            })

        # Check if PO line falls within selected Purchase Period
        in_purchase_period = True
        if p_date_from_str and dt_raw and dt_raw < p_date_from_str:
            in_purchase_period = False
        if p_date_to_str and dt_raw and dt_raw > p_date_to_str:
            in_purchase_period = False

        # Track Open / Pending POs within selected Purchase Period
        if pend_qty > 0 and in_purchase_period:
            open_po_qty_by_pid[pid] = open_po_qty_by_pid.get(pid, 0.0) + pend_qty
            if line_vendor_matches:
                try:
                    days_waiting = max(0, (today_dt - datetime.strptime(dt_day, "%Y-%m-%d")).days)
                except Exception:
                    days_waiting = 0
                open_po_rows.append({
                    "pid": pid,
                    "order_name": order_name,
                    "date": dt_day,
                    "days_waiting": days_waiting,
                    "vendor_name": vendor_name,
                    "ordered_qty": p_qty,
                    "received_qty": r_qty,
                    "pending_qty": pend_qty,
                    "net_price": net_u,
                    "pending_value": round(pend_qty * net_u, 2),
                })

        if in_purchase_period and line_vendor_matches and p_qty > 0:
            code_val = str(prod.get("default_code") or "")
            bc_val   = str(prod.get("barcode") or "")
            nm_en    = str(prod.get("name") or "")
            nm_ar    = str(prod.get("product_name_arabic") or "")
            tags_str = ", ".join(prod.get("_tag_names", []))
            _, categ_name = _parse_m2o(prod.get("categ_id"))
            _, uom_name   = _parse_m2o(l.get("product_uom") or prod.get("uom_id"))

            period_purchase_rows.append({
                "pid": pid,
                "order_name": order_name,
                "date": dt_day,
                "vendor_name": vendor_name,
                "partner_ref": partner_ref,
                "code": code_val,
                "barcode": bc_val,
                "name_en": nm_en,
                "name_ar": nm_ar,
                "tags": tags_str,
                "category": categ_name,
                "uom": uom_name,
                "ordered_qty": p_qty,
                "received_qty": r_qty,
                "pending_qty": pend_qty,
                "invoiced_qty": inv_qty,
                "price_unit": price_u,
                "discount_pct": round(disc_pct / 100.0, 4),
                "net_price": net_u,
                "line_type": "🎁 بونص مجاني" if is_bonus else "📦 شراء أساسي",
                "is_bonus": is_bonus,
                "subtotal": round(sub_val, 2),
                "tax": round(tax_val, 2),
                "total": round(tot_val, 2),
                "list_price": float(prod.get("list_price") or 0.0),
            })

            vs = vendor_stats.setdefault(vendor_name, {
                "vendor_name": vendor_name,
                "orders_set": set(),
                "skus_set": set(),
                "ordered_qty": 0.0,
                "received_qty": 0.0,
                "bonus_qty": 0.0,
                "bonus_retail_val": 0.0,
                "disc_weighted_sum": 0.0,
                "disc_weight_base": 0.0,
                "untaxed_total": 0.0,
                "taxed_total": 0.0,
                "current_stock_val": 0.0,
                "suggested_po_val": 0.0,
            })
            vs["orders_set"].add(order_name)
            vs["skus_set"].add(pid)
            vs["ordered_qty"]  += p_qty
            vs["received_qty"] += r_qty
            vs["untaxed_total"] += sub_val
            vs["taxed_total"]   += tot_val
            if is_bonus:
                vs["bonus_qty"] += r_qty if r_qty > 0 else p_qty
                vs["bonus_retail_val"] += (r_qty if r_qty > 0 else p_qty) * float(prod.get("list_price") or 0.0)
            elif price_u > 0 and p_qty > 0:
                vs["disc_weighted_sum"] += disc_pct * (price_u * p_qty)
                vs["disc_weight_base"]  += (price_u * p_qty)

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 5 — Build Smart Replenishment ("What to Buy") & Price Variance Rows
    # ═════════════════════════════════════════════════════════════════════════
    replenishment_rows = []
    variance_rows = []
    stock_by_pid = {}
    sold_by_pid = {}
    days_cover_by_pid = {}

    for r in filtered_records:
        chk()
        pid = r["id"]
        tid = prod_to_tmpl.get(pid, 0)

        code_val = str(r.get("default_code") or "")
        bc_val   = str(r.get("barcode") or "")
        nm_en    = str(r.get("name") or "")
        nm_ar    = str(r.get("product_name_arabic") or "")
        tags_str = ", ".join(r.get("_tag_names", []))
        _, categ_name = _parse_m2o(r.get("categ_id"))
        _, uom_name   = _parse_m2o(r.get("uom_id"))

        cost_val  = float(r.get("standard_price") or 0.0)
        price_val = float(r.get("list_price") or 0.0)

        # Showroom & Warehouse Stock + POS Sales (computed for all products so open_po_rows always has sales/stock)
        sh_oh_total = 0.0
        sh_sl_total = 0.0
        deficits_branches = []
        surpluses_branches = []

        for s in target_showrooms:
            sid = s["id"]
            lot = s.get("lot_stock_id")
            oh = stock_map.get((pid, lot), 0.0) if lot else 0.0
            sl = showroom_sales.get(sid, {}).get(pid, 0.0)
            sh_oh_total += oh
            sh_sl_total += sl

            sh_m = (sl / (period_days / 30.0)) if period_days > 0 else (sl / 12.0)
            if oh <= 1 and sl > 0:
                deficits_branches.append((s["name"], oh, sl, max(1.0, round(sh_m - oh))))
            elif oh >= 3:
                keep_buf = max(1.0, round(sh_m * 1.5))
                surp = max(0.0, oh - keep_buf)
                if surp >= 1.0:
                    surpluses_branches.append((s["name"], oh, sl, surp))

        wh_oh_total = 0.0
        for w in target_warehouses:
            lot = w.get("lot_stock_id")
            if lot:
                wh_oh_total += stock_map.get((pid, lot), 0.0)

        company_oh = float(r.get("qty_available") or 0.0)
        # If no warehouses were explicitly ticked, derive central warehouse stock if company_oh > sh_oh_total
        effective_wh_oh = wh_oh_total if target_warehouses else max(0.0, company_oh - sh_oh_total)
        total_current_stock = sh_oh_total + effective_wh_oh
        stock_by_pid[pid] = total_current_stock

        open_po_qty = open_po_qty_by_pid.get(pid, 0.0)

        # Sales velocity
        analysis_sl = sh_sl_total if target_showrooms else float(r.get("sales_count") or 0.0)
        sold_by_pid[pid] = analysis_sl
        daily_sales = (analysis_sl / float(period_days)) if period_days > 0 else 0.0
        monthly_sales = daily_sales * 30.0

        # Coverage days (based on total available stock in showrooms + warehouses)
        avail_for_cover = total_current_stock if deduct_internal_surplus else sh_oh_total
        if avail_for_cover <= 0:
            days_cover = 0
        elif daily_sales <= 0:
            days_cover = 999
        else:
            days_cover = round(avail_for_cover / daily_sales)
        days_cover_by_pid[pid] = days_cover

        # Resolve authoritative vendor & price
        hist = po_history_by_pid.get(pid, [])
        sup_info = vendor_tmpl_map.get(tid, {})

        if hist:
            latest_po = hist[0]
            vendor_name = latest_po["vendor_name"] or sup_info.get("vendor_name", "")
            vendor_price = latest_po["price_unit"]
            vendor_disc  = latest_po["discount"]
            net_buy_price = latest_po["net_price"]
            last_buy_date = latest_po["date"]
        else:
            vendor_name   = sup_info.get("vendor_name", "")
            vendor_price  = float(sup_info.get("vendor_price") or 0.0)
            vendor_disc   = float(sup_info.get("vendor_discount") or 0.0)
            net_buy_price = float(sup_info.get("vendor_discounted_price") or 0.0)
            last_buy_date = sup_info.get("vendor_last_purchase", "")

        if net_buy_price <= 0:
            net_buy_price = vendor_price if vendor_price > 0 else cost_val

        # Check Vendor Filter on product level (resolved authoritative vendor must strictly match)
        if vn_pat:
            if not vendor_name or not match_wildcards(vendor_name, vn_pat):
                continue

        # Target Stock for coverage_days
        target_qty = round(daily_sales * coverage_days)
        gross_need = max(0.0, round(target_qty - sh_oh_total))

        effective_existing = (sh_oh_total + effective_wh_oh) if deduct_internal_surplus else sh_oh_total
        effective_in_transit = open_po_qty if deduct_open_pos else 0.0
        net_buy_qty = max(0.0, round(target_qty - effective_existing - effective_in_transit))

        # Margin % Excl. VAT
        if price_val > 0 and net_buy_price > 0:
            p_excl = price_val / 1.15
            expected_margin = round((p_excl - net_buy_price) / p_excl, 4)
        else:
            expected_margin = 0.0

        # Transfer recommendation vs Buy recommendation
        internal_transfer_qty = sum(x[3] for x in surpluses_branches)
        if net_buy_qty > 0:
            if effective_wh_oh > 0 and gross_need > net_buy_qty:
                sys_action = f"شراء ({int(net_buy_qty)}) + صرف من المستودع ({int(min(effective_wh_oh, gross_need - net_buy_qty))})"
            else:
                sys_action = f"✅ اعتماد شراء ({int(net_buy_qty)} {uom_name or 'قطعة'})"
        else:
            if gross_need > 0 and effective_wh_oh >= gross_need:
                sys_action = f"🔄 لا تشتري — يُصرف من المستودع ({int(gross_need)})"
            elif gross_need > 0 and open_po_qty >= gross_need:
                sys_action = f"🚚 لا تشتري — بانتظار استلام طلبية ({int(open_po_qty)})"
            elif deficits_branches and surpluses_branches:
                sys_action = f"🔄 لا تشتري — يُغطى بمناقلة داخلية ({int(min(sum(x[3] for x in deficits_branches), internal_transfer_qty))})"
            elif days_cover >= 180 or (analysis_sl <= 0 and total_current_stock > 0):
                sys_action = "🛑 إيقاف شراء (مخزون فائض / راكد)"
            else:
                sys_action = "⚪ الرصيد الحالي كافٍ"

        revenue_val = (analysis_sl * price_val) if price_val > 0 else (analysis_sl * net_buy_price)

        rep_row = {
            "pid": pid,
            "code": code_val,
            "barcode": bc_val,
            "name_en": nm_en,
            "name_ar": nm_ar,
            "tags": tags_str,
            "category": categ_name,
            "uom": uom_name,
            "abc": "C",  # Populated in Pareto post-process
            "vendor_name": vendor_name or "غير محدد",
            "sh_stock": sh_oh_total,
            "wh_stock": effective_wh_oh,
            "total_stock": total_current_stock,
            "open_po_qty": open_po_qty,
            "sold_qty": analysis_sl,
            "monthly_sales": round(monthly_sales, 1),
            "days_cover": days_cover,
            "priority": "",  # Populated after ABC classification
            "priority_rank": 9,
            "net_buy_qty": net_buy_qty,
            "net_buy_price": round(net_buy_price, 2),
            "vendor_disc_pct": round(vendor_disc / 100.0, 4),
            "expected_po_val": round(net_buy_qty * net_buy_price, 2),
            "last_buy_date": last_buy_date,
            "sales_price": price_val,
            "expected_margin": expected_margin,
            "sys_action": sys_action,
            "_revenue": revenue_val,
        }
        replenishment_rows.append(rep_row)

        # Accumulate vendor stock & suggested PO value in vendor_stats
        if vendor_name:
            vs = vendor_stats.setdefault(vendor_name, {
                "vendor_name": vendor_name,
                "orders_set": set(),
                "skus_set": set(),
                "ordered_qty": 0.0,
                "received_qty": 0.0,
                "bonus_qty": 0.0,
                "bonus_retail_val": 0.0,
                "disc_weighted_sum": 0.0,
                "disc_weight_base": 0.0,
                "untaxed_total": 0.0,
                "taxed_total": 0.0,
                "current_stock_val": 0.0,
                "suggested_po_val": 0.0,
            })
            vs["skus_set"].add(pid)
            vs["current_stock_val"] += max(0.0, total_current_stock) * net_buy_price
            vs["suggested_po_val"]  += round(net_buy_qty * net_buy_price, 2)

        # Build Price Variance Row if product has >= 2 historical purchases (or PO vs standard cost difference)
        if allow_price_variance and len(hist) >= 2:
            latest = hist[0]
            # Find the most recent distinct purchase order with a different date or order
            prev = hist[1]
            for h_cand in hist[1:]:
                if h_cand["order_name"] != latest["order_name"] or h_cand["net_price"] != latest["net_price"]:
                    prev = h_cand
                    break

            min_hist_price = min(h["net_price"] for h in hist if h["net_price"] > 0)
            prev_p = prev["net_price"]
            curr_p = latest["net_price"]
            diff_p = round(curr_p - prev_p, 2)
            diff_pct = round((curr_p - prev_p) / prev_p, 4) if prev_p > 0 else 0.0
            fin_impact = round(diff_p * latest["product_qty"], 2)

            if diff_pct > 0.005:
                if expected_margin < 0.20:
                    v_status = "🚨 ارتفاع بالسعر + تآكل الهامش (<20%)"
                    v_rank = 1
                else:
                    v_status = "🔺 ارتفاع في سعر الشراء"
                    v_rank = 2
            elif diff_pct < -0.005:
                v_status = "🟢 انخفاض في سعر الشراء (وفر)"
                v_rank = 3
            else:
                if expected_margin < 0.20 and price_val > 0:
                    v_status = "⚠️ سعر ثابت ولكن الهامش منخفض (<20%)"
                    v_rank = 2
                else:
                    v_status = "⚪ سعر شراء مستقر"
                    v_rank = 4

            variance_rows.append({
                "code": code_val,
                "barcode": bc_val,
                "name_ar": nm_ar or nm_en,
                "category": categ_name,
                "vendor_name": latest["vendor_name"],
                "prev_order": prev["order_name"],
                "prev_date": prev["date"],
                "prev_price": round(prev_p, 2),
                "curr_order": latest["order_name"],
                "curr_date": latest["date"],
                "curr_price": round(curr_p, 2),
                "min_price": round(min_hist_price, 2),
                "diff_val": diff_p,
                "diff_pct": diff_pct,
                "latest_qty": latest["product_qty"],
                "fin_impact": fin_impact,
                "sales_price": price_val,
                "margin_pct": expected_margin,
                "status": v_status,
                "_rank": v_rank,
            })

    # ── Post-Process 1: Pareto ABC Classification & Priority Assignment ───────
    total_rev = sum(r["_revenue"] for r in replenishment_rows)
    if total_rev > 0:
        sorted_by_rev = sorted(replenishment_rows, key=lambda x: x["_revenue"], reverse=True)
        cum_rev = 0.0
        for r in sorted_by_rev:
            rev = r["_revenue"]
            if rev <= 0:
                r["abc"] = "C"
            else:
                cum_rev += rev
                pct = (cum_rev / total_rev) * 100.0
                if pct <= 80.0:
                    r["abc"] = "A"
                elif pct <= 95.0:
                    r["abc"] = "B"
                else:
                    r["abc"] = "C"

    for r in replenishment_rows:
        nb = r["net_buy_qty"]
        dc = r["days_cover"]
        abc = r["abc"]
        sl = r["sold_qty"]
        tot_st = r["total_stock"]
        open_q = r["open_po_qty"]

        if nb > 0:
            if (tot_st <= 0 or dc <= 7) and abc in ("A", "B"):
                r["priority"] = "🚨 عاجل جداً (نفاد صنف A/B)"
                r["priority_rank"] = 1
            elif tot_st <= 0 or dc <= 15:
                r["priority"] = "⚠️ تحت حد الطلب (طلب قريب)"
                r["priority_rank"] = 2
            else:
                r["priority"] = "📦 تعزيز مخزون دوري"
                r["priority_rank"] = 3
        else:
            if open_q > 0 and dc < coverage_days:
                r["priority"] = "🚚 بانتظار استلام طلبية"
                r["priority_rank"] = 4
            elif "لا تشتري —" in r["sys_action"]:
                r["priority"] = "🔄 متوفر بالمستودع/المعارض"
                r["priority_rank"] = 5
            elif dc >= 180 or (sl <= 0 and tot_st > 0):
                r["priority"] = "🛑 إيقاف شراء (فائض/راكد)"
                r["priority_rank"] = 7
            else:
                r["priority"] = "✅ مخزون متوازن وكافٍ"
                r["priority_rank"] = 6

    # Filter replenishment_rows if user checked `only_needed_items`
    if only_needed_items:
        filtered_rep = [r for r in replenishment_rows if r["net_buy_qty"] > 0 or r["priority_rank"] <= 4]
        if filtered_rep:
            replenishment_rows = filtered_rep

    # Sort replenishment_rows: Urgent & Needed items first, then by revenue descending
    replenishment_rows.sort(key=lambda x: (x["priority_rank"], -x["expected_po_val"], -x["_revenue"]))

    # Enrich Period Purchases Rows with Current Stock & Sell-Through %
    for pr in period_purchase_rows:
        pid = pr["pid"]
        cur_st = max(0.0, stock_by_pid.get(pid, 0.0))
        pr["current_stock"] = cur_st
        rcv = pr["received_qty"] if pr["received_qty"] > 0 else pr["ordered_qty"]
        if rcv > 0:
            # Approximate sell-through of received batch
            sold_approx = max(0.0, rcv - cur_st) if cur_st < rcv else 0.0
            pr["sell_through_pct"] = round(min(1.0, sold_approx / rcv), 4)
        else:
            pr["sell_through_pct"] = 0.0

    # Enrich Open PO Rows with Current Showroom Status & Sales Period Velocity
    for op in open_po_rows:
        pid = op["pid"]
        prod = product_ById.get(pid, {})
        op["code"] = str(prod.get("default_code") or "")
        op["barcode"] = str(prod.get("barcode") or "")
        op["name_ar"] = str(prod.get("product_name_arabic") or prod.get("name") or "")
        cur_st = stock_by_pid.get(pid, 0.0)
        sold_q = sold_by_pid.get(pid, 0.0)
        d_cov  = days_cover_by_pid.get(pid, 0 if cur_st <= 0 else 999)
        op["current_stock"] = cur_st
        op["sold_qty"] = sold_q
        op["days_cover"] = d_cov
        if cur_st <= 0 and sold_q > 0:
            op["urgency"] = "🚨 نفاد لصنف متحرك - استعجال فوري للمورد!"
            op["urgency_rank"] = 1
        elif cur_st > 0 and sold_q > 0 and d_cov <= 14:
            op["urgency"] = "⚠️ رصيد حرج وشيك النفاد - استعجال التسليم"
            op["urgency_rank"] = 2
        elif cur_st > 0 and sold_q > 0:
            op["urgency"] = "🚚 الرصيد يغطي الطلب حالياً - متابعة عادية"
            op["urgency_rank"] = 3
        elif sold_q <= 0 and cur_st <= 0:
            if op["days_waiting"] > 60:
                op["urgency"] = "🛑 راكد بلا مبيعات (متأخر) - يوصى بإلغاء المتبقي"
                op["urgency_rank"] = 5
            else:
                op["urgency"] = "⚪ رصيد صفري ولكن بلا مبيعات بالفترة"
                op["urgency_rank"] = 4
        else:
            op["urgency"] = "🛑 متوفر بالمخزون وبلا مبيعات - يوصى بإلغاء المتبقي"
            op["urgency_rank"] = 5

    open_po_rows.sort(key=lambda x: (x["urgency_rank"], -x["sold_qty"], -x["days_waiting"], -x["pending_value"]))
    variance_rows.sort(key=lambda x: (x["_rank"], -abs(x["fin_impact"])))

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 6 — Excel Workbook Construction (Multi-Sheet Executive Styling)
    # ═════════════════════════════════════════════════════════════════════════
    notify(78, "جاري بناء مصنف الإكسيل التنفيذي متعدد الأوراق...")
    chk()

    if not output_path:
        export_dir = r"c:\OdooDB\exports"
        os.makedirs(export_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(export_dir, f"تقرير_المشتريات_الذكي_{ts}.xlsx")
    else:
        out_dir = os.path.dirname(os.path.abspath(output_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

    wb = openpyxl.Workbook()
    # Remove default sheet after creating custom sheets
    default_ws = wb.active

    # Color Palette & Typography
    FONT_FAMILY = "Segoe UI"
    C_NAVY_DARK = "0F172A"
    C_NAVY_HDR  = "1E3A5F"
    C_GOLD      = "B8860B"
    C_TEAL      = "0D9488"
    C_GREEN     = "15803D"
    C_RED       = "B91C1C"
    C_AMBER     = "B45309"
    C_PURPLE    = "5B21B6"
    C_ALT_ROW   = "F8FAFC"
    C_BORDER    = "CBD5E1"
    C_TOTAL_BG  = "E2E8F0"

    s_thin = Side(style="thin", color=C_BORDER)
    s_med_navy = Side(style="medium", color=C_NAVY_HDR)
    BORDER_CELL = Border(left=s_thin, right=s_thin, top=s_thin, bottom=s_thin)
    BORDER_TOTAL = Border(left=s_thin, right=s_thin, top=s_med_navy, bottom=s_med_navy)

    FONT_HDR = Font(name=FONT_FAMILY, size=10, bold=True, color="FFFFFF")
    FONT_DATA = Font(name=FONT_FAMILY, size=10, bold=False, color="1E293B")
    FONT_BOLD = Font(name=FONT_FAMILY, size=10, bold=True, color="0F172A")
    FONT_TOTAL = Font(name=FONT_FAMILY, size=10, bold=True, color="0F172A")

    FONT_URGENT = Font(name=FONT_FAMILY, size=10, bold=True, color="B91C1C")
    FONT_WARN   = Font(name=FONT_FAMILY, size=10, bold=True, color="B45309")
    FONT_OK     = Font(name=FONT_FAMILY, size=10, bold=True, color="15803D")
    FONT_BLUE   = Font(name=FONT_FAMILY, size=10, bold=True, color="1D4ED8")
    FONT_MUTED  = Font(name=FONT_FAMILY, size=9, bold=False, color="64748B")

    FILL_HDR_NAVY   = PatternFill("solid", fgColor=C_NAVY_HDR)
    FILL_HDR_GOLD   = PatternFill("solid", fgColor=C_GOLD)
    FILL_HDR_TEAL   = PatternFill("solid", fgColor=C_TEAL)
    FILL_HDR_GREEN  = PatternFill("solid", fgColor=C_GREEN)
    FILL_HDR_PURPLE = PatternFill("solid", fgColor=C_PURPLE)
    FILL_ALT        = PatternFill("solid", fgColor=C_ALT_ROW)
    FILL_TOTAL      = PatternFill("solid", fgColor=C_TOTAL_BG)
    FILL_INPUT_QTY  = PatternFill("solid", fgColor="FEF9C3")  # Soft yellow highlight for editable qty
    FILL_URGENT_BG  = PatternFill("solid", fgColor="FEE2E2")
    FILL_BONUS_BG   = PatternFill("solid", fgColor="DCFCE7")

    ALIGN_CTR = Alignment(horizontal="center", vertical="center", wrap_text=False)
    ALIGN_HDR = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ALIGN_RT  = Alignment(horizontal="right",  vertical="center", wrap_text=False)
    ALIGN_LT  = Alignment(horizontal="left",   vertical="center", wrap_text=False)

    # Calculate Executive Summary KPIs
    tot_purchased_untaxed = sum(r["subtotal"] for r in period_purchase_rows)
    tot_purchased_taxed   = sum(r["total"] for r in period_purchase_rows)
    tot_purchased_qty     = sum(r["received_qty"] for r in period_purchase_rows)
    distinct_pos_count    = len({r["order_name"] for r in period_purchase_rows})
    tot_bonus_retail_val  = sum(vs["bonus_retail_val"] for vs in vendor_stats.values())

    tot_open_po_val       = sum(r["pending_value"] for r in open_po_rows)
    tot_open_po_qty       = sum(r["pending_qty"] for r in open_po_rows)

    needed_items          = [r for r in replenishment_rows if r["net_buy_qty"] > 0]
    tot_suggested_po_val  = sum(r["expected_po_val"] for r in needed_items)
    tot_suggested_po_qty  = sum(r["net_buy_qty"] for r in needed_items)
    urgent_a_count        = sum(1 for r in needed_items if r["priority_rank"] == 1)
    price_inc_count       = sum(1 for r in variance_rows if r["diff_pct"] > 0.005)

    profile = load_company_profile()
    comp_name_ar = profile.get("name_ar") or "شركة العسلي التجارية"
    comp_name_en = profile.get("name_en") or "Al-Assali Trading Co."

    # ─────────────────────────────────────────────────────────────────────────
    # SHEET 1: 📊 لوحة قيادة المشتريات (Executive Procurement Dashboard)
    # ─────────────────────────────────────────────────────────────────────────
    ws_dash = wb.create_sheet(title="📊 لوحة قيادة المشتريات")
    ws_dash.views.sheetView[0].rightToLeft = True
    ws_dash.views.sheetView[0].showGridLines = True

    ws_dash.merge_cells("A1:H1")
    c_title = ws_dash["A1"]
    c_title.value = f"📊 لوحة القيادة التنفيذية لإدارة المشتريات وسلاسل الإمداد — {comp_name_ar}"
    c_title.font = Font(name=FONT_FAMILY, size=15, bold=True, color="FFFFFF")
    c_title.fill = PatternFill("solid", fgColor=C_NAVY_DARK)
    c_title.alignment = ALIGN_CTR
    ws_dash.row_dimensions[1].height = 38

    ws_dash.merge_cells("A2:H2")
    c_sub = ws_dash["A2"]
    vendor_filter_txt = filter_vendors if filter_vendors else "جميع الموردين"
    c_sub.value = (
        f"📈 فترة المبيعات: {period_label}   |   🧾 فترة المشتريات: {p_period_label}   |   "
        f"🎯 هدف التغطية: {coverage_days} يوم   |   🤝 الموردين: {vendor_filter_txt}   |   ⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    c_sub.font = Font(name=FONT_FAMILY, size=10, bold=True, color="E2E8F0")
    c_sub.fill = FILL_HDR_NAVY
    c_sub.alignment = ALIGN_CTR
    ws_dash.row_dimensions[2].height = 24

    # 8 KPI Cards across 2 rows (Rows 4-5 and Rows 7-8)
    kpi_cards = [
        # Row 1: What Was Bought & Open POs
        ("💰 إجمالي المشتريات الفعلية (شامل الضريبة)", f"{tot_purchased_taxed:,.2f} ر.س", "1E3A5F", 4, 1),
        ("🧾 عدد أوامر الشراء المؤكدة بالفترة", f"{distinct_pos_count:,} أمر شراء ({tot_purchased_qty:,.0f} قطعة)", "0D9488", 4, 3),
        ("🎁 قيمة البونص والعينات المجانية المستلمة", f"{tot_bonus_retail_val:,.2f} ر.س (بسعر البيع)", "15803D", 4, 5),
        ("🚚 بضائع بالطريق (طلبيات مفتوحة قيد الاستلام)", f"{tot_open_po_val:,.2f} ر.س ({tot_open_po_qty:,.0f} قطعة)", "B45309", 4, 7),
        # Row 2: What to Buy & Alerts
        ("🛒 ميزانية خطة الشراء المقترحة ({} يوم)".format(coverage_days), f"{tot_suggested_po_val:,.2f} ر.س ({len(needed_items):,} صنف)", "5B21B6", 7, 1),
        ("🚨 أصناف حرجة (فئة A/B) نفدت وتحتاج شراء فوري", f"{urgent_a_count:,} صنف استراتيجي", "B91C1C", 7, 3),
        ("📈 تنبيهات ارتفاع أسعار الشراء من الموردين", f"{price_inc_count:,} صنف ارتفع سعره", "C2410C", 7, 5),
        ("🤝 عدد الموردين النشطين بالتقرير", f"{len(vendor_stats):,} مورد نشط", "334155", 7, 7),
    ]

    for lbl_txt, val_txt, hex_bg, r_top, c_start in kpi_cards:
        c_end = c_start + 1
        ws_dash.merge_cells(start_row=r_top, start_column=c_start, end_row=r_top, end_column=c_end)
        ws_dash.merge_cells(start_row=r_top + 1, start_column=c_start, end_row=r_top + 1, end_column=c_end)

        cell_lbl = ws_dash.cell(row=r_top, column=c_start, value=lbl_txt)
        cell_lbl.font = Font(name=FONT_FAMILY, size=9, bold=True, color="FFFFFF")
        cell_lbl.fill = PatternFill("solid", fgColor=hex_bg)
        cell_lbl.alignment = ALIGN_CTR

        cell_val = ws_dash.cell(row=r_top + 1, column=c_start, value=val_txt)
        cell_val.font = Font(name=FONT_FAMILY, size=13, bold=True, color=hex_bg)
        cell_val.fill = PatternFill("solid", fgColor="F8FAFC")
        cell_val.alignment = ALIGN_CTR

        for rr in (r_top, r_top + 1):
            for cc in (c_start, c_end):
                ws_dash.cell(row=rr, column=cc).border = BORDER_CELL

    ws_dash.row_dimensions[4].height = 20
    ws_dash.row_dimensions[5].height = 30
    ws_dash.row_dimensions[7].height = 20
    ws_dash.row_dimensions[8].height = 30

    # Dashboard Table: Top 12 Vendors by Spend & Replenishment Need
    ws_dash.merge_cells("A10:H10")
    t_hdr = ws_dash["A10"]
    t_hdr.value = "🏆 أعلى الموردين من حيث حجم التعامل والاحتياج الشرائي المقترح"
    t_hdr.font = Font(name=FONT_FAMILY, size=11, bold=True, color="FFFFFF")
    t_hdr.fill = FILL_HDR_NAVY
    t_hdr.alignment = ALIGN_CTR
    ws_dash.row_dimensions[10].height = 26

    dash_cols = [
        "اسم المورد (Vendor)", "عدد الأوامر", "عدد الأصناف", "الكميات المستلمة",
        "نسبة الالتزام بالتوريد", "إجمالي المشتريات الفعلية (ر.س)", "قيمة المخزون الحالي (ر.س)", "قيمة الشراء المقترح (ر.س)"
    ]
    for ci, ch_txt in enumerate(dash_cols, 1):
        c = ws_dash.cell(row=11, column=ci, value=ch_txt)
        c.font = FONT_HDR
        c.fill = FILL_HDR_TEAL
        c.alignment = ALIGN_HDR
        c.border = BORDER_CELL
    ws_dash.row_dimensions[11].height = 24

    top_vendors = sorted(
        vendor_stats.values(),
        key=lambda x: (x["taxed_total"] + x["suggested_po_val"]),
        reverse=True
    )[:15]

    for idx_v, vs in enumerate(top_vendors, 12):
        fill_r = FILL_ALT if idx_v % 2 == 1 else None
        fill_rate = round(min(1.0, vs["received_qty"] / vs["ordered_qty"]), 4) if vs["ordered_qty"] > 0 else 1.0
        row_v = [
            (vs["vendor_name"], ALIGN_RT, "@"),
            (len(vs["orders_set"]), ALIGN_CTR, "#,##0"),
            (len(vs["skus_set"]), ALIGN_CTR, "#,##0"),
            (vs["received_qty"], ALIGN_CTR, "#,##0"),
            (fill_rate, ALIGN_CTR, "0.0%"),
            (round(vs["taxed_total"], 2), ALIGN_RT, "#,##0.00"),
            (round(vs["current_stock_val"], 2), ALIGN_RT, "#,##0.00"),
            (round(vs["suggested_po_val"], 2), ALIGN_RT, "#,##0.00"),
        ]
        for ci, (v_val, v_al, v_fmt) in enumerate(row_v, 1):
            c = ws_dash.cell(row=idx_v, column=ci, value=v_val)
            c.font = FONT_DATA
            c.alignment = v_al
            c.number_format = v_fmt
            c.border = BORDER_CELL
            if fill_r:
                c.fill = fill_r
        ws_dash.row_dimensions[idx_v].height = 20

    dash_widths = [34, 14, 14, 18, 20, 24, 24, 24]
    for ci, w in enumerate(dash_widths, 1):
        ws_dash.column_dimensions[get_column_letter(ci)].width = w

    # ─────────────────────────────────────────────────────────────────────────
    # SHEET 2: 🛒 ما يجب شراؤه (خطة الاحتياج والتوريد الذكي)
    # ─────────────────────────────────────────────────────────────────────────
    if report_mode in ("comprehensive", "what_to_buy"):
        notify(82, "جاري كتابة ورقة 'ما يجب شراؤه (خطة الاحتياج الذكي)'...")
        chk()

        ws_buy = wb.create_sheet(title="🛒 ما يجب شراؤه (الاحتياج)")
        ws_buy.views.sheetView[0].rightToLeft = True
        ws_buy.freeze_panes = "A2"

        buy_headers = [
            ("Internal\nReference", ALIGN_CTR, "@", 14, FILL_HDR_NAVY),
            ("Barcode", ALIGN_CTR, "@", 16, FILL_HDR_NAVY),
            ("Name", ALIGN_LT, "@", 28, FILL_HDR_NAVY),
            ("Product Name Arabic", ALIGN_RT, "@", 30, FILL_HDR_NAVY),
            ("Products/Tags", ALIGN_RT, "@", 20, FILL_HDR_NAVY),
            ("Product Category", ALIGN_RT, "@", 22, FILL_HDR_NAVY),
            ("Unit", ALIGN_CTR, "@", 10, FILL_HDR_NAVY),
            ("تصنيف\nABC", ALIGN_CTR, "@", 9, FILL_HDR_NAVY),
            ("المورد المعتمد\n(Vendor)", ALIGN_RT, "@", 28, FILL_HDR_NAVY),
            ("رصيد\nالمعارض", ALIGN_CTR, "#,##0", 12, FILL_HDR_TEAL),
            ("رصيد\nالمستودعات", ALIGN_CTR, "#,##0", 12, FILL_HDR_GOLD),
            ("بضاعة بالطريق\n(Open PO)", ALIGN_CTR, "#,##0", 13, FILL_HDR_TEAL),
            (f"إجمالي المبيعات\n({period_label})", ALIGN_CTR, "#,##0", 14, FILL_HDR_NAVY),
            ("معدل البيع\nالشهري", ALIGN_CTR, "#,##0.0", 12, FILL_HDR_NAVY),
            ("أيام التغطية\n(DOI)", ALIGN_CTR, "#,##0", 12, FILL_HDR_NAVY),
            ("أولوية وقرار الشراء", ALIGN_CTR, "@", 24, FILL_HDR_PURPLE),
            (f"الكمية المقترح شراؤها\n(لتغطية {coverage_days} يوم)", ALIGN_CTR, "#,##0", 18, FILL_HDR_GREEN),
            ("آخر سعر شراء\nصافي (ر.س)", ALIGN_RT, "#,##0.00", 14, FILL_HDR_GREEN),
            ("خصم المورد\n(%)", ALIGN_CTR, "0.0%", 11, FILL_HDR_GREEN),
            ("إجمالي تكلفة الشراء\nالمتوقعة (ر.س)", ALIGN_RT, "#,##0.00", 18, FILL_HDR_GREEN),
            ("تاريخ آخر\nشراء", ALIGN_CTR, "@", 13, FILL_HDR_NAVY),
            ("سعر البيع\nالحالي", ALIGN_RT, "#,##0.00", 12, FILL_HDR_NAVY),
            ("هامش الربح\nالفعلي (%)", ALIGN_CTR, "0.0%", 12, FILL_HDR_NAVY),
            ("توصية النظام الذكية\n(شراء / مناقلة / مستودع)", ALIGN_RT, "@", 32, FILL_HDR_PURPLE),
        ]

        for ci, (h_text, _, _, col_w, h_fill) in enumerate(buy_headers, 1):
            c = ws_buy.cell(row=1, column=ci, value=h_text)
            c.font = FONT_HDR
            c.fill = h_fill
            c.alignment = ALIGN_HDR
            c.border = BORDER_CELL
            ws_buy.column_dimensions[get_column_letter(ci)].width = col_w
        ws_buy.row_dimensions[1].height = 32

        # Column letters for live Excel formulas:
        # Col 17 (Q) = Net Buy Qty
        # Col 18 (R) = Net Buy Price
        # Col 20 (T) = Expected Purchase Cost (=Q{row}*R{row})
        for r_idx, r_data in enumerate(replenishment_rows, 2):
            if r_idx % 2000 == 0:
                chk()
            is_alt = (r_idx % 2 == 1)
            row_fill = FILL_ALT if is_alt else None

            formula_cost = f"=Q{r_idx}*R{r_idx}"
            row_vals = [
                r_data["code"],
                r_data["barcode"],
                r_data["name_en"],
                r_data["name_ar"],
                r_data["tags"],
                r_data["category"],
                r_data["uom"],
                r_data["abc"],
                r_data["vendor_name"],
                r_data["sh_stock"],
                r_data["wh_stock"],
                r_data["open_po_qty"],
                r_data["sold_qty"],
                r_data["monthly_sales"],
                r_data["days_cover"],
                r_data["priority"],
                r_data["net_buy_qty"],
                r_data["net_buy_price"],
                r_data["vendor_disc_pct"],
                formula_cost,
                r_data["last_buy_date"],
                r_data["sales_price"],
                r_data["expected_margin"],
                r_data["sys_action"],
            ]
            ws_buy.append(row_vals)

            for ci, (_, c_align, c_fmt, _, _) in enumerate(buy_headers, 1):
                cell = ws_buy.cell(row=r_idx, column=ci)
                cell.alignment = c_align
                cell.border = BORDER_CELL
                if c_fmt != "@":
                    cell.number_format = c_fmt

                if ci == 17:  # Editable Suggested Qty column
                    cell.fill = FILL_INPUT_QTY
                    cell.font = FONT_BOLD
                elif ci == 16:  # Priority status
                    pr_rank = r_data["priority_rank"]
                    if pr_rank == 1:
                        cell.font = FONT_URGENT
                        cell.fill = FILL_URGENT_BG
                    elif pr_rank == 2:
                        cell.font = FONT_WARN
                    elif pr_rank == 3:
                        cell.font = FONT_BLUE
                    elif pr_rank in (4, 5):
                        cell.font = FONT_OK
                    else:
                        cell.font = FONT_MUTED
                elif row_fill:
                    cell.fill = row_fill
                    cell.font = FONT_DATA
                else:
                    cell.font = FONT_DATA

        # Totals Row for Sheet 2
        n_buy = len(replenishment_rows)
        if n_buy > 0:
            tot_r = n_buy + 2
            last_r = n_buy + 1
            for ci, (_, c_align, c_fmt, _, _) in enumerate(buy_headers, 1):
                c = ws_buy.cell(row=tot_r, column=ci)
                c.fill = FILL_TOTAL
                c.font = FONT_TOTAL
                c.alignment = c_align
                c.border = BORDER_TOTAL
                col_let = get_column_letter(ci)
                if ci == 1:
                    c.value = f"=SUBTOTAL(103, A2:A{last_r})"
                    c.number_format = "#,##0"
                elif ci == 4:
                    c.value = "▶ إجمالي خطة الشراء والاحتياج"
                    c.alignment = ALIGN_RT
                elif ci in (10, 11, 12, 13, 17, 20):
                    c.value = f"=SUBTOTAL(9, {col_let}2:{col_let}{last_r})"
                    c.number_format = c_fmt
            ws_buy.row_dimensions[tot_r].height = 24
            ws_buy.auto_filter.ref = f"A1:{get_column_letter(len(buy_headers))}{last_r}"

    # ─────────────────────────────────────────────────────────────────────────
    # SHEET 3: 🧾 ما تم شراؤه (سجل المشتريات والاستلامات الفعلي)
    # ─────────────────────────────────────────────────────────────────────────
    if report_mode in ("comprehensive", "what_was_bought"):
        notify(87, "جاري كتابة ورقة 'ما تم شراؤه (سجل المشتريات والاستلامات)'...")
        chk()

        ws_hist = wb.create_sheet(title="🧾 ما تم شراؤه (المشتريات)")
        ws_hist.views.sheetView[0].rightToLeft = True
        ws_hist.freeze_panes = "A2"

        hist_headers = [
            ("رقم أمر الشراء\n(PO Number)", ALIGN_CTR, "@", 15, FILL_HDR_NAVY),
            ("تاريخ التعميد\n(Order Date)", ALIGN_CTR, "@", 13, FILL_HDR_NAVY),
            ("المورد\n(Vendor)", ALIGN_RT, "@", 28, FILL_HDR_NAVY),
            ("مرجع المورد\n(Vendor Ref)", ALIGN_CTR, "@", 15, FILL_HDR_NAVY),
            ("Internal\nReference", ALIGN_CTR, "@", 14, FILL_HDR_NAVY),
            ("Barcode", ALIGN_CTR, "@", 16, FILL_HDR_NAVY),
            ("Name", ALIGN_LT, "@", 26, FILL_HDR_NAVY),
            ("Product Name Arabic", ALIGN_RT, "@", 28, FILL_HDR_NAVY),
            ("Products/Tags", ALIGN_RT, "@", 18, FILL_HDR_NAVY),
            ("Product Category", ALIGN_RT, "@", 20, FILL_HDR_NAVY),
            ("Unit", ALIGN_CTR, "@", 10, FILL_HDR_NAVY),
            ("الكمية المطلوبة\n(Ordered)", ALIGN_CTR, "#,##0", 13, FILL_HDR_TEAL),
            ("الكمية المستلمة\n(Received)", ALIGN_CTR, "#,##0", 13, FILL_HDR_GREEN),
            ("الكمية المتبقية\n(Pending)", ALIGN_CTR, "#,##0", 13, FILL_HDR_GOLD),
            ("الكمية المفوترة\n(Billed)", ALIGN_CTR, "#,##0", 13, FILL_HDR_NAVY),
            ("سعر الوحدة\nالأساسي", ALIGN_RT, "#,##0.00", 13, FILL_HDR_NAVY),
            ("نسبة الخصم\n(%)", ALIGN_CTR, "0.0%", 11, FILL_HDR_NAVY),
            ("سعر الشراء\nالصافي", ALIGN_RT, "#,##0.00", 13, FILL_HDR_GREEN),
            ("نوع السطر\n(شراء / بونص)", ALIGN_CTR, "@", 16, FILL_HDR_PURPLE),
            ("الإجمالي بدون\nضريبة (ر.س)", ALIGN_RT, "#,##0.00", 16, FILL_HDR_NAVY),
            ("قيمة الضريبة\n(ر.س)", ALIGN_RT, "#,##0.00", 14, FILL_HDR_NAVY),
            ("الإجمالي شامل\nالضريبة (ر.س)", ALIGN_RT, "#,##0.00", 17, FILL_HDR_GREEN),
            ("الرصيد المتبقي\nحالياً بالمخزون", ALIGN_CTR, "#,##0", 14, FILL_HDR_TEAL),
            ("نسبة تصريف\nالدفعة (%)", ALIGN_CTR, "0.0%", 13, FILL_HDR_TEAL),
        ]

        for ci, (h_text, _, _, col_w, h_fill) in enumerate(hist_headers, 1):
            c = ws_hist.cell(row=1, column=ci, value=h_text)
            c.font = FONT_HDR
            c.fill = h_fill
            c.alignment = ALIGN_HDR
            c.border = BORDER_CELL
            ws_hist.column_dimensions[get_column_letter(ci)].width = col_w
        ws_hist.row_dimensions[1].height = 32

        for r_idx, pr in enumerate(period_purchase_rows, 2):
            if r_idx % 2000 == 0:
                chk()
            is_alt = (r_idx % 2 == 1)
            row_fill = FILL_BONUS_BG if pr["is_bonus"] else (FILL_ALT if is_alt else None)

            row_vals = [
                pr["order_name"],
                pr["date"],
                pr["vendor_name"],
                pr["partner_ref"],
                pr["code"],
                pr["barcode"],
                pr["name_en"],
                pr["name_ar"],
                pr["tags"],
                pr["category"],
                pr["uom"],
                pr["ordered_qty"],
                pr["received_qty"],
                pr["pending_qty"],
                pr["invoiced_qty"],
                pr["price_unit"],
                pr["discount_pct"],
                pr["net_price"],
                pr["line_type"],
                pr["subtotal"],
                pr["tax"],
                pr["total"],
                pr["current_stock"],
                pr["sell_through_pct"],
            ]
            ws_hist.append(row_vals)

            for ci, (_, c_align, c_fmt, _, _) in enumerate(hist_headers, 1):
                cell = ws_hist.cell(row=r_idx, column=ci)
                cell.alignment = c_align
                cell.border = BORDER_CELL
                if c_fmt != "@":
                    cell.number_format = c_fmt
                if row_fill:
                    cell.fill = row_fill
                if ci == 19 and pr["is_bonus"]:
                    cell.font = FONT_OK
                else:
                    cell.font = FONT_DATA

        n_hist = len(period_purchase_rows)
        if n_hist > 0:
            tot_r = n_hist + 2
            last_r = n_hist + 1
            for ci, (_, c_align, c_fmt, _, _) in enumerate(hist_headers, 1):
                c = ws_hist.cell(row=tot_r, column=ci)
                c.fill = FILL_TOTAL
                c.font = FONT_TOTAL
                c.alignment = c_align
                c.border = BORDER_TOTAL
                col_let = get_column_letter(ci)
                if ci == 1:
                    c.value = f"=SUBTOTAL(103, A2:A{last_r})"
                    c.number_format = "#,##0"
                elif ci == 3:
                    c.value = "▶ إجماليات المشتريات الفعلية"
                    c.alignment = ALIGN_RT
                elif ci in (12, 13, 14, 15, 20, 21, 22):
                    c.value = f"=SUBTOTAL(9, {col_let}2:{col_let}{last_r})"
                    c.number_format = c_fmt
            ws_hist.row_dimensions[tot_r].height = 24
            ws_hist.auto_filter.ref = f"A1:{get_column_letter(len(hist_headers))}{last_r}"

    # ─────────────────────────────────────────────────────────────────────────
    # SHEET 4: 🤝 تقييم وأداء الموردين (Vendor Performance Scorecard)
    # ─────────────────────────────────────────────────────────────────────────
    if include_vendor_scorecard and vendor_stats:
        notify(91, "جاري إعداد ورقة 'تقييم وأداء الموردين'...")
        chk()

        ws_vend = wb.create_sheet(title="🤝 تقييم وأداء الموردين")
        ws_vend.views.sheetView[0].rightToLeft = True
        ws_vend.freeze_panes = "A2"

        vend_headers = [
            ("اسم المورد\n(Vendor Name)", ALIGN_RT, "@", 34, FILL_HDR_NAVY),
            ("عدد أوامر\nالشراء", ALIGN_CTR, "#,##0", 13, FILL_HDR_NAVY),
            ("عدد الأصناف\n(SKUs)", ALIGN_CTR, "#,##0", 13, FILL_HDR_NAVY),
            ("إجمالي الكميات\nالمطلوبة", ALIGN_CTR, "#,##0", 15, FILL_HDR_TEAL),
            ("إجمالي الكميات\nالمستلمة", ALIGN_CTR, "#,##0", 15, FILL_HDR_GREEN),
            ("نسبة الالتزام بالتوريد\n(Fill Rate %)", ALIGN_CTR, "0.0%", 17, FILL_HDR_PURPLE),
            ("متوسط نسبة\nالخصم (%)", ALIGN_CTR, "0.0%", 14, FILL_HDR_NAVY),
            ("كمية البونص\nالمجاني", ALIGN_CTR, "#,##0", 14, FILL_HDR_GREEN),
            ("قيمة البونص\nبسعر البيع (ر.س)", ALIGN_RT, "#,##0.00", 17, FILL_HDR_GREEN),
            ("إجمالي المشتريات\nبدون ضريبة (ر.س)", ALIGN_RT, "#,##0.00", 18, FILL_HDR_NAVY),
            ("إجمالي المشتريات\nشامل الضريبة (ر.س)", ALIGN_RT, "#,##0.00", 18, FILL_HDR_GREEN),
            ("قيمة المخزون الحالي\nمن بضاعة المورد", ALIGN_RT, "#,##0.00", 18, FILL_HDR_GOLD),
            ("قيمة الشراء المقترح\nالقادم (ر.س)", ALIGN_RT, "#,##0.00", 18, FILL_HDR_PURPLE),
            ("تقييم التزام المورد", ALIGN_CTR, "@", 20, FILL_HDR_NAVY),
        ]

        for ci, (h_text, _, _, col_w, h_fill) in enumerate(vend_headers, 1):
            c = ws_vend.cell(row=1, column=ci, value=h_text)
            c.font = FONT_HDR
            c.fill = h_fill
            c.alignment = ALIGN_HDR
            c.border = BORDER_CELL
            ws_vend.column_dimensions[get_column_letter(ci)].width = col_w
        ws_vend.row_dimensions[1].height = 32

        sorted_vendors = sorted(
            vendor_stats.values(),
            key=lambda x: (x["taxed_total"], x["suggested_po_val"]),
            reverse=True
        )

        for r_idx, vs in enumerate(sorted_vendors, 2):
            is_alt = (r_idx % 2 == 1)
            row_fill = FILL_ALT if is_alt else None

            ord_q = vs["ordered_qty"]
            rcv_q = vs["received_qty"]
            fill_rate = round(min(1.0, rcv_q / ord_q), 4) if ord_q > 0 else 1.0
            avg_disc = round((vs["disc_weighted_sum"] / vs["disc_weight_base"]) / 100.0, 4) if vs["disc_weight_base"] > 0 else 0.0

            if ord_q <= 0:
                rating = "⚪ بدون أوامر في الفترة"
            elif fill_rate >= 0.95:
                rating = "⭐ التزام ممتاز (≥95%)"
            elif fill_rate >= 0.80:
                rating = "✅ التزام جيد (80%-95%)"
            else:
                rating = "⚠️ تأخر/نقص بالتوريد (<80%)"

            row_vals = [
                vs["vendor_name"],
                len(vs["orders_set"]),
                len(vs["skus_set"]),
                ord_q,
                rcv_q,
                fill_rate,
                avg_disc,
                vs["bonus_qty"],
                round(vs["bonus_retail_val"], 2),
                round(vs["untaxed_total"], 2),
                round(vs["taxed_total"], 2),
                round(vs["current_stock_val"], 2),
                round(vs["suggested_po_val"], 2),
                rating,
            ]
            ws_vend.append(row_vals)

            for ci, (_, c_align, c_fmt, _, _) in enumerate(vend_headers, 1):
                cell = ws_vend.cell(row=r_idx, column=ci)
                cell.alignment = c_align
                cell.border = BORDER_CELL
                cell.font = FONT_DATA
                if c_fmt != "@":
                    cell.number_format = c_fmt
                if row_fill:
                    cell.fill = row_fill

        n_v = len(sorted_vendors)
        if n_v > 0:
            tot_r = n_v + 2
            last_r = n_v + 1
            for ci, (_, c_align, c_fmt, _, _) in enumerate(vend_headers, 1):
                c = ws_vend.cell(row=tot_r, column=ci)
                c.fill = FILL_TOTAL
                c.font = FONT_TOTAL
                c.alignment = c_align
                c.border = BORDER_TOTAL
                col_let = get_column_letter(ci)
                if ci == 1:
                    c.value = f"▶ الإجمالي العام ({n_v} مورد)"
                    c.alignment = ALIGN_RT
                elif ci in (2, 3, 4, 5, 8, 9, 10, 11, 12, 13):
                    c.value = f"=SUBTOTAL(9, {col_let}2:{col_let}{last_r})"
                    c.number_format = c_fmt
            ws_vend.row_dimensions[tot_r].height = 24
            ws_vend.auto_filter.ref = f"A1:{get_column_letter(len(vend_headers))}{last_r}"

    # ─────────────────────────────────────────────────────────────────────────
    # SHEET 5: 📈 رقابة تغير أسعار الشراء (Purchase Price Variance Audit)
    # ─────────────────────────────────────────────────────────────────────────
    if include_vendor_scorecard and allow_price_variance and variance_rows:
        notify(94, "جاري إعداد ورقة 'رقابة تغير أسعار الشراء'...")
        chk()

        ws_var = wb.create_sheet(title="📈 رقابة أسعار الشراء")
        ws_var.views.sheetView[0].rightToLeft = True
        ws_var.freeze_panes = "A2"

        var_headers = [
            ("Internal\nReference", ALIGN_CTR, "@", 14, FILL_HDR_NAVY),
            ("Barcode", ALIGN_CTR, "@", 16, FILL_HDR_NAVY),
            ("اسم الصنف", ALIGN_RT, "@", 30, FILL_HDR_NAVY),
            ("Product Category", ALIGN_RT, "@", 20, FILL_HDR_NAVY),
            ("المورد الأخير", ALIGN_RT, "@", 28, FILL_HDR_NAVY),
            ("أمر الشراء\nالسابق", ALIGN_CTR, "@", 14, FILL_HDR_TEAL),
            ("تاريخ الشراء\nالسابق", ALIGN_CTR, "@", 13, FILL_HDR_TEAL),
            ("سعر الشراء\nالسابق (صافي)", ALIGN_RT, "#,##0.00", 14, FILL_HDR_TEAL),
            ("أمر الشراء\nالأخير", ALIGN_CTR, "@", 14, FILL_HDR_GREEN),
            ("تاريخ الشراء\nالأخير", ALIGN_CTR, "@", 13, FILL_HDR_GREEN),
            ("سعر الشراء\nالأخير (صافي)", ALIGN_RT, "#,##0.00", 14, FILL_HDR_GREEN),
            ("أقل سعر شراء\nمسجل", ALIGN_RT, "#,##0.00", 13, FILL_HDR_GOLD),
            ("فرق السعر\n(ر.س)", ALIGN_RT, "+#,##0.00;-#,##0.00;0.00", 13, FILL_HDR_PURPLE),
            ("نسبة التغير\nفي السعر (%)", ALIGN_CTR, "+0.0%;-0.0%;0.0%", 14, FILL_HDR_PURPLE),
            ("الأثر المالي على\nالطلبية الأخيرة", ALIGN_RT, "#,##0.00", 15, FILL_HDR_PURPLE),
            ("سعر البيع\nالحالي", ALIGN_RT, "#,##0.00", 13, FILL_HDR_NAVY),
            ("هامش الربح\nالفعلي (%)", ALIGN_CTR, "0.0%", 13, FILL_HDR_NAVY),
            ("تشخيص السعر والربحية", ALIGN_CTR, "@", 28, FILL_HDR_PURPLE),
        ]

        for ci, (h_text, _, _, col_w, h_fill) in enumerate(var_headers, 1):
            c = ws_var.cell(row=1, column=ci, value=h_text)
            c.font = FONT_HDR
            c.fill = h_fill
            c.alignment = ALIGN_HDR
            c.border = BORDER_CELL
            ws_var.column_dimensions[get_column_letter(ci)].width = col_w
        ws_var.row_dimensions[1].height = 32

        for r_idx, vr in enumerate(variance_rows, 2):
            is_alt = (r_idx % 2 == 1)
            row_fill = FILL_ALT if is_alt else None

            row_vals = [
                vr["code"],
                vr["barcode"],
                vr["name_ar"],
                vr["category"],
                vr["vendor_name"],
                vr["prev_order"],
                vr["prev_date"],
                vr["prev_price"],
                vr["curr_order"],
                vr["curr_date"],
                vr["curr_price"],
                vr["min_price"],
                vr["diff_val"],
                vr["diff_pct"],
                vr["fin_impact"],
                vr["sales_price"],
                vr["margin_pct"],
                vr["status"],
            ]
            ws_var.append(row_vals)

            for ci, (_, c_align, c_fmt, _, _) in enumerate(var_headers, 1):
                cell = ws_var.cell(row=r_idx, column=ci)
                cell.alignment = c_align
                cell.border = BORDER_CELL
                if c_fmt != "@":
                    cell.number_format = c_fmt
                if ci in (13, 14, 18):
                    if vr["diff_pct"] > 0.005:
                        cell.font = FONT_URGENT
                    elif vr["diff_pct"] < -0.005:
                        cell.font = FONT_OK
                    else:
                        cell.font = FONT_DATA
                else:
                    cell.font = FONT_DATA
                if row_fill:
                    cell.fill = row_fill

        ws_var.auto_filter.ref = f"A1:{get_column_letter(len(var_headers))}{len(variance_rows) + 1}"

    # ─────────────────────────────────────────────────────────────────────────
    # SHEET 6: 🚚 طلبيات مفتوحة بالطريق (Open POs & Pending Deliveries)
    # ─────────────────────────────────────────────────────────────────────────
    if open_po_rows:
        ws_open = wb.create_sheet(title="🚚 طلبيات قيد الاستلام")
        ws_open.views.sheetView[0].rightToLeft = True
        ws_open.freeze_panes = "A2"

        open_headers = [
            ("رقم أمر الشراء\n(PO Number)", ALIGN_CTR, "@", 15, FILL_HDR_NAVY),
            ("تاريخ الطلب", ALIGN_CTR, "@", 13, FILL_HDR_NAVY),
            ("أيام الانتظار\nمنذ الطلب", ALIGN_CTR, "#,##0", 13, FILL_HDR_GOLD),
            ("المورد\n(Vendor)", ALIGN_RT, "@", 28, FILL_HDR_NAVY),
            ("Internal\nReference", ALIGN_CTR, "@", 14, FILL_HDR_NAVY),
            ("Barcode", ALIGN_CTR, "@", 16, FILL_HDR_NAVY),
            ("اسم الصنف", ALIGN_RT, "@", 30, FILL_HDR_NAVY),
            ("الكمية المطلوبة", ALIGN_CTR, "#,##0", 14, FILL_HDR_TEAL),
            ("الكمية المستلمة", ALIGN_CTR, "#,##0", 14, FILL_HDR_GREEN),
            ("الكمية المتبقية\n(قيد التوريد)", ALIGN_CTR, "#,##0", 15, FILL_HDR_PURPLE),
            ("سعر الشراء\nالصافي", ALIGN_RT, "#,##0.00", 13, FILL_HDR_NAVY),
            ("قيمة البضاعة\nالمتبقية (ر.س)", ALIGN_RT, "#,##0.00", 16, FILL_HDR_PURPLE),
            ("الرصيد الحالي\nبالمعارض والمستودع", ALIGN_CTR, "#,##0", 15, FILL_HDR_TEAL),
            ("الكمية المباعة\n(خلال فترة المبيعات)", ALIGN_CTR, "#,##0", 16, FILL_HDR_GREEN),
            ("حالة الاستعجال والمتابعة", ALIGN_CTR, "@", 32, FILL_HDR_GOLD),
        ]

        for ci, (h_text, _, _, col_w, h_fill) in enumerate(open_headers, 1):
            c = ws_open.cell(row=1, column=ci, value=h_text)
            c.font = FONT_HDR
            c.fill = h_fill
            c.alignment = ALIGN_HDR
            c.border = BORDER_CELL
            ws_open.column_dimensions[get_column_letter(ci)].width = col_w
        ws_open.row_dimensions[1].height = 32

        for r_idx, op in enumerate(open_po_rows, 2):
            is_alt = (r_idx % 2 == 1)
            row_fill = FILL_URGENT_BG if op["urgency_rank"] == 1 else (FILL_ALT if is_alt else None)

            row_vals = [
                op["order_name"],
                op["date"],
                op["days_waiting"],
                op["vendor_name"],
                op["code"],
                op["barcode"],
                op["name_ar"],
                op["ordered_qty"],
                op["received_qty"],
                op["pending_qty"],
                op["net_price"],
                op["pending_value"],
                op["current_stock"],
                op["sold_qty"],
                op["urgency"],
            ]
            ws_open.append(row_vals)

            for ci, (_, c_align, c_fmt, _, _) in enumerate(open_headers, 1):
                cell = ws_open.cell(row=r_idx, column=ci)
                cell.alignment = c_align
                cell.border = BORDER_CELL
                if c_fmt != "@":
                    cell.number_format = c_fmt
                if row_fill:
                    cell.fill = row_fill
                if ci == 14 and op["sold_qty"] > 0:
                    cell.font = FONT_OK
                elif ci == 15:
                    if op["urgency_rank"] == 1:
                        cell.font = FONT_URGENT
                    elif op["urgency_rank"] == 2:
                        cell.font = FONT_WARN
                    elif op["urgency_rank"] == 3:
                        cell.font = FONT_OK
                    else:
                        cell.font = FONT_MUTED
                else:
                    cell.font = FONT_DATA

        n_op = len(open_po_rows)
        if n_op > 0:
            tot_r = n_op + 2
            last_r = n_op + 1
            for ci, (_, c_align, c_fmt, _, _) in enumerate(open_headers, 1):
                c = ws_open.cell(row=tot_r, column=ci)
                c.fill = FILL_TOTAL
                c.font = FONT_TOTAL
                c.alignment = c_align
                c.border = BORDER_TOTAL
                col_let = get_column_letter(ci)
                if ci == 4:
                    c.value = "▶ إجمالي الطلبيات المفتوحة قيد الاستلام"
                    c.alignment = ALIGN_RT
                elif ci in (8, 9, 10, 12, 13, 14):
                    c.value = f"=SUBTOTAL(9, {col_let}2:{col_let}{last_r})"
                    c.number_format = c_fmt
            ws_open.row_dimensions[tot_r].height = 24
            ws_open.auto_filter.ref = f"A1:{get_column_letter(len(open_headers))}{last_r}"

    # ─────────────────────────────────────────────────────────────────────────
    # SHEET 7: 📄 طلب شراء معتمد (Official Print-Ready RFQ/PO Form)
    # ─────────────────────────────────────────────────────────────────────────
    # Always build the printable sheet when needed_items exist, and ONLY export to PDF when export_rfq_pdf=True
    if needed_items and (export_rfq_pdf or report_mode in ("comprehensive", "what_to_buy")):
        ws_po = wb.create_sheet(title="📄 طلب شراء معتمد")
        ws_po.views.sheetView[0].rightToLeft = True
        ws_po.views.sheetView[0].showGridLines = False

        ws_po.page_setup.orientation = ws_po.ORIENTATION_PORTRAIT
        ws_po.page_setup.paperSize = ws_po.PAPERSIZE_A4
        ws_po.sheet_properties.pageSetUpPr.fitToPage = True
        ws_po.page_setup.fitToWidth = 1
        ws_po.page_setup.fitToHeight = 0

        # Header Banner
        ws_po.merge_cells("A1:H1")
        ws_po["A1"].value = f"{comp_name_ar}  |  {comp_name_en}"
        ws_po["A1"].font = Font(name=FONT_FAMILY, size=14, bold=True, color="FFFFFF")
        ws_po["A1"].fill = PatternFill("solid", fgColor=C_NAVY_DARK)
        ws_po["A1"].alignment = ALIGN_CTR
        ws_po.row_dimensions[1].height = 32

        ws_po.merge_cells("A2:H2")
        ws_po["A2"].value = f"📄 بيان احتياج وطلب شراء بضاعة معتمد (Purchase Order / RFQ) — تغطية {coverage_days} يوم"
        ws_po["A2"].font = Font(name=FONT_FAMILY, size=12, bold=True, color="FFFFFF")
        ws_po["A2"].fill = FILL_HDR_NAVY
        ws_po["A2"].alignment = ALIGN_CTR
        ws_po.row_dimensions[2].height = 26

        ws_po.merge_cells("A3:D3")
        ws_po["A3"].value = f"السادة الموردون: {vendor_filter_txt}"
        ws_po["A3"].font = FONT_BOLD
        ws_po["A3"].alignment = ALIGN_RT

        ws_po.merge_cells("E3:H3")
        ws_po["E3"].value = f"تاريخ الإصدار: {datetime.now().strftime('%Y/%m/%d')}  |  الرقم الضريبي: {profile.get('tax_id', '-')}"
        ws_po["E3"].font = FONT_BOLD
        ws_po["E3"].alignment = ALIGN_LT
        ws_po.row_dimensions[3].height = 22

        po_cols = [
            ("م", ALIGN_CTR, "#,##0", 6),
            ("كود الصنف", ALIGN_CTR, "@", 14),
            ("الباركود", ALIGN_CTR, "@", 16),
            ("اسم الصنف والوصف", ALIGN_RT, "@", 34),
            ("الوحدة", ALIGN_CTR, "@", 10),
            ("الكمية المطلوبة", ALIGN_CTR, "#,##0", 14),
            ("سعر الوحدة الصافي", ALIGN_RT, "#,##0.00", 15),
            ("الإجمالي (ر.س)", ALIGN_RT, "#,##0.00", 16),
        ]
        for ci, (h_txt, _, _, w) in enumerate(po_cols, 1):
            c = ws_po.cell(row=5, column=ci, value=h_txt)
            c.font = FONT_HDR
            c.fill = FILL_HDR_NAVY
            c.alignment = ALIGN_HDR
            c.border = BORDER_CELL
            ws_po.column_dimensions[get_column_letter(ci)].width = w
        ws_po.row_dimensions[5].height = 26

        for idx_p, item in enumerate(needed_items, 1):
            rr = 5 + idx_p
            fill_r = FILL_ALT if idx_p % 2 == 0 else None
            p_vals = [
                idx_p,
                item["code"],
                item["barcode"],
                item["name_ar"] or item["name_en"],
                item["uom"] or "قطعة",
                item["net_buy_qty"],
                item["net_buy_price"],
                f"=F{rr}*G{rr}",
            ]
            for ci, (val, (_, c_al, c_fmt, _)) in enumerate(zip(p_vals, po_cols), 1):
                c = ws_po.cell(row=rr, column=ci, value=val)
                c.font = FONT_DATA
                c.alignment = c_al
                c.border = BORDER_CELL
                if c_fmt != "@":
                    c.number_format = c_fmt
                if fill_r:
                    c.fill = fill_r
            ws_po.row_dimensions[rr].height = 20

        last_item_r = 5 + len(needed_items)
        sum_r1 = last_item_r + 1
        sum_r2 = last_item_r + 2
        sum_r3 = last_item_r + 3

        ws_po.merge_cells(start_row=sum_r1, start_column=1, end_row=sum_r1, end_column=5)
        ws_po.cell(row=sum_r1, column=1, value="إجمالي الكميات والإجمالي قبل الضريبة:").alignment = ALIGN_RT
        ws_po.cell(row=sum_r1, column=1).font = FONT_BOLD
        ws_po.cell(row=sum_r1, column=6, value=f"=SUM(F6:F{last_item_r})").number_format = "#,##0"
        ws_po.cell(row=sum_r1, column=6).font = FONT_BOLD
        ws_po.cell(row=sum_r1, column=6).alignment = ALIGN_CTR
        ws_po.cell(row=sum_r1, column=8, value=f"=SUM(H6:H{last_item_r})").number_format = "#,##0.00"
        ws_po.cell(row=sum_r1, column=8).font = FONT_BOLD

        ws_po.merge_cells(start_row=sum_r2, start_column=1, end_row=sum_r2, end_column=7)
        ws_po.cell(row=sum_r2, column=1, value="ضريبة القيمة المضافة (15% VAT):").alignment = ALIGN_RT
        ws_po.cell(row=sum_r2, column=1).font = FONT_BOLD
        ws_po.cell(row=sum_r2, column=8, value=f"=ROUND(H{sum_r1}*0.15, 2)").number_format = "#,##0.00"
        ws_po.cell(row=sum_r2, column=8).font = FONT_BOLD

        ws_po.merge_cells(start_row=sum_r3, start_column=1, end_row=sum_r3, end_column=7)
        ws_po.cell(row=sum_r3, column=1, value="▶ الصافي الإجمالي شامل الضريبة (ريال سعودي):").alignment = ALIGN_RT
        ws_po.cell(row=sum_r3, column=1).font = FONT_TOTAL
        ws_po.cell(row=sum_r3, column=8, value=f"=H{sum_r1}+H{sum_r2}").number_format = "#,##0.00"
        ws_po.cell(row=sum_r3, column=8).font = FONT_TOTAL

        for sr in (sum_r1, sum_r2, sum_r3):
            ws_po.row_dimensions[sr].height = 22
            for cc in range(1, 9):
                cell_s = ws_po.cell(row=sr, column=cc)
                cell_s.border = BORDER_TOTAL
                if sr == sum_r3:
                    cell_s.fill = FILL_TOTAL

        # Signature Blocks
        sig_r = sum_r3 + 3
        ws_po.merge_cells(start_row=sig_r, start_column=1, end_row=sig_r, end_column=3)
        ws_po.merge_cells(start_row=sig_r, start_column=4, end_row=sig_r, end_column=5)
        ws_po.merge_cells(start_row=sig_r, start_column=6, end_row=sig_r, end_column=8)

        ws_po.cell(row=sig_r, column=1, value="إعداد قسم المشتريات والتوريد\nالتوقيع: ............................").alignment = ALIGN_CTR
        ws_po.cell(row=sig_r, column=4, value="مراجعة الإدارة المالية\nالتوقيع: ............................").alignment = ALIGN_CTR
        ws_po.cell(row=sig_r, column=6, value="اعتماد المدير العام\nالتوقيع والختم: ............................").alignment = ALIGN_CTR
        for cc in (1, 4, 6):
            ws_po.cell(row=sig_r, column=cc).font = FONT_BOLD
        ws_po.row_dimensions[sig_r].height = 42

    # Remove the initial blank sheet
    if len(wb.sheetnames) > 1 and default_ws in wb.worksheets:
        wb.remove(default_ws)

    notify(96, "جاري حفظ مصنف المشتريات الذكي...")
    chk()
    wb.save(output_path)

    pdf_path = None
    if export_rfq_pdf and needed_items:
        notify(98, "جاري تصدير طلب الشراء الرسمي كملف PDF معتمد...")
        base_no_ext = os.path.splitext(output_path)[0]
        target_pdf = f"{base_no_ext}_طلب_شراء_رسمي.pdf"
        pdf_path = export_sheet_to_pdf(output_path, target_pdf, sheet_name="📄 طلب شراء معتمد")

    elapsed = round(time.time() - t_start, 2)
    notify(100, f"✅ اكتمل تصدير منظومة المشتريات في {elapsed} ثانية.")

    top_v_name = "-"
    top_v_spend = 0.0
    if vendor_stats:
        top_v = max(vendor_stats.values(), key=lambda x: x.get("taxed_total", 0.0))
        if top_v.get("taxed_total", 0.0) > 0:
            top_v_name = top_v.get("vendor_name", "-")
            top_v_spend = round(top_v.get("taxed_total", 0.0), 2)

    return {
        "success": True,
        "output_path": output_path,
        "pdf_path": pdf_path,
        "total_rows": len(replenishment_rows) if report_mode != "what_was_bought" else len(period_purchase_rows),
        "replenishment_count": len(replenishment_rows),
        "needed_items_count": len(needed_items),
        "items_to_buy_count": len(needed_items),
        "suggested_po_qty": tot_suggested_po_qty,
        "suggested_po_value": round(tot_suggested_po_val, 2),
        "total_suggested_po_val": round(tot_suggested_po_val, 2),
        "urgent_a_count": urgent_a_count,
        "purchased_lines_count": len(period_purchase_rows),
        "distinct_pos_count": distinct_pos_count,
        "purchased_taxed_total": round(tot_purchased_taxed, 2),
        "total_purchases_net": round(tot_purchased_taxed, 2),
        "bonus_retail_value": round(tot_bonus_retail_val, 2),
        "total_bonus_val": round(tot_bonus_retail_val, 2),
        "open_po_value": round(tot_open_po_val, 2),
        "open_po_val": round(tot_open_po_val, 2),
        "open_po_lines_count": len(open_po_rows),
        "price_inc_count": price_inc_count,
        "price_hikes_count": price_inc_count,
        "active_vendors_count": len(vendor_stats),
        "top_vendor_name": top_v_name,
        "top_vendor_spend": top_v_spend,
        "total_time": elapsed,
    }
