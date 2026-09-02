import os
import sys
import subprocess
import shutil
import time
import customtkinter

def build():
    work_dir = r"c:\OdooDB"
    main_script = os.path.join(work_dir, "app_gui.py")
    keygen_script = os.path.join(work_dir, "keygen.py")

    print("==================================================", flush=True)
    print("  Building Standalone Protected Application       ", flush=True)
    print("==================================================", flush=True)

    # Terminate any running instances first
    try:
        subprocess.run(["taskkill", "/F", "/IM", "OdooReportExporter.exe", "/T"], capture_output=True)
        subprocess.run(["taskkill", "/F", "/IM", "Keygen_Admin.exe", "/T"], capture_output=True)
        time.sleep(1)
    except Exception:
        pass

    # 1. Build Main Application (OdooReportExporter.exe)
    print("\n[1/2] Compiling Main App (OdooReportExporter.exe)...", flush=True)
    cmd_main = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "OdooReportExporter",
        "--collect-all", "customtkinter",
        "--hidden-import", "openpyxl",
        "--hidden-import", "pandas",
        "--hidden-import", "cryptography",
        "--hidden-import", "xmlrpc.client",
        "--hidden-import", "permissions",
        "--hidden-import", "licensing",
        "--clean",
        main_script
    ]
    subprocess.run(cmd_main, cwd=work_dir, check=True)

    target_exe = os.path.join(work_dir, "OdooReportExporter.exe")
    dist_exe = os.path.join(work_dir, "dist", "OdooReportExporter.exe")
    if os.path.exists(dist_exe):
        shutil.copy2(dist_exe, target_exe)

    # 2. Build Admin Keygen Tool (Keygen_Admin.exe) for Abdullah Al-Khatib
    print("\n[2/2] Compiling Admin Key Generator (Keygen_Admin.exe)...", flush=True)
    cmd_keygen = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "Keygen_Admin",
        "--collect-all", "customtkinter",
        "--clean",
        keygen_script
    ]
    subprocess.run(cmd_keygen, cwd=work_dir, check=True)

    target_keygen = os.path.join(work_dir, "Keygen_Admin.exe")
    dist_keygen = os.path.join(work_dir, "dist", "Keygen_Admin.exe")
    if os.path.exists(dist_keygen):
        shutil.copy2(dist_keygen, target_keygen)

    print("\n==================================================", flush=True)
    print("         ALL BUILDS COMPLETED SUCCESSFULLY!       ", flush=True)
    print("==================================================", flush=True)
    print(f"1. Main Application  : {target_exe} ({round(os.path.getsize(target_exe)/(1024*1024), 2)} MB)")
    print(f"2. Admin Keygen Tool : {target_keygen} ({round(os.path.getsize(target_keygen)/(1024*1024), 2)} MB)")
    print("==================================================", flush=True)

if __name__ == "__main__":
    build()
