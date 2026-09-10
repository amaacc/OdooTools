"""
company_profile.py
Manages official company profile metadata (Name, Tax ID, CR, Address, Phone, Email, Logo)
used in official reports, printouts, and claim forms.
"""

import os
import json

def get_config_dir():
    d = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "AlAssaliOdooExporter")
    os.makedirs(d, exist_ok=True)
    return d

def get_profile_path():
    return os.path.join(get_config_dir(), "company_profile.json")

DEFAULT_PROFILE = {
    "name_ar": "شركة فهد إبراهيم العسلي للتجارة",
    "name_en": "Fahad Ibrahim Al-Assali Trading Co.",
    "tax_id": "300000000000003",
    "cr_number": "1010000000",
    "phone": "",
    "email": "",
    "address": "المملكة العربية السعودية - الرياض",
    "logo_path": r"c:\OdooDB\assets\company_logo.png" if os.path.exists(r"c:\OdooDB\assets\company_logo.png") else ""
}

def load_company_profile():
    p = get_profile_path()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                res = DEFAULT_PROFILE.copy()
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
