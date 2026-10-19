"""
OdooReportExporter – Main GUI (v1.00 Standard)
Designed & developed by: عبدالله الخطيب (Abdullah Al-Khatib)
"""

APP_VERSION = "v1.00"

import os
import sys
import json
import threading
import subprocess
from datetime import datetime, timedelta

import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from licensing import (
    get_machine_id, is_activated, activate_device, deactivate_device,
    register_or_update_device_in_odoo, fetch_device_status_from_odoo,
    show_device_license_dialog
)
from permissions import ALL_PROTECTED_FIELDS, load_permissions, save_permissions, verify_admin_password, sync_permissions_from_odoo
from auto_updater import check_and_prompt_update_async
from exporter_engine import get_active_showrooms, get_all_warehouses, get_all_product_tags, get_all_pricelists, generate_report
from pos_discount_engine import generate_pos_discount_report
from purchase_report_engine import get_all_vendors, generate_purchase_intelligence_report
from showroom_config import get_showroom_category, load_showroom_types, save_showroom_types, is_default_care_showroom


# ─────────────────────────────────────────────────────────
# 🎨 Premium Design System — Professional SaaS Palette
# ─────────────────────────────────────────────────────────
BRAND_GOLD = "#E5B31A"
BRAND_GOLD_SOFT = "#D4A01744"
BRAND_BLUE = "#2563EB"
BRAND_BLUE_HOVER = "#1D4ED8"
BRAND_BLUE_GLOW = "#3B82F6"
BRAND_GREEN = "#16A34A"
BRAND_GREEN_HOVER = "#15803D"
BRAND_RED = "#EF4444"
BRAND_RED_HOVER = "#DC2626"
BRAND_PURPLE = "#8B5CF6"
BRAND_PURPLE_HOVER = "#7C3AED"
BRAND_SLATE = "#64748B"
BRAND_SLATE_HOVER = "#475569"
BRAND_DARK = ("#1E293B", "#0F172A")

# Deep background layers
BG_DEEPEST = "#060D19"
BG_DEEP = "#0A1128"
BG_BASE = "#0F172A"
BG_ELEVATED = "#1E293B"
BG_CARD = "#172033"
BG_CARD_LIGHT = "#F8FAFC"

# Border & separator colors
BORDER_SUBTLE = ("#E2E8F0", "#1E3A5F")
BORDER_GLOW = ("#CBD5E1", "#2563EB33")

# Header gradient colors
HDR_BG = ("#1E40AF", "#070E1C")
HDR_TITLE_COLOR = "#F1F5F9"

# Footer
FOOTER_BG = ("#F1F5F9", "#0B1222")

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
    def __init__(self, master, tags_list=None, placeholder_text=None, empty_text=None, chips_height=130, chip_color=BRAND_BLUE, **kwargs):
        super().__init__(master, **kwargs)
        self._all_tags = self._extract_tag_names(tags_list)
        self._selected = []
        self._dropdown_open = False
        self._dropdown_items = []
        self._empty_text = empty_text or "لا توجد وسوم محددة بعد"
        self._chip_color = chip_color

        # ─ Top: search entry ─
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=0, pady=0)

        self._entry = ctk.CTkEntry(
            top,
            placeholder_text=placeholder_text or "ابحث عن وسم... (اكتب للبحث أو اضغط Enter / مسافة للاختيار)",
            height=36,
            font=ctk.CTkFont(APP_FONT, 12)
        )
        self._entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._entry.bind("<KeyRelease>", self._on_key)
        self._entry.bind("<space>", self._on_space)
        self._entry.bind("<Return>", self._on_enter)
        self._entry.bind("<FocusIn>", self._on_key)

        ctk.CTkButton(top, text="➕ إضافة", width=72, height=36,
                      fg_color=self._chip_color, hover_color=BRAND_BLUE_HOVER,
                      font=ctk.CTkFont(APP_FONT, 11, "bold"), command=self._on_enter).pack(side="left", padx=(0, 4))

        ctk.CTkButton(top, text="✕ مسح الكل", width=85, height=36,
                      fg_color=BRAND_SLATE, hover_color=BRAND_SLATE_HOVER,
                      font=ctk.CTkFont(APP_FONT, 11), command=self._clear_all).pack(side="left")

        # ─ Dropdown container ─
        self._dropdown_container = ctk.CTkFrame(self, fg_color="transparent")
        self._dropdown_container.pack(fill="x")

        self._dropdown_frame = ctk.CTkScrollableFrame(self._dropdown_container, height=110, fg_color=("white", "#1E293B"),
                                                      border_width=1, border_color=("#CBD5E1", "#334155"),
                                                      corner_radius=6)

        # ─ Chips area ─
        self._chips_frame = ctk.CTkScrollableFrame(self, height=chips_height, orientation="horizontal",
                                                   fg_color=("gray93", "#1A2230"),
                                                   corner_radius=6)
        self._chips_frame.pack(fill="both", expand=True, pady=(4, 0))

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
        if event and getattr(event, "keysym", "") in ("Return", "Escape"):
            return
        raw_text = self._entry.get().strip().rstrip(" ")
        if not raw_text:
            self._hide_dropdown()
            return
        last_tok = raw_text.replace("،", ",").split(",")[-1].strip()
        if not last_tok:
            self._hide_dropdown()
            return
        stem = last_tok.replace("*", "").replace("?", "").strip().lower()
        matches = []
        if stem:
            matches = [
                t for t in self._all_tags
                if (stem in t.lower() or stem in t.lower().replace("[", "").replace("]", ""))
                and t not in self._selected
            ][:40]
        if matches or ("*" in last_tok or "?" in last_tok):
            self._refresh_dropdown(matches, wildcard_token=last_tok if ("*" in last_tok or "?" in last_tok or "," in raw_text or "،" in raw_text) else None)
            self._show_dropdown()
        else:
            self._hide_dropdown()

    def _on_enter(self, event=None):
        """Add typed token(s) or wildcard pattern(s) directly as chips when pressing Enter or clicking Add."""
        raw_text = self._entry.get().strip()
        if not raw_text:
            return "break"
        tokens = [t.strip() for t in raw_text.replace("،", ",").split(",") if t.strip()]
        for tok in tokens:
            if "*" in tok or "?" in tok or len(tokens) > 1:
                if tok not in self._selected:
                    self._selected.append(tok)
            else:
                exact = [t for t in self._all_tags if t.lower() == tok.lower() and t not in self._selected]
                if exact:
                    self._selected.append(exact[0])
                elif tok not in self._selected:
                    self._selected.append(tok)
        self._redraw_chips()
        self._entry.delete(0, "end")
        self._hide_dropdown()
        return "break"

    def _on_space(self, event=None):
        """Auto-select matching tag or add wildcard/comma pattern on space press."""
        text = self._entry.get().strip().rstrip(" ")
        if not text:
            return
        if any(ch in text for ch in ("*", "?", ",", "،")):
            return self._on_enter(event)
        matches = [t for t in self._all_tags if text.lower() in t.lower() and t not in self._selected]
        if matches:
            self._add_tag(matches[0])
        else:
            self._add_tag(text)
        return "break"  # prevent space insertion

    def _refresh_dropdown(self, items, wildcard_token=None):
        for w in self._dropdown_frame.winfo_children():
            w.destroy()
        self._dropdown_items = []
        if wildcard_token:
            raw_all = self._entry.get().strip()
            w_btn = ctk.CTkButton(
                self._dropdown_frame,
                text=f"➕ اعتماد الفلتر المخصص: {raw_all}  (أو اضغط Enter)",
                height=30, anchor="e",
                font=ctk.CTkFont(APP_FONT, 11, "bold"),
                fg_color=(BRAND_EMERALD + "22", BRAND_EMERALD + "33"),
                hover_color=(BRAND_EMERALD + "44", BRAND_EMERALD + "66"),
                text_color=(BRAND_EMERALD, "#34D399"),
                command=self._on_enter
            )
            w_btn.pack(fill="x", padx=4, pady=(2, 3))
            self._dropdown_items.append(w_btn)
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
            ctk.CTkLabel(self._chips_frame, text=self._empty_text,
                         text_color=BRAND_SLATE, font=ctk.CTkFont(APP_FONT, 11)).pack(side="right", padx=6)
            return
        for tag_name in self._selected:
            chip = ctk.CTkFrame(self._chips_frame, fg_color=(self._chip_color, self._chip_color),
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
        """Returns comma-separated string of selected tags AND any pending text typed in the entry field."""
        combined = list(self._selected)
        raw_entry = self._entry.get().strip()
        if raw_entry:
            for tok in raw_entry.replace("،", ",").split(","):
                t = tok.strip()
                if t and t not in combined:
                    combined.append(t)
        return ", ".join(combined) if combined else None

    def set_tags_list(self, tags_list):
        """Update available tags list (after fetching from Odoo)."""
        self._all_tags = self._extract_tag_names(tags_list)
        text = self._entry.get().strip().lower().rstrip(" ")
        if text:
            self._on_key()


# ─────────────────────────────────────────────────────────
# 📊 Section Card (visual grouping widget) — Premium
# ─────────────────────────────────────────────────────────
class SectionCard(ctk.CTkFrame):
    """A titled card for visually grouping content sections — premium glass style."""
    def __init__(self, master, title="", icon="", **kwargs):
        kwargs.setdefault("corner_radius", 12)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", BORDER_SUBTLE)
        super().__init__(master, **kwargs)

        if title:
            header = ctk.CTkFrame(self, fg_color="transparent")
            header.pack(fill="x", padx=14, pady=(10, 0))
            ctk.CTkLabel(header, text=f"{icon}  {title}" if icon else title,
                         font=ctk.CTkFont(APP_FONT, 13, "bold"),
                         text_color=(BRAND_BLUE, BRAND_BLUE_GLOW)).pack(side="right")

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(fill="both", expand=True, padx=14, pady=(6, 10))


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
        self._center_window(1120, 720)
        self.minsize(960, 580)

        self.showrooms = []
        self.warehouses = []
        self.all_tags = []
        self.all_vendors = []
        self.showroom_vars = {}
        self.warehouse_vars = {}
        self.is_exporting = False
        self.last_exported_file = None
        self.last_exported_pdf = None
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
        self._center_window(660, 640)
        self.resizable(False, False)
        for w in self.winfo_children():
            w.destroy()

        outer = ctk.CTkFrame(self, fg_color=(BG_CARD_LIGHT, BG_DEEP), corner_radius=0)
        outer.pack(fill="both", expand=True)

        # Top Gold accent bar
        bar = ctk.CTkFrame(outer, fg_color=BRAND_GOLD, height=4, corner_radius=0)
        bar.pack(fill="x")

        # Main Card
        card = ctk.CTkFrame(outer, corner_radius=16, fg_color=("white", BG_ELEVATED),
                            border_width=1, border_color=BORDER_SUBTLE)
        card.pack(fill="both", expand=True, padx=28, pady=(18, 10))

        # Header with Icon
        header_frame = ctk.CTkFrame(card, fg_color="transparent")
        header_frame.pack(fill="x", padx=24, pady=(20, 8))

        ctk.CTkLabel(header_frame, text="🔐", font=ctk.CTkFont(size=42)).pack()
        ctk.CTkLabel(header_frame, text="تفعيل وترخيص البرنامج",
                     font=ctk.CTkFont(APP_FONT, 20, "bold"),
                     text_color=(BRAND_BLUE, BRAND_BLUE_GLOW)).pack(pady=(6, 2))
        ctk.CTkLabel(header_frame, text="هذا البرنامج مخصص ومحمي للأجهزة المعتمدة فقط.",
                     font=ctk.CTkFont(APP_FONT, 11), text_color=BRAND_SLATE).pack()

        sep = ctk.CTkFrame(card, height=1, fg_color=BORDER_SUBTLE)
        sep.pack(fill="x", padx=24, pady=(8, 14))

        # 1. Machine ID Section
        mid_box = ctk.CTkFrame(card, fg_color=("gray94", BG_CARD), corner_radius=12,
                               border_width=1, border_color=BORDER_SUBTLE)
        mid_box.pack(fill="x", padx=24, pady=(0, 14))

        ctk.CTkLabel(mid_box, text="📌 معرّف هذا الجهاز (Machine ID) الخاص بك:",
                     font=ctk.CTkFont(APP_FONT, 12, "bold"),
                     text_color=(BRAND_BLUE, "#93C5FD")).pack(anchor="e", padx=16, pady=(10, 4))

        self._current_mid = get_machine_id()
        mid_row = ctk.CTkFrame(mid_box, fg_color="transparent")
        mid_row.pack(fill="x", padx=16, pady=(0, 8))

        self._mid_entry = ctk.CTkEntry(mid_row, font=ctk.CTkFont("Consolas", 15, "bold"),
                                       text_color=(BRAND_BLUE, BRAND_BLUE_GLOW), justify="center", height=40,
                                       corner_radius=8)
        self._mid_entry.insert(0, self._current_mid)
        self._mid_entry.configure(state="readonly")
        self._mid_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctk.CTkButton(mid_row, text="📋 نسخ المعرّف", width=120, height=40,
                      corner_radius=8,
                      font=ctk.CTkFont(APP_FONT, 12, "bold"),
                      fg_color=BRAND_BLUE, hover_color=BRAND_BLUE_HOVER,
                      command=self._copy_machine_id).pack(side="left")

        ctk.CTkLabel(mid_box, text="انسخ المعرّف أعلاه وأرسله للمسؤول (الأستاذ عبدالله الخطيب) للحصول على مفتاح التفعيل.",
                     font=ctk.CTkFont(APP_FONT, 10), text_color=BRAND_SLATE).pack(anchor="e", padx=16, pady=(0, 10))

        # 2. Device Name Section (Optional description for Odoo registry)
        name_box = ctk.CTkFrame(card, fg_color="transparent")
        name_box.pack(fill="x", padx=24, pady=(0, 10))

        ctk.CTkLabel(name_box, text="🏢 اسم المعرض / الموظف / المحطة (للتعريف في Odoo):",
                     font=ctk.CTkFont(APP_FONT, 11, "bold")).pack(anchor="e", pady=(0, 4))

        self._dev_name_entry = ctk.CTkEntry(name_box, placeholder_text="مثال: إدارة المشتريات - لابتوب 1",
                                            font=ctk.CTkFont(APP_FONT, 12), justify="right", height=38,
                                            corner_radius=8)
        default_dname = os.environ.get("COMPUTERNAME", "")
        if default_dname:
            self._dev_name_entry.insert(0, f"جهاز ({default_dname})")
        self._dev_name_entry.pack(fill="x")

        # 3. Activation Key Entry Section
        key_box = ctk.CTkFrame(card, fg_color="transparent")
        key_box.pack(fill="x", padx=24, pady=(0, 12))

        ctk.CTkLabel(key_box, text="🔑 أدخل مفتاح التفعيل (Activation Key):",
                     font=ctk.CTkFont(APP_FONT, 12, "bold")).pack(anchor="e", pady=(0, 6))

        self._act_entry = ctk.CTkEntry(key_box, placeholder_text="XXXX-XXXX-XXXX-XXXX (بشرطات أو بدون)",
                                       font=ctk.CTkFont("Consolas", 15, "bold"), justify="center", height=44,
                                       corner_radius=8)
        self._act_entry.pack(fill="x", pady=(0, 12))
        self._act_entry.bind("<Return>", lambda _: self._do_activate())

        ctk.CTkButton(key_box, text="🚀  تفعيل البرنامج والبدء بالاستخدام",
                      font=ctk.CTkFont(APP_FONT, 14, "bold"),
                      fg_color=BRAND_GREEN, hover_color=BRAND_GREEN_HOVER,
                      corner_radius=10,
                      height=46, command=self._do_activate).pack(fill="x")

        # Footer Signature
        ctk.CTkLabel(outer, text="✨ تم التصميم والتطوير بواسطة: عبدالله الخطيب",
                     font=ctk.CTkFont(APP_FONT, 11, "bold"),
                     text_color=BRAND_GOLD).pack(side="bottom", pady=(4, 10))

    def _copy_machine_id(self):
        self.clipboard_clear()
        self.clipboard_append(self._current_mid)
        messagebox.showinfo("تم النسخ", f"تم نسخ معرّف الجهاز للحافظة بنجاح:\n\n{self._current_mid}\n\nأرسله للمسؤول للحصول على مفتاح التفعيل.")

    def _do_activate(self):
        key = self._act_entry.get().strip().upper()
        if not key:
            messagebox.showwarning("تنبيه", "يرجى إدخال مفتاح التفعيل أولاً.")
            return
        d_name = self._dev_name_entry.get().strip() if hasattr(self, '_dev_name_entry') else ""
        ok, msg = activate_device(key, device_name=d_name, app_name="OdooReportExporter", app_version=APP_VERSION)
        if ok:
            messagebox.showinfo("نجاح التفعيل", "🎉 تم تفعيل البرنامج بنجاح لهذا الجهاز!\nتم تسجيل الجهاز في نظام التراخيص المركزي Odoo.")
            self._center_window(1120, 720)
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

        # ─── BOTTOM PROGRESS & ACTION BAR (built BEFORE content so pack side=bottom gets space) ───
        self._build_footer(main_container)

        # ─── CONTENT AREA (Sidebar + Tabs) ────────────────────
        content = ctk.CTkFrame(main_container, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=10, pady=(0, 4))

        # Build sidebar + tabview side by side
        self._build_sidebar(content)
        self._build_tabs(content)

        # Check authorization with central Odoo registry in background
        self._check_device_status_with_odoo()

        # Async loads
        self._load_showrooms_async()
        self._load_tags_async()
        self._load_vendors_async()
        self._load_pricelists_async()

    def _check_device_status_with_odoo(self):
        """Checks if device is authorized in Odoo registry. Only shows sync button if NOT added."""
        def worker():
            try:
                st = fetch_device_status_from_odoo()
                if st == "blocked":
                    self.after(0, self._handle_remote_device_blocked)
                elif st == "not_found":
                    # Device is NOT in Odoo -> show warning sync button
                    self.after(0, self._show_license_sync_button)
                elif st == "active":
                    # Device is ALREADY licensed in Odoo -> ensure button is hidden & update heartbeat
                    self.after(0, self._hide_license_sync_button)
                    register_or_update_device_in_odoo(
                        app_name="OdooReportExporter",
                        app_version=APP_VERSION
                    )
                    # Sync remote permissions and admin password set by Abdullah Al-Khatib
                    updated, new_perms = sync_permissions_from_odoo()
                    if updated:
                        self.permissions = new_perms
                        self.after(0, self._refresh_permission_buttons)

                    # Check for updates in background
                    check_and_prompt_update_async(self, "OdooReportExporter", APP_VERSION)
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _refresh_permission_buttons(self):
        """Refreshes buttons gated by permissions like Price Comparator."""
        try:
            has_comparator = self.permissions.get("Price_Comparator", False)
            comp_text = "🎯  مساعد التسعير والمنافسين" if has_comparator else "🔒  مساعد التسعير (مقفل)"
            comp_fg = (BRAND_GREEN, "#059669") if has_comparator else (BRAND_SLATE, "#334155")
            comp_hover = (BRAND_GREEN_HOVER, "#047857") if has_comparator else (BRAND_SLATE_HOVER, "#1E293B")
            if hasattr(self, '_btn_price_comparator') and self._btn_price_comparator.winfo_exists():
                self._btn_price_comparator.configure(text=comp_text, fg_color=comp_fg, hover_color=comp_hover)
        except Exception:
            pass

    def _show_license_sync_button(self):
        if hasattr(self, '_btn_lic_sync') and self._btn_lic_sync.winfo_exists():
            if not self._btn_lic_sync.winfo_ismapped():
                if hasattr(self, '_btn_price_comparator') and self._btn_price_comparator.winfo_exists():
                    self._btn_lic_sync.pack(side="left", padx=(0, 8), before=self._btn_price_comparator)
                else:
                    self._btn_lic_sync.pack(side="left", padx=(0, 8))

    def _hide_license_sync_button(self):
        if hasattr(self, '_btn_lic_sync') and self._btn_lic_sync.winfo_exists():
            self._btn_lic_sync.pack_forget()

    def _open_license_sync_dialog(self):
        show_device_license_dialog(
            self,
            "OdooReportExporter",
            APP_VERSION,
            on_deactivate=self._build_activation_screen,
            on_synced=self._hide_license_sync_button
        )

    def _handle_remote_device_blocked(self):
        """Immediately terminates local activation when revoked remotely from Odoo."""
        deactivate_device()
        messagebox.showerror(
            "🚫 تم إلغاء ترخيص هذا الجهاز",
            "تم إنهاء وتجميد ترخيص هذا الجهاز من قبل إدارة النظام عبر Odoo.\nيرجى التواصل مع الإدارة لإعادة تفعيل الجهاز."
        )
        self._build_activation_screen()

    # ─── HEADER ───────────────────────────────────────────────
    def _build_header(self, parent):
        # Gold top accent strip
        gold_strip = ctk.CTkFrame(parent, fg_color=BRAND_GOLD, height=3, corner_radius=0)
        gold_strip.pack(fill="x")

        hdr = ctk.CTkFrame(parent, corner_radius=0,
                            fg_color=HDR_BG, height=64)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        # Right side: Company logo
        brand_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        brand_frame.pack(side="right", padx=16, pady=6)

        # Load official company logo
        self._header_logo_img = None
        try:
            from company_profile import get_default_logo_path
            from PIL import Image
            logo_path = get_default_logo_path()
            if not logo_path or not os.path.exists(logo_path):
                logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "company_logo.png")
            if os.path.exists(logo_path):
                pil_img = Image.open(logo_path)
                target_h = 44
                target_w = int(target_h * (pil_img.width / pil_img.height))
                self._header_logo_img = ctk.CTkImage(light_image=pil_img,
                                                     dark_image=pil_img,
                                                     size=(target_w, target_h))
                ctk.CTkLabel(brand_frame, image=self._header_logo_img, text="").pack(side="right", padx=2)
            else:
                ctk.CTkLabel(brand_frame, text="العسلي التجارية",
                             font=ctk.CTkFont(APP_FONT, 14, "bold"),
                             text_color=BRAND_GOLD).pack(side="right")
        except Exception:
            ctk.CTkLabel(brand_frame, text="العسلي التجارية",
                         font=ctk.CTkFont(APP_FONT, 14, "bold"),
                         text_color=BRAND_GOLD).pack(side="right")

        # Left controls
        ctrl_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        ctrl_frame.pack(side="left", padx=14, pady=8)

        # Theme toggle
        self._theme_var = ctk.StringVar(value="☀️  فاتح" if self.settings.get("theme") == "Light" else "🌙  داكن")
        theme_menu = ctk.CTkOptionMenu(ctrl_frame,
                                       values=["🌙  داكن", "☀️  فاتح"],
                                       variable=self._theme_var,
                                       width=115, height=32,
                                       corner_radius=8,
                                       font=ctk.CTkFont(APP_FONT, 11),
                                       command=self._change_theme)
        theme_menu.pack(side="left", padx=(0, 8))

        # Company Profile & Logo button
        ctk.CTkButton(ctrl_frame, text="🏢  بيانات الشركة",
                      font=ctk.CTkFont(APP_FONT, 11, "bold"),
                      fg_color=BRAND_BLUE, hover_color=BRAND_BLUE_HOVER,
                      corner_radius=8,
                      width=130, height=32,
                      command=self._open_company_profile_dialog).pack(side="left", padx=(0, 8))

        # Admin permissions button
        ctk.CTkButton(ctrl_frame, text="🔒  الصلاحيات",
                      font=ctk.CTkFont(APP_FONT, 11, "bold"),
                      fg_color=BRAND_PURPLE, hover_color=BRAND_PURPLE_HOVER,
                      corner_radius=8,
                      width=115, height=32,
                      command=self._open_admin_dialog).pack(side="left", padx=(0, 8))

        # Device & Odoo License sync button (Hidden by default; surfaces ONLY if device is not in Odoo)
        self._btn_lic_sync = ctk.CTkButton(
            ctrl_frame,
            text="⚠️  ترخيص الجهاز في Odoo",
            font=ctk.CTkFont(APP_FONT, 11, "bold"),
            fg_color=("#D97706", "#B45309"), hover_color="#92400E",
            corner_radius=8,
            width=160, height=32,
            command=self._open_license_sync_dialog
        )

        # Price Comparator & Competitor Intelligence button (Gated by Permissions)
        has_comparator = self.permissions.get("Price_Comparator", False)
        comp_text = "🎯  مساعد التسعير والمنافسين" if has_comparator else "🔒  مساعد التسعير (مقفل)"
        comp_fg = (BRAND_GREEN, "#059669") if has_comparator else (BRAND_SLATE, "#334155")
        comp_hover = (BRAND_GREEN_HOVER, "#047857") if has_comparator else (BRAND_SLATE_HOVER, "#1E293B")

        self._btn_price_comparator = ctk.CTkButton(
            ctrl_frame,
            text=comp_text,
            font=ctk.CTkFont(APP_FONT, 11, "bold"),
            fg_color=comp_fg,
            hover_color=comp_hover,
            corner_radius=8,
            width=175, height=32,
            command=self._launch_price_comparator
        )
        self._btn_price_comparator.pack(side="left")

        # Center: App title, Developer credit, & 12h Clock
        title_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        title_frame.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(title_frame, text="📊  نظام تصدير تقارير منتجات ومعارض Odoo",
                     font=ctk.CTkFont(APP_FONT, 16, "bold"),
                     text_color=HDR_TITLE_COLOR).pack(pady=(0, 2))

        # Sub-header bar: Developer credit & 12h Clock (without seconds)
        sub_bar = ctk.CTkFrame(title_frame, fg_color="transparent")
        sub_bar.pack()

        ctk.CTkLabel(sub_bar,
                     text=f"{APP_VERSION} تصميم وتطوير: عبدالله الخطيب",
                     font=ctk.CTkFont(APP_FONT, 11, "bold"),
                     text_color=BRAND_GOLD).pack(side="right", padx=(0, 10))

        ctk.CTkLabel(sub_bar,
                     text="|",
                     font=ctk.CTkFont(APP_FONT, 11),
                     text_color=("#93C5FD", "#475569")).pack(side="right", padx=(0, 10))

        now = datetime.now()
        period = "ص" if now.hour < 12 else "م"
        h = now.hour % 12 or 12
        init_clock = f"📅 {now.strftime('%Y/%m/%d')}   ⏰ {h:02d}:{now.minute:02d} {period}"
        self._hdr_clock = ctk.CTkLabel(sub_bar,
                                       text=init_clock,
                                       font=ctk.CTkFont(APP_FONT, 11, "bold"),
                                       text_color=("#F1F5F9", "#CBD5E1"))
        self._hdr_clock.pack(side="right")
        self._tick_clock()

    # ─── SIDEBAR ──────────────────────────────────────────────
    def _build_sidebar(self, parent):
        sidebar = ctk.CTkFrame(parent, width=235, corner_radius=12,
                                border_width=1, border_color=BORDER_SUBTLE)
        sidebar.pack(side="right", fill="y", padx=(8, 0), pady=8)
        sidebar.pack_propagate(False)

        ctk.CTkLabel(sidebar, text="⚙️  إعدادات التصدير",
                     font=ctk.CTkFont(APP_FONT, 14, "bold"),
                     text_color=(BRAND_BLUE, BRAND_BLUE_GLOW)).pack(pady=(14, 8))

        sep0 = ctk.CTkFrame(sidebar, height=1, fg_color=BORDER_SUBTLE)
        sep0.pack(fill="x", padx=14)

        # ── Report Type Selector ─────────────────────────
        ctk.CTkLabel(sidebar, text="📑 نوع التقرير المطلوب",
                     font=ctk.CTkFont(APP_FONT, 11, "bold"),
                     text_color=BRAND_SLATE).pack(anchor="e", padx=14, pady=(10, 4))

        self._report_type_var = ctk.StringVar(value="inventory")
        ctk.CTkRadioButton(sidebar, text="📊 حركة ومخزون المنتجات", variable=self._report_type_var,
                           value="inventory", font=ctk.CTkFont(APP_FONT, 11),
                           command=self._on_report_type_change).pack(anchor="e", padx=18, pady=2)
        ctk.CTkRadioButton(sidebar, text="🧾 مبيعات وخصومات نقاط البيع", variable=self._report_type_var,
                           value="pos_discounts", font=ctk.CTkFont(APP_FONT, 11),
                           command=self._on_report_type_change).pack(anchor="e", padx=18, pady=2)
        ctk.CTkRadioButton(sidebar, text="🛒 تقارير المشتريات والتوريد", variable=self._report_type_var,
                           value="purchases", font=ctk.CTkFont(APP_FONT, 11, "bold"),
                           text_color=("#B45309", "#FBBF24"),
                           command=self._on_report_type_change).pack(anchor="e", padx=18, pady=2)

        sep1 = ctk.CTkFrame(sidebar, height=1, fg_color=BORDER_SUBTLE)
        sep1.pack(fill="x", padx=14, pady=(8, 6))

        # ── Pinned Bottom: Output path & browse ───────────
        save_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        save_frame.pack(side="bottom", fill="x", padx=12, pady=(0, 10))

        sep_save = ctk.CTkFrame(save_frame, height=1, fg_color=BORDER_SUBTLE)
        sep_save.pack(fill="x", padx=2, pady=(2, 8))

        ctk.CTkLabel(save_frame, text="💾 حفظ الملف",
                     font=ctk.CTkFont(APP_FONT, 11, "bold"),
                     text_color=BRAND_SLATE).pack(anchor="e", pady=(0, 3))

        default_file = os.path.join(
            os.path.expanduser("~"), "Desktop",
            f"تقرير_العسلي_{datetime.now().strftime('%Y%m%d')}.xlsx"
        )
        self._path_entry = ctk.CTkEntry(save_frame, placeholder_text="مسار الحفظ...",
                                        font=ctk.CTkFont(APP_FONT, 10), height=34,
                                        corner_radius=8)
        self._path_entry.insert(0, default_file)
        self._path_entry.pack(fill="x", pady=(0, 4))

        ctk.CTkButton(save_frame, text="📂  استعراض", height=32,
                      fg_color=BRAND_SLATE, hover_color=BRAND_SLATE_HOVER,
                      corner_radius=8,
                      font=ctk.CTkFont(APP_FONT, 11),
                      command=self._browse_path).pack(fill="x")

        # ── Middle dynamic container (Scrollable Frame) ───
        self._sidebar_scroll = ctk.CTkScrollableFrame(sidebar, fg_color="transparent")
        self._sidebar_scroll.pack(side="top", fill="both", expand=True, padx=2, pady=0)

        # --- Subframe A: Inventory & Stock Options ---
        self._inventory_options_frame = ctk.CTkFrame(self._sidebar_scroll, fg_color="transparent")
        self._inventory_options_frame.pack(fill="x", pady=0)

        # Movement filter
        ctk.CTkLabel(self._inventory_options_frame, text="⚡ حركة الأصناف",
                     font=ctk.CTkFont(APP_FONT, 11, "bold"),
                     text_color=BRAND_SLATE).pack(anchor="e", padx=10, pady=(2, 4))

        self._movement_var = ctk.StringVar(value="all")
        movements = [
            ("all", "جميع الأصناف"),
            ("fast_moving", "🔥 سريعة الحركة"),
            ("stagnant", "⚠️  أصناف راكدة"),
            ("low_stock", "📉  قاربت على النفاذ"),
        ]
        for val, label in movements:
            ctk.CTkRadioButton(self._inventory_options_frame, text=label, variable=self._movement_var,
                               value=val, font=ctk.CTkFont(APP_FONT, 11)).pack(
                anchor="e", padx=16, pady=2)

        sep_inv1 = ctk.CTkFrame(self._inventory_options_frame, height=1, fg_color=BORDER_SUBTLE)
        sep_inv1.pack(fill="x", padx=8, pady=8)

        # Pricelist selector
        ctk.CTkLabel(self._inventory_options_frame, text="🏷️ قائمة الأسعار (Pricelist)",
                     font=ctk.CTkFont(APP_FONT, 11, "bold"),
                     text_color=BRAND_SLATE).pack(anchor="e", padx=10, pady=(0, 4))

        self._pricelist_var = ctk.StringVar(value="سعر الشاطئ")
        self._pricelist_menu = ctk.CTkOptionMenu(
            self._inventory_options_frame,
            variable=self._pricelist_var,
            values=["سعر الشاطئ"],
            font=ctk.CTkFont(APP_FONT, 10),
            dropdown_font=ctk.CTkFont(APP_FONT, 10),
            corner_radius=8,
            height=30
        )
        self._pricelist_menu.pack(fill="x", padx=12, pady=(0, 4))

        sep_pl = ctk.CTkFrame(self._inventory_options_frame, height=1, fg_color=BORDER_SUBTLE)
        sep_pl.pack(fill="x", padx=8, pady=8)

        # Column groups
        ctk.CTkLabel(self._inventory_options_frame, text="📋 مجموعات الأعمدة",
                     font=ctk.CTkFont(APP_FONT, 11, "bold"),
                     text_color=BRAND_SLATE).pack(anchor="e", padx=10, pady=(0, 4))

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
            ctk.CTkCheckBox(self._inventory_options_frame, text=label, variable=var,
                            font=ctk.CTkFont(APP_FONT, 11)).pack(anchor="e", padx=16, pady=2)

        sep_guide = ctk.CTkFrame(self._inventory_options_frame, height=1, fg_color=BORDER_SUBTLE)
        sep_guide.pack(fill="x", padx=8, pady=8)

        # Documentation / Guide sheet
        ctk.CTkLabel(self._inventory_options_frame, text="📖 توثيق ودليل التقرير",
                     font=ctk.CTkFont(APP_FONT, 11, "bold"),
                     text_color=BRAND_SLATE).pack(anchor="e", padx=10, pady=(0, 4))

        self._include_guide = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self._inventory_options_frame, text="تضمين دليل الحسابات في Excel", variable=self._include_guide,
                        font=ctk.CTkFont(APP_FONT, 11)).pack(anchor="e", padx=16, pady=2)

        # --- Subframe B: POS Discounts Options ---
        self._pos_options_frame = ctk.CTkFrame(self._sidebar_scroll, fg_color="transparent")
        # (initially hidden)

        ctk.CTkLabel(self._pos_options_frame, text="🧾 خيارات تقرير الخصومات",
                     font=ctk.CTkFont(APP_FONT, 11, "bold"),
                     text_color=(BRAND_BLUE, BRAND_BLUE_GLOW)).pack(anchor="e", padx=10, pady=(4, 4))

        pos_info_card = ctk.CTkFrame(self._pos_options_frame, fg_color=("gray95", BG_CARD), corner_radius=8,
                                     border_width=1, border_color=BORDER_SUBTLE)
        pos_info_card.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkLabel(pos_info_card,
                     text="💡 يستخرج التقرير حركات الكاشير (المبيعات والمرتجعات) التي تشتمل على خصومات فقط، لاحتساب التعويض المستحق من الموردين.",
                     font=ctk.CTkFont(APP_FONT, 10), text_color=BRAND_SLATE,
                     wraplength=190, justify="right").pack(padx=8, pady=8)

        self._pos_include_showroom = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self._pos_options_frame, text="🏢 إضافة عمود المعرض / الفرع",
                        variable=self._pos_include_showroom,
                        font=ctk.CTkFont(APP_FONT, 11)).pack(anchor="e", padx=16, pady=4)

        self._pos_all_sales = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self._pos_options_frame, text="🛍️  إظهار كل مبيعات الصنف (مع وبدون خصم)",
                        variable=self._pos_all_sales,
                        font=ctk.CTkFont(APP_FONT, 11),
                        command=self._on_pos_options_change).pack(anchor="e", padx=16, pady=4)

        self._pos_include_pro_sheets = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(self._pos_options_frame, text="📊  لوحة المؤشرات وملخص الأصناف وكشف المطالبة",
                        variable=self._pos_include_pro_sheets,
                        font=ctk.CTkFont(APP_FONT, 11)).pack(anchor="e", padx=16, pady=4)

        self._pos_split_showrooms = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self._pos_options_frame, text="📑  أوراق عمل مستقلة لكل معرض",
                        variable=self._pos_split_showrooms,
                        font=ctk.CTkFont(APP_FONT, 11)).pack(anchor="e", padx=16, pady=4)

        self._pos_export_pdf = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self._pos_options_frame, text="📄  تصدير كشف المطالبة كملف PDF معتمد",
                        variable=self._pos_export_pdf,
                        font=ctk.CTkFont(APP_FONT, 11)).pack(anchor="e", padx=16, pady=(4, 6))

        # --- Subframe C: Smart Purchasing & Supply Chain Options ---
        self._purchase_options_frame = ctk.CTkFrame(self._sidebar_scroll, fg_color="transparent")
        # (initially hidden)

        ctk.CTkLabel(self._purchase_options_frame, text="🛒 منظومة المشتريات والتوريد",
                     font=ctk.CTkFont(APP_FONT, 11, "bold"),
                     text_color=("#D97706", "#FBBF24")).pack(anchor="e", padx=10, pady=(4, 4))

        purch_info_card = ctk.CTkFrame(self._purchase_options_frame, fg_color=("gray95", BG_CARD), corner_radius=8,
                                       border_width=1, border_color=BORDER_SUBTLE)
        purch_info_card.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkLabel(purch_info_card,
                     text="💡 منظومة تنفيذية شاملة: ما يجب شراؤه، سجل ما تم شراؤه والبونص، تقييم الموردين، رقابة الأسعار، والطلبيات بالطريق.",
                     font=ctk.CTkFont(APP_FONT, 10), text_color=BRAND_SLATE,
                     wraplength=195, justify="right").pack(padx=8, pady=7)

        # Scope / Mode selector
        ctk.CTkLabel(self._purchase_options_frame, text="📌 نطاق تقارير المشتريات",
                     font=ctk.CTkFont(APP_FONT, 11, "bold"),
                     text_color=BRAND_SLATE).pack(anchor="e", padx=10, pady=(2, 3))

        self._purch_mode_var = ctk.StringVar(value="comprehensive")
        purch_modes = [
            ("comprehensive", "📊 الحزمة الشاملة (كافة التقارير)"),
            ("what_to_buy", "🛒 ما يجب شراؤه فقط (الاحتياج)"),
            ("what_was_bought", "🧾 ما تم شراؤه فقط (سجل الشراء)"),
        ]
        for val, label in purch_modes:
            ctk.CTkRadioButton(self._purchase_options_frame, text=label, variable=self._purch_mode_var,
                               value=val, font=ctk.CTkFont(APP_FONT, 10),
                               command=self._on_purch_options_change).pack(anchor="e", padx=12, pady=2)

        sep_p1 = ctk.CTkFrame(self._purchase_options_frame, height=1, fg_color=BORDER_SUBTLE)
        sep_p1.pack(fill="x", padx=8, pady=6)

        # Target Coverage Days selector
        ctk.CTkLabel(self._purchase_options_frame, text="⏳ أيام التغطية المستهدفة للاحتياج",
                     font=ctk.CTkFont(APP_FONT, 11, "bold"),
                     text_color=BRAND_SLATE).pack(anchor="e", padx=10, pady=(0, 3))

        self._purch_cov_var = ctk.StringVar(value="60 يوم (شهران - افتراضي)")
        self._purch_cov_menu = ctk.CTkOptionMenu(
            self._purchase_options_frame,
            variable=self._purch_cov_var,
            values=[
                "30 يوم (شهر)",
                "60 يوم (شهران - افتراضي)",
                "90 يوم (3 أشهر)",
                "120 يوم (4 أشهر)",
                "180 يوم (6 أشهر)",
                "مخصص..."
            ],
            font=ctk.CTkFont(APP_FONT, 10),
            dropdown_font=ctk.CTkFont(APP_FONT, 10),
            corner_radius=8,
            height=28,
            command=self._on_purch_cov_change
        )
        self._purch_cov_menu.pack(fill="x", padx=10, pady=(0, 4))

        self._purch_custom_cov_frame = ctk.CTkFrame(self._purchase_options_frame, fg_color="transparent")
        ctk.CTkLabel(self._purch_custom_cov_frame, text="عدد الأيام:", font=ctk.CTkFont(APP_FONT, 10)).pack(side="right", padx=(0, 4))
        self._purch_custom_cov_entry = ctk.CTkEntry(self._purch_custom_cov_frame, width=80, height=28,
                                                    justify="center", font=ctk.CTkFont(APP_FONT, 11, "bold"))
        self._purch_custom_cov_entry.insert(0, "45")
        self._purch_custom_cov_entry.pack(side="right", padx=4)

        sep_p2 = ctk.CTkFrame(self._purchase_options_frame, height=1, fg_color=BORDER_SUBTLE)
        sep_p2.pack(fill="x", padx=8, pady=6)

        ctk.CTkLabel(self._purchase_options_frame, text="🧠 خيارات ذكاء المشتريات",
                     font=ctk.CTkFont(APP_FONT, 11, "bold"),
                     text_color=BRAND_SLATE).pack(anchor="e", padx=10, pady=(0, 3))

        self._purch_only_needed = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self._purchase_options_frame, text="🎯 الأصناف المطلوبة للشراء فقط",
                        variable=self._purch_only_needed,
                        font=ctk.CTkFont(APP_FONT, 10)).pack(anchor="e", padx=12, pady=3)

        self._purch_deduct_open_po = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(self._purchase_options_frame, text="🚚 خصم الطلبيات المفتوحة (بالطريق)",
                        variable=self._purch_deduct_open_po,
                        font=ctk.CTkFont(APP_FONT, 10)).pack(anchor="e", padx=12, pady=3)

        self._purch_deduct_surplus = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(self._purchase_options_frame, text="🏭 خصم رصيد المستودعات والفائض",
                        variable=self._purch_deduct_surplus,
                        font=ctk.CTkFont(APP_FONT, 10)).pack(anchor="e", padx=12, pady=3)

        self._purch_vendor_score = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(self._purchase_options_frame, text="🤝 تقييم الموردين ورقابة الأسعار",
                        variable=self._purch_vendor_score,
                        font=ctk.CTkFont(APP_FONT, 10)).pack(anchor="e", padx=12, pady=3)

        self._purch_export_pdf = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self._purchase_options_frame, text="📄 تصدير طلب الشراء PDF (عند الطلب)",
                        variable=self._purch_export_pdf,
                        font=ctk.CTkFont(APP_FONT, 10)).pack(anchor="e", padx=12, pady=(3, 6))

    # ─── TABS ─────────────────────────────────────────────────
    def _build_tabs(self, parent):
        self._tabview = ctk.CTkTabview(parent, corner_radius=12,
                                        border_width=1, border_color=BORDER_SUBTLE)
        self._tabview.pack(side="left", fill="both", expand=True, pady=8)

        # NOTE: Tk on Windows renders Arabic words in LTR order. We pre-reverse
        # the word order so that when read RTL the text appears correct.
        # Emoji placed at end of source → appears at visual right (RTL start).
        tab_filters = self._tabview.add("الأصناف فلاتر  🔍")
        tab_period = self._tabview.add("الزمنية الفترة  📅")
        tab_showrooms = self._tabview.add("المعارض  🏬")

        self._build_tab_filters(tab_filters)
        self._build_tab_period(tab_period)
        self._build_tab_showrooms(tab_showrooms)

    # ─── TAB: FILTERS ─────────────────────────────────────────
    def _build_tab_filters(self, parent):
        container = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=4, pady=4)

        info = ctk.CTkLabel(container,
            text="يمكن ترك أي فلتر فارغاً لتضمين جميع الأصناف. تدعم الفلاتر: الفاصلة `,` للعناصر المتعددة، والنجمة `*` و `?` للبحث الجزئي.",
            font=ctk.CTkFont(APP_FONT, 10), text_color=BRAND_SLATE,
            wraplength=750, justify="right")
        info.pack(anchor="e", padx=6, pady=(0, 6))

        # Main 2-column layout: Right column (Filters 1, 2, 3) | Left column (Filters 4 & 5)
        cols_frame = ctk.CTkFrame(container, fg_color="transparent")
        cols_frame.pack(fill="both", expand=True)
        cols_frame.columnconfigure(0, weight=1, uniform="filter_cols")  # Left: Filters 4 (Tags) & 5 (Vendors)
        cols_frame.columnconfigure(1, weight=1, uniform="filter_cols")  # Right: Filters 1, 2, 3
        cols_frame.rowconfigure(0, weight=1)

        # ── Right Column: Filters 1, 2, 3 ──────────────────────
        right_col = ctk.CTkFrame(cols_frame, fg_color="transparent")
        right_col.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=0)

        # 1️⃣ كود الصنف (Internal Reference)
        card1 = SectionCard(right_col, title="كود الصنف (Internal Reference)", icon="1️⃣")
        card1.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(card1.content,
                     text="مثال: 4101-000000, TS*",
                     font=ctk.CTkFont(APP_FONT, 10), text_color=BRAND_SLATE).pack(anchor="e")
        self._f_ref = ctk.CTkEntry(card1.content, placeholder_text="أكواد مفصولة بفاصلة...",
                                   height=36, font=ctk.CTkFont(APP_FONT, 12))
        self._f_ref.pack(fill="x", pady=(4, 0))

        # 2️⃣ الباركود والعبوات (Barcode)
        card2 = SectionCard(right_col, title="الباركود والعبوات (Barcode)", icon="2️⃣")
        card2.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(card2.content,
                     text="مثال: 628100*, 123456789",
                     font=ctk.CTkFont(APP_FONT, 10), text_color=BRAND_SLATE).pack(anchor="e")
        self._f_barcode = ctk.CTkEntry(card2.content, placeholder_text="باركودات مفصولة بفاصلة...",
                                       height=36, font=ctk.CTkFont(APP_FONT, 12))
        self._f_barcode.pack(fill="x", pady=(4, 0))

        # 3️⃣ اسم الصنف (Product Name)
        card3 = SectionCard(right_col, title="اسم الصنف (Product Name)", icon="3️⃣")
        card3.pack(fill="x", pady=(0, 0))
        ctk.CTkLabel(card3.content,
                     text="مثال: عطر*, *PERFUME*, لوشن",
                     font=ctk.CTkFont(APP_FONT, 10), text_color=BRAND_SLATE).pack(anchor="e")
        self._f_name = ctk.CTkEntry(card3.content, placeholder_text="جزء من الاسم أو عدة أسماء...",
                                    height=36, font=ctk.CTkFont(APP_FONT, 12))
        self._f_name.pack(fill="x", pady=(4, 0))

        # ── Left Column: Filter 4 (Tags) & Filter 5 (Vendors) ──
        left_col = ctk.CTkFrame(cols_frame, fg_color="transparent")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=0)

        card4 = SectionCard(left_col, title="وسوم الأصناف (Tags)", icon="4️⃣")
        card4.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(card4.content,
                     text="اكتب جزءاً من اسم الوسم ثم اضغط مسافة أو اختر من القائمة.",
                     font=ctk.CTkFont(APP_FONT, 10), text_color=BRAND_SLATE).pack(anchor="e")
        self._tag_selector = TagMultiSelect(
            card4.content,
            tags_list=self.all_tags,
            chips_height=58,
            fg_color="transparent"
        )
        self._tag_selector.pack(fill="x", pady=(4, 0))

        card5 = SectionCard(left_col, title="فلتر الموردين (Vendors)", icon="5️⃣")
        card5.pack(fill="x")
        ctk.CTkLabel(card5.content,
                     text="اكتب جزءاً من اسم المورد لاختيار مورد واحد أو عدة موردين للتقرير.",
                     font=ctk.CTkFont(APP_FONT, 10), text_color=BRAND_SLATE).pack(anchor="e")
        self._vendor_selector = TagMultiSelect(
            card5.content,
            tags_list=self.all_vendors,
            placeholder_text="ابحث عن مورد... (اكتب للبحث أو اضغط مسافة للاختيار)",
            empty_text="جميع الموردين (لم يتم تحديد مورد)",
            chips_height=58,
            chip_color="#D97706",
            fg_color="transparent"
        )
        self._vendor_selector.pack(fill="x", pady=(4, 0))

        # Clear button
        btn_bar = ctk.CTkFrame(container, fg_color="transparent")
        btn_bar.pack(fill="x", pady=(8, 0))
        ctk.CTkButton(btn_bar, text="🔄  تفريغ جميع حقول الفلاتر",
                      fg_color=BRAND_SLATE, hover_color=BRAND_SLATE_HOVER,
                      height=34, font=ctk.CTkFont(APP_FONT, 11),
                      command=self._clear_filters).pack(side="left", padx=4)

    # ─── TAB: PERIOD ──────────────────────────────────────────
    def _build_tab_period(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        info = ctk.CTkLabel(
            scroll,
            text="💡 يمكنك تحديد فترة قياس المبيعات بشكل مستقل عن فترة سجل المشتريات والطلبيات قيد الاستلام (مثال: قياس مبيعات آخر 90 يوماً مع مراجعة مشتريات العام الحالي).",
            font=ctk.CTkFont(APP_FONT, 10), text_color=BRAND_SLATE,
            wraplength=760, justify="right"
        )
        info.pack(anchor="e", padx=6, pady=(0, 6))

        cols_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        cols_frame.pack(fill="both", expand=True)
        cols_frame.columnconfigure(0, weight=1, uniform="period_cols")  # Left: Purchases Period
        cols_frame.columnconfigure(1, weight=1, uniform="period_cols")  # Right: Sales Period
        cols_frame.rowconfigure(0, weight=1)

        # ── Right Column: 1️⃣ Sales Period ─────────────────────
        right_col = ctk.CTkFrame(cols_frame, fg_color="transparent")
        right_col.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=0)

        period_card = SectionCard(right_col, title="الفترة الزمنية للمبيعات (Sales Period)", icon="1️⃣")
        period_card.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            period_card.content,
            text="تُستخدم لاحتساب الكمية المباعة، المعدل اليومي، وأيام التغطية والاحتياج:",
            font=ctk.CTkFont(APP_FONT, 10), text_color=BRAND_SLATE
        ).pack(anchor="e", pady=(0, 4))

        self._period_var = ctk.StringVar(value="this_year")
        sales_periods = [
            ("this_year", f"العام الحالي ({datetime.now().year}) (افتراضي)"),
            ("last_30_days", "آخر 30 يوماً"),
            ("last_60_days", "آخر 60 يوماً"),
            ("last_90_days", "آخر 90 يوماً"),
            ("last_180_days", "آخر 180 يوماً (6 أشهر)"),
            ("last_365_days", "آخر 365 يوماً"),
            ("all", "إجمالي كل الفترات"),
            ("custom", "فترة مبيعات مخصصة..."),
        ]
        for val, label in sales_periods:
            ctk.CTkRadioButton(period_card.content, text=label,
                               variable=self._period_var, value=val,
                               font=ctk.CTkFont(APP_FONT, 12),
                               command=self._on_period_change).pack(
                anchor="e", pady=3)

        # Custom sales date range (hidden by default)
        self._custom_dates = SectionCard(right_col, title="فترة المبيعات المخصصة", icon="🗓️")
        date_row = ctk.CTkFrame(self._custom_dates.content, fg_color="transparent")
        date_row.pack(fill="x")

        ctk.CTkLabel(date_row, text="من:", font=ctk.CTkFont(APP_FONT, 12)).pack(side="right", padx=4)
        self._date_from = ctk.CTkEntry(date_row, placeholder_text="YYYY-MM-DD", width=120, height=32)
        self._date_from.insert(0, (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"))
        self._date_from.pack(side="right", padx=3)

        ctk.CTkLabel(date_row, text="إلى:", font=ctk.CTkFont(APP_FONT, 12)).pack(side="right", padx=4)
        self._date_to = ctk.CTkEntry(date_row, placeholder_text="YYYY-MM-DD", width=120, height=32)
        self._date_to.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self._date_to.pack(side="right", padx=3)

        # ── Left Column: 2️⃣ Purchases Period ──────────────────
        left_col = ctk.CTkFrame(cols_frame, fg_color="transparent")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=0)

        purch_period_card = SectionCard(left_col, title="الفترة الزمنية للمشتريات (Purchases Period)", icon="2️⃣")
        purch_period_card.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            purch_period_card.content,
            text="تُستخدم لفلترة (ما تم شراؤه)، (تقييم الموردين)، و(طلبيات قيد الاستلام):",
            font=ctk.CTkFont(APP_FONT, 10), text_color=BRAND_SLATE
        ).pack(anchor="e", pady=(0, 4))

        self._purch_period_var = ctk.StringVar(value="this_year")
        purch_periods = [
            ("this_year", f"العام الحالي ({datetime.now().year}) (افتراضي)"),
            ("same_as_sales", "🔗 مطابقة لفترة المبيعات تلقائياً"),
            ("last_30_days", "آخر 30 يوماً"),
            ("last_60_days", "آخر 60 يوماً"),
            ("last_90_days", "آخر 90 يوماً"),
            ("last_180_days", "آخر 180 يوماً (6 أشهر)"),
            ("last_365_days", "آخر 365 يوماً"),
            ("all", "إجمالي كل الفترات"),
            ("custom", "فترة مشتريات مخصصة..."),
        ]
        for val, label in purch_periods:
            ctk.CTkRadioButton(purch_period_card.content, text=label,
                               variable=self._purch_period_var, value=val,
                               font=ctk.CTkFont(APP_FONT, 12),
                               command=self._on_purch_period_change).pack(
                anchor="e", pady=3)

        # Custom purchase date range (hidden by default)
        self._purch_custom_dates = SectionCard(left_col, title="فترة المشتريات المخصصة", icon="🗓️")
        p_date_row = ctk.CTkFrame(self._purch_custom_dates.content, fg_color="transparent")
        p_date_row.pack(fill="x")

        ctk.CTkLabel(p_date_row, text="من:", font=ctk.CTkFont(APP_FONT, 12)).pack(side="right", padx=4)
        self._purch_date_from = ctk.CTkEntry(p_date_row, placeholder_text="YYYY-MM-DD", width=120, height=32)
        self._purch_date_from.insert(0, (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d"))
        self._purch_date_from.pack(side="right", padx=3)

        ctk.CTkLabel(p_date_row, text="إلى:", font=ctk.CTkFont(APP_FONT, 12)).pack(side="right", padx=4)
        self._purch_date_to = ctk.CTkEntry(p_date_row, placeholder_text="YYYY-MM-DD", width=120, height=32)
        self._purch_date_to.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self._purch_date_to.pack(side="right", padx=3)

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

        ctk.CTkButton(top_bar, text="🏭 مستودعات فقط", width=105,
                      fg_color="#D97706", hover_color="#B45309",
                      height=28, font=ctk.CTkFont(APP_FONT, 11),
                      command=self._select_only_warehouses).pack(side="left", padx=4)

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

        self._sh_scroll = ctk.CTkScrollableFrame(parent, fg_color=("gray94", BG_CARD),
                                                  corner_radius=10)
        self._sh_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._sh_loading = ctk.CTkLabel(self._sh_scroll,
                                         text="⏳ جاري استرجاع قائمة المعارض من Odoo...",
                                         font=ctk.CTkFont(APP_FONT, 13), text_color=BRAND_SLATE)
        self._sh_loading.pack(pady=24)

    # ─── FOOTER ───────────────────────────────────────────────
    def _build_footer(self, parent):
        footer = ctk.CTkFrame(parent, corner_radius=0,
                               fg_color=FOOTER_BG, height=90)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        # Progress bar
        self._progress = ctk.CTkProgressBar(footer, height=6, corner_radius=3,
                                             progress_color=(BRAND_BLUE, BRAND_BLUE_GLOW))
        self._progress.pack(fill="x", padx=18, pady=(10, 2))
        self._progress.set(0)

        self._status_lbl = ctk.CTkLabel(footer, text="جاهز.",
                                         font=ctk.CTkFont(APP_FONT, 11),
                                         text_color=BRAND_SLATE)
        self._status_lbl.pack(anchor="e", padx=20)

        btn_row = ctk.CTkFrame(footer, fg_color="transparent")
        btn_row.pack(fill="x", padx=18, pady=(2, 10))

        self._btn_open_dir = ctk.CTkButton(btn_row, text="📁 المجلد", width=100, height=36,
                                            corner_radius=8,
                                            fg_color=BRAND_SLATE, hover_color=BRAND_SLATE_HOVER,
                                            font=ctk.CTkFont(APP_FONT, 11),
                                            state="disabled", command=self._open_dir)
        self._btn_open_dir.pack(side="left", padx=4)

        self._btn_open = ctk.CTkButton(btn_row, text="📊 فتح الإكسيل", width=120, height=36,
                                        corner_radius=8,
                                        fg_color=BRAND_GREEN, hover_color=BRAND_GREEN_HOVER,
                                        font=ctk.CTkFont(APP_FONT, 11),
                                        state="disabled", command=self._open_file)
        self._btn_open.pack(side="left", padx=4)

        self._btn_open_pdf = ctk.CTkButton(btn_row, text="📄 فتح كشف PDF", width=125, height=36,
                                           corner_radius=8,
                                           fg_color="#059669", hover_color="#047857",
                                           font=ctk.CTkFont(APP_FONT, 11),
                                           state="disabled", command=self._open_pdf)
        self._btn_open_pdf.pack(side="left", padx=4)

        self._btn_cancel = ctk.CTkButton(btn_row, text="⏹ إلغاء", width=100, height=36,
                                          corner_radius=8,
                                          fg_color=BRAND_RED, hover_color=BRAND_RED_HOVER,
                                          font=ctk.CTkFont(APP_FONT, 11),
                                          state="disabled", command=self._cancel_export)
        self._btn_cancel.pack(side="left", padx=4)

        self._btn_export = ctk.CTkButton(btn_row,
                                          text="🚀  بدء تصدير التقرير (Excel)",
                                          font=ctk.CTkFont(APP_FONT, 15, "bold"),
                                          fg_color=BRAND_BLUE, hover_color=BRAND_BLUE_HOVER,
                                          corner_radius=10,
                                          height=42, command=self._start_export)
        self._btn_export.pack(side="right", fill="x", expand=True, padx=(14, 0))

    # ══════════════════════════════════════════════════════
    # 🎯 PRICE COMPARATOR & COMPETITOR INTELLIGENCE LAUNCHER
    # ══════════════════════════════════════════════════════
    def _launch_price_comparator(self):
        """
        Launches the Price Comparator & Competitor Intelligence Suite.
        Protected by permissions: if not active, prompts for admin password.
        """
        perms, _ = load_permissions()
        if not perms.get("Price_Comparator", False):
            dlg = SecurePasswordDialog(
                self,
                title="🔒 صلاحية مقفلة",
                prompt="⚠️ برنامج مساعد التسعير يحتوي على تكاليف الشراء ومقيد بالصلاحيات.\nأدخل كلمة مرور الإدارة لفتحه:"
            )
            pwd = dlg.get_input()
            if not pwd:
                return
            if not verify_admin_password(pwd.strip()):
                messagebox.showerror("صلاحية مرفوضة", "عذراً، كلمة المرور غير صحيحة أو ليس لديك صلاحية للوصول إلى مساعد التسعير والتكاليف.")
                return

        # Determine binary or script path
        base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        work_dir = r"c:\OdooDB"

        candidates = [
            os.path.join(base_dir, "PriceComparator.exe"),
            os.path.join(work_dir, "PriceComparator.exe"),
            os.path.join(work_dir, "releases", "v1.00", "PriceComparator.exe"),
        ]

        for p in candidates:
            if os.path.exists(p):
                try:
                    subprocess.Popen([p], cwd=os.path.dirname(p))
                    return
                except Exception:
                    pass

        # Fallback to python script
        py_path = os.path.join(work_dir, "price_comparator_app.py")
        if os.path.exists(py_path):
            try:
                subprocess.Popen([sys.executable, py_path], cwd=work_dir)
                return
            except Exception as e:
                messagebox.showerror("خطأ", f"فشل تشغيل مساعد التسعير:\n{e}")
                return

        messagebox.showerror("غير موجود", "تعذر العثور على ملف تشغيل مساعد التسعير (PriceComparator.exe أو price_comparator_app.py).")

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
        win.geometry("700x720")
        win.minsize(640, 640)
        win.grab_set()
        win.lift()

        # Header
        hdr = ctk.CTkFrame(win, fg_color=(BRAND_PURPLE, "#1A0F3D"), corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="🛡️  التحكم في الحقول المسموح بظهورها للمستخدمين",
                     font=ctk.CTkFont(APP_FONT, 15, "bold"), text_color="white").pack(pady=16, padx=24)

        ctk.CTkLabel(win,
                     text="✅ مفعّل = يظهر الحقل في التصدير  |  ❌ معطّل = يُحجب الحقل نهائياً",
                     font=ctk.CTkFont(APP_FONT, 12), text_color=BRAND_SLATE).pack(pady=(10, 4))

        scroll = ctk.CTkScrollableFrame(win, height=360, corner_radius=10,
                                         fg_color=("gray94", BG_CARD))
        scroll.pack(fill="x", padx=22, pady=4)

        current_perms, _ = load_permissions()
        field_vars = {}

        # Group fields visually
        groups = [
            ("🔑 المعرفات والبيانات التقنية", ["id"]),
            ("🎯 التطبيقات والأدوات المتقدمة (تكاليف وأسعار الموردين)", ["Price_Comparator", "Purchase_Reports", "Purchase_Price_Variance"]),
            ("💰 الأسعار", ["Cost", "Sales Price", "Shati Price", "SO Price", "Pos Minimum Price",
                           "خصم البيع", "نوع احتساب الخصم", "وسم قاعدة الخصم", "التكلفة الفعلية", "هامش الربح الفعلي (%)", "السعر الجديد"]),
            ("📦 المخزون والمبيعات الإجمالية", ["Quantity On Hand", "365d Sold"]),
            ("🏭 بيانات الموردين", ["Vendors", "Vendors/Price", "Vendors/Discount (%)",
                                   "Vendors/Discounted Price", "Vendors/Last Purchase",
                                   "Vendors/Last Updated on", "Last Received Qty"]),
            ("🏬 المعارض التفصيلية", ["Showrooms_OnHand", "Showrooms_Sold"]),
            ("🏢 المستودعات ومخازن البضائع (مخزون فقط)", ["Warehouses_OnHand"]),
            ("📈 تحليلات وتوصيات المخزون", ["تصنيف ABC", "أيام التغطية", "حالة الصنف", "الطلب المقترح (60 يوم)", "قيمة الطلب المقترح", "توصيات المناقلة"]),
            ("📝 الملاحظات والبيانات الإضافية", ["Internal Notes"]),
        ]

        field_label_map = {f_id: f_label for f_id, f_label in ALL_PROTECTED_FIELDS}

        for group_title, field_ids in groups:
            grp_header = ctk.CTkFrame(scroll, fg_color=("gray88", "#1E2D45"), corner_radius=8)
            grp_header.pack(fill="x", padx=4, pady=(10, 2))
            ctk.CTkLabel(grp_header, text=group_title,
                         font=ctk.CTkFont(APP_FONT, 12, "bold"),
                         text_color=(BRAND_PURPLE, "#C4B5FD")).pack(anchor="e", padx=14, pady=5)

            grp_content = ctk.CTkFrame(scroll, fg_color="transparent")
            grp_content.pack(fill="x", padx=14, pady=2)

            for f_id in field_ids:
                var = ctk.BooleanVar(value=current_perms.get(f_id, False))
                field_vars[f_id] = var
                ctk.CTkCheckBox(grp_content,
                                text=field_label_map.get(f_id, f_id),
                                variable=var,
                                font=ctk.CTkFont(APP_FONT, 12)).pack(anchor="e", padx=22, pady=4)

        # Quick actions
        qa_frame = ctk.CTkFrame(win, fg_color="transparent")
        qa_frame.pack(fill="x", padx=22, pady=(6, 0))
        ctk.CTkButton(qa_frame, text="✅ تفعيل الكل", width=120, height=28,
                      fg_color=BRAND_GREEN, hover_color=BRAND_GREEN_HOVER,
                      command=lambda: [v.set(True) for v in field_vars.values()]).pack(side="right", padx=4)
        ctk.CTkButton(qa_frame, text="❌ تعطيل الكل", width=120, height=28,
                      fg_color=BRAND_RED, hover_color=BRAND_RED_HOVER,
                      command=lambda: [v.set(False) for v in field_vars.values()]).pack(side="right", padx=4)

        # Password change
        pass_card = SectionCard(win, title="تغيير كلمة مرور الإدارة (اتركها فارغة إذا لا ترغب بالتغيير)", icon="🔑")
        pass_card.pack(fill="x", padx=22, pady=(8, 0))
        new_pass = ctk.CTkEntry(pass_card.content, show="●", height=36,
                                placeholder_text="كلمة المرور الجديدة...",
                                corner_radius=8,
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
                      corner_radius=10,
                      height=42, command=_save).pack(fill="x", padx=22, pady=14)

    # ══════════════════════════════════════════════════════
    # ⚙️ HELPERS
    # ══════════════════════════════════════════════════════
    def _tick_clock(self):
        """Update header clock every second in 12-hour format without seconds."""
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

    def _on_period_change(self):
        if self._period_var.get() == "custom":
            self._custom_dates.pack(fill="x", padx=0, pady=(0, 8))
        else:
            self._custom_dates.pack_forget()

    def _on_purch_period_change(self):
        if hasattr(self, '_purch_period_var') and self._purch_period_var.get() == "custom":
            self._purch_custom_dates.pack(fill="x", padx=0, pady=(0, 8))
        elif hasattr(self, '_purch_custom_dates'):
            self._purch_custom_dates.pack_forget()

    def _is_auto_filename(self, cur_path):
        if not cur_path:
            return True
        auto_prefixes = (
            "تقرير_العسلي_",
            "تقرير_مبيعات_الخصومات_",
            "تقرير_مبيعات_الأصناف_",
            "منظومة_المشتريات_والتوريد_",
            "خطة_احتياج_المشتريات_",
            "سجل_وتحليل_المشتريات_",
        )
        return any(p in cur_path for p in auto_prefixes)

    def _get_default_filename(self):
        today_str = datetime.now().strftime('%Y%m%d')
        rtype = self._report_type_var.get() if hasattr(self, '_report_type_var') else "inventory"
        if rtype == "pos_discounts":
            is_all = hasattr(self, '_pos_all_sales') and self._pos_all_sales.get()
            return f"تقرير_مبيعات_الأصناف_{today_str}.xlsx" if is_all else f"تقرير_مبيعات_الخصومات_{today_str}.xlsx"
        elif rtype == "purchases":
            pmode = self._purch_mode_var.get() if hasattr(self, '_purch_mode_var') else "comprehensive"
            if pmode == "what_to_buy":
                return f"خطة_احتياج_المشتريات_{today_str}.xlsx"
            elif pmode == "what_was_bought":
                return f"سجل_وتحليل_المشتريات_{today_str}.xlsx"
            return f"منظومة_المشتريات_والتوريد_{today_str}.xlsx"
        return f"تقرير_العسلي_{today_str}.xlsx"

    def _on_report_type_change(self):
        rtype = self._report_type_var.get()
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")

        self._inventory_options_frame.pack_forget()
        self._pos_options_frame.pack_forget()
        if hasattr(self, '_purchase_options_frame'):
            self._purchase_options_frame.pack_forget()

        if rtype == "pos_discounts":
            self._pos_options_frame.pack(fill="x", pady=0)
            if hasattr(self, '_btn_open_pdf'):
                self._btn_open_pdf.configure(text="📄 فتح كشف PDF")
        elif rtype == "purchases":
            if hasattr(self, '_purchase_options_frame'):
                self._purchase_options_frame.pack(fill="x", pady=0)
            if hasattr(self, '_btn_open_pdf'):
                self._btn_open_pdf.configure(text="📄 فتح طلب الشراء PDF")
        else:
            self._inventory_options_frame.pack(fill="x", pady=0)

        self._btn_export.configure(text=self._get_export_button_text())
        cur_path = self._path_entry.get().strip()
        if self._is_auto_filename(cur_path):
            self._path_entry.delete(0, "end")
            self._path_entry.insert(0, os.path.join(desktop, self._get_default_filename()))

    def _on_pos_options_change(self):
        self._btn_export.configure(text=self._get_export_button_text())
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        cur_path = self._path_entry.get().strip()
        if self._is_auto_filename(cur_path):
            self._path_entry.delete(0, "end")
            self._path_entry.insert(0, os.path.join(desktop, self._get_default_filename()))

    def _on_purch_options_change(self):
        self._btn_export.configure(text=self._get_export_button_text())
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        cur_path = self._path_entry.get().strip()
        if self._is_auto_filename(cur_path):
            self._path_entry.delete(0, "end")
            self._path_entry.insert(0, os.path.join(desktop, self._get_default_filename()))

    def _on_purch_cov_change(self, choice=None):
        val = self._purch_cov_var.get()
        if "مخصص" in val:
            self._purch_custom_cov_frame.pack(fill="x", padx=10, pady=(0, 4), after=self._purch_cov_menu)
        else:
            self._purch_custom_cov_frame.pack_forget()

    def _get_purch_coverage_days(self):
        val = self._purch_cov_var.get() if hasattr(self, '_purch_cov_var') else "60"
        if "مخصص" in val:
            try:
                d = int(self._purch_custom_cov_entry.get().strip())
                return max(1, min(730, d))
            except Exception:
                return 60
        for num in (30, 60, 90, 120, 180):
            if str(num) in val:
                return num
        return 60

    def _get_export_button_text(self):
        rtype = self._report_type_var.get() if hasattr(self, '_report_type_var') else "inventory"
        if rtype == "pos_discounts":
            if hasattr(self, '_pos_all_sales') and self._pos_all_sales.get():
                return "🧾  تصدير كافة مبيعات الأصناف (Excel)"
            return "🧾  تصدير مبيعات الخصومات (Excel)"
        elif rtype == "purchases":
            pmode = self._purch_mode_var.get() if hasattr(self, '_purch_mode_var') else "comprehensive"
            if pmode == "what_to_buy":
                return "🛒  تصدير خطة الاحتياج وما يجب شراؤه (Excel)"
            elif pmode == "what_was_bought":
                return "🧾  تصدير سجل وتحليل المشتريات (Excel)"
            return "🛒  تصدير منظومة المشتريات والتوريد الذكي (Excel)"
        return "🚀  بدء تصدير التقرير (Excel)"

    def _browse_path(self):
        default_name = self._get_default_filename()
        f = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel Files", "*.xlsx")],
            initialfile=default_name
        )
        if f:
            self._path_entry.delete(0, "end")
            self._path_entry.insert(0, f)

    def _clear_filters(self):
        self._f_ref.delete(0, "end")
        self._f_barcode.delete(0, "end")
        self._f_name.delete(0, "end")
        self._tag_selector._clear_all()
        if hasattr(self, '_vendor_selector'):
            self._vendor_selector._clear_all()

    def _select_showrooms(self):
        for v in self.showroom_vars.values():
            v.set(True)

    def _deselect_showrooms(self):
        for v in self.showroom_vars.values():
            v.set(False)
        for v in self.warehouse_vars.values():
            v.set(False)

    def _select_only_showrooms(self):
        custom_types = load_showroom_types()
        for s in self.showrooms:
            is_care = (get_showroom_category(s['code'], s['name'], custom_types) == 'care')
            var = self.showroom_vars.get(s['id'])
            if var:
                var.set(not is_care)
        for v in self.warehouse_vars.values():
            v.set(False)

    def _select_only_care(self):
        custom_types = load_showroom_types()
        for s in self.showrooms:
            is_care = (get_showroom_category(s['code'], s['name'], custom_types) == 'care')
            var = self.showroom_vars.get(s['id'])
            if var:
                var.set(is_care)
        for v in self.warehouse_vars.values():
            v.set(False)

    def _select_only_warehouses(self):
        for v in self.showroom_vars.values():
            v.set(False)
        for v in self.warehouse_vars.values():
            v.set(True)

    def _open_showroom_types_dialog(self):
        """Interactive modal to classify showrooms as 'معارض' or 'عناية'."""
        if not self.showrooms:
            messagebox.showinfo("تنبيه", "جاري تحميل قائمة المعارض، يرجى الانتظار لحظات...")
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title("🏢 تعديل تصنيف فروع الشركة (معارض / عناية)")
        dlg.geometry("640x680")
        dlg.resizable(True, True)
        dlg.transient(self)
        dlg.grab_set()
        dlg.lift()
        dlg.focus_force()

        # Header
        hdr = ctk.CTkFrame(dlg, fg_color=HDR_BG, height=62, corner_radius=0)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        accent = ctk.CTkFrame(hdr, fg_color=BRAND_GOLD, width=4, corner_radius=0)
        accent.pack(side="right", fill="y")

        hdr_content = ctk.CTkFrame(hdr, fg_color="transparent")
        hdr_content.pack(side="right", fill="both", expand=True, padx=16, pady=10)

        ctk.CTkLabel(hdr_content, text="🏢  تصنيف فروع الشركة (معارض / عناية)",
                     font=ctk.CTkFont(APP_FONT, 14, "bold"), text_color="white").pack(anchor="e")
        ctk.CTkLabel(hdr_content, text="حدد نوع كل فرع (معارض أو عناية). فروع العناية تُلوَّن باللون الفيروزي الفاتح في التقرير والملخصات.",
                     font=ctk.CTkFont(APP_FONT, 10), text_color="gray80").pack(anchor="e")

        # Current types
        current_types = load_showroom_types()
        var_map = {}

        # Scrollable table
        scroll = ctk.CTkScrollableFrame(dlg, fg_color=("gray96", BG_CARD))
        scroll.pack(fill="both", expand=True, padx=14, pady=10)

        # Table Header
        th = ctk.CTkFrame(scroll, fg_color=(BRAND_BLUE, "#1E3A8A"), corner_radius=6)
        th.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(th, text="اسم المعرض / الفرع", font=ctk.CTkFont(APP_FONT, 11, "bold"), text_color="white").pack(side="right", padx=14, pady=5)
        ctk.CTkLabel(th, text="نوع الفرع", font=ctk.CTkFont(APP_FONT, 11, "bold"), text_color="white").pack(side="left", padx=45, pady=5)

        for s in self.showrooms:
            code = s.get('code') or ''
            name = s.get('name') or ''
            current_cat = get_showroom_category(code, name, current_types)

            row_frame = ctk.CTkFrame(scroll, fg_color=("white", "#1B2838"), corner_radius=4)
            row_frame.pack(fill="x", pady=2)

            lbl_text = f"[{code}]  {name}" if code else name
            ctk.CTkLabel(row_frame, text=lbl_text, font=ctk.CTkFont(APP_FONT, 11)).pack(side="right", padx=10, pady=6)

            seg_var = ctk.StringVar(value="عناية" if current_cat == "care" else "معارض")
            var_map[s['id']] = {
                'code': code,
                'name': name,
                'var': seg_var
            }

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
            for item in var_map.values():
                is_care = is_default_care_showroom(item['code'], item['name'])
                item['var'].set("عناية" if is_care else "معارض")

        def _save():
            new_types = {}
            for item in var_map.values():
                cat = "care" if item['var'].get() == "عناية" else "showroom"
                c = str(item['code'] or '').strip()
                n = str(item['name'] or '').strip()
                if c:
                    new_types[c] = cat
                if n:
                    new_types[n] = cat
            save_showroom_types(new_types)
            self._populate_showrooms()
            dlg.destroy()
            messagebox.showinfo("تم الحفظ", "✅ تم حفظ وتحديث تصنيفات المعارض بنجاح!")

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

    def _open_company_profile_dialog(self):
        """Interactive modal to set official company profile metadata and company logo."""
        from company_profile import load_company_profile, save_company_profile

        profile = load_company_profile()

        dlg = ctk.CTkToplevel(self)
        dlg.title("🏢 إعدادات بيانات وشعار الشركة للمطبوعات الرسمية")
        dlg.geometry("580x670")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()
        dlg.lift()
        dlg.focus_force()

        # Header
        hdr = ctk.CTkFrame(dlg, fg_color=HDR_BG, height=62, corner_radius=0)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        accent = ctk.CTkFrame(hdr, fg_color=BRAND_GOLD, width=4, corner_radius=0)
        accent.pack(side="right", fill="y")

        hdr_content = ctk.CTkFrame(hdr, fg_color="transparent")
        hdr_content.pack(side="right", fill="both", expand=True, padx=16, pady=10)

        ctk.CTkLabel(hdr_content, text="🏢  بيانات وشعار الشركة للمطبوعات الرسمية",
                     font=ctk.CTkFont(APP_FONT, 14, "bold"), text_color="white").pack(anchor="e")
        ctk.CTkLabel(hdr_content, text="تُستخدم هذه البيانات والشعار في ترويسة التقارير الرسمية وكشوف مطالبات الموردين وملفات PDF.",
                     font=ctk.CTkFont(APP_FONT, 10), text_color="gray80").pack(anchor="e")

        content = ctk.CTkFrame(dlg, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=12)

        entries = {}
        fields_info = [
            ("name_ar", "اسم الشركة (بالعربي):", profile.get("name_ar", "")),
            ("name_en", "English Company Name:", profile.get("name_en", "")),
            ("cr_number", "رقم السجل التجاري (C.R.):", profile.get("cr_number", "")),
            ("tax_id", "الرقم الضريبي (VAT ID):", profile.get("tax_id", "")),
            ("phone", "رقم الهاتف / الجوال:", profile.get("phone", "")),
            ("email", "البريد الإلكتروني:", profile.get("email", "")),
            ("address", "العنوان / المقر الرئيسي:", profile.get("address", "")),
        ]

        for key, lbl, default_val in fields_info:
            f_frame = ctk.CTkFrame(content, fg_color="transparent")
            f_frame.pack(fill="x", pady=2)
            ctk.CTkLabel(f_frame, text=lbl, font=ctk.CTkFont(APP_FONT, 10, "bold"),
                         text_color=BRAND_SLATE).pack(anchor="e")
            entry = ctk.CTkEntry(f_frame, font=ctk.CTkFont(APP_FONT, 11), height=30)
            entry.insert(0, default_val)
            entry.pack(fill="x")
            entries[key] = entry

        # Logo path
        logo_frame = ctk.CTkFrame(content, fg_color="transparent")
        logo_frame.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(logo_frame, text="شعار الشركة (صورة PNG / JPG):",
                     font=ctk.CTkFont(APP_FONT, 10, "bold"), text_color=BRAND_SLATE).pack(anchor="e")
        
        logo_row = ctk.CTkFrame(logo_frame, fg_color="transparent")
        logo_row.pack(fill="x")
        
        logo_entry = ctk.CTkEntry(logo_row, font=ctk.CTkFont(APP_FONT, 10), height=30)
        logo_entry.insert(0, profile.get("logo_path", ""))
        logo_entry.pack(side="right", fill="x", expand=True, padx=(4, 0))
        entries["logo_path"] = logo_entry

        def _pick_logo():
            f = filedialog.askopenfilename(
                title="اختيار شعار الشركة",
                filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp")]
            )
            if f:
                logo_entry.delete(0, "end")
                logo_entry.insert(0, f)

        ctk.CTkButton(logo_row, text="🖼️  استعراض...", width=100, height=30,
                      fg_color=BRAND_SLATE, hover_color=BRAND_SLATE_HOVER,
                      command=_pick_logo).pack(side="left")

        # Buttons
        btn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(6, 14))

        def _save():
            new_data = {k: e.get().strip() for k, e in entries.items()}
            if save_company_profile(new_data):
                messagebox.showinfo("تم الحفظ", "🎉 تم حفظ بيانات وشعار الشركة بنجاح! سيتم استخدامها في كافة التقارير والمطبوعات الرسمية.")
                dlg.destroy()
            else:
                messagebox.showerror("خطأ", "فشل حفظ بيانات الشركة.")

        ctk.CTkButton(btn_frame, text="💾  حفظ بيانات الشركة", font=ctk.CTkFont(APP_FONT, 12, "bold"),
                      fg_color=BRAND_BLUE, hover_color=BRAND_BLUE_HOVER, height=36,
                      command=_save).pack(side="right", fill="x", expand=True, padx=(8, 0))

        ctk.CTkButton(btn_frame, text="إلغاء", font=ctk.CTkFont(APP_FONT, 11),
                      fg_color=BRAND_SLATE, hover_color=BRAND_SLATE_HOVER, height=36, width=90,
                      command=dlg.destroy).pack(side="left")

    def _load_showrooms_async(self):
        def _worker():
            try:
                self.showrooms = get_active_showrooms()
                sh_wh_ids = {s['id'] for s in self.showrooms}
                try:
                    self.warehouses = get_all_warehouses(exclude_showroom_ids=sh_wh_ids)
                except Exception:
                    self.warehouses = []
                self.after(0, self._populate_showrooms)
            except Exception as e:
                self.after(0, lambda err=e: self._sh_loading.configure(
                    text=f"⚠️ تعذر جلب المعارض:\n{err}"))
        threading.Thread(target=_worker, daemon=True).start()

    def _populate_showrooms(self):
        self._sh_loading.pack_forget()
        prev_selected = {sid: var.get() for sid, var in self.showroom_vars.items()}
        prev_wh_selected = {wid: var.get() for wid, var in self.warehouse_vars.items()}
        self.showroom_vars.clear()
        self.warehouse_vars.clear()
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
            care_header = ctk.CTkFrame(self._sh_scroll, fg_color=("#D1F2EB", "#0E3A36"), corner_radius=8)
            care_header.pack(fill="x", padx=6, pady=(4, 8))
            ctk.CTkLabel(care_header, text=f"🌿  فروع ومراكز العناية ({len(care_showrooms)} فروع) — تظهر بخلفية فيروزية في التقرير",
                         font=ctk.CTkFont(APP_FONT, 12, "bold"), text_color=("#0E6251", "#76D7C4")).pack(anchor="e", padx=12, pady=6)

            care_grid = ctk.CTkFrame(self._sh_scroll, fg_color="transparent")
            care_grid.pack(fill="x", padx=6, pady=(0, 10))

            row, col = 0, 0
            for s in care_showrooms:
                var = ctk.BooleanVar(value=prev_selected.get(s['id'], True))
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
            std_header = ctk.CTkFrame(self._sh_scroll, fg_color=("gray88", "#1B2A3D"), corner_radius=8)
            std_header.pack(fill="x", padx=6, pady=(4, 8))
            ctk.CTkLabel(std_header, text=f"🏬  المعارض الرئيسية ({len(std_showrooms)} معرض)",
                         font=ctk.CTkFont(APP_FONT, 12, "bold"), text_color=BRAND_BLUE).pack(anchor="e", padx=12, pady=6)

            std_grid = ctk.CTkFrame(self._sh_scroll, fg_color="transparent")
            std_grid.pack(fill="x", padx=6, pady=(0, 8))

            row, col = 0, 0
            for s in std_showrooms:
                var = ctk.BooleanVar(value=prev_selected.get(s['id'], True))
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

        # 3. Warehouses section (if user has permission)
        if self.warehouses and self.permissions.get("Warehouses_OnHand", True):
            wh_header = ctk.CTkFrame(self._sh_scroll, fg_color=("#FEF3C7", "#3B2A05"), corner_radius=8)
            wh_header.pack(fill="x", padx=6, pady=(6, 8))
            ctk.CTkLabel(wh_header, text=f"🏭  المستودعات ومخازن البضائع ({len(self.warehouses)} مستودعات)",
                         font=ctk.CTkFont(APP_FONT, 12, "bold"), text_color=("#92400E", "#FCD34D")).pack(anchor="e", padx=12, pady=6)

            wh_grid = ctk.CTkFrame(self._sh_scroll, fg_color="transparent")
            wh_grid.pack(fill="x", padx=6, pady=(0, 10))

            row, col = 0, 0
            for w in self.warehouses:
                var = ctk.BooleanVar(value=prev_wh_selected.get(w['id'], False))
                self.warehouse_vars[w['id']] = var
                chk = ctk.CTkCheckBox(wh_grid,
                                       text=f"[{w['code']}] {w['name']}",
                                       variable=var,
                                       fg_color="#D97706", hover_color="#B45309",
                                       font=ctk.CTkFont(APP_FONT, 11, "bold"))
                chk.grid(row=row, column=col, padx=12, pady=5, sticky="e")
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

    def _load_vendors_async(self):
        def _worker():
            try:
                vendors = get_all_vendors()
                self.all_vendors = vendors
                if hasattr(self, '_vendor_selector'):
                    self.after(0, lambda: self._vendor_selector.set_tags_list(vendors))
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _load_pricelists_async(self):
        def _worker():
            try:
                pls = get_all_pricelists()
                self._pricelists = pls
                self._pricelist_map = {pl['name']: pl['id'] for pl in pls}
                pl_names = [pl['name'] for pl in pls]
                default_val = "سعر الشاطئ" if "سعر الشاطئ" in pl_names else (pl_names[0] if pl_names else "")
                self.after(0, lambda: self._update_pricelist_menu(pl_names, default_val))
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _update_pricelist_menu(self, names, default_val):
        if hasattr(self, '_pricelist_menu') and names:
            self._pricelist_menu.configure(values=names)
            if default_val:
                self._pricelist_var.set(default_val)

    def _get_selected_pricelist_id(self):
        if hasattr(self, '_pricelist_map') and hasattr(self, '_pricelist_var'):
            name = self._pricelist_var.get()
            return self._pricelist_map.get(name)
        return None

    # ══════════════════════════════════════════════════════
    # 🚀 EXPORT
    # ══════════════════════════════════════════════════════
    def _start_export(self):
        if self.is_exporting:
            return

        rtype = self._report_type_var.get()
        if rtype == "purchases":
            perms, _ = load_permissions()
            if not perms.get("Purchase_Reports", True):
                dlg = SecurePasswordDialog(
                    self,
                    title="🔒 صلاحية مقفلة",
                    prompt="⚠️ منظومة تقارير المشتريات والتكاليف مقيدة بالصلاحيات.\nأدخل كلمة مرور الإدارة للمتابعة:"
                )
                pwd = dlg.get_input()
                if not pwd:
                    return
                if not verify_admin_password(pwd.strip()):
                    messagebox.showerror("صلاحية مرفوضة", "عذراً، كلمة المرور غير صحيحة أو ليس لديك صلاحية لتصدير تقارير المشتريات والتكاليف.")
                    return

        out_path = self._path_entry.get().strip()
        if not out_path:
            messagebox.showerror("خطأ", "يرجى تحديد مسار حفظ الملف.")
            return

        # Check if destination file(s) are currently open/locked in Excel or another program
        def _check_locked(p):
            if p and os.path.exists(p):
                try:
                    with open(p, "r+b"):
                        pass
                except Exception:
                    return True
            return False

        files_to_check = [out_path]
        if rtype == "pos_discounts" and hasattr(self, '_pos_export_pdf') and self._pos_export_pdf.get():
            base_no_ext = os.path.splitext(out_path)[0]
            files_to_check.append(f"{base_no_ext}_كشف_مطالبة_رسمي.pdf")
        elif rtype == "purchases" and hasattr(self, '_purch_export_pdf') and self._purch_export_pdf.get():
            base_no_ext = os.path.splitext(out_path)[0]
            files_to_check.append(f"{base_no_ext}_طلب_شراء_رسمي.pdf")

        for f_path in files_to_check:
            if _check_locked(f_path):
                fn = os.path.basename(f_path)
                msg = (
                    f"⚠️ الملف الهدف مفتوح حالياً في برنامج آخر ولا يمكن الكتابة عليه!\n\n"
                    f"الملف التالي قيد الاستخدام حالياً:\n"
                    f"📁 {f_path}\n\n"
                    f"💡 للمتابعة يرجى اختيار أحد الحلين:\n"
                    f"1️⃣ إغلاق الملف المفتوح ({fn}) في برنامج Excel أو قارئ PDF ثم الضغط على زر التصدير مجدداً.\n"
                    f"2️⃣ أو تغيير اسم الملف أو مسار الحفظ (من زر 'استعراض' أو كتابة اسم جديد) إذا كنت ترغب في الاحتفاظ بالملف السابق المفتوح.\n"
                )
                messagebox.showwarning("الملف قيد الاستخدام", msg)
                return

        selected = [sid for sid, v in self.showroom_vars.items() if v.get()]
        selected_wh = [wid for wid, v in self.warehouse_vars.items() if v.get()] if hasattr(self, 'warehouse_vars') else []
        if not self.permissions.get("Warehouses_OnHand", True):
            selected_wh = []

        col_opts = {
            'basic_info': self._col_basic.get(),
            'pricing': self._col_price.get(),
            'totals': self._col_totals.get(),
            'vendors': self._col_vendors.get(),
            'showrooms': self._col_showrooms.get() and bool(selected or selected_wh),
            'analytics': self._col_analytics.get()
        }

        period = self._period_var.get()
        c_from = self._date_from.get().strip() if period == "custom" else None
        c_to = self._date_to.get().strip() if period == "custom" else None

        purch_period = self._purch_period_var.get() if hasattr(self, '_purch_period_var') else "this_year"
        p_from = self._purch_date_from.get().strip() if (purch_period == "custom" and hasattr(self, '_purch_date_from')) else None
        p_to = self._purch_date_to.get().strip() if (purch_period == "custom" and hasattr(self, '_purch_date_to')) else None

        f_ref = self._f_ref.get().strip() or None
        f_bc = self._f_barcode.get().strip() or None
        f_name = self._f_name.get().strip() or None
        f_tags = self._tag_selector.get_selected_tags()
        f_vendors = self._vendor_selector.get_selected_tags() if hasattr(self, '_vendor_selector') else None

        self.is_exporting = True
        self._cancel_flag = False
        self._btn_export.configure(state="disabled", text="⏳  جاري التصدير...")
        self._btn_cancel.configure(state="normal")
        self._btn_open.configure(state="disabled")
        self._btn_open_dir.configure(state="disabled")
        self._progress.set(0)

        def _cb(pct, text):
            self.after(0, lambda: self._update_progress(pct, text))

        if rtype == "pos_discounts":
            def _run():
                try:
                    res = generate_pos_discount_report(
                        selected_showroom_ids=selected,
                        sales_period=period,
                        custom_date_from=c_from,
                        custom_date_to=c_to,
                        filter_internal_ref=f_ref,
                        filter_barcode=f_bc,
                        filter_name=f_name,
                        filter_tags=f_tags,
                        include_showroom_col=self._pos_include_showroom.get(),
                        include_all_sales=self._pos_all_sales.get(),
                        include_pro_sheets=self._pos_include_pro_sheets.get(),
                        include_showroom_sheets=self._pos_split_showrooms.get(),
                        export_claim_pdf=self._pos_export_pdf.get(),
                        output_path=out_path,
                        progress_callback=_cb,
                        is_cancelled=lambda: self._cancel_flag
                    )
                    self.last_exported_file = res['output_path']
                    self.last_exported_pdf = res.get('pdf_path')
                    self.after(0, lambda: self._on_success(res))
                except InterruptedError:
                    self.after(0, lambda: self._on_cancelled())
                except Exception as e:
                    self.after(0, lambda err=e: self._on_error(err))

            threading.Thread(target=_run, daemon=True).start()
        elif rtype == "purchases":
            cov_days = self._get_purch_coverage_days()
            pmode = self._purch_mode_var.get()
            inc_vendor_score = self._purch_vendor_score.get()
            inc_price_var = inc_vendor_score and self.permissions.get("Purchase_Price_Variance", True)

            def _run():
                try:
                    res = generate_purchase_intelligence_report(
                        filter_internal_ref=f_ref,
                        filter_barcode=f_bc,
                        filter_name=f_name,
                        filter_tags=f_tags,
                        filter_vendors=f_vendors,
                        selected_showroom_ids=selected,
                        selected_warehouse_ids=selected_wh,
                        sales_period=period,
                        custom_date_from=c_from,
                        custom_date_to=c_to,
                        purchase_period=purch_period,
                        purchase_date_from=p_from,
                        purchase_date_to=p_to,
                        purchase_mode=pmode,
                        coverage_days=cov_days,
                        only_needed_items=self._purch_only_needed.get(),
                        deduct_open_po=self._purch_deduct_open_po.get(),
                        deduct_warehouse_surplus=self._purch_deduct_surplus.get(),
                        include_vendor_scorecard=inc_vendor_score,
                        include_price_variance=inc_price_var,
                        include_open_po_sheet=True,
                        export_rfq_pdf=self._purch_export_pdf.get(),
                        output_path=out_path,
                        progress_callback=_cb,
                        is_cancelled=lambda: self._cancel_flag
                    )
                    self.last_exported_file = res['output_path']
                    self.last_exported_pdf = res.get('pdf_path')
                    self.after(0, lambda: self._on_success(res))
                except InterruptedError:
                    self.after(0, lambda: self._on_cancelled())
                except Exception as e:
                    self.after(0, lambda err=e: self._on_error(err))

            threading.Thread(target=_run, daemon=True).start()
        else:
            def _run():
                try:
                    res = generate_report(
                        selected_showroom_ids=selected,
                        selected_warehouse_ids=selected_wh,
                        column_options=col_opts,
                        sales_period=period,
                        custom_date_from=c_from,
                        custom_date_to=c_to,
                        movement_filter=self._movement_var.get(),
                        selected_pricelist_id=self._get_selected_pricelist_id(),
                        filter_internal_ref=f_ref,
                        filter_barcode=f_bc,
                        filter_name=f_name,
                        filter_tags=f_tags,
                        filter_vendors=f_vendors,
                        output_path=out_path,
                        include_methodology_guide=self._include_guide.get(),
                        progress_callback=_cb,
                        is_cancelled=lambda: self._cancel_flag
                    )
                    self.last_exported_file = res['output_path']
                    self.last_exported_pdf = None
                    self.after(0, lambda: self._on_success(res))
                except InterruptedError:
                    self.after(0, lambda: self._on_cancelled())
                except Exception as e:
                    self.after(0, lambda err=e: self._on_error(err))

            threading.Thread(target=_run, daemon=True).start()

    def _update_progress(self, pct, text):
        self._progress.set(pct / 100.0)
        self._status_lbl.configure(text=text)

    def _on_success(self, res):
        self.is_exporting = False
        self._btn_export.configure(state="normal", text=self._get_export_button_text())
        self._btn_cancel.configure(state="disabled")
        self._btn_open.configure(state="normal")
        self._btn_open_dir.configure(state="normal")
        if hasattr(self, '_btn_open_pdf'):
            if res.get('pdf_path') and os.path.exists(res['pdf_path']):
                self._btn_open_pdf.configure(state="normal")
            else:
                self._btn_open_pdf.configure(state="disabled")

        rtype = self._report_type_var.get() if hasattr(self, '_report_type_var') else "inventory"
        unit_label = "حركة" if rtype == "pos_discounts" else "صنف"
        self._status_lbl.configure(text=f"✅ اكتمل | {res['total_rows']:,} {unit_label} | {res['total_time']}ث")

        if rtype == "pos_discounts":
            is_all = hasattr(self, '_pos_all_sales') and self._pos_all_sales.get()
            rep_title = "كافة مبيعات الأصناف" if is_all else "مبيعات وخصومات نقاط البيع"
            count_label = "إجمالي حركات البيع المطابقة" if is_all else "عدد الحركات المبيعة بخصم"
            tot_sales = res.get('total_sales', 0.0)
            tot_comp = res.get('total_compensation', 0.0)
            tot_qty = res.get('total_qty', 0.0)
            inv_cnt = res.get('distinct_invoices', 0)
            top_p_name = res.get('top_product_name', '-')
            top_p_comp = res.get('top_product_comp', 0.0)

            msg = (
                f"🎉 تم تصدير تقرير {rep_title} بنجاح!\n\n"
                f"📊 ملخص المؤشرات التنفيذية والمالية:\n"
                f"• 💰 إجمالي المبيعات (شامل الضريبة): {tot_sales:,.2f} ر.س\n"
                f"• 🎁 إجمالي التعويض المطلوب: {tot_comp:,.2f} ر.س\n"
                f"• 📦 إجمالي الكميات المباعة: {tot_qty:,.2f}\n"
                f"• 🧾 {count_label}: {res['total_rows']:,}\n"
                f"• 🔢 عدد الفواتير الفريدة: {inv_cnt:,}\n"
                f"• 🏆 أعلى صنف طلباً للتعويض: {top_p_name} ({top_p_comp:,.2f} ر.س)\n"
                f"• ⏱️ الوقت المستغرق: {res['total_time']} ثانية\n\n"
                f"📁 ملف الإكسيل الشامل:\n{res['output_path']}"
            )
            if res.get('pdf_path'):
                msg += f"\n\n📄 كشف المطالبة المعتمد (PDF جاهز للطباعة والختم):\n{res['pdf_path']}"
        elif rtype == "purchases":
            tot_purch = res.get('total_purchases_net', 0.0)
            tot_bonus = res.get('total_bonus_val', 0.0)
            need_cnt = res.get('items_to_buy_count', 0)
            tot_sugg_val = res.get('total_suggested_po_val', 0.0)
            open_val = res.get('open_po_val', 0.0)
            hikes_cnt = res.get('price_hikes_count', 0)
            top_v_name = res.get('top_vendor_name', '-')
            top_v_spend = res.get('top_vendor_spend', 0.0)

            msg = (
                f"🎉 تم تصدير منظومة تقارير المشتريات والتوريد الذكي بنجاح!\n\n"
                f"📊 ملخص مؤشرات المشتريات والاحتياج:\n"
                f"• 🛒 عدد الأصناف المطلوبة للشراء الآن: {need_cnt:,} صنف\n"
                f"• 💵 التكلفة التقديرية لخطة الاحتياج المقترحة: {tot_sugg_val:,.2f} ر.س\n"
                f"• 🧾 إجمالي المشتريات الفعلية للفترة (صافي): {tot_purch:,.2f} ر.س\n"
                f"• 🎁 قيمة البونص المجاني المكتسب: {tot_bonus:,.2f} ر.س\n"
                f"• 🚚 قيمة الطلبيات المفتوحة بالطريق: {open_val:,.2f} ر.س\n"
                f"• 📈 أصناف شهدت ارتفاعاً بسعر المورد: {hikes_cnt:,} صنف\n"
                f"• 🏆 أعلى مورد تعاملاً: {top_v_name} ({top_v_spend:,.2f} ر.س)\n"
                f"• ⏱️ الوقت المستغرق: {res['total_time']} ثانية\n\n"
                f"📁 ملف الإكسيل التفاعلي الشامل:\n{res['output_path']}"
            )
            if res.get('pdf_path'):
                msg += f"\n\n📄 طلب الشراء الرسمي المعتمد (PDF جاهز للطباعة):\n{res['pdf_path']}"
        else:
            msg = (
                f"🎉 تم تصدير التقرير بنجاح!\n\n"
                f"• عدد الأصناف المطابقة: {res['total_rows']:,}\n"
                f"• عدد الأعمدة: {res['total_columns']}\n"
                f"• الوقت المستغرق: {res['total_time']} ثانية\n\n"
                f"📁 الملف:\n{res['output_path']}"
            )
        messagebox.showinfo("اكتمل التصدير", msg)

    def _on_error(self, err):
        self.is_exporting = False
        self._btn_export.configure(state="normal", text=self._get_export_button_text())
        self._btn_cancel.configure(state="disabled")
        self._status_lbl.configure(text="❌ حدث خطأ أثناء التصدير.")

        err_str = str(err)
        if isinstance(err, PermissionError) or "[Errno 13]" in err_str or "Permission denied" in err_str:
            out_path = self._path_entry.get().strip()
            fn = os.path.basename(out_path)
            msg = (
                f"⚠️ تعذر حفظ الملف لأن الملف السابق مفتوح حالياً في برنامج آخر!\n\n"
                f"يبدو أن الملف التالي مفتوح في برنامج Excel أو قارئ آخر:\n"
                f"📁 {out_path}\n\n"
                f"💡 للمتابعة يرجى اختيار أحد الحلين:\n"
                f"1️⃣ إغلاق الملف المفتوح ({fn}) على جهازك ثم إعادة محاولة التصدير.\n"
                f"2️⃣ أو تغيير اسم الملف أو مسار الحفظ إذا كنت ترغب في الاحتفاظ بالملف السابق.\n\n"
                f"ثم أعد الضغط على زر التصدير."
            )
            messagebox.showwarning("الملف قيد الاستخدام", msg)
        else:
            messagebox.showerror("خطأ في التصدير", f"حدث خطأ:\n\n{err}")

    def _on_cancelled(self):
        self.is_exporting = False
        self._btn_export.configure(state="normal", text=self._get_export_button_text())
        self._btn_cancel.configure(state="disabled")
        self._status_lbl.configure(text="⏹ تم إلغاء التصدير.")

    def _cancel_export(self):
        self._cancel_flag = True
        self._status_lbl.configure(text="⏳ جاري إلغاء العملية...")
        self._btn_cancel.configure(state="disabled")

    def _open_file(self):
        if self.last_exported_file and os.path.exists(self.last_exported_file):
            os.startfile(self.last_exported_file)

    def _open_pdf(self):
        if self.last_exported_pdf and os.path.exists(self.last_exported_pdf):
            os.startfile(self.last_exported_pdf)

    def _open_dir(self):
        if self.last_exported_file:
            d = os.path.dirname(self.last_exported_file)
            if os.path.exists(d):
                os.startfile(d)


# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = OdooReportApp()
    app.mainloop()
