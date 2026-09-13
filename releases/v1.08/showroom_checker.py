"""
showroom_checker.py — محدد احتياجات ورصيد المعرض
Designed & Developed for: شركة العسلي التجارية
Author: عبدالله الخطيب (Abdullah Al-Khatib)
Version: v1.00
"""

import os
import sys
import json
import time
import math
import threading
import xmlrpc.client
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

from licensing import get_machine_id, is_activated, activate_device
from security import get_odoo_credentials

APP_VERSION = "v1.00"
APP_FONT = "Segoe UI"

# ─────────────────────────────────────────────────────────────────────────────
# 🎨 Design Palette (Tailored for 15-inch POS & retail displays)
# ─────────────────────────────────────────────────────────────────────────────
BRAND_GOLD         = "#D4A017"
BRAND_BLUE         = "#1E6EBA"
BRAND_BLUE_HOVER   = "#1558A0"
BRAND_GREEN        = "#10B981"  # Emerald Green for Deficit / Needs Order (> 0)
BRAND_GREEN_BG     = ("#D1FAE5", "#064E3B")
BRAND_RED          = "#EF4444"  # Crimson Red for Surplus / Overstocked (< 0)
BRAND_RED_BG       = ("#FEE2E2", "#7F1D1D")
BRAND_NEUTRAL      = "#64748B"  # Slate for Balanced (= 0)
BRAND_NEUTRAL_BG   = ("#F1F5F9", "#1E293B")
BRAND_DARK_BG      = "#0B1320"
CARD_DARK_BG       = "#162235"
CARD_LIGHT_BG      = "#FFFFFF"
BORDER_COLOR       = ("#CBD5E1", "#223249")


# ─────────────────────────────────────────────────────────────────────────────
# ⚙️ Settings Persistence
# ─────────────────────────────────────────────────────────────────────────────
def _get_settings_path():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    dir_path = os.path.join(appdata, "AlAssaliOdooExporter")
    os.makedirs(dir_path, exist_ok=True)
    return os.path.join(dir_path, "showroom_checker_settings.json")

def load_settings():
    p = _get_settings_path()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "theme": "Dark",
        "last_showroom_id": None,
        "last_period": "this_year",
        "last_need_months": 2,
    }

def save_settings(data):
    p = _get_settings_path()
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# 🏢 Showrooms & Odoo Data Layer
# ─────────────────────────────────────────────────────────────────────────────
def safe_execute_kw(models, db, uid, password, obj, method, args, kw=None, max_retries=4):
    """Network-resilient XML-RPC caller with automatic retry logic."""
    if kw is None:
        kw = {}
    for attempt in range(1, max_retries + 1):
        try:
            return models.execute_kw(db, uid, password, obj, method, args, kw)
        except Exception as e:
            if attempt == max_retries:
                raise
            time.sleep(attempt * 1.2)


def get_active_showrooms():
    """
    Returns list of active POS showrooms with warehouse lot_stock_id and POS config IDs.
    Matches the exact mapping used across the Al-Assali systems.
    """
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


def calculate_period_days_and_domain(period, custom_from=None, custom_to=None):
    """Returns (date_filter_domain, period_days) based on period mode."""
    today = datetime.now()
    date_filter = []
    period_days = 365

    if period == "last_30_days":
        date_filter.append(['date', '>=', (today - timedelta(days=30)).strftime('%Y-%m-%d 00:00:00')])
        period_days = 30
    elif period == "last_60_days":
        date_filter.append(['date', '>=', (today - timedelta(days=60)).strftime('%Y-%m-%d 00:00:00')])
        period_days = 60
    elif period == "last_90_days":
        date_filter.append(['date', '>=', (today - timedelta(days=90)).strftime('%Y-%m-%d 00:00:00')])
        period_days = 90
    elif period in ("last_365_days", "365d"):
        date_filter.append(['date', '>=', (today - timedelta(days=365)).strftime('%Y-%m-%d 00:00:00')])
        period_days = 365
    elif period == "this_year":
        date_filter.append(['date', '>=', f"{today.year}-01-01 00:00:00"])
        start_year = datetime(today.year, 1, 1)
        period_days = max(1, (today - start_year).days + 1)
    elif period == "all":
        period_days = 365
    elif period == "custom" and custom_from:
        date_filter.append(['date', '>=', f"{custom_from} 00:00:00"])
        if custom_to:
            date_filter.append(['date', '<=', f"{custom_to} 23:59:59"])
            try:
                d1 = datetime.strptime(custom_from, "%Y-%m-%d")
                d2 = datetime.strptime(custom_to, "%Y-%m-%d")
                period_days = max(1, (d2 - d1).days + 1)
            except Exception:
                period_days = 30
        else:
            try:
                d1 = datetime.strptime(custom_from, "%Y-%m-%d")
                period_days = max(1, (today - d1).days + 1)
            except Exception:
                period_days = 30

    return date_filter, period_days


def query_product_and_needs(barcode_input, showroom, period, need_months, custom_from=None, custom_to=None):
    """
    Looks up an item in Odoo by barcode (primary, packaging, or internal reference).
    Fetches real-time stock and sales for the target showroom and computes net need.
    """
    clean_code = str(barcode_input).strip()
    if not clean_code:
        return None, "يرجى إدخال أو مسح الباركود."

    url, db, username, password = get_odoo_credentials()
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, username, password, {})
    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

    # 1. Search product directly by barcode or default_code
    p_ids = safe_execute_kw(
        models, db, uid, password, 'product.product', 'search',
        [[['active', '=', True],
          '|', ['barcode', '=', clean_code], ['default_code', '=ilike', clean_code]]],
        {'limit': 1}
    )

    # 2. If not found, check product.packaging by barcode
    matched_pkg_barcode = None
    if not p_ids:
        pkg_records = safe_execute_kw(
            models, db, uid, password, 'product.packaging', 'search_read',
            [[['barcode', '=ilike', clean_code]]],
            {'fields': ['product_id', 'barcode'], 'limit': 1}
        )
        if pkg_records and pkg_records[0].get('product_id'):
            p_ids = [pkg_records[0]['product_id'][0]]
            matched_pkg_barcode = clean_code

    if not p_ids:
        return None, f"الصنف غير مسجل في النظام بالباركود / الكود: {clean_code}"

    pid = p_ids[0]

    # Parallel auxiliary fetch: details, packaging, stock quant, pos sales
    date_filter, period_days = calculate_period_days_and_domain(period, custom_from, custom_to)
    lot_stock_id = showroom.get('lot_stock_id')
    pos_config_ids = showroom.get('pos_config_ids', [])

    def _fetch_product():
        m = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        fields = ['id', 'default_code', 'barcode', 'name', 'product_name_arabic', 'uom_id']
        res = safe_execute_kw(m, db, uid, password, 'product.product', 'read', [[pid]], {'fields': fields})
        return res[0] if res else {}

    def _fetch_packagings():
        m = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        res = safe_execute_kw(m, db, uid, password, 'product.packaging', 'search_read',
                              [[['product_id', '=', pid], ['barcode', '!=', False]]],
                              {'fields': ['barcode', 'name', 'qty']})
        return res or []

    def _fetch_stock():
        if not lot_stock_id:
            return 0.0
        m = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        res = safe_execute_kw(m, db, uid, password, 'stock.quant', 'search_read',
                              [[['product_id', '=', pid], ['location_id', '=', lot_stock_id]]],
                              {'fields': ['quantity']})
        return sum([float(q.get('quantity') or 0.0) for q in res])

    def _fetch_sales():
        if not pos_config_ids:
            return 0.0
        m = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        dom = [['product_id', '=', pid],
               ['state', 'in', ['paid', 'done', 'invoiced']],
               ['config_id', 'in', pos_config_ids]] + date_filter
        res = safe_execute_kw(m, db, uid, password, 'report.pos.order', 'read_group',
                              [dom, ['product_qty:sum'], []],
                              {'lazy': False})
        if res and res[0].get('product_qty'):
            return float(res[0]['product_qty'])
        return 0.0

    with ThreadPoolExecutor(max_workers=4) as ex:
        f_p = ex.submit(_fetch_product)
        f_pkg = ex.submit(_fetch_packagings)
        f_stk = ex.submit(_fetch_stock)
        f_sl = ex.submit(_fetch_sales)

    p_data = f_p.result()
    pkg_list = f_pkg.result()
    stock_qty = f_stk.result()
    sold_qty = f_sl.result()

    # Calculations
    monthly_rate = (sold_qty / float(period_days)) * 30.0 if period_days > 0 else (sold_qty / 12.0)
    target_need = round(monthly_rate * float(need_months), 2)
    net_need = round(target_need - stock_qty, 2)

    # Packaging barcodes formatting
    all_pkg_bcs = [str(p.get('barcode')).strip() for p in pkg_list if p.get('barcode')]
    pkg_str = ", ".join(all_pkg_bcs) if all_pkg_bcs else "-"

    uom_name = p_data.get('uom_id')[1] if isinstance(p_data.get('uom_id'), (list, tuple)) else "قطعة"

    return {
        'id': pid,
        'default_code': p_data.get('default_code') or '-',
        'barcode': p_data.get('barcode') or '-',
        'packaging_barcodes': pkg_str,
        'matched_pkg_barcode': matched_pkg_barcode,
        'name_en': p_data.get('name') or '-',
        'name_ar': p_data.get('product_name_arabic') or '-',
        'uom': uom_name,
        'stock_qty': round(stock_qty, 2),
        'sold_qty': round(sold_qty, 2),
        'period_days': period_days,
        'monthly_rate': round(monthly_rate, 2),
        'target_need': target_need,
        'need_months': need_months,
        'net_need': net_need,
        'scanned_code': clean_code,
        'timestamp': datetime.now().strftime("%H:%M:%S")
    }, None


# ─────────────────────────────────────────────────────────────────────────────
# 🖥️ Main Application GUI
# ─────────────────────────────────────────────────────────────────────────────
class ShowroomCheckerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.settings = load_settings()
        ctk.set_appearance_mode(self.settings.get("theme", "Dark"))
        ctk.set_default_color_theme("blue")

        self.title(f"🏬 محدد احتياجات ورصيد المعرض — شركة العسلي التجارية [{APP_VERSION}]")
        self._center_window(1100, 740)
        self.minsize(960, 620)

        # Set App Icon if present
        self._set_app_icon()

        self.showrooms = []
        self.showroom_map = {}
        self.recent_scans = []
        self._is_querying = False
        self._pending_code = None
        self._scan_timer = None
        self._last_key_time = 0.0
        self._rapid_keystroke_count = 0
        self.current_product = None
        self.current_raw_input = None

        if not is_activated():
            self._build_activation_screen()
        else:
            self._build_main_ui()

    def _set_app_icon(self):
        try:
            base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
            icon_file = os.path.join(base_dir, "assets", "AssaliLogoColor.png")
            if os.path.exists(icon_file):
                from PIL import Image, ImageTk
                img = ImageTk.PhotoImage(Image.open(icon_file))
                self.iconphoto(False, img)
        except Exception:
            pass

    def _center_window(self, w, h):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ═════════════════════════════════════════════════════════════════════════
    # 🔒 ACTIVATION SCREEN (Keygen_Admin license verification)
    # ═════════════════════════════════════════════════════════════════════════
    def _build_activation_screen(self):
        self._center_window(640, 620)
        self.resizable(False, False)

        for w in self.winfo_children():
            w.destroy()

        outer = ctk.CTkFrame(self, fg_color=("gray95", "#0F172A"), corner_radius=0)
        outer.pack(fill="both", expand=True)

        bar = ctk.CTkFrame(outer, fg_color=BRAND_GOLD, height=5, corner_radius=0)
        bar.pack(fill="x")

        card = ctk.CTkFrame(outer, corner_radius=14, fg_color=("white", "#1E293B"),
                            border_width=1, border_color=("gray85", "#334155"))
        card.pack(fill="both", expand=True, padx=25, pady=(15, 8))

        header_frame = ctk.CTkFrame(card, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(15, 6))

        ctk.CTkLabel(header_frame, text="🏬", font=ctk.CTkFont(size=36)).pack()
        ctk.CTkLabel(header_frame, text="محدد احتياجات ورصيد المعرض",
                     font=ctk.CTkFont(APP_FONT, 18, "bold"), text_color=BRAND_GOLD).pack(pady=(4, 0))
        ctk.CTkLabel(header_frame, text="شركة العسلي التجارية — تفعيل رخصة الاستخدام  |  تصميم/ عبدالله الخطيب",
                     font=ctk.CTkFont(APP_FONT, 11), text_color=BRAND_NEUTRAL).pack()

        mid_card = ctk.CTkFrame(card, corner_radius=8, fg_color=("gray95", "#0F172A"),
                                border_width=1, border_color=("gray80", "#334155"))
        mid_card.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(mid_card, text="معرّف هذا الجهاز (Machine ID):",
                     font=ctk.CTkFont(APP_FONT, 11), text_color=BRAND_NEUTRAL).pack(anchor="e", padx=14, pady=(8, 2))

        mid_val = get_machine_id()
        mid_entry = ctk.CTkEntry(mid_card, height=36, font=ctk.CTkFont("Consolas", 14, "bold"),
                                 justify="center", fg_color=("white", "#1E293B"))
        mid_entry.insert(0, mid_val)
        mid_entry.configure(state="readonly")
        mid_entry.pack(fill="x", padx=14, pady=(0, 6))

        def _copy_mid():
            self.clipboard_clear()
            self.clipboard_append(mid_val)
            messagebox.showinfo("تم النسخ", "✅ تم نسخ معرّف الجهاز إلى الحافظة بنجاح.")

        ctk.CTkButton(mid_card, text="📋  نسخ معرّف الجهاز", height=28,
                      font=ctk.CTkFont(APP_FONT, 11), fg_color=BRAND_NEUTRAL,
                      command=_copy_mid).pack(pady=(0, 8))

        key_frame = ctk.CTkFrame(card, fg_color="transparent")
        key_frame.pack(fill="x", padx=20, pady=(5, 0))

        ctk.CTkLabel(key_frame, text="مفتاح التفعيل (Activation Key):",
                     font=ctk.CTkFont(APP_FONT, 11, "bold")).pack(anchor="e", pady=(0, 4))

        key_entry = ctk.CTkEntry(key_frame, height=40, font=ctk.CTkFont("Consolas", 14, "bold"),
                                 placeholder_text="XXXX-XXXX-XXXX-XXXX", justify="center")
        key_entry.pack(fill="x")

        status_lbl = ctk.CTkLabel(card, text="", font=ctk.CTkFont(APP_FONT, 11))
        status_lbl.pack(pady=4)

        def _do_activate():
            key = key_entry.get().strip()
            if not key:
                status_lbl.configure(text="⚠️ يرجى إدخال مفتاح التفعيل.", text_color=BRAND_RED)
                return
            ok, msg = activate_device(key)
            if ok:
                messagebox.showinfo("تم التفعيل بنجاح", "🎉 تم تفعيل هذا الجهاز بنجاح! جاري فتح البرنامج...")
                self._center_window(1100, 740)
                self.resizable(True, True)
                self._build_main_ui()
            else:
                status_lbl.configure(text=f"❌ {msg}", text_color=BRAND_RED)

        ctk.CTkButton(card, text="🔑  تفعيل البرنامج الآن",
                      font=ctk.CTkFont(APP_FONT, 13, "bold"),
                      fg_color=BRAND_BLUE, hover_color=BRAND_BLUE_HOVER,
                      height=40, command=_do_activate).pack(fill="x", padx=20, pady=(4, 12))

    # ═════════════════════════════════════════════════════════════════════════
    # 🏬 MAIN APPLICATION UI
    # ═════════════════════════════════════════════════════════════════════════
    def _build_main_ui(self):
        for w in self.winfo_children():
            w.destroy()

        self.resizable(True, True)

        # ── Top Bar ──────────────────────────────────────────────────────────
        top_bar = ctk.CTkFrame(self, fg_color=CARD_DARK_BG if self.settings.get("theme") == "Dark" else CARD_LIGHT_BG,
                               height=60, corner_radius=0, border_width=1, border_color=BORDER_COLOR)
        top_bar.pack(fill="x")
        top_bar.pack_propagate(False)

        # Accent Gold strip
        ctk.CTkFrame(top_bar, fg_color=BRAND_GOLD, width=6, corner_radius=0).pack(side="right", fill="y")

        # Right branding
        brand_f = ctk.CTkFrame(top_bar, fg_color="transparent")
        brand_f.pack(side="right", padx=16, pady=6)
        ctk.CTkLabel(brand_f, text="🏬  محدد احتياجات ورصيد المعرض",
                     font=ctk.CTkFont(APP_FONT, 16, "bold"), text_color=BRAND_GOLD).pack(anchor="e")

        sub_f = ctk.CTkFrame(brand_f, fg_color="transparent")
        sub_f.pack(anchor="e")
        ctk.CTkLabel(sub_f, text="شركة العسلي التجارية — فحص المخزون والاحتياج اللحظي بالباركود",
                     font=ctk.CTkFont(APP_FONT, 10), text_color=BRAND_NEUTRAL).pack(side="right")
        ctk.CTkLabel(sub_f, text="  |  ",
                     font=ctk.CTkFont(APP_FONT, 10), text_color=BRAND_NEUTRAL).pack(side="right")
        ctk.CTkLabel(sub_f, text="تصميم/ عبدالله الخطيب",
                     font=ctk.CTkFont(APP_FONT, 10, "bold"), text_color=BRAND_GOLD).pack(side="right")

        # Left options (Theme, Status)
        left_f = ctk.CTkFrame(top_bar, fg_color="transparent")
        left_f.pack(side="left", padx=16, pady=8)

        self._theme_btn = ctk.CTkButton(left_f, text="🌓 مظهر", width=75, height=30,
                                        fg_color=BRAND_NEUTRAL, font=ctk.CTkFont(APP_FONT, 11),
                                        command=self._toggle_theme)
        self._theme_btn.pack(side="left", padx=4)

        self._status_badge = ctk.CTkLabel(left_f, text="🟢 متصل بنظام Odoo", font=ctk.CTkFont(APP_FONT, 11),
                                          text_color=BRAND_GREEN)
        self._status_badge.pack(side="left", padx=10)

        # ── Main Scrollable Container ─────────────────────────────────────────
        main_container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=16, pady=10)

        # ── 1. Top Controls Card (Showroom, Period, Horizon) ──────────────────
        ctrl_card = ctk.CTkFrame(main_container, fg_color=("white", CARD_DARK_BG),
                                 corner_radius=10, border_width=1, border_color=BORDER_COLOR)
        ctrl_card.pack(fill="x", pady=(0, 10))

        ctrl_inner = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        ctrl_inner.pack(fill="x", padx=14, pady=12)

        # Showroom Selector
        sh_col = ctk.CTkFrame(ctrl_inner, fg_color="transparent")
        sh_col.pack(side="right", fill="x", expand=True, padx=8)
        ctk.CTkLabel(sh_col, text="🏬  المعرض المستهدف:", font=ctk.CTkFont(APP_FONT, 12, "bold")).pack(anchor="e", pady=(0, 4))
        self._showroom_var = ctk.StringVar(value="جاري تحميل المعارض...")
        self._showroom_menu = ctk.CTkOptionMenu(sh_col, variable=self._showroom_var,
                                                values=["جاري تحميل المعارض..."],
                                                height=36, font=ctk.CTkFont(APP_FONT, 12, "bold"),
                                                fg_color=BRAND_BLUE, button_color=BRAND_BLUE_HOVER,
                                                command=self._on_showroom_change)
        self._showroom_menu.pack(fill="x")

        # Period Selector
        per_col = ctk.CTkFrame(ctrl_inner, fg_color="transparent")
        per_col.pack(side="right", fill="x", expand=True, padx=8)
        ctk.CTkLabel(per_col, text="📅  فترة قياس المبيعات:", font=ctk.CTkFont(APP_FONT, 12, "bold")).pack(anchor="e", pady=(0, 4))
        self.period_labels = {
            "العام الحالي (افتراضي)": "this_year",
            "آخر 30 يوماً": "last_30_days",
            "آخر 60 يوماً": "last_60_days",
            "آخر 90 يوماً": "last_90_days",
            "آخر 365 يوماً": "last_365_days",
            "كل الفترات": "all",
            "فترة مخصصة...": "custom"
        }
        self.period_labels_rev = {v: k for k, v in self.period_labels.items()}
        saved_per = self.settings.get("last_period", "this_year")
        default_per_lbl = self.period_labels_rev.get(saved_per, "العام الحالي (افتراضي)")
        self._period_var = ctk.StringVar(value=default_per_lbl)
        self._period_menu = ctk.CTkOptionMenu(per_col, variable=self._period_var,
                                              values=list(self.period_labels.keys()),
                                              height=36, font=ctk.CTkFont(APP_FONT, 11),
                                              fg_color=BRAND_NEUTRAL,
                                              command=self._on_period_change)
        self._period_menu.pack(fill="x")

        # Needs Horizon Months Selector
        months_col = ctk.CTkFrame(ctrl_inner, fg_color="transparent")
        months_col.pack(side="right", padx=8)
        ctk.CTkLabel(months_col, text="⏱️  شهور الاحتياج:", font=ctk.CTkFont(APP_FONT, 12, "bold")).pack(anchor="e", pady=(0, 4))
        self.month_options = [f"{m} شهر" if m <= 2 or m >= 11 else f"{m} أشهر" for m in range(1, 13)]
        saved_m = self.settings.get("last_need_months", 2)
        default_m_str = f"{saved_m} شهر" if saved_m <= 2 or saved_m >= 11 else f"{saved_m} أشهر"
        if default_m_str not in self.month_options:
            default_m_str = self.month_options[1]
        self._months_var = ctk.StringVar(value=default_m_str)
        self._months_menu = ctk.CTkOptionMenu(months_col, variable=self._months_var,
                                              values=self.month_options, width=110,
                                              height=36, font=ctk.CTkFont(APP_FONT, 12, "bold"),
                                              fg_color=BRAND_GOLD, button_color="#B8860B",
                                              text_color="black",
                                              command=self._on_months_change)
        self._months_menu.pack()

        # Custom date range frame (hidden by default unless 'custom' is selected)
        self._custom_dates_frame = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        ctk.CTkLabel(self._custom_dates_frame, text="من:", font=ctk.CTkFont(APP_FONT, 11)).pack(side="right", padx=4)
        self._date_from = ctk.CTkEntry(self._custom_dates_frame, width=115, height=30)
        self._date_from.insert(0, (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"))
        self._date_from.pack(side="right", padx=4)
        self._date_from.bind("<Return>", lambda _: self._apply_custom_dates())

        ctk.CTkLabel(self._custom_dates_frame, text="إلى:", font=ctk.CTkFont(APP_FONT, 11)).pack(side="right", padx=4)
        self._date_to = ctk.CTkEntry(self._custom_dates_frame, width=115, height=30)
        self._date_to.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self._date_to.pack(side="right", padx=4)
        self._date_to.bind("<Return>", lambda _: self._apply_custom_dates())

        ctk.CTkButton(self._custom_dates_frame, text="تطبيق 🔄", width=70, height=28,
                      font=ctk.CTkFont(APP_FONT, 11), fg_color=BRAND_BLUE,
                      command=self._apply_custom_dates).pack(side="right", padx=8)

        if saved_per == "custom":
            self._custom_dates_frame.pack(fill="x", padx=14, pady=(0, 8))

        # ── 2. Hero Barcode Input Bar ─────────────────────────────────────────
        bc_card = ctk.CTkFrame(main_container, fg_color=("white", CARD_DARK_BG),
                               corner_radius=10, border_width=2, border_color=BRAND_BLUE)
        bc_card.pack(fill="x", pady=(0, 10))

        bc_row = ctk.CTkFrame(bc_card, fg_color="transparent")
        bc_row.pack(fill="x", padx=14, pady=10)

        self._btn_reset = ctk.CTkButton(bc_row, text="مسح ⌫", width=75, height=44,
                                        font=ctk.CTkFont(APP_FONT, 12),
                                        fg_color=BRAND_NEUTRAL, hover_color="#475569",
                                        command=self._clear_view)
        self._btn_reset.pack(side="left", padx=(0, 6))

        self._btn_search = ctk.CTkButton(bc_row, text="🔍 بحث", width=100, height=44,
                                         font=ctk.CTkFont(APP_FONT, 13, "bold"),
                                         fg_color=BRAND_BLUE, hover_color=BRAND_BLUE_HOVER,
                                         command=self._trigger_lookup)
        self._btn_search.pack(side="left", padx=(0, 10))

        self._barcode_entry = ctk.CTkEntry(
            bc_row,
            height=46,
            font=ctk.CTkFont(APP_FONT, 15, "bold"),
            placeholder_text="📷  امسح الباركود بالقارئ الآلي (يبدأ البحث تلقائياً بدون Enter)...",
            justify="right"
        )
        self._barcode_entry.pack(side="right", fill="x", expand=True)
        self._barcode_entry.bind("<Return>", self._on_enter_or_tab)
        self._barcode_entry.bind("<KP_Enter>", self._on_enter_or_tab)
        self._barcode_entry.bind("<Tab>", self._on_enter_or_tab)
        self._barcode_entry.bind("<KeyRelease>", self._on_barcode_key_release)

        # Subtle badge indicating smart auto-scan without Enter
        bc_hint_row = ctk.CTkFrame(bc_card, fg_color="transparent")
        bc_hint_row.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkLabel(bc_hint_row, text="⚡ مسح تلقائي فوري: يبدأ البحث تلقائياً بمجرد مسح الباركود دون الحاجة للضغط على زر Enter",
                     font=ctk.CTkFont(APP_FONT, 10), text_color=BRAND_NEUTRAL).pack(side="right")

        # Global Esc key to reset view and refocus
        self.bind("<Escape>", lambda _: self._clear_view())

        # ── 3. KPI Dashboard Tiles (Stock, Sales, Net Need) ───────────────────
        kpi_row = ctk.CTkFrame(main_container, fg_color="transparent")
        kpi_row.pack(fill="x", pady=(0, 10))

        # Card 1: On-Hand Stock
        self.card_stock = ctk.CTkFrame(kpi_row, fg_color=("white", CARD_DARK_BG),
                                       corner_radius=10, border_width=1, border_color=BORDER_COLOR)
        self.card_stock.pack(side="right", fill="both", expand=True, padx=(8, 0))

        ctk.CTkLabel(self.card_stock, text="🏬  رصيد المعرض الحالي",
                     font=ctk.CTkFont(APP_FONT, 13, "bold"), text_color=BRAND_NEUTRAL).pack(anchor="e", padx=16, pady=(12, 0))
        self.lbl_stock_val = ctk.CTkLabel(self.card_stock, text="-",
                                          font=ctk.CTkFont(APP_FONT, 34, "bold"), text_color=BRAND_BLUE)
        self.lbl_stock_val.pack(padx=16, pady=(4, 0))
        self.lbl_stock_unit = ctk.CTkLabel(self.card_stock, text="الرصيد الفعلي المتوفر",
                                           font=ctk.CTkFont(APP_FONT, 11), text_color=BRAND_NEUTRAL)
        self.lbl_stock_unit.pack(padx=16, pady=(0, 12))

        # Card 2: Sold in Period
        self.card_sold = ctk.CTkFrame(kpi_row, fg_color=("white", CARD_DARK_BG),
                                      corner_radius=10, border_width=1, border_color=BORDER_COLOR)
        self.card_sold.pack(side="right", fill="both", expand=True, padx=4)

        ctk.CTkLabel(self.card_sold, text="📈  المبيعات خلال الفترة",
                     font=ctk.CTkFont(APP_FONT, 13, "bold"), text_color=BRAND_NEUTRAL).pack(anchor="e", padx=16, pady=(12, 0))
        self.lbl_sold_val = ctk.CTkLabel(self.card_sold, text="-",
                                         font=ctk.CTkFont(APP_FONT, 34, "bold"), text_color=BRAND_GOLD)
        self.lbl_sold_val.pack(padx=16, pady=(4, 0))
        self.lbl_sold_rate = ctk.CTkLabel(self.card_sold, text="معدل المبيعات الشهري: -",
                                          font=ctk.CTkFont(APP_FONT, 11), text_color=BRAND_NEUTRAL)
        self.lbl_sold_rate.pack(padx=16, pady=(0, 12))

        # Card 3: Net Showroom Need
        self.card_need = ctk.CTkFrame(kpi_row, fg_color=("white", CARD_DARK_BG),
                                      corner_radius=10, border_width=2, border_color=BRAND_NEUTRAL)
        self.card_need.pack(side="right", fill="both", expand=True, padx=(0, 8))

        ctk.CTkLabel(self.card_need, text="🎯  احتياج المعرض بعد خصم الرصيد",
                     font=ctk.CTkFont(APP_FONT, 13, "bold"), text_color=BRAND_NEUTRAL).pack(anchor="e", padx=16, pady=(12, 0))
        self.lbl_need_val = ctk.CTkLabel(self.card_need, text="-",
                                         font=ctk.CTkFont(APP_FONT, 36, "bold"), text_color=BRAND_NEUTRAL)
        self.lbl_need_val.pack(padx=16, pady=(2, 0))
        self.lbl_need_badge = ctk.CTkLabel(self.card_need, text="بانتظار مسح صنف...",
                                           font=ctk.CTkFont(APP_FONT, 12, "bold"), text_color=BRAND_NEUTRAL)
        self.lbl_need_badge.pack(padx=16, pady=(0, 12))

        # ── 4. Product Details Card ───────────────────────────────────────────
        prod_card = ctk.CTkFrame(main_container, fg_color=("white", CARD_DARK_BG),
                                 corner_radius=10, border_width=1, border_color=BORDER_COLOR)
        prod_card.pack(fill="x", pady=(0, 10))

        prod_inner = ctk.CTkFrame(prod_card, fg_color="transparent")
        prod_inner.pack(fill="x", padx=16, pady=12)

        # Names
        self.lbl_prod_name_ar = ctk.CTkLabel(prod_inner, text="يرجى مسح باركود الصنف للبدء...",
                                             font=ctk.CTkFont(APP_FONT, 16, "bold"),
                                             anchor="e", text_color=BRAND_GOLD)
        self.lbl_prod_name_ar.pack(fill="x", pady=(0, 2))

        self.lbl_prod_name_en = ctk.CTkLabel(prod_inner, text="Scan or enter product barcode above",
                                             font=ctk.CTkFont(APP_FONT, 12),
                                             anchor="e", text_color=BRAND_NEUTRAL)
        self.lbl_prod_name_en.pack(fill="x", pady=(0, 8))

        # Details line (Code, Barcode, Packaging)
        details_grid = ctk.CTkFrame(prod_inner, fg_color=("gray95", "#0F172A"), corner_radius=6)
        details_grid.pack(fill="x", pady=2)

        d_inner = ctk.CTkFrame(details_grid, fg_color="transparent")
        d_inner.pack(fill="x", padx=10, pady=8)

        # Internal ref
        f_ref = ctk.CTkFrame(d_inner, fg_color="transparent")
        f_ref.pack(side="right", fill="x", expand=True)
        ctk.CTkLabel(f_ref, text="كود الصنف (Internal Ref):", font=ctk.CTkFont(APP_FONT, 10, "bold"), text_color=BRAND_NEUTRAL).pack(anchor="e")
        self.lbl_val_code = ctk.CTkLabel(f_ref, text="-", font=ctk.CTkFont("Consolas", 13, "bold"))
        self.lbl_val_code.pack(anchor="e")

        # Barcode
        f_bc = ctk.CTkFrame(d_inner, fg_color="transparent")
        f_bc.pack(side="right", fill="x", expand=True)
        ctk.CTkLabel(f_bc, text="الباركود الرئيسي (Barcode):", font=ctk.CTkFont(APP_FONT, 10, "bold"), text_color=BRAND_NEUTRAL).pack(anchor="e")
        self.lbl_val_bc = ctk.CTkLabel(f_bc, text="-", font=ctk.CTkFont("Consolas", 13, "bold"))
        self.lbl_val_bc.pack(anchor="e")

        # Packaging Barcodes
        f_pkg = ctk.CTkFrame(d_inner, fg_color="transparent")
        f_pkg.pack(side="right", fill="x", expand=True)
        ctk.CTkLabel(f_pkg, text="باركودات العبوات (Packages):", font=ctk.CTkFont(APP_FONT, 10, "bold"), text_color=BRAND_NEUTRAL).pack(anchor="e")
        self.lbl_val_pkg = ctk.CTkLabel(f_pkg, text="-", font=ctk.CTkFont("Consolas", 12))
        self.lbl_val_pkg.pack(anchor="e")

        # ── 5. Recent Scans Log Table ─────────────────────────────────────────
        hist_header = ctk.CTkFrame(main_container, fg_color="transparent")
        hist_header.pack(fill="x", pady=(4, 4))
        ctk.CTkLabel(hist_header, text="🕒  سجل الأصناف الممسوحة مؤخراً (انقر على أي صنف لإعادة عرضه):",
                     font=ctk.CTkFont(APP_FONT, 12, "bold"), text_color=BRAND_NEUTRAL).pack(side="right")

        self.hist_scroll = ctk.CTkScrollableFrame(main_container, height=190, fg_color=("white", CARD_DARK_BG),
                                                 corner_radius=8, border_width=1, border_color=BORDER_COLOR)
        self.hist_scroll.pack(fill="both", expand=True, pady=(0, 4))

        self._render_history_table()

        # Load showrooms in background
        self._load_showrooms_async()

        # Keep initial focus on barcode entry
        self.after(200, self._refocus_barcode)

    # ═════════════════════════════════════════════════════════════════════════
    # ⚙️ Events, Recalculation & Lookups
    # ═════════════════════════════════════════════════════════════════════════
    def _refocus_barcode(self):
        """Maintains active cursor focus on barcode entry field for continuous scanner input."""
        if hasattr(self, '_barcode_entry'):
            try:
                self._barcode_entry.focus_set()
                self._barcode_entry.select_range(0, 'end')
            except Exception:
                pass

    def _toggle_theme(self):
        cur = self.settings.get("theme", "Dark")
        nxt = "Light" if cur == "Dark" else "Dark"
        ctk.set_appearance_mode(nxt)
        self.settings["theme"] = nxt
        save_settings(self.settings)
        self._build_main_ui()

    def _clear_view(self):
        """Clears current product display and refocuses barcode entry."""
        if self._scan_timer is not None:
            try:
                self.after_cancel(self._scan_timer)
            except Exception:
                pass
            self._scan_timer = None

        self._pending_code = None
        self._rapid_keystroke_count = 0
        self._last_key_time = 0.0
        self.current_product = None
        self.current_raw_input = None

        self.lbl_prod_name_ar.configure(text="يرجى مسح باركود الصنف للبدء...", text_color=BRAND_GOLD)
        self.lbl_prod_name_en.configure(text="Scan or enter product barcode above")
        self.lbl_val_code.configure(text="-")
        self.lbl_val_bc.configure(text="-")
        self.lbl_val_pkg.configure(text="-")
        self.lbl_stock_val.configure(text="-", text_color=BRAND_BLUE)
        self.lbl_stock_unit.configure(text="الرصيد الفعلي المتوفر")
        self.lbl_sold_val.configure(text="-", text_color=BRAND_GOLD)
        self.lbl_sold_rate.configure(text="معدل المبيعات الشهري: -")
        self.lbl_need_val.configure(text="-", text_color=BRAND_NEUTRAL)
        self.lbl_need_badge.configure(text="بانتظار مسح صنف...", text_color=BRAND_NEUTRAL)
        self.card_need.configure(border_color=BRAND_NEUTRAL)

        if hasattr(self, '_barcode_entry'):
            self._barcode_entry.delete(0, 'end')
        self._refocus_barcode()

    def _on_showroom_change(self, choice):
        """When showroom changes, persist setting and auto-recalculate if an item is loaded."""
        sh = self.showroom_map.get(choice)
        if sh:
            self.settings["last_showroom_id"] = sh.get('id')
            save_settings(self.settings)

        if self.current_raw_input:
            self._trigger_lookup(code_override=self.current_raw_input)
        else:
            self._refocus_barcode()

    def _on_period_change(self, choice):
        """When period changes, persist setting, show/hide custom range, and auto-recalculate."""
        p_val = self.period_labels.get(choice, "this_year")
        self.settings["last_period"] = p_val
        save_settings(self.settings)

        if p_val == "custom":
            self._custom_dates_frame.pack(fill="x", padx=14, pady=(0, 8))
        else:
            self._custom_dates_frame.pack_forget()

        if self.current_raw_input:
            self._trigger_lookup(code_override=self.current_raw_input)
        else:
            self._refocus_barcode()

    def _apply_custom_dates(self):
        """Applies manual custom date range and updates currently loaded product."""
        if self.current_raw_input:
            self._trigger_lookup(code_override=self.current_raw_input)
        else:
            self._refocus_barcode()

    def _on_months_change(self, choice):
        """Instantaneous in-memory recalculation when needs horizon changes (no network lag)."""
        try:
            m_val = int(choice.split()[0])
            self.settings["last_need_months"] = m_val
            save_settings(self.settings)
        except Exception:
            m_val = 2

        if self.current_product:
            self._recalculate_current_product(m_val)
        self._refocus_barcode()

    def _recalculate_current_product(self, need_months):
        """Recalculates target need and net need instantly without re-querying Odoo."""
        if not self.current_product:
            return
        p = self.current_product
        monthly_rate = p['monthly_rate']
        stock_qty = p['stock_qty']
        target_need = round(monthly_rate * float(need_months), 2)
        net_need = round(target_need - stock_qty, 2)

        p['need_months'] = need_months
        p['target_need'] = target_need
        p['net_need'] = net_need

        self._update_display(p)

        # Update in recent scans list
        for r in self.recent_scans:
            if r.get('id') == p['id']:
                r['need_months'] = need_months
                r['target_need'] = target_need
                r['net_need'] = net_need
                break
        self._render_history_table()

    def _load_showrooms_async(self):
        def _worker():
            try:
                shs = get_active_showrooms()
                self.showrooms = shs
                self.showroom_map = {f"[{s['code']}] {s['name']}" if s['code'] else s['name']: s for s in shs}
                names = list(self.showroom_map.keys())

                saved_id = self.settings.get("last_showroom_id")
                default_name = names[0] if names else ""
                if saved_id:
                    for n, s in self.showroom_map.items():
                        if s['id'] == saved_id:
                            default_name = n
                            break

                self.after(0, lambda: self._populate_showrooms(names, default_name))
            except Exception as e:
                self.after(0, lambda: self._status_badge.configure(text=f"⚠️ تعذر الاتصال بـ Odoo: {e}", text_color=BRAND_RED))

        threading.Thread(target=_worker, daemon=True).start()

    def _populate_showrooms(self, names, default_name):
        if hasattr(self, '_showroom_menu') and names:
            self._showroom_menu.configure(values=names)
            self._showroom_var.set(default_name)
            self._status_badge.configure(text="🟢 متصل بنظام Odoo", text_color=BRAND_GREEN)
            self._refocus_barcode()

    def _on_barcode_key_release(self, event):
        """
        Intelligent scanner detection:
        Detects rapid bursts of keystrokes typical of barcode scanners (inter-key < 75ms)
        and automatically triggers the search after a minimal pause without requiring Enter.
        """
        ignored_keys = {
            "Return", "KP_Enter", "Tab", "ISO_Left_Tab", "Escape",
            "Up", "Down", "Left", "Right", "Home", "End", "Prior", "Next",
            "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
            "Caps_Lock", "Num_Lock", "Scroll_Lock", "Pause"
        }
        if event.keysym in ignored_keys:
            return

        if self._scan_timer is not None:
            try:
                self.after_cancel(self._scan_timer)
            except Exception:
                pass
            self._scan_timer = None

        code = self._barcode_entry.get().strip()
        if not code or len(code) < 3:
            return

        now = time.time()
        delta = now - self._last_key_time if self._last_key_time > 0 else 1.0
        self._last_key_time = now

        # Scanners typically enter characters with inter-keystroke time < 75ms
        if delta < 0.075:
            self._rapid_keystroke_count += 1
        else:
            self._rapid_keystroke_count = 0

        # Fast 180ms debounce for scanner gun bursts, 320ms for manual typing
        delay_ms = 180 if self._rapid_keystroke_count >= 2 else 320
        self._scan_timer = self.after(delay_ms, self._auto_trigger_lookup)

    def _auto_trigger_lookup(self):
        self._scan_timer = None
        code = self._barcode_entry.get().strip()
        if code and len(code) >= 3:
            self._trigger_lookup()

    def _on_enter_or_tab(self, event=None):
        if self._scan_timer is not None:
            try:
                self.after_cancel(self._scan_timer)
            except Exception:
                pass
            self._scan_timer = None
        self._trigger_lookup()
        return "break"

    def _trigger_lookup(self, code_override=None):
        if self._scan_timer is not None:
            try:
                self.after_cancel(self._scan_timer)
            except Exception:
                pass
            self._scan_timer = None

        if code_override:
            code = str(code_override).strip()
        else:
            code = self._barcode_entry.get().strip()

        if not code:
            self._refocus_barcode()
            return

        if self._is_querying:
            self._pending_code = code
            return

        sh_name = self._showroom_var.get()
        sh = self.showroom_map.get(sh_name)
        if not sh:
            messagebox.showwarning("تنبيه", "يرجى الانتظار حتى اكتمال تحميل المعارض واختيار المعرض.")
            self._refocus_barcode()
            return

        period_key = self.period_labels.get(self._period_var.get(), "this_year")
        try:
            need_m = int(self._months_var.get().split()[0])
        except Exception:
            need_m = 2

        c_from = self._date_from.get().strip() if period_key == "custom" else None
        c_to = self._date_to.get().strip() if period_key == "custom" else None

        self._is_querying = True
        self._btn_search.configure(text="⏳ جاري البحث...")
        self._status_badge.configure(text=f"🔍 استعلام: {code}...", text_color=BRAND_GOLD)

        def _worker():
            res, err = query_product_and_needs(
                barcode_input=code,
                showroom=sh,
                period=period_key,
                need_months=need_m,
                custom_from=c_from,
                custom_to=c_to
            )
            self.after(0, lambda: self._handle_lookup_result(res, err, code))

        threading.Thread(target=_worker, daemon=True).start()

    def _handle_lookup_result(self, res, err, raw_input):
        self._is_querying = False
        self._btn_search.configure(text="🔍 بحث")
        self._status_badge.configure(text="🟢 متصل بنظام Odoo", text_color=BRAND_GREEN)
        self._rapid_keystroke_count = 0
        self._last_key_time = 0.0

        if err:
            self.current_product = None
            self.current_raw_input = None

            self.lbl_prod_name_ar.configure(text=f"⚠️ {err}", text_color=BRAND_RED)
            self.lbl_prod_name_en.configure(text=f"Barcode / Code: {raw_input}")
            self.lbl_val_code.configure(text="-")
            self.lbl_val_bc.configure(text="-")
            self.lbl_val_pkg.configure(text="-")
            self.lbl_stock_val.configure(text="-", text_color=BRAND_BLUE)
            self.lbl_sold_val.configure(text="-", text_color=BRAND_GOLD)
            self.lbl_need_val.configure(text="-", text_color=BRAND_NEUTRAL)
            self.lbl_need_badge.configure(text="الصنف غير مسجل", text_color=BRAND_RED)
            self.card_need.configure(border_color=BRAND_RED)
            self.bell()

            # Keep the invalid input selected so cashier sees what was scanned and can overwrite immediately
            self._refocus_barcode()
        else:
            # Clear and refocus barcode entry so user can scan next immediately
            self._barcode_entry.delete(0, 'end')
            self._refocus_barcode()

            # Store current active item
            self.current_product = res
            self.current_raw_input = raw_input

            # Update visual KPI cards and details
            self._update_display(res)

            # Add to recent scans history (avoid duplicates at the top)
            self.recent_scans = [r for r in self.recent_scans if r.get('id') != res['id']]
            self.recent_scans.insert(0, res)
            if len(self.recent_scans) > 25:
                self.recent_scans.pop()

            self._render_history_table()

        # If another scan arrived while query was in flight, trigger it now
        if self._pending_code:
            p_code = self._pending_code
            self._pending_code = None
            self.after(50, lambda: self._trigger_lookup(code_override=p_code))

    def _update_display(self, res):
        """Renders product information, stock, sales, and calculated net needs."""
        self.lbl_prod_name_ar.configure(text=res['name_ar'], text_color=BRAND_GOLD)
        self.lbl_prod_name_en.configure(text=res['name_en'])
        self.lbl_val_code.configure(text=res['default_code'])
        self.lbl_val_bc.configure(text=res['barcode'])
        self.lbl_val_pkg.configure(text=res['packaging_barcodes'])

        # Stock & Sales
        self.lbl_stock_val.configure(text=f"{res['stock_qty']:g}")
        self.lbl_stock_unit.configure(text=f"{res['uom']} (الرصيد الفعلي المتوفر)")

        self.lbl_sold_val.configure(text=f"{res['sold_qty']:g}")
        self.lbl_sold_rate.configure(text=f"معدل الاستهلاك: {res['monthly_rate']:g} {res['uom']}/شهر ({res['period_days']} يوم)")

        # Net Need Calculation & Color Coding
        need = res['net_need']
        target = res['target_need']
        uom = res['uom']
        n_months = res['need_months']

        if need > 0:
            # DEFICIT -> GREEN (بحاجة لطلب / تزويد)
            self.lbl_need_val.configure(text=f"+{need:g} {uom}", text_color=BRAND_GREEN)
            self.lbl_need_badge.configure(
                text=f"🟢 بحاجة لطلب تزويد (+{need:g} {uom}) | المستهدف لـ {n_months} شهر: {target:g}",
                text_color=BRAND_GREEN
            )
            self.card_need.configure(border_color=BRAND_GREEN)
        elif need < 0:
            # SURPLUS -> RED (فائض مخزون)
            abs_need = abs(need)
            self.lbl_need_val.configure(text=f"-{abs_need:g} {uom}", text_color=BRAND_RED)
            self.lbl_need_badge.configure(
                text=f"🔴 فائض عن الحاجة (-{abs_need:g} {uom}) | المستهدف لـ {n_months} شهر: {target:g}",
                text_color=BRAND_RED
            )
            self.card_need.configure(border_color=BRAND_RED)
        else:
            # BALANCED -> NEUTRAL
            self.lbl_need_val.configure(text=f"0 {uom}", text_color=BRAND_NEUTRAL)
            self.lbl_need_badge.configure(
                text=f"⚪ المخزون متوازن تماماً (0 {uom}) | المستهدف لـ {n_months} شهر: {target:g}",
                text_color=BRAND_NEUTRAL
            )
            self.card_need.configure(border_color=BRAND_NEUTRAL)

    def _render_history_table(self):
        for w in self.hist_scroll.winfo_children():
            w.destroy()

        if not self.recent_scans:
            ctk.CTkLabel(self.hist_scroll, text="لم يتم مسح أي صنف في هذه الجلسة بعد.",
                         font=ctk.CTkFont(APP_FONT, 11), text_color=BRAND_NEUTRAL).pack(pady=20)
            return

        # Header Row
        hdr = ctk.CTkFrame(self.hist_scroll, fg_color=BRAND_BLUE, corner_radius=4)
        hdr.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(hdr, text="الوقت", font=ctk.CTkFont(APP_FONT, 10, "bold"), text_color="white", width=65).pack(side="right", padx=6)
        ctk.CTkLabel(hdr, text="كود الصنف", font=ctk.CTkFont(APP_FONT, 10, "bold"), text_color="white", width=110).pack(side="right", padx=6)
        ctk.CTkLabel(hdr, text="الاسم العربي", font=ctk.CTkFont(APP_FONT, 10, "bold"), text_color="white").pack(side="right", fill="x", expand=True, padx=6)
        ctk.CTkLabel(hdr, text="الرصيد", font=ctk.CTkFont(APP_FONT, 10, "bold"), text_color="white", width=75).pack(side="right", padx=6)
        ctk.CTkLabel(hdr, text="المبيعات", font=ctk.CTkFont(APP_FONT, 10, "bold"), text_color="white", width=75).pack(side="right", padx=6)
        ctk.CTkLabel(hdr, text="صافي الاحتياج", font=ctk.CTkFont(APP_FONT, 10, "bold"), text_color="white", width=120).pack(side="right", padx=6)

        for item in self.recent_scans:
            row = ctk.CTkFrame(self.hist_scroll, fg_color=("gray95", "#141D2A"), corner_radius=4, cursor="hand2")
            row.pack(fill="x", pady=2)

            need = item['net_need']
            uom = item['uom']
            if need > 0:
                need_txt = f"+{need:g} {uom}"
                need_color = BRAND_GREEN
            elif need < 0:
                need_txt = f"-{abs(need):g} {uom}"
                need_color = BRAND_RED
            else:
                need_txt = f"0 {uom}"
                need_color = BRAND_NEUTRAL

            def _select_item(e, it=item):
                self.current_product = it
                self.current_raw_input = it.get('scanned_code') or it.get('default_code')
                self._update_display(it)
                self._refocus_barcode()

            w_time = ctk.CTkLabel(row, text=item['timestamp'], font=ctk.CTkFont("Consolas", 10), text_color=BRAND_NEUTRAL, width=65)
            w_time.pack(side="right", padx=6)

            w_code = ctk.CTkLabel(row, text=item['default_code'], font=ctk.CTkFont("Consolas", 11, "bold"), width=110)
            w_code.pack(side="right", padx=6)

            w_name = ctk.CTkLabel(row, text=item['name_ar'], font=ctk.CTkFont(APP_FONT, 11), anchor="e")
            w_name.pack(side="right", fill="x", expand=True, padx=6)

            w_stk = ctk.CTkLabel(row, text=f"{item['stock_qty']:g}", font=ctk.CTkFont(APP_FONT, 11, "bold"), text_color=BRAND_BLUE, width=75)
            w_stk.pack(side="right", padx=6)

            w_sold = ctk.CTkLabel(row, text=f"{item['sold_qty']:g}", font=ctk.CTkFont(APP_FONT, 11, "bold"), text_color=BRAND_GOLD, width=75)
            w_sold.pack(side="right", padx=6)

            w_need = ctk.CTkLabel(row, text=need_txt, font=ctk.CTkFont(APP_FONT, 11, "bold"), text_color=need_color, width=120)
            w_need.pack(side="right", padx=6)

            # Bind click on row and labels to reload this item
            row.bind("<Button-1>", _select_item)
            for ch in (w_time, w_code, w_name, w_stk, w_sold, w_need):
                ch.bind("<Button-1>", _select_item)


# ─────────────────────────────────────────────────────────────────────────────
# 🚀 Entry Point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = ShowroomCheckerApp()
    app.mainloop()
