import os
import sys
import json
import winreg
import platform
import hashlib
import hmac
import uuid
from cryptography.fernet import Fernet

# Secret salt and Master override password for Abdullah Al-Khatib
_SECRET_SALT = b"AL_KHATIB_SECURE_ODOO_2026_PROD_SALT"
_MASTER_PASS = "KHATIB@MASTER#2026"
_FERNET_KEY = b"xW5_8jLq7E2mN0zV3rT6yP1uA9sD4fG8hJ2kL5nP7tQ="

def get_machine_id():
    """
    Retrieves a unique, immutable hardware fingerprint for the local Windows machine.
    """
    components = []
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
        guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        if guid:
            components.append(guid)
    except Exception:
        pass

    components.append(platform.node())
    components.append(platform.machine())
    components.append(str(uuid.getnode()))

    raw = "-".join(components)
    h = hashlib.sha256(raw.encode()).hexdigest().upper()
    return f"{h[:4]}-{h[4:8]}-{h[8:12]}-{h[12:16]}"

def generate_license_key(machine_id):
    """
    Generates a cryptographically signed license key specifically bound to the given machine ID.
    """
    clean_id = machine_id.strip().upper().replace(" ", "")
    h = hmac.new(_SECRET_SALT, clean_id.encode(), hashlib.sha256).hexdigest().upper()
    return f"{h[:4]}-{h[4:8]}-{h[8:12]}-{h[12:16]}"

def generate_android_license_key(device_id):
    """
    Generates a cryptographically signed license key specifically for Android devices (ShowroomChecker).
    Matches Android LicenseManager.kt (strips spaces and dashes).
    """
    clean_id = device_id.strip().upper().replace(" ", "").replace("-", "")
    h = hmac.new(_SECRET_SALT, clean_id.encode('utf-8'), hashlib.sha256).hexdigest().upper()
    return f"{h[:4]}-{h[4:8]}-{h[8:12]}-{h[12:16]}"

def verify_license_key(machine_id, input_key):
    """
    Verifies if the provided key is valid for this machine ID or matches the Master Password.
    Accepts keys with or without hyphens, case-insensitive, stripped of whitespace.
    """
    clean_k = input_key.strip().upper().replace(" ", "").replace("-", "")
    if not clean_k:
        return False
    clean_master = _MASTER_PASS.strip().upper().replace(" ", "").replace("-", "")
    if clean_k == clean_master or input_key.strip().upper() == _MASTER_PASS:
        return True
    expected = generate_license_key(machine_id).replace("-", "")
    return clean_k == expected

def verify_android_license_key(device_id, input_key):
    """
    Verifies Android license keys with or without hyphens.
    """
    clean_k = input_key.strip().upper().replace(" ", "").replace("-", "")
    if not clean_k:
        return False
    clean_master = _MASTER_PASS.strip().upper().replace(" ", "").replace("-", "")
    if clean_k == clean_master or input_key.strip().upper() == _MASTER_PASS:
        return True
    expected = generate_android_license_key(device_id).replace("-", "")
    return clean_k == expected

def _get_license_file_path():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    lic_dir = os.path.join(appdata, "AlAssaliOdooExporter")
    os.makedirs(lic_dir, exist_ok=True)
    return os.path.join(lic_dir, "license.dat")

def is_activated():
    """
    Checks if the local machine is currently activated with a valid license.
    Ensures that copying files to another machine will invalidate activation.
    """
    lic_file = _get_license_file_path()
    if not os.path.exists(lic_file):
        return False

    try:
        cipher = Fernet(_FERNET_KEY)
        with open(lic_file, "rb") as f:
            encrypted_data = f.read()
        decrypted = cipher.decrypt(encrypted_data)
        data = json.loads(decrypted.decode("utf-8"))

        saved_mid = data.get("machine_id", "")
        saved_key = data.get("license_key", "")
        current_mid = get_machine_id()

        # Machine ID mismatch protection
        if saved_mid != current_mid:
            return False

        return verify_license_key(current_mid, saved_key)
    except Exception:
        return False

def deactivate_device():
    """
    Removes the local license file to immediately deactivate the device.
    """
    lic_file = _get_license_file_path()
    try:
        if os.path.exists(lic_file):
            os.remove(lic_file)
        return True
    except Exception:
        return False

# ─────────────────────────────────────────────────────────────────────────────
# 🌐 Centralized Odoo Device Registry Integration
# ─────────────────────────────────────────────────────────────────────────────
import xmlrpc.client
from datetime import datetime

def fetch_device_status_from_odoo(device_id=None):
    """
    Checks the device's authorization status in Odoo's centralized device registry.
    Returns: 'active', 'blocked', 'not_found', or 'unknown' (if offline).
    """
    from security import get_odoo_credentials
    clean_id = (device_id or get_machine_id()).strip().upper()
    try:
        url, db, user, pwd = get_odoo_credentials()
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(db, user, pwd, {})
        if not uid:
            return "unknown"
        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
        raw = models.execute_kw(db, uid, pwd, "ir.config_parameter", "get_param", ["shelfchecker.device_registry"])
        if not raw or raw is False:
            return "not_found"
        registry = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else {})
        if clean_id in registry:
            return registry[clean_id].get("status", "active")
        return "not_found"
    except Exception:
        return "unknown"

def register_or_update_device_in_odoo(device_id=None, device_name=None, model=None, app_name="OdooReportExporter", app_version="v1.00"):
    """
    Registers a device or updates heartbeat/last_seen in Odoo's registry.
    Preserves 'blocked' status if the device has been revoked by admin.
    Returns the current device status ('active', 'blocked', or 'unknown').
    """
    from security import get_odoo_credentials
    clean_id = (device_id or get_machine_id()).strip().upper()
    default_name = os.environ.get("COMPUTERNAME", platform.node())
    default_model = f"{platform.system()} {platform.release()} ({platform.machine()})"
    dev_name = (device_name or default_name).strip()
    dev_model = (model or default_model).strip()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        url, db, user, pwd = get_odoo_credentials()
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(db, user, pwd, {})
        if not uid:
            return "unknown"
        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
        raw = models.execute_kw(db, uid, pwd, "ir.config_parameter", "get_param", ["shelfchecker.device_registry"])
        registry = json.loads(raw) if (raw and isinstance(raw, str)) else (raw if isinstance(raw, dict) else {})

        if clean_id in registry:
            dev_obj = registry[clean_id]
        else:
            dev_obj = {
                "device_id": clean_id,
                "registered_at": now_str,
                "status": "active"
            }

        if dev_name:
            dev_obj["device_name"] = dev_name
        elif not dev_obj.get("device_name"):
            dev_obj["device_name"] = default_name

        dev_obj["model"] = dev_model
        dev_obj["app_name"] = app_name
        dev_obj["app_version"] = app_version
        dev_obj["last_seen"] = now_str

        current_status = dev_obj.get("status", "active")
        registry[clean_id] = dev_obj

        models.execute_kw(
            db, uid, pwd,
            "ir.config_parameter", "set_param",
            ["shelfchecker.device_registry", json.dumps(registry, ensure_ascii=False)]
        )
        return current_status
    except Exception:
        return "unknown"

def activate_device(input_key, device_name=None, app_name="OdooReportExporter", app_version="v1.00"):
    """
    Verifies and saves activation for the current device, and registers with Odoo.
    If the device is marked 'blocked' in Odoo, activation is denied.
    """
    current_mid = get_machine_id()
    if not verify_license_key(current_mid, input_key):
        return False, "مفتاح التفعيل غير صحيح لهذا الجهاز."

    # Check remote Odoo blacklist status
    remote_status = fetch_device_status_from_odoo(current_mid)
    if remote_status == "blocked":
        return False, "🚫 هذا الجهاز محظور في نظام Odoo من قبل الإدارة. يرجى مراجعة المسؤول."

    try:
        lic_file = _get_license_file_path()
        cipher = Fernet(_FERNET_KEY)
        clean_key = input_key.strip().upper().replace(" ", "").replace("-", "")
        formatted_key = f"{clean_key[:4]}-{clean_key[4:8]}-{clean_key[8:12]}-{clean_key[12:16]}" if len(clean_key) == 16 else input_key.strip().upper()

        payload = json.dumps({
            "machine_id": current_mid,
            "license_key": formatted_key,
            "device_name": device_name or os.environ.get("COMPUTERNAME", platform.node()),
            "activated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }).encode("utf-8")

        encrypted = cipher.encrypt(payload)
        with open(lic_file, "wb") as f:
            f.write(encrypted)

        # Register in Odoo central registry (in thread or synchronously)
        try:
            register_or_update_device_in_odoo(
                device_id=current_mid,
                device_name=device_name,
                app_name=app_name,
                app_version=app_version
            )
        except Exception:
            pass

        return True, "تم تفعيل البرنامج بنجاح!"
    except Exception as e:
        return False, f"فشل حفظ التفعيل: {e}"

def fetch_device_info_from_odoo(device_id=None):
    """
    Fetches the specific device details dictionary from Odoo registry.
    """
    from security import get_odoo_credentials
    clean_id = (device_id or get_machine_id()).strip().upper()
    try:
        url, db, user, pwd = get_odoo_credentials()
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(db, user, pwd, {})
        if not uid:
            return None
        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
        raw = models.execute_kw(db, uid, pwd, "ir.config_parameter", "get_param", ["shelfchecker.device_registry"])
        if not raw or raw is False:
            return None
        registry = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else {})
        return registry.get(clean_id)
    except Exception:
        return None

def show_device_license_dialog(parent, app_name="OdooReportExporter", app_version="v1.00", on_deactivate=None, on_synced=None):
    """
    Opens a user-friendly modal dialog showing device ID, current Odoo status,
    and a 1-click button to synchronize/register with Odoo.
    """
    import threading
    from tkinter import messagebox
    import customtkinter as ctk

    dlg = ctk.CTkToplevel(parent)
    dlg.title("معلومات ترخيص هذا الجهاز والربط مع Odoo")
    dlg.geometry("520x460")
    dlg.resizable(False, False)
    dlg.grab_set()

    mid = get_machine_id()
    default_dname = os.environ.get("COMPUTERNAME", platform.node())

    ctk.CTkLabel(dlg, text="🔐 ترخيص الجهاز وإدارته عبر Odoo",
                 font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
                 text_color="#10B981").pack(pady=(18, 6))

    card = ctk.CTkFrame(dlg, corner_radius=10, fg_color=("#F1F5F9", "#1E293B"))
    card.pack(fill="both", expand=True, padx=20, pady=(0, 16))

    # Machine ID
    f_mid = ctk.CTkFrame(card, fg_color="transparent")
    f_mid.pack(fill="x", padx=16, pady=(14, 6))
    ctk.CTkLabel(f_mid, text="معرّف هذا الجهاز (Machine ID):",
                 font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold")).pack(anchor="e")
    
    mid_row = ctk.CTkFrame(f_mid, fg_color="transparent")
    mid_row.pack(fill="x", pady=2)

    e_mid = ctk.CTkEntry(mid_row, font=ctk.CTkFont("Consolas", 14, "bold"), justify="center", height=34)
    e_mid.insert(0, mid)
    e_mid.configure(state="readonly")
    e_mid.pack(side="right", fill="x", expand=True, padx=(8, 0))

    def _copy():
        dlg.clipboard_clear()
        dlg.clipboard_append(mid)
        messagebox.showinfo("تم النسخ", f"تم نسخ معرّف الجهاز للحافظة بنجاح:\n\n{mid}")

    ctk.CTkButton(mid_row, text="📋 نسخ", width=75, height=34, command=_copy).pack(side="left")

    # Device Name in Odoo
    f_name = ctk.CTkFrame(card, fg_color="transparent")
    f_name.pack(fill="x", padx=16, pady=6)
    ctk.CTkLabel(f_name, text="اسم المعرض أو الموظف في Odoo:",
                 font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold")).pack(anchor="e")
    e_name = ctk.CTkEntry(f_name, font=ctk.CTkFont(family="Segoe UI", size=11), justify="right", height=34)
    e_name.insert(0, default_dname)
    e_name.pack(fill="x", pady=2)

    # Status Label
    lbl_status = ctk.CTkLabel(card, text="جاري فحص حالة الجهاز في Odoo...",
                              font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                              text_color="#F59E0B")
    lbl_status.pack(pady=8)

    def _fetch_info():
        info = fetch_device_info_from_odoo(mid)
        if info:
            st = info.get("status", "active")
            d_name = info.get("device_name", default_dname)
            seen = info.get("last_seen", "غير معروف")
            e_name.delete(0, "end")
            e_name.insert(0, d_name)
            if st == "blocked":
                lbl_status.configure(text=f"🔴 هذا الجهاز محظور في Odoo! (آخر ظهور: {seen})", text_color="#EF4444")
            else:
                lbl_status.configure(text=f"🟢 مسجل ومفعل في Odoo بنجاح (آخر اتصال: {seen})", text_color="#10B981")
        else:
            lbl_status.configure(text="⚪ هذا الجهاز غير مضاف بعد في Odoo (اضغط زر المزامنة للإضافة الآن)", text_color="#94A3B8")

    threading.Thread(target=_fetch_info, daemon=True).start()

    # Sync Button
    def _do_sync():
        d_name = e_name.get().strip() or default_dname
        lbl_status.configure(text="جاري المزامنة مع Odoo...", text_color="#38BDF8")
        btn_sync.configure(state="disabled")

        def worker():
            try:
                st = register_or_update_device_in_odoo(
                    device_id=mid,
                    device_name=d_name,
                    app_name=app_name,
                    app_version=app_version
                )
                def on_done():
                    btn_sync.configure(state="normal")
                    _fetch_info()
                    if on_synced:
                        try:
                            on_synced()
                        except Exception:
                            pass
                    messagebox.showinfo("تمت المزامنة", f"✅ تم تسجيل وتحديث هذا الجهاز بنجاح في Odoo!\n\nاسم الجهاز: {d_name}\nالتطبيق: {app_name}\nالحالة: {st}")
                dlg.after(0, on_done)
            except Exception as e:
                def on_err():
                    btn_sync.configure(state="normal")
                    messagebox.showerror("خطأ", f"تعذر الاتصال بـ Odoo:\n{e}")
                dlg.after(0, on_err)

        threading.Thread(target=worker, daemon=True).start()

    btn_sync = ctk.CTkButton(card, text="🔄 مزامنة وتسجيل هذا الجهاز في Odoo الآن",
                             font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                             fg_color="#059669", hover_color="#047857", height=38, command=_do_sync)
    btn_sync.pack(fill="x", padx=16, pady=8)

    # Deactivate / Clear License Button
    def _do_deactivate():
        if not messagebox.askyesno("تأكيد إلغاء التفعيل", "هل أنت متأكد من إلغاء تفعيل هذا الجهاز وإعادته لشاشة الترخيص؟"):
            return
        deactivate_device()
        dlg.destroy()
        if on_deactivate:
            on_deactivate()
        else:
            messagebox.showinfo("تم الإلغاء", "تم مسح ملف الترخيص المحلي من هذا الجهاز.")

    ctk.CTkButton(card, text="🗑️ إلغاء تفعيل هذا الجهاز محلياً",
                  font=ctk.CTkFont(family="Segoe UI", size=11),
                  fg_color="#7F1D1D", hover_color="#991B1B", height=30, command=_do_deactivate).pack(padx=16, pady=(4, 10))

if __name__ == "__main__":
    mid = get_machine_id()
    print("Machine ID:", mid)
    print("Activation Key:", generate_license_key(mid))
    print("Is Activated:", is_activated())
    print("Odoo Status:", fetch_device_status_from_odoo(mid))
