"""
showroom_config.py — Showroom Classification (معارض vs عناية) Management
Designed by: عبدالله الخطيب (Abdullah Al-Khatib)
"""

import os
import sys
import json

DEFAULT_CARE_KEYWORDS = ["الصفاء", "الصفا", "الطايف", "الطائف", "الحمدانية", "الحمدانيه", "سوق الشاطئ", "الشاطئ", "الشاطي"]
DEFAULT_CARE_CODES = ["106", "118", "120", "128"]
DEFAULT_WAREHOUSE_CODES = ["JEDMK", "JEDPE", "JEDHA", "RIY"]
DEFAULT_WAREHOUSE_KEYWORDS = ["مستودع"]

def _get_config_path():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    dir_path = os.path.join(appdata, "AlAssaliOdooExporter")
    os.makedirs(dir_path, exist_ok=True)
    return os.path.join(dir_path, "showroom_types.json")

def _get_local_config_path():
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), "showroom_types.json")
    return os.path.join(r"c:\OdooDB", "showroom_types.json")

def is_default_care_showroom(code, name):
    c_str = str(code or '').strip()
    n_str = str(name or '').strip()
    if c_str in DEFAULT_CARE_CODES:
        return True
    for kw in DEFAULT_CARE_KEYWORDS:
        if kw in n_str:
            return True
    return False

def is_default_warehouse(code, name):
    """Check if a warehouse code/name matches known warehouse patterns."""
    c_str = str(code or '').strip()
    n_str = str(name or '').strip()
    if c_str in DEFAULT_WAREHOUSE_CODES:
        return True
    for kw in DEFAULT_WAREHOUSE_KEYWORDS:
        if kw in n_str:
            return True
    return False

def load_showroom_types():
    """
    Returns dict mapping showroom key (e.g. str(code) or str(id) or name) to 'care', 'showroom', or 'warehouse'.
    """
    for path in [_get_config_path(), _get_local_config_path()]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
    return {}

def save_showroom_types(types_dict):
    """
    Saves showroom classifications persistently.
    """
    payload = json.dumps(types_dict, ensure_ascii=False, indent=2)
    saved = False
    for path in [_get_config_path(), _get_local_config_path()]:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(payload)
            saved = True
        except Exception:
            pass
    return saved

def get_showroom_category(s_code, s_name, custom_types_map=None):
    """
    Returns 'care', 'showroom', or 'warehouse'.
    """
    if custom_types_map is None:
        custom_types_map = load_showroom_types()

    c_str = str(s_code or '').strip()
    n_str = str(s_name or '').strip()

    # Check custom config by code, then by name
    if c_str and c_str in custom_types_map:
        return custom_types_map[c_str]
    if n_str and n_str in custom_types_map:
        return custom_types_map[n_str]

    # Fallback to default detection
    if is_default_warehouse(c_str, n_str):
        return "warehouse"
    if is_default_care_showroom(c_str, n_str):
        return "care"
    return "showroom"

