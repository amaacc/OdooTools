"""
محرك رسم وتصميم ملصق الرف الفاخر (Label Renderer)
دقة 300 DPI — مقاس 60×40 مم (708×472 بكسل)
المواصفات المحدثة:
- ترويسة بشعارين متجاورين في المنتصف بحجم كبير
- خط عربي نقي ورائع (Calibri Bold) بحجم كبير وبارز
- التفاف سليم ومتوازن للسطور (Balanced 2-Line Wrapping) يمنع الكلمات المعزولة
- خط إنجليزي واضح وعريض بلون أسود صريح
- ضبط تلقائي ذكي لحجم خط السعر (Auto-Fit Price Font) لمنع خروج الأرقام الكبيرة مثل 1314.50 عن المربع
- باركود Code 128 مرتفع وسريع المسح + أرقام 34pt كبيرة مقروءة للعين بدون مسافات
- استغلال ديناميكي احترافي لكامل المساحة الرأسية
- رمز الريال السعودي الجديد المعتمد (ساما) ⃁
"""
import os
from typing import Optional, Tuple, List
from PIL import Image, ImageDraw, ImageFont

from label_model import LabelItem
from arabic_shaper import reshape_and_bidi
from barcode_generator import generate_barcode_image
from path_utils import get_resource_path

# الأبعاد بالبكسل عند 300 DPI (60 مم × 40 مم)
LABEL_WIDTH = 708
LABEL_HEIGHT = 472

# مسار الخطوط المعتمدة
WIN_FONTS = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")
FONT_ARABIC_BOLD = os.path.join(WIN_FONTS, "calibrib.ttf") if os.path.exists(os.path.join(WIN_FONTS, "calibrib.ttf")) else os.path.join(WIN_FONTS, "arialbd.ttf")
FONT_ARABIC_REG = os.path.join(WIN_FONTS, "calibri.ttf") if os.path.exists(os.path.join(WIN_FONTS, "calibri.ttf")) else os.path.join(WIN_FONTS, "arial.ttf")
FONT_ENGLISH_BOLD = os.path.join(WIN_FONTS, "arialbd.ttf")

# مسار رمز الريال السعودي الجديد
RIYAL_SYMBOL_PATH = get_resource_path(os.path.join("assets", "saudi_riyal_symbol.png"))

def get_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(font_path, size)
    except Exception:
        return ImageFont.load_default()

def wrap_arabic_smart(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.Draw) -> List[str]:
    """
    التفاف ذكي ومتوازن للنص العربي:
    إذا كان النص يتسع في سطر واحد، يعيده في سطر واحد.
    إذا تجاوز السطر، يقسمه إلى سطرين متوازنين في الطول (بدون ترك كلمة واحدة يتيمة في السطر الثاني).
    """
    clean_text = text.strip()
    if not clean_text:
        return []

    # فحص سطر واحد
    bbox = draw.textbbox((0, 0), reshape_and_bidi(clean_text), font=font)
    if (bbox[2] - bbox[0]) <= max_width:
        return [clean_text]

    words = clean_text.split()
    n = len(words)
    if n <= 1:
        return [clean_text]

    # تقسيم متوازن إلى سطرين
    best_diff = 9999
    best_idx = n // 2
    for i in range(1, n):
        l1 = " ".join(words[:i])
        l2 = " ".join(words[i:])
        w1 = draw.textbbox((0, 0), reshape_and_bidi(l1), font=font)[2] - draw.textbbox((0, 0), reshape_and_bidi(l1), font=font)[0]
        w2 = draw.textbbox((0, 0), reshape_and_bidi(l2), font=font)[2] - draw.textbbox((0, 0), reshape_and_bidi(l2), font=font)[0]
        
        # نفضل التقسيم الذي يجعل السطرين داخل max_width ومتساويين تقريباً
        if w1 <= max_width and w2 <= max_width:
            diff = abs(w1 - w2)
            if diff < best_diff:
                best_diff = diff
                best_idx = i

    l1 = " ".join(words[:best_idx])
    l2 = " ".join(words[best_idx:])
    return [l1, l2]

class LabelRenderer:
    def __init__(
        self,
        logo1_path: Optional[str] = None,
        logo2_path: Optional[str] = None
    ):
        self.logo1_path = logo1_path
        self.logo2_path = logo2_path
        
        self.logo1_img = self._load_logo(self.logo1_path)
        self.logo2_img = self._load_logo(self.logo2_path)
        
        # تحميل رمز الريال السعودي
        self.riyal_img = None
        if os.path.exists(RIYAL_SYMBOL_PATH):
            try:
                self.riyal_img = Image.open(RIYAL_SYMBOL_PATH).convert("RGBA")
            except Exception as e:
                print(f"[LabelRenderer] Riyal symbol load error: {e}")

    def _load_logo(self, path: Optional[str]) -> Optional[Image.Image]:
        if path and os.path.exists(path):
            try:
                return Image.open(path).convert("RGBA")
            except Exception as e:
                print(f"[LabelRenderer] Error loading logo {path}: {e}")
        return None

    def render_label(self, item: LabelItem, draw_border: bool = True) -> Image.Image:
        """
        رسم ملصق مفرد بالكامل بأعلى معايير الأناقة والوضوح
        - draw_border: رسم إطار خارجي رمادي خفيف للملصق (مفيد للقص في ورق A4)
        """
        # إنشاء الخلفية البيضاء
        img = Image.new("RGBA", (LABEL_WIDTH, LABEL_HEIGHT), (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)

        # -------------------------------------------------------------
        # 1. إطار الملصق (خط القص للأوراق العادية)
        # -------------------------------------------------------------
        if draw_border:
            border_color = (215, 215, 215, 255)
            draw.rectangle([0, 0, LABEL_WIDTH - 1, LABEL_HEIGHT - 1], outline=border_color, width=1)

        # -------------------------------------------------------------
        # 2. الترويسة: الشعاران كبيران ومتجاوران في المنتصف
        # -------------------------------------------------------------
        header_top = 8
        header_height = 72
        max_logo_h = 66

        l1_scaled = None
        l2_scaled = None

        if self.logo1_img:
            l1_scaled = self.logo1_img.copy()
            asp1 = l1_scaled.width / l1_scaled.height
            target_w1 = min(340, int(max_logo_h * asp1))
            l1_scaled = l1_scaled.resize((target_w1, max_logo_h), Image.Resampling.LANCZOS)

        if self.logo2_img:
            l2_scaled = self.logo2_img.copy()
            asp2 = l2_scaled.width / l2_scaled.height
            target_w2 = min(120, int(max_logo_h * asp2))
            l2_scaled = l2_scaled.resize((target_w2, max_logo_h), Image.Resampling.LANCZOS)

        gap = 25
        if l1_scaled and l2_scaled:
            total_logos_w = l2_scaled.width + gap + l1_scaled.width
            group_start_x = (LABEL_WIDTH - total_logos_w) // 2

            y2 = header_top + (header_height - l2_scaled.height) // 2
            img.paste(l2_scaled, (group_start_x, y2), l2_scaled)

            x1 = group_start_x + l2_scaled.width + gap
            y1 = header_top + (header_height - l1_scaled.height) // 2
            img.paste(l1_scaled, (x1, y1), l1_scaled)
        elif l1_scaled:
            x1 = (LABEL_WIDTH - l1_scaled.width) // 2
            y1 = header_top + (header_height - l1_scaled.height) // 2
            img.paste(l1_scaled, (x1, y1), l1_scaled)
        elif l2_scaled:
            x2 = (LABEL_WIDTH - l2_scaled.width) // 2
            y2 = header_top + (header_height - l2_scaled.height) // 2
            img.paste(l2_scaled, (x2, y2), l2_scaled)
        # -------------------------------------------------------------
        # 3. مستطيل الوصف الجمالي البديع (Description Box)
        # -------------------------------------------------------------
        content_margin_x = 18
        desc_box_x1 = content_margin_x
        desc_box_x2 = LABEL_WIDTH - content_margin_x
        desc_box_w = desc_box_x2 - desc_box_x1
        desc_box_y1 = 82
        desc_box_y2 = 234
        desc_box_h = desc_box_y2 - desc_box_y1

        desc_border_color = (120, 130, 145, 255)
        draw.rounded_rectangle(
            [desc_box_x1, desc_box_y1, desc_box_x2, desc_box_y2],
            radius=16,
            fill=(255, 255, 255, 255),
            outline=desc_border_color,
            width=2
        )

        inner_pad_x = 18
        usable_inner_w = desc_box_w - (inner_pad_x * 2)

        en_name = (item.name_en or "").strip()
        has_en = bool(en_name and en_name.lower() != item.name_ar.lower())

        ar_test_font = get_font(FONT_ARABIC_BOLD, 36 if has_en else 38)
        ar_lines = wrap_arabic_smart(item.name_ar, ar_test_font, usable_inner_w, draw)

        if has_en:
            if len(ar_lines) <= 1:
                ar_font = get_font(FONT_ARABIC_BOLD, 37)
                ar_y = desc_box_y1 + 20
                en_font_size = 25
                en_y = desc_box_y1 + 86
            else:
                ar_font = get_font(FONT_ARABIC_BOLD, 31)
                ar_lines = wrap_arabic_smart(item.name_ar, ar_font, usable_inner_w, draw)
                ar_y = desc_box_y1 + 12
                en_font_size = 23
                en_y = desc_box_y1 + 94

            # رسم العربي
            curr_ar_y = ar_y
            line_spacing = 40 if len(ar_lines) > 1 else 0
            for line in ar_lines:
                shaped_line = reshape_and_bidi(line)
                bbox = draw.textbbox((0, 0), shaped_line, font=ar_font)
                line_w = bbox[2] - bbox[0]
                x = desc_box_x2 - inner_pad_x - line_w
                draw.text((x, curr_ar_y), shaped_line, fill=(10, 10, 10, 255), font=ar_font)
                curr_ar_y += line_spacing

            # رسم الإنجليزي
            en_font = get_font(FONT_ENGLISH_BOLD, en_font_size)
            en_bbox = draw.textbbox((0, 0), en_name, font=en_font)
            en_w = en_bbox[2] - en_bbox[0]
            if en_w > usable_inner_w:
                while len(en_name) > 5 and en_w > usable_inner_w:
                    en_name = en_name[:-4] + "..."
                    en_bbox = draw.textbbox((0, 0), en_name, font=en_font)
                    en_w = en_bbox[2] - en_bbox[0]
            draw.text((desc_box_x1 + inner_pad_x, en_y), en_name, fill=(0, 0, 0, 255), font=en_font)

        else:
            # عربي فقط - توسيط عمودي كامل
            if len(ar_lines) <= 1:
                ar_font = get_font(FONT_ARABIC_BOLD, 40)
                shaped = reshape_and_bidi(ar_lines[0])
                bbox = draw.textbbox((0, 0), shaped, font=ar_font)
                line_w = bbox[2] - bbox[0]
                line_h = bbox[3] - bbox[1]
                x = desc_box_x2 - inner_pad_x - line_w
                y = desc_box_y1 + (desc_box_h - line_h) // 2 - 4
                draw.text((x, y), shaped, fill=(10, 10, 10, 255), font=ar_font)
            else:
                ar_font = get_font(FONT_ARABIC_BOLD, 35)
                ar_lines = wrap_arabic_smart(item.name_ar, ar_font, usable_inner_w, draw)
                total_h = 44 * len(ar_lines)
                curr_y = desc_box_y1 + (desc_box_h - total_h) // 2
                for line in ar_lines:
                    shaped = reshape_and_bidi(line)
                    bbox = draw.textbbox((0, 0), shaped, font=ar_font)
                    line_w = bbox[2] - bbox[0]
                    x = desc_box_x2 - inner_pad_x - line_w
                    draw.text((x, curr_y), shaped, fill=(10, 10, 10, 255), font=ar_font)
                    curr_y += 44

        # -------------------------------------------------------------
        # 4. القسم السفلي: صندوق السعر والباركود
        # -------------------------------------------------------------
        bottom_area_y = desc_box_y2 + 12
        price_box_w = 280
        price_box_x2 = LABEL_WIDTH - 18
        price_box_x1 = price_box_x2 - price_box_w
        price_box_y1 = bottom_area_y
        price_box_y2 = LABEL_HEIGHT - 18
        price_box_h = price_box_y2 - price_box_y1

        # رسم كادر بطاقة السعر الفخمة
        box_bg_color = (248, 250, 254, 255)
        box_border_color = (15, 45, 95, 255)
        draw.rounded_rectangle(
            [price_box_x1, price_box_y1, price_box_x2, price_box_y2],
            radius=16,
            fill=box_bg_color,
            outline=box_border_color,
            width=2
        )

        # عنوان داخل صندوق السعر: "السعر شامل الضريبة"
        tax_title = reshape_and_bidi("السعر شامل الضريبة")
        tax_font = get_font(FONT_ARABIC_BOLD, 20)
        tax_bbox = draw.textbbox((0, 0), tax_title, font=tax_font)
        tax_w = tax_bbox[2] - tax_bbox[0]
        tax_x = price_box_x1 + (price_box_w - tax_w) // 2
        tax_y = price_box_y1 + 14
        draw.text((tax_x, tax_y), tax_title, fill=(65, 75, 90, 255), font=tax_font)

        # السعر (Bold Numerical Display) مع تصغير تلقائي ذكي لمنع خروجه نهائياً
        price_str = item.formatted_price
        navy_color = (10, 35, 85)
        max_price_content_w = price_box_w - 24  # الحد الأقصى للمحتوى داخل الصندوق

        # احتساب الحجم المناسب ديناميكياً
        price_font_size = 66
        fnt_price = None
        pw, ph = 0, 0
        sym_w, sym_h = 0, 0
        sym_img_resized = None

        while price_font_size >= 32:
            fnt_price = get_font(FONT_ENGLISH_BOLD, price_font_size)
            bbox_p = draw.textbbox((0, 0), price_str, font=fnt_price)
            pw = bbox_p[2] - bbox_p[0]
            ph = bbox_p[3] - bbox_p[1]

            if self.riyal_img:
                sym_h = int(ph * 0.95)
                sym_w = int(sym_h * (self.riyal_img.width / self.riyal_img.height))
            else:
                sym_w, sym_h = 0, 0

            spacing = 10
            total_content_w = pw + (sym_w + spacing if sym_w > 0 else 0)

            if total_content_w <= max_price_content_w or price_font_size <= 32:
                break
            price_font_size -= 2

        # تجهيز صورة الرمز بالحجم المتناسق وتلوينها
        if self.riyal_img and sym_w > 0:
            raw_sym = self.riyal_img.resize((sym_w, sym_h), Image.Resampling.LANCZOS)
            alpha = raw_sym.split()[3]
            sym_img_resized = Image.new("RGBA", (sym_w, sym_h), (*navy_color, 255))
            sym_img_resized.putalpha(alpha)

        # توسيط السعر والرمز بدقة تامة داخل الصندوق
        spacing = 10
        total_content_w = pw + (sym_w + spacing if sym_w > 0 else 0)
        px_start = price_box_x1 + (price_box_w - total_content_w) // 2
        py = price_box_y1 + 54 + (66 - price_font_size) // 3

        # وضع الرمز إلى يسار الرقم
        if sym_img_resized:
            sym_x = px_start
            sym_y = py + (ph - sym_h) // 2 + 6
            img.paste(sym_img_resized, (sym_x, sym_y), sym_img_resized)
            price_x = px_start + sym_w + spacing
        else:
            price_x = px_start

        # رسم رقم السعر
        draw.text((price_x, py), price_str, fill=(*navy_color, 255), font=fnt_price)

        # -------------------------------------------------------------
        # 6. منطقة الباركود: باركود طويل (105-115px) + أرقام 34pt ضخمة مقروءة للعين
        # -------------------------------------------------------------
        barcode_area_x = content_margin_x
        barcode_area_w = price_box_x1 - content_margin_x - 15
        clean_barcode = (item.barcode or "").strip()

        if clean_barcode:
            # باركود مرتفع وواضح جداً لسرعة المسح بالليزر
            bar_height = min(115, max(85, price_box_h - 60))
            mod_width = 3 if len(clean_barcode) <= 13 else 2
            bc_img = generate_barcode_image(clean_barcode, module_width=mod_width, height=bar_height, add_quiet_zone=False)
            
            if bc_img.width > barcode_area_w:
                target_w = barcode_area_w
                target_h = int(bar_height * (target_w / bc_img.width))
                bc_img = bc_img.resize((target_w, target_h), Image.Resampling.NEAREST)

            bc_x = barcode_area_x + (barcode_area_w - bc_img.width) // 2
            bc_y = bottom_area_y + 8
            img.paste(bc_img, (bc_x, bc_y))

            digits_font = get_font(FONT_ENGLISH_BOLD, 34)
            digits_bbox = draw.textbbox((0, 0), clean_barcode, font=digits_font)
            digits_w = digits_bbox[2] - digits_bbox[0]
            digits_x = barcode_area_x + (barcode_area_w - digits_w) // 2
            digits_y = bc_y + bc_img.height + 6
            draw.text((digits_x, digits_y), clean_barcode, fill=(0, 0, 0, 255), font=digits_font)

        return img.convert("RGB")
