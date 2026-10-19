"""
نقطة انطلاق تطبيق طباعة ملصقات الأرفف (Shelf Label Printer Launcher)
شركة العصلي للتجارة
"""
import sys
import os

# إضافة المجلد الحالي للمسار لضمان عمل كافة الوحدات
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from app_gui import ShelfLabelPrinterApp

def main():
    try:
        app = ShelfLabelPrinterApp()
        app.mainloop()
    except Exception as e:
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()
