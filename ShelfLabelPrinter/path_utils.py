"""
مساعد إدارة مسارات الملفات والموارد لبيئة التطوير والبرنامج التنفيذي المجمد (Frozen Executable / PyInstaller)
"""
import os
import sys

def get_app_dir() -> str:
    """إرجاع المسار الفعلي الدائم للتطبيق (المجلد الذي يحتوي الملف التنفيذي أو السكربت)"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_resource_path(relative_path: str) -> str:
    """
    إرجاع مسار المورد (صور، خطوط، قوالب).
    يبحث أولاً بجانب الملف التنفيذي، وإذا لم يجده يبحث في مجلد الحزمة المستخرجة مؤقتاً (sys._MEIPASS).
    """
    # 1. البحث في المجلد الخارجي للتطبيق
    app_dir_path = os.path.join(get_app_dir(), relative_path)
    if os.path.exists(app_dir_path):
        return app_dir_path

    # 2. البحث في حزمة PyInstaller المدمجة داخل الـ EXE
    if getattr(sys, "frozen", False):
        base_path = getattr(sys, "_MEIPASS", get_app_dir())
        bundle_path = os.path.join(base_path, relative_path)
        if os.path.exists(bundle_path):
            return bundle_path

    # 3. المسار الافتراضي
    return app_dir_path
