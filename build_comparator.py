"""
build_comparator.py — Standalone Compiler for Price Comparator Application
Designed by: عبدالله الخطيب (Abdullah Al-Khatib)
"""

import os
import sys
import subprocess
import shutil
import time

def build():
    work_dir = r"c:\OdooDB"
    main_script = os.path.join(work_dir, "price_comparator_app.py")

    print("==================================================", flush=True)
    print("  Building Price Comparator & Competitor Suite    ", flush=True)
    print("==================================================", flush=True)

    # Terminate any running instances
    try:
        subprocess.run(["taskkill", "/F", "/IM", "PriceComparator.exe", "/T"], capture_output=True)
        time.sleep(1)
    except Exception:
        pass

    # Build PriceComparator.exe
    print("\nCompiling Standalone App (PriceComparator.exe)...", flush=True)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "PriceComparator",
        "--collect-all", "customtkinter",
        "--collect-all", "PIL",
        "--collect-all", "selenium",
        "--add-data", "assets;assets",
        "--hidden-import", "openpyxl",
        "--hidden-import", "cryptography",
        "--hidden-import", "xmlrpc.client",
        "--hidden-import", "licensing",
        "--hidden-import", "security",
        "--hidden-import", "odoo_product_lookup",
        "--hidden-import", "competitor_scraper",
        "--hidden-import", "price_intelligence",
        "--hidden-import", "auto_updater",
        "--hidden-import", "batch_excel_pricer",
        "--clean",
        main_script
    ]
    subprocess.run(cmd, cwd=work_dir, check=True)

    dist_exe = os.path.join(work_dir, "dist", "PriceComparator.exe")
    root_exe = os.path.join(work_dir, "PriceComparator.exe")
    rel_dir  = os.path.join(work_dir, "releases", "v1.00")
    os.makedirs(rel_dir, exist_ok=True)
    rel_exe  = os.path.join(rel_dir, "PriceComparator.exe")

    if os.path.exists(dist_exe):
        shutil.copy2(dist_exe, root_exe)
        shutil.copy2(dist_exe, rel_exe)

        # Also copy updated python sources to releases/v1.00
        for src in ["price_comparator_app.py", "competitor_scraper.py", "odoo_product_lookup.py", "price_intelligence.py", "batch_excel_pricer.py"]:
            src_path = os.path.join(work_dir, src)
            if os.path.exists(src_path):
                shutil.copy2(src_path, os.path.join(rel_dir, src))

        # Cleanup build and dist
        shutil.rmtree(os.path.join(work_dir, "build"), ignore_errors=True)
        shutil.rmtree(os.path.join(work_dir, "dist"), ignore_errors=True)
        spec_path = os.path.join(work_dir, "PriceComparator.spec")
        if os.path.exists(spec_path):
            os.remove(spec_path)

        sz_mb = round(os.path.getsize(rel_exe) / (1024 * 1024), 2)
        print("\n==================================================", flush=True)
        print("         BUILD COMPLETED SUCCESSFULLY!            ", flush=True)
        print("==================================================", flush=True)
        print(f"Executable (Releases): {rel_exe} ({sz_mb} MB)")
        print(f"Executable (Root)    : {root_exe} ({sz_mb} MB)")
        print("==================================================", flush=True)
    else:
        print("ERROR: dist/PriceComparator.exe not found!")

if __name__ == "__main__":
    build()
