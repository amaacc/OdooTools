"""
company_profile.py
Manages official company profile metadata (Name, Tax ID, CR, Address, Phone, Email, Logo)
used in official reports, printouts, and claim forms.
"""

import os
import sys
import json

def get_config_dir():
    d = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "AlAssaliOdooExporter")
    os.makedirs(d, exist_ok=True)
    return d

def get_profile_path():
    return os.path.join(get_config_dir(), "company_profile.json")

def get_default_logo_path():
    candidates = []
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        candidates.append(os.path.join(sys._MEIPASS, "assets", "AssaliLogoColor.png"))
        candidates.append(os.path.join(sys._MEIPASS, "assets", "company_logo.png"))
    candidates.extend([
        r"c:\OdooDB\AssaliLogoColor.png",
        r"c:\OdooDB\assets\AssaliLogoColor.png",
        r"c:\OdooDB\assets\company_logo.png",
        os.path.join(os.path.dirname(__file__), "assets", "AssaliLogoColor.png"),
        os.path.join(os.path.dirname(__file__), "AssaliLogoColor.png"),
    ])
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)
    return ""

DEFAULT_PROFILE = {
    "name_ar": "شركة العسلي التجارية",
    "name_en": "Al-Assali Trading Company",
    "cr_number": "4030127564",
    "tax_id": "310902438900003",
    "phone": "",
    "email": "",
    "address": "المملكة العربية السعودية - جدة - البلد – شارع الملك عبدالعزيز – عمارة الملكة الدور السابع",
    "logo_path": get_default_logo_path()
}

def load_company_profile():
    p = get_profile_path()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                res = DEFAULT_PROFILE.copy()
                # If logo_path in data doesn't exist on disk, fallback to default logo
                if not data.get("logo_path") or not os.path.exists(data.get("logo_path", "")):
                    data["logo_path"] = get_default_logo_path()
                res.update(data)
                return res
        except Exception:
            pass
    return DEFAULT_PROFILE.copy()

def save_company_profile(profile_dict):
    p = get_profile_path()
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(profile_dict, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving company profile: {e}")
        return False
