"""
إدارة إعدادات تطبيق طباعة ملصقات الأرفف (Config Manager)
يحفظ الإعدادات في ملف config.json الدائم بجانب البرنامج:
- مسارات الشعارين (شعار 1 وشعار 2)
- خيارات الطباعة وعلامات القص
- الطابعة الافتراضية
"""
import os
import json
from typing import Dict, Any
from path_utils import get_app_dir, get_resource_path

DEFAULT_CONFIG_PATH = os.path.join(get_app_dir(), "config.json")

DEFAULT_LOGO_1 = get_resource_path(os.path.join("assets", "logos", "AssaliLogoColor.png"))
DEFAULT_LOGO_2 = get_resource_path(os.path.join("assets", "logos", "company_logo.png"))

DEFAULT_SETTINGS = {
    "logo1_path": DEFAULT_LOGO_1 if os.path.exists(DEFAULT_LOGO_1) else "",
    "logo2_path": DEFAULT_LOGO_2 if os.path.exists(DEFAULT_LOGO_2) else "",
    "paper_type": "a4",
    "start_position": 1,
    "draw_cut_guides": True,
    "draw_roll_border": False,
    "selected_printer_a4": "[الطابعة الافتراضية للنظام]",
    "selected_printer_roll": "",
    "default_printer": "",
    "auto_clear_after_print": False
}

class ConfigManager:
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        self.settings: Dict[str, Any] = self.load()

    def load(self) -> Dict[str, Any]:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    merged = dict(DEFAULT_SETTINGS)
                    merged.update(data)
                    return merged
            except Exception as e:
                print(f"[ConfigManager] Error loading config: {e}")
        return dict(DEFAULT_SETTINGS)

    def save(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[ConfigManager] Error saving config: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def set(self, key: str, value: Any):
        self.settings[key] = value
        self.save()
