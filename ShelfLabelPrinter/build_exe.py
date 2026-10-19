"""
سكربت بناء البرنامج التنفيذي المستقل (ShelfLabelPrinter.exe)
يستخدم PyInstaller لتجميع كل ملفات بايثون والمكتبات والواجهات والشعارات في ملف تشغيلي واحد يعمل على أي جهاز ويندوز بدون الحاجة لتثبيت بايثون.
"""
import os
import sys
import shutil
import subprocess
import PyInstaller.__main__
from PyInstaller.utils.hooks import collect_all

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(CURRENT_DIR, "assets")
ICON_PATH = os.path.join(ASSETS_DIR, "app_icon.ico")

def build():
    print("=== Starting PyInstaller build for ShelfLabelPrinter ===")

    # تجهيز الوسائط
    datas = [
        (ASSETS_DIR, "assets")
    ]
    
    # تجميع ملفات customtkinter
    ctk_datas, ctk_binaries, ctk_hidden = collect_all("customtkinter")
    
    # بناء أمر PyInstaller
    cmd_args = [
        os.path.join(CURRENT_DIR, "main.py"),
        "--name=ShelfLabelPrinter",
        "--noconsole",
        "--onefile",
        f"--icon={ICON_PATH}",
        f"--add-data={ASSETS_DIR};assets",
        "--collect-all=customtkinter",
        "--hidden-import=PIL",
        "--hidden-import=PIL.Image",
        "--hidden-import=PIL.ImageDraw",
        "--hidden-import=PIL.ImageFont",
        "--hidden-import=cryptography",
        "--hidden-import=cryptography.fernet",
        "--hidden-import=winsound",
        "--hidden-import=win32print",
        "--hidden-import=win32api",
        "--hidden-import=win32con",
        "--hidden-import=auto_updater",
        "--hidden-import=security",
        "--paths=c:\\OdooDB",
        "--clean",
        f"--workpath={os.path.join(CURRENT_DIR, 'build')}",
        f"--distpath={os.path.join(CURRENT_DIR, 'dist')}",
        f"--specpath={CURRENT_DIR}"
    ]

    print("Running PyInstaller...")
    PyInstaller.__main__.run(cmd_args)

    dist_exe = os.path.join(CURRENT_DIR, "dist", "ShelfLabelPrinter.exe")
    if os.path.exists(dist_exe):
        size_mb = os.path.getsize(dist_exe) / (1024 * 1024)
        print(f"\n[SUCCESS] Build completed successfully!")
        print(f"Path: {dist_exe}")
        print(f"Size: {size_mb:.2f} MB")
        
        # Copy to root directory for easy access
        target_root_exe = os.path.join(CURRENT_DIR, "ShelfLabelPrinter.exe")
        shutil.copy2(dist_exe, target_root_exe)
        print(f"[COPIED] Copied executable to root folder: {target_root_exe}")
    else:
        print("\n[ERROR] Output executable not found!")

if __name__ == "__main__":
    build()
