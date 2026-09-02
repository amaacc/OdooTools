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

def verify_license_key(machine_id, input_key):
    """
    Verifies if the provided key is valid for this machine ID or matches the Master Password.
    """
    clean_k = input_key.strip().upper().replace(" ", "")
    if clean_k == _MASTER_PASS:
        return True
    expected = generate_license_key(machine_id)
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

def activate_device(input_key):
    """
    Verifies and saves activation for the current device.
    """
    current_mid = get_machine_id()
    if not verify_license_key(current_mid, input_key):
        return False, "مفتاح التفعيل غير صحيح لهذا الجهاز."

    try:
        lic_file = _get_license_file_path()
        cipher = Fernet(_FERNET_KEY)
        payload = json.dumps({
            "machine_id": current_mid,
            "license_key": input_key.strip().upper(),
            "activated_at": str(os.path.getmtime(lic_file) if os.path.exists(lic_file) else "")
        }).encode("utf-8")

        encrypted = cipher.encrypt(payload)
        with open(lic_file, "wb") as f:
            f.write(encrypted)

        return True, "تم تفعيل البرنامج بنجاح!"
    except Exception as e:
        return False, f"فشل حفظ التفعيل: {e}"

if __name__ == "__main__":
    mid = get_machine_id()
    print("Machine ID:", mid)
    print("Activation Key:", generate_license_key(mid))
    print("Is Activated:", is_activated())
