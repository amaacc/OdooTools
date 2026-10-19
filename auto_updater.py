"""
AutoUpdater Engine — Centralized Multi-App Automatic Updater for Windows Executables
Company: Al-Assali Trading Co. (شركة العسلي للتجارة)
Architect & Developer: Abdullah Al-Khatib (عبدالله الخطيب)
"""

import os
import sys
import json
import time
import shutil
import threading
import subprocess
import urllib.request
import urllib.error
import xmlrpc.client
from datetime import datetime

import customtkinter as ctk
from tkinter import messagebox

from security import get_odoo_credentials

MANIFEST_PARAM_KEY = "app.updates_manifest"

APP_DISPLAY_NAMES = {
    "OdooReportExporter": "📊 برنامج التقارير والمبيعات والمشتريات (OdooReportExporter)",
    "ShowroomChecker": "🏬 برنامج فحص رصيد واحتياج المعرض (ShowroomChecker)",
    "ShowroomChecker_Android": "📱 تطبيق فاحص المعرض للأندرويد (ShowroomChecker Android)",
    "ShelfChecker_Windows": "💻 تطبيق فحص الرف للويندوز (ShelfChecker PC)",
    "ShelfChecker": "📱 تطبيق فحص الرف للأندرويد (ShelfChecker Android)",
    "FastInventory": "📦 تطبيق الجرد السريع للأندرويد (FastInventory Android)",
    "OdooItemImporter": "📥 أداة تدقيق وتجهيز استيراد الأصناف (OdooItemImporter)",
    "PriceComparator": "🎯 مساعد التسعير ومراقبة المنافسين (PriceComparator)",
    "ShelfLabelPrinter": "🖨️ نظام طباعة ملصقات الرف (ShelfLabelPrinter)"
}


def _parse_version(v_str):
    """Parses version strings like 'v1.01', '1.2.0', '1.0' into numeric tuples."""
    if not v_str:
        return (0,)
    clean = str(v_str).strip().lower().lstrip("v")
    parts = []
    for p in clean.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def is_version_newer(remote_version, local_version):
    """Returns True if remote_version is strictly higher than local_version."""
    try:
        r = _parse_version(remote_version)
        l = _parse_version(local_version)
        # Pad shorter tuple with zeros
        max_len = max(len(r), len(l))
        r_padded = r + (0,) * (max_len - len(r))
        l_padded = l + (0,) * (max_len - len(l))
        return r_padded > l_padded
    except Exception:
        return False


def fetch_updates_manifest_from_odoo():
    """
    Fetches the JSON dictionary containing update specifications for all apps
    from Odoo ir.config_parameter ('app.updates_manifest').
    """
    try:
        url, db, user, pwd = get_odoo_credentials()
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(db, user, pwd, {})
        if not uid:
            return {}
        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
        raw = models.execute_kw(db, uid, pwd, "ir.config_parameter", "get_param", [MANIFEST_PARAM_KEY])
        if not raw or raw is False:
            return {}
        return json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else {})
    except Exception:
        return {}


def publish_updates_manifest_to_odoo(manifest_dict):
    """
    Saves the entire updates manifest dictionary back into Odoo ir.config_parameter.
    """
    url, db, user, pwd = get_odoo_credentials()
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
    uid = common.authenticate(db, user, pwd, {})
    if not uid:
        raise RuntimeError("فشل المصادقة مع سيرفر Odoo")
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
    models.execute_kw(
        db, uid, pwd,
        "ir.config_parameter", "set_param",
        [MANIFEST_PARAM_KEY, json.dumps(manifest_dict, ensure_ascii=False, indent=2)]
    )
    return True


def check_for_app_update(app_name, current_version):
    """
    Checks if a newer version of the specified app is available in Odoo manifest.
    Returns (has_update, update_info_dict).
    """
    manifest = fetch_updates_manifest_from_odoo()
    if not manifest or app_name not in manifest:
        return False, None

    info = manifest[app_name]
    latest_ver = info.get("latest_version", "")
    dl_url = info.get("download_url", "").strip()

    if not dl_url or not latest_ver:
        return False, None

    if is_version_newer(latest_ver, current_version):
        return True, info

    return False, info


# ─────────────────────────────────────────────────────────────────────────────
# 🖥️ Client UI: Non-Intrusive Prompt & Smooth In-Place Updater
# ─────────────────────────────────────────────────────────────────────────────
def check_and_prompt_update_async(parent, app_name, current_version, on_no_update=None):
    """
    Asynchronously checks for updates and displays the prompt dialog if a newer
    version is found. Safe to call during app startup without blocking UI.
    """
    def worker():
        try:
            has_update, update_info = check_for_app_update(app_name, current_version)
            if has_update and update_info:
                def show():
                    _show_update_modal(parent, app_name, current_version, update_info)
                parent.after(0, show)
            else:
                if on_no_update:
                    parent.after(0, on_no_update)
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


def _show_update_modal(parent, app_name, current_version, update_info):
    """Displays the custom update dialog in Arabic with release notes and action buttons."""
    latest_ver = update_info.get("latest_version", "v1.0")
    dl_url = update_info.get("download_url", "")
    notes = update_info.get("release_notes", "• تحسينات عامة في الأداء والاستقرار وتوافق البيانات.")
    is_mandatory = update_info.get("is_mandatory", False)
    rel_date = update_info.get("release_date", datetime.now().strftime("%Y-%m-%d"))

    dlg = ctk.CTkToplevel(parent)
    dlg.title(f"🚀 يتوفر تحديث جديد: {latest_ver}")
    dlg.geometry("540x480")
    dlg.resizable(False, False)
    dlg.grab_set()

    # Header Accent Frame
    hdr = ctk.CTkFrame(dlg, corner_radius=0, fg_color=("#0F766E", "#042F2E"), height=70)
    hdr.pack(fill="x")
    hdr.pack_propagate(False)

    ctk.CTkLabel(
        hdr,
        text="🚀 يتوفر إصدار جديد وجاهز للترقية",
        font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
        text_color="#5EEAD4"
    ).pack(pady=(12, 2))

    app_title = APP_DISPLAY_NAMES.get(app_name, app_name)
    ctk.CTkLabel(
        hdr,
        text=f"{app_title}  |  تاريخ الإطلاق: {rel_date}",
        font=ctk.CTkFont(family="Segoe UI", size=11),
        text_color="#CCFBF1"
    ).pack()

    # Version comparison badge row
    card = ctk.CTkFrame(dlg, corner_radius=10, fg_color=("#F8FAFC", "#1E293B"))
    card.pack(fill="both", expand=True, padx=16, pady=12)

    ver_row = ctk.CTkFrame(card, fg_color="transparent")
    ver_row.pack(fill="x", padx=14, pady=(12, 6))

    # Old version badge
    b_old = ctk.CTkFrame(ver_row, fg_color=("#E2E8F0", "#334155"), corner_radius=6)
    b_old.pack(side="right", padx=6)
    ctk.CTkLabel(b_old, text=f"الإصدار الحالي: {current_version}",
                 font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                 text_color=("#475569", "#94A3B8")).pack(padx=10, pady=4)

    ctk.CTkLabel(ver_row, text=" ⬅️ ", font=ctk.CTkFont(size=14)).pack(side="right")

    # New version badge
    b_new = ctk.CTkFrame(ver_row, fg_color=("#D1FAE5", "#064E3B"), corner_radius=6)
    b_new.pack(side="right", padx=6)
    ctk.CTkLabel(b_new, text=f"الإصدار الجديد: {latest_ver}",
                 font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                 text_color=("#065F46", "#6EE7B7")).pack(padx=10, pady=4)

    if is_mandatory:
        b_mand = ctk.CTkFrame(ver_row, fg_color=("#FEE2E2", "#7F1D1D"), corner_radius=6)
        b_mand.pack(side="left")
        ctk.CTkLabel(b_mand, text="⚠️ تحديث إلزامي",
                     font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                     text_color=("#991B1B", "#FCA5A5")).pack(padx=8, pady=4)

    # Release Notes
    ctk.CTkLabel(card, text="📝 ما الجديد في هذا الإصدار:",
                 font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")).pack(anchor="e", padx=14, pady=(6, 2))

    notes_box = ctk.CTkTextbox(card, height=140, font=ctk.CTkFont(family="Segoe UI", size=11))
    notes_box.pack(fill="both", expand=True, padx=14, pady=(0, 10))
    notes_box.insert("1.0", notes.strip())
    notes_box.configure(state="disabled")

    # Progress Area (Initially Hidden)
    prog_frame = ctk.CTkFrame(card, fg_color="transparent")
    lbl_progress = ctk.CTkLabel(prog_frame, text="جاري التجهيز للتحميل...",
                                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                                text_color="#0284C7")
    lbl_progress.pack(pady=(2, 4))
    prog_bar = ctk.CTkProgressBar(prog_frame, height=14, corner_radius=7, fg_color=("#CBD5E1", "#334155"),
                                  progress_color="#10B981")
    prog_bar.set(0)
    prog_bar.pack(fill="x", padx=10, pady=(0, 4))

    # Action Buttons Frame
    btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
    btn_row.pack(fill="x", padx=16, pady=(0, 14))

    def _start_download():
        btn_update.configure(state="disabled")
        if not is_mandatory and btn_skip:
            btn_skip.configure(state="disabled")
        prog_frame.pack(fill="x", padx=14, pady=(0, 8))

        def download_worker():
            try:
                # Prepare local temp path
                appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
                upd_dir = os.path.join(appdata, "AlAssaliOdooExporter", "updates")
                os.makedirs(upd_dir, exist_ok=True)
                tmp_exe = os.path.join(upd_dir, f"{app_name}_{latest_ver}.tmp")

                req = urllib.request.Request(
                    dl_url,
                    headers={"User-Agent": "AlAssali-AutoUpdater/1.0"}
                )

                with urllib.request.urlopen(req, timeout=60) as resp:
                    total_size = int(resp.headers.get("content-length", 0))
                    downloaded = 0
                    chunk_size = 65536
                    last_ui_update = 0

                    with open(tmp_exe, "wb") as f_out:
                        while True:
                            chunk = resp.read(chunk_size)
                            if not chunk:
                                break
                            f_out.write(chunk)
                            downloaded += len(chunk)

                            now = time.time()
                            if now - last_ui_update > 0.08 or downloaded == total_size:
                                last_ui_update = now
                                if total_size > 0:
                                    pct = downloaded / total_size
                                    mb_cur = downloaded / (1024 * 1024)
                                    mb_tot = total_size / (1024 * 1024)
                                    txt = f"جاري تحميل التحديث: {pct*100:.1f}% ({mb_cur:.1f} من {mb_tot:.1f} MB)"
                                else:
                                    pct = 0.5
                                    mb_cur = downloaded / (1024 * 1024)
                                    txt = f"جاري التحميل: {mb_cur:.1f} MB تم استلامها..."

                                def update_ui(p=pct, t=txt):
                                    prog_bar.set(p)
                                    lbl_progress.configure(text=t)
                                dlg.after(0, update_ui)

                # Download succeeded: trigger atomic swap & restart
                def trigger_swap():
                    lbl_progress.configure(text="✅ اكتمل التحميل! جاري تشغيل الإصدار الجديد فوراً...", text_color="#10B981")
                    dlg.after(600, lambda: _execute_atomic_swap_and_exit(tmp_exe))

                dlg.after(0, trigger_swap)

            except Exception as e:
                def on_fail(err_msg=str(e)):
                    prog_frame.pack_forget()
                    btn_update.configure(state="normal")
                    if not is_mandatory and btn_skip:
                        btn_skip.configure(state="normal")
                    messagebox.showerror(
                        "خطأ في التحميل",
                        f"تعذر استكمال تنزيل التحديث من السيرفر:\n\n{err_msg}\n\nيرجى التأكد من اتصال الإنترنت أو تجربة التحديث لاحقاً."
                    )
                dlg.after(0, on_fail)

        threading.Thread(target=download_worker, daemon=True).start()

    btn_update = ctk.CTkButton(
        btn_row,
        text="🚀  تحديث البرنامج والتشغيل التلقائي الآن",
        font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        fg_color="#059669",
        hover_color="#047857",
        height=40,
        command=_start_download
    )
    btn_update.pack(side="right", fill="x", expand=True, padx=(8, 0))

    btn_skip = None
    if not is_mandatory:
        btn_skip = ctk.CTkButton(
            btn_row,
            text="تذكيري لاحقاً",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=("#64748B", "#475569"),
            hover_color=("#475569", "#334155"),
            width=110,
            height=40,
            command=dlg.destroy
        )
        btn_skip.pack(side="left")


def _execute_atomic_swap_and_exit(tmp_new_exe):
    """
    Spawns an asynchronous PowerShell helper to wait for current process exit,
    swap the executable atomically, start the new version, and terminates current process.
    """
    target_exe = os.path.abspath(sys.argv[0])
    if not target_exe.lower().endswith(".exe"):
        # If running from raw python script, notify user
        messagebox.showinfo(
            "وضع التطوير (Python Source)",
            f"تم تنزيل حزمة التحديث بنجاح إلى:\n{tmp_new_exe}\n\nنظراً لتشغيل السكربت من كود بايثون مباشرة، لن يتم استبدال الملف تلقائياً."
        )
        return

    pid = os.getpid()

    # Generate companion PowerShell script
    appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
    swap_script = os.path.join(appdata, "AlAssaliOdooExporter", "updates", "swap_and_run.ps1")

    ps_code = f"""
# PowerShell In-Place Atomic App Replacer
$oldPid = {pid}
$target = "{target_exe}"
$newTmp = "{tmp_new_exe}"
$bak = "{target_exe}.bak"

# 1. Wait for parent process to exit
try {{
    $p = Get-Process -Id $oldPid -ErrorAction Stop
    $p.WaitForExit(15000)
}} catch {{}}
Start-Sleep -Milliseconds 600

# 2. Swap binary files with safety backup
try {{
    if (Test-Path -Path $target) {{
        Move-Item -Path $target -Destination $bak -Force -ErrorAction SilentlyContinue
    }}
    Move-Item -Path $newTmp -Destination $target -Force
    Start-Process -FilePath $target
    Start-Sleep -Seconds 2
    if (Test-Path -Path $bak) {{
        Remove-Item -Path $bak -Force -ErrorAction SilentlyContinue
    }}
}} catch {{
    # Rollback if move failed
    if (Test-Path -Path $bak) {{
        Move-Item -Path $bak -Destination $target -Force -ErrorAction SilentlyContinue
    }}
}}
"""
    with open(swap_script, "w", encoding="utf-8") as f:
        f.write(ps_code)

    # Launch PowerShell detached without any visible window
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-WindowStyle", "Hidden",
            "-ExecutionPolicy", "Bypass",
            "-File", swap_script
        ],
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )

    # Immediately exit current process cleanly
    os._exit(0)
