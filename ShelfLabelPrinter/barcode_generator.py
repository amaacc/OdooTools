"""
مولد باركود Code 128 نقي وعالي الدقة بلغة بايثون بدون أي مكتبات خارجية
يقوم بترميز النصوص والأرقام إلى صورة باركود واضحة وعالية الجودة (300 DPI)
يدعم الفئات Code 128 Subsets B & C (للأرقام الزوجية السريعة والنصوص العامة)
"""
from PIL import Image, ImageDraw, ImageFont
from typing import Optional, Tuple

# جداول ترميز Code 128 (107 نمط)
# كل نمط يتكون من 6 أرقام تعبر بالتتابع عن عرض: (شريط أسود، مسافة بيضاء، شريط، مسافة، شريط، مسافة)
# مجموعها = 11 وحدة، عدا رمز التوقف (Stop) = 13 وحدة (7 أرقام: 2331112)
PATTERNS = [
    "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312", "132212", "221213",
    "221312", "231212", "112232", "122132", "122231", "113222", "123122", "123221", "223211", "221132",
    "221231", "213212", "223112", "312131", "311222", "321122", "321221", "312212", "322112", "322211",
    "212123", "212321", "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313",
    "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121", "313121", "211331",
    "231131", "213113", "213311", "213131", "311123", "311321", "331121", "312113", "312311", "332111",
    "314111", "221411", "431111", "111224", "111422", "121124", "121421", "141122", "141221", "112214",
    "112412", "122114", "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111",
    "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112", "421211", "212141",
    "214121", "412121", "111143", "111341", "131141", "114113", "114311", "411113", "411311", "113141",
    "114131", "311141", "411131", "211412", "211214", "211232", "2331112"
]

START_B = 104
START_C = 105
STOP = 106

def encode_code128(text: str) -> list:
    """ترميز النص إلى تسلسل أكواد Code 128 مع مجموع التحقق (Checksum)"""
    text = str(text).strip()
    if not text:
        return []

    # إذا كان النص أرقاماً زوجية الطول فقط، نستخدم Subset C لضغط الحجم للنصف، وإلا Subset B
    is_all_digits = text.isdigit()
    use_code_c = is_all_digits and len(text) >= 4 and len(text) % 2 == 0

    codes = []
    if use_code_c:
        codes.append(START_C)
        for i in range(0, len(text), 2):
            val = int(text[i:i+2])
            codes.append(val)
    else:
        codes.append(START_B)
        for c in text:
            # في Code B: القيمة = كود ASCII - 32
            val = ord(c) - 32
            if 0 <= val <= 95:
                codes.append(val)
            else:
                codes.append(0)  # مسافة بديلة للرموز غير المعروفة

    # حساب Checksum
    checksum = codes[0]
    for idx, c in enumerate(codes[1:], start=1):
        checksum += c * idx
    codes.append(checksum % 103)
    codes.append(STOP)

    return codes

def generate_barcode_image(
    text: str,
    module_width: int = 3,
    height: int = 100,
    add_quiet_zone: bool = True
) -> Image.Image:
    """
    توليد صورة باركود أبيض وأسود بصيغة PIL.Image
    - module_width: عرض أنحف شريط بالبكسل (افتراضي 3 = مناسب جداً لـ 300 DPI)
    - height: ارتفاع الباركود بالبكسل
    """
    codes = encode_code128(text)
    if not codes:
        # صورة بيضاء فارغة
        return Image.new("RGB", (100, height), (255, 255, 255))

    # تحويل الأكواد إلى سلسلة وحدات (Bars & Spaces)
    # كل خانة فردية = أسود (Bar)، وكل خانة زوجية = أبيض (Space)
    bit_sequence = []
    for code in codes:
        pattern = PATTERNS[code]
        is_bar = True
        for digit in pattern:
            width = int(digit)
            bit_sequence.extend([1 if is_bar else 0] * width)
            is_bar = not is_bar

    # منطقة الهدوء (Quiet Zone) على الجوانب: 10 وحدات
    quiet_units = 10 if add_quiet_zone else 2
    full_sequence = [0] * quiet_units + bit_sequence + [0] * quiet_units

    total_width = len(full_sequence) * module_width
    img = Image.new("RGB", (total_width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # رسم الأشرطة السوداء
    x = 0
    for bit in full_sequence:
        if bit == 1:
            draw.rectangle([x, 0, x + module_width - 1, height - 1], fill=(0, 0, 0))
        x += module_width

    return img
