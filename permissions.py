import os
import json
import hashlib
from cryptography.fernet import Fernet

_PERM_KEY = b"k9L_2mN8vX4rT7yP1uA3sD5fG7hJ9kL2nP4tQ6wE8rT="
_DEFAULT_ADMIN_HASH = hashlib.sha256(b"Abd@15021974").hexdigest()
_MASTER_PASS = "KHATIB@MASTER#2026"

ALL_PROTECTED_FIELDS = [
    ("Cost", "سعر التكلفة (Cost)"),
    ("Sales Price", "سعر البيع (Sales Price)"),
    ("Shati Price", "سعر الشاطئ (Shati Price)"),
    ("SO Price", "سعر أمر البيع (SO Price)"),
    ("Pos Minimum Price", "الحد الأدنى لسعر الكاشير (POS Min Price)"),
    ("Quantity On Hand", "إجمالي رصيد المخزون (Quantity On Hand)"),
    ("Sold", "إجمالي المبيعات العامة (Sold)"),
    ("Vendors", "اسم المورد (Vendors)"),
    ("Vendors/Price", "سعر المورد (Vendors/Price)"),
    ("Vendors/Discount (%)", "نسبة خصم المورد (Vendors/Discount)"),
    ("Vendors/Discounted Price", "السعر بعد الخصم (Discounted Price)"),
    ("Vendors/Last Purchase", "تاريخ آخر عملية شراء (Last Purchase)"),
    ("Vendors/Last Updated on", "تاريخ آخر تحديث للمورد (Last Updated on)"),
    ("Last Received Qty", "الكمية المستلمة في آخر شراء (Last Received Qty)"),
    ("Showrooms_OnHand", "أرصدة المعارض التفصيلية (Showrooms On Hand)"),
    ("Showrooms_Sold", "مبيعات المعارض التفصيلية (Showrooms Sold)")
]

def _get_perm_file_path():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    dir_path = os.path.join(appdata, "AlAssaliOdooExporter")
    os.makedirs(dir_path, exist_ok=True)
    return os.path.join(dir_path, "permissions.dat")

def get_default_permissions():
    # All fields are OFF by default — admin must explicitly enable them
    return {field_id: False for field_id, _ in ALL_PROTECTED_FIELDS}

def load_permissions():
    """
    Loads permissions securely. If no file exists, returns default (all OFF).
    """
    perm_file = _get_perm_file_path()
    if not os.path.exists(perm_file):
        return get_default_permissions(), _DEFAULT_ADMIN_HASH

    try:
        cipher = Fernet(_PERM_KEY)
        with open(perm_file, "rb") as f:
            encrypted_data = f.read()
        decrypted = cipher.decrypt(encrypted_data)
        data = json.loads(decrypted.decode("utf-8"))
        perms = data.get("permissions", get_default_permissions())
        admin_hash = data.get("admin_hash", _DEFAULT_ADMIN_HASH)
        return perms, admin_hash
    except Exception:
        return get_default_permissions(), _DEFAULT_ADMIN_HASH

def save_permissions(permissions_dict, new_admin_password=None):
    """
    Saves encrypted permissions and optionally updates admin password.
    """
    _, current_hash = load_permissions()
    admin_hash = current_hash
    if new_admin_password:
        admin_hash = hashlib.sha256(new_admin_password.strip().encode("utf-8")).hexdigest()

    perm_file = _get_perm_file_path()
    cipher = Fernet(_PERM_KEY)
    payload = json.dumps({
        "permissions": permissions_dict,
        "admin_hash": admin_hash
    }).encode("utf-8")

    encrypted = cipher.encrypt(payload)
    with open(perm_file, "wb") as f:
        f.write(encrypted)
    return True

def verify_admin_password(input_password):
    """
    Verifies input password against stored admin password hash or emergency master.
    """
    if input_password == _MASTER_PASS:
        return True
    _, stored_hash = load_permissions()
    input_hash = hashlib.sha256(input_password.strip().encode("utf-8")).hexdigest()
    return input_hash == stored_hash

if __name__ == "__main__":
    perms, h = load_permissions()
    print("Loaded Permissions:", perms)
    print("Admin verification test:", verify_admin_password("KHATIB@ADMIN#2026"))
