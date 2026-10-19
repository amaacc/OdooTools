import os
import sys
import threading
import json
import xmlrpc.client
from datetime import datetime
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, simpledialog

from licensing import generate_license_key, generate_android_license_key, _MASTER_PASS
from security import get_odoo_credentials
from permissions import ALL_PROTECTED_FIELDS, get_default_permissions, set_device_permissions_in_odoo, encrypt_admin_password, decrypt_admin_password
from auto_updater import fetch_updates_manifest_from_odoo, publish_updates_manifest_to_odoo, APP_DISPLAY_NAMES

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("green")

# ─────────────────────────────────────────────────────────────────────────────
# 🌐 Odoo Centralized Device Registry Communication
# ─────────────────────────────────────────────────────────────────────────────
def fetch_device_registry_from_odoo():
    """Fetches the dictionary of all registered devices from Odoo ir.config_parameter."""
    url, db, user, pwd = get_odoo_credentials()
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, user, pwd, {})
    if not uid:
        raise RuntimeError("فشل الاتصال والمصادقة مع سيرفر Odoo")
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
    val = models.execute_kw(db, uid, pwd, "ir.config_parameter", "get_param", ["shelfchecker.device_registry"])
    if not val or val is False:
        return {}
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return {}
    if isinstance(val, dict):
        return val
    return {}

def save_device_registry_to_odoo(registry_dict):
    """Saves the device registry dictionary back to Odoo ir.config_parameter."""
    url, db, user, pwd = get_odoo_credentials()
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, user, pwd, {})
    if not uid:
        raise RuntimeError("فشل الاتصال والمصادقة مع سيرفر Odoo")
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
    models.execute_kw(
        db, uid, pwd,
        "ir.config_parameter", "set_param",
        ["shelfchecker.device_registry", json.dumps(registry_dict, ensure_ascii=False)]
    )


# ─────────────────────────────────────────────────────────────────────────────
# 🖥️ Main Admin Keygen & Device Manager Application
# ─────────────────────────────────────────────────────────────────────────────
class KeygenApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("منظومة إدارة وتراخيص أجهزة التطبيقات — شركة العسلي التجارية")
        self.geometry("880x720")
        self.minsize(820, 600)

        self.device_data = {}
        self.is_loading = False
        self.app_filter = "all"
        self.filter_buttons = {}

        self.setup_ui()

    def setup_ui(self):
        # Header Bar
        header = ctk.CTkFrame(self, corner_radius=10, fg_color=("#14532D", "#064E3B"))
        header.pack(fill="x", padx=15, pady=(12, 6))

        ctk.CTkLabel(
            header,
            text="🔑 إدارة تراخيص وتفعيل كافة الأجهزة (ShelfChecker / ShowroomChecker / OdooReportExporter)",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color="#86EFAC"
        ).pack(side="right", padx=15, pady=10)

        ctk.CTkLabel(
            header,
            text="تصميم/ عبدالله الخطيب",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#FDE047"
        ).pack(side="left", padx=15, pady=10)

        # Tabview for Keygen & Device Registry
        self.tabview = ctk.CTkTabview(self, corner_radius=10)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=(0, 12))

        self.tab_devices = self.tabview.add("📱 إدارة وحظر الأجهزة في Odoo")
        self.tab_updates = self.tabview.add("🚀 إدارة وتوزيع التحديثات الآلية")
        self.tab_keygen = self.tabview.add("⚡ توليد مفاتيح التفعيل يدوياً")

        self.setup_devices_tab()
        self.setup_updates_tab()
        self.setup_keygen_tab()

        # Auto-refresh devices on startup
        self.after(500, self.refresh_devices_thread)

    # ─────────────────────────────────────────────────────────────────────────
    # Tab 1: Device Management & Remote Revocation
    # ─────────────────────────────────────────────────────────────────────────
    def setup_devices_tab(self):
        parent = self.tab_devices

        # Top Control Bar (Refresh, Add, Search)
        top_bar = ctk.CTkFrame(parent, fg_color="transparent")
        top_bar.pack(fill="x", padx=10, pady=(6, 6))

        self.btn_refresh = ctk.CTkButton(
            top_bar,
            text="🔄 تحديث من Odoo",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1",
            width=140,
            height=34,
            command=self.refresh_devices_thread
        )
        self.btn_refresh.pack(side="right", padx=(8, 0))

        self.btn_add_manual = ctk.CTkButton(
            top_bar,
            text="➕ تسجيل جهاز جديد",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            width=150,
            height=34,
            command=self.dialog_add_device
        )
        self.btn_add_manual.pack(side="right", padx=8)

        # Search / Filter Entry
        self.search_entry = ctk.CTkEntry(
            top_bar,
            placeholder_text="🔍 بحث باسم المعرض، الموظف، الموديل، أو كود الجهاز...",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            height=34
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.search_entry.bind("<KeyRelease>", lambda _: self.render_device_cards())

        # Quick Filter Pills (All, ShelfChecker, ShowroomChecker, OdooReportExporter, Blocked)
        filter_row = ctk.CTkFrame(parent, fg_color="transparent")
        filter_row.pack(fill="x", padx=10, pady=(0, 6))

        filters_def = [
            ("all", "🌐 كافة الأجهزة"),
            ("FastInventory", "📦 FastInventory"),
            ("ShelfChecker", "📱 ShelfChecker"),
            ("ShowroomChecker", "🔍 ShowroomChecker"),
            ("OdooReportExporter", "📊 OdooReportExporter"),
            ("blocked", "🔴 المحظورة فقط")
        ]
        for key, label in filters_def:
            btn = ctk.CTkButton(
                filter_row,
                text=label,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                height=28,
                fg_color="#0F766E" if key == "all" else "#1E293B",
                hover_color="#115E59",
                command=lambda k=key: self.set_app_filter(k)
            )
            btn.pack(side="right", padx=3)
            self.filter_buttons[key] = btn

        # Status Summary Bar
        self.summary_bar = ctk.CTkFrame(parent, fg_color=("#1E293B", "#0F172A"), corner_radius=6, height=32)
        self.summary_bar.pack(fill="x", padx=10, pady=(0, 8))

        self.lbl_summary = ctk.CTkLabel(
            self.summary_bar,
            text="جاري الاتصال بسيرفر Odoo لجلب بيانات الأجهزة المفعّلة...",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#94A3B8"
        )
        self.lbl_summary.pack(pady=4)

        # Scrollable Frame for Device Cards
        self.scroll_devices = ctk.CTkScrollableFrame(parent, corner_radius=8)
        self.scroll_devices.pack(fill="both", expand=True, padx=10, pady=(0, 5))

    def set_app_filter(self, key):
        self.app_filter = key
        for k, btn in self.filter_buttons.items():
            btn.configure(fg_color="#0F766E" if k == key else "#1E293B")
        self.render_device_cards()

    def refresh_devices_thread(self):
        if self.is_loading:
            return
        self.is_loading = True
        self.btn_refresh.configure(state="disabled", text="⏳ جاري الجلب...")
        self.lbl_summary.configure(text="جاري الاتصال بـ Odoo ومزامنة الأجهزة...")

        def worker():
            try:
                data = fetch_device_registry_from_odoo()
                self.after(0, lambda: self.on_devices_loaded(data, None))
            except Exception as e:
                self.after(0, lambda: self.on_devices_loaded({}, str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def on_devices_loaded(self, data, error_msg):
        self.is_loading = False
        self.btn_refresh.configure(state="normal", text="🔄 تحديث من Odoo")
        if error_msg:
            self.lbl_summary.configure(
                text=f"❌ تعذر الاتصال بـ Odoo: {error_msg}",
                text_color="#EF4444"
            )
            messagebox.showerror("خطأ في الاتصال", f"فشل جلب الأجهزة من Odoo:\n{error_msg}")
            return

        self.device_data = data
        self.render_device_cards()

    def render_device_cards(self):
        # Clear existing cards
        for widget in self.scroll_devices.winfo_children():
            widget.destroy()

        query = self.search_entry.get().strip().lower()

        total = len(self.device_data)
        active_count = 0
        blocked_count = 0

        matching_devices = []
        for dev_id, info in self.device_data.items():
            st = info.get("status", "active")
            if st == "blocked":
                blocked_count += 1
            else:
                active_count += 1

            # App Filter
            app_n = str(info.get("app_name", "")).lower()
            if self.app_filter == "blocked":
                if st != "blocked":
                    continue
            elif self.app_filter != "all":
                filter_key = self.app_filter.lower()
                matches = (filter_key in app_n) or (self.app_filter == "FastInventory" and "inventory" in app_n)
                if not matches:
                    continue

            # Text Search Filter
            name = str(info.get("device_name", "")).lower()
            model = str(info.get("model", "")).lower()
            dev_id_low = dev_id.lower()
            if not query or query in name or query in model or query in dev_id_low or query in app_n:
                matching_devices.append((dev_id, info))

        # Update summary
        self.lbl_summary.configure(
            text=f"إجمالي الأجهزة المسجلة في Odoo: {total}  |  🟢 النشطة: {active_count}  |  🔴 المحظورة: {blocked_count}",
            text_color="#F8FAFC"
        )

        if not matching_devices:
            lbl_empty = ctk.CTkLabel(
                self.scroll_devices,
                text="لا توجد أجهزة مطابقة للفلتر المحدد أو لم يتم تسجيل أي جهاز بعد.",
                font=ctk.CTkFont(family="Segoe UI", size=14),
                text_color="#94A3B8"
            )
            lbl_empty.pack(pady=40)
            return

        # Render each card
        for dev_id, info in matching_devices:
            self.create_device_card(dev_id, info)

    def create_device_card(self, dev_id, info):
        status = info.get("status", "active")
        is_blocked = (status == "blocked")
        dev_name = info.get("device_name", "نقطة بيع غير مسماة")
        model = info.get("model", "Android Device")
        app_name = info.get("app_name", "ShelfChecker")
        app_ver = info.get("app_version", "")
        last_seen = info.get("last_seen", info.get("registered_at", "غير معروف"))
        reg_at = info.get("registered_at", "غير معروف")

        # Determine App Badge styling
        app_low = app_name.lower()
        if "inventory" in app_low:
            app_badge_text = "📦 FastInventory (Android)"
            app_badge_bg = "#065F46"
            app_badge_fg = "#A7F3D0"
        elif "shelf" in app_low:
            app_badge_text = "📱 ShelfChecker"
            app_badge_bg = "#0369A1"
            app_badge_fg = "#BAE6FD"
        elif "showroom" in app_low:
            if "windows" in app_low or "pc" in model.lower():
                app_badge_text = "🖥️ ShowroomChecker (PC)"
                app_badge_bg = "#0F766E"
                app_badge_fg = "#CCFBF1"
            else:
                app_badge_text = "🔍 ShowroomChecker (Android)"
                app_badge_bg = "#6D28D9"
                app_badge_fg = "#EDE9FE"
        elif "report" in app_low or "export" in app_low:
            app_badge_text = "📊 OdooReportExporter (PC)"
            app_badge_bg = "#B45309"
            app_badge_fg = "#FEF3C7"
        else:
            app_badge_text = f"⚙️ {app_name}"
            app_badge_bg = "#334155"
            app_badge_fg = "#CBD5E1"

        # Card Frame
        border_col = "#EF4444" if is_blocked else "#10B981"
        card = ctk.CTkFrame(
            self.scroll_devices,
            corner_radius=8,
            border_width=1,
            border_color=border_col,
            fg_color=("#1E293B", "#0F172A")
        )
        card.pack(fill="x", padx=5, pady=6)

        # Header Row: Badges (Status + App) + Device Name
        hdr_row = ctk.CTkFrame(card, fg_color="transparent")
        hdr_row.pack(fill="x", padx=12, pady=(10, 4))

        status_text = "🔴 محظور (معطل)" if is_blocked else "🟢 نشط ومفعل"
        status_bg = "#7F1D1D" if is_blocked else "#064E3B"
        status_color = "#FCA5A5" if is_blocked else "#86EFAC"

        badge_status = ctk.CTkLabel(
            hdr_row,
            text=f"  {status_text}  ",
            fg_color=status_bg,
            text_color=status_color,
            corner_radius=4,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
        )
        badge_status.pack(side="left", padx=(0, 6))

        badge_app = ctk.CTkLabel(
            hdr_row,
            text=f"  {app_badge_text}  ",
            fg_color=app_badge_bg,
            text_color=app_badge_fg,
            corner_radius=4,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold")
        )
        badge_app.pack(side="left")

        lbl_name = ctk.CTkLabel(
            hdr_row,
            text=dev_name,
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color="#38BDF8"
        )
        lbl_name.pack(side="right")

        # Details Row: ID + Model + Dates
        details_row = ctk.CTkFrame(card, fg_color="transparent")
        details_row.pack(fill="x", padx=12, pady=(0, 8))

        ver_txt = f" ({app_ver})" if app_ver else ""
        txt_info = f"معرف الجهاز: {dev_id}   |   الموديل: {model}{ver_txt}\nآخر ظهور: {last_seen}   |   تاريخ أول تفعيل: {reg_at}"
        lbl_info = ctk.CTkLabel(
            details_row,
            text=txt_info,
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#CBD5E1",
            justify="right"
        )
        lbl_info.pack(side="right")

        # Actions Bar
        actions_bar = ctk.CTkFrame(card, fg_color="transparent")
        actions_bar.pack(fill="x", padx=12, pady=(0, 10))

        # Block / Unblock Button
        if is_blocked:
            btn_toggle = ctk.CTkButton(
                actions_bar,
                text="🟢 فك الحظر والتفعيل",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                fg_color="#059669",
                hover_color="#047857",
                width=140,
                height=30,
                command=lambda d=dev_id: self.set_device_status(d, "active")
            )
        else:
            btn_toggle = ctk.CTkButton(
                actions_bar,
                text="🚫 حظر وإلغاء الترخيص",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                fg_color="#DC2626",
                hover_color="#B91C1C",
                width=150,
                height=30,
                command=lambda d=dev_id: self.set_device_status(d, "blocked")
            )
        btn_toggle.pack(side="right", padx=(8, 0))

        # Smart 1-Click Generate & Copy Key Button
        btn_gen = ctk.CTkButton(
            actions_bar,
            text="⚡ توليد ونسخ الكود",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color="#D97706",
            hover_color="#B45309",
            text_color="black",
            width=135,
            height=30,
            command=lambda d=dev_id, inf=info: self.quick_generate_for_device(d, inf)
        )
        btn_gen.pack(side="right", padx=6)

        # Edit Name Button
        btn_edit = ctk.CTkButton(
            actions_bar,
            text="✏️ تعديل الاسم",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="#475569",
            hover_color="#334155",
            width=100,
            height=30,
            command=lambda d=dev_id, n=dev_name: self.dialog_edit_name(d, n)
        )
        btn_edit.pack(side="right", padx=6)

        # Edit Permissions & Admin Password Button
        btn_perm = ctk.CTkButton(
            actions_bar,
            text="🔒 الصلاحيات والرقم السري",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color="#6D28D9",
            hover_color="#5B21B6",
            width=150,
            height=30,
            command=lambda d=dev_id, inf=info: self.dialog_edit_permissions(d, inf)
        )
        btn_perm.pack(side="right", padx=6)

        # Copy Device ID Button
        btn_copy = ctk.CTkButton(
            actions_bar,
            text="📋 نسخ ID",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="#334155",
            hover_color="#1E293B",
            width=80,
            height=30,
            command=lambda d=dev_id: self.copy_key(d, "معرف الجهاز")
        )
        btn_copy.pack(side="right", padx=6)

        # Delete Device Button
        btn_del = ctk.CTkButton(
            actions_bar,
            text="🗑️ حذف",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="#7F1D1D",
            hover_color="#991B1B",
            width=70,
            height=30,
            command=lambda d=dev_id, n=dev_name: self.delete_device(d, n)
        )
        btn_del.pack(side="left")

    def quick_generate_for_device(self, dev_id, info):
        """Detects whether device is Android or Windows PC, generates the exact key, and copies it."""
        model = str(info.get("model", "")).lower()
        app_n = str(info.get("app_name", "")).lower()
        is_android = "android" in model or "shelf" in app_n or "inventory" in app_n or ("showroom" in app_n and "windows" not in app_n and "pc" not in model)
        if is_android:
            k = generate_android_license_key(dev_id)
            title = f"كود تفعيل الأندرويد ({info.get('app_name', 'FastInventory')})"
        else:
            k = generate_license_key(dev_id)
            title = f"كود تفعيل الكمبيوتر ({info.get('app_name', 'Windows')})"

        self.copy_key(k, title)
        self.mid_entry.delete(0, "end")
        self.mid_entry.insert(0, dev_id)
        self.generate_key()

    def set_device_status(self, device_id, new_status):
        action_name = "حظر وإلغاء تفعيل" if new_status == "blocked" else "فك حظر وتفعيل"
        if not messagebox.askyesno("تأكيد الإجراء", f"هل أنت متأكد من رغبتك في {action_name} هذا الجهاز؟\n\nمعرف الجهاز: {device_id}"):
            return

        def worker():
            try:
                registry = fetch_device_registry_from_odoo()
                if device_id in registry:
                    registry[device_id]["status"] = new_status
                else:
                    registry[device_id] = {
                        "device_id": device_id,
                        "device_name": "نقطة بيع",
                        "status": new_status,
                        "registered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                save_device_registry_to_odoo(registry)
                self.after(0, lambda: self.on_status_updated(device_id, new_status))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("خطأ", f"تعذر تحديث الحالة في Odoo:\n{str(e)}"))

        threading.Thread(target=worker, daemon=True).start()

    def on_status_updated(self, device_id, new_status):
        if device_id in self.device_data:
            self.device_data[device_id]["status"] = new_status
        self.render_device_cards()
        msg = "تم حظر هذا الجهاز بنجاح في Odoo. سيتم إيقاف التطبيق وإلغاء تفعيله فور اتصاله بالإنترنت." if new_status == "blocked" else "تم فك حظر وتفعيل الجهاز بنجاح في Odoo."
        messagebox.showinfo("تم بنجاح", msg)

    def switch_to_keygen(self, device_id):
        self.tabview.set("⚡ توليد مفاتيح التفعيل يدوياً")
        self.mid_entry.delete(0, "end")
        self.mid_entry.insert(0, device_id)
        self.generate_key()

    def dialog_edit_name(self, device_id, old_name):
        new_name = simpledialog.askstring("تعديل اسم المعرض/الموظف", f"أدخل الاسم الجديد للجهاز ({device_id}):", initialvalue=old_name)
        if new_name is not None and new_name.strip():
            clean_name = new_name.strip()
            def worker():
                try:
                    registry = fetch_device_registry_from_odoo()
                    if device_id in registry:
                        registry[device_id]["device_name"] = clean_name
                        save_device_registry_to_odoo(registry)
                    self.after(0, lambda: self.on_name_updated(device_id, clean_name))
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("خطأ", f"تعذر تحديث الاسم في Odoo:\n{str(e)}"))
            threading.Thread(target=worker, daemon=True).start()

    def on_name_updated(self, device_id, new_name):
        if device_id in self.device_data:
            self.device_data[device_id]["device_name"] = new_name
        self.render_device_cards()
        messagebox.showinfo("تم التعديل", f"تم تحديث اسم الجهاز في Odoo إلى:\n{new_name}")

    def delete_device(self, device_id, dev_name):
        if not messagebox.askyesno("تأكيد الحذف", f"هل أنت متأكد من حذف الجهاز ({dev_name}) من سجل Odoo؟"):
            return
        def worker():
            try:
                registry = fetch_device_registry_from_odoo()
                if device_id in registry:
                    del registry[device_id]
                    save_device_registry_to_odoo(registry)
                self.after(0, lambda: self.on_device_deleted(device_id))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("خطأ", f"تعذر حذف الجهاز من Odoo:\n{str(e)}"))
        threading.Thread(target=worker, daemon=True).start()

    def on_device_deleted(self, device_id):
        if device_id in self.device_data:
            del self.device_data[device_id]
        self.render_device_cards()
        messagebox.showinfo("تم الحذف", "تم حذف الجهاز من سجل Odoo بنجاح.")

    def dialog_add_device(self):
        # Dedicated custom modal for adding a new device with app type selection
        dlg = ctk.CTkToplevel(self)
        dlg.title("تسجيل جهاز جديد في Odoo")
        dlg.geometry("450x330")
        dlg.resizable(False, False)
        dlg.grab_set()

        ctk.CTkLabel(dlg, text="➕ تسجيل جهاز جديد في نظام Odoo", font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"), text_color="#10B981").pack(pady=(15, 8))

        f_id = ctk.CTkFrame(dlg, fg_color="transparent")
        f_id.pack(fill="x", padx=25, pady=4)
        ctk.CTkLabel(f_id, text="معرّف الجهاز (Device / Machine ID):", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold")).pack(anchor="e")
        e_id = ctk.CTkEntry(f_id, placeholder_text="XXXX-XXXX-XXXX-XXXX", font=ctk.CTkFont("Consolas", 13), justify="center", height=34)
        e_id.pack(fill="x", pady=2)

        f_nm = ctk.CTkFrame(dlg, fg_color="transparent")
        f_nm.pack(fill="x", padx=25, pady=4)
        ctk.CTkLabel(f_nm, text="اسم المعرض أو الموظف:", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold")).pack(anchor="e")
        e_nm = ctk.CTkEntry(f_nm, placeholder_text="مثال: معرض الشاطيء - كاشير 1", font=ctk.CTkFont(family="Segoe UI", size=11), justify="right", height=34)
        e_nm.pack(fill="x", pady=2)

        f_app = ctk.CTkFrame(dlg, fg_color="transparent")
        f_app.pack(fill="x", padx=25, pady=4)
        ctk.CTkLabel(f_app, text="التطبيق المستهدف:", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold")).pack(anchor="e")
        app_opts = ["FastInventory", "ShelfChecker", "ShowroomChecker", "OdooReportExporter", "ShowroomChecker (Windows)"]
        app_var = ctk.StringVar(value="FastInventory")
        om_app = ctk.CTkOptionMenu(f_app, variable=app_var, values=app_opts, font=ctk.CTkFont(family="Segoe UI", size=11), height=34)
        om_app.pack(fill="x", pady=2)

        def _submit():
            raw_id = e_id.get().strip().upper().replace(" ", "").replace("-", "")
            if not raw_id:
                messagebox.showwarning("تنبيه", "يرجى إدخال معرّف الجهاز.")
                return
            formatted_id = f"{raw_id[:4]}-{raw_id[4:8]}-{raw_id[8:12]}-{raw_id[12:16]}" if len(raw_id) == 16 else e_id.get().strip().upper()
            d_name = e_nm.get().strip() or "نقطة بيع"
            sel_app = app_var.get()
            dlg.destroy()

            def worker():
                try:
                    registry = fetch_device_registry_from_odoo()
                    registry[formatted_id] = {
                        "device_id": formatted_id,
                        "device_name": d_name,
                        "app_name": sel_app,
                        "model": "مسجل يدوياً من الإدارة",
                        "status": "active",
                        "registered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "last_seen": "لم يسجل دخول بعد"
                    }
                    save_device_registry_to_odoo(registry)
                    self.after(0, lambda: self.on_manual_device_added(formatted_id, registry[formatted_id]))
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("خطأ", f"تعذر إضافة الجهاز إلى Odoo:\n{str(e)}"))
            threading.Thread(target=worker, daemon=True).start()

        ctk.CTkButton(dlg, text="💾 حفظ وتسجيل في Odoo", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                      fg_color="#059669", hover_color="#047857", height=38, command=_submit).pack(fill="x", padx=25, pady=(15, 0))

    def on_manual_device_added(self, dev_id, info):
        self.device_data[dev_id] = info
        self.render_device_cards()
        messagebox.showinfo("تمت الإضافة", f"تم تسجيل الجهاز بنجاح في Odoo:\n\nالاسم: {info['device_name']}\nالتطبيق: {info.get('app_name', '')}\nمعرف الجهاز: {dev_id}")

    def dialog_edit_permissions(self, dev_id, info):
        """
        Modal dialog to view and update permissions and admin password for a specific device in Odoo.
        """
        dev_name = info.get("device_name", "نقطة بيع غير مسماة")
        existing_perms = info.get("permissions") or get_default_permissions()
        existing_pwd = decrypt_admin_password(info.get("admin_password", ""))

        dlg = ctk.CTkToplevel(self)
        dlg.title(f"🔒 صلاحيات وكلمة مرور: {dev_name}")
        dlg.geometry("640x660")
        dlg.resizable(False, False)
        dlg.grab_set()

        # Header
        hdr = ctk.CTkFrame(dlg, fg_color=("#581C87", "#3B0764"), height=60, corner_radius=0)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        ctk.CTkLabel(
            hdr,
            text=f"🔒 إدارة الصلاحيات والرقم السري — {dev_name}",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color="#E9D5FF"
        ).pack(pady=(10, 2))

        ctk.CTkLabel(
            hdr,
            text=f"معرّف الجهاز: {dev_id}",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#C4B5FD"
        ).pack()

        # Admin Password Frame
        f_pwd = ctk.CTkFrame(dlg, fg_color=("#F1F5F9", "#1E293B"), corner_radius=8)
        f_pwd.pack(fill="x", padx=16, pady=(10, 6))

        pwd_top = ctk.CTkFrame(f_pwd, fg_color="transparent")
        pwd_top.pack(fill="x", padx=12, pady=(8, 4))

        ctk.CTkLabel(
            pwd_top,
            text="🔑 كلمة مرور الصلاحيات لهذا الجهاز (تُفرض من السيرفر):",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold")
        ).pack(side="right")

        e_pwd = ctk.CTkEntry(f_pwd, font=ctk.CTkFont("Consolas", 13, "bold"), height=34, justify="right")
        e_pwd.insert(0, existing_pwd)
        e_pwd.pack(fill="x", padx=12, pady=(0, 4))

        ctk.CTkLabel(
            f_pwd,
            text="💡 ملاحظة: الكلمة المكتوبة هنا تلغي وتتجاوز أي كلمة مرور قام المستخدم بتغييرها محلياً في جهازه فور اتصاله بالنظام.",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color="#A855F7"
        ).pack(anchor="e", padx=12, pady=(0, 8))

        # Presets Buttons Bar
        presets_bar = ctk.CTkFrame(dlg, fg_color="transparent")
        presets_bar.pack(fill="x", padx=16, pady=(2, 6))

        ctk.CTkLabel(presets_bar, text="قوالب جاهزة:", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold")).pack(side="right", padx=(0, 8))

        var_dict = {}

        def _apply_preset(mode):
            if mode == "all":
                for v in var_dict.values():
                    v.set(True)
            elif mode == "none":
                for v in var_dict.values():
                    v.set(False)
            elif mode == "pos":
                for k, v in var_dict.items():
                    if k in ("Cost", "Vendors", "Vendors/Price", "Vendors/Discount (%)", "Vendors/Discounted Price",
                             "التكلفة الفعلية", "هامش الربح الفعلي (%)", "Purchase_Reports", "Purchase_Price_Variance",
                             "Price_Comparator", "id"):
                        v.set(False)
                    else:
                        v.set(True)
            elif mode == "manager":
                for k, v in var_dict.items():
                    v.set(True)

        ctk.CTkButton(presets_bar, text="👑 مدير كامل (الكل)", width=110, height=26, font=ctk.CTkFont(family="Segoe UI", size=10),
                      command=lambda: _apply_preset("manager")).pack(side="right", padx=4)
        ctk.CTkButton(presets_bar, text="🏬 كاشير معرض (مقيد)", width=120, height=26, font=ctk.CTkFont(family="Segoe UI", size=10),
                      fg_color="#0F766E", hover_color="#0D5F58", command=lambda: _apply_preset("pos")).pack(side="right", padx=4)
        ctk.CTkButton(presets_bar, text="⚪ حظر الكل", width=80, height=26, font=ctk.CTkFont(family="Segoe UI", size=10),
                      fg_color="#475569", hover_color="#334155", command=lambda: _apply_preset("none")).pack(side="right", padx=4)

        # Scrollable Permissions Checkboxes
        f_scroll = ctk.CTkScrollableFrame(dlg, fg_color=("#F8FAFC", "#0F172A"), corner_radius=8)
        f_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        for idx, (f_id, f_label) in enumerate(ALL_PROTECTED_FIELDS):
            val = existing_perms.get(f_id, True) if f_id not in ("Price_Comparator", "id") else existing_perms.get(f_id, False)
            var = ctk.BooleanVar(value=bool(val))
            var_dict[f_id] = var

            r = idx // 2
            c = 1 - (idx % 2)

            chk = ctk.CTkCheckBox(
                f_scroll,
                text=f_label,
                variable=var,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                checkbox_width=18,
                checkbox_height=18,
                corner_radius=4
            )
            chk.grid(row=r, column=c, sticky="e", padx=10, pady=4)

        f_scroll.grid_columnconfigure(0, weight=1)
        f_scroll.grid_columnconfigure(1, weight=1)

        # Save Button
        def _do_save():
            new_perms = {f_id: var_dict[f_id].get() for f_id, _ in ALL_PROTECTED_FIELDS}
            pwd_val = e_pwd.get().strip()

            btn_save.configure(state="disabled", text="جاري الحفظ في Odoo...")

            def worker():
                ok, msg = set_device_permissions_in_odoo(dev_id, new_perms, admin_password=pwd_val)
                def on_done():
                    btn_save.configure(state="normal", text="💾 حفظ الصلاحيات والرقم السري في Odoo")
                    if ok:
                        if dev_id in self.device_data:
                            self.device_data[dev_id]["permissions"] = new_perms
                            if pwd_val:
                                self.device_data[dev_id]["admin_password"] = encrypt_admin_password(pwd_val)
                        messagebox.showinfo("تم الحفظ", f"✅ تم حفظ وتثبيت الصلاحيات بنجاح لهذا الجهاز في Odoo!\n\nسيتم تطبيقها فوراً على جهاز المعرض عند تشغيل البرنامج.")
                        dlg.destroy()
                    else:
                        messagebox.showerror("خطأ", f"تعذر حفظ الصلاحيات:\n{msg}")
                dlg.after(0, on_done)

            threading.Thread(target=worker, daemon=True).start()

        btn_save = ctk.CTkButton(
            dlg,
            text="💾  حفظ وتطبيق الصلاحيات وكلمة المرور في Odoo لهذا الجهاز",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            height=42,
            command=_do_save
        )
        btn_save.pack(fill="x", padx=16, pady=(0, 14))

    # ─────────────────────────────────────────────────────────────────────────
    # Tab 2: Auto-Updates Distribution Hub (All 8 Apps)
    # ─────────────────────────────────────────────────────────────────────────
    def setup_updates_tab(self):
        parent = self.tab_updates

        # Top Control Bar
        top_bar = ctk.CTkFrame(parent, fg_color="transparent")
        top_bar.pack(fill="x", padx=10, pady=(6, 6))

        ctk.CTkButton(
            top_bar,
            text="🔄 تحديث قراءة التحديثات من Odoo",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1",
            width=210,
            height=34,
            command=self.refresh_updates_thread
        ).pack(side="right", padx=(8, 0))

        ctk.CTkLabel(
            top_bar,
            text="🚀 لوحة التحكم بتحديثات البرامج وتوزيعها آلياً عبر GitHub Releases و Odoo",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#38BDF8"
        ).pack(side="right", padx=10)

        # Scrollable container for the 8 apps
        self.scroll_updates = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self.scroll_updates.pack(fill="both", expand=True, padx=5, pady=(0, 6))

        # Initial render and async load
        self.render_updates_cards()
        self.after(600, self.refresh_updates_thread)

    def render_updates_cards(self, manifest_data=None):
        for w in self.scroll_updates.winfo_children():
            w.destroy()

        manifest = manifest_data or {}
        apps_spec = [
            ("OdooReportExporter", "📊 OdooReportExporter (Windows)", "OdooReportExporter.exe", "#B45309"),
            ("ShowroomChecker", "🏬 ShowroomChecker (Windows)", "ShowroomChecker.exe", "#0F766E"),
            ("ShowroomChecker_Android", "📱 ShowroomChecker (Android)", "ShowroomChecker.apk", "#6D28D9"),
            ("FastInventory", "📦 FastInventory (Android)", "FastInventory.apk", "#059669"),
            ("ShelfChecker_Windows", "💻 ShelfChecker (Windows)", "ShelfChecker.exe", "#0369A1"),
            ("ShelfChecker", "📱 ShelfChecker (Android)", "ShelfChecker.apk", "#1D4ED8"),
            ("OdooItemImporter", "📥 OdooItemImporter (Windows)", "OdooItemImporter.exe", "#C026D3"),
            ("PriceComparator", "🎯 PriceComparator (Windows)", "PriceComparator.exe", "#059669"),
            ("ShelfLabelPrinter", "🖨️ ShelfLabelPrinter (Windows)", "ShelfLabelPrinter.exe", "#475569"),
        ]

        for app_key, app_title, exe_name, badge_col in apps_spec:
            info = manifest.get(app_key, {})
            cur_ver = info.get("latest_version", "1.00")
            dl_url = info.get("download_url", "")
            is_mand = info.get("is_mandatory", False)
            notes = info.get("release_notes", "")

            # Card Container
            card = ctk.CTkFrame(self.scroll_updates, corner_radius=10, fg_color=("#1E293B", "#0F172A"),
                                border_width=1, border_color="#334155")
            card.pack(fill="x", padx=6, pady=8)

            # Header Row
            hdr = ctk.CTkFrame(card, fg_color="transparent")
            hdr.pack(fill="x", padx=12, pady=(10, 6))

            ctk.CTkLabel(
                hdr,
                text=app_title,
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                text_color=badge_col
            ).pack(side="right")

            lbl_status = ctk.CTkLabel(
                hdr,
                text=f"الإصدار الحالي في Odoo: {cur_ver}",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#10B981" if dl_url else "#94A3B8"
            )
            lbl_status.pack(side="left")

            # Inputs Frame
            f_inputs = ctk.CTkFrame(card, fg_color="transparent")
            f_inputs.pack(fill="x", padx=12, pady=(0, 6))

            # Row 1: Version + Mandatory
            r1 = ctk.CTkFrame(f_inputs, fg_color="transparent")
            r1.pack(fill="x", pady=2)

            ctk.CTkLabel(r1, text="رقم الإصدار الجديد:", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold")).pack(side="right", padx=(4, 0))
            e_ver = ctk.CTkEntry(r1, width=110, height=32, font=ctk.CTkFont("Consolas", 12, "bold"), justify="center")
            e_ver.insert(0, cur_ver)
            e_ver.pack(side="right", padx=(0, 16))

            chk_mand_var = ctk.BooleanVar(value=is_mand)
            chk_mand = ctk.CTkCheckBox(r1, text="⚠️ تحديث إلزامي لجميع الأجهزة (Mandatory)", variable=chk_mand_var,
                                       font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                                       text_color="#F87171", checkbox_width=18, checkbox_height=18)
            chk_mand.pack(side="right")

            # Row 2: Download URL
            r2 = ctk.CTkFrame(f_inputs, fg_color="transparent")
            r2.pack(fill="x", pady=4)

            ctk.CTkLabel(r2, text="رابط التنزيل المباشر (GitHub Releases URL):",
                         font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold")).pack(side="right", padx=(4, 0))

            def _fill_github(ev=e_ver, eu=None, fname=exe_name):
                v_val = ev.get().strip() or "1.00"
                if not v_val.startswith("v"):
                    v_val = f"v{v_val}"
                sample = f"https://github.com/amaacc/OdooTools/releases/download/{v_val}/{fname}"
                eu.delete(0, "end")
                eu.insert(0, sample)

            e_url = ctk.CTkEntry(r2, height=32, font=ctk.CTkFont("Consolas", 11),
                                 placeholder_text=f"https://github.com/amaacc/OdooTools/releases/download/v1.01/{exe_name}")
            e_url.insert(0, dl_url)

            btn_gh = ctk.CTkButton(r2, text="🔗 مسار GitHub افتراضي", width=140, height=32,
                                   font=ctk.CTkFont(family="Segoe UI", size=10),
                                   fg_color="#334155", hover_color="#1E293B",
                                   command=lambda ev=e_ver, eu=e_url, fn=exe_name: _fill_github(ev, eu, fn))
            btn_gh.pack(side="left", padx=(8, 0))
            e_url.pack(side="right", fill="x", expand=True)

            # Row 3: Release notes
            r3 = ctk.CTkFrame(f_inputs, fg_color="transparent")
            r3.pack(fill="x", pady=2)

            ctk.CTkLabel(r3, text="سجل الميزات الجديدة (Release Notes بالعربية):",
                         font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold")).pack(anchor="e")

            txt_notes = ctk.CTkTextbox(r3, height=60, font=ctk.CTkFont(family="Segoe UI", size=11))
            txt_notes.pack(fill="x", pady=(2, 6))
            txt_notes.insert("1.0", notes or "• تحسينات عامة في الأداء والسرعة وتوافق البيانات.")

            # Row 4: Publish Action
            r4 = ctk.CTkFrame(card, fg_color="transparent")
            r4.pack(fill="x", padx=12, pady=(0, 10))

            def _publish_single(k=app_key, ev=e_ver, eu=e_url, cm=chk_mand_var, tn=txt_notes, t=app_title):
                ver_val = ev.get().strip()
                url_val = eu.get().strip()
                notes_val = tn.get("1.0", "end").strip()
                mand_val = cm.get()

                if not ver_val or not url_val:
                    messagebox.showwarning("تنبيه", "يرجى تحديد رقم الإصدار ورابط التحميل المباشر أولاً.")
                    return

                def worker():
                    try:
                        cur_manifest = fetch_updates_manifest_from_odoo()
                        cur_manifest[k] = {
                            "latest_version": ver_val,
                            "download_url": url_val,
                            "is_mandatory": mand_val,
                            "release_notes": notes_val,
                            "release_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        publish_updates_manifest_to_odoo(cur_manifest)
                        self.after(0, lambda: messagebox.showinfo("تم النشر بنجاح", f"✅ تم نشر تحديث {t} في Odoo بنجاح!\n\nالإصدار: {ver_val}\nسيصل التحديث تلقائياً لكافة الأجهزة عند تشغيل البرنامج."))
                        self.after(500, self.refresh_updates_thread)
                    except Exception as e:
                        self.after(0, lambda err=str(e): messagebox.showerror("خطأ", f"فشل نشر التحديث في Odoo:\n{err}"))

                threading.Thread(target=worker, daemon=True).start()

            btn_pub = ctk.CTkButton(
                r4,
                text=f"🚀 نشر تحديث {app_title} لجميع الأجهزة الآن في Odoo",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                fg_color="#059669",
                hover_color="#047857",
                height=36,
                command=_publish_single
            )
            btn_pub.pack(side="right", fill="x", expand=True)

    def refresh_updates_thread(self):
        def worker():
            try:
                m = fetch_updates_manifest_from_odoo()
                self.after(0, lambda: self.render_updates_cards(m))
            except Exception as e:
                self.after(0, lambda err=str(e): messagebox.showerror("خطأ", f"تعذر جلب التحديثات من Odoo:\n{err}"))
        threading.Thread(target=worker, daemon=True).start()

    # ─────────────────────────────────────────────────────────────────────────
    # Tab 3: Classic Key Generator
    # ─────────────────────────────────────────────────────────────────────────
    def setup_keygen_tab(self):
        body = self.tab_keygen

        ctk.CTkLabel(
            body,
            text="أدخل معرّف الجهاز (Machine ID / Device ID) الخاص بالجهاز:",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        ).pack(anchor="e", padx=20, pady=(12, 4))

        self.mid_entry = ctk.CTkEntry(
            body,
            placeholder_text="مثال: B575-D008-319B-29E5",
            font=ctk.CTkFont(family="Consolas", size=15),
            height=38,
            justify="center"
        )
        self.mid_entry.pack(fill="x", padx=20, pady=(0, 8))
        self.mid_entry.bind("<Return>", lambda _: self.generate_key())

        # Generate Button
        self.btn_gen = ctk.CTkButton(
            body,
            text="⚡ توليد مفاتيح التفعيل للأجهزة",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=38,
            fg_color="#059669",
            hover_color="#047857",
            command=self.generate_key
        )
        self.btn_gen.pack(fill="x", padx=20, pady=(0, 10))

        # ── 1. Android Key Section ───────────────────────────────────────────
        card_android = ctk.CTkFrame(body, fg_color=("#1E293B", "#0F172A"), corner_radius=8)
        card_android.pack(fill="x", padx=20, pady=5)

        lbl_and_row = ctk.CTkFrame(card_android, fg_color="transparent")
        lbl_and_row.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(
            lbl_and_row,
            text="📱 مفتاح تفعيل الأندرويد (ShelfChecker / ShowroomChecker Android):",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#38BDF8"
        ).pack(side="right")

        row_and_in = ctk.CTkFrame(card_android, fg_color="transparent")
        row_and_in.pack(fill="x", padx=12, pady=(0, 8))

        self.key_android_display = ctk.CTkEntry(
            row_and_in,
            font=ctk.CTkFont(family="Consolas", size=15, weight="bold"),
            text_color="#38BDF8",
            justify="center",
            height=36
        )
        self.key_android_display.pack(side="right", fill="x", expand=True, padx=(8, 0))

        btn_copy_and = ctk.CTkButton(
            row_and_in,
            text="📋 نسخ كود الأندرويد",
            width=140,
            height=36,
            fg_color="#0284C7",
            hover_color="#0369A1",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=lambda: self.copy_key(self.key_android_display.get(), "كود الأندرويد")
        )
        btn_copy_and.pack(side="left")

        # ── 2. Windows PC Key Section ─────────────────────────────────────────
        card_win = ctk.CTkFrame(body, fg_color=("#1E293B", "#0F172A"), corner_radius=8)
        card_win.pack(fill="x", padx=20, pady=5)

        lbl_win_row = ctk.CTkFrame(card_win, fg_color="transparent")
        lbl_win_row.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(
            lbl_win_row,
            text="💻 مفتاح تفعيل الكمبيوتر (ShowroomChecker Windows / Exporter):",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#4ADE80"
        ).pack(side="right")

        row_win_in = ctk.CTkFrame(card_win, fg_color="transparent")
        row_win_in.pack(fill="x", padx=12, pady=(0, 8))

        self.key_win_display = ctk.CTkEntry(
            row_win_in,
            font=ctk.CTkFont(family="Consolas", size=15, weight="bold"),
            text_color="#4ADE80",
            justify="center",
            height=36
        )
        self.key_win_display.pack(side="right", fill="x", expand=True, padx=(8, 0))

        btn_copy_win = ctk.CTkButton(
            row_win_in,
            text="📋 نسخ كود الكمبيوتر",
            width=140,
            height=36,
            fg_color="#0F766E",
            hover_color="#115E59",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=lambda: self.copy_key(self.key_win_display.get(), "كود الكمبيوتر")
        )
        btn_copy_win.pack(side="left")

        # ── 3. Master Override Section ───────────────────────────────────────
        card_master = ctk.CTkFrame(body, fg_color=("#372B15", "#241906"), corner_radius=8, border_width=1, border_color="#B45309")
        card_master.pack(fill="x", padx=20, pady=(6, 10))

        lbl_m_row = ctk.CTkFrame(card_master, fg_color="transparent")
        lbl_m_row.pack(fill="x", padx=12, pady=(6, 2))
        ctk.CTkLabel(
            lbl_m_row,
            text="👑 كود الماستر الشامل (Master Key - يفعّل أي جهاز أندرويد أو كمبيوتر فوراً):",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FBBF24"
        ).pack(side="right")

        row_m_in = ctk.CTkFrame(card_master, fg_color="transparent")
        row_m_in.pack(fill="x", padx=12, pady=(0, 8))

        self.master_display = ctk.CTkEntry(
            row_m_in,
            font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),
            text_color="#FBBF24",
            justify="center",
            height=32
        )
        self.master_display.insert(0, _MASTER_PASS)
        self.master_display.configure(state="readonly")
        self.master_display.pack(side="right", fill="x", expand=True, padx=(8, 0))

        btn_copy_m = ctk.CTkButton(
            row_m_in,
            text="📋 نسخ الماستر",
            width=140,
            height=32,
            fg_color="#D97706",
            hover_color="#B45309",
            text_color="black",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=lambda: self.copy_key(_MASTER_PASS, "كود الماستر")
        )
        btn_copy_m.pack(side="left")

    def generate_key(self):
        raw_mid = self.mid_entry.get().strip().upper().replace(" ", "").replace("-", "")
        if not raw_mid:
            messagebox.showwarning("تنبيه", "يرجى إدخال معرّف الجهاز (Machine ID / Device ID) أولاً.")
            return

        # Android Key
        k_and = generate_android_license_key(raw_mid)
        self.key_android_display.delete(0, "end")
        self.key_android_display.insert(0, k_and)

        # Windows Key
        k_win = generate_license_key(raw_mid)
        self.key_win_display.delete(0, "end")
        self.key_win_display.insert(0, k_win)

    def copy_key(self, text, title):
        k = str(text).strip()
        if k:
            self.clipboard_clear()
            self.clipboard_append(k)
            messagebox.showinfo("تم النسخ", f"تم نسخ {title} للحافظة بنجاح:\n\n{k}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # CLI Mode: python keygen.py <MACHINE_ID>
        input_mid = sys.argv[1].strip().upper()
        print(f"Device / Machine ID : {input_mid}")
        print(f"Android Key         : {generate_android_license_key(input_mid)}")
        print(f"Windows Key         : {generate_license_key(input_mid)}")
        print(f"Master Password     : {_MASTER_PASS}")
    else:
        app = KeygenApp()
        app.mainloop()
