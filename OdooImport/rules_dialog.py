"""
Rules and Categories Visual Table Editor for Odoo Item Importer.
Provides an interactive, easy-to-edit table for:
1. Internal Reference Ranges (قواعد الترقيم)
2. Category Aliases (مطابقة التصنيفات)
3. Advanced JSON configuration view
Full RTL/LTR direction support and dropdown category selection from Odoo.
"""

import os
import re
import json
import ctypes
import customtkinter as ctk
from tkinter import messagebox
from typing import Callable, Optional, Dict, Any, List

from import_engine import DEFAULT_TAX_RULES

# Official 32 Odoo Product Categories
DEFAULT_ODOO_CATEGORIES = [
    "All",
    "All / Expenses",
    "GCP-General Cosmetics Products",
    "GCS-General Cosmetics Samples",
    "GCT-General Cosmetics Testers",
    "GIP-General Imported Products",
    "GP-GENERAL PRODUCT",
    "GPS-GENERAL PRODUCT SAMPLE",
    "GPT-GENERAL PRODUCT TESTER",
    "HCP-Hair Care Products",
    "HCS-Hair Care Samples",
    "HCT-Hair Care Testers",
    "HHP-Houshold Products",
    "HHS-Houshold Samples",
    "HHT-Houshold Testers",
    "HQP-High Quality Perfumes",
    "HQS-High Quality Samples",
    "HQT-High Quality Testers",
    "MAP-Mass Quality Perfumes",
    "MAS-Mass Quality Samples",
    "MAT-Mass Quality Testers",
    "MDP-Medium Quality Perfumes",
    "MDS-Medium Quality Samples",
    "MDT-Medium Quality Testers",
    "PSP-Personal Care Products",
    "PSS-Personal Care Samples",
    "PST-Personal Care Testers",
    "SCP-Skin Care Products",
    "SCS-Skin Care",
    "SCS-Skin Care Samples",
    "SCT-Skin Care Testers",
    "SET-GIFT COLLECT",
    "STF-Display Stand"
]


def is_arabic(text: str) -> bool:
    """Detects if text contains Arabic characters."""
    if not text:
        return False
    for ch in text:
        if '\u0600' <= ch <= '\u06FF' or '\u0750' <= ch <= '\u077F' or '\u08A0' <= ch <= '\u08FF':
            return True
    return False


def update_entry_direction(widget: Any, text: Optional[str] = None):
    """
    Sets entry alignment and reading order:
    - If Arabic: justify='right', sets Win32 WS_EX_RTLREADING | WS_EX_RIGHT
    - If non-Arabic: justify='left', sets LTR reading
    Supports both CTkEntry and CTkComboBox.
    """
    if widget is None:
        return

    actual_entry = getattr(widget, "_entry", widget)

    if text is None:
        try:
            text = widget.get()
        except Exception:
            text = ""

    is_ar = is_arabic(str(text))
    desired_justify = "right" if is_ar else "left"

    try:
        if hasattr(widget, "configure"):
            widget.configure(justify=desired_justify)
    except Exception:
        pass

    try:
        if actual_entry and hasattr(actual_entry, "configure"):
            actual_entry.configure(justify=desired_justify)

        if actual_entry and hasattr(actual_entry, "winfo_id"):
            hwnd = actual_entry.winfo_id()
            if hwnd:
                user32 = ctypes.windll.user32
                GWL_EXSTYLE = -20
                WS_EX_RTLREADING = 0x00002000
                WS_EX_RIGHT = 0x00001000
                style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                if is_ar:
                    style |= (WS_EX_RTLREADING | WS_EX_RIGHT)
                else:
                    style &= ~(WS_EX_RTLREADING | WS_EX_RIGHT)
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
                user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
    except Exception:
        pass


class RulesEditorDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent,
        config_path: str,
        on_save_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        odoo_categories: Optional[List[str]] = None
    ):
        super().__init__(parent)
        self.title("إدارة قواعد الترقيم والتصنيفات — Rules & Categories Manager")
        self.geometry("900x720")
        self.minsize(820, 600)
        self.config_path = config_path
        self.on_save_callback = on_save_callback

        self.full_config: Dict[str, Any] = {}
        self.range_rows: List[Dict[str, Any]] = []
        self.alias_rows: List[Dict[str, Any]] = []

        self.load_config()

        # Resolve available Odoo categories list
        if odoo_categories and len(odoo_categories) > 0:
            self.odoo_categories = list(odoo_categories)
        else:
            cfg_cats = list(self.full_config.get("category_prefix_rules", {}).keys())
            if cfg_cats:
                self.odoo_categories = sorted(cfg_cats)
            else:
                self.odoo_categories = list(DEFAULT_ODOO_CATEGORIES)

        self.grab_set()
        self.after(100, self.lift)

        self._build_ui()

    def load_config(self):
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.full_config = json.load(f)
        except Exception as e:
            self.full_config = {"settings": {}, "internal_reference_ranges": [], "category_aliases": {}}
            print(f"[RulesDialog] Error loading config: {e}")

    def _build_ui(self):
        # 1. Title Banner
        banner_frame = ctk.CTkFrame(self, fg_color="#1E293B", corner_radius=0, height=65)
        banner_frame.pack(fill="x")
        banner_frame.pack_propagate(False)

        title_lbl = ctk.CTkLabel(
            banner_frame,
            text="⚙️ جدول قواعد الترقيم ومطابقة التصنيفات",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color="#FFFFFF"
        )
        title_lbl.pack(side="right", padx=20, pady=(10, 2))

        sub_lbl = ctk.CTkLabel(
            banner_frame,
            text="تعديل بادئات الترقيم الآلي ومطابقة أسماء تصنيفات الموردين مع فئات أودو الرسمية عبر القائمة المنسدلة",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94A3B8"
        )
        sub_lbl.pack(side="right", padx=20, pady=(0, 10))

        # 2. Tabs (RTL feel)
        self.tabview = ctk.CTkTabview(self, fg_color="#F8FAFC")
        self.tabview.pack(fill="both", expand=True, padx=16, pady=(10, 6))

        tab_aliases = self.tabview.add("🏷️ مطابقة التصنيفات (Aliases)")
        tab_ranges = self.tabview.add("🔢 قواعد مدى الترقيم (Ranges)")
        tab_tax = self.tabview.add("💰 قواعد تمييز الضريبة (Tax Rules)")
        tab_json = self.tabview.add("📝 كود JSON المتقدم")

        self._build_aliases_tab(tab_aliases)
        self._build_ranges_tab(tab_ranges)
        self._build_tax_tab(tab_tax)
        self._build_json_tab(tab_json)

        # 3. Bottom Action Bar
        action_bar = ctk.CTkFrame(self, fg_color="#FFFFFF", height=60, corner_radius=0, border_width=1, border_color="#E2E8F0")
        action_bar.pack(fill="x", side="bottom")
        action_bar.pack_propagate(False)

        btn_save = ctk.CTkButton(
            action_bar,
            text="💾 حفظ وتطبيق التغييرات",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            height=38,
            width=200,
            command=self.save_all
        )
        btn_save.pack(side="right", padx=16, pady=11)

        btn_cancel = ctk.CTkButton(
            action_bar,
            text="إلغاء",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color="#64748B",
            hover_color="#475569",
            height=38,
            width=90,
            command=self.destroy
        )
        btn_cancel.pack(side="left", padx=16, pady=11)

    # -------------------------------------------------------------
    # TAB 1: RANGES
    # -------------------------------------------------------------
    def _build_ranges_tab(self, parent):
        # Description
        desc = ctk.CTkLabel(
            parent,
            text="تُحدد هذه القواعد بادئة الكود الداخلي (Internal Reference Prefix) للصنف بناءً على كود التصنيف والـ Tag.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#475569"
        )
        desc.pack(anchor="e", padx=10, pady=(4, 6))

        # Table Header (RTL order: Category -> Tag -> Prefix -> Description -> Delete)
        hdr_frame = ctk.CTkFrame(parent, fg_color="#1E6EBA", height=36, corner_radius=6)
        hdr_frame.pack(fill="x", padx=10, pady=(2, 4))
        hdr_frame.pack_propagate(False)

        col_w = {"cat": 130, "tag": 130, "prefix": 120, "desc": 320, "del": 45}
        ctk.CTkLabel(hdr_frame, text="كود الفئة (Category)", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color="#FFFFFF", width=col_w["cat"]).pack(side="right", padx=4)
        ctk.CTkLabel(hdr_frame, text="كود الوسم (Tag)", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color="#FFFFFF", width=col_w["tag"]).pack(side="right", padx=4)
        ctk.CTkLabel(hdr_frame, text="بادئة الترقيم (Prefix)", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color="#FFFFFF", width=col_w["prefix"]).pack(side="right", padx=4)
        ctk.CTkLabel(hdr_frame, text="الوصف والبيان", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color="#FFFFFF", width=col_w["desc"]).pack(side="right", padx=4)
        ctk.CTkLabel(hdr_frame, text="إجراء", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color="#FFFFFF", width=col_w["del"]).pack(side="left", padx=6)

        # Scrollable container for rows
        self.scroll_ranges = ctk.CTkScrollableFrame(parent, fg_color="#FFFFFF", corner_radius=6, border_width=1, border_color="#CBD5E1")
        self.scroll_ranges.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        # Populate existing ranges
        ranges = self.full_config.get("internal_reference_ranges", [])
        for r in ranges:
            self.add_range_row(
                category_code=r.get("category_code", ""),
                tag_code=r.get("tag_code", ""),
                prefix=r.get("prefix", ""),
                description=r.get("description", "")
            )

        # Add Row Button (Placed on Right for RTL)
        btn_add = ctk.CTkButton(
            parent,
            text="➕ إضافة قاعدة ترقيم جديدة",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#0F766E",
            hover_color="#115E59",
            height=34,
            command=lambda: self.add_range_row("", "", "", "")
        )
        btn_add.pack(anchor="e", padx=10, pady=(0, 6))

    def add_range_row(self, category_code: str = "", tag_code: str = "", prefix: str = "", description: str = ""):
        row_frame = ctk.CTkFrame(self.scroll_ranges, fg_color="#F8FAFC", corner_radius=4, height=36)
        row_frame.pack(fill="x", pady=2)

        e_cat = ctk.CTkEntry(row_frame, width=130, height=30, placeholder_text="مثال: SCP", justify="left")
        e_cat.insert(0, category_code)
        e_cat.pack(side="right", padx=4)

        e_tag = ctk.CTkEntry(row_frame, width=130, height=30, placeholder_text="مثال: SG0040", justify="left")
        e_tag.insert(0, tag_code)
        e_tag.pack(side="right", padx=4)

        e_pre = ctk.CTkEntry(row_frame, width=120, height=30, placeholder_text="مثال: 4505-4", justify="left")
        e_pre.insert(0, prefix)
        e_pre.pack(side="right", padx=4)

        e_desc = ctk.CTkEntry(row_frame, width=320, height=30, placeholder_text="وصف القاعدة...")
        e_desc.insert(0, description)
        update_entry_direction(e_desc, description)
        e_desc.bind("<KeyRelease>", lambda event, e=e_desc: update_entry_direction(e))
        self.after(50, lambda e=e_desc: update_entry_direction(e))
        e_desc.pack(side="right", padx=4)

        row_item = {
            "frame": row_frame,
            "e_cat": e_cat,
            "e_tag": e_tag,
            "e_pre": e_pre,
            "e_desc": e_desc
        }

        btn_del = ctk.CTkButton(
            row_frame,
            text="🗑️",
            width=38,
            height=30,
            fg_color="#FEE2E2",
            text_color="#DC2626",
            hover_color="#FCA5A5",
            command=lambda: self.delete_range_row(row_item)
        )
        btn_del.pack(side="left", padx=6)

        self.range_rows.append(row_item)

    def delete_range_row(self, row_item: Dict[str, Any]):
        if row_item in self.range_rows:
            self.range_rows.remove(row_item)
            row_item["frame"].destroy()

    # -------------------------------------------------------------
    # TAB 2: ALIASES (Dropdown ComboBox with typing capability)
    # -------------------------------------------------------------
    def _build_aliases_tab(self, parent):
        desc = ctk.CTkLabel(
            parent,
            text="مطابقة أسماء الفئات الواردة في ملف المورد مع فئات أودو الرسمية عبر القائمة المنسدلة مع إمكانية الكتابة اليدوية.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#475569"
        )
        desc.pack(anchor="e", padx=10, pady=(4, 6))

        # Table Header (RTL order: Raw Alias -> Target Odoo Category -> Delete)
        hdr_frame = ctk.CTkFrame(parent, fg_color="#1E6EBA", height=36, corner_radius=6)
        hdr_frame.pack(fill="x", padx=10, pady=(2, 4))
        hdr_frame.pack_propagate(False)

        col_w = {"alias": 310, "target": 410, "del": 45}
        ctk.CTkLabel(hdr_frame, text="اسم التصنيف عند المورد (Raw Alias)", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color="#FFFFFF", width=col_w["alias"]).pack(side="right", padx=6)
        ctk.CTkLabel(hdr_frame, text="التصنيف المقابل المعتمد بأودو (Odoo Category)", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color="#FFFFFF", width=col_w["target"]).pack(side="right", padx=6)
        ctk.CTkLabel(hdr_frame, text="إجراء", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color="#FFFFFF", width=col_w["del"]).pack(side="left", padx=6)

        # Scrollable container for rows
        self.scroll_aliases = ctk.CTkScrollableFrame(parent, fg_color="#FFFFFF", corner_radius=6, border_width=1, border_color="#CBD5E1")
        self.scroll_aliases.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        aliases = self.full_config.get("category_aliases", {})
        for raw_alias, target_cat in aliases.items():
            self.add_alias_row(raw_alias=raw_alias, target_category=target_cat)

        btn_add = ctk.CTkButton(
            parent,
            text="➕ إضافة تصنيف مرادف جديد",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#0F766E",
            hover_color="#115E59",
            height=34,
            command=lambda: self.add_alias_row("", "")
        )
        btn_add.pack(anchor="e", padx=10, pady=(0, 6))

    def add_alias_row(self, raw_alias: str = "", target_category: str = ""):
        row_frame = ctk.CTkFrame(self.scroll_aliases, fg_color="#F8FAFC", corner_radius=4, height=36)
        row_frame.pack(fill="x", pady=2)

        # 1. Raw Alias entry (RTL/LTR dynamic)
        e_alias = ctk.CTkEntry(row_frame, width=310, height=30, placeholder_text="مثال: eye & lash care أو عناية بالبشرة")
        e_alias.insert(0, raw_alias)
        update_entry_direction(e_alias, raw_alias)
        e_alias.bind("<KeyRelease>", lambda event, e=e_alias: update_entry_direction(e))
        self.after(50, lambda e=e_alias: update_entry_direction(e))
        e_alias.pack(side="right", padx=6)

        # 2. Target Category Dropdown (CTkComboBox allows selection AND free typing)
        e_target = ctk.CTkComboBox(
            row_frame,
            width=410,
            height=30,
            values=self.odoo_categories,
            font=ctk.CTkFont(family="Segoe UI", size=12)
        )
        if target_category:
            e_target.set(target_category)
        else:
            e_target.set("")
        update_entry_direction(e_target, target_category)
        if hasattr(e_target, "_entry"):
            e_target._entry.bind("<KeyRelease>", lambda event, e=e_target: update_entry_direction(e))
        self.after(50, lambda e=e_target: update_entry_direction(e))
        e_target.pack(side="right", padx=6)

        # 3. Delete button on far left
        btn_del = ctk.CTkButton(
            row_frame,
            text="🗑️",
            width=38,
            height=30,
            fg_color="#FEE2E2",
            text_color="#DC2626",
            hover_color="#FCA5A5",
            command=lambda: self.delete_alias_row(row_item)
        )
        btn_del.pack(side="left", padx=6)

        row_item = {
            "frame": row_frame,
            "e_alias": e_alias,
            "e_target": e_target
        }
        self.alias_rows.append(row_item)

    def delete_alias_row(self, row_item: Dict[str, Any]):
        if row_item in self.alias_rows:
            self.alias_rows.remove(row_item)
            row_item["frame"].destroy()

    # -------------------------------------------------------------
    # TAB 3: JSON VIEW
    # -------------------------------------------------------------
    # TAB 3: TAX RULES
    # -------------------------------------------------------------
    def _build_tax_tab(self, parent):
        desc = ctk.CTkLabel(
            parent,
            text="الكلمات والمصطلحات التي يعتمد عليها البرنامج للتعرف التلقائي على خضوع الصنف للضريبة (15%) أو إعفائه (0%) من ملفات الموردين.\nالبرنامج يتعرف تلقائياً على العبارات المركبة مثل 'Yes - 15% VAT' أو '15% VAT' أو 'شامل الضريبة'. يمكنك إضافة كلمات إضافية مفصولة بفواصل أو أسطر.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#475569",
            justify="right",
            wraplength=800
        )
        desc.pack(anchor="e", padx=14, pady=(8, 10))

        tax_rules = self.full_config.get("tax_rules", {})
        taxable_list = tax_rules.get("taxable_keywords", DEFAULT_TAX_RULES["taxable_keywords"])
        exempt_list = tax_rules.get("exempt_keywords", DEFAULT_TAX_RULES["exempt_keywords"])

        # 1. Taxable Box (Green)
        box_taxable = ctk.CTkFrame(parent, fg_color="#F0FDF4", border_width=1, border_color="#BBF7D0", corner_radius=8)
        box_taxable.pack(fill="x", padx=14, pady=6)

        lbl_tax = ctk.CTkLabel(
            box_taxable,
            text="🟢 كلمات الخضوع للضريبة 15% (Taxable Keywords):",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#166534"
        )
        lbl_tax.pack(anchor="e", padx=10, pady=(8, 4))

        self.txt_taxable_kw = ctk.CTkTextbox(box_taxable, font=ctk.CTkFont(family="Segoe UI", size=12), height=70)
        self.txt_taxable_kw.pack(fill="x", padx=10, pady=(0, 8))
        self.txt_taxable_kw.insert("1.0", ", ".join(taxable_list))

        # 2. Exempt Box (Amber)
        box_exempt = ctk.CTkFrame(parent, fg_color="#FEFCE8", border_width=1, border_color="#FEF08A", corner_radius=8)
        box_exempt.pack(fill="x", padx=14, pady=6)

        lbl_ex = ctk.CTkLabel(
            box_exempt,
            text="⚪ كلمات الإعفاء من الضريبة 0% (Exempt Keywords):",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#854D0E"
        )
        lbl_ex.pack(anchor="e", padx=10, pady=(8, 4))

        self.txt_exempt_kw = ctk.CTkTextbox(box_exempt, font=ctk.CTkFont(family="Segoe UI", size=12), height=70)
        self.txt_exempt_kw.pack(fill="x", padx=10, pady=(0, 8))
        self.txt_exempt_kw.insert("1.0", ", ".join(exempt_list))

        # 3. Tax Database IDs Box (Blue)
        settings = self.full_config.get("settings", {})
        cust_tax_15 = str(settings.get("customer_tax_id", 1))
        vend_tax_15 = str(settings.get("vendor_tax_id", 3))
        cust_tax_0 = str(settings.get("customer_tax_id_zero", 45))
        vend_tax_0 = str(settings.get("vendor_tax_id_zero", 9))

        box_ids = ctk.CTkFrame(parent, fg_color="#F8FAFC", border_width=1, border_color="#CBD5E1", corner_radius=8)
        box_ids.pack(fill="x", padx=14, pady=6)

        lbl_ids = ctk.CTkLabel(
            box_ids,
            text="🏷️ أرقام معرّفات الضرائب في أودو (Odoo Database Tax IDs):",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#0F172A"
        )
        lbl_ids.pack(anchor="e", padx=10, pady=(8, 4))

        grid_frame = ctk.CTkFrame(box_ids, fg_color="transparent")
        grid_frame.pack(fill="x", padx=10, pady=(0, 8))

        # Row 1: 15% taxes
        ctk.CTkLabel(grid_frame, text="ضريبة المبيعات 15% (Customer Tax ID):", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#166534").grid(row=0, column=3, padx=6, pady=4, sticky="e")
        self.entry_cust_tax_15 = ctk.CTkEntry(grid_frame, width=70, height=28, justify="center")
        self.entry_cust_tax_15.insert(0, cust_tax_15)
        self.entry_cust_tax_15.grid(row=0, column=2, padx=6, pady=4, sticky="w")

        ctk.CTkLabel(grid_frame, text="ضريبة المشتريات 15% (Vendor Tax ID):", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#166534").grid(row=0, column=1, padx=6, pady=4, sticky="e")
        self.entry_vend_tax_15 = ctk.CTkEntry(grid_frame, width=70, height=28, justify="center")
        self.entry_vend_tax_15.insert(0, vend_tax_15)
        self.entry_vend_tax_15.grid(row=0, column=0, padx=6, pady=4, sticky="w")

        # Row 2: 0% / Exempt taxes
        ctk.CTkLabel(grid_frame, text="ضريبة المبيعات 0% (معفى / Customer 0% ID):", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#854D0E").grid(row=1, column=3, padx=6, pady=4, sticky="e")
        self.entry_cust_tax_0 = ctk.CTkEntry(grid_frame, width=70, height=28, justify="center")
        self.entry_cust_tax_0.insert(0, cust_tax_0)
        self.entry_cust_tax_0.grid(row=1, column=2, padx=6, pady=4, sticky="w")

        ctk.CTkLabel(grid_frame, text="ضريبة المشتريات 0% (معفى / Vendor 0% ID):", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#854D0E").grid(row=1, column=1, padx=6, pady=4, sticky="e")
        self.entry_vend_tax_0 = ctk.CTkEntry(grid_frame, width=70, height=28, justify="center")
        self.entry_vend_tax_0.insert(0, vend_tax_0)
        self.entry_vend_tax_0.grid(row=1, column=0, padx=6, pady=4, sticky="w")

    # -------------------------------------------------------------
    # TAB 4: JSON VIEW
    # -------------------------------------------------------------
    def _build_json_tab(self, parent):
        desc = ctk.CTkLabel(
            parent,
            text="عرض محتوى ملف الإعدادات الكامل بصيغة JSON (للمستخدمين المتقدمين).",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#475569"
        )
        desc.pack(anchor="e", padx=10, pady=(4, 6))

        self.txt_json = ctk.CTkTextbox(parent, font=ctk.CTkFont(family="Consolas", size=12))
        self.txt_json.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.txt_json.insert("1.0", f.read())
        except Exception as e:
            self.txt_json.insert("1.0", f"Error loading json: {e}")

    # -------------------------------------------------------------
    # SAVE ACTION
    # -------------------------------------------------------------
    def save_all(self):
        # 1. Collect ranges
        new_ranges = []
        for r in self.range_rows:
            cat = r["e_cat"].get().strip()
            tag = r["e_tag"].get().strip()
            pre = r["e_pre"].get().strip()
            desc = r["e_desc"].get().strip()

            # Ignore totally empty rows
            if not cat and not tag and not pre and not desc:
                continue

            if not pre:
                messagebox.showerror("خطأ في البيانات", f"يجب إدخال بادئة الترقيم (Prefix) للقاعدة: '{cat} / {tag}'", parent=self)
                return

            new_ranges.append({
                "category_code": cat,
                "tag_code": tag,
                "prefix": pre,
                "description": desc
            })

        # 2. Collect aliases
        new_aliases = {}
        for a in self.alias_rows:
            raw = a["e_alias"].get().strip()
            target = a["e_target"].get().strip()

            if not raw and not target:
                continue

            if not raw or not target:
                messagebox.showerror("خطأ في البيانات", "يجب ملء اسم التصنيف عند المورد والتصنيف المقابل في أودو معاً.", parent=self)
                return

            new_aliases[raw.lower()] = target

        # 3. Assemble full config
        updated_config = dict(self.full_config)
        updated_config["internal_reference_ranges"] = new_ranges
        updated_config["category_aliases"] = new_aliases

        # Collect tax rules if tab exists
        if hasattr(self, 'txt_taxable_kw') and hasattr(self, 'txt_exempt_kw'):
            raw_taxable = self.txt_taxable_kw.get("1.0", "end")
            raw_exempt = self.txt_exempt_kw.get("1.0", "end")
            taxable_words = [w.strip() for w in re.split(r'[,،\n]+', raw_taxable) if w.strip()]
            exempt_words = [w.strip() for w in re.split(r'[,،\n]+', raw_exempt) if w.strip()]
            updated_config["tax_rules"] = {
                "taxable_keywords": taxable_words,
                "exempt_keywords": exempt_words
            }

        # Collect tax database IDs if present
        if "settings" not in updated_config or not isinstance(updated_config["settings"], dict):
            updated_config["settings"] = {}

        if hasattr(self, 'entry_cust_tax_15'):
            try:
                updated_config["settings"]["customer_tax_id"] = int(self.entry_cust_tax_15.get().strip())
            except ValueError:
                pass
        if hasattr(self, 'entry_vend_tax_15'):
            try:
                updated_config["settings"]["vendor_tax_id"] = int(self.entry_vend_tax_15.get().strip())
            except ValueError:
                pass
        if hasattr(self, 'entry_cust_tax_0'):
            try:
                updated_config["settings"]["customer_tax_id_zero"] = int(self.entry_cust_tax_0.get().strip())
            except ValueError:
                pass
        if hasattr(self, 'entry_vend_tax_0'):
            try:
                updated_config["settings"]["vendor_tax_id_zero"] = int(self.entry_vend_tax_0.get().strip())
            except ValueError:
                pass

        # 4. Save to config.json
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(updated_config, f, ensure_ascii=False, indent=2)

            self.full_config = updated_config

            # Update JSON tab text
            self.txt_json.delete("1.0", "end")
            self.txt_json.insert("1.0", json.dumps(updated_config, ensure_ascii=False, indent=2))

            if self.on_save_callback:
                self.on_save_callback(updated_config)

            messagebox.showinfo(
                "تم الحفظ بنجاح",
                f"تم حفظ {len(new_ranges)} قاعدة ترقيم و {len(new_aliases)} تصنيف وقواعد الضريبة بنجاح في ملف الإعدادات.",
                parent=self
            )
            self.destroy()

        except Exception as e:
            messagebox.showerror("خطأ في الحفظ", f"تعذر حفظ ملف الإعدادات:\n{e}", parent=self)
