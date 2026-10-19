"""
وحدة معالجة النص العربي وتشكيل الحروف (Arabic Shaper & BiDi Reorderer)
مكتوبة بلغة بايثون نقية 100% بدون أي مكتبات خارجية لتشغيل سريع ومضمون على أي جهاز
تقوم بربط الحروف العربية (Presentation Forms-B) وعكس الاتجاه للعرض الصحيح في Pillow
مع معالجة متقدمة للأرقام (الشرقية والغربية) والرموز والكلمات الإنجليزية لمنع قلب الأرقام
"""
import re

# خريطة أشكال الحروف العربية: [معزول (Isolated), نهائي (Final), بدائي (Initial), وسطي (Medial)]
ARABIC_FORMS = {
    # همزة
    '\u0621': ('\uFE80', '\uFE80', '\uFE80', '\uFE80'),
    # أ - ألف همزة فوق
    '\u0622': ('\uFE81', '\uFE82', '\uFE81', '\uFE82'),
    '\u0623': ('\uFE83', '\uFE84', '\uFE83', '\uFE84'),
    # ؤ - واو همزة
    '\u0624': ('\uFE85', '\uFE86', '\uFE85', '\uFE86'),
    # إ - ألف همزة تحت
    '\u0625': ('\uFE87', '\uFE88', '\uFE87', '\uFE88'),
    # ئ - ياء همزة
    '\u0626': ('\uFE89', '\uFE8A', '\uFE8B', '\uFE8C'),
    # ا - ألف
    '\u0627': ('\uFE8D', '\uFE8E', '\uFE8D', '\uFE8E'),
    # ب
    '\u0628': ('\uFE8F', '\uFE90', '\uFE91', '\uFE92'),
    # ة - تاء مربوطة
    '\u0629': ('\uFE93', '\uFE94', '\uFE93', '\uFE94'),
    # ت
    '\u062A': ('\uFE95', '\uFE96', '\uFE97', '\uFE98'),
    # ث
    '\u062B': ('\uFE99', '\uFE9A', '\uFE9B', '\uFE9C'),
    # ج
    '\u062C': ('\uFE9D', '\uFE9E', '\uFE9F', '\uFEA0'),
    # ح
    '\u062D': ('\uFEA1', '\uFEA2', '\uFEA3', '\uFEA4'),
    # خ
    '\u062E': ('\uFEA5', '\uFEA6', '\uFEA7', '\uFEA8'),
    # د
    '\u062F': ('\uFEA9', '\uFEAA', '\uFEA9', '\uFEAA'),
    # ذ
    '\u0630': ('\uFEAB', '\uFEAC', '\uFEAB', '\uFEAC'),
    # ر
    '\u0631': ('\uFEAD', '\uFEAE', '\uFEAD', '\uFEAE'),
    # ز
    '\u0632': ('\uFEAF', '\uFEB0', '\uFEAF', '\uFEB0'),
    # س
    '\u0633': ('\uFEB1', '\uFEB2', '\uFEB3', '\uFEB4'),
    # ش
    '\u0634': ('\uFEB5', '\uFEB6', '\uFEB7', '\uFEB8'),
    # ص
    '\u0635': ('\uFEB9', '\uFEBA', '\uFEBB', '\uFEBC'),
    # ض
    '\u0636': ('\uFEBD', '\uFEBE', '\uFEBF', '\uFEC0'),
    # ط
    '\u0637': ('\uFEC1', '\uFEC2', '\uFEC3', '\uFEC4'),
    # ظ
    '\u0638': ('\uFEC5', '\uFEC6', '\uFEC7', '\uFEC8'),
    # ع
    '\u0639': ('\uFEC9', '\uFECA', '\uFECB', '\uFECC'),
    # غ
    '\u063A': ('\uFECD', '\uFECE', '\uFECF', '\uFED0'),
    # تطويل ـ
    '\u0640': ('\u0640', '\u0640', '\u0640', '\u0640'),
    # ف
    '\u0641': ('\uFED1', '\uFED2', '\uFED3', '\uFED4'),
    # ق
    '\u0642': ('\uFED5', '\uFED6', '\uFED7', '\uFED8'),
    # ك
    '\u0643': ('\uFED9', '\uFEDA', '\uFEDB', '\uFEDC'),
    # ل
    '\u0644': ('\uFEDD', '\uFEDE', '\uFEDF', '\uFEE0'),
    # م
    '\u0645': ('\uFEE1', '\uFEE2', '\uFEE3', '\uFEE4'),
    # ن
    '\u0646': ('\uFEE5', '\uFEE6', '\uFEE7', '\uFEE8'),
    # هـ
    '\u0647': ('\uFEE9', '\uFEEA', '\uFEEB', '\uFEEC'),
    # و
    '\u0648': ('\uFEED', '\uFEEE', '\uFEED', '\uFEEE'),
    # ى - ألف مقصورة
    '\u0649': ('\uFEEF', '\uFEF0', '\uFEEF', '\uFEF0'),
    # ي
    '\u064A': ('\uFEF1', '\uFEF2', '\uFEF3', '\uFEF4'),
}

# الحروف التي لا تتصل بما بعدها (فقط من اليمين)
NON_CONNECTING_FORWARD = {
    '\u0621', '\u0622', '\u0623', '\u0624', '\u0625',
    '\u0627', '\u0629', '\u062F', '\u0630', '\u0631',
    '\u0632', '\u0648', '\u0649'
}

# مدغمات اللام ألف (Lam-Alef Ligatures)
LAM_ALEF = {
    ('\u0644', '\u0622'): ('\uFEF5', '\uFEF6'),  # لآ
    ('\u0644', '\u0623'): ('\uFEF7', '\uFEF8'),  # لأ
    ('\u0644', '\u0625'): ('\uFEF9', '\uFEFA'),  # لإ
    ('\u0644', '\u0627'): ('\uFEFB', '\uFEFC'),  # لا
}

# الحركات العربية
HARAKAT = {
    '\u064B', '\u064C', '\u064D', '\u064E',
    '\u064F', '\u0650', '\u0651', '\u0652', '\u0670'
}

def is_arabic_char(c: str) -> bool:
    if not c:
        return False
    code = ord(c)
    # الحروف الأبجدية العربية فقط (بدون الأرقام)
    return (0x0621 <= code <= 0x064A) or (0x0671 <= code <= 0x06D3) or (0xFE70 <= code <= 0xFEFC)

def reshape_arabic_word(word: str) -> str:
    """تشكيل كلمة عربية واحدة وربط حروفها بدقة مع دعم اللام ألف"""
    if not word:
        return ""
    
    clean_chars = [c for c in word if c not in HARAKAT]
    n = len(clean_chars)
    if n == 0:
        return ""

    shaped = []
    i = 0
    while i < n:
        curr = clean_chars[i]

        # فحص إدغام اللام ألف
        if curr == '\u0644' and i + 1 < n and clean_chars[i+1] in ('\u0622', '\u0623', '\u0625', '\u0627'):
            alef = clean_chars[i+1]
            connected_before = (i > 0 and 
                                clean_chars[i-1] in ARABIC_FORMS and 
                                clean_chars[i-1] not in NON_CONNECTING_FORWARD)
            
            iso, fin = LAM_ALEF.get((curr, alef), ('\uFEFB', '\uFEFC'))
            shaped.append(fin if connected_before else iso)
            i += 2
            continue

        if curr not in ARABIC_FORMS:
            shaped.append(curr)
            i += 1
            continue

        connected_before = (i > 0 and 
                            clean_chars[i-1] in ARABIC_FORMS and 
                            clean_chars[i-1] not in NON_CONNECTING_FORWARD)

        connected_after = False
        if i + 1 < n and curr not in NON_CONNECTING_FORWARD:
            nxt = clean_chars[i+1]
            if nxt in ARABIC_FORMS:
                connected_after = True

        forms = ARABIC_FORMS[curr]
        if connected_before and connected_after:
            shaped.append(forms[3])  # Medial
        elif connected_before and not connected_after:
            shaped.append(forms[1])  # Final
        elif not connected_before and connected_after:
            shaped.append(forms[2])  # Initial
        else:
            shaped.append(forms[0])  # Isolated

        i += 1

    return "".join(shaped)

def reshape_and_bidi(text: str) -> str:
    """
    تحويل جملة كاملة إلى نص مرتب جاهز للرسم في Pillow (من اليسار لليمين)
    - توحيد الأرقام الشرقية (٢٥٠) إلى الأرقام القياسية (250) لمنع أي التباس
    - الحفاظ التام على قراءة الأرقام من اليسار لليمين بدون أي قلب
    - دعم الكلمات الإنجليزية والأرقام العشرية (مثل 3.0)
    """
    if not text:
        return ""

    # 1. تحويل الأرقام العربية الشرقية (٠١٢٣٤٥٦٧٨٩) إلى القياسية (0123456789)
    # لضمان اتساق قراءتها الدقيقة في التجزئة والطباعة
    eastern_digits = '٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹'
    western_digits = '01234567890123456789'
    text = text.translate(str.maketrans(eastern_digits, western_digits))

    # 2. تقسيم النص بدقة عالية إلى:
    # - كلمات عربية
    # - أرقام (صحيحة أو عشرية مثل 250 أو 3.0)
    # - كلمات إنجليزية
    # - مسافات ورموز
    tokens = re.findall(
        r'[\u0621-\u064A\u0671-\u06D3\uFE70-\uFEFC]+|[0-9]+(?:\.[0-9]+)?|[a-zA-Z]+|\s+|.',
        text
    )
    
    processed_tokens = []
    has_arabic = False
    for tok in tokens:
        if any(is_arabic_char(c) for c in tok):
            has_arabic = True
            shaped = reshape_arabic_word(tok)
            # قلب حروف الكلمة العربية نفسها للعرض LTR
            processed_tokens.append(shaped[::-1])
        else:
            # الأرقام والكلمات الإنجليزية تظل بترتيبها الطبيعي
            processed_tokens.append(tok)

    if not has_arabic:
        return text

    # في سياق RTL، نعكس ترتيب الكلمات بحيث تظهر الكلمة الأولى في أقصى اليمين
    bracket_map = {
        '(': ')', ')': '(',
        '[': ']', ']': '[',
        '{': '}', '}': '{',
        '<': '>', '>': '<',
        '«': '»', '»': '«'
    }

    final_tokens = []
    for tok in reversed(processed_tokens):
        mapped_tok = "".join(bracket_map.get(c, c) for c in tok)
        final_tokens.append(mapped_tok)

    return "".join(final_tokens)
