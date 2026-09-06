"""
OdooReportExporter – Main GUI (v1.01)
Designed & developed by: عبدالله الخطيب (Abdullah Al-Khatib)
"""

APP_VERSION = "v1.01"

import os
import sys
import json
import threading
from datetime import datetime, timedelta

import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from licensing import get_machine_id, is_activated, activate_device
from permissions import ALL_PROTECTED_FIELDS, load_permissions, save_permissions, verify_admin_password
from exporter_engine import get_active_showrooms, get_all_product_tags, generate_report
from showroom_config import get_showroom_category, load_showroom_types, save_showroom_types, is_default_care_showroom


# ─────────────────────────────────────────────────────────
# 🎨 Design tokens (override per theme in apply_theme)
# ─────────────────────────────────────────────────────────
BRAND_GOLD = "#D4A017"
BRAND_BLUE = "#1E6EBA"
BRAND_BLUE_HOVER = "#1558A0"
BRAND_GREEN = "#16A34A"
BRAND_GREEN_HOVER = "#138040"
BRAND_RED = "#DC2626"
BRAND_RED_HOVER = "#B91C1C"
BRAND_PURPLE = "#7C3AED"
BRAND_PURPLE_HOVER = "#6D28D9"
BRAND_SLATE = "#64748B"
BRAND_SLATE_HOVER = "#475569"

APP_FONT = "Segoe UI"

# ─────────────────────────────────────────────────────────
# ⚙️ Persistent user settings
# ─────────────────────────────────────────────────────────
def _settings_path():
    d = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "AlAssaliOdooExporter")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "settings.json")

def load_settings():
    try:
        with open(_settings_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"theme": "Dark"}

def save_settings(s):
    try:
        with open(_settings_path(), "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────
# 🔒 Secure Password Dialog (hides input)
# ─────────────────────────────────────────────────────────
class SecurePasswordDialog(ctk.CTkToplevel):
    """Modal dialog that hides password input."""
    def __init__(self, parent, title="إدخال كلمة المرور", prompt="أدخل كلمة المرور:"):
        super().__init__(parent)
        self.title(title)
        self.geometry("420x220")
        self.resizable(False, False)
        self.grab_set()
        self.lift()
        self.focus_force()
        self._result = None

        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(APP_FONT, 15, "bold"),
                     text_color=BRAND_BLUE).pack(pady=(18, 4))
        ctk.CTkLabel(self, text=prompt, font=ctk.CTkFont(APP_FONT, 12)).pack(pady=(0, 8))

        self._entry = ctk.CTkEntry(self, show="●", width=300, height=38,
                                   font=ctk.CTkFont("Consolas", 14), justify="center")
        self._entry.pack(pady=(0, 14))
        self._entry.bind("<Return>", lambda _: self._submit())

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack()
        ctk.CTkButton(btn_frame, text="تأكيد", width=110, height=34,
                      fg_color=BRAND_BLUE, hover_color=BRAND_BLUE_HOVER,
                      command=self._submit).pack(side="left", padx=8)
        ctk.CTkButton(btn_frame, text="إلغاء", width=110, height=34,
                      fg_color=BRAND_SLATE, hover_color=BRAND_SLATE_HOVER,
                      command=self._cancel).pack(side="left", padx=8)

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._entry.focus()

    def _submit(self):
        self._result = self._entry.get()
        self.destroy()

    def _cancel(self):
        self._result = None
        self.destroy()

    def get_input(self):
        self.wait_window()
        return self._result


# ─────────────────────────────────────────────────────────
# 🏷️ Tag Multi-Select with Autocomplete
# ─────────────────────────────────────────────────────────
class TagMultiSelect(ctk.CTkFrame):
    """
    A tag/chip selector with live autocomplete search.
    Tags are loaded from Odoo. Selected tags shown as removable chips.
    """
    def __init__(self, master, tags_list=None, **kwargs):
        super().__init__(master, **kwargs)
        self._all_tags = self._extract_tag_names(tags_list)
        self._selected = []
        self._dropdown_open = False
        self._dropdown_items = []

        # ─ Top: search entry ─
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=0, pady=0)

        self._entry = ctk.CTkEntry(top, placeholder_text="ابحث عن وسم... (اكتب للبحث أو اضغط مسافة للاختيار)",
                                   height=36, font=ctk.CTkFont(APP_FONT, 12))
        self._entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._entry.bind("<KeyRelease>", self._on_key)
        self._entry.bind("<space>", self._on_space)
        self._entry.bind("<FocusIn>", self._on_key)

        ctk.CTkButton(top, text="✕ مسح الكل", width=90, height=36,
                      fg_color=BRAND_SLATE, hover_color=BRAND_SLATE_HOVER,
                      font=ctk.CTkFont(APP_FONT, 11), command=self._clear_all).pack(side="left")

        # ─ Dropdown container ─
        self._dropdown_container = ctk.CTkFrame(self, fg_color="transparent")
        self._dropdown_container.pack(fill="x")

        self._dropdown_frame = ctk.CTkScrollableFrame(self._dropdown_container, height=140, fg_color=("white", "#1E293B"),
                                                      border_width=1, border_color=("#CBD5E1", "#334155"),
                                                      corner_radius=6)

        # ─ Chips area ─
        self._chips_frame = ctk.CTkScrollableFrame(self, height=80, orientation="horizontal",
                                                   fg_color=("gray93", "#1A2230"),
                                                   corner_radius=6)
        self._chips_frame.pack(fill="x", pady=(6, 0))

        self._redraw_chips()

    def _extract_tag_names(self, tags_list):
        cleaned = []
        if not tags_list:
            return cleaned
        for item in tags_list:
            if isinstance(item, dict):
                n = str(item.get('name') or '').strip()
            else:
                n = str(item or '').strip()
            n = " ".join(n.split())
            if n and n not in cleaned:
                cleaned.append(n)
        return sorted(cleaned, key=lambda s: s.lower())

    def _on_key(self, event=None):
        text = self._entry.get().strip().lower().rstrip(" ")
        if not text:
            self._hide_dropdown()
            return
        matches = [t for t in self._all_tags if text in t.lower() and t not in self._selected][:40]
        if matches:
            self._refresh_dropdown(matches)
            self._show_dropdown()
        else:
            self._hide_dropdown()

    def _on_space(self, event=None):
        """Auto-select the first matching tag on space press."""
        text = self._entry.get().strip().rstrip(" ")
        if not text:
            return
        matches = [t for t in self._all_tags if text.lower() in t.lower() and t not in self._selected]
        if matches:
            self._add_tag(matches[0])
        return "break"  # prevent space insertion

    def _refresh_dropdown(self, items):
        for w in self._dropdown_frame.winfo_children():
            w.destroy()
        self._dropdown_items = []
        for tag_name in items:
            btn = ctk.CTkButton(self._dropdown_frame, text=tag_name,
                                height=28, anchor="e",
                                font=ctk.CTkFont(APP_FONT, 11),
                                fg_color="transparent",
                                hover_color=(BRAND_BLUE + "22", BRAND_BLUE + "44"),
                                text_color=("black", "white"),
                                command=lambda t=tag_name: self._add_tag(t))
            btn.pack(fill="x", padx=4, pady=1)
            self._dropdown_items.append(btn)

    def _show_dropdown(self):
        if not self._dropdown_open:
            self._dropdown_frame.pack(fill="x", pady=(2, 0))
            self._dropdown_open = True

    def _hide_dropdown(self):
        if self._dropdown_open:
            self._dropdown_frame.pack_forget()
            self._dropdown_open = False

    def _add_tag(self, tag_name):
        if tag_name and tag_name not in self._selected:
            self._selected.append(tag_name)
            self._redraw_chips()
        self._entry.delete(0, "end")
        self._hide_dropdown()

    def _remove_tag(self, tag_name):
        if tag_name in self._selected:
            self._selected.remove(tag_name)
            self._redraw_chips()

    def _redraw_chips(self):
        for w in self._chips_frame.winfo_children():
            w.destroy()
        if not self._selected:
            ctk.CTkLabel(self._chips_frame, text="لا توجد وسوم محددة بعد",
                         text_color=BRAND_SLATE, font=ctk.CTkFont(APP_FONT, 11)).pack(side="right", padx=6)
            return
        for tag_name in self._selected:
            chip = ctk.CTkFrame(self._chips_frame, fg_color=(BRAND_BLUE, BRAND_BLUE),
                                corner_radius=14, height=30)
            chip.pack(side="right", padx=4, pady=4)
            chip.pack_propagate(False)

            inner = ctk.CTkFrame(chip, fg_color="transparent")
            inner.pack(fill="both", expand=True, padx=6, pady=2)

            ctk.CTkButton(inner, text="✕", width=20, height=20,
                          fg_color="transparent", hover_color=BRAND_RED,
                          text_color="white", font=ctk.CTkFont(APP_FONT, 10),
                          command=lambda t=tag_name: self._remove_tag(t)).pack(side="left")

            ctk.CTkLabel(inner, text=tag_name, text_color="white",
                         font=ctk.CTkFont(APP_FONT, 11)).pack(side="left", padx=(0, 4))

    def _clear_all(self):
        self._selected.clear()
        self._redraw_chips()
        self._entry.delete(0, "end")
        self._hide_dropdown()

    def get_selected_tags(self):
        """Returns comma-separated string of selected tags."""
        return ", ".join(self._selected) if self._selected else None

    def set_tags_list(self, tags_list):
        """Update available tags list (after fetching from Odoo)."""
        self._all_tags = self._extract_tag_names(tags_list)
        text = self._entry.get().strip().lower().rstrip(" ")
        if text:
            self._on_key()


# ─────────────────────────────────────────────────────────
# 📊 Section Card (visual grouping widget)
# ─────────────────────────────────────────────────────────
class SectionCard(ctk.CTkFrame):
    """A titled card for visually grouping content sections."""
    def __init__(self, master, title="", icon="", **kwargs):
        kwargs.setdefault("corner_radius", 10)
        super().__init__(master, **kwargs)

        if title:
            header = ctk.CTkFrame(self, fg_color="transparent")
            header.pack(fill="x", padx=14, pady=(10, 0))
            ctk.CTkLabel(header, text=f"{icon}  {title}" if icon else title,
                         font=ctk.CTkFont(APP_FONT, 13, "bold"),
                         text_color=(BRAND_BLUE, "#60A5FA")).pack(side="right")

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(fill="both", expand=True, padx=14, pady=(6, 12))


# ─────────────────────────────────────────────────────────
# 🖥️ Main Application
# ─────────────────────────────────────────────────────────
class OdooReportApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.settings = load_settings()
        ctk.set_appearance_mode(self.settings.get("theme", "Dark"))
        ctk.set_default_color_theme("blue")

        self.title(f"نظام تصدير تقارير منتجات ومعارض Odoo — شركة العسلي التجارية [{APP_VERSION}]")
        self._center_window(1060, 680)
        self.minsize(900, 540)

        self.showrooms = []
        self.all_tags = []
        self.showroom_vars = {}
        self.is_exporting = False
        self.last_exported_file = None
        self._cancel_flag = False

        if not is_activated():
            self._build_activation_screen()
        else:
            self._build_main_ui()

    # ══════════════════════════════════════════════════════
    # 🔒 ACTIVATION SCREEN
    # ══════════════════════════════════════════════════════
    def _center_window(self, w, h):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ══════════════════════════════════════════════════════
    # 🔒 ACTIVATION SCREEN
    # ══════════════════════════════════════════════════════
    def _build_activation_screen(self):
        self._center_window(640, 620)
        self.resizable(False, False)
        for w in self.winfo_children():
            w.destroy()

        outer = ctk.CTkFrame(self, fg_color=("gray95", "#0F172A"), corner_radius=0)
        outer.pack(fill="both", expand=True)

        # Top Gold accent bar
        bar = ctk.CTkFrame(outer, fg_color=BRAND_GOLD, height=5, corner_radius=0)
        bar.pack(fill="x")

        # Main Card
        card = ctk.CTkFrame(outer, corner_radius=14, fg_color=("white", "#1E293B"),
                            border_width=1, border_color=("gray85", "#334155"))
        card.pack(fill="both", expand=True, padx=25, pady=(15, 8))

        # Header with Icon
        header_frame = ctk.CTkFrame(card, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(15, 6))

        ctk.CTkLabel(header_frame, text="🔐", font=ctk.CTkFont(size=36)).pack()
        ctk.CTkLabel(header_frame, text="تفعيل وترخيص البرنامج",
                     font=ctk.CTkFont(APP_FONT, 18, "bold"),
                     text_color=(BRAND_BLUE, "#60A5FA")).pack(pady=(4, 2))
        ctk.CTkLabel(header_frame, text="هذا البرنامج مخصص ومحمي للأجهزة المعتمدة فقط.",
                     font=ctk.CTkFont(APP_FONT, 11), text_color=BRAND_SLATE).pack()

        sep = ctk.CTkFrame(card, height=1, fg_color=("gray85", "#334155"))
        sep.pack(fill="x", padx=20, pady=(6, 12))

        # 1. Machine ID Section
        mid_box = ctk.CTkFrame(card, fg_color=("gray92", "#0F172A"), corner_radius=10,
                               border_width=1, border_color=("gray80", "#334155"))
        mid_box.pack(fill="x", padx=20, pady=(0, 12))

        ctk.CTkLabel(mid_box, text="📌 معرّف هذا الجهاز (Machine ID) الخاص بك:",
                     font=ctk.CTkFont(APP_FONT, 12, "bold"),
                     text_color=(BRAND_BLUE, "#93C5FD")).pack(anchor="e", padx=14, pady=(8, 4))

        self._current_mid = get_machine_id()
        mid_row = ctk.CTkFrame(mid_box, fg_color="transparent")
        mid_row.pack(fill="x", padx=14, pady=(0, 6))

        self._mid_entry = ctk.CTkEntry(mid_row, font=ctk.CTkFont("Consolas", 15, "bold"),
                                       text_color=(BRAND_BLUE, "#60A5FA"), justify="center", height=38)
        self._mid_entry.insert(0, self._current_mid)
        self._mid_entry.configure(state="readonly")
        self._mid_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(mid_row, text="📋 نسخ المعرّف", width=110, height=38,
                      font=ctk.CTkFont(APP_FONT, 12, "bold"),
                      fg_color=BRAND_BLUE, hover_color=BRAND_BLUE_HOVER,
                      command=self._copy_machine_id).pack(side="left")

        ctk.CTkLabel(mid_box, text="انسخ المعرّف أعلاه وأرسله للمسؤول (الأستاذ عبدالله الخطيب) للحصول على مفتاح التفعيل.",
                     font=ctk.CTkFont(APP_FONT, 10), text_color=BRAND_SLATE).pack(anchor="e", padx=14, pady=(0, 8))

        # 2. Activation Key Entry Section
        key_box = ctk.CTkFrame(card, fg_color="transparent")
        key_box.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(key_box, text="🔑 أدخل مفتاح التفعيل (Activation Key):",
                     font=ctk.CTkFont(APP_FONT, 12, "bold")).pack(anchor="e", pady=(0, 4))

        self._act_entry = ctk.CTkEntry(key_box, placeholder_text="XXXX-XXXX-XXXX-XXXX",
                                       font=ctk.CTkFont("Consolas", 15, "bold"), justify="center", height=42)
        self._act_entry.pack(fill="x", pady=(0, 10))
        self._act_entry.bind("<Return>", lambda _: self._do_activate())

        ctk.CTkButton(key_box, text="🚀  تفعيل البرنامج والبدء بالاستخدام",
                      font=ctk.CTkFont(APP_FONT, 14, "bold"),
                      fg_color=BRAND_GREEN, hover_color=BRAND_GREEN_HOVER,
                      height=44, command=self._do_activate).pack(fill="x")

        # Footer Signature
        ctk.CTkLabel(outer, text="✨ تم التصميم والتطوير بواسطة: عبدالله الخطيب",
                     font=ctk.CTkFont(APP_FONT, 11, "bold"),
                     text_color=BRAND_GOLD).pack(side="bottom", pady=(2, 8))

    def _copy_machine_id(self):
        self.clipboard_clear()
        self.clipboard_append(self._current_mid)
        messagebox.showinfo("تم النسخ", f"تم نسخ معرّف الجهاز للحافظة بنجاح:\n\n{self._current_mid}\n\nأرسله للمسؤول للحصول على مفتاح التفعيل.")

    def _do_activate(self):
        key = self._act_entry.get().strip().upper()
        if not key:
            messagebox.showwarning("تنبيه", "يرجى إدخال مفتاح التفعيل أولاً.")
            return
        ok, msg = activate_device(key)
        if ok:
            messagebox.showinfo("نجاح التفعيل", "🎉 تم تفعيل البرنامج بنجاح لهذا الجهاز!\n\nيمكنك الآن استخدام كافة ميزات البرنامج.")
            self._center_window(1060, 680)
            self.resizable(True, True)
            self._build_main_ui()
        else:
            messagebox.showerror("خطأ في التفعيل", msg)

    # ══════════════════════════════════════════════════════
    # 🖥️ MAIN UI
    # ══════════════════════════════════════════════════════
    def _build_main_ui(self):
        for w in self.winfo_children():
            w.destroy()
        self.permissions, _ = load_permissions()

        main_container = ctk.CTkFrame(self, fg_color="transparent")
        main_container.pack(fill="both", expand=True)

        # ─── TOP HEADER BAR ───────────────────────────────────
        self._build_header(main_container)

        # ─── CONTENT AREA (Sidebar + Tabs) ────────────────────
        content = ctk.CTkFrame(main_container, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        # Build sidebar + tabview side by side
        self._build_sidebar(content)
        self._build_tabs(content)

        # ─── BOTTOM PROGRESS & ACTION BAR ─────────────────────
        self._build_footer(main_container)

        # Async loads
        self._load_showrooms_async()
        self._load_tags_async()

    # ─── HEADER ───────────────────────────────────────────────
    def _build_header(self, parent):
        hdr = ctk.CTkFrame(parent, corner_radius=0,
                            fg_color=(BRAND_BLUE, "#0F1E33"), height=58)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        # Gold accent strip
        accent = ctk.CTkFrame(hdr, fg_color=BRAND_GOLD, width=6, corner_radius=0)
        accent.pack(side="right", fill="y")

        # Left controls
        ctrl_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        ctrl_frame.pack(side="left", padx=12, pady=8)

        # Theme toggle
        self._theme_var = ctk.StringVar(value="☀️  فاتح" if self.settings.get("theme") == "Light" else "🌙  داكن")
        theme_menu = ctk.CTkOptionMenu(ctrl_frame,
                                       values=["🌙  داكن", "☀️  فاتح"],
                                       variable=self._theme_var,
                                       width=120, height=30,
                                       font=ctk.CTkFont(APP_FONT, 11),
                                       command=self._change_theme)
        theme_menu.pack(side="left", padx=(0, 8))

        # Admin permissions button
        ctk.CTkButton(ctrl_frame, text="🔒  الصلاحيات الإدارية",
                      font=ctk.CTkFont(APP_FONT, 11, "bold"),
                      fg_color=BRAND_PURPLE, hover_color=BRAND_PURPLE_HOVER,
                      width=148, height=30,
                      command=self._open_admin_dialog).pack(side="left")

        # Center: App title
        title_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        title_frame.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(title_frame, text="📊  نظام تصدير تقارير منتجات ومعارض Odoo",
                     font=ctk.CTkFont(APP_FONT, 17, "bold"),
                     text_color="white").pack()
        ctk.CTkLabel(title_frame,
                     text="✨ تم التصميم والتطوير بواسطة: عبدالله الخطيب",
                     font=ctk.CTkFont(APP_FONT, 11), text_color=BRAND_GOLD).pack()

    # ─── SIDEBAR ──────────────────────────────────────────────
    def _build_sidebar(self, parent):
        sidebar = ctk.CTkFrame(parent, width=220, corner_radius=10)
        sidebar.pack(side="right", fill="y", padx=(8, 0), pady=6)
        sidebar.pack_propagate(False)

        ctk.CTkLabel(sidebar, text="⚙️  إعدادات التصدير",
                     font=ctk.CTkFont(APP_FONT, 13, "bold"),
                     text_color=(BRAND_BLUE, "#60A5FA")).pack(pady=(14, 8))

        sep = ctk.CTkFrame(sidebar, height=1, fg_color=("gray80", "#334155"))
        sep.pack(fill="x", padx=12)

        # ── Movement filter ──────────────────────────────
        ctk.CTkLabel(sidebar, text="⚡ حركة الأصناف",
                     font=ctk.CTkFont(APP_FONT, 11, "bold"),
                     text_color=BRAND_SLATE).pack(anchor="e", padx=12, pady=(12, 4))

        self._movement_var = ctk.StringVar(value="all")
        movements = [
            ("all", "جميع الأصناف"),
            ("fast_moving", "🔥 سريعة الحركة"),
            ("stagnant", "⚠️  أصناف راكدة"),
            ("low_stock", "📉  قاربت على النفاذ"),
        ]
        for val, label in movements:
            ctk.CTkRadioButton(sidebar, text=label, variable=self._movement_var,
                               value=val, font=ctk.CTkFont(APP_FONT, 11)).pack(
                anchor="e", padx=18, pady=2)

        sep2 = ctk.CTkFrame(sidebar, height=1, fg_color=("gray80", "#334155"))
        sep2.pack(fill="x", padx=12, pady=10)

        # ── Column groups ────────────────────────────────
        ctk.CTkLabel(sidebar, text="📋 مجموعات الأعمدة",
                     font=ctk.CTkFont(APP_FONT, 11, "bold"),
                     text_color=BRAND_SLATE).pack(anchor="e", padx=12, pady=(0, 4))

        self._col_basic = ctk.BooleanVar(value=True)
        self._col_price = ctk.BooleanVar(value=True)
        self._col_totals = ctk.BooleanVar(value=True)
        self._col_vendors = ctk.BooleanVar(value=True)
        self._col_showrooms = ctk.BooleanVar(value=True)
        self._col_analytics = ctk.BooleanVar(value=True)

        col_options = [
            (self._col_basic, "البيانات الأساسية"),
            (self._col_price, "الأسعار"),
            (self._col_totals, "الإجماليات"),
            (self._col_vendors, "بيانات الموردين"),
            (self._col_showrooms, "تفاصيل المعارض"),
            (self._col_analytics, "تحليلات وتوصيات المخزون"),
        ]
        for var, label in col_options:
            ctk.CTkCheckBox(sidebar, text=label, variable=var,
                            font=ctk.CTkFont(APP_FONT, 11)).pack(anchor="e", padx=18, pady=2)

        sep3 = ctk.CTkFrame(sidebar, height=1, fg_color=("gray80", "#334155"))
        sep3.pack(fill="x", padx=12, pady=10)

        # ── Output path ──────────────────────────────────
        ctk.CTkLabel(sidebar, text="💾 حفظ الملف",
                     font=ctk.CTkFont(APP_FONT, 11, "bold"),
                     text_color=BRAND_SLATE).pack(anchor="e", padx=12, pady=(0, 4))

        default_file = os.path.join(
            os.path.expanduser("~"), "Desktop",
            f"تقرير_العسلي_{datetime.now().strftime('%Y%m%d')}.xlsx"
        )
        self._path_entry = ctk.CTkEntry(sidebar, placeholder_text="مسار الحفظ...",
                                        font=ctk.CTkFont(APP_FONT, 10), height=32)
        self._path_entry.insert(0, default_file)
        self._path_entry.pack(fill="x", padx=10, pady=(0, 4))

        ctk.CTkButton(sidebar, text="📂  استعراض", height=30,
                      fg_color=BRAND_SLATE, hover_color=BRAND_SLATE_HOVER,
                      font=ctk.CTkFont(APP_FONT, 11),
                      command=self._browse_path).pack(fill="x", padx=10)

    # ─── TABS ─────────────────────────────────────────────────
    def _build_tabs(self, parent):
        self._tabview = ctk.CTkTabview(parent, corner_radius=10)
        self._tabview.pack(side="left", fill="both", expand=True, pady=6)

        tab_filters = self._tabview.add("🔍  فلاتر الأصناف")
        tab_period = self._tabview.add("📅  الفترة الزمنية")
        tab_showrooms = self._tabview.add("🏬  المعارض")

        self._build_tab_filters(tab_filters)
        self._build_tab_period(tab_period)
        self._build_tab_showrooms(tab_showrooms)

    # ─── TAB: FILTERS ─────────────────────────────────────────
    def _build_tab_filters(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        info = ctk.CTkLabel(scroll,
            text="يمكن ترك أي فلتر فارغاً لتضمين جميع الأصناف. تدعم الفلاتر: الفاصلة `,` للعناصر المتعددة، والنجمة `*` والاستفهام `?` للبحث الجزئي.",
            font=ctk.CTkFont(APP_FONT, 11), text_color=BRAND_SLATE,
            wraplength=700, justify="right")
        info.pack(anchor="e", padx=8, pady=(4, 12))

        # Filter 1: Internal Reference
        card1 = SectionCard(scroll, title="كود الصنف  (Internal Reference)", icon="1️⃣")
        card1.pack(fill="x", padx=4, pady=(0, 8))
        ctk.CTkLabel(card1.content,
                     text="مثال: 4101-000000, 4101-000002, TS*",
                     font=ctk.CTkFont(APP_FONT, 10), text_color=BRAND_SLATE).pack(anchor="e")
        self._f_ref = ctk.CTkEntry(card1.content, placeholder_text="أكواد مفصولة بفاصلة...",
                                   height=36, font=ctk.CTkFont(APP_FONT, 12))
        self._f_ref.pack(fill="x", pady=(4, 0))

        # Filter 2: Barcode (unified)
        card2 = SectionCard(scroll, title="الباركود وباركود العبوات  (Barcode & Packages) — حقل موحد", icon="2️⃣")
        card2.pack(fill="x", padx=4, pady=(0, 8))
        ctk.CTkLabel(card2.content,
                     text="مثال: 628100*, 628???99, 123456789",
                     font=ctk.CTkFont(APP_FONT, 10), text_color=BRAND_SLATE).pack(anchor="e")
        self._f_barcode = ctk.CTkEntry(card2.content, placeholder_text="باركودات مفصولة بفاصلة...",
                                       height=36, font=ctk.CTkFont(APP_FONT, 12))
        self._f_barcode.pack(fill="x", pady=(4, 0))

        # Filter 3: Name
        card3 = SectionCard(scroll, title="اسم الصنف بالعربي أو الإنجليزي  (Product Name)", icon="3️⃣")
        card3.pack(fill="x", padx=4, pady=(0, 8))
        ctk.CTkLabel(card3.content,
                     text="مثال: عطر*, *PERFUME*, لوشن, صابون",
                     font=ctk.CTkFont(APP_FONT, 10), text_color=BRAND_SLATE).pack(anchor="e")
        self._f_name = ctk.CTkEntry(card3.content, placeholder_text="جزء من الاسم أو عدة أسماء...",
                                    height=36, font=ctk.CTkFont(APP_FONT, 12))
        self._f_name.pack(fill="x", pady=(4, 0))

        # Filter 4: Tags — autocomplete
        card4 = SectionCard(scroll, title="وسوم الأصناف  (Products / Tags) — اختيار تلقائي", icon="4️⃣")
        card4.pack(fill="x", padx=4, pady=(0, 8))
        ctk.CTkLabel(card4.content,
                     text="اكتب جزءاً من اسم الوسم ثم اضغط مسافة أو اختر من القائمة.",
                     font=ctk.CTkFont(APP_FONT, 10), text_color=BRAND_SLATE).pack(anchor="e")
        self._tag_selector = TagMultiSelect(card4.content, tags_list=self.all_tags,
                                            fg_color="transparent")
        self._tag_selector.pack(fill="x", pady=(4, 0))

        # Clear button
        ctk.CTkButton(scroll, text="🔄  تفريغ جميع حقول الفلاتر",
                      fg_color=BRAND_SLATE, hover_color=BRAND_SLATE_HOVER,
                      height=32, font=ctk.CTkFont(APP_FONT, 11),
                      command=self._clear_filters).pack(anchor="w", padx=8, pady=8)

    # ─── TAB: PERIOD ──────────────────────────────────────────
    def _build_tab_period(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        period_card = SectionCard(scroll, title="تحديد الفترة الزمنية للمبيعات", icon="📅")
        period_card.pack(fill="x", padx=4, pady=(4, 8))

        self._period_var = ctk.StringVar(value="all")
        periods = [
            ("all", "إجمالي كل الفترات (افتراضي)"),
            ("last_30_days", "آخر 30 يوماً"),
            ("last_60_days", "آخر 60 يوماً"),
            ("last_90_days", "آخر 90 يوماً"),
            ("this_year", f"العام الحالي ({datetime.now().year})"),
            ("custom", "فترة مخصصة..."),
        ]
        for val, label in periods:
            ctk.CTkRadioButton(period_card.content, text=label,
                               variable=self._period_var, value=val,
                               font=ctk.CTkFont(APP_FONT, 12),
                               command=self._on_period_change).pack(
                anchor="e", pady=4)

        # Custom date range (hidden by default)
        self._custom_dates = SectionCard(scroll, title="الفترة المخصصة", icon="🗓️")
        date_row = ctk.CTkFrame(self._custom_dates.content, fg_color="transparent")
        date_row.pack(fill="x")

        ctk.CTkLabel(date_row, text="من:", font=ctk.CTkFont(APP_FONT, 12)).pack(side="right", padx=6)
        self._date_from = ctk.CTkEntry(date_row, placeholder_text="YYYY-MM-DD", width=140, height=34)
        self._date_from.insert(0, (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"))
        self._date_from.pack(side="right", padx=4)

        ctk.CTkLabel(date_row, text="إلى:", font=ctk.CTkFont(APP_FONT, 12)).pack(side="right", padx=6)
        self._date_to = ctk.CTkEntry(date_row, placeholder_text="YYYY-MM-DD", width=140, height=34)
        self._date_to.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self._date_to.pack(side="right", padx=4)

    # ─── TAB: SHOWROOMS ───────────────────────────────────────
    def _build_tab_showrooms(self, parent):
        top_bar = ctk.CTkFrame(parent, fg_color="transparent")
        top_bar.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(top_bar, text="اختر المعارض المراد تضمينها في التقرير:",
                     font=ctk.CTkFont(APP_FONT, 13, "bold")).pack(side="right", padx=6)

        ctk.CTkButton(top_bar, text="⚙️  تعديل نوع المعارض (معارض / عناية)",
                      fg_color="#148F77", hover_color="#117864",
                      font=ctk.CTkFont(APP_FONT, 11, "bold"),
                      height=28, command=self._open_showroom_types_dialog).pack(side="left", padx=4)

        ctk.CTkButton(top_bar, text="إلغاء تحديد الكل", width=100,
                      fg_color=BRAND_SLATE, hover_color=BRAND_SLATE_HOVER,
                      height=28, font=ctk.CTkFont(APP_FONT, 11),
                      command=self._deselect_showrooms).pack(side="left", padx=4)

        ctk.CTkButton(top_bar, text="🌿 عناية فقط", width=95,
                      fg_color="#179B9B", hover_color="#148F77",
                      height=28, font=ctk.CTkFont(APP_FONT, 11),
                      command=self._select_only_care).pack(side="left", padx=4)

        ctk.CTkButton(top_bar, text="🏬 معارض فقط", width=95,
                      fg_color=BRAND_SLATE, hover_color=BRAND_SLATE_HOVER,
                      height=28, font=ctk.CTkFont(APP_FONT, 11),
                      command=self._select_only_showrooms).pack(side="left", padx=4)

        ctk.CTkButton(top_bar, text="✅ تحديد الكل", width=95,
                      fg_color=BRAND_GREEN, hover_color=BRAND_GREEN_HOVER,
                      height=28, font=ctk.CTkFont(APP_FONT, 11),
                      command=self._select_showrooms).pack(side="left", padx=4)

        self._sh_scroll = ctk.CTkScrollableFrame(parent, fg_color=("gray92", "#1A2230"),
                                                  corner_radius=8)
        self._sh_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._sh_loading = ctk.CTkLabel(self._sh_scroll,
                                         text="⏳ جاري استرجاع قائمة المعارض من Odoo...",
                                         font=ctk.CTkFont(APP_FONT, 13), text_color=BRAND_SLATE)
        self._sh_loading.pack(pady=24)

    # ─── FOOTER ───────────────────────────────────────────────
    def _build_footer(self, parent):
        footer = ctk.CTkFrame(parent, corner_radius=0,
                               fg_color=("gray90", "#0D1724"), height=88)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        # Progress bar
        self._progress = ctk.CTkProgressBar(footer, height=8, corner_radius=4)
        self._progress.pack(fill="x", padx=16, pady=(10, 2))
        self._progress.set(0)

        self._status_lbl = ctk.CTkLabel(footer, text="جاهز.",
                                         font=ctk.CTkFont(APP_FONT, 11),
                                         text_color=BRAND_SLATE)
        self._status_lbl.pack(anchor="e", padx=18)

        btn_row = ctk.CTkFrame(footer, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(2, 8))

        self._btn_open_dir = ctk.CTkButton(btn_row, text="📁 المجلد", width=100, height=34,
                                            fg_color=BRAND_SLATE, hover_color=BRAND_SLATE_HOVER,
                                            state="disabled", command=self._open_dir)
        self._btn_open_dir.pack(side="left", padx=4)

        self._btn_open = ctk.CTkButton(btn_row, text="📄 فتح الملف", width=120, height=34,
                                        fg_color=BRAND_GREEN, hover_color=BRAND_GREEN_HOVER,
                                        state="disabled", command=self._open_file)
        self._btn_open.pack(side="left", padx=4)

        self._btn_cancel = ctk.CTkButton(btn_row, text="⏹ إلغاء", width=100, height=34,
                                          fg_color=BRAND_RED, hover_color=BRAND_RED_HOVER,
                                          state="disabled", command=self._cancel_export)
        self._btn_cancel.pack(side="left", padx=4)

        self._btn_export = ctk.CTkButton(btn_row,
                                          text="🚀  بدء تصدير التقرير (Excel)",
                                          font=ctk.CTkFont(APP_FONT, 14, "bold"),
                                          fg_color=BRAND_BLUE, hover_color=BRAND_BLUE_HOVER,
                                          height=40, command=self._start_export)
        self._btn_export.pack(side="right", fill="x", expand=True, padx=(12, 0))

        # Bottom signature
        ctk.CTkLabel(parent,
                     text="تصميم وبرمجة: عبدالله الخطيب  |  Abdullah Al-Khatib © 2026  |  جميع الحقوق محفوظة",
                     font=ctk.CTkFont(APP_FONT, 10), text_color=("gray50", "#3D5168")).pack(pady=(0, 4))

    # ══════════════════════════════════════════════════════
    # 🔒 ADMIN PERMISSIONS DIALOG
    # ══════════════════════════════════════════════════════
    def _open_admin_dialog(self):
        dlg = SecurePasswordDialog(self,
                                   title="🔒 التحقق الإداري",
                                   prompt="أدخل كلمة مرور الإدارة للدخول إلى لوحة الصلاحيات:")
        pwd = dlg.get_input()
        if not pwd:
            return
        if not verify_admin_password(pwd):
            messagebox.showerror("خطأ", "كلمة المرور الإدارية غير صحيحة.")
            return
        self._show_permissions_editor()

    def _show_permissions_editor(self):
        win = ctk.CTkToplevel(self)
        win.title("🛡️ لوحة تحكم الصلاحيات — عبدالله الخطيب")
        win.geometry("680x700")
        win.minsize(620, 620)
        win.grab_set()
        win.lift()

        # Header
        hdr = ctk.CTkFrame(win, fg_color=(BRAND_PURPLE, "#2D1B69"), corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="🛡️  التحكم في الحقول المسموح بظهورها للمستخدمين",
                     font=ctk.CTkFont(APP_FONT, 15, "bold"), text_color="white").pack(pady=14, padx=20)

        ctk.CTkLabel(win,
                     text="✅ مفعّل = يظهر الحقل في التصدير  |  ❌ معطّل = يُحجب الحقل نهائياً",
                     font=ctk.CTkFont(APP_FONT, 12), text_color=BRAND_SLATE).pack(pady=(8, 4))

        scroll = ctk.CTkScrollableFrame(win, height=360, corner_radius=8,
                                         fg_color=("gray92", "#1A2230"))
        scroll.pack(fill="x", padx=20, pady=4)

        current_perms, _ = load_permissions()
        field_vars = {}

        # Group fields visually
        groups = [
            ("💰 الأسعار", ["Cost", "Sales Price", "هامش الربح (%)", "Shati Price", "SO Price", "Pos Minimum Price"]),
            ("📦 المخزون والمبيعات الإجمالية", ["Quantity On Hand", "365d Sold"]),
            ("🏭 بيانات الموردين", ["Vendors", "Vendors/Price", "Vendors/Discount (%)",
                                   "Vendors/Discounted Price", "Vendors/Last Purchase",
                                   "Vendors/Last Updated on", "Last Received Qty"]),
            ("🏬 المعارض التفصيلية", ["Showrooms_OnHand", "Showrooms_Sold"]),
            ("📈 تحليلات وتوصيات المخزون", ["أيام التغطية", "حالة الصنف", "الطلب المقترح (60 يوم)", "قيمة الطلب المقترح", "توصيات المناقلة"]),
        ]

        field_label_map = {f_id: f_label for f_id, f_label in ALL_PROTECTED_FIELDS}

        for group_title, field_ids in groups:
            grp_header = ctk.CTkFrame(scroll, fg_color=("gray85", "#253047"), corner_radius=6)
            grp_header.pack(fill="x", padx=4, pady=(8, 2))
            ctk.CTkLabel(grp_header, text=group_title,
                         font=ctk.CTkFont(APP_FONT, 12, "bold"),
                         text_color=(BRAND_PURPLE, "#A78BFA")).pack(anchor="e", padx=12, pady=4)

            grp_content = ctk.CTkFrame(scroll, fg_color="transparent")
            grp_content.pack(fill="x", padx=12, pady=2)

            for f_id in field_ids:
                var = ctk.BooleanVar(value=current_perms.get(f_id, False))
                field_vars[f_id] = var
                ctk.CTkCheckBox(grp_content,
                                text=field_label_map.get(f_id, f_id),
                                variable=var,
                                font=ctk.CTkFont(APP_FONT, 12)).pack(anchor="e", padx=20, pady=4)

        # Quick actions
        qa_frame = ctk.CTkFrame(win, fg_color="transparent")
        qa_frame.pack(fill="x", padx=20, pady=(4, 0))
        ctk.CTkButton(qa_frame, text="✅ تفعيل الكل", width=120, height=28,
                      fg_color=BRAND_GREEN, hover_color=BRAND_GREEN_HOVER,
                      command=lambda: [v.set(True) for v in field_vars.values()]).pack(side="right", padx=4)
        ctk.CTkButton(qa_frame, text="❌ تعطيل الكل", width=120, height=28,
                      fg_color=BRAND_RED, hover_color=BRAND_RED_HOVER,
                      command=lambda: [v.set(False) for v in field_vars.values()]).pack(side="right", padx=4)

        # Password change
        pass_card = SectionCard(win, title="تغيير كلمة مرور الإدارة (اتركها فارغة إذا لا ترغب بالتغيير)", icon="🔑")
        pass_card.pack(fill="x", padx=20, pady=(8, 0))
        new_pass = ctk.CTkEntry(pass_card.content, show="●", height=34,
                                placeholder_text="كلمة المرور الجديدة...",
                                font=ctk.CTkFont("Consolas", 13))
        new_pass.pack(fill="x")

        # Save button
        def _save():
            updated = {f_id: var.get() for f_id, var in field_vars.items()}
            np = new_pass.get().strip() or None
            if np and len(np) < 6:
                messagebox.showwarning("تنبيه", "كلمة المرور الجديدة يجب أن تكون 6 أحرف على الأقل.")
                return
            save_permissions(updated, new_admin_password=np)
            messagebox.showinfo("تم الحفظ", "🎉 تم حفظ الصلاحيات وتطبيقها بنجاح على هذا الجهاز!")
            win.destroy()
            self._build_main_ui()

        ctk.CTkButton(win, text="💾  حفظ الصلاحيات والإعدادات المشفرة",
                      font=ctk.CTkFont(APP_FONT, 13, "bold"),
                      fg_color=BRAND_PURPLE, hover_color=BRAND_PURPLE_HOVER,
                      height=40, command=_save).pack(fill="x", padx=20, pady=12)

    # ══════════════════════════════════════════════════════
    # ⚙️ HELPERS
    # ══════════════════════════════════════════════════════
    def _change_theme(self, choice):
        theme = "Light" if "فاتح" in choice else "Dark"
        ctk.set_appearance_mode(theme)
        self.settings["theme"] = theme
        save_settings(self.settings)

    def _on_period_change(self):
        if self._period_var.get() == "custom":
            self._custom_dates.pack(fill="x", padx=4, pady=(0, 8))
        else:
            self._custom_dates.pack_forget()

    def _browse_path(self):
        f = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel Files", "*.xlsx")],
            initialfile=f"تقرير_العسلي_{datetime.now().strftime('%Y%m%d')}.xlsx"
        )
        if f:
            self._path_entry.delete(0, "end")
            self._path_entry.insert(0, f)

    def _clear_filters(self):
        self._f_ref.delete(0, "end")
        self._f_barcode.delete(0, "end")
        self._f_name.delete(0, "end")
        self._tag_selector._clear_all()

    def _select_showrooms(self):
        for v in self.showroom_vars.values():
            v.set(True)

    def _deselect_showrooms(self):
        for v in self.showroom_vars.values():
            v.set(False)

    def _select_only_showrooms(self):
        custom_types = load_showroom_types()
        for s in self.showrooms:
            is_care = (get_showroom_category(s['code'], s['name'], custom_types) == 'care')
            var = self.showroom_vars.get(s['id'])
            if var:
                var.set(not is_care)

    def _select_only_care(self):
        custom_types = load_showroom_types()
        for s in self.showrooms:
            is_care = (get_showroom_category(s['code'], s['name'], custom_types) == 'care')
            var = self.showroom_vars.get(s['id'])
            if var:
                var.set(is_care)

    def _open_showroom_types_dialog(self):
        """Interactive modal to classify showrooms as 'معارض' or 'عناية'."""
        if not self.showrooms:
            messagebox.showinfo("تنبيه", "جاري تحميل قائمة المعارض، يرجى الانتظار لحظات...")
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title("🏢 تعديل تصنيف فروع الشركة (معارض / عناية)")
        dlg.geometry("600x640")
        dlg.resizable(True, True)
        dlg.grab_set()

        # Header
        hdr = ctk.CTkFrame(dlg, fg_color=BRAND_DARK, corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="🏢  تصنيف فروع الشركة (معارض / عناية)",
                     font=ctk.CTkFont(APP_FONT, 14, "bold"), text_color="white").pack(anchor="e", padx=16, pady=(10, 2))
        ctk.CTkLabel(hdr, text="حدد نوع كل فرع (معارض أو عناية). فروع العناية تُلوَّن باللون الفيروزي الفاتح في التقرير.",
                     font=ctk.CTkFont(APP_FONT, 10), text_color="gray70").pack(anchor="e", padx=16, pady=(0, 10))

        # Current types
        current_types = load_showroom_types()
        var_map = {}

        # Scrollable table
        scroll = ctk.CTkScrollableFrame(dlg, fg_color=("gray95", "#141D29"))
        scroll.pack(fill="both", expand=True, padx=12, pady=8)

        # Table Header
        th = ctk.CTkFrame(scroll, fg_color=BRAND_BLUE, corner_radius=4)
        th.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(th, text="اسم المعرض / الفرع", font=ctk.CTkFont(APP_FONT, 11, "bold"), text_color="white").pack(side="right", padx=14, pady=5)
        ctk.CTkLabel(th, text="نوع الفرع", font=ctk.CTkFont(APP_FONT, 11, "bold"), text_color="white").pack(side="left", padx=45, pady=5)

        for s in self.showrooms:
            code = s['code']
            name = s['name']
            current_cat = get_showroom_category(code, name, current_types)

            row_frame = ctk.CTkFrame(scroll, fg_color=("white", "#1B2838"), corner_radius=4)
            row_frame.pack(fill="x", pady=2)

            lbl_text = f"[{code}]  {name}"
            ctk.CTkLabel(row_frame, text=lbl_text, font=ctk.CTkFont(APP_FONT, 11)).pack(side="right", padx=10, pady=6)

            seg_var = ctk.StringVar(value="عناية" if current_cat == "care" else "معارض")
            var_map[code] = (seg_var, name)

            seg = ctk.CTkSegmentedButton(
                row_frame,
                values=["معارض", "عناية"],
                variable=seg_var,
                font=ctk.CTkFont(APP_FONT, 10, "bold"),
                selected_color="#179B9B",
                selected_hover_color="#148F77",
                width=140
            )
            seg.pack(side="left", padx=10, pady=4)

        # Bottom buttons
        btn_bar = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_bar.pack(fill="x", padx=12, pady=10)

        def _reset_default():
            for code, (var, name) in var_map.items():
                is_care = is_default_care_showroom(code, name)
                var.set("عناية" if is_care else "معارض")

        def _save():
            new_types = {}
            for code, (var, name) in var_map.items():
                cat = "care" if var.get() == "عناية" else "showroom"
                new_types[code] = cat
                new_types[name] = cat
            save_showroom_types(new_types)
            self._populate_showrooms()
            dlg.destroy()
            messagebox.showinfo("تم الحفظ", "✅ تم حفظ تصنيفات المعارض بنجاح!")

        ctk.CTkButton(btn_bar, text="🔄 استعادة الافتراضي",
                      fg_color=BRAND_SLATE, hover_color=BRAND_SLATE_HOVER,
                      font=ctk.CTkFont(APP_FONT, 11),
                      command=_reset_default).pack(side="left", padx=4)

        ctk.CTkButton(btn_bar, text="❌ إلغاء", width=80,
                      fg_color=BRAND_RED, hover_color=BRAND_RED_HOVER,
                      font=ctk.CTkFont(APP_FONT, 11),
                      command=dlg.destroy).pack(side="left", padx=4)

        ctk.CTkButton(btn_bar, text="💾  حفظ التصنيفات",
                      fg_color=BRAND_GREEN, hover_color=BRAND_GREEN_HOVER,
                      font=ctk.CTkFont(APP_FONT, 12, "bold"),
                      command=_save).pack(side="right", fill="x", expand=True, padx=(10, 0))

    def _load_showrooms_async(self):
        def _worker():
            try:
                self.showrooms = get_active_showrooms()
                self.after(0, self._populate_showrooms)
            except Exception as e:
                self.after(0, lambda: self._sh_loading.configure(
                    text=f"⚠️ تعذر جلب المعارض:\n{e}"))
        threading.Thread(target=_worker, daemon=True).start()

    def _populate_showrooms(self):
        self._sh_loading.pack_forget()
        self.showroom_vars.clear()
        for w in self._sh_scroll.winfo_children():
            w.destroy()

        custom_types = load_showroom_types()

        # Split showrooms into Care and Standard Showrooms
        care_showrooms = []
        std_showrooms = []
        for s in self.showrooms:
            if get_showroom_category(s['code'], s['name'], custom_types) == 'care':
                care_showrooms.append(s)
            else:
                std_showrooms.append(s)

        # 1. Care Showrooms section
        if care_showrooms:
            care_header = ctk.CTkFrame(self._sh_scroll, fg_color=("#D1F2EB", "#0E3A36"), corner_radius=6)
            care_header.pack(fill="x", padx=6, pady=(4, 6))
            ctk.CTkLabel(care_header, text=f"🌿  فروع ومراكز العناية ({len(care_showrooms)} فروع) — تظهر بخلفية فيروزية في التقرير",
                         font=ctk.CTkFont(APP_FONT, 12, "bold"), text_color=("#0E6251", "#76D7C4")).pack(anchor="e", padx=12, pady=6)

            care_grid = ctk.CTkFrame(self._sh_scroll, fg_color="transparent")
            care_grid.pack(fill="x", padx=6, pady=(0, 10))

            row, col = 0, 0
            for s in care_showrooms:
                var = ctk.BooleanVar(value=True)
                self.showroom_vars[s['id']] = var
                chk = ctk.CTkCheckBox(care_grid,
                                       text=f"[{s['code']}] {s['name']}",
                                       variable=var,
                                       fg_color="#179B9B", hover_color="#148F77",
                                       font=ctk.CTkFont(APP_FONT, 11, "bold"))
                chk.grid(row=row, column=col, padx=12, pady=5, sticky="e")
                col += 1
                if col >= 3:
                    col = 0
                    row += 1

        # 2. Standard Showrooms section
        if std_showrooms:
            std_header = ctk.CTkFrame(self._sh_scroll, fg_color=("gray85", "#1B2A3D"), corner_radius=6)
            std_header.pack(fill="x", padx=6, pady=(4, 6))
            ctk.CTkLabel(std_header, text=f"🏬  المعارض الرئيسية ({len(std_showrooms)} معرض)",
                         font=ctk.CTkFont(APP_FONT, 12, "bold"), text_color=BRAND_BLUE).pack(anchor="e", padx=12, pady=6)

            std_grid = ctk.CTkFrame(self._sh_scroll, fg_color="transparent")
            std_grid.pack(fill="x", padx=6, pady=(0, 8))

            row, col = 0, 0
            for s in std_showrooms:
                var = ctk.BooleanVar(value=True)
                self.showroom_vars[s['id']] = var
                chk = ctk.CTkCheckBox(std_grid,
                                       text=f"[{s['code']}] {s['name']}",
                                       variable=var,
                                       font=ctk.CTkFont(APP_FONT, 11))
                chk.grid(row=row, column=col, padx=12, pady=4, sticky="e")
                col += 1
                if col >= 3:
                    col = 0
                    row += 1

    def _load_tags_async(self):
        def _worker():
            try:
                tags = get_all_product_tags()
                self.all_tags = tags
                self.after(0, lambda: self._tag_selector.set_tags_list(tags))
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    # ══════════════════════════════════════════════════════
    # 🚀 EXPORT
    # ══════════════════════════════════════════════════════
    def _start_export(self):
        if self.is_exporting:
            return

        out_path = self._path_entry.get().strip()
        if not out_path:
            messagebox.showerror("خطأ", "يرجى تحديد مسار حفظ الملف.")
            return

        selected = [sid for sid, v in self.showroom_vars.items() if v.get()]

        col_opts = {
            'basic_info': self._col_basic.get(),
            'pricing': self._col_price.get(),
            'totals': self._col_totals.get(),
            'vendors': self._col_vendors.get(),
            'showrooms': self._col_showrooms.get() and bool(selected),
            'analytics': self._col_analytics.get()
        }

        period = self._period_var.get()
        c_from = self._date_from.get().strip() if period == "custom" else None
        c_to = self._date_to.get().strip() if period == "custom" else None

        f_ref = self._f_ref.get().strip() or None
        f_bc = self._f_barcode.get().strip() or None
        f_name = self._f_name.get().strip() or None
        f_tags = self._tag_selector.get_selected_tags()

        self.is_exporting = True
        self._cancel_flag = False
        self._btn_export.configure(state="disabled", text="⏳  جاري التصدير...")
        self._btn_cancel.configure(state="normal")
        self._btn_open.configure(state="disabled")
        self._btn_open_dir.configure(state="disabled")
        self._progress.set(0)

        def _cb(pct, text):
            self.after(0, lambda: self._update_progress(pct, text))

        def _run():
            try:
                res = generate_report(
                    selected_showroom_ids=selected,
                    column_options=col_opts,
                    sales_period=period,
                    custom_date_from=c_from,
                    custom_date_to=c_to,
                    movement_filter=self._movement_var.get(),
                    filter_internal_ref=f_ref,
                    filter_barcode=f_bc,
                    filter_name=f_name,
                    filter_tags=f_tags,
                    output_path=out_path,
                    progress_callback=_cb,
                    is_cancelled=lambda: self._cancel_flag
                )
                self.last_exported_file = res['output_path']
                self.after(0, lambda: self._on_success(res))
            except InterruptedError:
                self.after(0, lambda: self._on_cancelled())
            except Exception as e:
                self.after(0, lambda: self._on_error(e))

        threading.Thread(target=_run, daemon=True).start()

    def _update_progress(self, pct, text):
        self._progress.set(pct / 100.0)
        self._status_lbl.configure(text=text)

    def _on_success(self, res):
        self.is_exporting = False
        self._btn_export.configure(state="normal", text="🚀  بدء تصدير التقرير (Excel)")
        self._btn_cancel.configure(state="disabled")
        self._btn_open.configure(state="normal")
        self._btn_open_dir.configure(state="normal")
        self._status_lbl.configure(text=f"✅ اكتمل | {res['total_rows']:,} صنف | {res['total_time']}ث")
        messagebox.showinfo("اكتمل التصدير",
            f"🎉 تم تصدير التقرير بنجاح!\n\n"
            f"• عدد الأصناف المطابقة: {res['total_rows']:,}\n"
            f"• عدد الأعمدة: {res['total_columns']}\n"
            f"• الوقت المستغرق: {res['total_time']} ثانية\n\n"
            f"📁 الملف:\n{res['output_path']}")

    def _on_error(self, err):
        self.is_exporting = False
        self._btn_export.configure(state="normal", text="🚀  بدء تصدير التقرير (Excel)")
        self._btn_cancel.configure(state="disabled")
        self._status_lbl.configure(text="❌ حدث خطأ أثناء التصدير.")
        messagebox.showerror("خطأ في التصدير", f"حدث خطأ:\n\n{err}")

    def _on_cancelled(self):
        self.is_exporting = False
        self._btn_export.configure(state="normal", text="🚀  بدء تصدير التقرير (Excel)")
        self._btn_cancel.configure(state="disabled")
        self._status_lbl.configure(text="⏹ تم إلغاء التصدير.")

    def _cancel_export(self):
        self._cancel_flag = True
        self._status_lbl.configure(text="⏳ جاري إلغاء العملية...")
        self._btn_cancel.configure(state="disabled")

    def _open_file(self):
        if self.last_exported_file and os.path.exists(self.last_exported_file):
            os.startfile(self.last_exported_file)

    def _open_dir(self):
        if self.last_exported_file:
            d = os.path.dirname(self.last_exported_file)
            if os.path.exists(d):
                os.startfile(d)


# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = OdooReportApp()
    app.mainloop()
