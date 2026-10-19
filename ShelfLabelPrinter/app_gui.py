"""
واجهة المستخدم الرسومية الفاخرة لبرنامج طباعة ملصقات الأرفف (Shelf Label Printer GUI)
مبنية باستخدام CustomTkinter بأحدث المعايير مع دعم كامل للغة العربية ومطابقة للمواصفات:
- قراءة فورية من قارئ الباركود (Scanner Wedge)
- استيراد ملفات CSV / TXT من أجهزة Honeywell EDA51
- لصق متعدد للباركودات
- جدول تفاعلي للأصناف مع التحكم بكمية كل صنف
- معاينة حية للملصق بدقة 300 DPI
- تجهيز وطباعة على ورق A4 عادي مع خطوط وعلامات القص
- تحكم بموضع البداية على الصفحة (1 - 21) لتفادي هدر الورق
- إدارة شعاري الترويسة (شعار 1 وشعار 2)
"""
import os
import sys
import threading
import winsound
from typing import List, Optional
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image

parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    import auto_updater
except Exception:
    auto_updater = None

from label_model import LabelItem
from odoo_service import OdooService
from label_renderer import LabelRenderer, LABEL_WIDTH, LABEL_HEIGHT
from page_generator import PageGenerator, LABELS_PER_PAGE, COLS, ROWS
from config_manager import ConfigManager
from path_utils import get_resource_path

# تعيين المظهر العام
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class ShelfLabelPrinterApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # إعدادات النافذة الرئيسية
        self.title("نظام طباعة ملصقات أرفف المستودعات والمعارض — شركة العصلي للتجارة")
        self.geometry("1280x820")
        self.minsize(1050, 700)

        # أيقونة النافذة
        ico = get_resource_path(os.path.join("assets", "app_icon.ico"))
        if os.path.exists(ico):
            try:
                self.iconbitmap(ico)
            except Exception:
                pass

        # الخدمات والبيانات
        self.config_mgr = ConfigManager()
        self.odoo_service = OdooService()
        self.items: List[LabelItem] = []
        self.selected_item_index: Optional[int] = None

        # إنشاء محرك الرسم والتوليد
        self.renderer = LabelRenderer(
            logo1_path=self.config_mgr.get("logo1_path"),
            logo2_path=self.config_mgr.get("logo2_path")
        )
        self.page_generator = PageGenerator(self.renderer)

        # بناء الواجهة
        self._build_ui()

        # ضبط التركيز التلقائي على حقل الباركود
        self.after(500, lambda: self.entry_scanner.focus_set())

        # فحص التحديثات التلقائية في الخلفية
        if auto_updater:
            auto_updater.check_and_prompt_update_async(self, "ShelfLabelPrinter", "1.00")

    def _build_ui(self):
        # الحاوية الرئيسية مقسمة لعمودين:
        # العمود الأيمن (أو الأيسر حسب LTR في Tkinter): جدول الأصناف والتحكم
        # العمود الجانبي: المعاينة الحية وإعدادات الطباعة
        self.grid_columnconfigure(0, weight=1)  # منطقة الجدول
        self.grid_columnconfigure(1, weight=0)  # منطقة المعاينة والطباعة (عرض ثابت)
        self.grid_rowconfigure(1, weight=1)

        # -------------------------------------------------------------
        # 1. الشريط العلوي (Header Bar)
        # -------------------------------------------------------------
        header_frame = ctk.CTkFrame(self, height=65, corner_radius=0)
        header_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=0, pady=0)
        header_frame.grid_columnconfigure(0, weight=1)

        # عنوان البرنامج وبيانات المطور
        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.grid(row=0, column=0, padx=20, pady=8, sticky="e")

        title_label = ctk.CTkLabel(
            title_box,
            text="🏷️ نظام طباعة ملصقات الأرفف (60×40 مم — ورق A4)",
            font=ctk.CTkFont(family="Tahoma", size=18, weight="bold")
        )
        title_label.pack(anchor="e")

        dev_label_top = ctk.CTkLabel(
            title_box,
            text="تصميم وتطوير/ عبدالله الخطيب",
            font=ctk.CTkFont(family="Tahoma", size=11, weight="bold"),
            text_color=("#1565C0", "#64B5F6")
        )
        dev_label_top.pack(anchor="e")

        # أزرار الإعدادات والمساعدة في الشريط العلوي
        top_btns = ctk.CTkFrame(header_frame, fg_color="transparent")
        top_btns.grid(row=0, column=1, padx=20, pady=10, sticky="w")

        btn_settings = ctk.CTkButton(
            top_btns,
            text="⚙️ إعدادات الشعارات",
            font=ctk.CTkFont(family="Tahoma", size=13),
            width=140,
            command=self._open_settings_dialog
        )
        btn_settings.pack(side="left", padx=5)

        # -------------------------------------------------------------
        # 2. منطقة العمل الرئيسية (Main Content)
        # -------------------------------------------------------------
        # اللوحة اليسرى: قائمة الأصناف وعمليات الإدخال
        left_panel = ctk.CTkFrame(self, fg_color="transparent")
        left_panel.grid(row=1, column=0, sticky="nsew", padx=15, pady=10)
        left_panel.grid_rowconfigure(2, weight=1)
        left_panel.grid_columnconfigure(0, weight=1)

        # أ. شريط الإدخال السريع (Barcode Scanner Input)
        scan_box = ctk.CTkFrame(left_panel, corner_radius=10)
        scan_box.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        scan_box.grid_columnconfigure(1, weight=1)

        lbl_scan_icon = ctk.CTkLabel(
            scan_box,
            text="📷 مسح الباركود:",
            font=ctk.CTkFont(family="Tahoma", size=15, weight="bold")
        )
        lbl_scan_icon.grid(row=0, column=2, padx=(10, 15), pady=12, sticky="e")

        self.entry_scanner = ctk.CTkEntry(
            scan_box,
            placeholder_text="امسح بالباركود سنر أو اكتب واضغط Enter...",
            height=42,
            font=ctk.CTkFont(family="Consolas", size=16),
            justify="right"
        )
        self.entry_scanner.grid(row=0, column=1, sticky="ew", padx=10, pady=12)
        self.entry_scanner.bind("<Return>", self._on_scanner_enter)

        btn_add = ctk.CTkButton(
            scan_box,
            text="➕ إضافة",
            font=ctk.CTkFont(family="Tahoma", size=14, weight="bold"),
            width=90,
            height=40,
            command=self._on_add_button_clicked
        )
        btn_add.grid(row=0, column=0, padx=(15, 10), pady=12, sticky="w")

        # ب. شريط أدوات الاستيراد والإجراءات السريعة
        toolbar = ctk.CTkFrame(left_panel, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        btn_import_hw = ctk.CTkButton(
            toolbar,
            text="📂 استيراد من Honeywell (CSV / TXT)",
            font=ctk.CTkFont(family="Tahoma", size=13),
            fg_color="#1E88E5",
            hover_color="#1565C0",
            command=self._import_from_honeywell
        )
        btn_import_hw.pack(side="right", padx=(0, 10))

        btn_paste = ctk.CTkButton(
            toolbar,
            text="📋 لصق قائمة باركودات",
            font=ctk.CTkFont(family="Tahoma", size=13),
            fg_color="#43A047",
            hover_color="#2E7D32",
            command=self._open_paste_dialog
        )
        btn_paste.pack(side="right", padx=(0, 10))

        self.btn_clear_all = ctk.CTkButton(
            toolbar,
            text="🗑️ مسح الكل",
            font=ctk.CTkFont(family="Tahoma", size=13),
            fg_color="#E53935",
            hover_color="#C62828",
            width=100,
            command=self._clear_all_items
        )
        self.btn_clear_all.pack(side="left")

        # ج. جدول الأصناف (Scrollable List)
        self.table_container = ctk.CTkScrollableFrame(left_panel, corner_radius=10)
        self.table_container.grid(row=2, column=0, sticky="nsew")
        self.table_container.grid_columnconfigure(2, weight=1)  # اسم الصنف يتمدد

        # ترويسة الجدول
        self._build_table_header()

        # د. شريط المعلومات والإحصائيات أسفل الجدول
        status_bar = ctk.CTkFrame(left_panel, height=35, corner_radius=8)
        status_bar.grid(row=3, column=0, sticky="ew", pady=(10, 0))

        self.lbl_stats = ctk.CTkLabel(
            status_bar,
            text="إجمالي الأصناف: 0 | إجمالي الاستيكرات: 0 | صفحات A4 المطلوبة: 0",
            font=ctk.CTkFont(family="Tahoma", size=13, weight="bold")
        )
        self.lbl_stats.pack(side="right", padx=15, pady=6)

        self.lbl_status_msg = ctk.CTkLabel(
            status_bar,
            text="جاهز لاستقبال المسح...",
            text_color="#888888"
        )
        self.lbl_status_msg.pack(side="left", padx=15, pady=6)

        lbl_dev = ctk.CTkLabel(
            status_bar,
            text="✨ تصميم وتطوير/ عبدالله الخطيب",
            font=ctk.CTkFont(family="Tahoma", size=11, weight="bold"),
            text_color=("#1565C0", "#64B5F6")
        )
        lbl_dev.pack(side="left", padx=20, pady=6)

        # -------------------------------------------------------------
        # 3. اللوحة الجانبية: المعاينة الحية وعناصر التحكم بالطباعة
        # -------------------------------------------------------------
        right_panel = ctk.CTkFrame(self, width=420, corner_radius=10)
        right_panel.grid(row=1, column=1, sticky="nsew", padx=(0, 15), pady=10)
        right_panel.grid_propagate(False)

        # أ. عنوان المعاينة
        lbl_preview_title = ctk.CTkLabel(
            right_panel,
            text="👁️ معاينة الملصق المباشرة (60×40 مم)",
            font=ctk.CTkFont(family="Tahoma", size=15, weight="bold")
        )
        lbl_preview_title.pack(pady=(15, 10))

        # ب. إطار عرض صورة المعاينة (Aspect Ratio 60:40 -> 360 x 240)
        self.preview_canvas = ctk.CTkLabel(
            right_panel,
            text="لا توجد بيانات للمعاينة\nامسح باركود أو اختر صنفاً",
            width=360,
            height=240,
            fg_color=("gray85", "gray20"),
            corner_radius=8,
            font=ctk.CTkFont(family="Tahoma", size=13)
        )
        self.preview_canvas.pack(padx=20, pady=5)

        # ج. خيارات وسيط وطريقة الطباعة (ورق A4 أو رول)
        print_options_frame = ctk.CTkFrame(right_panel, corner_radius=8)
        print_options_frame.pack(fill="x", padx=20, pady=12)

        lbl_options_title = ctk.CTkLabel(
            print_options_frame,
            text="⚙️ وسيط وإعدادات الطباعة",
            font=ctk.CTkFont(family="Tahoma", size=13, weight="bold")
        )
        lbl_options_title.pack(pady=(10, 6), padx=12, anchor="e")

        # اختيار نوع الورق (SegmentedButton)
        self.seg_paper_type = ctk.CTkSegmentedButton(
            print_options_frame,
            values=["📄 ورق عادي A4 (21 ملصق)", "🏷️ ورق رول (60×40 مم)"],
            command=self._on_paper_type_changed,
            font=ctk.CTkFont(family="Tahoma", size=12, weight="bold")
        )
        self.seg_paper_type.pack(fill="x", padx=12, pady=(0, 8))

        # إطار خيارات A4
        self.a4_options_frame = ctk.CTkFrame(print_options_frame, fg_color="transparent")
        
        start_pos_row = ctk.CTkFrame(self.a4_options_frame, fg_color="transparent")
        start_pos_row.pack(fill="x", padx=5, pady=4)

        lbl_start_pos = ctk.CTkLabel(
            start_pos_row,
            text="البدء من الملصق رقم (1 - 21):",
            font=ctk.CTkFont(family="Tahoma", size=12)
        )
        lbl_start_pos.pack(side="right")

        self.spin_start_pos = ctk.CTkOptionMenu(
            start_pos_row,
            values=[str(i) for i in range(1, 22)],
            width=70,
            font=ctk.CTkFont(family="Tahoma", size=12)
        )
        self.spin_start_pos.set("1")
        self.spin_start_pos.pack(side="left")

        self.check_cut_guides = ctk.CTkCheckBox(
            self.a4_options_frame,
            text="تضمين علامات وخطوط القص (للورق العادي)",
            font=ctk.CTkFont(family="Tahoma", size=12)
        )
        self.check_cut_guides.select()
        self.check_cut_guides.pack(padx=5, pady=(4, 6), anchor="e")

        # إطار خيارات ورق الرول
        self.roll_options_frame = ctk.CTkFrame(print_options_frame, fg_color="transparent")

        lbl_roll_desc = ctk.CTkLabel(
            self.roll_options_frame,
            text="• كل ملصق صفحة مستقلة (60×40 مم) على الرول\n• تتكرر الملصقات تلقائياً حسب كمية كل صنف",
            font=ctk.CTkFont(family="Tahoma", size=11),
            text_color=("gray30", "gray70"),
            justify="right"
        )
        lbl_roll_desc.pack(padx=5, pady=(2, 6), anchor="e")

        self.check_roll_border = ctk.CTkCheckBox(
            self.roll_options_frame,
            text="تضمين إطار خارجي خفيف للملصق",
            font=ctk.CTkFont(family="Tahoma", size=12)
        )
        if self.config_mgr.get("draw_roll_border", False):
            self.check_roll_border.select()
        else:
            self.check_roll_border.deselect()
        self.check_roll_border.pack(padx=5, pady=(0, 6), anchor="e")

        # إطار تحديد الطابعة المستهدفة
        self.printer_row_frame = ctk.CTkFrame(print_options_frame, fg_color="transparent")
        self.printer_row_frame.pack(fill="x", padx=12, pady=(4, 10))

        lbl_printer = ctk.CTkLabel(
            self.printer_row_frame,
            text="🖨️ الطابعة:",
            font=ctk.CTkFont(family="Tahoma", size=12, weight="bold")
        )
        lbl_printer.pack(side="right", padx=(5, 0))

        self.installed_printers = self._get_installed_printers()
        self.combo_printers = ctk.CTkOptionMenu(
            self.printer_row_frame,
            values=self.installed_printers,
            command=self._on_printer_changed,
            font=ctk.CTkFont(family="Tahoma", size=11),
            width=230
        )
        self.combo_printers.pack(side="right", fill="x", expand=True)

        # ضبط الحالة الافتراضية للورق والطابعة
        saved_paper = self.config_mgr.get("paper_type", "a4")
        if saved_paper == "roll":
            self.seg_paper_type.set("🏷️ ورق رول (60×40 مم)")
            self.roll_options_frame.pack(fill="x", padx=12, pady=(0, 6), before=self.printer_row_frame)
            roll_printer = self._detect_default_roll_printer(self.installed_printers)
            self.combo_printers.set(roll_printer)
            if roll_printer and roll_printer != "[الطابعة الافتراضية للنظام]":
                PageGenerator.configure_roll_printer_size(roll_printer, 60.0, 40.0)
        else:
            self.seg_paper_type.set("📄 ورق عادي A4 (21 ملصق)")
            self.a4_options_frame.pack(fill="x", padx=12, pady=(0, 6), before=self.printer_row_frame)
            a4_printer = self._detect_default_a4_printer(self.installed_printers)
            self.combo_printers.set(a4_printer)

        # د. أزرار الطباعة والتصدير
        btn_print_direct = ctk.CTkButton(
            right_panel,
            text="🖨️ طباعة فورية على الطابعة المحددة",
            font=ctk.CTkFont(family="Tahoma", size=15, weight="bold"),
            height=46,
            fg_color="#0D47A1",
            hover_color="#1565C0",
            command=self._print_direct
        )
        btn_print_direct.pack(fill="x", padx=20, pady=(10, 8))

        btn_export_pdf = ctk.CTkButton(
            right_panel,
            text="📄 تصدير ومعاينة ملف PDF (300 DPI)",
            font=ctk.CTkFont(family="Tahoma", size=14, weight="bold"),
            height=42,
            fg_color="#2E7D32",
            hover_color="#388E3C",
            command=self._export_pdf
        )
        btn_export_pdf.pack(fill="x", padx=20, pady=5)

    def _build_table_header(self):
        header = ctk.CTkFrame(self.table_container, height=35, fg_color=("gray80", "gray25"), corner_radius=6)
        header.grid(row=0, column=0, columnspan=6, sticky="ew", padx=2, pady=(0, 5))
        header.grid_columnconfigure(2, weight=1)

        labels = [
            ("#", 40, "center"),
            ("الباركود", 140, "center"),
            ("اسم الصنف (عربي / إنجليزي)", 300, "e"),
            ("السعر شامل الضريبة", 130, "center"),
            ("الكمية", 110, "center"),
            ("حذف", 50, "center")
        ]

        for idx, (txt, w, anchor) in enumerate(labels):
            lbl = ctk.CTkLabel(
                header,
                text=txt,
                font=ctk.CTkFont(family="Tahoma", size=12, weight="bold"),
                width=w,
                anchor=anchor
            )
            lbl.grid(row=0, column=idx, padx=5, pady=4, sticky="ew" if idx == 2 else "")

    def _render_table_rows(self):
        # مسح الصفوف القديمة فقط (مع إبقاء الترويسة)
        for widget in self.table_container.winfo_children():
            grid_info = widget.grid_info()
            if grid_info.get("row", 0) > 0:
                widget.destroy()

        for idx, item in enumerate(self.items):
            row_num = idx + 1
            is_selected = (idx == self.selected_item_index)
            row_bg = ("#D0E2FF", "#1E3A5F") if is_selected else ("white", "gray17")

            row_frame = ctk.CTkFrame(self.table_container, height=44, fg_color=row_bg, corner_radius=6)
            row_frame.grid(row=row_num, column=0, columnspan=6, sticky="ew", padx=2, pady=2)
            row_frame.grid_columnconfigure(2, weight=1)

            # النقر على الصف يحدده ويحدث المعاينة
            row_frame.bind("<Button-1>", lambda e, i=idx: self._select_item(i))

            # # الترقيم
            lbl_num = ctk.CTkLabel(row_frame, text=str(row_num), width=40, font=ctk.CTkFont(family="Tahoma", size=12))
            lbl_num.grid(row=0, column=0, padx=5, pady=4)
            lbl_num.bind("<Button-1>", lambda e, i=idx: self._select_item(i))

            # الباركود
            lbl_bc = ctk.CTkLabel(
                row_frame,
                text=item.barcode,
                width=140,
                font=ctk.CTkFont(family="Consolas", size=13, weight="bold")
            )
            lbl_bc.grid(row=0, column=1, padx=5, pady=4)
            lbl_bc.bind("<Button-1>", lambda e, i=idx: self._select_item(i))

            # اسم الصنف
            display_name = item.name_ar or item.name_en or "صنف بدون اسم"
            lbl_name = ctk.CTkLabel(
                row_frame,
                text=display_name,
                anchor="e",
                font=ctk.CTkFont(family="Tahoma", size=12)
            )
            lbl_name.grid(row=0, column=2, padx=10, pady=4, sticky="ew")
            lbl_name.bind("<Button-1>", lambda e, i=idx: self._select_item(i))

            # السعر شامل الضريبة
            lbl_price = ctk.CTkLabel(
                row_frame,
                text=f"{item.formatted_price} ﷼",
                width=130,
                font=ctk.CTkFont(family="Tahoma", size=13, weight="bold"),
                text_color="#0D47A1"
            )
            lbl_price.grid(row=0, column=3, padx=5, pady=4)
            lbl_price.bind("<Button-1>", lambda e, i=idx: self._select_item(i))

            # صندوق التحكم بالكمية
            qty_frame = ctk.CTkFrame(row_frame, fg_color="transparent", width=110)
            qty_frame.grid(row=0, column=4, padx=5, pady=2)

            btn_minus = ctk.CTkButton(
                qty_frame,
                text="−",
                width=24,
                height=24,
                font=ctk.CTkFont(family="Tahoma", size=12, weight="bold"),
                fg_color=("gray75", "gray30"),
                text_color=("black", "white"),
                command=lambda i=idx: self._change_quantity(i, -1)
            )
            btn_minus.pack(side="left", padx=2)

            lbl_qty = ctk.CTkLabel(
                qty_frame,
                text=str(item.quantity),
                width=35,
                font=ctk.CTkFont(family="Tahoma", size=13, weight="bold")
            )
            lbl_qty.pack(side="left", padx=2)

            btn_plus = ctk.CTkButton(
                qty_frame,
                text="+",
                width=24,
                height=24,
                font=ctk.CTkFont(family="Tahoma", size=12, weight="bold"),
                fg_color=("gray75", "gray30"),
                text_color=("black", "white"),
                command=lambda i=idx: self._change_quantity(i, 1)
            )
            btn_plus.pack(side="left", padx=2)

            # زر الحذف
            btn_del = ctk.CTkButton(
                row_frame,
                text="❌",
                width=32,
                height=26,
                font=ctk.CTkFont(family="Tahoma", size=11),
                fg_color="transparent",
                hover_color=("#FFCDD2", "#B71C1C"),
                text_color=("#C62828", "#FF8A80"),
                command=lambda i=idx: self._delete_item(i)
            )
            btn_del.grid(row=0, column=5, padx=5, pady=4)

        self._update_stats()

    def _select_item(self, index: int):
        if 0 <= index < len(self.items):
            self.selected_item_index = index
            self._render_table_rows()
            self._update_preview()

    def _change_quantity(self, index: int, delta: int):
        if 0 <= index < len(self.items):
            new_qty = self.items[index].quantity + delta
            if new_qty > 0:
                self.items[index].quantity = new_qty
            else:
                # إذا وصلت للصفر نحذفه
                self._delete_item(index)
                return
            self._render_table_rows()

    def _delete_item(self, index: int):
        if 0 <= index < len(self.items):
            del self.items[index]
            if self.selected_item_index == index:
                self.selected_item_index = len(self.items) - 1 if self.items else None
            elif self.selected_item_index is not None and self.selected_item_index > index:
                self.selected_item_index -= 1
            self._render_table_rows()
            self._update_preview()

    def _update_stats(self):
        total_items = len(self.items)
        total_stickers = sum(it.quantity for it in self.items)
        start_pos = int(self.spin_start_pos.get()) if hasattr(self, "spin_start_pos") else 1
        
        # حساب عدد صفحات A4 المطلوبة مع مراعاة موضع البداية
        if total_stickers == 0:
            pages = 0
        else:
            first_page_capacity = LABELS_PER_PAGE - start_pos + 1
            if total_stickers <= first_page_capacity:
                pages = 1
            else:
                remaining = total_stickers - first_page_capacity
                pages = 1 + (remaining + LABELS_PER_PAGE - 1) // LABELS_PER_PAGE

        self.lbl_stats.configure(
            text=f"إجمالي الأصناف: {total_items} | إجمالي الاستيكرات: {total_stickers} | صفحات A4: {pages}"
        )

    def _update_preview(self):
        if not self.items:
            self.preview_canvas.configure(
                image=None,
                text="لا توجد بيانات للمعاينة\nامسح باركود أو اختر صنفاً"
            )
            return

        idx = self.selected_item_index if self.selected_item_index is not None and 0 <= self.selected_item_index < len(self.items) else 0
        item = self.items[idx]

        # توليد صورة الملصق
        try:
            label_img = self.renderer.render_label(item)
            # تصغير المعاينة لتناسب الكانفاس (360×240)
            preview_thumb = label_img.resize((360, 240), Image.Resampling.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=preview_thumb, dark_image=preview_thumb, size=(360, 240))
            self.preview_canvas.configure(image=ctk_img, text="")
        except Exception as e:
            print(f"[Preview Error]: {e}")
            self.preview_canvas.configure(image=None, text=f"خطأ في المعاينة: {e}")

    # -------------------------------------------------------------
    # عمليات المسح والإضافة
    # -------------------------------------------------------------
    def _on_scanner_enter(self, event=None):
        barcode = self.entry_scanner.get().strip()
        if not barcode:
            return
        self.entry_scanner.delete(0, tk.END)
        self._lookup_and_add(barcode)

    def _on_add_button_clicked(self):
        self._on_scanner_enter()

    def _lookup_and_add(self, barcode: str):
        # 1. إذا كان الباركود موجوداً في القائمة مسبقاً، نزيد كميته فوراً ونحدده
        for idx, item in enumerate(self.items):
            if item.barcode == barcode:
                item.quantity += 1
                self.selected_item_index = idx
                self._render_table_rows()
                self._update_preview()
                self._play_beep()
                self.lbl_status_msg.configure(text=f"✅ تم زيادة كمية الصنف ({barcode})")
                return

        # 2. جلب البيانات من Odoo في خيط منفصل لتجنب تجميد الواجهة
        self.lbl_status_msg.configure(text=f"⏳ جلب بيانات الباركود {barcode} من Odoo...")

        def fetch_worker():
            try:
                item = self.odoo_service.get_product_by_barcode(barcode)
                if not item:
                    item = LabelItem(
                        barcode=barcode,
                        name_ar="صنف غير معرّف في Odoo",
                        name_en="Unknown Item",
                        price=0.0
                    )
                self.after(0, lambda: self._add_item_success(item))
            except Exception as e:
                self.after(0, lambda: self.lbl_status_msg.configure(text=f"❌ خطأ: {e}"))

        threading.Thread(target=fetch_worker, daemon=True).start()

    def _add_item_success(self, item: LabelItem):
        self.items.append(item)
        self.selected_item_index = len(self.items) - 1
        self._render_table_rows()
        self._update_preview()
        self._play_beep()
        self.lbl_status_msg.configure(text=f"✅ تمت إضافة: {item.name_ar[:30]}")

    def _play_beep(self):
        try:
            winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass

    # -------------------------------------------------------------
    # الاستيراد واللصق
    # -------------------------------------------------------------
    def _import_from_honeywell(self):
        file_path = filedialog.askopenfilename(
            title="اختر ملف قائمة الفحص من Honeywell",
            filetypes=[("Text & CSV Files", "*.csv *.txt"), ("All Files", "*.*")]
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            barcodes = []
            for line in lines:
                clean = line.strip()
                # إذا كان ملف CSV مفصولاً بفواصل
                if "," in clean:
                    parts = clean.split(",")
                    clean = parts[0].strip()
                if clean and not clean.startswith("#") and clean.lower() != "barcode":
                    barcodes.append(clean)

            if not barcodes:
                messagebox.showwarning("تنبيه", "لم يتم العثور على باركودات صالحة في الملف.")
                return

            self._process_bulk_barcodes(barcodes)
        except Exception as e:
            messagebox.showerror("خطأ", f"فشل قراءة الملف: {e}")

    def _open_paste_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("لصق قائمة باركودات")
        dialog.geometry("450x450")
        dialog.transient(self)
        dialog.grab_set()

        lbl = ctk.CTkLabel(
            dialog,
            text="الصق الباركودات هنا (كل باركود في سطر جديد):",
            font=ctk.CTkFont(family="Tahoma", size=13, weight="bold")
        )
        lbl.pack(padx=20, pady=(15, 8), anchor="e")

        txt_box = ctk.CTkTextbox(dialog, height=260, font=ctk.CTkFont(family="Consolas", size=14))
        txt_box.pack(fill="both", expand=True, padx=20, pady=5)
        txt_box.focus_set()

        def do_process():
            raw = txt_box.get("1.0", tk.END)
            barcodes = [line.strip() for line in raw.splitlines() if line.strip()]
            dialog.destroy()
            if barcodes:
                self._process_bulk_barcodes(barcodes)

        btn_confirm = ctk.CTkButton(
            dialog,
            text="📥 جلب بيانات الأصناف",
            font=ctk.CTkFont(family="Tahoma", size=14, weight="bold"),
            height=40,
            command=do_process
        )
        btn_confirm.pack(fill="x", padx=20, pady=15)

    def _process_bulk_barcodes(self, barcodes: List[str]):
        self.lbl_status_msg.configure(text=f"⏳ جلب {len(barcodes)} صنف دفعة واحدة من Odoo...")

        def bulk_worker():
            try:
                items = self.odoo_service.get_products_bulk(barcodes)
                self.after(0, lambda: self._add_bulk_success(items))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("خطأ", f"فشل جلب البيانات: {e}"))

        threading.Thread(target=bulk_worker, daemon=True).start()

    def _add_bulk_success(self, new_items: List[LabelItem]):
        # دمج الأصناف مع الموجود
        existing_map = {it.barcode: it for it in self.items}
        for it in new_items:
            if it.barcode in existing_map:
                existing_map[it.barcode].quantity += 1
            else:
                self.items.append(it)
                existing_map[it.barcode] = it

        if self.items and self.selected_item_index is None:
            self.selected_item_index = 0

        self._render_table_rows()
        self._update_preview()
        self._play_beep()
        self.lbl_status_msg.configure(text=f"✅ تم تحميل وتحديث {len(new_items)} صنف بنجاح!")

    def _clear_all_items(self):
        if not self.items:
            return
        if messagebox.askyesno("تأكيد", "هل تريد مسح جميع الأصناف من القائمة؟"):
            self.items.clear()
            self.selected_item_index = None
            self._render_table_rows()
            self._update_preview()
            self.lbl_status_msg.configure(text="تم مسح القائمة.")

    # -------------------------------------------------------------
    # الطباعة وتصدير PDF
    # -------------------------------------------------------------
    def _get_installed_printers(self) -> List[str]:
        default_opt = "[الطابعة الافتراضية للنظام]"
        printers = [default_opt]
        try:
            import win32print
            for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS):
                p_name = p[2]
                if p_name not in printers:
                    printers.append(p_name)
        except Exception:
            pass
        return printers

    def _detect_default_roll_printer(self, printers: List[str]) -> str:
        saved = self.config_mgr.get("selected_printer_roll", "")
        if saved and saved in printers:
            return saved
        keywords = ['zebra', 'gk', 'gx', 'zd', 'roll', 'label', 'thermal', 'xprinter', 'tsc', 'bixolon', 'citizen', 'honeywell', 'sato', 'godex', 'barcode']
        for p in printers:
            if any(k in p.lower() for k in keywords):
                return p
        return "[الطابعة الافتراضية للنظام]"

    def _detect_default_a4_printer(self, printers: List[str]) -> str:
        saved = self.config_mgr.get("selected_printer_a4", "")
        if saved and saved in printers:
            return saved
        return "[الطابعة الافتراضية للنظام]"

    def _get_current_paper_type(self) -> str:
        val = self.seg_paper_type.get()
        return "roll" if ("رول" in val or "roll" in val.lower()) else "a4"

    def _on_paper_type_changed(self, value: str):
        is_roll = "رول" in value or "roll" in value.lower()
        if is_roll:
            self.seg_paper_type.set("🏷️ ورق رول (60×40 مم)")
            self.a4_options_frame.pack_forget()
            self.roll_options_frame.pack(fill="x", padx=12, pady=(0, 6), before=self.printer_row_frame)
            self.config_mgr.set("paper_type", "roll")
            roll_printer = self._detect_default_roll_printer(self.installed_printers)
            if roll_printer in self.installed_printers:
                self.combo_printers.set(roll_printer)
                if roll_printer != "[الطابعة الافتراضية للنظام]":
                    PageGenerator.configure_roll_printer_size(roll_printer, 60.0, 40.0)
        else:
            self.seg_paper_type.set("📄 ورق عادي A4 (21 ملصق)")
            self.roll_options_frame.pack_forget()
            self.a4_options_frame.pack(fill="x", padx=12, pady=(0, 6), before=self.printer_row_frame)
            self.config_mgr.set("paper_type", "a4")
            a4_printer = self._detect_default_a4_printer(self.installed_printers)
            if a4_printer in self.installed_printers:
                self.combo_printers.set(a4_printer)

    def _on_printer_changed(self, selected_printer: str):
        current_paper = self._get_current_paper_type()
        if current_paper == "roll":
            self.config_mgr.set("selected_printer_roll", selected_printer)
            if selected_printer != "[الطابعة الافتراضية للنظام]":
                PageGenerator.configure_roll_printer_size(selected_printer, 60.0, 40.0)
        else:
            self.config_mgr.set("selected_printer_a4", selected_printer)

    # -------------------------------------------------------------
    # الطباعة وتصدير PDF
    # -------------------------------------------------------------
    def _get_start_pos(self) -> int:
        try:
            return int(self.spin_start_pos.get())
        except (ValueError, AttributeError):
            return 1

    def _print_direct(self):
        if not self.items:
            messagebox.showwarning("تنبيه", "القائمة فارغة! أضف أصنافاً أولاً للطباعة.")
            return

        paper_type = self._get_current_paper_type()
        start_pos = self._get_start_pos()
        draw_guides = bool(self.check_cut_guides.get()) if hasattr(self, "check_cut_guides") else True
        draw_roll_border = bool(self.check_roll_border.get()) if hasattr(self, "check_roll_border") else False
        
        self.config_mgr.set("draw_roll_border", draw_roll_border)

        chosen_printer = self.combo_printers.get()
        target_printer = None if chosen_printer == "[الطابعة الافتراضية للنظام]" else chosen_printer

        total_labels = sum(it.quantity for it in self.items)

        if paper_type == "roll":
            self.lbl_status_msg.configure(text="⏳ جاري إرسال الملصقات لطابعة الرول (60×40 مم)...")
        else:
            self.lbl_status_msg.configure(text="⏳ جاري إرسال صفحات A4 للطابعة...")

        try:
            pdf_path = self.page_generator.print_to_printer(
                self.items,
                paper_type=paper_type,
                start_position=start_pos,
                draw_cut_guides=draw_guides,
                draw_roll_border=draw_roll_border,
                printer_name=target_printer
            )
            printer_display = f" إلى [{chosen_printer}]" if target_printer else ""
            if paper_type == "roll":
                msg = f"تم إرسال {total_labels} ملصق رول (60×40 مم){printer_display} بنجاح!"
            else:
                msg = f"تم إرسال {total_labels} ملصق على ورق A4{printer_display} بنجاح!"
            self.lbl_status_msg.configure(text="✅ تم إرسال أمر الطباعة بنجاح.")
            messagebox.showinfo("نجاح الطباعة", msg)
        except Exception as e:
            messagebox.showerror("خطأ في الطباعة", f"تعذر إرسال أمر الطباعة: {e}")

    def _export_pdf(self):
        if not self.items:
            messagebox.showwarning("تنبيه", "القائمة فارغة! أضف أصنافاً أولاً للتصدير.")
            return

        paper_type = self._get_current_paper_type()
        start_pos = self._get_start_pos()
        draw_guides = bool(self.check_cut_guides.get()) if hasattr(self, "check_cut_guides") else True
        draw_roll_border = bool(self.check_roll_border.get()) if hasattr(self, "check_roll_border") else False

        default_filename = "shelf_labels_roll_60x40.pdf" if paper_type == "roll" else "shelf_labels_a4.pdf"
        dialog_title = "حفظ ملف ملصقات الرول PDF (60×40 مم)" if paper_type == "roll" else "حفظ ملف ملصقات A4 PDF"

        file_path = filedialog.asksaveasfilename(
            title=dialog_title,
            defaultextension=".pdf",
            filetypes=[("PDF Document", "*.pdf")],
            initialfile=default_filename
        )
        if not file_path:
            return

        try:
            self.page_generator.save_pdf(
                self.items,
                file_path,
                paper_type=paper_type,
                start_position=start_pos,
                draw_cut_guides=draw_guides,
                draw_roll_border=draw_roll_border
            )
            self.lbl_status_msg.configure(text="✅ تم حفظ ملف PDF بنجاح.")
            total_labels = sum(it.quantity for it in self.items)
            msg_type = f"ملف رول 60×40 مم ({total_labels} ملصق)" if paper_type == "roll" else f"ملف A4 ({total_labels} ملصق)"
            if messagebox.askyesno("نجاح التصدير", f"تم إنشاء {msg_type} بنجاح!\nهل تريد فتحه الآن لمعاينته؟"):
                os.startfile(file_path)
        except Exception as e:
            messagebox.showerror("خطأ", f"فشل تصدير PDF: {e}")

    # -------------------------------------------------------------
    # نافذة الإعدادات واختيار الشعارات والطابعات
    # -------------------------------------------------------------
    def _open_settings_dialog(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("إعدادات البرنامج والشعارات")
        dlg.geometry("580x540")
        dlg.transient(self)
        dlg.grab_set()

        lbl_header = ctk.CTkLabel(
            dlg,
            text="⚙️ إعدادات الشعارات وطابعات الملصقات",
            font=ctk.CTkFont(family="Tahoma", size=16, weight="bold")
        )
        lbl_header.pack(pady=(15, 10))

        # شعار 1 (يمين الملصق)
        frame_l1 = ctk.CTkFrame(dlg)
        frame_l1.pack(fill="x", padx=25, pady=6)
        lbl_l1 = ctk.CTkLabel(frame_l1, text="شعار 1 (يمين الترويسة):", font=ctk.CTkFont(family="Tahoma", size=12, weight="bold"))
        lbl_l1.pack(anchor="e", padx=15, pady=(6, 2))

        entry_l1 = ctk.CTkEntry(frame_l1, font=ctk.CTkFont(size=11))
        entry_l1.insert(0, self.config_mgr.get("logo1_path", ""))
        entry_l1.pack(side="right", fill="x", expand=True, padx=(10, 15), pady=6)

        def browse_l1():
            f = filedialog.askopenfilename(title="اختر ملف الشعار 1", filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")])
            if f:
                entry_l1.delete(0, tk.END)
                entry_l1.insert(0, f)

        btn_browse_l1 = ctk.CTkButton(frame_l1, text="تصفح...", width=80, command=browse_l1)
        btn_browse_l1.pack(side="left", padx=10, pady=6)

        # شعار 2 (يسار الملصق)
        frame_l2 = ctk.CTkFrame(dlg)
        frame_l2.pack(fill="x", padx=25, pady=6)
        lbl_l2 = ctk.CTkLabel(frame_l2, text="شعار 2 (يسار الترويسة):", font=ctk.CTkFont(family="Tahoma", size=12, weight="bold"))
        lbl_l2.pack(anchor="e", padx=15, pady=(6, 2))

        entry_l2 = ctk.CTkEntry(frame_l2, font=ctk.CTkFont(size=11))
        entry_l2.insert(0, self.config_mgr.get("logo2_path", ""))
        entry_l2.pack(side="right", fill="x", expand=True, padx=(10, 15), pady=6)

        def browse_l2():
            f = filedialog.askopenfilename(title="اختر ملف الشعار 2", filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")])
            if f:
                entry_l2.delete(0, tk.END)
                entry_l2.insert(0, f)

        btn_browse_l2 = ctk.CTkButton(frame_l2, text="تصفح...", width=80, command=browse_l2)
        btn_browse_l2.pack(side="left", padx=10, pady=6)

        # قسم الطابعات الافتراضية
        frame_printers = ctk.CTkFrame(dlg)
        frame_printers.pack(fill="x", padx=25, pady=10)

        lbl_p_title = ctk.CTkLabel(frame_printers, text="🖨️ تعيين الطابعات الافتراضية:", font=ctk.CTkFont(family="Tahoma", size=12, weight="bold"))
        lbl_p_title.pack(anchor="e", padx=15, pady=(8, 4))

        # طابعة الرول
        row_roll = ctk.CTkFrame(frame_printers, fg_color="transparent")
        row_roll.pack(fill="x", padx=15, pady=4)
        lbl_p_roll = ctk.CTkLabel(row_roll, text="طابعة الرول (60×40 مم):", font=ctk.CTkFont(family="Tahoma", size=11))
        lbl_p_roll.pack(side="right", padx=(5, 0))

        opt_roll_printer = ctk.CTkOptionMenu(row_roll, values=self.installed_printers, font=ctk.CTkFont(size=11), width=250)
        curr_roll = self._detect_default_roll_printer(self.installed_printers)
        opt_roll_printer.set(curr_roll)
        opt_roll_printer.pack(side="right", fill="x", expand=True)

        # طابعة A4
        row_a4 = ctk.CTkFrame(frame_printers, fg_color="transparent")
        row_a4.pack(fill="x", padx=15, pady=4)
        lbl_p_a4 = ctk.CTkLabel(row_a4, text="طابعة الورق العادي A4:", font=ctk.CTkFont(family="Tahoma", size=11))
        lbl_p_a4.pack(side="right", padx=(5, 0))

        opt_a4_printer = ctk.CTkOptionMenu(row_a4, values=self.installed_printers, font=ctk.CTkFont(size=11), width=250)
        curr_a4 = self._detect_default_a4_printer(self.installed_printers)
        opt_a4_printer.set(curr_a4)
        opt_a4_printer.pack(side="right", fill="x", expand=True)

        def save_and_close():
            p1 = entry_l1.get().strip()
            p2 = entry_l2.get().strip()
            self.config_mgr.set("logo1_path", p1)
            self.config_mgr.set("logo2_path", p2)
            self.config_mgr.set("selected_printer_roll", opt_roll_printer.get())
            self.config_mgr.set("selected_printer_a4", opt_a4_printer.get())

            if self._get_current_paper_type() == "roll":
                self.combo_printers.set(opt_roll_printer.get())
            else:
                self.combo_printers.set(opt_a4_printer.get())

            # تحديث محرك الرسم
            self.renderer.logo1_path = p1
            self.renderer.logo2_path = p2
            self.renderer.logo1_img = self.renderer._load_logo(p1)
            self.renderer.logo2_img = self.renderer._load_logo(p2)
            self._update_preview()
            dlg.destroy()
            messagebox.showinfo("تم", "تم حفظ وتطبيق الإعدادات بنجاح!")

        btn_save = ctk.CTkButton(
            dlg,
            text="💾 حفظ الإعدادات",
            font=ctk.CTkFont(family="Tahoma", size=14, weight="bold"),
            height=42,
            fg_color="#0D47A1",
            command=save_and_close
        )
        btn_save.pack(fill="x", padx=25, pady=(15, 10))

if __name__ == "__main__":
    app = ShelfLabelPrinterApp()
    app.mainloop()
