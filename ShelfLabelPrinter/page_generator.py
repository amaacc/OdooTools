"""
محرك توليد صفحات A4 للطباعة وتجهيز خطوط القص (Page Generator)
مخصص للورق العادي A4:
- 3 أعمدة × 7 صفوف = 21 ملصق في الصفحة الواحدة
- مقاس كل ملصق: 60 مم × 40 مم
- علامات وخطوط قص دقيقة واضحة لتسهيل القص بالمقص أو القاطعة
- دعم تحديد موضع البداية (Start Position من 1 إلى 21) لتجنب هدر الورق المستخدم جزئياً
- تصدير ملف PDF جاهز للطباعة بدقة 300 DPI وإرساله لطابعة ويندوز مباشرة
"""
import os
import tempfile
from typing import List, Optional
from PIL import Image, ImageDraw

from label_model import LabelItem
from label_renderer import LabelRenderer

# مقاس A4 بالبكسل عند 300 DPI
A4_WIDTH = 2480
A4_HEIGHT = 3508

# مقاس الملصق بالبكسل
LABEL_WIDTH = 708
LABEL_HEIGHT = 472

COLS = 3
ROWS = 7
LABELS_PER_PAGE = COLS * ROWS  # 21

# هوامش الصفحة لتوسيط الشبكة بدقة متناهية
# 3 أعمدة * 708 = 2124 بكسل (المتبقي: 356 بكسل / 2 = 178 بكسل هامش يمين ويسار)
MARGIN_X = (A4_WIDTH - (COLS * LABEL_WIDTH)) // 2
# 7 صفوف * 472 = 3304 بكسل (المتبقي: 204 بكسل / 2 = 102 بكسل هامش أعلى وأسفل)
MARGIN_Y = (A4_HEIGHT - (ROWS * LABEL_HEIGHT)) // 2

class PageGenerator:
    def __init__(self, renderer: LabelRenderer):
        self.renderer = renderer

    def generate_pages(
        self,
        items: List[LabelItem],
        start_position: int = 1,
        draw_cut_guides: bool = True
    ) -> List[Image.Image]:
        """
        توليد قائمة بصور صفحات A4 كاملة
        - items: قائمة الأصناف (كل صنف يتم تكراره بعدد item.quantity)
        - start_position: موضع بداية الطباعة في الصفحة الأولى (1 إلى 21)
        - draw_cut_guides: رسم خطوط القص الممتدة للهوامش
        """
        # فك تكرار الأصناف حسب الكمية المطلوبة
        expanded_items: List[LabelItem] = []
        for it in items:
            qty = max(1, it.quantity)
            for _ in range(qty):
                expanded_items.append(it)

        if not expanded_items:
            return []

        # تصحيح موضع البداية
        start_pos = max(1, min(start_position, LABELS_PER_PAGE)) - 1  # 0-indexed

        pages: List[Image.Image] = []
        total_items = len(expanded_items)
        item_idx = 0
        page_num = 0

        while item_idx < total_items:
            # إنشاء صفحة A4 بيضاء
            page = Image.new("RGB", (A4_WIDTH, A4_HEIGHT), (255, 255, 255))
            draw = ImageDraw.Draw(page)

            # تحديد نقطة البداية لهذه الصفحة
            # الصفحة الأولى تبدأ من start_pos، والصفحات اللاحقة تبدأ من 0
            current_slot = start_pos if page_num == 0 else 0

            while current_slot < LABELS_PER_PAGE and item_idx < total_items:
                item = expanded_items[item_idx]
                label_img = self.renderer.render_label(item)

                col = current_slot % COLS
                row = current_slot // COLS

                x = MARGIN_X + (col * LABEL_WIDTH)
                y = MARGIN_Y + (row * LABEL_HEIGHT)

                page.paste(label_img, (x, y))

                current_slot += 1
                item_idx += 1

            # رسم خطوط القص الممتدة (Cut Guides) على هوامش الصفحة
            if draw_cut_guides:
                self._draw_page_cut_guides(draw)

            pages.append(page)
            page_num += 1

        return pages

    def _draw_page_cut_guides(self, draw: ImageDraw.Draw):
        """رسم علامات وخطوط القص الرفيعة لتسهيل القص الدقيق بالمقص أو القاطعة"""
        guide_color = (200, 200, 200)

        # 1. خطوط عمودية بين الأعمدة تمتد إلى حواف الهامش
        for c in range(COLS + 1):
            x = MARGIN_X + (c * LABEL_WIDTH)
            # خطوط علوية وسفلية في الهامش كعلامات قص
            draw.line([(x, 0), (x, MARGIN_Y - 5)], fill=guide_color, width=1)
            draw.line([(x, A4_HEIGHT - MARGIN_Y + 5), (x, A4_HEIGHT)], fill=guide_color, width=1)
            # خط منقط خفيف جداً على طول الصفحة بين الأعمدة
            for y_dot in range(MARGIN_Y, A4_HEIGHT - MARGIN_Y, 8):
                draw.point((x, y_dot), fill=guide_color)

        # 2. خطوط أفقية بين الصفوف تمتد إلى حواف الهامش
        for r in range(ROWS + 1):
            y = MARGIN_Y + (r * LABEL_HEIGHT)
            # خطوط يمنى ويسرى في الهامش كعلامات قص
            draw.line([(0, y), (MARGIN_X - 5, y)], fill=guide_color, width=1)
            draw.line([(A4_WIDTH - MARGIN_X + 5, y), (A4_WIDTH, y)], fill=guide_color, width=1)
            # خط منقط خفيف جداً على طول الصفحة بين الصفوف
            for x_dot in range(MARGIN_X, A4_WIDTH - MARGIN_X, 8):
                draw.point((x_dot, y), fill=guide_color)

    def generate_roll_labels(
        self,
        items: List[LabelItem],
        draw_border: bool = False
    ) -> List[Image.Image]:
        """
        توليد قائمة بملصقات الرول الفردية (مقاس 60×40 مم عند 300 DPI: 708×472 بكسل)
        كل ملصق يمثل صفحة مستقلة، مكررة حسب الكمية المطلوبة لكل صنف.
        """
        labels: List[Image.Image] = []
        for it in items:
            qty = max(1, it.quantity)
            rendered = self.renderer.render_label(it, draw_border=draw_border)
            for _ in range(qty):
                labels.append(rendered)
        return labels

    def save_pdf(
        self,
        items: List[LabelItem],
        output_pdf_path: str,
        paper_type: str = "a4",
        start_position: int = 1,
        draw_cut_guides: bool = True,
        draw_roll_border: bool = False
    ) -> str:
        """
        تصدير الأصناف إلى ملف PDF بدقة 300 DPI:
        - paper_type: "a4" (ورق عادي مقسم 21 ملصق) أو "roll" (ورق رول 60×40 مم صفحة لكل ملصق)
        """
        if paper_type == "roll":
            pages = self.generate_roll_labels(items, draw_border=draw_roll_border)
        else:
            pages = self.generate_pages(items, start_position=start_position, draw_cut_guides=draw_cut_guides)

        if not pages:
            raise ValueError("لا توجد ملصقات لطباعتها")

        # حفظ كملف PDF
        first_page = pages[0]
        other_pages = pages[1:] if len(pages) > 1 else []

        first_page.save(
            output_pdf_path,
            "PDF",
            resolution=300.0,
            save_all=True,
            append_images=other_pages
        )
        return output_pdf_path

    @staticmethod
    def configure_roll_printer_size(printer_name: str, width_mm: float = 60.0, height_mm: float = 40.0) -> bool:
        """
        ضبط مقاس الملصق في مشغل الطابعة إلى 60×40 مم تلقائياً في ويندوز
        لضمان أن المشغل يطبع بكامل حجم الملصق ولا يقوم بتصغيره
        """
        if not printer_name or printer_name in ("", "default", "[الطابعة الافتراضية للنظام]"):
            return False
        try:
            import win32print, win32con
            hprinter = win32print.OpenPrinter(printer_name, {"DesiredAccess": win32print.PRINTER_ALL_ACCESS})
            try:
                pinfo = win32print.GetPrinter(hprinter, 2)
                dm = pinfo.get("pDevMode")
                if dm:
                    target_w = int(width_mm * 10)
                    target_h = int(height_mm * 10)
                    if dm.PaperWidth != target_w or dm.PaperLength != target_h:
                        dm.PaperWidth = target_w
                        dm.PaperLength = target_h
                        dm.Fields |= win32con.DM_PAPERWIDTH | win32con.DM_PAPERLENGTH
                        pinfo["pDevMode"] = dm
                        win32print.SetPrinter(hprinter, 2, pinfo, 0)
                        return True
            finally:
                win32print.ClosePrinter(hprinter)
        except Exception as e:
            print(f"[PageGenerator] Note on configure_roll_printer_size: {e}")
        return False

    def print_direct_gdi(
        self,
        images: List[Image.Image],
        printer_name: str,
        doc_name: str = "Shelf Labels"
    ) -> bool:
        """
        الطباعة المباشرة عبر Windows GDI (Native Printing).
        ترسل الصور مباشرة إلى محرك طابعة ويندوز دون الحاجة لبرامج PDF وسيطة،
        مما يضمن ملء الملصق بدقة 100% وبدون أي تصغير أو هوامش غير مرغوبة.
        """
        import win32ui, win32con
        from PIL import ImageWin

        hdc = win32ui.CreateDC()
        hdc.CreatePrinterDC(printer_name)
        try:
            w = hdc.GetDeviceCaps(win32con.HORZRES)
            h = hdc.GetDeviceCaps(win32con.VERTRES)

            hdc.StartDoc(doc_name)
            for img in images:
                hdc.StartPage()
                rgb_img = img.convert("RGB")
                dib = ImageWin.Dib(rgb_img)
                dib.draw(hdc.GetHandleOutput(), (0, 0, w, h))
                hdc.EndPage()
            hdc.EndDoc()
            return True
        finally:
            hdc.DeleteDC()

    def print_to_printer(
        self,
        items: List[LabelItem],
        paper_type: str = "a4",
        start_position: int = 1,
        draw_cut_guides: bool = True,
        draw_roll_border: bool = False,
        printer_name: Optional[str] = None
    ) -> str:
        """
        طباعة الملصقات مباشرة إلى الطابعة المحددة.
        - في وضع الرول: تضبط مقاس الورق في الطابعة إلى 60×40 مم وتطبع مباشرة عبر GDI لضمان الحجم الكامل 100%.
        - في حال عدم توفر GDI أو حدوث استثناء، ترجع إلى أسلوب ملف PDF والطباعة عبر النظام.
        """
        effective_printer = printer_name
        if not effective_printer or effective_printer == "[الطابعة الافتراضية للنظام]":
            try:
                import win32print
                effective_printer = win32print.GetDefaultPrinter()
            except Exception:
                effective_printer = None

        if paper_type == "roll":
            # 1. التأكد التلقائي من ضبط مقاس المشغل في ويندوز على 60×40 مم
            if effective_printer:
                self.configure_roll_printer_size(effective_printer, 60.0, 40.0)

            # 2. توليد صور ملصقات الرول
            roll_images = self.generate_roll_labels(items, draw_border=draw_roll_border)

            # 3. محاولة الطباعة المباشرة عبر GDI لملء الملصق بنسبة 100%
            if effective_printer and "print to pdf" not in effective_printer.lower():
                try:
                    self.print_direct_gdi(roll_images, effective_printer, doc_name="Shelf Labels Roll")
                    return "GDI_SUCCESS"
                except Exception as e:
                    print(f"[PageGenerator] Direct GDI print failed ({e}), falling back to PDF...")

        # في وضع A4 أو في حال الفشل: الطباعة عبر ملف PDF
        tmp_dir = tempfile.gettempdir()
        prefix = "shelf_labels_roll" if paper_type == "roll" else "shelf_labels_a4"
        pdf_path = os.path.join(tmp_dir, f"{prefix}_to_print.pdf")

        self.save_pdf(
            items,
            pdf_path,
            paper_type=paper_type,
            start_position=start_position,
            draw_cut_guides=draw_cut_guides,
            draw_roll_border=draw_roll_border
        )

        self._send_file_to_printer(pdf_path, printer_name=effective_printer)
        return pdf_path

    def _send_file_to_printer(self, pdf_path: str, printer_name: Optional[str] = None):
        """
        إرسال ملف PDF إلى الطابعة المحددة عبر نظام ويندوز.
        إذا تم تحديد طابعة مخصصة وليست الافتراضية، يتم ضبطها مؤقتاً كطابعة افتراضية
        ثم إرجاع الطابعة السابقة في خيط منفصل لضمان استلام أمر الطباعة.
        """
        original_printer = None
        need_restore = False

        if printer_name and printer_name not in ("", "default", "[الطابعة الافتراضية للنظام]"):
            try:
                import win32print
                original_printer = win32print.GetDefaultPrinter()
                if original_printer != printer_name:
                    win32print.SetDefaultPrinter(printer_name)
                    need_restore = True
            except Exception as e:
                print(f"[PageGenerator] Warning setting default printer: {e}")

        try:
            os.startfile(pdf_path, "print")
        except Exception as e:
            print(f"[PageGenerator] Direct print failed ({e}), opening file...")
            os.startfile(pdf_path)
        finally:
            if need_restore and original_printer:
                def restore(target_name):
                    import time
                    time.sleep(4)
                    try:
                        import win32print
                        win32print.SetDefaultPrinter(target_name)
                    except Exception:
                        pass
                import threading
                threading.Thread(target=restore, args=(original_printer,), daemon=True).start()
