import os
import sys
import threading
import queue
import json
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Dict, Any, Optional, List
import customtkinter as ctk

# Ensure parent path is in sys.path for auto_updater and security
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    import auto_updater
except Exception:
    auto_updater = None

# Ensure cryptography and security are recognized by PyInstaller
import cryptography
import security
from import_engine import ImportEngine
from rules_dialog import RulesEditorDialog, update_entry_direction, DEFAULT_ODOO_CATEGORIES

# Set appearance and theme
ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

DEFAULT_TAG_OPTIONS = [
    "SG0040-OTHER PRODUCTS",
    "SG0010-AL ASSALI PRODUCTS",
    "SG0020-SPCI PRODUCTS",
    "SG0030-MAHMOOD SAEED PRODUCTS",
    "SG0060-AL MUTAMAIZA PRODUCTS"
]


class OdooImportApp(ctk.CTk):
    """
    Luxury GUI for preparing, validating, and generating Odoo 17
    product import files and duplicate comparison reports.
    """

    def __init__(self):
        super().__init__()

        self.title("مُجهّز ومُدقّق استيراد أصناف أودو 17 — Al-Assali OdooImport")
        self.geometry("960x840")
        self.minsize(860, 720)

        # Paths
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))

        self.default_supp_path = os.path.join(self.base_dir, "suppItems.xlsx")
        self.default_all_new_path = os.path.join(self.base_dir, "AllNewItems.xlsx")
        self.output_import_path = os.path.join(self.base_dir, "Odooimport.xlsx")

        self.engine = ImportEngine()
        self.last_result = None
        self.current_vendor_info: Optional[Dict[str, Any]] = None
        self.msg_queue = queue.Queue()

        self.init_ui()
        # Start queue poller
        self.after(50, self._check_queue)
        # Check Odoo connection in background
        threading.Thread(target=self._check_initial_connection, daemon=True).start()
        if os.path.exists(self.default_supp_path):
            self.after(600, lambda: self._auto_detect_vendor(self.default_supp_path))

        # Check for auto updates
        if auto_updater:
            auto_updater.check_and_prompt_update_async(self, "OdooItemImporter", "1.00")

    def _check_queue(self):
        try:
            while True:
                item = self.msg_queue.get_nowait()
                msg_type = item[0]
                if msg_type == 'progress':
                    self._on_progress(item[1], item[2])
                elif msg_type == 'completed':
                    self._on_completed(item[1])
                elif msg_type == 'error':
                    self._on_error(item[1])
        except queue.Empty:
            pass
        finally:
            self.after(50, self._check_queue)

    def get_odoo_categories_list(self) -> List[str]:
        try:
            if self.engine.verifier and self.engine.verifier.uid:
                cats = self.engine.verifier.get_category_names_list()
                if cats:
                    return cats
        except Exception:
            pass
        cfg_cats = list(self.engine.config.get("category_prefix_rules", {}).keys())
        if cfg_cats:
            return sorted(cfg_cats)
        return list(DEFAULT_ODOO_CATEGORIES)

    def _check_initial_connection(self):
        ok = self.engine.verifier.authenticate()
        if ok:
            db_name = getattr(self.engine.verifier, 'db', '')
            self.after(0, lambda: self.lbl_conn_status.configure(
                text=f"🟢 متصل بقاعدة أودو 17 بنجاح ({db_name})",
                text_color="#86EFAC"
            ))
            # Refresh category dropdown with live Odoo categories
            try:
                cats = self.get_odoo_categories_list()
                if hasattr(self, 'combo_default_category') and cats:
                    self.after(0, lambda: self.combo_default_category.configure(values=cats))
            except Exception as e:
                print(f"[GUI] Error updating categories on connect: {e}")
        else:
            err = self.engine.verifier.last_error or "تعذر الاتصال"
            self.after(0, lambda: self.lbl_conn_status.configure(
                text=f"🔴 تعذر الاتصال بأودو 17 ({err})",
                text_color="#FCA5A5"
            ))

    def init_ui(self):
        # 1. Header Frame
        header_frame = ctk.CTkFrame(self, fg_color="#1E6EBA", corner_radius=0, height=105)
        header_frame.pack(fill="x", side="top")
        header_frame.pack_propagate(False)

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="🏛️ مُجهّز ومُدقّق استيراد أصناف أودو 17 (OdooImport)",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color="#FFFFFF"
        )
        title_lbl.pack(pady=(10, 2))

        sub_lbl = ctk.CTkLabel(
            header_frame,
            text="شركة العسلي للتجارة — فحص الباركودات • احتساب الأسعار • الترقيم الآلي • صفحة المقارنة للأصناف المكررة",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#E2E8F0"
        )
        sub_lbl.pack(pady=(0, 4))

        self.lbl_conn_status = ctk.CTkLabel(
            header_frame,
            text="⏳ جاري التحقق من الاتصال بأودو 17...",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FEF08A"
        )
        self.lbl_conn_status.pack(pady=(0, 6))

        # Main Scrollable Container
        main_scroll = ctk.CTkScrollableFrame(self, fg_color="#F8FAFC")
        main_scroll.pack(fill="both", expand=True, padx=20, pady=16)

        # 2. File Selection Card
        card_file = ctk.CTkFrame(main_scroll, fg_color="#FFFFFF", corner_radius=12, border_width=1, border_color="#E2E8F0")
        card_file.pack(fill="x", pady=(0, 14), padx=4)

        card_file_header = ctk.CTkLabel(
            card_file,
            text="📁 اختيار ملف المورد (Vendor Items File)",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color="#1E293B"
        )
        card_file_header.pack(anchor="e", padx=16, pady=(12, 8))

        file_row = ctk.CTkFrame(card_file, fg_color="transparent")
        file_row.pack(fill="x", padx=16, pady=(0, 14))

        self.btn_browse = ctk.CTkButton(
            file_row,
            text="استعراض 📂",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#1E6EBA",
            hover_color="#1558A0",
            width=110,
            height=38,
            command=self.browse_file
        )
        self.btn_browse.pack(side="left", padx=(0, 8))

        self.entry_file_path = ctk.CTkEntry(
            file_row,
            font=ctk.CTkFont(family="Consolas", size=12),
            height=38,
            justify="left"
        )
        self.entry_file_path.pack(side="right", fill="x", expand=True)
        if os.path.exists(self.default_supp_path):
            self.entry_file_path.insert(0, self.default_supp_path)

        # 2.5 Vendor / Partner Card
        card_vendor = ctk.CTkFrame(main_scroll, fg_color="#FFFFFF", corner_radius=12, border_width=1, border_color="#E2E8F0")
        card_vendor.pack(fill="x", pady=(0, 14), padx=4)

        card_vendor_header = ctk.CTkLabel(
            card_vendor,
            text="🏢 بيانات المورد / الشريك (Vendor / Partner Tag)",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color="#1E293B"
        )
        card_vendor_header.pack(anchor="e", padx=16, pady=(12, 4))

        vendor_sub = ctk.CTkLabel(
            card_vendor,
            text="التقاط رقم المورد تلقائياً من اسم الملف أو الترويسة، والبحث عنه في أودو لاعتماد اسمه الرسمي كوسم (Tag).",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#64748B"
        )
        vendor_sub.pack(anchor="e", padx=16, pady=(0, 8))

        vendor_row = ctk.CTkFrame(card_vendor, fg_color="transparent")
        vendor_row.pack(fill="x", padx=16, pady=(0, 6))

        self.btn_search_vendor = ctk.CTkButton(
            vendor_row,
            text="بحث بأودو 🔍",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#0F766E",
            hover_color="#115E59",
            width=110,
            height=36,
            command=self.search_vendor_manually
        )
        self.btn_search_vendor.pack(side="left", padx=(0, 8))

        self.entry_vendor = ctk.CTkEntry(
            vendor_row,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            placeholder_text="رقم المورد أو اسمه (مثال: 905-315 أو AlArkan)...",
            height=36
        )
        self.entry_vendor.pack(side="right", fill="x", expand=True)
        self.entry_vendor.bind("<Return>", lambda e: self.search_vendor_manually())
        self.entry_vendor.bind("<KeyRelease>", lambda e: update_entry_direction(self.entry_vendor))

        # Vendor verification badge
        self.lbl_vendor_badge = ctk.CTkLabel(
            card_vendor,
            text="⚪ لم يتم فحص المورد بعد (اختر ملف أو اكتب رقم المورد واضغط بحث)",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#475569"
        )
        self.lbl_vendor_badge.pack(anchor="e", padx=16, pady=(0, 12))

        # 3. Parameters Card (Margin, Tag & Category Settings)
        card_params = ctk.CTkFrame(main_scroll, fg_color="#FFFFFF", corner_radius=12, border_width=1, border_color="#E2E8F0")
        card_params.pack(fill="x", pady=(0, 14), padx=4)

        param_title = ctk.CTkLabel(
            card_params,
            text="⚙️ معاملات التسعير والترقيم والتصنيف",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color="#1E293B"
        )
        param_title.pack(anchor="e", padx=16, pady=(12, 6))

        # Row 1: Pricing & Margin & Tax Note
        row_pricing = ctk.CTkFrame(card_params, fg_color="#F8FAFC", corner_radius=8)
        row_pricing.pack(fill="x", padx=16, pady=(0, 8))

        btn_rules = ctk.CTkButton(
            row_pricing,
            text="قواعد الترقيم والتصنيفات 📋",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#475569",
            hover_color="#334155",
            height=34,
            command=self.open_rules_dialog
        )
        btn_rules.pack(side="left", padx=10, pady=8)

        lbl_tax_note = ctk.CTkLabel(
            row_pricing,
            text="• الضريبة: 15% ZATCA  • التقريب: ربع ريال  • قاعدة الهللة: .99 للأعداد الصحيحة",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#64748B"
        )
        lbl_tax_note.pack(side="left", padx=10, pady=8)

        self.entry_margin = ctk.CTkEntry(
            row_pricing,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            width=70,
            height=34,
            justify="center"
        )
        self.entry_margin.insert(0, "20")
        self.entry_margin.pack(side="right", padx=(4, 10), pady=8)

        lbl_margin = ctk.CTkLabel(
            row_pricing,
            text="نسبة هامش الربح (%):",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#334155"
        )
        lbl_margin.pack(side="right", padx=(0, 4), pady=8)

        # Row 2: Tag Selection & Suffix Digit Indicator
        row_tag = ctk.CTkFrame(card_params, fg_color="transparent")
        row_tag.pack(fill="x", padx=16, pady=(0, 8))

        self.lbl_tag_suffix_hint = ctk.CTkLabel(
            row_tag,
            text="🔢 الرقم بعد الشرطة: 8",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#1E6EBA",
            fg_color="#EFF6FF",
            corner_radius=6,
            width=175,
            height=34
        )
        self.lbl_tag_suffix_hint.pack(side="left", padx=(0, 8))

        self.combo_product_tag = ctk.CTkComboBox(
            row_tag,
            values=DEFAULT_TAG_OPTIONS,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            width=320,
            height=34,
            command=self._on_tag_change
        )
        default_tag_val = self.engine.config.get("settings", {}).get("default_tag", "SG0040-OTHER PRODUCTS")
        self.combo_product_tag.set(default_tag_val)
        self.combo_product_tag.pack(side="right", fill="x", expand=True, padx=(8, 0))

        lbl_tag = ctk.CTkLabel(
            row_tag,
            text="الوسم الرئيسي (Product Tag):",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#334155"
        )
        lbl_tag.pack(side="right", padx=(0, 8))

        # Initial tag badge update
        self._on_tag_change(default_tag_val)

        # Row 3: Category Dropdown (Odoo Categories)
        row_cat = ctk.CTkFrame(card_params, fg_color="transparent")
        row_cat.pack(fill="x", padx=16, pady=(0, 12))

        lbl_cat_hint = ctk.CTkLabel(
            row_cat,
            text="(يُطبق تلقائياً في حال عدم وجود تصنيف بملف المورد)",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#64748B"
        )
        lbl_cat_hint.pack(side="left", padx=(0, 8))

        all_cats = self.get_odoo_categories_list()
        self.combo_default_category = ctk.CTkComboBox(
            row_cat,
            values=all_cats,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            width=320,
            height=34
        )
        default_cat_val = self.engine.config.get("settings", {}).get("default_category", "SCP-Skin Care Products")
        self.combo_default_category.set(default_cat_val)
        self.combo_default_category.pack(side="right", fill="x", expand=True, padx=(8, 0))

        lbl_cat = ctk.CTkLabel(
            row_cat,
            text="التصنيف الافتراضي (Category):",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#334155"
        )
        lbl_cat.pack(side="right", padx=(0, 8))

        # 4. Action Buttons Card
        card_actions = ctk.CTkFrame(main_scroll, fg_color="#FFFFFF", corner_radius=12, border_width=1, border_color="#E2E8F0")
        card_actions.pack(fill="x", pady=(0, 14), padx=4)

        act_title = ctk.CTkLabel(
            card_actions,
            text="🚀 تنفيذ المعالجة والتحقق",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color="#1E293B"
        )
        act_title.pack(anchor="e", padx=16, pady=(12, 6))

        btn_row = ctk.CTkFrame(card_actions, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(4, 12))

        self.btn_process = ctk.CTkButton(
            btn_row,
            text="⚡ فحص وتجهيز ملف أودو (Odooimport.xlsx)",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            fg_color="#1E6EBA",
            hover_color="#1558A0",
            height=46,
            command=self.start_processing
        )
        self.btn_process.pack(side="right", fill="x", expand=True, padx=(8, 0))

        self.btn_open_file = ctk.CTkButton(
            btn_row,
            text="📂 فتح ملف Odooimport.xlsx",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#0F766E",
            hover_color="#115E59",
            height=46,
            state="disabled",
            command=self.open_import_file
        )
        self.btn_open_file.pack(side="left", padx=(0, 8))

        self.btn_archive = ctk.CTkButton(
            card_actions,
            text="📥 اعتماد وأرشفة الأصناف السليمة في AllNewItems.xlsx",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            height=40,
            state="disabled",
            command=self.archive_items
        )
        self.btn_archive.pack(fill="x", padx=16, pady=(0, 14))

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(card_actions, height=8, fg_color="#E2E8F0", progress_color="#1E6EBA")
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 4))

        self.lbl_status = ctk.CTkLabel(
            card_actions,
            text="جاهز لبدء الفحص والتجهيز...",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#64748B"
        )
        self.lbl_status.pack(anchor="center", pady=(0, 10))

        # 5. Results & Statistics Dashboard Card
        self.card_stats = ctk.CTkFrame(main_scroll, fg_color="#FFFFFF", corner_radius=12, border_width=1, border_color="#E2E8F0")
        self.card_stats.pack(fill="x", pady=(0, 14), padx=4)

        stats_title = ctk.CTkLabel(
            self.card_stats,
            text="📊 لوحة نتائج الفحص والمقارنة",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color="#1E293B"
        )
        stats_title.pack(anchor="e", padx=16, pady=(12, 8))

        tiles_row = ctk.CTkFrame(self.card_stats, fg_color="transparent")
        tiles_row.pack(fill="x", padx=16, pady=(0, 14))

        # 4 Summary Tiles
        self.tile_total = self.create_tile(tiles_row, "إجمالي الأصناف", "0", "#1E6EBA", 0)
        self.tile_valid = self.create_tile(tiles_row, "أصناف جديدة جاهزة", "0", "#059669", 1)
        self.tile_dup = self.create_tile(tiles_row, "أصناف مكررة بأودو", "0", "#D97706", 2)
        self.tile_errors = self.create_tile(tiles_row, "أصناف بها أخطاء", "0", "#DC2626", 3)

        # Log Text Box
        self.txt_log = ctk.CTkTextbox(
            self.card_stats,
            height=140,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#0F172A",
            text_color="#E2E8F0"
        )
        self.txt_log.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        self.log_message("مرحباً بك في أداة تجهيز استيراد أودو 17. اختر ملف المورد واضغط 'فحص وتجهيز'.")

        # 6. Footer Credits
        footer_lbl = ctk.CTkLabel(
            self,
            text="تصميم وتطوير: م. عبدالله الخطيب — شركة العسلي للتجارة • إصدار 2026",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8"
        )
        footer_lbl.pack(side="bottom", pady=6)

    def _on_tag_change(self, choice: str):
        tag_upper = str(choice).upper()
        if "40" in tag_upper:
            digit = "8"
        elif "10" in tag_upper or "60" in tag_upper:
            digit = "4"
        elif "20" in tag_upper or "30" in tag_upper:
            digit = "3"
        else:
            digit = "4"
        self.lbl_tag_suffix_hint.configure(text=f"🔢 الرقم بعد الشرطة: {digit}")

    def create_tile(self, parent, title: str, val: str, color: str, col: int):
        f = ctk.CTkFrame(parent, fg_color="#F8FAFC", corner_radius=10, border_width=1, border_color="#E2E8F0")
        f.grid(row=0, column=col, sticky="nsew", padx=4, pady=2)
        parent.grid_columnconfigure(col, weight=1)

        t_lbl = ctk.CTkLabel(f, text=title, font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#64748B")
        t_lbl.pack(pady=(8, 2))

        v_lbl = ctk.CTkLabel(f, text=val, font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"), text_color=color)
        v_lbl.pack(pady=(0, 8))
        return v_lbl

    def log_message(self, msg: str):
        self.txt_log.insert("end", msg + "\n")
        self.txt_log.see("end")

    def browse_file(self):
        f = filedialog.askopenfilename(
            title="اختر ملف المورد",
            filetypes=[("Excel Files", "*.xlsx *.xls"), ("All Files", "*.*")]
        )
        if f:
            self.entry_file_path.delete(0, "end")
            self.entry_file_path.insert(0, f)
            out_dir = os.path.dirname(os.path.abspath(f))
            self.output_import_path = os.path.join(out_dir, "Odooimport.xlsx")
            self._auto_detect_vendor(f)

    def _auto_detect_vendor(self, file_path: str):
        def worker():
            try:
                from import_engine import extract_vendor_hint
                hint = extract_vendor_hint(file_path)
                query = hint.get('code') or hint.get('name') or ""
                if query:
                    self.after(0, lambda: self._set_vendor_entry(query))
                    self._resolve_and_display_vendor(query)
            except Exception as e:
                print(f"[GUI] Auto detect vendor error: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def _set_vendor_entry(self, text: str):
        self.entry_vendor.delete(0, "end")
        self.entry_vendor.insert(0, text)
        update_entry_direction(self.entry_vendor, text)

    def search_vendor_manually(self):
        query = self.entry_vendor.get().strip()
        if not query:
            self.lbl_vendor_badge.configure(
                text="⚠️ يرجى كتابة كود المورد أو اسمه للبحث",
                text_color="#DC2626"
            )
            return

        self.lbl_vendor_badge.configure(
            text="⏳ جاري البحث في أودو...",
            text_color="#2563EB"
        )
        threading.Thread(target=lambda: self._resolve_and_display_vendor(query), daemon=True).start()

    def _resolve_and_display_vendor(self, query: str):
        res = self.engine.verifier.resolve_vendor(query)
        self.current_vendor_info = res
        tag_name = res.get('tag_name') or query
        is_tag = res.get('is_tag_in_odoo', False)

        if res.get('success'):
            if is_tag:
                text = f"🟢 معرّف كـ Tag في أودو: {tag_name}"
                color = "#15803D"
            else:
                text = f"🟡 مسجل كشريك في أودو: {tag_name} (غير معرّف كـ Tag - سيُدرج بورقة التاجات)"
                color = "#B45309"
        else:
            text = f"⚪ مورد محلي: {tag_name} (غير مسجل بأودو - سيُدرج بورقة التاجات)"
            color = "#475569"

        self.after(0, lambda: self.lbl_vendor_badge.configure(text=text, text_color=color))

    def start_processing(self):
        file_path = self.entry_file_path.get().strip()
        if not file_path or not os.path.exists(file_path):
            messagebox.showerror("خطأ", "يرجى تحديد ملف المورد بصيغة Excel بشكل صحيح.", parent=self)
            return

        try:
            margin_val = float(self.entry_margin.get().strip()) / 100.0
        except ValueError:
            messagebox.showerror("خطأ", "نسبة هامش الربح غير صحيحة، يرجى كتابة رقم مثل 20.", parent=self)
            return

        out_dir = os.path.dirname(os.path.abspath(file_path))
        self.output_import_path = os.path.join(out_dir, "Odooimport.xlsx")

        vendor_q = self.entry_vendor.get().strip()
        if vendor_q and (not self.current_vendor_info or self.current_vendor_info.get('supplier_no') != vendor_q):
            self.current_vendor_info = self.engine.verifier.resolve_vendor(vendor_q)

        # Check Odoo connection before starting
        if not self.engine.verifier.authenticate():
            err = self.engine.verifier.last_error or "تعذر الاتصال بسيرفر أودو 17"
            proceed = messagebox.askyesno(
                "تنبيه - أودو غير متصل",
                f"تعذر الاتصال بسيرفر أودو 17:\n{err}\n\nفي حال المتابعة، لن يتمكن البرنامج من التحقق من الباركودات المسجلة أو مطابقة التصنيفات مع قاعدة أودو.\n\nهل تريد المتابعة بدون فحص أودو؟",
                parent=self
            )
            if not proceed:
                return

        selected_tag = self.combo_product_tag.get().strip() if hasattr(self, 'combo_product_tag') else None
        selected_cat = self.combo_default_category.get().strip() if hasattr(self, 'combo_default_category') else None

        self.btn_process.configure(state="disabled")
        self.btn_open_file.configure(state="disabled")
        self.btn_archive.configure(state="disabled")
        self.txt_log.delete("1.0", "end")

        thread = threading.Thread(
            target=self._process_worker,
            args=(file_path, margin_val, self.output_import_path, self.current_vendor_info, selected_tag, selected_cat),
            daemon=True
        )
        thread.start()

    def _process_worker(
        self,
        file_path: str,
        margin_val: float,
        output_path: str,
        vendor_info: Optional[Dict[str, Any]] = None,
        tag_val: Optional[str] = None,
        category_val: Optional[str] = None
    ):
        def notify(pct, msg):
            self.msg_queue.put(('progress', pct, msg))

        try:
            res = self.engine.process_file(
                supp_items_path=file_path,
                output_import_path=output_path,
                margin_override=margin_val,
                vendor_override=vendor_info,
                tag_override=tag_val,
                category_override=category_val,
                progress_cb=notify
            )
            self.msg_queue.put(('completed', res))
        except Exception as e:
            self.msg_queue.put(('error', str(e)))

    def _on_progress(self, pct: float, msg: str):
        self.progress_bar.set(pct / 100.0)
        self.lbl_status.configure(text=msg)
        self.log_message(f"[{int(pct)}%] {msg}")

    def _on_completed(self, res: Dict[str, Any]):
        self.last_result = res
        self.btn_process.configure(state="normal")
        self.btn_open_file.configure(state="normal")

        actual_output = res.get('output_file', self.output_import_path)
        self.output_import_path = actual_output
        save_warn = res.get('save_warning', '')

        total = res.get('total_items', 0)
        errs = res.get('total_errors', 0)
        comparison_count = res.get('duplicate_count', 0)
        total_dups = res.get('total_duplicates', comparison_count)
        new_valid = max(0, total - total_dups - errs)

        self.tile_total.configure(text=str(total))
        self.tile_valid.configure(text=str(new_valid))
        self.tile_dup.configure(text=str(total_dups))
        self.tile_errors.configure(text=str(errs))

        self.log_message("\n" + "=" * 55)
        self.log_message(f"🎉 اكتملت المعالجة وتجهيز ملف {os.path.basename(self.output_import_path)} بنجاح!")
        if save_warn:
            self.log_message(f"⚠️ تنبيه: {save_warn}")
        self.log_message(f"• المورد: {res.get('supplier_no')} - {res.get('supplier_name')}")
        self.log_message(f"• إجمالي الأصناف: {total}")
        self.log_message(f"• الأصناف الجديدة الجاهزة للرفع: {new_valid}")
        self.log_message(f"• أصناف مسجلة مسبقاً بأودو: {total_dups} (المدرجة في ورقة المقارنة: {comparison_count})")
        self.log_message(f"• أصناف تحتوي على أخطاء تتطلب مراجعة: {errs}")

        missing_tags_count = res.get('missing_tags_count', 0)
        missing_tags = res.get('missing_tags', [])
        if missing_tags_count > 0:
            self.log_message(f"🏷️ تنبيه تاجات: يوجد {missing_tags_count} وسم غير معرّف في أودو ({', '.join(missing_tags[:5])}) - تم إنشاء ورقة 'التاجات الواجب تعريفها' لتعريفها قبل الرفع.")

        if errs == 0:
            self.btn_archive.configure(state="normal")
            self.log_message("✅ الملف سليم 100% وخالٍ من الأخطاء! يمكنك الآن الاعتماد والأرشفة.")
        else:
            self.btn_archive.configure(state="disabled")
            self.log_message("⚠️ توجد خلايا مظللة بالأحمر الفاتح في ملف الإكسل. يرجى فتح الملف وتصحيحها قبل الأرشفة.")

        msg_body = (
            f"تم تجهيز ملف أودو بنجاح!\n\n"
            f"• الإجمالي: {total}\n"
            f"• أصناف جديدة: {new_valid}\n"
            f"• أصناف مسجلة بأودو: {total_dups} (أصناف بها ملاحظات/فروقات: {comparison_count})\n"
            f"• أصناف بها أخطاء: {errs}\n"
        )
        if missing_tags_count > 0:
            msg_body += f"• 🏷️ تاجات مطلوب تعريفها بأودو: {missing_tags_count} (انظر ورقة 'التاجات الواجب تعريفها')\n"
        msg_body += f"\nتم حفظ الملف في:\n{self.output_import_path}"
        if save_warn:
            msg_body += f"\n\n⚠️ {save_warn}"

        messagebox.showinfo("اكتمل التجهيز", msg_body, parent=self)

    def _on_error(self, err_msg: str):
        self.btn_process.configure(state="normal")
        self.progress_bar.set(0)
        self.lbl_status.configure(text="❌ حدث خطأ أثناء المعالجة")
        self.log_message(f"❌ خطأ: {err_msg}")
        messagebox.showerror("خطأ", f"حدث خطأ أثناء فحص وتجهيز الملف:\n{err_msg}", parent=self)

    def open_import_file(self):
        if os.path.exists(self.output_import_path):
            try:
                os.startfile(self.output_import_path)
            except Exception as e:
                subprocess.Popen(["explorer", self.output_import_path])
        else:
            messagebox.showwarning("تنبيه", "الملف غير موجود بعد.", parent=self)

    def archive_items(self):
        if not self.last_result:
            return

        supp_path = self.entry_file_path.get().strip()
        all_new_path = self.default_all_new_path

        if not os.path.exists(all_new_path):
            messagebox.showerror("خطأ", f"ملف الأرشيف AllNewItems.xlsx غير موجود في:\n{all_new_path}", parent=self)
            return

        confirm = messagebox.askyesno(
            "تأكيد الأرشفة",
            "هل أنت متأكد من رغبتك في إلحاق هذه الأصناف بملف الأرشيف AllNewItems.xlsx؟",
            parent=self
        )
        if not confirm:
            return

        selected_cat = self.combo_default_category.get().strip() if hasattr(self, 'combo_default_category') else None

        try:
            count = self.engine.append_to_all_new_items(
                supp_path,
                all_new_path,
                vendor_override=self.current_vendor_info,
                category_override=selected_cat
            )
            self.log_message(f"✅ تمت أرشفة {count} صنف بنجاح في ملف AllNewItems.xlsx")
            messagebox.showinfo("تمت الأرشفة", f"تم إلحاق {count} صنف بنجاح في ملف:\n{all_new_path}", parent=self)
        except Exception as e:
            messagebox.showerror("خطأ الأرشفة", f"تعذر إلحاق الأصناف بملف الأرشيف:\n{e}", parent=self)

    def open_rules_dialog(self):
        def on_config_updated(new_cfg):
            self.engine.config = new_cfg
            self.log_message("📋 تم تحديث وتطبيق قواعد الترقيم والتصنيفات في البرنامج بنجاح.")
            cats = self.get_odoo_categories_list()
            if hasattr(self, 'combo_default_category'):
                self.combo_default_category.configure(values=cats)

        cats = self.get_odoo_categories_list()
        RulesEditorDialog(self, self.engine.config_path, on_save_callback=on_config_updated, odoo_categories=cats)


if __name__ == "__main__":
    app = OdooImportApp()
    app.mainloop()
