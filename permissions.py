import os
import json
import hashlib
from cryptography.fernet import Fernet

_PERM_KEY = b"k9L_2mN8vX4rT7yP1uA3sD5fG7hJ9kL2nP4tQ6wE8rT="
_DEFAULT_ADMIN_HASH = hashlib.sha256(b"Abd@15021974").hexdigest()
_MASTER_PASS = "KHATIB@MASTER#2026"

def encrypt_admin_password(plain_pwd: str) -> str:
    """
    Encrypts a plain text password into an AES-128-CBC / Fernet ciphertext.
    Ensures passwords are never stored in cleartext in Odoo ir.config_parameter.
    """
    if not plain_pwd:
        return ""
    plain = str(plain_pwd).strip()
    try:
        cipher = Fernet(_PERM_KEY)
        cipher.decrypt(plain.encode("utf-8"))
        return plain
    except Exception:
        pass

    try:
        cipher = Fernet(_PERM_KEY)
        return cipher.encrypt(plain.encode("utf-8")).decode("utf-8")
    except Exception:
        return plain

def decrypt_admin_password(ciphertext: str) -> str:
    """
    Decrypts an AES-128-CBC / Fernet ciphertext back to cleartext.
    If the input is legacy cleartext, returns it as-is.
    """
    if not ciphertext:
        return ""
    text = str(ciphertext).strip()
    try:
        cipher = Fernet(_PERM_KEY)
        return cipher.decrypt(text.encode("utf-8")).decode("utf-8")
    except Exception:
        return text

ALL_PROTECTED_FIELDS = [
    ("Cost", "سعر التكلفة (Cost)"),
    ("Sales Price", "سعر البيع (Sales Price)"),
    ("Shati Price", "سعر الشاطئ (Shati Price)"),
    ("SO Price", "سعر أمر البيع (SO Price)"),
    ("Pos Minimum Price", "الحد الأدنى لسعر الكاشير (POS Min Price)"),
    ("Quantity On Hand", "إجمالي رصيد المخزون (Quantity On Hand)"),
    ("365d Sold", "إجمالي مبيعات 365 يوم (365d Sold)"),
    ("Vendors", "اسم المورد (Vendors)"),
    ("Vendors/Price", "سعر المورد (Vendors/Price)"),
    ("Vendors/Discount (%)", "نسبة خصم المورد (Vendors/Discount)"),
    ("Vendors/Discounted Price", "السعر بعد الخصم (Discounted Price)"),
    ("Vendors/Last Purchase", "تاريخ آخر عملية شراء (Last Purchase)"),
    ("Vendors/Last Updated on", "تاريخ آخر تحديث للمورد (Last Updated on)"),
    ("Last Received Qty", "الكمية المستلمة في آخر شراء (Last Received Qty)"),
    ("Showrooms_OnHand", "أرصدة المعارض التفصيلية (Showrooms On Hand)"),
    ("Showrooms_Sold", "مبيعات المعارض التفصيلية (Showrooms Sold)"),
    ("Warehouses_OnHand", "أرصدة المستودعات التفصيلية (Warehouses On Hand)"),
    ("تصنيف ABC", "تصنيف باريتو للمنتجات (ABC Classification)"),
    ("أيام التغطية", "أيام تغطية المخزون (Days of Inventory)"),
    ("حالة الصنف", "حالة الصنف (Item Status)"),
    ("الطلب المقترح (60 يوم)", "الطلب المقترح 60 يوم (Suggested Order)"),
    ("قيمة الطلب المقترح", "قيمة الطلب المقترح بالريال (Suggested Order Value)"),
    ("توصيات المناقلة", "توصيات المناقلة بين المعارض (Transfer Recs)"),
    ("خصم البيع", "خصم البيع من قائمة الأسعار (Pricelist Discount)"),
    ("نوع احتساب الخصم", "نوع احتساب الخصم (Discount Computation)"),
    ("وسم قاعدة الخصم", "وسم قاعدة الخصم (Pricelist Rule Tag)"),
    ("التكلفة الفعلية", "التكلفة الفعلية (Actual Cost)"),
    ("هامش الربح الفعلي (%)", "نسبة هامش الربح الفعلي بدون ضريبة (Actual Margin %)"),
    ("السعر الجديد", "السعر الجديد المقترح شامل الضريبة (New Suggested Price)"),
    ("Internal Notes", "الملاحظات الداخلية للصنف (Internal Notes)"),
    ("Price_Comparator", "مساعد التسعير ومقارنة المنافسين (Price Comparator)"),
    ("Purchase_Reports", "منظومة تقارير المشتريات والتوريد الذكي (Purchase Suite)"),
    ("Purchase_Price_Variance", "تقرير رقابة تغير أسعار الموردين (Price Variance)"),
    ("id", "المعرف الخارجي من أودو (__export__.product_template_...)")
]

def _get_perm_file_path():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    dir_path = os.path.join(appdata, "AlAssaliOdooExporter")
    os.makedirs(dir_path, exist_ok=True)
    return os.path.join(dir_path, "permissions.dat")

def get_default_permissions():
    # Regular reporting fields default to True, but Price_Comparator and id default to False (admin activation required)
    perms = {field_id: True for field_id, _ in ALL_PROTECTED_FIELDS}
    perms["Price_Comparator"] = False
    perms["id"] = False
    return perms

def load_permissions():
    """
    Loads permissions securely. If no file exists, returns default.
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
        if "Sold" in perms and "365d Sold" not in perms:
            perms["365d Sold"] = perms["Sold"]
        for f_id, _ in ALL_PROTECTED_FIELDS:
            if f_id not in perms:
                perms[f_id] = False if f_id in ("Price_Comparator", "id") else True
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

def sync_permissions_from_odoo(device_id=None):
    """
    Syncs permissions and admin password from Odoo centralized registry.
    If the admin specified custom permissions or changed the password in Odoo,
    this overrides local settings and ensures the admin maintains total authority.
    Returns (synced_bool, permissions_dict).
    """
    import xmlrpc.client
    from security import get_odoo_credentials
    from licensing import get_machine_id

    clean_id = (device_id or get_machine_id()).strip().upper()
    try:
        url, db, user, pwd = get_odoo_credentials()
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(db, user, pwd, {})
        if not uid:
            perms, _ = load_permissions()
            return False, perms

        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
        raw = models.execute_kw(db, uid, pwd, "ir.config_parameter", "get_param", ["shelfchecker.device_registry"])
        if not raw or raw is False:
            perms, _ = load_permissions()
            return False, perms

        registry = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else {})
        dev_info = registry.get(clean_id)
        if not dev_info:
            perms, _ = load_permissions()
            return False, perms

        remote_perms = dev_info.get("permissions")
        remote_pwd = dev_info.get("admin_password")

        current_perms, current_hash = load_permissions()
        updated = False

        if remote_perms and isinstance(remote_perms, dict):
            # Merge remote perms into current
            merged_perms = current_perms.copy()
            merged_perms.update(remote_perms)
            current_perms = merged_perms
            updated = True

        if remote_pwd:
            # Enforce admin password from Odoo (overriding any local changes by user)
            plain_pwd = decrypt_admin_password(str(remote_pwd).strip())
            save_permissions(current_perms, new_admin_password=plain_pwd)
            updated = True
        elif updated:
            save_permissions(current_perms)

        return updated, current_perms
    except Exception:
        perms, _ = load_permissions()
        return False, perms

def set_device_permissions_in_odoo(device_id, permissions_dict, admin_password=None):
    """
    Admin utility to write permissions and/or custom admin password for a device into Odoo.
    """
    import xmlrpc.client
    from security import get_odoo_credentials

    clean_id = device_id.strip().upper()
    try:
        url, db, user, pwd = get_odoo_credentials()
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(db, user, pwd, {})
        if not uid:
            return False, "فشل المصادقة مع سيرفر Odoo"

        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
        raw = models.execute_kw(db, uid, pwd, "ir.config_parameter", "get_param", ["shelfchecker.device_registry"])
        registry = json.loads(raw) if (raw and isinstance(raw, str)) else (raw if isinstance(raw, dict) else {})

        if clean_id not in registry:
            return False, "الجهاز غير مسجل في Odoo بعد"

        dev_obj = registry[clean_id]
        dev_obj["permissions"] = permissions_dict
        if admin_password is not None and str(admin_password).strip():
            dev_obj["admin_password"] = encrypt_admin_password(str(admin_password).strip())
        registry[clean_id] = dev_obj

        models.execute_kw(
            db, uid, pwd,
            "ir.config_parameter", "set_param",
            ["shelfchecker.device_registry", json.dumps(registry, ensure_ascii=False)]
        )
        return True, "تم حفظ الصلاحيات وكلمة المرور في Odoo بنجاح"
    except Exception as e:
        return False, f"حدث خطأ أثناء الحفظ في Odoo: {e}"

if __name__ == "__main__":
    perms, h = load_permissions()
    print("Loaded Permissions:", perms)
    print("Admin verification test:", verify_admin_password("KHATIB@ADMIN#2026"))
