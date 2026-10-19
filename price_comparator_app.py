"""
price_comparator_app.py — Odoo Price Comparator & Competitor Intelligence Suite
Designed & Developed by: عبدالله الخطيب (Abdullah Al-Khatib)
Version: v1.00 (Standard Production Edition)
"""

APP_VERSION = "v1.01"

import os
import sys
import json
import webbrowser
import threading
import time
from datetime import datetime

import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk

from licensing import get_machine_id, is_activated, activate_device
from auto_updater import check_and_prompt_update_async
from odoo_product_lookup import lookup_product_by_barcode_or_code
from competitor_scraper import STORES_REGISTRY, STORES_MAP, search_all_competitors
from price_intelligence import analyze_market_competition, round_smart_price
from batch_excel_pricer import inspect_excel_file, BatchExcelPricer, scrape_store_catalog_to_excel

# ─────────────────────────────────────────────────────────────────────────────
# 🎨 Design Palette & Brand Colors
# ─────────────────────────────────────────────────────────────────────────────
BRAND_GOLD = "#E5B31A"
BRAND_GOLD_HOVER = "#CA9E17"
BRAND_GOLD_SOFT = ("#FEF9C3", "#422006")

BRAND_BLUE = "#2563EB"
BRAND_BLUE_HOVER = "#1D4ED8"
BRAND_BLUE_GLOW = "#3B82F6"

BRAND_GREEN = "#10B981"
BRAND_GREEN_HOVER = "#059669"
BRAND_GREEN_SOFT = ("#D1FAE5", "#064E3B")

BRAND_RED = "#EF4444"
BRAND_RED_HOVER = "#DC2626"
BRAND_RED_SOFT = ("#FEE2E2", "#7F1D1D")

BRAND_AMBER = "#F59E0B"
BRAND_AMBER_SOFT = ("#FEF3C7", "#78350F")

BRAND_PURPLE = "#8B5CF6"
BRAND_PURPLE_HOVER = "#7C3AED"

BRAND_SLATE = "#64748B"
BORDER_SUBTLE = ("#CBD5E1", "#1E3A5F")
BG_CARD = ("#FFFFFF", "#1E293B")
BG_CARD_LIGHT = ("#F8FAFC", "#0F172A")
HDR_BG = ("#1E40AF", "#070E1C")
HDR_TITLE_COLOR = "#F1F5F9"

APP_FONT = "Segoe UI"


# ─────────────────────────────────────────────────────────────────────────────
# 🛠️ Configuration & Settings Persistence
# ─────────────────────────────────────────────────────────────────────────────
def _get_settings_path():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(appdata, "AlAssaliOdooExporter")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "comparator_settings.json")


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
        "target_margin": 20.0,
        "cost_basis": "net_purchase"  # 'net_purchase' or 'standard_cost'
    }


def save_settings(settings):
    p = _get_settings_path()
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# 🖥️ Main Price Comparator Application
# ─────────────────────────────────────────────────────────────────────────────
class PriceComparatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.settings = load_settings()
        ctk.set_appearance_mode(self.settings.get("theme", "Dark"))
        ctk.set_default_color_theme("blue")

        self.title(f"مساعد التسعير ومراقبة المنافسين — شركة العسلي التجارية [{APP_VERSION}]")
        self._center_window(1440, 880)
        self.minsize(1200, 720)
        self.resizable(True, True)

        # Application State
        self.is_searching = False
        self.current_product = None
        self.current_competitors = None
        self.current_analysis = None
        self._comp_filter_mode = "all"  # 'all' or 'found'

        if not is_activated():
            self._build_activation_screen()
        else:
            self._build_main_ui()
            try:
                self.after(50, lambda: self.state('zoomed'))
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
    # 🔒 ACTIVATION SCREEN
    # ═════════════════════════════════════════════════════════════════════════
    def _build_activation_screen(self):
        self._center_window(660, 640)
        self.resizable(False, False)
        for w in self.winfo_children():
            w.destroy()

        ctk.CTkFrame(self, fg_color=BRAND_GOLD, height=4, corner_radius=0).pack(fill="x")

        box = ctk.CTkFrame(self, fg_color="transparent")
        box.pack(fill="both", expand=True, padx=40, pady=25)

        # Header Logo & Title
        try:
            from PIL import Image
            logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "company_logo.png")
            if os.path.exists(logo_path):
                pil_img = Image.open(logo_path)
                target_h = 60
                target_w = int(target_h * (pil_img.width / pil_img.height))
                self._act_logo_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(target_w, target_h))
                ctk.CTkLabel(box, image=self._act_logo_img, text="").pack(pady=(0, 6))
            else:
                ctk.CTkLabel(box, text="🏢 شركة العسلي التجارية",
                             font=ctk.CTkFont(APP_FONT, 18, "bold"), text_color=BRAND_GOLD).pack(pady=(0, 4))
        except Exception:
            ctk.CTkLabel(box, text="🏢 شركة العسلي التجارية",
                         font=ctk.CTkFont(APP_FONT, 18, "bold"), text_color=BRAND_GOLD).pack(pady=(0, 4))

        ctk.CTkLabel(box, text="🎯 نظام مقارنة الأسعار ومراقبة المنافسين",
                     font=ctk.CTkFont(APP_FONT, 20, "bold")).pack(pady=(0, 2))

        ctk.CTkLabel(box, text=f"الإصدار الرسمي {APP_VERSION} | تصميم وتطوير: عبدالله الخطيب",
                     font=ctk.CTkFont(APP_FONT, 12, "bold"), text_color=BRAND_GOLD).pack(pady=(0, 16))

        info_box = ctk.CTkFrame(box, fg_color=BG_CARD, corner_radius=12,
                                border_width=1, border_color=BORDER_SUBTLE)
        info_box.pack(fill="x", pady=(0, 14))

        ctk.CTkLabel(info_box, text="🔒  تفعيل ترخيص البرنامج على هذا الجهاز",
                     font=ctk.CTkFont(APP_FONT, 14, "bold"),
                     text_color=(BRAND_BLUE, BRAND_BLUE_GLOW)).pack(pady=(12, 4))

        ctk.CTkLabel(info_box,
                     text="الرجاء نسخ معرّف الجهاز (Machine ID) التالي وتزويد المهندس عبدالله به للحصول على مفتاح التفعيل الرسمي:",
                     font=ctk.CTkFont(APP_FONT, 11), text_color=BRAND_SLATE,
                     wraplength=520, justify="center").pack(padx=16, pady=(0, 10))

        # Machine ID display
        mid = get_machine_id()
        mid_row = ctk.CTkFrame(info_box, fg_color=("gray90", "#0F172A"), corner_radius=8)
        mid_row.pack(fill="x", padx=16, pady=(0, 12))

        mid_entry = ctk.CTkEntry(mid_row, font=ctk.CTkFont("Consolas", 13, "bold"),
                                 height=36, justify="center")
        mid_entry.insert(0, mid)
        mid_entry.configure(state="readonly")
        mid_entry.pack(side="right", fill="x", expand=True, padx=(8, 4), pady=4)

        def _copy_mid():
            self.clipboard_clear()
            self.clipboard_append(mid)
            btn_copy.configure(text="✅ تم النسخ", fg_color=BRAND_GREEN)
            self.after(2000, lambda: btn_copy.configure(text="📋 نسخ المعرّف", fg_color=BRAND_BLUE))

        btn_copy = ctk.CTkButton(mid_row, text="📋 نسخ المعرّف", width=110, height=36,
                                 font=ctk.CTkFont(APP_FONT, 11, "bold"),
                                 fg_color=BRAND_BLUE, hover_color=BRAND_BLUE_HOVER,
                                 command=_copy_mid)
        btn_copy.pack(side="left", padx=(4, 8), pady=4)

        # License key entry
        key_box = ctk.CTkFrame(box, fg_color=BG_CARD, corner_radius=12,
                               border_width=1, border_color=BORDER_SUBTLE)
        key_box.pack(fill="x", pady=(0, 14))

        ctk.CTkLabel(key_box, text="أدخل مفتاح التفعيل (License Key):",
                     font=ctk.CTkFont(APP_FONT, 12, "bold")).pack(anchor="e", padx=16, pady=(10, 4))

        self._key_entry = ctk.CTkEntry(key_box, placeholder_text="XXXX-XXXX-XXXX-XXXX-XXXX",
                                       font=ctk.CTkFont("Consolas", 13),
                                       height=40, justify="center")
        self._key_entry.pack(fill="x", padx=16, pady=(0, 12))

        self._act_status = ctk.CTkLabel(box, text="", font=ctk.CTkFont(APP_FONT, 11, "bold"))
        self._act_status.pack(pady=(0, 8))

        # Submit button
        btn_act = ctk.CTkButton(box, text="⚡  تفعيل وبدء تشغيل البرنامج",
                                font=ctk.CTkFont(APP_FONT, 14, "bold"),
                                fg_color=BRAND_GOLD, hover_color=BRAND_GOLD_HOVER,
                                text_color="#1E293B", height=46, corner_radius=10,
                                command=self._do_activate)
        btn_act.pack(fill="x", pady=(0, 8))

    def _do_activate(self):
        k = self._key_entry.get().strip()
        if not k:
            self._act_status.configure(text="يرجى إدخال مفتاح التفعيل أولاً.", text_color=BRAND_RED)
            return

        ok, msg = activate_device(k)
        if ok:
            messagebox.showinfo("تم التفعيل بنجاح", "🎉 تم تفعيل ترخيص البرنامج بنجاح!\nأهلاً بك في مساعد التسعير ومراقبة المنافسين.")
            self._build_main_ui()
            try:
                self.after(50, lambda: self.state('zoomed'))
            except Exception:
                pass
        else:
            self._act_status.configure(text=f"❌ {msg}", text_color=BRAND_RED)

    # ═════════════════════════════════════════════════════════════════════════
    # 🌟 MAIN APPLICATION UI (DASHBOARD)
    # ═════════════════════════════════════════════════════════════════════════
    def _build_main_ui(self):
        for w in self.winfo_children():
            w.destroy()

        self.minsize(1200, 720)
        self.resizable(True, True)

        main_box = ctk.CTkFrame(self, fg_color="transparent")
        main_box.pack(fill="both", expand=True)

        # 1. Header (Corporate Bar)
        self._build_header(main_box)

        # 2. Main Tabview (Multi-Mode Suite)
        self._main_tabs = ctk.CTkTabview(main_box, fg_color="transparent", corner_radius=10)
        self._main_tabs.pack(fill="both", expand=True, padx=14, pady=(2, 4))

        tab_single = self._main_tabs.add("🎯  فحص ومقارنة صنف فوري (Live Product)")
        tab_batch = self._main_tabs.add("📑  تسعير ملفات الإكسيل بالجملة (Batch Excel)")
        tab_catalog = self._main_tabs.add("🌐  سحب كتالوج متجر كامل (Full Catalog)")

        # ── Tab 1: Live Single Product Lookup ────────────────────────────────
        self._build_search_bar(tab_single)

        content = ctk.CTkFrame(tab_single, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=0, pady=(2, 4))

        content.columnconfigure(0, weight=1, uniform="group")  # Column 0 (Left): Strategy & Intelligence
        content.columnconfigure(1, weight=1, uniform="group")  # Column 1 (Middle): 34 Competitors
        content.columnconfigure(2, weight=1, uniform="group")  # Column 2 (Right): Odoo Internal Product
        content.rowconfigure(0, weight=1)

        self._build_section_odoo(content)         # Grid column 2
        self._build_section_competitors(content)  # Grid column 1
        self._build_section_strategy(content)     # Grid column 0

        # ── Tab 2: Batch Excel Pricing ───────────────────────────────────────
        self._build_batch_excel_tab(tab_batch)

        # ── Tab 3: Store Catalog Scraper ─────────────────────────────────────
        self._build_catalog_scraper_tab(tab_catalog)

        # 4. Status Bar (Footer)
        self._build_footer(main_box)

        # Auto-focus search entry on startup
        self.after(200, lambda: self._barcode_entry.focus_set())

        # Check for updates in background
        check_and_prompt_update_async(self, "PriceComparator", APP_VERSION)

    # ─── 1. HEADER ───────────────────────────────────────────────────────────
    def _build_header(self, parent):
        # Gold accent top line
        ctk.CTkFrame(parent, fg_color=BRAND_GOLD, height=3, corner_radius=0).pack(fill="x")

        hdr = ctk.CTkFrame(parent, corner_radius=0, fg_color=HDR_BG, height=64)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        # Right: Company Logo
        brand_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        brand_frame.pack(side="right", padx=16, pady=6)

        try:
            from PIL import Image
            logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "company_logo.png")
            if os.path.exists(logo_path):
                pil_img = Image.open(logo_path)
                target_h = 44
                target_w = int(target_h * (pil_img.width / pil_img.height))
                self._header_logo_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(target_w, target_h))
                ctk.CTkLabel(brand_frame, image=self._header_logo_img, text="").pack(side="right", padx=2)
            else:
                ctk.CTkLabel(brand_frame, text="🏢 العسلي التجارية",
                             font=ctk.CTkFont(APP_FONT, 14, "bold"), text_color=BRAND_GOLD).pack(side="right")
        except Exception:
            ctk.CTkLabel(brand_frame, text="🏢 العسلي التجارية",
                         font=ctk.CTkFont(APP_FONT, 14, "bold"), text_color=BRAND_GOLD).pack(side="right")

        # Left: Controls (Theme toggle & Refresh Odoo connection)
        ctrl_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        ctrl_frame.pack(side="left", padx=14, pady=8)

        self._theme_var = ctk.StringVar(value="☀️  فاتح" if self.settings.get("theme") == "Light" else "🌙  داكن")
        theme_menu = ctk.CTkOptionMenu(ctrl_frame, values=["🌙  داكن", "☀️  فاتح"],
                                       variable=self._theme_var, width=105, height=32,
                                       font=ctk.CTkFont(APP_FONT, 11, "bold"),
                                       fg_color=("#3B82F6", "#1E293B"),
                                       command=self._change_theme)
        theme_menu.pack(side="left", padx=(0, 8))

        # Center: Title, Version, Developer, and 12-hour Clock without seconds
        title_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        title_frame.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(title_frame, text="🎯  مساعد التسعير ومراقبة المنافسين الذكي",
                     font=ctk.CTkFont(APP_FONT, 16, "bold"),
                     text_color=HDR_TITLE_COLOR).pack(pady=(0, 2))

        sub_bar = ctk.CTkFrame(title_frame, fg_color="transparent")
        sub_bar.pack()

        ctk.CTkLabel(sub_bar,
                     text=f"{APP_VERSION} تصميم وتطوير: عبدالله الخطيب",
                     font=ctk.CTkFont(APP_FONT, 11, "bold"),
                     text_color=BRAND_GOLD).pack(side="right", padx=(0, 10))

        ctk.CTkLabel(sub_bar, text="|", font=ctk.CTkFont(APP_FONT, 11),
                     text_color=("#93C5FD", "#475569")).pack(side="right", padx=(0, 10))

        now = datetime.now()
        period = "ص" if now.hour < 12 else "م"
        h = now.hour % 12 or 12
        init_clock = f"📅 {now.strftime('%Y/%m/%d')}   ⏰ {h:02d}:{now.minute:02d} {period}"
        self._hdr_clock = ctk.CTkLabel(sub_bar, text=init_clock,
                                       font=ctk.CTkFont(APP_FONT, 11, "bold"),
                                       text_color=("#F1F5F9", "#CBD5E1"))
        self._hdr_clock.pack(side="right")
        self._tick_clock()

    def _tick_clock(self):
        if hasattr(self, '_hdr_clock') and self._hdr_clock.winfo_exists():
            now = datetime.now()
            period = "ص" if now.hour < 12 else "م"
            h = now.hour % 12 or 12
            self._hdr_clock.configure(text=f"📅 {now.strftime('%Y/%m/%d')}   ⏰ {h:02d}:{now.minute:02d} {period}")
            self.after(1000, self._tick_clock)

    def _change_theme(self, choice):
        theme = "Light" if "فاتح" in choice else "Dark"
        ctk.set_appearance_mode(theme)
        self.settings["theme"] = theme
        save_settings(self.settings)

    # ─── 2. SEARCH & SCANNER BAR ─────────────────────────────────────────────
    def _build_search_bar(self, parent):
        search_card = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=12,
                                   border_width=1, border_color=BORDER_SUBTLE)
        search_card.pack(fill="x", padx=14, pady=(8, 4))

        row = ctk.CTkFrame(search_card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=10)

        # Search / Scan Entry
        self._barcode_entry = ctk.CTkEntry(
            row,
            placeholder_text="📷  امسح الباركود بجهاز السكانر أو اكتب الكود / الباركود واضغط Enter للبحث والمقارنة...",
            font=ctk.CTkFont(APP_FONT, 13),
            height=44, corner_radius=10, justify="right"
        )
        self._barcode_entry.pack(side="right", fill="x", expand=True, padx=(10, 0))
        self._barcode_entry.bind("<Return>", lambda e: self._start_search())

        # Action Buttons
        self._btn_search = ctk.CTkButton(
            row, text="🔍  بحث ومقارنة شاملة",
            font=ctk.CTkFont(APP_FONT, 13, "bold"),
            fg_color=BRAND_BLUE, hover_color=BRAND_BLUE_HOVER,
            width=160, height=44, corner_radius=10,
            command=self._start_search
        )
        self._btn_search.pack(side="right", padx=(8, 0))

        self._btn_clear = ctk.CTkButton(
            row, text="🔄 مسح",
            font=ctk.CTkFont(APP_FONT, 12, "bold"),
            fg_color=("#64748B", "#334155"), hover_color=("#475569", "#1E293B"),
            width=80, height=44, corner_radius=10,
            command=self._clear_all
        )
        self._btn_clear.pack(side="right", padx=(8, 12))

        # Target Margin & Cost Basis Controls
        opts_frame = ctk.CTkFrame(row, fg_color="transparent")
        opts_frame.pack(side="left")

        ctk.CTkLabel(opts_frame, text="% الهامش المستهدف:",
                     font=ctk.CTkFont(APP_FONT, 11, "bold"),
                     text_color=BRAND_SLATE).pack(side="left", padx=(0, 4))

        self._target_margin_entry = ctk.CTkEntry(
            opts_frame, width=54, height=34, font=ctk.CTkFont(APP_FONT, 12, "bold"), justify="center"
        )
        self._target_margin_entry.insert(0, str(int(self.settings.get("target_margin", 20))))
        self._target_margin_entry.pack(side="left", padx=(0, 10))

        # Cost basis toggle
        self._cost_basis_var = ctk.StringVar(value=self.settings.get("cost_basis", "net_purchase"))
        cost_combo = ctk.CTkOptionMenu(
            opts_frame, values=["صافي آخر شراء", "التكلفة القياسية (Cost)"],
            width=140, height=34, font=ctk.CTkFont(APP_FONT, 11, "bold"),
            command=self._on_cost_basis_change
        )
        cost_combo.set("صافي آخر شراء" if self._cost_basis_var.get() == "net_purchase" else "التكلفة القياسية (Cost)")
        cost_combo.pack(side="left")

    def _on_cost_basis_change(self, choice):
        self._cost_basis_var.set("net_purchase" if "آخر شراء" in choice else "standard_cost")
        self.settings["cost_basis"] = self._cost_basis_var.get()
        save_settings(self.settings)
        if self.current_product and self.current_competitors:
            self._update_strategy_section()

    # ─── 3. SECTION 1: ODOO INTERNAL PRODUCT (RIGHT COLUMN) ──────────────────
    def _build_section_odoo(self, parent):
        col = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=14,
                            border_width=1, border_color=BORDER_SUBTLE)
        col.grid(row=0, column=2, sticky="nsew", padx=(6, 0))

        # Title Header
        hdr = ctk.CTkFrame(col, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(hdr, text="🏢  بيانات الصنف في نظام Odoo",
                     font=ctk.CTkFont(APP_FONT, 14, "bold"),
                     text_color=(BRAND_BLUE, BRAND_BLUE_GLOW)).pack(side="right")

        self._odoo_match_badge = ctk.CTkLabel(hdr, text="جاهز للبحث",
                                              font=ctk.CTkFont(APP_FONT, 10, "bold"),
                                              fg_color=("#E2E8F0", "#334155"),
                                              corner_radius=6, padx=8, pady=2)
        self._odoo_match_badge.pack(side="left")

        sep = ctk.CTkFrame(col, height=1, fg_color=BORDER_SUBTLE)
        sep.pack(fill="x", padx=12, pady=(0, 8))

        scroll = ctk.CTkScrollableFrame(col, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        def _make_field_box(parent_widget, label, default="—", is_bold=False, text_color=None):
            box = ctk.CTkFrame(parent_widget, fg_color=("gray94", "#172033"), corner_radius=8,
                               border_width=1, border_color=BORDER_SUBTLE)
            box.pack(fill="x", pady=3)
            ctk.CTkLabel(box, text=label, font=ctk.CTkFont(APP_FONT, 10, "bold"),
                         text_color=BRAND_SLATE).pack(anchor="e", padx=12, pady=(4, 0))
            val_lbl = ctk.CTkLabel(box, text=default,
                                   font=ctk.CTkFont(APP_FONT, 12, "bold" if is_bold else "normal"),
                                   text_color=text_color or ("#0F172A", "#F8FAFC"),
                                   wraplength=520, justify="right")
            val_lbl.pack(anchor="e", padx=12, pady=(1, 5))
            return val_lbl

        self._odoo_code_lbl   = _make_field_box(scroll, "كود الصنف الداخلي (Internal Reference):", is_bold=True, text_color=BRAND_GOLD)
        self._odoo_name_ar    = _make_field_box(scroll, "الاسم باللغة العربية:", is_bold=True)
        self._odoo_name_en    = _make_field_box(scroll, "الاسم باللغة الإنجليزية:")
        self._odoo_barcode    = _make_field_box(scroll, "الباركود الأساسي (Primary Barcode):")

        # Packaging barcodes container
        pkg_box = ctk.CTkFrame(scroll, fg_color=("gray94", "#172033"), corner_radius=8,
                               border_width=1, border_color=BORDER_SUBTLE)
        pkg_box.pack(fill="x", pady=3)
        ctk.CTkLabel(pkg_box, text="باركودات التعبئة والتجزئة (Packaging Barcodes):",
                     font=ctk.CTkFont(APP_FONT, 10, "bold"), text_color=BRAND_SLATE).pack(anchor="e", padx=12, pady=(4, 2))
        self._odoo_pkg_lbl = ctk.CTkLabel(pkg_box, text="—", font=ctk.CTkFont(APP_FONT, 11),
                                          wraplength=520, justify="right")
        self._odoo_pkg_lbl.pack(anchor="e", padx=12, pady=(0, 6))

        # Tax Status Box (Integrated ZATCA Status)
        tax_box = ctk.CTkFrame(scroll, fg_color=("gray94", "#172033"), corner_radius=8,
                               border_width=1, border_color=BORDER_SUBTLE)
        tax_box.pack(fill="x", pady=3)
        tax_hdr_row = ctk.CTkFrame(tax_box, fg_color="transparent")
        tax_hdr_row.pack(fill="x", padx=12, pady=(4, 1))

        ctk.CTkLabel(tax_hdr_row, text="الوضع الضريبي في أودو (ZATCA):",
                     font=ctk.CTkFont(APP_FONT, 10, "bold"), text_color=BRAND_SLATE).pack(side="right")
        self._odoo_tax_badge = ctk.CTkLabel(tax_hdr_row, text="—",
                                             font=ctk.CTkFont(APP_FONT, 10, "bold"),
                                             fg_color=("#E2E8F0", "#334155"),
                                             corner_radius=6, padx=8, pady=1)
        self._odoo_tax_badge.pack(side="left")

        self._odoo_tax_lbl = ctk.CTkLabel(tax_box, text="—",
                                          font=ctk.CTkFont(APP_FONT, 12, "bold"),
                                          wraplength=520, justify="right")
        self._odoo_tax_lbl.pack(anchor="e", padx=12, pady=(1, 5))

        # Pricing Grid
        p_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        p_frame.pack(fill="x", pady=3)
        p_frame.columnconfigure(0, weight=1)
        p_frame.columnconfigure(1, weight=1)

        # Standard Cost
        cost_box = ctk.CTkFrame(p_frame, fg_color=("gray94", "#172033"), corner_radius=8,
                                border_width=1, border_color=BORDER_SUBTLE)
        cost_box.grid(row=0, column=1, sticky="nsew", padx=(3, 0))
        ctk.CTkLabel(cost_box, text="التكلفة القياسية (Cost):", font=ctk.CTkFont(APP_FONT, 10, "bold"),
                     text_color=BRAND_SLATE).pack(pady=(4, 0))
        self._odoo_cost_lbl = ctk.CTkLabel(cost_box, text="—", font=ctk.CTkFont(APP_FONT, 13, "bold"),
                                           text_color=("#2563EB", "#60A5FA"))
        self._odoo_cost_lbl.pack(pady=(1, 5))

        # Retail Price
        retail_box = ctk.CTkFrame(p_frame, fg_color=("gray94", "#172033"), corner_radius=8,
                                  border_width=1, border_color=BORDER_SUBTLE)
        retail_box.grid(row=0, column=0, sticky="nsew", padx=(0, 3))
        ctk.CTkLabel(retail_box, text="سعر البيع الحالي (Retail):", font=ctk.CTkFont(APP_FONT, 10, "bold"),
                     text_color=BRAND_SLATE).pack(pady=(4, 0))
        self._odoo_retail_lbl = ctk.CTkLabel(retail_box, text="—", font=ctk.CTkFont(APP_FONT, 13, "bold"),
                                             text_color=("#16A34A", "#34D399"))
        self._odoo_retail_lbl.pack(pady=(1, 5))

        # Net Last Purchase Price (The core pricing factor requested by user)
        last_p_box = ctk.CTkFrame(scroll, fg_color=("#FEF3C7", "#2D2005"), corner_radius=8,
                                  border_width=1, border_color=("#F59E0B", "#78350F"))
        last_p_box.pack(fill="x", pady=4)
        ctk.CTkLabel(last_p_box, text="💰 صافي آخر سعر شراء بعد الخصم (Net Purchase):",
                     font=ctk.CTkFont(APP_FONT, 10, "bold"), text_color=("#92400E", "#FCD34D")).pack(anchor="e", padx=10, pady=(5, 0))
        self._odoo_net_purchase_lbl = ctk.CTkLabel(last_p_box, text="—",
                                                    font=ctk.CTkFont(APP_FONT, 15, "bold"),
                                                    text_color=("#B45309", "#FBBF24"))
        self._odoo_net_purchase_lbl.pack(anchor="e", padx=10, pady=(1, 5))

        self._odoo_vendor_lbl = _make_field_box(scroll, "اسم آخر مورد تم الشراء منه:")
        self._odoo_date_lbl   = _make_field_box(scroll, "تاريخ آخر توريد / شراء:")
        self._odoo_stock_lbl  = _make_field_box(scroll, "الرصيد الكلي المتوفر بالشركة (On Hand):")

    # ─── 4. SECTION 2: COMPETITOR PRICES (MIDDLE COLUMN - 34 STORES) ─────────
    def _build_section_competitors(self, parent):
        col = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=14,
                            border_width=1, border_color=BORDER_SUBTLE)
        col.grid(row=0, column=1, sticky="nsew", padx=6)

        hdr = ctk.CTkFrame(col, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(hdr, text="🌐  أسعار السوق والمواقع المنافسة",
                     font=ctk.CTkFont(APP_FONT, 14, "bold"),
                     text_color=(BRAND_BLUE, BRAND_BLUE_GLOW)).pack(side="right")

        self._comp_status_badge = ctk.CTkLabel(hdr, text=f"{len(STORES_REGISTRY)} متجراً معتمداً",
                                                font=ctk.CTkFont(APP_FONT, 10, "bold"),
                                                fg_color=("#E2E8F0", "#334155"),
                                                corner_radius=6, padx=8, pady=2)
        self._comp_status_badge.pack(side="left")

        # Toolbar: Filter & Live Search
        toolbar = ctk.CTkFrame(col, fg_color="transparent")
        toolbar.pack(fill="x", padx=12, pady=(0, 6))

        self._store_filter_entry = ctk.CTkEntry(
            toolbar, placeholder_text="🔍 تصفية المتاجر بالاسم...",
            font=ctk.CTkFont(APP_FONT, 11), height=30, corner_radius=8, justify="right"
        )
        self._store_filter_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._store_filter_entry.bind("<KeyRelease>", lambda e: self._apply_store_filter())

        self._comp_filter_mode = "all"
        self._seg_filter = ctk.CTkSegmentedButton(
            toolbar, values=[f"🌐 الكل ({len(STORES_REGISTRY)})", "🟢 المتوفرة فقط"],
            font=ctk.CTkFont(APP_FONT, 11, "bold"), height=30,
            command=self._on_filter_tab_change
        )
        self._seg_filter.set(f"🌐 الكل ({len(STORES_REGISTRY)})")
        self._seg_filter.pack(side="right")

        sep = ctk.CTkFrame(col, height=1, fg_color=BORDER_SUBTLE)
        sep.pack(fill="x", padx=12, pady=(0, 6))

        self._comp_scroll = ctk.CTkScrollableFrame(col, fg_color="transparent")
        self._comp_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Build 34 Store Cards
        self._store_cards = {}
        for s in STORES_REGISTRY:
            key = s['key']
            name = s['name']
            domain = s['domain']
            accent = s.get('color', '#3B82F6')

            card = ctk.CTkFrame(self._comp_scroll, fg_color=("gray94", "#172033"), corner_radius=10,
                                border_width=1, border_color=BORDER_SUBTLE)
            card.pack(fill="x", pady=4, padx=2)

            # Top row: Name & Domain & Badge
            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=12, pady=(8, 2))

            title_box = ctk.CTkFrame(top, fg_color="transparent")
            title_box.pack(side="right")
            ctk.CTkLabel(title_box, text=name, font=ctk.CTkFont(APP_FONT, 12, "bold"),
                         text_color=accent).pack(side="right")
            ctk.CTkLabel(title_box, text=f"({domain})", font=ctk.CTkFont(APP_FONT, 9),
                         text_color=BRAND_SLATE).pack(side="right", padx=(0, 6))

            badge = ctk.CTkLabel(top, text="في الانتظار...", font=ctk.CTkFont(APP_FONT, 9, "bold"),
                                 fg_color=("#E2E8F0", "#1E293B"), corner_radius=5, padx=7, pady=2)
            badge.pack(side="left")

            # Price row
            p_row = ctk.CTkFrame(card, fg_color="transparent")
            p_row.pack(fill="x", padx=12, pady=2)

            price_lbl = ctk.CTkLabel(p_row, text="—  ر.س", font=ctk.CTkFont(APP_FONT, 16, "bold"),
                                     text_color=("#0F172A", "#F8FAFC"))
            price_lbl.pack(side="right")

            unit_lbl = ctk.CTkLabel(p_row, text="", font=ctk.CTkFont(APP_FONT, 10, "bold"),
                                    fg_color=("#E0E7FF", "#1E1B4B"), text_color=("#4338CA", "#A5B4FC"),
                                    corner_radius=5, padx=7, pady=1)

            method_lbl = ctk.CTkLabel(p_row, text="", font=ctk.CTkFont(APP_FONT, 10),
                                      text_color=BRAND_SLATE)
            method_lbl.pack(side="left")

            # Title in Store
            title_lbl = ctk.CTkLabel(card, text="لم يتم البحث بعد.",
                                     font=ctk.CTkFont(APP_FONT, 10),
                                     text_color=BRAND_SLATE, wraplength=480, justify="right")
            title_lbl.pack(anchor="e", padx=12, pady=(1, 4))

            # Action button
            act_row = ctk.CTkFrame(card, fg_color="transparent")
            act_row.pack(fill="x", padx=12, pady=(0, 6))

            btn_open = ctk.CTkButton(act_row, text="🔗 فتح صفحة المنتج بالموقع",
                                     font=ctk.CTkFont(APP_FONT, 10, "bold"),
                                     fg_color=("#3B82F6", "#1E293B"),
                                     hover_color=BRAND_BLUE_HOVER,
                                     height=26, corner_radius=6, state="disabled")
            btn_open.pack(side="right", fill="x", expand=True)

            self._store_cards[key] = {
                'frame': card,
                'badge': badge,
                'price_lbl': price_lbl,
                'unit_lbl': unit_lbl,
                'method_lbl': method_lbl,
                'title_lbl': title_lbl,
                'btn_open': btn_open,
                'url': '',
                'name': name,
                'domain': domain,
                'found': False,
                'price': 0.0,
                'accent': accent
            }

    def _on_filter_tab_change(self, choice):
        self._comp_filter_mode = "found" if "المتوفرة" in choice else "all"
        self._apply_store_filter()

    def _apply_store_filter(self):
        q = self._store_filter_entry.get().strip().lower()

        # Sort: in-stock found first, then out-of-stock found, then not found, by price ascending
        sorted_keys = sorted(
            self._store_cards.keys(),
            key=lambda k: (
                0 if (self._store_cards[k]['found'] and self._store_cards[k].get('in_stock', True)) else (1 if self._store_cards[k]['found'] else 2),
                self._store_cards[k]['price'] if self._store_cards[k]['price'] > 0 else 999999
            )
        )

        for k in sorted_keys:
            card = self._store_cards[k]
            name_match = (q in card['name'].lower() or q in card['domain'].lower()) if q else True

            if self._comp_filter_mode == "found":
                should_show = card['found'] and card.get('in_stock', True) and name_match
            else:
                should_show = name_match

            if should_show:
                card['frame'].pack(fill="x", pady=3, padx=2)
            else:
                card['frame'].pack_forget()

    # ─── 5. SECTION 3: COMPETITIVE STRATEGY (LEFT COLUMN) ────────────────────
    def _build_section_strategy(self, parent):
        col = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=14,
                            border_width=1, border_color=BORDER_SUBTLE)
        col.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        hdr = ctk.CTkFrame(col, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(hdr, text="💡  لوحة ذكاء التسعير واستراتيجية المنافسة",
                     font=ctk.CTkFont(APP_FONT, 14, "bold"),
                     text_color=(BRAND_BLUE, BRAND_BLUE_GLOW)).pack(side="right")

        self._strategy_badge = ctk.CTkLabel(hdr, text="بانتظار البيانات",
                                             font=ctk.CTkFont(APP_FONT, 10, "bold"),
                                             fg_color=("#E2E8F0", "#334155"),
                                             corner_radius=6, padx=8, pady=2)
        self._strategy_badge.pack(side="left")

        sep = ctk.CTkFrame(col, height=1, fg_color=BORDER_SUBTLE)
        sep.pack(fill="x", padx=12, pady=(0, 8))

        scroll = ctk.CTkScrollableFrame(col, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # 4 Quick Stat Metric Tiles
        stats_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        stats_frame.pack(fill="x", pady=4)
        stats_frame.columnconfigure(0, weight=1)
        stats_frame.columnconfigure(1, weight=1)

        def _make_stat_tile(row_i, col_i, title, default="—", text_color=None):
            box = ctk.CTkFrame(stats_frame, fg_color=("gray94", "#172033"), corner_radius=8,
                               border_width=1, border_color=BORDER_SUBTLE)
            box.grid(row=row_i, column=col_i, sticky="nsew", padx=3, pady=3)
            ctk.CTkLabel(box, text=title, font=ctk.CTkFont(APP_FONT, 10, "bold"),
                         text_color=BRAND_SLATE).pack(pady=(4, 0))
            lbl = ctk.CTkLabel(box, text=default, font=ctk.CTkFont(APP_FONT, 13, "bold"),
                               text_color=text_color or ("#0F172A", "#F8FAFC"))
            lbl.pack(pady=(1, 5))
            return lbl

        self._stat_lowest_price = _make_stat_tile(0, 1, "أدنى سعر بالسوق:", text_color="#10B981")
        self._stat_avg_price    = _make_stat_tile(0, 0, "متوسط أسعار السوق:", text_color="#3B82F6")
        self._stat_price_diff   = _make_stat_tile(1, 1, "فارق السعر عن أقل منافس:")
        self._stat_target_margin = _make_stat_tile(1, 0, "الهامش المحقق عند أقل سعر:", text_color=BRAND_GOLD)

        # Big Strategic Recommendation Card
        self._rec_card = ctk.CTkFrame(scroll, fg_color=("#EFF6FF", "#111C36"), corner_radius=12,
                                      border_width=2, border_color=("#3B82F6", "#1E3A8A"))
        self._rec_card.pack(fill="x", pady=8)

        self._rec_title_lbl = ctk.CTkLabel(
            self._rec_card, text="قم بمسح أو إدخال باركود لعرض التحليل الذكي",
            font=ctk.CTkFont(APP_FONT, 12, "bold"), text_color=BRAND_BLUE,
            wraplength=520, justify="right"
        )
        self._rec_title_lbl.pack(anchor="e", padx=16, pady=(10, 4))

        self._rec_body_lbl = ctk.CTkLabel(
            self._rec_card,
            text="سيقوم النظام آلياً بمطابقة الأسعار وحساب الهامش الربحي والتوصية بالتسعير التنافسي الأمثل مع مراعاة الضريبة.",
            font=ctk.CTkFont(APP_FONT, 11), text_color=("#334155", "#CBD5E1"),
            wraplength=520, justify="right"
        )
        self._rec_body_lbl.pack(anchor="e", padx=16, pady=(0, 10))

        # Suggested Price Card (Hero Highlight)
        sug_card = ctk.CTkFrame(scroll, fg_color=("#FEF3C7", "#271E07"), corner_radius=12,
                                border_width=2, border_color=("#F59E0B", "#B45309"))
        sug_card.pack(fill="x", pady=6)

        ctk.CTkLabel(sug_card, text="⭐  السعر التنافسي المقترح للبيع (شامل الضريبة إن وجدت):",
                     font=ctk.CTkFont(APP_FONT, 11, "bold"),
                     text_color=("#92400E", "#FCD34D")).pack(anchor="e", padx=16, pady=(8, 0))

        self._sug_price_lbl = ctk.CTkLabel(
            sug_card, text="—  ر.س",
            font=ctk.CTkFont(APP_FONT, 24, "bold"),
            text_color=("#B45309", "#FBBF24")
        )
        self._sug_price_lbl.pack(anchor="center", pady=(2, 8))

        # Export & Actions
        self._btn_export_excel = ctk.CTkButton(
            scroll, text="📊  تصدير بطاقة المقارنة (Excel)",
            font=ctk.CTkFont(APP_FONT, 13, "bold"),
            fg_color=BRAND_GREEN, hover_color=BRAND_GREEN_HOVER,
            corner_radius=10, height=42, state="disabled",
            command=self._export_to_excel
        )
        self._btn_export_excel.pack(fill="x", pady=(10, 6))

    # ─── 6. FOOTER STATUS BAR ────────────────────────────────────────────────
    def _build_footer(self, parent):
        footer = ctk.CTkFrame(parent, fg_color=HDR_BG, height=34, corner_radius=0)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        self._status_lbl = ctk.CTkLabel(footer, text="جاهز للبحث والمقارنة في 34 متجراً...",
                                        font=ctk.CTkFont(APP_FONT, 11),
                                        text_color=HDR_TITLE_COLOR)
        self._status_lbl.pack(side="right", padx=16)

        self._time_lbl = ctk.CTkLabel(footer, text="", font=ctk.CTkFont(APP_FONT, 10),
                                      text_color=BRAND_GOLD)
        self._time_lbl.pack(side="left", padx=16)

    # ═════════════════════════════════════════════════════════════════════════
    # ⚡ ACTIONS & THREADING LOGIC
    # ═════════════════════════════════════════════════════════════════════════
    def _start_search(self):
        query = self._barcode_entry.get().strip()
        if not query:
            messagebox.showwarning("تنبيه", "يرجى مسح أو إدخال باركود أو كود الصنف أولاً.")
            self._barcode_entry.focus_set()
            return

        if self.is_searching:
            return

        self.is_searching = True
        self._btn_search.configure(state="disabled", text="⏳ جاري البحث...")
        self._status_lbl.configure(text=f"🔍 جاري البحث عن ({query}) في Odoo و 34 متجراً منافساً...")

        # Reset live progress counters and store cards
        self._live_completed_count = 0
        self._live_found_count = 0
        self._completed_store_keys = set()

        for key, s_ui in self._store_cards.items():
            s_ui['found'] = False
            s_ui['price'] = 0.0
            s_ui['badge'].configure(text="جاري الفحص...", fg_color=("#FEF3C7", "#78350F"))
            s_ui['price_lbl'].configure(text="—  ر.س", text_color=("#0F172A", "#F8FAFC"))
            s_ui['title_lbl'].configure(text="جاري استعلام المتجر بالتزامن...")
            s_ui['method_lbl'].configure(text="")
            s_ui['btn_open'].configure(state="disabled")

        self._seg_filter.set("🌐 الكل (34)")
        self._comp_filter_mode = "all"
        self._apply_store_filter()

        start_t = time.time()

        def _worker():
            try:
                # 1. Immediate targeted lookup in Odoo
                p_res = lookup_product_by_barcode_or_code(query)

                if not p_res.get('success'):
                    self.after(0, lambda: self._on_odoo_not_found(p_res.get('error'), query))
                    return

                # Update Odoo UI immediately
                self.current_product = p_res
                self.after(0, lambda: self._populate_odoo_ui(p_res))

                # 2. Competitor search strictly by product barcodes (No name/description search)
                all_bcs = p_res.get('all_barcodes', [])
                if not all_bcs:
                    bc = p_res.get('primary_barcode')
                    if bc:
                        all_bcs = [bc]

                def _progress_cb(store_name, status_text):
                    pass

                def _on_store_result_cb(store_key, res):
                    self.after(0, lambda sk=store_key, r=res: self._update_single_store_card(sk, r))

                comp_results = search_all_competitors(
                    all_bcs,
                    on_store_result=_on_store_result_cb,
                    progress_callback=_progress_cb
                )
                self.current_competitors = comp_results

                elapsed = round(time.time() - start_t, 2)
                self.after(0, lambda: self._on_search_complete(comp_results, elapsed))

            except Exception as e:
                self.after(0, lambda: self._on_search_error(e))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_odoo_not_found(self, err_msg, query):
        self.is_searching = False
        self._btn_search.configure(state="normal", text="🔍  بحث ومقارنة شاملة")
        self._status_lbl.configure(text=f"❌ لم يتم العثور على الصنف ({query})")
        self._odoo_match_badge.configure(text="غير موجود", fg_color=("#FEE2E2", "#7F1D1D"))
        messagebox.showinfo("غير موجود في Odoo", err_msg)
        self._barcode_entry.focus_set()

    def _on_search_error(self, err):
        self.is_searching = False
        self._btn_search.configure(state="normal", text="🔍  بحث ومقارنة شاملة")
        self._status_lbl.configure(text=f"❌ خطأ أثناء الفحص: {err}")
        messagebox.showerror("خطأ", f"حدث خطأ أثناء الاتصال أو المعالجة:\n\n{err}")
        self._barcode_entry.focus_set()

    def _populate_odoo_ui(self, p):
        self._odoo_match_badge.configure(text=p.get('matched_by', 'مطابق'), fg_color=("#D1FAE5", "#064E3B"))
        self._odoo_code_lbl.configure(text=p.get('default_code') or 'بدون كود')
        self._odoo_name_ar.configure(text=p.get('name_ar') or '—')
        self._odoo_name_en.configure(text=p.get('name_en') or '—')
        self._odoo_barcode.configure(text=p.get('primary_barcode') or 'بدون باركود أساسي')

        # Packaging barcodes
        pkgs = p.get('packaging_barcodes', [])
        if pkgs:
            lines = [f"• {pkg['name']} (سعة {int(pkg['qty'])}): {pkg['barcode']}" for pkg in pkgs]
            self._odoo_pkg_lbl.configure(text="\n".join(lines))
        else:
            self._odoo_pkg_lbl.configure(text="لا توجد باركودات تعبئة إضافية مسجلة")

        # Tax Status (ZATCA)
        is_taxable = p.get('is_taxable', False)
        tax_rate = float(p.get('tax_rate', 0.0))
        tax_name = p.get('tax_name', 'معفى من الضريبة (0%)')

        if is_taxable and tax_rate > 0:
            self._odoo_tax_badge.configure(text=f"خاضع {tax_rate:.0f}%", fg_color=("#DBEAFE", "#1E3A8A"))
            self._odoo_tax_lbl.configure(
                text=f"{tax_name} — أسعار البيع شاملة ضريبة القيمة المضافة",
                text_color=("#2563EB", "#60A5FA")
            )
        else:
            self._odoo_tax_badge.configure(text="معفى 0%", fg_color=("#D1FAE5", "#064E3B"))
            self._odoo_tax_lbl.configure(
                text="✨ معفى من ضريبة القيمة المضافة (0% VAT) — ميزة سعرية وتنافسية",
                text_color=("#10B981", "#34D399")
            )

        self._odoo_cost_lbl.configure(text=f"{p.get('cost_price', 0.0):.2f} ر.س")
        self._odoo_retail_lbl.configure(text=f"{p.get('retail_price', 0.0):.2f} ر.س")

        net_p = p.get('net_last_purchase_price', 0.0)
        disc = p.get('last_purchase_discount', 0.0)
        if net_p > 0:
            self._odoo_net_purchase_lbl.configure(text=f"{net_p:.2f} ر.س  (خصم {disc:.1f}%)")
        else:
            self._odoo_net_purchase_lbl.configure(text="غير متوفر في أوامر الشراء")

        v_name = p.get('vendor_name') or 'غير محدد'
        self._odoo_vendor_lbl.configure(text=v_name)
        self._odoo_date_lbl.configure(text=p.get('last_purchase_date') or '—')
        self._odoo_stock_lbl.configure(text=f"{p.get('qty_available', 0.0):,.0f} {p.get('uom_name', 'حبة')}")

    def _update_single_store_card(self, key, res):
        card = self._store_cards.get(key)
        if not card:
            return

        if key not in self._completed_store_keys:
            self._completed_store_keys.add(key)
            self._live_completed_count += 1

        is_found = res.get('found') and float(res.get('price') or 0.0) > 0.5
        is_in_stock = res.get('in_stock', True)
        if is_found:
            card['found'] = True
            card['in_stock'] = is_in_stock
            card['price'] = float(res['price'])
            if is_in_stock:
                self._live_found_count += 1
                card['badge'].configure(text="متوفر ✅", fg_color=("#D1FAE5", "#064E3B"))
            else:
                card['badge'].configure(text="نفد من المخزون ⚠️", fg_color=("#FEF3C7", "#78350F"))

            p_val = float(res['price'])
            reg_val = float(res.get('regular_price') or 0.0)
            if reg_val > p_val:
                card['price_lbl'].configure(
                    text=f"{p_val:.2f}  ر.س  (خصم من {reg_val:.2f})",
                    text_color=("#16A34A", "#34D399")
                )
            else:
                card['price_lbl'].configure(text=f"{p_val:.2f}  ر.س", text_color=("#16A34A", "#34D399"))

            unit_text = res.get('unit') or ''
            if unit_text:
                card['unit_lbl'].configure(text=f"📦 {unit_text}")
                card['unit_lbl'].pack(side="right", padx=(0, 8))
            else:
                card['unit_lbl'].pack_forget()

            card['method_lbl'].configure(text=res.get('matched_by', 'مطابقة باركود'))
            card['title_lbl'].configure(text=res.get('title') or '—')
            card['url'] = res.get('url', '')
            card['btn_open'].configure(state="normal", command=lambda u=res.get('url'): self._open_browser_url(u))
        else:
            card['found'] = False
            card['in_stock'] = False
            card['price'] = 0.0
            card['unit_lbl'].pack_forget()
            card['badge'].configure(text="غير متوفر ❌", fg_color=("#FEE2E2", "#7F1D1D"))
            card['price_lbl'].configure(text="غير متوفر بالباركود", text_color=BRAND_SLATE)
            card['method_lbl'].configure(text="")
            card['title_lbl'].configure(text=res.get('error') or "غير متوفر بالباركود في هذا المتجر.")
            card['btn_open'].configure(state="disabled")

        # Live Streaming Progress Badge & Label
        total_stores = len(STORES_REGISTRY)
        display_completed = min(self._live_completed_count, total_stores)
        self._comp_status_badge.configure(
            text=f"فحص مباشر: {display_completed}/{total_stores} ({self._live_found_count} متوفر)",
            fg_color=("#D1FAE5", "#064E3B") if self._live_found_count > 0 else ("#FEF3C7", "#78350F")
        )
        self._status_lbl.configure(
            text=f"⚡ فحص متزامن فائق السرعة: تم استلام {display_completed} من {total_stores} متجراً (رصد {self._live_found_count} عروض متوفرة حتى الآن)..."
        )

    def _on_search_complete(self, comp_results, elapsed):
        self.is_searching = False
        self._btn_search.configure(state="normal", text="🔍  بحث ومقارنة شاملة")
        self._time_lbl.configure(text=f"⏱️ {elapsed}s")

        total_stores = len(STORES_REGISTRY)
        if self._live_found_count > 0:
            self._comp_status_badge.configure(
                text=f"تم رصد {self._live_found_count} من {total_stores} متجراً",
                fg_color=("#D1FAE5", "#064E3B")
            )
            self._status_lbl.configure(
                text=f"✅ اكتمل الفحص المتزامن لجميع الـ 34 متجراً خلال {elapsed} ثانية (متوفر في {self._live_found_count} متجراً)."
            )
            self._seg_filter.set("🟢 المتوفرة فقط")
            self._comp_filter_mode = "found"
        else:
            self._comp_status_badge.configure(
                text=f"غير متوفر في أي من الـ {total_stores} متجراً",
                fg_color=("#FEE2E2", "#7F1D1D")
            )
            self._status_lbl.configure(
                text=f"ℹ️ انتهى الفحص المتزامن خلال {elapsed} ثانية: الصنف غير معروض بالباركود في أي متجر."
            )
            self._seg_filter.set("🌐 الكل (34)")
            self._comp_filter_mode = "all"

        self._apply_store_filter()
        self._update_strategy_section()

    def _open_browser_url(self, url):
        if url:
            webbrowser.open(url)

    def _update_strategy_section(self):
        if not self.current_product:
            return

        try:
            target_margin = float(self._target_margin_entry.get().strip() or 20.0)
        except ValueError:
            target_margin = 20.0
        self.settings["target_margin"] = target_margin
        save_settings(self.settings)

        cost_basis = self._cost_basis_var.get()
        if cost_basis == "net_purchase" and self.current_product.get('net_last_purchase_price', 0.0) > 0:
            effective_cost = self.current_product['net_last_purchase_price']
        else:
            effective_cost = self.current_product.get('cost_price', 0.0)

        effective_retail = self.current_product.get('retail_price', 0.0)
        is_taxable = self.current_product.get('is_taxable', True)
        tax_rate = self.current_product.get('tax_rate', 15.0)

        analysis = analyze_market_competition(
            our_cost=effective_cost,
            our_retail=effective_retail,
            competitors_data=self.current_competitors,
            target_margin_pct=target_margin,
            is_taxable=is_taxable,
            tax_rate=tax_rate
        )
        self.current_analysis = analysis

        # Update stat metrics
        if analysis['has_competitors']:
            self._stat_lowest_price.configure(text=f"{analysis['lowest_price']:.2f} ر.س\n({analysis['lowest_store']})")
            self._stat_avg_price.configure(text=f"{analysis['avg_price']:.2f} ر.س")

            diff = analysis['price_diff']
            if diff > 0:
                self._stat_price_diff.configure(text=f"+{diff:.2f} ر.س (+{analysis['price_diff_pct']:.1f}%)\nأغلى من المنافس", text_color="#EF4444")
            elif diff < 0:
                self._stat_price_diff.configure(text=f"{diff:.2f} ر.س ({analysis['price_diff_pct']:.1f}%)\nأرخص من المنافس", text_color="#10B981")
            else:
                self._stat_price_diff.configure(text="0.00 ر.س (مطابق تماماً)", text_color=BRAND_GOLD)

            if analysis['potential_margin_pct'] is not None:
                p_margin = analysis['potential_margin_pct']
                m_color = "#10B981" if p_margin >= target_margin else ("#F59E0B" if p_margin >= 5 else "#EF4444")
                self._stat_target_margin.configure(text=f"{p_margin:.1f}%\n({analysis['potential_profit_val']:.2f} ر.س)", text_color=m_color)
            else:
                self._stat_target_margin.configure(text="—")
        else:
            self._stat_lowest_price.configure(text="غير معروض")
            self._stat_avg_price.configure(text="—")
            self._stat_price_diff.configure(text="—", text_color=BRAND_SLATE)
            self._stat_target_margin.configure(text=f"{analysis['current_margin_pct']:.1f}%\n(الهامش الحالي)", text_color=BRAND_GOLD)

        # Update Recommendation Hero Card
        status_bg_map = {
            'leader': ("#D1FAE5", "#064E3B"),
            'opportunity': ("#FEF3C7", "#78350F"),
            'caution': ("#FFEDD5", "#7C2D12"),
            'danger': ("#FEE2E2", "#7F1D1D"),
            'exclusive': ("#DBEAFE", "#1E3A8A"),
        }
        badge_bg = status_bg_map.get(analysis.get('status_level'), ("#E2E8F0", "#334155"))
        self._strategy_badge.configure(text=analysis['status_badge'], fg_color=badge_bg)
        self._rec_card.configure(border_color=analysis['status_color'])
        self._rec_title_lbl.configure(text=analysis['status_title'], text_color=analysis['status_color'])
        self._rec_body_lbl.configure(text=analysis['recommendation_text'])

        # Suggested Price
        sug_p = analysis.get('suggested_price') or effective_retail
        self._sug_price_lbl.configure(text=f"{sug_p:.2f}  ر.س")

        self._btn_export_excel.configure(state="normal")

    def _clear_all(self):
        self._barcode_entry.delete(0, "end")
        self._barcode_entry.focus_set()
        self.current_product = None
        self.current_competitors = None
        self.current_analysis = None

        self._odoo_match_badge.configure(text="جاهز للبحث", fg_color=("#E2E8F0", "#334155"))
        self._odoo_code_lbl.configure(text="—")
        self._odoo_name_ar.configure(text="—")
        self._odoo_name_en.configure(text="—")
        self._odoo_barcode.configure(text="—")
        self._odoo_pkg_lbl.configure(text="—")
        self._odoo_tax_badge.configure(text="—", fg_color=("#E2E8F0", "#334155"))
        self._odoo_tax_lbl.configure(text="—")
        self._odoo_cost_lbl.configure(text="—")
        self._odoo_retail_lbl.configure(text="—")
        self._odoo_net_purchase_lbl.configure(text="—")
        self._odoo_vendor_lbl.configure(text="—")
        self._odoo_date_lbl.configure(text="—")
        self._odoo_stock_lbl.configure(text="—")

        self._comp_status_badge.configure(text=f"{len(STORES_REGISTRY)} متجراً معتمداً", fg_color=("#E2E8F0", "#334155"))
        self._store_filter_entry.delete(0, "end")
        self._seg_filter.set(f"🌐 الكل ({len(STORES_REGISTRY)})")
        self._comp_filter_mode = "all"

        for key, s_ui in self._store_cards.items():
            s_ui['found'] = False
            s_ui['price'] = 0.0
            s_ui['unit_lbl'].pack_forget()
            s_ui['badge'].configure(text="في الانتظار...", fg_color=("#E2E8F0", "#1E293B"))
            s_ui['price_lbl'].configure(text="—  ر.س", text_color=("#0F172A", "#F8FAFC"))
            s_ui['title_lbl'].configure(text="لم يتم البحث بعد.")
            s_ui['method_lbl'].configure(text="")
            s_ui['btn_open'].configure(state="disabled")

        self._apply_store_filter()

        self._stat_lowest_price.configure(text="—")
        self._stat_avg_price.configure(text="—")
        self._stat_price_diff.configure(text="—")
        self._stat_target_margin.configure(text="—")

        self._strategy_badge.configure(text="بانتظار البيانات", fg_color=("#E2E8F0", "#334155"))
        self._rec_card.configure(border_color=("#3B82F6", "#1E3A8A"))
        self._rec_title_lbl.configure(text="قم بمسح أو إدخال باركود لعرض التحليل الذكي", text_color=BRAND_BLUE)
        self._rec_body_lbl.configure(text="سيقوم النظام آلياً بمطابقة الأسعار وحساب الهامش الربحي والتوصية بالتسعير التنافسي الأمثل مع مراعاة الضريبة.")
        self._sug_price_lbl.configure(text="—  ر.س")
        self._btn_export_excel.configure(state="disabled")
        self._status_lbl.configure(text=f"جاهز للبحث والمقارنة في {len(STORES_REGISTRY)} متجراً...")
        self._time_lbl.configure(text="")

    def _export_to_excel(self):
        if not self.current_product or not self.current_analysis:
            return

        default_name = f"مقارنة_أسعار_{self.current_product.get('default_code', 'صنف')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        out_path = filedialog.asksaveasfilename(
            initialdir=desktop,
            initialfile=default_name,
            defaultextension=".xlsx",
            filetypes=[("Excel Files", "*.xlsx")]
        )
        if not out_path:
            return

        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "مقارنة الأسعار والمنافسين"
            ws.views.sheetView[0].rightToLeft = True

            font_title = Font(name="Segoe UI", size=14, bold=True, color="1E3A8A")
            font_hdr   = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
            font_bold  = Font(name="Segoe UI", size=11, bold=True)
            font_body  = Font(name="Segoe UI", size=10)

            fill_hdr  = PatternFill("solid", fgColor="1E40AF")
            fill_gold = PatternFill("solid", fgColor="FEF3C7")
            thin_border = Border(left=Side(style='thin', color='CBD5E1'),
                                 right=Side(style='thin', color='CBD5E1'),
                                 top=Side(style='thin', color='CBD5E1'),
                                 bottom=Side(style='thin', color='CBD5E1'))

            # Title
            ws.merge_cells("A1:E1")
            c = ws.cell(row=1, column=1, value="🎯 كشف مقارنة الأسعار ومراقبة المنافسين (34 متجراً) — شركة العسلي التجارية")
            c.font = font_title
            c.alignment = Alignment(horizontal="center", vertical="center")
            ws.row_dimensions[1].height = 34

            p = self.current_product
            a = self.current_analysis

            tax_label = a.get('tax_status_label', 'خاضع للضريبة (15% VAT)')

            rows = [
                ("كود الصنف الداخلي", p.get('default_code', ''), "تاريخ الاستعلام", datetime.now().strftime('%Y/%m/%d %H:%M')),
                ("الاسم باللغة العربية", p.get('name_ar', ''), "الباركود الأساسي", p.get('primary_barcode', '')),
                ("الاسم باللغة الإنجليزية", p.get('name_en', ''), "الرصيد المتوفر", f"{p.get('qty_available', 0):,.0f} {p.get('uom_name', '')}"),
                ("سعر التكلفة (Cost)", f"{p.get('cost_price', 0):.2f} ر.س", "سعر البيع الحالي", f"{p.get('retail_price', 0):.2f} ر.س"),
                ("صافي آخر سعر شراء", f"{p.get('net_last_purchase_price', 0):.2f} ر.س", "آخر مورد", p.get('vendor_name', '')),
                ("الوضع الضريبي", tax_label, "الهامش الصافي الحالي", f"{a.get('current_margin_pct', 0):.1f}%"),
            ]

            r_idx = 3
            for r_data in rows:
                ws.cell(row=r_idx, column=1, value=r_data[0]).font = font_bold
                ws.cell(row=r_idx, column=2, value=r_data[1]).font = font_body
                ws.cell(row=r_idx, column=4, value=r_data[2]).font = font_bold
                ws.cell(row=r_idx, column=5, value=r_data[3]).font = font_body
                for col_i in range(1, 6):
                    ws.cell(row=r_idx, column=col_i).border = thin_border
                r_idx += 1

            r_idx += 1
            # Competitors Table
            headers = ["المتجر المنافس", "السعر المعروض", "الحجم / الوحدة", "حالة التوفر", "طريقة المطابقة", "رابط المتجر"]
            for c_i, h in enumerate(headers, 1):
                cell = ws.cell(row=r_idx, column=c_i, value=h)
                cell.font = font_hdr
                cell.fill = fill_hdr
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.border = thin_border
            ws.row_dimensions[r_idx].height = 26

            r_idx += 1
            # Sort competitors so in-stock found appear first, then out-of-stock, then not found
            comp_list = list((self.current_competitors or {}).items())
            comp_list.sort(key=lambda item: (
                0 if (item[1].get('found') and item[1].get('in_stock', True)) else (1 if item[1].get('found') else 2),
                float(item[1].get('price') or 999999)
            ))

            for key, c_info in comp_list:
                p_text = f"{c_info['price']:.2f} ر.س" if c_info.get('found') and float(c_info.get('price') or 0) > 0.5 else "غير متوفر"
                unit_txt = c_info.get('unit') or "—"
                avail = ("متوفر ✅" if c_info.get('in_stock', True) else "نفد من المخزون ⚠️") if c_info.get('found') else "غير متوفر بالباركود"
                matched = c_info.get('matched_by', '—')
                url = c_info.get('url', '')

                ws.cell(row=r_idx, column=1, value=c_info.get('site_name', key)).font = font_bold
                ws.cell(row=r_idx, column=2, value=p_text).font = font_bold
                ws.cell(row=r_idx, column=3, value=unit_txt).font = font_body
                ws.cell(row=r_idx, column=4, value=avail).font = font_body
                ws.cell(row=r_idx, column=5, value=matched).font = font_body
                ws.cell(row=r_idx, column=6, value=url).font = font_body
                for c_i in range(1, 7):
                    ws.cell(row=r_idx, column=c_i).border = thin_border
                r_idx += 1

            r_idx += 1
            # Strategic Recommendation Summary
            ws.merge_cells(start_row=r_idx, start_column=1, end_row=r_idx, end_column=6)
            rec_hdr = ws.cell(row=r_idx, column=1, value=f"⭐ التوصية الاستراتيجية: {a.get('status_title', '')}")
            rec_hdr.font = font_bold
            rec_hdr.fill = fill_gold
            ws.row_dimensions[r_idx].height = 28
            r_idx += 1

            ws.merge_cells(start_row=r_idx, start_column=1, end_row=r_idx, end_column=6)
            rec_body = ws.cell(row=r_idx, column=1, value=a.get('recommendation_text', ''))
            rec_body.font = font_body
            rec_body.alignment = Alignment(wrap_text=True, vertical="center")
            ws.row_dimensions[r_idx].height = 55
            r_idx += 1

            ws.merge_cells(start_row=r_idx, start_column=1, end_row=r_idx, end_column=6)
            sug_cell = ws.cell(row=r_idx, column=1, value=f"السعر التنافسي المقترح: {a.get('suggested_price', 0):.2f} ر.س")
            sug_cell.font = font_title
            sug_cell.alignment = Alignment(horizontal="center", vertical="center")
            ws.row_dimensions[r_idx].height = 32

            ws.column_dimensions['A'].width = 24
            ws.column_dimensions['B'].width = 18
            ws.column_dimensions['C'].width = 16
            ws.column_dimensions['D'].width = 20
            ws.column_dimensions['E'].width = 22
            ws.column_dimensions['F'].width = 44

            wb.save(out_path)
            messagebox.showinfo("تم التصدير", f"🎉 تم تصدير كشف المقارنة بنجاح:\n\n{out_path}")
            if os.path.exists(out_path):
                os.startfile(out_path)
        except Exception as e:
            messagebox.showerror("خطأ في التصدير", f"تعذر حفظ ملف Excel:\n\n{e}")

    # ═════════════════════════════════════════════════════════════════════════
    # 📑 TAB 2: BATCH EXCEL PRICING IMPLEMENTATION
    # ═════════════════════════════════════════════════════════════════════════
    def _build_batch_excel_tab(self, parent):
        self._batch_file_path = ctk.StringVar(value="")
        self._batch_sheet_var = ctk.StringVar(value="")
        self._batch_barcode_col_var = ctk.StringVar(value="")
        self._batch_price_col_var = ctk.StringVar(value="")
        self._batch_workers_var = ctk.StringVar(value="10")
        self._batch_store_vars = {}
        self._active_pricer = None
        self._is_batch_running = False
        self._batch_output_file = None
        self._batch_excel_info = None

        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=8, pady=4)

        # ── 1. Top Card: File Selection & Column Configuration ───────────────
        card_file = ctk.CTkFrame(container, fg_color=BG_CARD, corner_radius=12,
                                 border_width=1, border_color=BORDER_SUBTLE)
        card_file.pack(fill="x", pady=(0, 6))

        row1 = ctk.CTkFrame(card_file, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=(10, 4))

        ctk.CTkLabel(row1, text="📁 ملف الإكسيل المستهدف:",
                     font=ctk.CTkFont(APP_FONT, 12, "bold")).pack(side="right", padx=(8, 0))

        self._entry_batch_file = ctk.CTkEntry(row1, textvariable=self._batch_file_path,
                                              font=ctk.CTkFont("Consolas", 11),
                                              placeholder_text="اضغط على زر (استعراض الملف) لاختيار ملف إكسيل (.xlsx)...",
                                              height=36, state="readonly")
        self._entry_batch_file.pack(side="right", fill="x", expand=True, padx=8)

        btn_browse = ctk.CTkButton(row1, text="📂 استعراض الملف...", width=140, height=36,
                                   font=ctk.CTkFont(APP_FONT, 11, "bold"),
                                   fg_color=BRAND_BLUE, hover_color=BRAND_BLUE_HOVER,
                                   command=self._on_browse_batch_file)
        btn_browse.pack(side="left")

        # Row 2: Dropdowns for Sheet, Barcode Col, Price Col, Threads
        row2 = ctk.CTkFrame(card_file, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=(0, 4))

        # Threads
        f_thr = ctk.CTkFrame(row2, fg_color="transparent")
        f_thr.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(f_thr, text="السرعة (خيوط):", font=ctk.CTkFont(APP_FONT, 10)).pack(side="top", anchor="w")
        self._opt_workers = ctk.CTkOptionMenu(f_thr, values=["5 خيوط", "10 خيوط (الموصى به)", "15 خيطاً", "20 خيطاً"],
                                              variable=self._batch_workers_var, width=135, height=28)
        self._opt_workers.set("10 خيوط (الموصى به)")
        self._opt_workers.pack(side="top")

        # Our Price Column (Optional)
        f_pr = ctk.CTkFrame(row2, fg_color="transparent")
        f_pr.pack(side="right", fill="x", expand=True, padx=6)
        ctk.CTkLabel(f_pr, text="عمود سعرنا (لحساب الفارق):", font=ctk.CTkFont(APP_FONT, 10)).pack(side="top", anchor="e")
        self._opt_price_col = ctk.CTkOptionMenu(f_pr, values=["(لا يوجد / تخطي)"],
                                                variable=self._batch_price_col_var, height=28)
        self._opt_price_col.pack(side="top", fill="x")

        # Barcode Column
        f_bc = ctk.CTkFrame(row2, fg_color="transparent")
        f_bc.pack(side="right", fill="x", expand=True, padx=6)
        ctk.CTkLabel(f_bc, text="عمود الباركود (GTIN):", font=ctk.CTkFont(APP_FONT, 10, "bold")).pack(side="top", anchor="e")
        self._opt_bc_col = ctk.CTkOptionMenu(f_bc, values=["— اختر ملف أولاً —"],
                                             variable=self._batch_barcode_col_var, height=28)
        self._opt_bc_col.pack(side="top", fill="x")

        # Sheet Dropdown
        f_sh = ctk.CTkFrame(row2, fg_color="transparent")
        f_sh.pack(side="right", padx=(0, 6))
        ctk.CTkLabel(f_sh, text="ورقة العمل:", font=ctk.CTkFont(APP_FONT, 10)).pack(side="top", anchor="e")
        self._opt_sheet = ctk.CTkOptionMenu(f_sh, values=["Sheet1"],
                                            variable=self._batch_sheet_var, width=120, height=28,
                                            command=self._on_sheet_changed)
        self._opt_sheet.pack(side="top")

        # Row 3: Status hint
        self._lbl_file_summary = ctk.CTkLabel(card_file, text="💡 حدد ملف الإكسيل ليبدأ البرنامج بالتعرف التلقائي على عمود الباركود والأصناف.",
                                              font=ctk.CTkFont(APP_FONT, 10), text_color=BRAND_SLATE)
        self._lbl_file_summary.pack(anchor="e", padx=16, pady=(0, 8))

        # ── 2. Middle Card: Multi-Store Competitor Selector ───────────────────
        card_stores = ctk.CTkFrame(container, fg_color=BG_CARD, corner_radius=12,
                                   border_width=1, border_color=BORDER_SUBTLE)
        card_stores.pack(fill="both", expand=True, pady=(0, 6))

        st_top = ctk.CTkFrame(card_stores, fg_color="transparent")
        st_top.pack(fill="x", padx=16, pady=(8, 4))

        ctk.CTkLabel(st_top, text="🏬 اختر المتاجر المنافسة المراد تضمين تسعيرتها في ملف الإكسيل:",
                     font=ctk.CTkFont(APP_FONT, 12, "bold"), text_color=BRAND_GOLD).pack(side="right")

        # Quick action pills
        ctk.CTkButton(st_top, text="⚡ المتاجر السريعة", width=105, height=26,
                      font=ctk.CTkFont(APP_FONT, 10, "bold"), fg_color="#0F766E", hover_color="#0D5F58",
                      command=lambda: self._quick_select_stores("fast")).pack(side="left", padx=3)
        ctk.CTkButton(st_top, text="⭐ كبار المنافسين (5)", width=115, height=26,
                      font=ctk.CTkFont(APP_FONT, 10, "bold"), fg_color="#D97706", hover_color="#B45309",
                      command=lambda: self._quick_select_stores("top5")).pack(side="left", padx=3)
        ctk.CTkButton(st_top, text="❌ إلغاء التحديد", width=85, height=26,
                      font=ctk.CTkFont(APP_FONT, 10), fg_color="#475569", hover_color="#334155",
                      command=lambda: self._quick_select_stores("none")).pack(side="left", padx=3)
        ctk.CTkButton(st_top, text="✅ تحديد الكل (37)", width=105, height=26,
                      font=ctk.CTkFont(APP_FONT, 10, "bold"), fg_color=BRAND_BLUE, hover_color=BRAND_BLUE_HOVER,
                      command=lambda: self._quick_select_stores("all")).pack(side="left", padx=3)

        # Scrollable Store Checkboxes Grid
        scroll_stores = ctk.CTkScrollableFrame(card_stores, fg_color=BG_CARD_LIGHT, corner_radius=8)
        scroll_stores.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        # Layout in 4 columns
        for idx, store in enumerate(STORES_REGISTRY):
            k = store['key']
            name = store['name']
            domain = store['domain']
            color = store.get('color', '#64748B')

            # Default: top 3 selected by default
            is_def = k in ['daralamirat', 'care_outlet', 'sidalih']
            var = ctk.BooleanVar(value=is_def)
            self._batch_store_vars[k] = var

            r = idx // 4
            c = 3 - (idx % 4)  # RTL order

            chk_txt = f"{name} ({domain})"
            chk = ctk.CTkCheckBox(
                scroll_stores,
                text=chk_txt,
                variable=var,
                font=ctk.CTkFont(APP_FONT, 10),
                checkbox_width=16,
                checkbox_height=16,
                corner_radius=4,
                hover_color=color,
                fg_color=color
            )
            chk.grid(row=r, column=c, sticky="e", padx=6, pady=3)

        for col_i in range(4):
            scroll_stores.grid_columnconfigure(col_i, weight=1)

        # ── 3. Bottom Card: Execution Controls & Live Progress ───────────────
        card_exec = ctk.CTkFrame(container, fg_color=BG_CARD, corner_radius=12,
                                 border_width=1, border_color=BORDER_SUBTLE)
        card_exec.pack(fill="x", pady=(0, 2))

        act_row = ctk.CTkFrame(card_exec, fg_color="transparent")
        act_row.pack(fill="x", padx=16, pady=(8, 4))

        self._btn_batch_start = ctk.CTkButton(
            act_row, text="⚡  بدء تسعير وتحديث ملف الإكسيل الآن",
            font=ctk.CTkFont(APP_FONT, 12, "bold"),
            fg_color=BRAND_GREEN, hover_color=BRAND_GREEN_HOVER,
            height=38, width=260, command=self._start_batch_pricing
        )
        self._btn_batch_start.pack(side="right", padx=(6, 0))

        self._btn_batch_pause = ctk.CTkButton(
            act_row, text="⏸️  إيقاف مؤقت",
            font=ctk.CTkFont(APP_FONT, 11, "bold"),
            fg_color="#D97706", hover_color="#B45309",
            height=38, width=110, state="disabled",
            command=self._toggle_batch_pause
        )
        self._btn_batch_pause.pack(side="right", padx=4)

        self._btn_batch_cancel = ctk.CTkButton(
            act_row, text="⏹️  إيقاف وحفظ ما تم",
            font=ctk.CTkFont(APP_FONT, 11, "bold"),
            fg_color=BRAND_RED, hover_color=BRAND_RED_HOVER,
            height=38, width=130, state="disabled",
            command=self._cancel_batch_pricing
        )
        self._btn_batch_cancel.pack(side="right", padx=4)

        self._btn_batch_open = ctk.CTkButton(
            act_row, text="📂  فتح ملف الإكسيل المحدث",
            font=ctk.CTkFont(APP_FONT, 11, "bold"),
            fg_color=BRAND_BLUE, hover_color=BRAND_BLUE_HOVER,
            height=38, width=180, state="disabled",
            command=self._open_batch_output_file
        )
        self._btn_batch_open.pack(side="left")

        # Progress Bar & Stats
        prog_row = ctk.CTkFrame(card_exec, fg_color="transparent")
        prog_row.pack(fill="x", padx=16, pady=(0, 2))

        self._batch_progress_bar = ctk.CTkProgressBar(prog_row, height=10, corner_radius=5)
        self._batch_progress_bar.pack(fill="x", pady=(2, 4))
        self._batch_progress_bar.set(0)

        stats_row = ctk.CTkFrame(card_exec, fg_color="transparent")
        stats_row.pack(fill="x", padx=16, pady=(0, 6))

        self._lbl_batch_stats = ctk.CTkLabel(
            stats_row, text="جاهز للبدء... اختر ملف إكسيل والمتاجر المستهدفة.",
            font=ctk.CTkFont(APP_FONT, 11, "bold")
        )
        self._lbl_batch_stats.pack(side="right")

        self._lbl_batch_ticker = ctk.CTkLabel(
            stats_row, text="",
            font=ctk.CTkFont("Consolas", 10), text_color=BRAND_GOLD
        )
        self._lbl_batch_ticker.pack(side="left")

    def _on_browse_batch_file(self):
        f = filedialog.askopenfilename(
            title="اختر ملف الإكسيل المحتوي على الباركودات",
            filetypes=[("Excel Files", "*.xlsx;*.xls"), ("All Files", "*.*")]
        )
        if not f:
            return

        self._batch_file_path.set(f)
        try:
            info = inspect_excel_file(f)
            self._batch_excel_info = info

            # Update sheet options
            self._opt_sheet.configure(values=info["sheets"])
            self._opt_sheet.set(info["active_sheet"])

            # Update columns
            col_opts = [f"{i+1}. {h}" for i, h in enumerate(info["headers"])]
            self._opt_bc_col.configure(values=col_opts)
            if info["detected_barcode_col"] is not None and info["detected_barcode_col"] < len(col_opts):
                self._opt_bc_col.set(col_opts[info["detected_barcode_col"]])
            elif col_opts:
                self._opt_bc_col.set(col_opts[0])

            self._opt_price_col.configure(values=["(لا يوجد / تخطي)"] + col_opts)
            if info["detected_price_col"] is not None and info["detected_price_col"] < len(col_opts):
                self._opt_price_col.set(col_opts[info["detected_price_col"]])
            else:
                self._opt_price_col.set("(لا يوجد / تخطي)")

            bc_h = info["headers"][info["detected_barcode_col"]] if info["detected_barcode_col"] is not None else "لم يُحدد"
            self._lbl_file_summary.configure(
                text=f"✅ تم فحص الملف بنجاح! إجمالي الأسطر: {info['total_data_rows']} صنفاً. عمود الباركود التلقائي: [{bc_h}]",
                text_color=BRAND_GREEN
            )
            self._lbl_batch_stats.configure(text=f"جاهز لتسعير {info['total_data_rows']} صنفاً...")
        except Exception as ex:
            messagebox.showerror("خطأ في فحص الملف", f"تعذر قراءة ملف الإكسيل:\n{ex}")

    def _on_sheet_changed(self, sheet_name):
        f = self._batch_file_path.get().strip()
        if not f or not os.path.exists(f):
            return
        try:
            wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
            if sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                for row in ws.iter_rows(values_only=True):
                    non_empty = [c for c in row if c is not None and str(c).strip() != ""]
                    if non_empty:
                        headers = [str(c).strip() if c is not None else f"Column_{i+1}" for i, c in enumerate(row)]
                        col_opts = [f"{i+1}. {h}" for i, h in enumerate(headers)]
                        self._opt_bc_col.configure(values=col_opts)
                        if col_opts:
                            self._opt_bc_col.set(col_opts[0])
                        self._opt_price_col.configure(values=["(لا يوجد / تخطي)"] + col_opts)
                        self._opt_price_col.set("(لا يوجد / تخطي)")
                        break
            wb.close()
        except Exception:
            pass

    def _quick_select_stores(self, mode):
        if mode == "all":
            for v in self._batch_store_vars.values():
                v.set(True)
        elif mode == "none":
            for v in self._batch_store_vars.values():
                v.set(False)
        elif mode == "top5":
            top5 = {'daralamirat', 'care_outlet', 'nazih', 'nahdi', 'sidalih'}
            for k, v in self._batch_store_vars.items():
                v.set(k in top5)
        elif mode == "fast":
            for k, v in self._batch_store_vars.items():
                st = STORES_MAP.get(k, {})
                v.set(st.get('platform') in ['zid', 'shopify'])

    def _start_batch_pricing(self):
        f = self._batch_file_path.get().strip()
        if not f or not os.path.exists(f):
            messagebox.showwarning("تنبيه", "يرجى اختيار ملف الإكسيل المستهدف أولاً.")
            return

        selected_keys = [k for k, v in self._batch_store_vars.items() if v.get()]
        if not selected_keys:
            messagebox.showwarning("تنبيه", "يرجى اختيار متجر منافس واحد على الأقل.")
            return

        bc_sel = self._batch_barcode_col_var.get().strip()
        if not bc_sel or "—" in bc_sel:
            messagebox.showwarning("تنبيه", "يرجى اختيار عمود الباركود.")
            return

        try:
            bc_col_idx = int(bc_sel.split(".")[0]) - 1
        except Exception:
            bc_col_idx = 0

        pr_sel = self._batch_price_col_var.get().strip()
        pr_col_idx = None
        if pr_sel and not pr_sel.startswith("("):
            try:
                pr_col_idx = int(pr_sel.split(".")[0]) - 1
            except Exception:
                pr_col_idx = None

        try:
            workers = int(self._batch_workers_var.get().split()[0])
        except Exception:
            workers = 10

        sheet = self._batch_sheet_var.get().strip()

        # Update UI state
        self._is_batch_running = True
        self._btn_batch_start.configure(state="disabled", text="⏳ جاري التسعير الآلي...")
        self._btn_batch_pause.configure(state="normal", text="⏸️ إيقاف مؤقت")
        self._btn_batch_cancel.configure(state="normal")
        self._btn_batch_open.configure(state="disabled")
        self._batch_progress_bar.set(0)

        def _worker():
            pricer = BatchExcelPricer(
                excel_path=f,
                selected_store_keys=selected_keys,
                barcode_col_idx=bc_col_idx,
                our_price_col_idx=pr_col_idx,
                sheet_name=sheet,
                max_workers=workers
            )
            self._active_pricer = pricer

            def _on_progress(processed, total, bc, stats):
                def _update():
                    pct = processed / total if total > 0 else 0
                    self._batch_progress_bar.set(pct)
                    m, s = divmod(stats['remaining_sec'], 60)
                    self._lbl_batch_stats.configure(
                        text=f"📊 إنجاز: {processed}/{total} ({pct*100:.0f}%) | أسعار: {stats['found']} | نفد: {stats['out_of_stock']} | متبقي: {m:02d}:{s:02d}"
                    )
                    self._lbl_batch_ticker.configure(text=f"🔍 باركود: {bc} ({stats['speed']:.1f} صنف/ثانية)")
                self.after(0, _update)

            def _on_status(txt):
                self.after(0, lambda: self._lbl_batch_stats.configure(text=txt))

            ok, res = pricer.run(progress_callback=_on_progress, status_callback=_on_status)

            def _on_finish():
                self._is_batch_running = False
                self._btn_batch_start.configure(state="normal", text="⚡ بدء تسعير وتحديث ملف الإكسيل الآن")
                self._btn_batch_pause.configure(state="disabled", text="⏸️ إيقاف مؤقت")
                self._btn_batch_cancel.configure(state="disabled")

                if ok:
                    self._batch_output_file = pricer.output_path
                    self._btn_batch_open.configure(state="normal")
                    self._batch_progress_bar.set(1.0)
                    self._lbl_batch_stats.configure(text="✅ اكتملت العملية بنجاح!")
                    self._lbl_batch_ticker.configure(text=f"📁 {os.path.basename(pricer.output_path)}")
                    
                    ask = messagebox.askyesno("اكتمل التسعير بنجاح", f"{res}\n\nهل ترغب في فتح ملف الإكسيل الناتج الآن؟")
                    if ask and os.path.exists(pricer.output_path):
                        os.startfile(pricer.output_path)
                else:
                    messagebox.showerror("خطأ في التسعير", res)

            self.after(0, _on_finish)

        threading.Thread(target=_worker, daemon=True).start()

    def _toggle_batch_pause(self):
        if not self._active_pricer:
            return
        if self._active_pricer.is_paused:
            self._active_pricer.resume()
            self._btn_batch_pause.configure(text="⏸️ إيقاف مؤقت", fg_color="#D97706")
        else:
            self._active_pricer.pause()
            self._btn_batch_pause.configure(text="▶️ استئناف", fg_color=BRAND_GREEN)

    def _cancel_batch_pricing(self):
        if not self._active_pricer:
            return
        if messagebox.askyesno("تأكيد الإيقاف", "هل تريد إيقاف العملية وحفظ ما تم إنجازه في ملف الإكسيل؟"):
            self._active_pricer.cancel()
            self._btn_batch_cancel.configure(state="disabled", text="جاري الحفظ...")

    def _open_batch_output_file(self):
        if self._batch_output_file and os.path.exists(self._batch_output_file):
            os.startfile(self._batch_output_file)

    # ═════════════════════════════════════════════════════════════════════════
    # 🌐 TAB 3: FULL STORE CATALOG SCRAPER IMPLEMENTATION
    # ═════════════════════════════════════════════════════════════════════════
    def _build_catalog_scraper_tab(self, parent):
        self._cat_output_file = None
        self._cat_cancel_event = threading.Event()

        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=16, pady=12)

        # Top Explanation Card
        info_card = ctk.CTkFrame(container, fg_color=BG_CARD, corner_radius=12,
                                 border_width=1, border_color=BORDER_SUBTLE)
        info_card.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            info_card,
            text="🌐  سحب وتصدير كتالوج متجر منافس بالكامل إلى ملف إكسيل",
            font=ctk.CTkFont(APP_FONT, 14, "bold"), text_color=BRAND_GOLD
        ).pack(anchor="e", padx=16, pady=(12, 4))

        ctk.CTkLabel(
            info_card,
            text="تتيح لك هذه الميزة سحب جميع المنتجات والباركودات والأسعار ونسب الخصم وروابط المنتجات المعروضة في أي متجر منافس وتفريغها تلقائياً في ملف Excel منظم بدون الحاجة لملف إكسيل مسبق.",
            font=ctk.CTkFont(APP_FONT, 11), text_color=BRAND_SLATE, wraplength=950, justify="right"
        ).pack(anchor="e", padx=16, pady=(0, 12))

        # Main Configuration Card
        cfg_card = ctk.CTkFrame(container, fg_color=BG_CARD, corner_radius=12,
                                border_width=1, border_color=BORDER_SUBTLE)
        cfg_card.pack(fill="x", pady=(0, 12))

        # Row 1: Select Store
        r1 = ctk.CTkFrame(cfg_card, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(14, 8))

        ctk.CTkLabel(r1, text="اختر المتجر المنافس المراد سحب كتالوجه:",
                     font=ctk.CTkFont(APP_FONT, 12, "bold")).pack(side="right", padx=(10, 0))

        store_options = [f"{s['name']} — ({s['domain']}) [{s['platform'].upper()}]" for s in STORES_REGISTRY]
        self._cat_store_options_map = {f"{s['name']} — ({s['domain']}) [{s['platform'].upper()}]": s['key'] for s in STORES_REGISTRY}

        self._opt_cat_store = ctk.CTkOptionMenu(
            r1, values=store_options, width=380, height=36,
            font=ctk.CTkFont(APP_FONT, 11, "bold"),
            fg_color=("#1E3A8A", "#1E293B")
        )
        self._opt_cat_store.pack(side="right", fill="x", expand=True)
        # Select sidalih by default
        for opt in store_options:
            if "صيدلية.كوم" in opt:
                self._opt_cat_store.set(opt)
                break

        # Row 2: Date Filter (Newest Products by Days)
        r2 = ctk.CTkFrame(cfg_card, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=(0, 10))

        self._chk_cat_days_var = ctk.BooleanVar(value=True)
        self._chk_cat_days = ctk.CTkCheckBox(
            r2, text="⏱️  استخراج أحدث الأصناف المضافة فقط خلال فترة محددة",
            variable=self._chk_cat_days_var,
            font=ctk.CTkFont(APP_FONT, 12, "bold"),
            text_color=BRAND_GOLD,
            command=self._on_cat_days_toggle
        )
        self._chk_cat_days.pack(side="right", padx=(0, 12))

        self._days_input_frame = ctk.CTkFrame(r2, fg_color="transparent")
        self._days_input_frame.pack(side="right")

        ctk.CTkLabel(self._days_input_frame, text="خلال آخر:", font=ctk.CTkFont(APP_FONT, 11, "bold")).pack(side="right", padx=(0, 4))

        self._ent_cat_days = ctk.CTkEntry(
            self._days_input_frame, width=50, height=32,
            font=ctk.CTkFont(APP_FONT, 12, "bold"), justify="center"
        )
        self._ent_cat_days.insert(0, "7")
        self._ent_cat_days.pack(side="right", padx=4)
        self._ent_cat_days.bind("<KeyRelease>", lambda e: self._update_cat_button_text())

        ctk.CTkLabel(self._days_input_frame, text="يوم", font=ctk.CTkFont(APP_FONT, 11, "bold")).pack(side="right", padx=(0, 8))

        # Quick preset buttons (3, 7, 14, 30)
        for d in [3, 7, 14, 30]:
            btn = ctk.CTkButton(
                self._days_input_frame, text=f"{d} يوم", width=46, height=26,
                font=ctk.CTkFont(APP_FONT, 10, "bold"), fg_color=("#E2E8F0", "#334155"),
                text_color=("#1E293B", "#F8FAFC"), hover_color=("#CBD5E1", "#475569"),
                command=lambda val=d: self._set_cat_days(val)
            )
            btn.pack(side="right", padx=2)

        # Row 3: Limit
        r3 = ctk.CTkFrame(cfg_card, fg_color="transparent")
        r3.pack(fill="x", padx=16, pady=(0, 14))

        ctk.CTkLabel(r3, text="الحد الأقصى لعدد المنتجات المراد سحبها:",
                     font=ctk.CTkFont(APP_FONT, 12, "bold")).pack(side="right", padx=(10, 0))

        self._opt_cat_limit = ctk.CTkOptionMenu(
            r3,
            values=[
                "سحب كل الأصناف المتاحة في الفترة",
                "100 منتج (تجربة سريعة)",
                "250 منتج",
                "500 منتج (الموصى به)",
                "1,000 منتج",
                "2,500 منتج",
                "5,000 منتج (كتالوج كبير)"
            ],
            width=300, height=32
        )
        self._opt_cat_limit.set("سحب كل الأصناف المتاحة في الفترة")
        self._opt_cat_limit.pack(side="right")

        # Action & Progress Card
        card_cat_act = ctk.CTkFrame(container, fg_color=BG_CARD, corner_radius=12,
                                    border_width=1, border_color=BORDER_SUBTLE)
        card_cat_act.pack(fill="x", pady=(0, 10))

        btn_row = ctk.CTkFrame(card_cat_act, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(12, 8))

        self._btn_cat_start = ctk.CTkButton(
            btn_row, text="⏱️  سحب أحدث المنتجات المضافة (آخر 7 أيام) إلى Excel",
            font=ctk.CTkFont(APP_FONT, 12, "bold"),
            fg_color=BRAND_GREEN, hover_color=BRAND_GREEN_HOVER,
            height=38, width=340, command=self._start_catalog_scraper
        )
        self._btn_cat_start.pack(side="right", padx=(8, 0))

        self._btn_cat_cancel = ctk.CTkButton(
            btn_row, text="⏹️  إيقاف وحفظ ما تم",
            font=ctk.CTkFont(APP_FONT, 11, "bold"),
            fg_color=BRAND_RED, hover_color=BRAND_RED_HOVER,
            height=38, width=130, state="disabled",
            command=self._cancel_catalog_scraper
        )
        self._btn_cat_cancel.pack(side="right", padx=4)

        self._btn_cat_open = ctk.CTkButton(
            btn_row, text="📂  فتح ملف الكتالوج (Excel)",
            font=ctk.CTkFont(APP_FONT, 11, "bold"),
            fg_color=BRAND_BLUE, hover_color=BRAND_BLUE_HOVER,
            height=38, width=190, state="disabled",
            command=self._open_cat_output_file
        )
        self._btn_cat_open.pack(side="left")

        # Progress bar
        self._cat_progress_bar = ctk.CTkProgressBar(card_cat_act, height=10, corner_radius=5)
        self._cat_progress_bar.pack(fill="x", padx=16, pady=(0, 6))
        self._cat_progress_bar.set(0)

        self._lbl_cat_status = ctk.CTkLabel(
            card_cat_act, text="جاهز لسحب وتصدير أحدث منتجات المتجر...",
            font=ctk.CTkFont(APP_FONT, 11, "bold")
        )
        self._lbl_cat_status.pack(anchor="e", padx=16, pady=(0, 10))

    def _set_cat_days(self, val):
        self._ent_cat_days.delete(0, "end")
        self._ent_cat_days.insert(0, str(val))
        self._update_cat_button_text()

    def _on_cat_days_toggle(self):
        is_active = self._chk_cat_days_var.get()
        state = "normal" if is_active else "disabled"
        self._ent_cat_days.configure(state=state)
        self._update_cat_button_text()

    def _update_cat_button_text(self):
        if hasattr(self, '_chk_cat_days_var') and self._chk_cat_days_var.get():
            days_txt = self._ent_cat_days.get().strip() or "7"
            self._btn_cat_start.configure(text=f"⏱️  سحب أحدث المنتجات المضافة (آخر {days_txt} أيام) إلى Excel")
        else:
            self._btn_cat_start.configure(text="🌐  بدء سحب الكتالوج وتصديره إلى Excel الآن")

    def _start_catalog_scraper(self):
        sel_txt = self._opt_cat_store.get()
        store_key = self._cat_store_options_map.get(sel_txt)
        if not store_key:
            messagebox.showwarning("تنبيه", "يرجى اختيار المتجر المنافس.")
            return

        days_limit = None
        if self._chk_cat_days_var.get():
            raw_days = self._ent_cat_days.get().strip()
            if not raw_days.isdigit() or int(raw_days) <= 0:
                messagebox.showwarning("تنبيه", "يرجى إدخال عدد أيام صحيح (مثلاً 7 أو 14 يوماً).", parent=self)
                return
            days_limit = int(raw_days)

        lim_txt = self._opt_cat_limit.get()
        if "100" in lim_txt:
            target_count = 100
        elif "250" in lim_txt:
            target_count = 250
        elif "500" in lim_txt:
            target_count = 500
        elif "1,000" in lim_txt or "1000" in lim_txt:
            target_count = 1000
        elif "2,500" in lim_txt or "2500" in lim_txt:
            target_count = 2500
        elif "5,000" in lim_txt or "5000" in lim_txt:
            target_count = 5000
        else:
            target_count = 50000

        self._cat_cancel_event.clear()
        self._btn_cat_start.configure(state="disabled", text="⏳ جاري فحص وسحب المنتجات...")
        self._btn_cat_cancel.configure(state="normal")
        self._btn_cat_open.configure(state="disabled")
        self._cat_progress_bar.set(0)
        self._lbl_cat_status.configure(text="جاري الاتصال بالمتجر وفحص المنتجات الحديثة...")

        def _worker():
            def _prog(count, total, item_name, speed):
                def _upd():
                    pct = min(1.0, count / max(1, total))
                    self._cat_progress_bar.set(pct)
                    name_display = (item_name[:35] + "...") if len(item_name) > 35 else item_name
                    self._lbl_cat_status.configure(
                        text=f"📦 جاري السحب: {count} من {total} ({pct*100:.0f}%) | آخر صنف: {name_display} | السرعة: {speed:.1f} صنف/ث"
                    )
                self.after(0, _upd)

            ok, res, out_file = scrape_store_catalog_to_excel(
                store_key=store_key,
                target_count=target_count,
                days_limit=days_limit,
                progress_callback=_prog,
                cancel_event=self._cat_cancel_event
            )

            def _done():
                self._update_cat_button_text()
                self._btn_cat_cancel.configure(state="disabled")

                if ok and out_file:
                    self._cat_output_file = out_file
                    self._cat_progress_bar.set(1.0)
                    self._btn_cat_open.configure(state="normal")
                    self._lbl_cat_status.configure(text=f"✅ اكتمل سحب الكتالوج وحفظه في الإكسيل بنجاح!")

                    try:
                        self.bell()
                    except Exception:
                        pass

                    # Prominent completion popup with parent=self to stay on top
                    messagebox.showinfo("🎉 تم اكتمال سحب الكتالوج بنجاح", res, parent=self)

                    ask = messagebox.askyesno("فتح ملف الكتالوج", "هل ترغب في فتح ملف الكتالوج في Excel الآن؟", parent=self)
                    if ask and self._cat_output_file and os.path.exists(self._cat_output_file):
                        try:
                            os.startfile(self._cat_output_file)
                        except Exception as e:
                            messagebox.showerror("خطأ", f"تعذر فتح الملف:\n{e}", parent=self)
                else:
                    self._lbl_cat_status.configure(text="⚠️ توقفت العملية أو تعذر استخراج المنتجات.")
                    messagebox.showerror("تنبيه استخراج الكتالوج", res, parent=self)

            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    def _cancel_catalog_scraper(self):
        self._cat_cancel_event.set()
        self._btn_cat_cancel.configure(state="disabled", text="جاري الإيقاف...")

    def _open_cat_output_file(self):
        if self._cat_output_file and os.path.exists(self._cat_output_file):
            try:
                os.startfile(self._cat_output_file)
            except Exception as e:
                messagebox.showerror("خطأ", f"تعذر فتح الملف:\n{e}", parent=self)
        else:
            messagebox.showinfo("تنبيه", "لم يتم إنشاء أو تحديد ملف الكتالوج بعد.", parent=self)


# ─────────────────────────────────────────────────────────────────────────────
# 🚀 Entrypoint
# ─────────────────────────────────────────────────────────────────────────────
def main():
    app = PriceComparatorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
