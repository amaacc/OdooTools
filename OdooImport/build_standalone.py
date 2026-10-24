import os
import sys
import shutil
import subprocess
import customtkinter

base_dir = os.path.dirname(os.path.abspath(__file__))
customtkinter_dir = os.path.dirname(customtkinter.__file__)

output_dir = os.path.join(base_dir, "dist")
releases_dir = r"c:\OdooDB\releases\v1.00"

print("==================================================")
print("[*] Starting PyInstaller Standalone Build (Single File)")
print("==================================================")

# Terminate any running instances first
try:
    subprocess.run(["taskkill", "/F", "/IM", "OdooItemImporter.exe", "/T"], capture_output=True)
except Exception:
    pass

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm",
    "--onefile",
    "--windowed",
    "--name", "OdooItemImporter",
    "--paths", r"c:\OdooDB",
    "--paths", base_dir,
    "--collect-all", "cryptography",
    "--collect-all", "customtkinter",
    "--collect-all", "openpyxl",
    "--hidden-import", "cryptography",
    "--hidden-import", "cryptography.fernet",
    "--hidden-import", "security",
    "--hidden-import", "xmlrpc.client",
    "--hidden-import", "openpyxl",
    "--hidden-import", "auto_updater",
    f"--add-data={customtkinter_dir};customtkinter",
    f"--add-data={os.path.join(base_dir, 'config.json')};.",
    f"--add-data={os.path.join(base_dir, 'importer_config.json')};.",
    f"--add-data={os.path.join(base_dir, 'odoo_verifier.py')};.",
    f"--add-data={os.path.join(base_dir, 'import_engine.py')};.",
    f"--add-data={os.path.join(base_dir, 'rules_dialog.py')};.",
    f"--add-data={os.path.join(base_dir, 'security.py')};.",
    os.path.join(base_dir, "app_gui.py")
]

print("Executing command:", " ".join(cmd))
res = subprocess.run(cmd, cwd=base_dir)

if res.returncode == 0:
    print("\n[+] Build succeeded!")
    built_exe = os.path.join(output_dir, "OdooItemImporter.exe")
    if os.path.exists(built_exe):
        print(f"Target executable: {built_exe} ({os.path.getsize(built_exe) / (1024*1024):.1f} MB)")
        
        # Ensure releases directory exists
        os.makedirs(releases_dir, exist_ok=True)
        
        # 1. Target release folder
        target_folder = os.path.join(releases_dir, "OdooItemImporter")
        os.makedirs(target_folder, exist_ok=True)
        shutil.copy2(built_exe, os.path.join(target_folder, "OdooItemImporter.exe"))
        shutil.copy2(os.path.join(base_dir, "config.json"), os.path.join(target_folder, "config.json"))
        shutil.copy2(os.path.join(base_dir, "importer_config.json"), os.path.join(target_folder, "importer_config.json"))
        
        # 2. Standalone root release file (so user can just grab the single exe)
        shutil.copy2(built_exe, os.path.join(releases_dir, "OdooItemImporter.exe"))
        shutil.copy2(os.path.join(base_dir, "importer_config.json"), os.path.join(releases_dir, "importer_config.json"))
        shutil.copy2(built_exe, r"c:\OdooDB\OdooItemImporter.exe")
        
        # 3. Create a clean ZIP archive for sharing
        zip_base = os.path.join(releases_dir, "OdooItemImporter_Portable")
        shutil.make_archive(zip_base, 'zip', target_folder)
        print(f"[+] Created release folder: {target_folder}")
        print(f"[+] Created standalone exe: {os.path.join(releases_dir, 'OdooItemImporter.exe')}")
        print(f"[+] Created ZIP package: {zip_base}.zip")
else:
    print(f"\n[-] Build failed with exit code: {res.returncode}")
