"""
competitor_scraper.py — Multi-Store Competitor Pricing Engine (34 Saudi Stores)
Designed by: عبدالله الخطيب (Abdullah Al-Khatib)
Part of: Odoo Price Comparator & Competitor Intelligence Suite

STRICT POLICY: Search is performed ONLY by product barcode (primary or packaging barcodes).
No name, description, or fuzzy text fallback to prevent irrelevant product matches.

WEIGHT / UNIT SAFETY FILTER:
Numbers representing weight/size (e.g. 600 جم, 500 مل, 100g, 15ml) are strictly
isolated and NEVER extracted as prices.
"""

import sys
import re
import html
import urllib.request
import urllib.parse
import ssl
import time
from collections import defaultdict
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

# Common Browser Headers
BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'ar,en-US;q=0.8,en;q=0.5',
    'Cache-Control': 'no-cache',
}

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


# ─────────────────────────────────────────────────────────────────────────────
# 📋 MASTER STORE REGISTRY (34 Stores)
# ─────────────────────────────────────────────────────────────────────────────
STORES_REGISTRY = [
    # ── 1. دار الأميرات
    {'key': 'daralamirat', 'name': 'دار الأميرات', 'domain': 'daralamirat.com.sa', 'platform': 'salla', 'color': '#8B5CF6'},
    # ── 2. كير أوتلت
    {'key': 'care_outlet', 'name': 'كير أوتلت', 'domain': 'care-outlet.com', 'platform': 'zid', 'color': '#10B981'},
    # ── 3. نزيه
    {'key': 'nazih', 'name': 'نزيه', 'domain': 'nazih.sa', 'platform': 'magento', 'color': '#EC4899'},
    # ── 4. النهدي أونلاين
    {'key': 'nahdi', 'name': 'النهدي أونلاين', 'domain': 'nahdionline.com', 'platform': 'nahdi', 'color': '#0284C7'},
    # ── 5. صيدلية كوم
    {'key': 'sidalih', 'name': 'صيدلية.كوم', 'domain': 'sidalih.com', 'platform': 'shopify', 'color': '#10B981'},
    # ── 6. متجر كنوز
    {'key': 'knooz', 'name': 'متجر كنوز', 'domain': 'knooz-store.com', 'platform': 'zid', 'color': '#D97706'},
    # ── 7. نسائم الجمال
    {'key': 'nasaem', 'name': 'نسائم الجمال', 'domain': 'nasaembeauty.com', 'platform': 'zid', 'color': '#EC4899'},
    # ── 8. وهج التجميل
    {'key': 'wahaj', 'name': 'وهج التجميل', 'domain': 'www.wahajbeauty.com', 'platform': 'shopify', 'color': '#F59E0B'},
    # ── 9. الصيدلية المتحدة
    {'key': 'unitedpharmacy', 'name': 'الصيدلية المتحدة', 'domain': 'unitedpharmacy.sa', 'platform': 'magento', 'color': '#0284C7'},
    # ── 10. سباما الطبية
    {'key': 'spama', 'name': 'سباما الطبية', 'domain': 'spama.sa', 'platform': 'opencart', 'color': '#0284C7'},
    # ── 11. بيوتي كلاود
    {'key': 'beautycloud', 'name': 'بيوتي كلاود', 'domain': 'beautycloudshop.com', 'platform': 'woocommerce', 'color': '#9333EA'},
    # ── 12. أسرار كير
    {'key': 'asrar', 'name': 'أسرار كير', 'domain': 'asrar-co.com', 'platform': 'salla', 'color': '#8B5CF6'},
    # ── 13. آي براند
    {'key': 'ibrand', 'name': 'آي براند', 'domain': 'ibrand.com.sa', 'platform': 'salla', 'color': '#3B82F6'},
    # ── 14. متجر عناية
    {'key': 'enaya', 'name': 'متجر عناية', 'domain': 'enayastore.com', 'platform': 'salla', 'color': '#10B981'},
    # ── 15. كير السعودية
    {'key': 'careksa', 'name': 'كير السعودية', 'domain': 'careksa.com', 'platform': 'salla', 'color': '#14B8A6'},
    # ── 16. إمداد
    {'key': 'emdad', 'name': 'إمداد', 'domain': 'emdad.co', 'platform': 'salla', 'color': '#3B82F6'},
    # ── 17. عوارض
    {'key': 'awarid', 'name': 'عوارض', 'domain': 'sa.awarid.com', 'platform': 'salla', 'color': '#6366F1'},
    # ── 18. بانو لايف ستايل
    {'key': 'banu', 'name': 'بانو لايف ستايل', 'domain': 'banulifestyle.com', 'platform': 'salla', 'color': '#F43F5E'},
    # ── 19. دار المشاغل
    {'key': 'daralmashaghel', 'name': 'دار المشاغل', 'domain': 'daralmashaghel.com', 'platform': 'salla', 'color': '#A855F7'},
    # ── 20. إيزي كير
    {'key': 'easy_sa', 'name': 'إيزي كير', 'domain': 'easy-sa.com', 'platform': 'salla', 'color': '#06B6D4'},
    # ── 21. مدينة الأناقة
    {'key': 'alanaqhah', 'name': 'مدينة الأناقة', 'domain': 'alanaqhahcity.com', 'platform': 'salla', 'color': '#E11D48'},
    # ── 22. أحلام البلد
    {'key': 'ahlamalbald', 'name': 'أحلام البلد', 'domain': 'ahlamalbaldbeauty.com', 'platform': 'salla', 'color': '#F59E0B'},
    # ── 23. الخزامى كير
    {'key': 'alkhuzama', 'name': 'الخزامى كير', 'domain': 'alkhuzamacare.com', 'platform': 'salla', 'color': '#8B5CF6'},
    # ── 24. سنيد
    {'key': 'sunaid', 'name': 'سنيد', 'domain': 'sunaidsa.com', 'platform': 'salla', 'color': '#F97316'},
    # ── 25. دار الصوالين
    {'key': 'daralswalen', 'name': 'دار الصوالين', 'domain': 'daralswalen.com', 'platform': 'salla', 'color': '#A855F7'},
    # ── 26. سمايل
    {'key': 'samaiel', 'name': 'سمايل', 'domain': 'samaiel.com', 'platform': 'salla', 'color': '#06B6D4'},
    # ── 27. أزال للتجميل
    {'key': 'azal', 'name': 'أزال للتجميل', 'domain': 'azalbeauty.com.sa', 'platform': 'salla', 'color': '#E11D48'},
    # ── 28. متجر الخبير
    {'key': 'alkhabeer', 'name': 'متجر الخبير', 'domain': 'alkhabeershop.com', 'platform': 'salla', 'color': '#2563EB'},
    # ── 29. أفكار العناية
    {'key': 'afkar', 'name': 'أفكار العناية', 'domain': 'afkaraleinaya.com', 'platform': 'salla', 'color': '#EC4899'},
    # ── 30. فوشي
    {'key': 'fuchi', 'name': 'فوشي', 'domain': 'fuchi.sa', 'platform': 'salla', 'color': '#DB2777'},
    # ── 31. غاية أونلاين
    {'key': 'ghaya', 'name': 'غاية أونلاين', 'domain': 'ghayaonline.com', 'platform': 'salla', 'color': '#059669'},
    # ── 32. ماضي إنترناشيونال
    {'key': 'madi', 'name': 'ماضي إنترناشيونال', 'domain': 'madi-intl.com', 'platform': 'custom', 'color': '#475569'},
    # ── 33. أوفر نايس
    {'key': 'theovernice', 'name': 'أوفر نايس', 'domain': 'theovernice.com', 'platform': 'salla', 'color': '#F43F5E'},
    # ── 34. تدلل كير
    {'key': 'tdalalcare', 'name': 'تدلل كير', 'domain': 'tdalalcare.com', 'platform': 'salla', 'color': '#06B6D4'},
    # ── 35. موب ماب
    {'key': 'mup_map', 'name': 'موب ماب', 'domain': 'mup-map.com', 'platform': 'zid', 'color': '#8B5CF6'},
]

STORES_MAP = {s['key']: s for s in STORES_REGISTRY}


def is_valid_gtin_barcode(bc):
    """
    STRICT GTIN BARCODE FILTER:
    A valid retail barcode MUST be purely numeric digits and have a standard GTIN length:
    8 (EAN-8), 12 (UPC-A), 13 (EAN-13), or 14 (GTIN-14).
    Rejects text codes, internal SKUs, shelf codes, or short numbers (e.g. '117-03901', '117', 'BOX-1').
    """
    if not bc:
        return False
    s = str(bc).strip()
    return s.isdigit() and len(s) in (8, 12, 13, 14)


def _clean_barcode(bc):
    """Ensure barcode is a valid pure numeric barcode. Returns empty string if invalid."""
    if not bc:
        return ""
    cleaned = re.sub(r'\s+', '', str(bc)).strip()
    if is_valid_gtin_barcode(cleaned):
        return cleaned
    return ""


def extract_unit_from_title(title):
    """
    Extract product size/weight/volume/count from title (e.g. '600 جم', '500 مل', '28 لصقة', '30 حبة', '100 كبسولة').
    """
    if not title:
        return ""
    # 1. Weights and volumes
    m = re.search(r'(\d+(?:\.\d+)?\s*(?:جرام|جم|ملل|مل|كجم|كيلو|لتر|g|gm|ml|kg|l|oz))\b', title, flags=re.I)
    if m:
        return m.group(1).strip()
    # 2. Counts and packaging units (e.g. 28 لصقات, 30 حبة, 60 كبسولة)
    m = re.search(r'(\d+(?:\.\d+)?\s*(?:لصقة|لصقات|لصقه|حبة|حبات|حبه|حبوب|قطعة|قطع|قطعه|شريط|شرائط|أشرطة|أشرطه|كبسولة|كبسولات|كبسوله|قرص|أقراص|أمبولة|أمبولات|امبولة|امبولات|كيس|أكياس|منديل|مناديل|غسلة|غسلات|غسله|جرعة|جرعات|جرعه|زوج|أزواج|علبة|علب|علبه|كرتون|كراتين|عبوة|عبوات|عبوه|pcs|pc|pieces|piece|strips|strip|caps|cap|capsules|capsule|tabs|tab|tablets|tablet|count|ct|pairs|pair|wipes|wipe|sachets|sachet|bags|bag))\b', title, flags=re.I)
    if m:
        return m.group(1).strip()
    return ""


OUT_OF_STOCK_KEYWORDS = [
    'غير متوفر', 'غير متوفره', 'غير متوفرة', 'غير متاحة', 'غير متاح',
    'أعلمني عند التوفر', 'اعلمني عند التوفر', 'إعلامي عند التوفر', 'اعلامي عند التوفر',
    'اشعرني عند التوفر', 'أشعرني عند التوفر',
    'نفذت الكمية', 'نفدت الكمية', 'نفذت', 'نفدت', 'نفذ المخزون', 'نفد المخزون',
    'انتهت الكمية', 'الكمية انتهت', 'مباع بالكامل', 'تم البيع', 'نفذ من المخزون',
    'غير متوفر في المخزون', 'غير متوفر بالمخزون', 'غير متوفرة بالمخزون', 'غير متوفرة في المخزون',
    'out of stock', 'sold out', 'notify when available', 'out-of-stock',
    'btn-product-card-out-of-stock', 'product-out-of-stock', 's-product-card-out-of-stock'
]


def is_out_of_stock_snippet(text):
    """Check if a text snippet, card, or button contains explicit out-of-stock keywords."""
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in OUT_OF_STOCK_KEYWORDS)


def _strip_weights_and_units(text):
    """
    Remove weights, sizes, percentages, packaging counts, cosmetic shades, model numbers,
    ratings, and non-price numbers from a text block so that numbers like:
    '600 جم', '500 مل', '28 لصقة', '30 حبة', '20% خصم', '3.0 بني غامق', 'رقم 3', 'SPF 50'
    are NEVER mistaken for prices.
    """
    if not text:
        return ""
    t = text

    # 1. Remove percentages and discounts (e.g. 20% or 20 % خصم)
    t = re.sub(r'\d+(?:\.\d+)?\s*%\s*(?:خصم)?', ' ', t)

    # 2. Remove retail barcodes / GTINs (8 to 14 digits)
    t = re.sub(r'\b\d{8,14}\b', ' ', t)

    # 3. Remove cosmetic shade / tone designations:
    # Numbers preceded by shade/color labels (e.g. رقم 3, درجة 3.0, shade 01, color 2.1)
    t = re.sub(r'\b(?:رقم|درجة|درجه|لون|درجات|shade|no\.?|n°|num\.?|number|color|colour|tone)\s*:?\s*#?\d+(?:\.\d+)?\b', ' ', t, flags=re.I)
    # Numbers followed or preceded by cosmetic color names (e.g. 3.0 بني غامق, 10.1 أشقر, dark brown 3.0)
    t = re.sub(r'\b\d+(?:\.\d+)?\s*(?:بني|أشقر|اشقر|أسود|اسود|أحمر|احمر|كستنائي|عسلي|رمادي|بلوند|ذهبي|فاتح|غامق|متوسط|مائل|أكحل|اكحل|نحاسي|شوكولاتة|شوكولاته|كراميل|ماهوجني|عاجي|بيج|برونزي|نيود|وردي|زهري|brown|blonde|black|red|chestnut|hazel|grey|gray|dark|light|medium|copper|chocolate|caramel|mahogany|ivory|beige|bronze|nude|pink)\b', ' ', t, flags=re.I)
    t = re.sub(r'\b(?:بني|أشقر|اشقر|أسود|اسود|أحمر|احمر|كستنائي|عسلي|رمادي|بلوند|ذهبي|فاتح|غامق|متوسط|brown|blonde|black|red)\s+\d+(?:\.\d+)?\b', ' ', t, flags=re.I)

    # 4. Remove SPF sun protection ratings (e.g. SPF 50+, SPF50, 50 SPF, حماية 50)
    t = re.sub(r'\b(?:spf|\+)?\s*\d+\s*(?:spf|\+)\b', ' ', t, flags=re.I)
    t = re.sub(r'\bspf\s*\d+\b', ' ', t, flags=re.I)
    t = re.sub(r'\bحماية\s*\d+\+?\b', ' ', t)

    # 5. Remove weights and volumes (e.g. 600 جم, 600 جرام, 600g, 500ml, 50 مل, 1.5 لتر, 15 جم, 100 IU)
    t = re.sub(r'\b\d+(?:\.\d+)?\s*(?:جرام|جم|ملل|مل|كجم|كيلو|لتر|g|gm|ml|kg|l|oz|iu)\b', ' ', t, flags=re.I)

    # 6. Remove attached size notations like 600ج or 500مل
    t = re.sub(r'\d+(?:\.\d+)?(?:ج|جم|جرام|مل)', ' ', t)

    # 7. Remove counts, strips, tablets, pieces, capsules
    t = re.sub(r'\b\d+(?:\.\d+)?\s*(?:لصقة|لصقات|لصقه|حبة|حبات|حبه|حبوب|قطعة|قطع|قطعه|شريط|شرائط|أشرطة|أشرطه|كبسولة|كبسولات|كبسوله|قرص|أقراص|أمبولة|أمبولات|امبولة|امبولات|كيس|أكياس|منديل|مناديل|غسلة|غسلات|غسله|جرعة|جرعات|جرعه|زوج|أزواج|علبة|علب|علبه|كرتون|كراتين|عبوة|عبوات|عبوه|pcs|pc|pieces|piece|strips|strip|caps|cap|capsules|capsule|tabs|tab|tablets|tablet|count|ct|pairs|pair|wipes|wipe|sachets|sachet|bags|bag)\b', ' ', t, flags=re.I)

    # 8. Remove countdown timers and time units
    t = re.sub(r'\b\d+\s*(?:ثانية|ثواني|ثوان|دقيقة|دقائق|ساعة|ساعات|يوم|أيام|ايام|شهر|أشهر|اشهر|سنة|سنوات)\b', ' ', t)

    # 9. Remove dimensions, ratios, steps (e.g. 1:1, 10x20, خطوة 1)
    t = re.sub(r'\b\d+\s*[:x*×]\s*\d+\b', ' ', t)
    t = re.sub(r'\b(?:خطوة|خطوه|مرحلة|مرحله|step|phase)\s*\d+\b', ' ', t, flags=re.I)

    # 10. Remove ratings (e.g. 4.8 / 5, 5 نجوم)
    t = re.sub(r'\b[1-5](?:\.\d+)?\s*(?:/\s*5|نجوم|نجمة|تقييم|stars?)\b', ' ', t, flags=re.I)

    return t



def check_product_page_barcode_conflict(product_url, searched_bc, clean_bcs=None):
    """
    STRICT BARCODE CONFLICT GUARD:
    Inspects candidate product page HTML/JSON to ensure it does not explicitly declare
    a different, conflicting international retail barcode (GTIN).
    
    Returns (True, conflict_details) if a conflicting barcode is declared.
    Returns (False, 'ok') if barcode matches or no conflict is detected.
    """
    if not product_url or not searched_bc:
        return False, "no_url"
        
    valid_bcs = set(clean_bcs or [])
    valid_bcs.add(str(searched_bc).strip())
    
    try:
        req = urllib.request.Request(product_url, headers=BROWSER_HEADERS)
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=3.0) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
    except Exception:
        return False, "network_error"

    # 1. Positive confirmation: searched barcode is present in the HTML!
    for bc in valid_bcs:
        if bc and bc in html:
            return False, f"confirmed_found_{bc}"

    # 2. Check if the page explicitly declares a DIFFERENT barcode/sku
    declared_bcs = set()
    
    # Salla product-sku element: class="... product-sku">1234567890</span>
    for m in re.finditer(r'product-sku[^>]*>\s*([0-9]{8,14})\s*<', html):
        declared_bcs.add(m.group(1).strip())
        
    # JSON sku or barcode: "sku":"1234567890" or "barcode":"1234567890"
    for m in re.finditer(r'\"(?:sku|barcode|gtin|gtin13|gtin12|gtin8|gtin14)\"\s*:\s*\"([0-9]{8,14})\"', html):
        declared_bcs.add(m.group(1).strip())
        
    # Table / spec text: الباركود : 1234567890
    for m in re.finditer(r'(?:الباركود|باركود|barcode)\s*[:<][^>]*>\s*([0-9]{8,14})', html, re.I):
        declared_bcs.add(m.group(1).strip())

    # If any declared barcode is a valid GTIN and does NOT match our product's barcodes:
    conflicting = [b for b in declared_bcs if is_valid_gtin_barcode(b) and b not in valid_bcs]
    if conflicting:
        return True, f"conflicting_declared_barcode_{conflicting[0]}"

    return False, "no_conflict"


# ─────────────────────────────────────────────────────────────────────────────
# 1. ZID PLATFORM SCRAPER (Care-Outlet, Knooz, Nasaem)
# ─────────────────────────────────────────────────────────────────────────────
def search_zid(domain, site_name, barcode):
    """
    Search Zid-powered store strictly by product barcode (?q=).
    Accurately extracts product titles, active prices, discounts, and real-time stock availability.
    """
    bc = _clean_barcode(barcode)
    if not bc:
        return {'found': False, 'error': 'باركود غير صالح'}

    url = f"https://{domain}/products?q={urllib.parse.quote(bc)}"
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)

    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=10) as r:
            raw_html = r.read().decode('utf-8', errors='ignore')

        # Find all unique product links
        raw_hrefs = re.findall(r'href="(/products/[^"?#]+)', raw_html)
        if not raw_hrefs:
            return {'found': False, 'error': f'غير متوفر بالباركود في {site_name}'}

        unique_hrefs = list(dict.fromkeys(raw_hrefs))

        for href in unique_hrefs:
            # Locate snippet around this product link in raw_html
            idx = raw_html.find(href)
            snippet = raw_html[max(0, idx - 400): min(len(raw_html), idx + 4500)] if idx != -1 else raw_html

            # Title extraction
            title = ""
            # 1. From alt or title inside snippet
            t_match = re.search(r'(?:title|alt)="([^"]+)"', snippet)
            if t_match:
                candidate = t_match.group(1).strip()
                if len(candidate) > 4 and not any(k in candidate for k in ['ثانية', 'دقيقة', 'ساعة', 'يوم', 'متوفر بخيارات']):
                    title = candidate

            # 2. From h2/h3/h1 or product-title in snippet
            if not title:
                h_match = re.search(r'<(?:h[1-4]|div)[^>]*class="[^"]*(?:product-title|title|h6|h5)[^"]*"[^>]*>(?:<a[^>]*>)?([^<]+)', snippet)
                if h_match:
                    candidate = h_match.group(1).strip()
                    if len(candidate) > 4:
                        title = candidate

            # 3. Fallback from URL slug
            if not title:
                slug = href.split('/products/')[-1].split('?')[0]
                title = urllib.parse.unquote(slug).replace('-', ' ')

            title = title or f"منتج باركود {bc}"

            # Clean out-of-stock / price garbage from title if present
            title = re.sub(r'\d+(?:\.\d+)?\s*(?:ر\.س|SAR|رس).*$', '', title).strip()
            title = re.sub(r'(?:هذا المنتج )?(?:غير متوفر|أعلمني عند التوفر).*$', '', title).strip()

            unit = extract_unit_from_title(title)

            # Check out of stock in snippet
            out_of_stock = is_out_of_stock_snippet(snippet)

            # Extract old / compare-at prices from snippet
            old_prices = set()
            old_p_matches = re.findall(r'<(?:del|s|strike)\b[^>]*>(.*?)</(?:del|s|strike)>', snippet, flags=re.DOTALL|re.I)
            old_p_matches += re.findall(r'<[^>]+class="[^"]*(?:before|old-price|price-old|-old|line-through|strike|compare)[^"]*"[^>]*>(.*?)</[^>]+>', snippet, flags=re.DOTALL|re.I)
            for op in old_p_matches:
                op_clean = _strip_weights_and_units(re.sub(r'<[^>]+>', ' ', op))
                for m in re.findall(r'(\d+(?:\.\d+)?)', op_clean):
                    if float(m) > 0.5:
                        old_prices.add(round(float(m), 2))

            # Strip old prices before active price search
            snippet_active = re.sub(r'<(?:del|s|strike)\b[^>]*>.*?</(?:del|s|strike)>', ' ', snippet, flags=re.DOTALL|re.I)
            snippet_active = re.sub(r'<[^>]+class="[^"]*(?:before|old-price|price-old|-old|line-through|strike|compare)[^"]*"[^>]*>.*?</[^>]+>', ' ', snippet_active, flags=re.DOTALL|re.I)

            # Look for price STRICTLY with currency symbol in card snippet
            snippet_clean = _strip_weights_and_units(re.sub(r'<[^>]+>', ' ', snippet_active))
            p_m = re.findall(r'(\d+(?:\.\d+)?)\s*(?:ر\.س|SAR|رس|ريال)', snippet_clean)

            price_val = 0.0
            regular_price = max(old_prices) if old_prices else 0.0

            candidates = [float(x) for x in p_m if 0.5 < float(x) < 50000 and round(float(x), 2) not in old_prices]
            if candidates:
                if old_prices:
                    lower = [c for c in candidates if c < max(old_prices)]
                    price_val = round(lower[0] if lower else candidates[0], 2)
                else:
                    price_val = round(candidates[0], 2)

            # Fallback: If price not found on card, or if price is 0, fetch the product page
            if price_val == 0.0:
                try:
                    quoted_href = urllib.parse.quote(href, safe='/:?=&')
                    p_url = f"https://{domain}{quoted_href}"
                    p_req = urllib.request.Request(p_url, headers=BROWSER_HEADERS)
                    with urllib.request.urlopen(p_req, context=SSL_CTX, timeout=6) as pr:
                        p_html = pr.read().decode('utf-8', errors='ignore')

                    # 1. JSON-LD
                    for jld in re.findall(r'<script type="application/ld\+json">(.*?)</script>', p_html, re.DOTALL):
                        try:
                            jd = json.loads(jld)
                            if jd.get("@type") == "Product" and "offers" in jd:
                                off = jd["offers"]
                                p_num = float(off.get("price") or 0.0)
                                if p_num > 0.5:
                                    price_val = round(p_num, 2)
                                    if "InStock" in str(off.get("availability", "")):
                                        out_of_stock = False
                                    elif "OutOfStock" in str(off.get("availability", "")):
                                        out_of_stock = True
                                    if not title and jd.get("name"):
                                        title = jd["name"]
                                    break
                        except Exception:
                            pass

                    # 2. Meta sale_price / price
                    if price_val == 0.0:
                        m_sale = re.search(r'property="product:sale_price:amount"\s+content="([0-9\.]+)"', p_html)
                        m_price = re.search(r'property="product:price:amount"\s+content="([0-9\.]+)"', p_html)
                        if m_sale and float(m_sale.group(1)) > 0.5:
                            price_val = round(float(m_sale.group(1)), 2)
                            if m_price and float(m_price.group(1)) > price_val:
                                regular_price = round(float(m_price.group(1)), 2)
                        elif m_price and float(m_price.group(1)) > 0.5:
                            price_val = round(float(m_price.group(1)), 2)

                    # 3. Product page out-of-stock check
                    if 'section-out-of-stock-notify-me' in p_html:
                        # If section is not d-none, it's out of stock
                        if re.search(r'class="[^"]*section-out-of-stock-notify-me\b(?![^"]*d-none)', p_html):
                            out_of_stock = True

                    avail_meta = re.search(r'property="product:availability"\s+content="([^"]+)"', p_html)
                    if avail_meta:
                        if 'out of stock' in avail_meta.group(1).lower():
                            out_of_stock = True
                        elif 'in stock' in avail_meta.group(1).lower():
                            out_of_stock = False

                except Exception:
                    pass

            if price_val > 0.5:
                return {
                    'found': True,
                    'title': title,
                    'price': price_val,
                    'regular_price': regular_price,
                    'has_discount': regular_price > price_val,
                    'unit': unit,
                    'in_stock': not out_of_stock,
                    'url': f"https://{domain}{urllib.parse.quote(href, safe='/:?=&')}",
                    'site_name': site_name,
                    'domain': domain
                }

        return {'found': False, 'error': f'غير متوفر بسعر صالح في {site_name}'}

    except Exception as e:
        return {'found': False, 'error': f'خطأ اتصال ({site_name}): {e}'}


# ─────────────────────────────────────────────────────────────────────────────
# 2. SHOPIFY PLATFORM SCRAPER (Sidalih, United Pharmacy, Wahaj)
# ─────────────────────────────────────────────────────────────────────────────
def search_shopify(domain, site_name, barcode):
    """
    Search Shopify stores strictly by product barcode (/search?q={bc}&type=product).
    """
    bc = _clean_barcode(barcode)
    if not bc:
        return {'found': False, 'error': 'باركود غير صالح'}

    url = f"https://{domain}/search?q={urllib.parse.quote(bc)}&type=product"
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)

    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=12) as r:
            raw_html = r.read().decode('utf-8', errors='ignore')

        if any(msg in raw_html for msg in ['0 نتيجة', '0 نتائج', '0 results', 'لم نتمكن من العثور']):
            return {'found': False, 'error': f'غير متوفر بالباركود في {site_name}'}

        prod_matches = re.findall(r'href="(/products/[^"?]+)(?:\?[^"]*)?"', raw_html)
        if not prod_matches:
            return {'found': False, 'error': f'غير متوفر بالباركود في {site_name}'}

        prod_urls = list(dict.fromkeys(prod_matches))
        first_href = prod_urls[0]
        idx = raw_html.find(first_href)
        snippet = raw_html[max(0, idx - 200):idx + 3500] if idx != -1 else raw_html

        title_m = re.search(r'title="([^"]+)"', snippet) or re.search(r'alt="([^"]+)"', snippet)
        title = ""
        if title_m and len(title_m.group(1).strip()) > 3:
            title = title_m.group(1).strip()
        else:
            slug = first_href.split('/products/')[-1]
            title = urllib.parse.unquote(slug).replace('-', ' ')

        unit = extract_unit_from_title(title)

        price_val = 0.0
        regular_price = 0.0

        # Extract old compare-at prices
        old_prices = set()
        compare_tags = re.findall(r'class="[^"]*(?:compare|price--compare|price-item--regular)[^"]*"[^>]*>(.*?)<', snippet, re.DOTALL)
        compare_tags += re.findall(r'<(?:del|s|strike)\b[^>]*>(.*?)</(?:del|s|strike)>', snippet, flags=re.DOTALL|re.I)
        for ct in compare_tags:
            for m in re.findall(r'(\d+(?:\.\d+)?)', _strip_weights_and_units(ct)):
                if float(m) > 0.5:
                    old_prices.add(round(float(m), 2))
        if old_prices:
            regular_price = max(old_prices)

        # 1. Check sale price item first: .price-item--sale
        p_sale_item = re.search(r'class="[^"]*price-item--sale[^"]*"[^>]*>.*?([0-9\.]+)', snippet, re.DOTALL)
        if p_sale_item:
            price_val = round(float(p_sale_item.group(1)), 2)

        # 2. Check standard shopify price patterns
        if price_val == 0.0:
            p_sale = re.search(r'class="[^"]*hdt-price[^"]*"[^>]*>.*?<span[^>]*class="[^"]*hdt-money[^"]*"[^>]*>([0-9\.]+)', snippet, re.DOTALL)
            if p_sale:
                price_val = round(float(p_sale.group(1)), 2)

        if price_val == 0.0:
            money_tags = re.findall(r'class="[^"]*money[^"]*"[^>]*>([0-9\.]+)', snippet)
            valid_money = [float(m) for m in money_tags if float(m) > 0.5 and round(float(m), 2) not in old_prices]
            if valid_money:
                price_val = round(valid_money[-1], 2)

        if price_val == 0.0:
            snippet_clean = _strip_weights_and_units(snippet)
            all_prices = re.findall(r'(\d+(?:\.\d+)?)\s*(?:ر\.س|SAR|رس)', snippet_clean)
            if all_prices:
                valid_p = [float(p) for p in all_prices if float(p) > 0.5 and round(float(p), 2) not in old_prices]
                if valid_p:
                    if old_prices:
                        lower = [p for p in valid_p if p < max(old_prices)]
                        price_val = round(lower[0] if lower else valid_p[0], 2)
                    else:
                        price_val = round(valid_p[-1], 2)

        if price_val > 0.5:
            full_url = f"https://{domain}{first_href}" if first_href.startswith('/') else first_href
            out_of_stock = is_out_of_stock_snippet(snippet) or any(k in snippet.lower() for k in ['sold-out', 'sold_out', 'badge--sold-out', 'out-of-stock', 'out_of_stock', 'price--sold-out'])
            title = re.sub(r'\d+(?:\.\d+)?\s*(?:ر\.س|SAR|رس).*$', '', title).strip()
            title = re.sub(r'(?:هذا المنتج )?(?:غير متوفر|أعلمني عند التوفر).*$', '', title).strip()
            return {
                'found': True,
                'title': title,
                'price': price_val,
                'regular_price': regular_price,
                'has_discount': regular_price > price_val,
                'unit': unit,
                'in_stock': not out_of_stock,
                'url': full_url,
                'site_name': site_name,
                'domain': domain
            }

        return {'found': False, 'error': f'غير متوفر بسعر صالح في {site_name}'}

    except Exception as e:
        return {'found': False, 'error': f'خطأ اتصال ({site_name}): {e}'}


# ─────────────────────────────────────────────────────────────────────────────
# 3. MAGENTO 2 SCRAPER (Nazih)
# ─────────────────────────────────────────────────────────────────────────────
def search_magento(domain, site_name, barcode):
    """
    Search Nazih strictly by barcode via Magento 2 catalogsearch.
    """
    bc = _clean_barcode(barcode)
    if not bc:
        return {'found': False, 'error': 'باركود غير صالح'}

    url = f"https://{domain}/catalogsearch/result/?q={urllib.parse.quote(bc)}"
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)

    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=12) as r:
            raw_html = r.read().decode('utf-8', errors='ignore')

        blocks = re.findall(r'<div[^>]*itemtype="https://schema\.org/Product"[^>]*>(.*?)</div>\s*</div>', raw_html, re.DOTALL)
        if not blocks:
            return {'found': False, 'error': f'غير متوفر بالباركود في {site_name}'}

        for b in blocks:
            name_m = re.search(r'itemprop="name"[^>]*>(.*?)<', b)
            price_m = re.search(r'itemprop="price"\s+content="([^"]+)"', b)
            avail_m = re.search(r'itemprop="availability"\s+href="([^"]+)"', b)
            link_m = re.search(r'href="([^"]+)"', b)

            if not price_m:
                continue

            try:
                p_val = round(float(price_m.group(1)), 2)
            except ValueError:
                continue

            if p_val > 0:
                raw_name = name_m.group(1).strip() if name_m else ''
                title = html.unescape(raw_name) or f"منتج باركود {bc}"
                unit = extract_unit_from_title(title)
                in_stock = 'InStock' in (avail_m.group(1) if avail_m else '')
                link = link_m.group(1) if link_m else url

                return {
                    'found': True,
                    'title': title,
                    'price': p_val,
                    'unit': unit,
                    'in_stock': in_stock,
                    'url': link,
                    'site_name': site_name,
                    'domain': domain
                }

        return {'found': False, 'error': f'غير متوفر بسعر صالح في {site_name}'}

    except Exception as e:
        return {'found': False, 'error': f'خطأ اتصال ({site_name}): {e}'}


# ─────────────────────────────────────────────────────────────────────────────
# 4. OPENCART SCRAPER (Spama)
# ─────────────────────────────────────────────────────────────────────────────
def search_opencart(domain, site_name, barcode):
    """
    Search OpenCart store (Spama) strictly by barcode.
    """
    bc = _clean_barcode(barcode)
    if not bc:
        return {'found': False, 'error': 'باركود غير صالح'}

    url = f"https://{domain}/index.php?route=product/search&search={urllib.parse.quote(bc)}"
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)

    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=12) as r:
            raw_html = r.read().decode('utf-8', errors='ignore')

        if "لا توجد نتائج تطابق معايير البحث" in raw_html or "There is no product that matches" in raw_html:
            return {'found': False, 'error': f'غير متوفر بالباركود في {site_name}'}

        thumbs = re.findall(r'<div[^>]*class="[^"]*product-thumb[^"]*"[^>]*>(.*?)</div>\s*</div>', raw_html, re.DOTALL)
        if not thumbs:
            link_m = re.search(r'href="(https://[^"]+/index\.php\?route=product/product[^"]+)"', raw_html)
            if not link_m:
                return {'found': False, 'error': f'غير متوفر بالباركود في {site_name}'}

        for t in (thumbs or [raw_html]):
            link_m = re.search(r'href="([^"]+route=product/product[^"]+)"', t)
            
            p_val = 0.0
            reg_val = 0.0
            p_old_m = re.search(r'class="[^"]*price-old[^"]*"[^>]*>([^<]+)', t)
            if p_old_m:
                old_nums = re.findall(r'(\d+(?:\.\d+)?)', _strip_weights_and_units(p_old_m.group(1)))
                if old_nums:
                    reg_val = round(float(old_nums[0]), 2)

            p_new_m = re.search(r'class="[^"]*price-new[^"]*"[^>]*>([^<]+)', t)
            if p_new_m:
                new_nums = re.findall(r'(\d+(?:\.\d+)?)', _strip_weights_and_units(p_new_m.group(1)))
                if new_nums and float(new_nums[0]) > 0.5:
                    p_val = round(float(new_nums[0]), 2)

            if p_val == 0.0:
                t_no_old = re.sub(r'<[^>]+class="[^"]*price-old[^"]*"[^>]*>.*?</[^>]+>', ' ', t)
                t_clean = _strip_weights_and_units(t_no_old)
                price_m = re.findall(r'(\d+(?:\.\d+)?)\s*(?:ر\.س|SAR|رس)', t_clean)
                if price_m:
                    p_val = round(float(price_m[-1]), 2)

            name_m = re.search(r'<h4><a[^>]*>(.*?)</a></h4>', t)

            if link_m and p_val > 0.5:
                title = name_m.group(1).strip() if name_m else f"منتج باركود {bc}"
                title = html.unescape(title)
                title = re.sub(r'\d+(?:\.\d+)?\s*(?:ر\.س|SAR|رس).*$', '', title).strip()
                title = re.sub(r'(?:هذا المنتج )?(?:غير متوفر|أعلمني عند التوفر).*$', '', title).strip()
                unit = extract_unit_from_title(title)
                out_of_stock = is_out_of_stock_snippet(t)
                return {
                    'found': True,
                    'title': title,
                    'price': p_val,
                    'regular_price': reg_val,
                    'has_discount': reg_val > p_val,
                    'unit': unit,
                    'in_stock': not out_of_stock,
                    'url': link_m.group(1),
                    'site_name': site_name,
                    'domain': domain
                }

        return {'found': False, 'error': f'غير متوفر بالباركود في {site_name}'}

    except Exception as e:
        return {'found': False, 'error': f'خطأ اتصال ({site_name}): {e}'}


# ─────────────────────────────────────────────────────────────────────────────
# 5. WOOCOMMERCE & CUSTOM SCRAPERS
# ─────────────────────────────────────────────────────────────────────────────
def search_woocommerce(domain, site_name, barcode):
    """
    Search WooCommerce / WordPress stores (Beauty Cloud, etc.)
    """
    bc = _clean_barcode(barcode)
    if not bc:
        return {'found': False, 'error': 'باركود غير صالح'}

    url = f"https://{domain}/?s={urllib.parse.quote(bc)}&post_type=product"
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)

    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=12) as r:
            raw_html = r.read().decode('utf-8', errors='ignore')

        if any(msg in raw_html for msg in ['لم يتم العثور على أي نتائج', 'No products were found', 'not-found']):
            return {'found': False, 'error': f'غير متوفر بالباركود في {site_name}'}

        prod_links = re.findall(r'href="([^"]+/product/[^"]+)"', raw_html)
        if not prod_links:
            return {'found': False, 'error': f'غير متوفر بالباركود في {site_name}'}

        first_url = prod_links[0]
        # Strip <del>...</del> tags to remove regular crossed-out price
        old_prices = re.findall(r'<del\b[^>]*>(.*?)</del>', raw_html, flags=re.DOTALL|re.I)
        reg_val = 0.0
        if old_prices:
            for op in old_prices:
                nums = re.findall(r'(\d+(?:\.\d+)?)', _strip_weights_and_units(op))
                if nums:
                    reg_val = max(reg_val, round(float(nums[0]), 2))

        html_no_old = re.sub(r'<del\b[^>]*>.*?</del>', ' ', raw_html, flags=re.DOTALL|re.I)
        html_clean = _strip_weights_and_units(html_no_old)
        prices = re.findall(r'(\d+(?:\.\d+)?)\s*(?:ر\.س|SAR|رس)', html_clean)
        p_val = float(prices[0]) if prices else 0.0

        slug = first_url.rstrip('/').split('/')[-1]
        title = urllib.parse.unquote(slug).replace('-', ' ') or f"منتج باركود {bc}"
        title = re.sub(r'\d+(?:\.\d+)?\s*(?:ر\.س|SAR|رس).*$', '', title).strip()
        title = re.sub(r'(?:هذا المنتج )?(?:غير متوفر|أعلمني عند التوفر).*$', '', title).strip()
        unit = extract_unit_from_title(title)
        out_of_stock = is_out_of_stock_snippet(raw_html)

        if p_val > 0.5:
            return {
                'found': True,
                'title': title,
                'price': round(p_val, 2),
                'regular_price': reg_val,
                'has_discount': reg_val > round(p_val, 2),
                'unit': unit,
                'in_stock': not out_of_stock,
                'url': first_url,
                'site_name': site_name,
                'domain': domain
            }

        return {'found': False, 'error': f'غير متوفر بسعر صالح في {site_name}'}

    except Exception as e:
        return {'found': False, 'error': f'خطأ اتصال ({site_name}): {e}'}


def search_custom_http(domain, site_name, barcode):
    """
    Generic fallback for simple catalog stores (Madi, Makhazen).
    """
    bc = _clean_barcode(barcode)
    if not bc:
        return {'found': False, 'error': 'باركود غير صالح'}

    for search_pattern in [f"https://{domain}/?s={bc}", f"https://{domain}/search?q={bc}"]:
        try:
            req = urllib.request.Request(search_pattern, headers=BROWSER_HEADERS)
            with urllib.request.urlopen(req, context=SSL_CTX, timeout=10) as r:
                raw_html = r.read().decode('utf-8', errors='ignore')

            if any(msg in raw_html for msg in ['0 نتائج', 'لم نتمكن', 'not found', 'No results']):
                continue

            links = re.findall(r'href="([^"]+)"', raw_html)
            matching = [l for l in links if any(k in l for k in ['/product/', '/item/']) and bc in l]
            if matching:
                html_clean = _strip_weights_and_units(raw_html)
                prices = re.findall(r'(\d+(?:\.\d+)?)\s*(?:ر\.س|SAR|رس)', html_clean)
                p_val = float(prices[0]) if prices else 0.0
                if p_val > 0:
                    title = f"منتج باركود {bc}"
                    unit = extract_unit_from_title(title)
                    return {
                        'found': True,
                        'title': title,
                        'price': round(p_val, 2),
                        'unit': unit,
                        'in_stock': True,
                        'url': matching[0],
                        'site_name': site_name,
                        'domain': domain
                    }
        except Exception:
            pass

    return {'found': False, 'error': f'غير متوفر بالباركود في {site_name}'}


# ─────────────────────────────────────────────────────────────────────────────
# 6. BROWSER WORKER (Salla & Nahdi & JS Heavy Platforms)
# ─────────────────────────────────────────────────────────────────────────────
def _create_headless_edge_driver():
    """Instantiate a fast headless Edge WebDriver with strict page load and script timeouts."""
    from selenium import webdriver
    from selenium.webdriver.edge.options import Options

    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--blink-settings=imagesEnabled=false')
    options.add_argument('--log-level=3')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    driver = webdriver.Edge(options=options)
    driver.set_page_load_timeout(6)   # Strict 6s timeout - prevents ANY store from hanging the app
    driver.set_script_timeout(4)     # Strict 4s script timeout
    return driver


def extract_active_price_from_salla_element(root_elem):
    """
    Extracts the TRUE active (current/discounted) price from a Salla container element.
    Strictly isolates and ignores any old/before/crossed-out regular prices.
    Returns (active_price, regular_price).
    """
    from selenium.webdriver.common.by import By
    if not root_elem:
        return 0.0, 0.0

    # 1. Collect all declared OLD / BEFORE / CROSSED-OUT prices (Case-insensitive)
    old_prices = set()
    try:
        old_nodes = root_elem.find_elements(
            By.XPATH,
            './/*[contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "before") or '
            'contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "old-price") or '
            'contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "price-old") or '
            'contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "-old") or '
            'contains(concat(" ", normalize-space(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")), " "), " old ") or '
            'contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "line-through") or '
            'contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "strike") or '
            'self::del or self::s]'
        )
        def _is_hidden(el):
            curr = el
            for _ in range(4):
                if not curr:
                    break
                try:
                    c = (curr.get_attribute("class") or "").lower()
                    style = (curr.get_attribute("style") or "").lower()
                    if "hidden" in c.split() or "display:none" in style.replace(" ", "") or "display: none" in style:
                        return True
                    curr = curr.find_element(By.XPATH, "..")
                except Exception:
                    break
            return False

        for on in old_nodes:
            if _is_hidden(on):
                continue
            txt = _strip_weights_and_units(on.text)
            for m in re.findall(r'(\d+(?:\.\d+)?)', txt):
                if float(m) > 0.5:
                    old_prices.add(round(float(m), 2))
    except Exception:
        pass

    regular_price = max(old_prices) if old_prices else 0.0

    # 2. Look for dedicated active / discounted price elements FIRST (Lableb, Salla, etc.)
    try:
        active_nodes = root_elem.find_elements(
            By.XPATH,
            './/*[contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "priceafterdiscount") or '
            'contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "sale-price") or '
            'contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "special-price") or '
            'contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "current-price") or '
            'contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "final-price") or '
            'self::salla-price]'
        )
        for an in active_nodes:
            txt = _strip_weights_and_units(an.text.strip())
            nums = re.findall(r'(\d+(?:\.\d+)?)', txt)
            if nums:
                val = round(float(nums[0]), 2)
                if 0.5 < val < 50000 and val not in old_prices:
                    return val, regular_price
    except Exception:
        pass

    # 3. Look for leaf price elements inside root_elem (avoiding parent wrappers with headings/paragraphs)
    try:
        p_nodes = root_elem.find_elements(
            By.XPATH,
            './/*[(contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "price") or '
            'contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "total") or '
            'contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "amount")) and '
            'not(contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "before")) and '
            'not(contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "old")) and '
            'not(contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "line-through")) and '
            'not(contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "tabby")) and '
            'not(contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "tamara"))]'
        )
        for pn in p_nodes:
            # Skip if this element contains child heading or paragraph tags (it's a product container!)
            try:
                if pn.find_elements(By.XPATH, './/*[self::p or self::h1 or self::h2 or self::h3 or self::h4 or self::h5 or self::h6]'):
                    continue
            except Exception:
                pass

            # Skip if this element contains child price elements (it's a wrapper!)
            try:
                if pn.find_elements(By.XPATH, './/*[contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "price")]'):
                    continue
            except Exception:
                pass

            txt = pn.text.strip()
            if not txt or len(txt) > 40:
                continue

            # Remove any embedded old price children text
            try:
                for bad in pn.find_elements(By.XPATH, './/*[contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "before") or contains(translate(@class, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "old") or contains(@class, "line-through") or self::del or self::s]'):
                    b_txt = bad.text.strip()
                    if b_txt:
                        txt = txt.replace(b_txt, ' ')
            except Exception:
                pass

            txt_clean = _strip_weights_and_units(txt)
            curr_m = re.findall(r'(\d+(?:\.\d+)?)\s*(?:ر\.س|SAR|رس|ريال)', txt_clean)
            if curr_m:
                val = round(float(curr_m[0]), 2)
                if 0.5 < val < 50000 and val not in old_prices:
                    return val, regular_price

            nums = re.findall(r'(\d+(?:\.\d+)?)', txt_clean)
            for n in nums:
                val = round(float(n), 2)
                if 0.5 < val < 50000 and val not in old_prices:
                    return val, regular_price
    except Exception:
        pass

    # 4. Fallback: Parse root_elem.text STRICTLY requiring currency symbol
    try:
        gp_txt = _strip_weights_and_units(root_elem.text)
        all_nums = re.findall(r'(\d+(?:\.\d+)?)\s*(?:ر\.س|SAR|رس|ريال)', gp_txt)
        candidates = []
        for n in all_nums:
            val = round(float(n), 2)
            if 0.5 < val < 50000 and val not in old_prices:
                candidates.append(val)
        if candidates:
            # If multiple numbers exist, prefer ones with decimal fraction or smaller than regular price
            if old_prices:
                lower = [c for c in candidates if c < max(old_prices)]
                if lower:
                    decimals = [c for c in lower if not c.is_integer()]
                    return decimals[0] if decimals else lower[0], regular_price
            decimals = [c for c in candidates if not c.is_integer()]
            return decimals[0] if decimals else candidates[-1], regular_price
    except Exception:
        pass

    return 0.0, regular_price


def search_browser_store_with_driver(driver, store_info, barcode, clean_bcs=None):
    """
    Search a browser-rendered store (Salla, Nahdi) using an active Edge driver.
    Strictly searches by barcode only.
    Protected against weight/unit extraction confusion and page load timeouts.
    """
    from selenium.webdriver.common.by import By

    bc = _clean_barcode(barcode)
    if not bc:
        return {'found': False, 'error': 'باركود غير صالح للبحث الخارجي'}

    key = store_info['key']
    domain = store_info['domain']
    site_name = store_info['name']

    # 1. Nahdi Online
    if key == 'nahdi':
        url = f"https://www.nahdionline.com/ar-sa/search?query={urllib.parse.quote(bc)}"
        try:
            try:
                driver.get(url)
            except Exception:
                try:
                    driver.execute_script("window.stop();")
                except Exception:
                    pass

            t_poll = time.time()
            while time.time() - t_poll < 2.5:
                try:
                    btn = driver.find_element(By.ID, 'onetrust-accept-btn-handler')
                    btn.click()
                except Exception:
                    pass
                try:
                    a_tags = driver.find_elements(By.TAG_NAME, "a")
                    if any("/p-" in (a.get_attribute("href") or "") or "/product/" in (a.get_attribute("href") or "") for a in a_tags):
                        break
                    body_txt = driver.find_element(By.TAG_NAME, "body").text
                    if "لم نتمكن من العثور" in body_txt or "لا توجد نتائج" in body_txt or "0 نتيجة" in body_txt:
                        break
                except Exception:
                    pass
                time.sleep(0.15)

            body_txt = driver.find_element(By.TAG_NAME, "body").text
            if "لم نتمكن من العثور" in body_txt or "لا توجد نتائج" in body_txt:
                return {'found': False, 'error': f'غير متوفر بالباركود في {site_name}'}

            links = driver.find_elements(By.TAG_NAME, "a")
            for a in links:
                href = a.get_attribute("href") or ""
                if "/p-" in href or "/product/" in href:
                    txt = a.text.strip().replace("\n", " ")
                    txt_clean = _strip_weights_and_units(txt)
                    prices = re.findall(r'(\d+(?:\.\d+)?)\s*(?:ر\.س|SAR|رس|ريال)', txt_clean)
                    if prices:
                        p_val = round(float(prices[-1]), 2)
                        title_clean = re.sub(r'[\d\.]+\s*(?:ر\.س|SAR|رس)?', '', txt).strip()
                        title = title_clean or f"منتج باركود {bc}"
                        title = re.sub(r'\d+(?:\.\d+)?\s*(?:ر\.س|SAR|رس).*$', '', title).strip()
                        title = re.sub(r'(?:هذا المنتج )?(?:غير متوفر|أعلمني عند التوفر).*$', '', title).strip()
                        unit = extract_unit_from_title(title)
                        out_of_stock = is_out_of_stock_snippet(txt)
                        return {
                            'found': True,
                            'title': title,
                            'price': p_val,
                            'unit': unit,
                            'in_stock': not out_of_stock,
                            'url': href,
                            'site_name': site_name,
                            'domain': domain
                        }

            return {'found': False, 'error': f'غير متوفر بالباركود في {site_name}'}
        except Exception as e:
            return {'found': False, 'error': f'خطأ اتصال ({site_name}): {e}'}

    # 3. Salla Stores (daralamirat, asrar, ibrand, afkar, banu, careksa, etc.)
    url = f"https://{domain}/search?q={urllib.parse.quote(bc)}"
    try:
        try:
            driver.get(url)
        except Exception:
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass

        t_poll = time.time()
        while time.time() - t_poll < 3.5:
            try:
                cards = driver.find_elements(By.CSS_SELECTOR, "salla-product-card, .product-card, .s-product-card, [class*='product-entry']")
                if cards:
                    break
                a_tags = driver.find_elements(By.TAG_NAME, "a")
                if any(re.search(r'/p\d+', a.get_attribute("href") or "") and domain in (a.get_attribute("href") or "") and "/page" not in (a.get_attribute("href") or "") for a in a_tags):
                    break

                # Quick short-circuit if page is definitely empty after 1.5s
                if time.time() - t_poll >= 1.5:
                    body_txt = driver.find_element(By.TAG_NAME, "body").text
                    if any(msg in body_txt for msg in ["لم نتمكن من العثور", "لا توجد نتائج", "لا يوجد نتائج", "0 نتيجة", "عذراً، لم نجد"]):
                        break
            except Exception:
                pass
            time.sleep(0.15)

        links = driver.find_elements(By.TAG_NAME, "a")
        for a in links:
            href = a.get_attribute("href") or ""
            # Must match product link pattern /p followed by digits and exclude /pages/ and /page-
            if re.search(r'/p\d+', href) and domain in href and "/pages/" not in href and "/page-" not in href:
                # 1. Reject Lableb fallback recommendation carousels (when query returns 0 results)
                if 'lableb_query=' in href:
                    q_m = re.search(r'lableb_query=([^&]*)', href)
                    if q_m:
                        q_val = urllib.parse.unquote(q_m.group(1)).strip()
                        if not q_val or (bc not in q_val and (clean_bcs and q_val not in clean_bcs)):
                            continue  # Skip fallback recommendation links!

                price_val = 0.0
                regular_price = 0.0

                title = ""
                # Try finding clean title element inside a or its card first
                try:
                    for t_elem in a.find_elements(By.XPATH, './/*[self::h1 or self::h2 or self::h3 or self::h4 or self::p or contains(@class, "title") or contains(@class, "name")]'):
                        t_txt = t_elem.text.strip()
                        if len(t_txt) > 3 and not any(k in t_txt for k in ['%', 'خصم', 'SAR', 'ر.س', 'إضافة للسلة', 'Add to cart']):
                            title = t_txt
                            break
                except Exception:
                    pass

                if not title:
                    try:
                        t_node = a.find_element(By.XPATH, 'ancestor::*[contains(@class, "product-entry") or contains(@class, "product-card") or contains(@class, "s-product-card") or self::salla-product-card][1]//*[self::h1 or self::h2 or self::h3 or self::h4 or contains(@class, "title") or contains(@class, "name")]')
                        if t_node and len(t_node.text.strip()) > 3:
                            title = t_node.text.strip()
                    except Exception:
                        pass

                if not title:
                    txt = a.text.strip().replace("\n", " ")
                    txt_clean = re.sub(r'\d+%\s*خصم', '', txt).strip()
                    title = txt_clean if len(txt_clean) > 4 else ""

                if not title or len(title) <= 4:
                    parts = [p for p in href.split('?')[0].split('/') if p]
                    slug = parts[-1]
                    if re.match(r'^p\d+$', slug, re.I) and len(parts) >= 2:
                        slug = parts[-2]
                    title = urllib.parse.unquote(slug).replace('-', ' ')

                title = title or f"منتج باركود {bc}"
                unit = extract_unit_from_title(title)

                # 2. Extract TRUE active price from grandparent / card container
                try:
                    gp = a.find_element(By.XPATH, "../..")
                except Exception:
                    gp = a

                card_elem = None
                try:
                    card_elem = a.find_element(
                        By.XPATH,
                        'ancestor::*[contains(@class, "product-entry") or contains(@class, "product-card") or contains(@class, "s-product-card") or self::salla-product-card or contains(@class, "item")][1]'
                    )
                except Exception:
                    pass

                price_val, regular_price = extract_active_price_from_salla_element(gp)

                # Fallback to ancestor card if gp had 0 price
                if price_val == 0.0 and card_elem:
                    try:
                        price_val, reg2 = extract_active_price_from_salla_element(card_elem)
                        if reg2 > 0:
                            regular_price = reg2
                    except Exception:
                        pass

                # Out of stock check on card text & buttons
                full_card_text = ""
                try:
                    full_card_text = (card_elem.text if card_elem else gp.text) or ""
                except Exception:
                    pass

                out_of_stock = is_out_of_stock_snippet(full_card_text)
                if not out_of_stock and card_elem:
                    try:
                        bad_btns = card_elem.find_elements(
                            By.CSS_SELECTOR,
                            '.out-of-stock, [disabled], .btn-out-of-stock, .badge-out-of-stock, salla-button[disabled], .s-product-card-out-of-stock'
                        )
                        if bad_btns:
                            out_of_stock = True
                    except Exception:
                        pass

                if price_val > 0.5:
                    # 3. Strict Barcode Conflict Verification on the candidate product page
                    has_conflict, c_reason = check_product_page_barcode_conflict(href, bc, clean_bcs)
                    if has_conflict:
                        continue  # Skip product if page declares a different conflicting GTIN!

                    title = re.sub(r'\d+(?:\.\d+)?\s*(?:ر\.س|SAR|رس).*$', '', title).strip()
                    title = re.sub(r'(?:هذا المنتج )?(?:غير متوفر|أعلمني عند التوفر).*$', '', title).strip()

                    return {
                        'found': True,
                        'title': title,
                        'price': price_val,
                        'regular_price': regular_price,
                        'has_discount': regular_price > price_val,
                        'unit': unit,
                        'in_stock': not out_of_stock,
                        'url': href,
                        'site_name': site_name,
                        'domain': domain
                    }

        return {'found': False, 'error': f'غير متوفر بالباركود في {site_name}'}
    except Exception as e:
        return {'found': False, 'error': f'خطأ اتصال ({site_name}): {e}'}


# ─────────────────────────────────────────────────────────────────────────────
# 7. HIGH-PERFORMANCE MULTI-STORE BATCH ENGINE
# ─────────────────────────────────────────────────────────────────────────────
def _search_store_single_barcode(store_info, barcode, driver=None, clean_bcs=None):
    """Route search strictly by barcode to the specialized scraper."""
    platform = store_info['platform']
    domain = store_info['domain']
    name = store_info['name']

    res = {'found': False, 'error': f'غير متوفر بالباركود في {name}'}
    if platform == 'zid':
        res = search_zid(domain, name, barcode)
    elif platform == 'shopify':
        res = search_shopify(domain, name, barcode)
    elif platform == 'magento':
        res = search_magento(domain, name, barcode)
    elif platform == 'opencart':
        res = search_opencart(domain, name, barcode)
    elif platform == 'woocommerce':
        res = search_woocommerce(domain, name, barcode)
    elif platform == 'custom':
        res = search_custom_http(domain, name, barcode)
    elif platform in ['salla', 'nahdi', 'browser']:
        if driver:
            return search_browser_store_with_driver(driver, store_info, barcode, clean_bcs=clean_bcs)
        else:
            d = _create_headless_edge_driver()
            try:
                return search_browser_store_with_driver(d, store_info, barcode, clean_bcs=clean_bcs)
            finally:
                d.quit()
    else:
        res = search_custom_http(domain, name, barcode)

    # Cross-verify HTTP store candidate URL for barcode conflict
    if res.get('found') and res.get('url'):
        has_conflict, c_reason = check_product_page_barcode_conflict(res['url'], barcode, clean_bcs)
        if has_conflict:
            return {'found': False, 'error': f'غير متوفر بالباركود في {name}'}

    return res


def search_all_competitors(barcodes, on_store_result=None, progress_callback=None):
    """
    Search all 34 competitor stores simultaneously strictly by product barcode.
    - True parallel dispatch: HTTP stores (11) and Browser workers (6) run at the exact same instant!
    - Streaming real-time callbacks: As soon as ANY store finishes, on_store_result(key, result) fires.
    - Rule: STRICTLY search by barcode only. No name/description fallback.
    """
    if isinstance(barcodes, (str, int)):
        bc_list = [str(barcodes)]
    elif isinstance(barcodes, (list, tuple, set)):
        bc_list = [str(b) for b in barcodes if b]
    else:
        bc_list = []

    clean_bcs = []
    for b in bc_list:
        cb = _clean_barcode(b)
        if cb and cb not in clean_bcs:
            clean_bcs.append(cb)
            # Automatic UPC-A <-> EAN-13 normalization (12-digit <-> 13-digit with leading 0)
            if len(cb) == 12 and cb.isdigit():
                ean13 = '0' + cb
                if ean13 not in clean_bcs:
                    clean_bcs.append(ean13)
            elif len(cb) == 13 and cb.startswith('0') and cb.isdigit():
                upc12 = cb[1:]
                if upc12 not in clean_bcs:
                    clean_bcs.append(upc12)

    if not clean_bcs:
        res_empty = {}
        for s in STORES_REGISTRY:
            res_empty[s['key']] = {
                'found': False,
                'error': 'لا يوجد باركود مسجل للصنف للبحث به',
                'site_name': s['name'],
                'domain': s['domain'],
                'color': s.get('color', '#64748B'),
                'matched_by': 'بدون باركود'
            }
            if on_store_result:
                on_store_result(s['key'], res_empty[s['key']])
        return res_empty

    results = {}

    import threading
    report_lock = threading.Lock()
    reported_keys = set()

    def _safe_on_store(k, r):
        with report_lock:
            results[k] = r
            if k in reported_keys:
                return
            reported_keys.add(k)
        if on_store_result:
            on_store_result(k, r)

    http_stores = [s for s in STORES_REGISTRY if s['platform'] in ['zid', 'shopify', 'magento', 'opencart', 'woocommerce', 'custom']]
    browser_stores = [s for s in STORES_REGISTRY if s['platform'] in ['salla', 'nahdi', 'browser']]
    # Sort browser stores so heavy stores (nahdi) execute at the end of chunks without delaying others
    browser_stores.sort(key=lambda s: 1 if s['key'] == 'nahdi' else 0)

    # 1. Worker for individual HTTP stores
    def _run_single_http(store):
        key = store['key']
        name = store['name']
        if progress_callback:
            progress_callback(name, "جاري فحص الباركود...")

        res = {'found': False, 'error': f'غير متوفر بالباركود في {name}'}
        for bc in clean_bcs:
            res = _search_store_single_barcode(store, bc, clean_bcs=clean_bcs)
            if res.get('found') and float(res.get('price') or 0.0) > 0:
                res['matched_by'] = f"باركود: {bc}"
                break

        res['site_name'] = name
        res['domain'] = store['domain']
        res['color'] = store.get('color', '#64748B')
        _safe_on_store(key, res)
        if progress_callback:
            progress_callback(name, "اكتمل")
        return key, res

    # 2. Worker for browser store chunks (6 concurrent Edge instances)
    num_browser_workers = 6
    chunks = [browser_stores[i::num_browser_workers] for i in range(num_browser_workers)]

    def _run_browser_chunk(stores_chunk):
        chunk_res = []
        if not stores_chunk:
            return chunk_res

        driver = None
        try:
            driver = _create_headless_edge_driver()
            for s in stores_chunk:
                key = s['key']
                name = s['name']
                if progress_callback:
                    progress_callback(name, "جاري فحص الباركود...")

                s_res = {'found': False, 'error': f'غير متوفر بالباركود في {name}'}
                for bc in clean_bcs:
                    s_res = search_browser_store_with_driver(driver, s, bc, clean_bcs=clean_bcs)
                    if s_res.get('found') and float(s_res.get('price') or 0.0) > 0:
                        s_res['matched_by'] = f"باركود: {bc}"
                        break

                s_res['site_name'] = name
                s_res['domain'] = s['domain']
                s_res['color'] = s.get('color', '#64748B')
                _safe_on_store(key, s_res)
                if progress_callback:
                    progress_callback(name, "اكتمل")
                chunk_res.append((key, s_res))
        except Exception:
            for s in stores_chunk:
                err_res = {
                    'found': False,
                    'error': f'خطأ تشغيل المتصفح لـ {s["name"]}',
                    'site_name': s['name'],
                    'domain': s['domain'],
                    'color': s.get('color', '#64748B')
                }
                _safe_on_store(s['key'], err_res)
                chunk_res.append((s['key'], err_res))
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

        return chunk_res

    # 3. Launch HTTP and Browser workers simultaneously in a unified high-throughput pool!
    total_workers = len(http_stores) + num_browser_workers
    executor = ThreadPoolExecutor(max_workers=total_workers)
    futures = []
    try:
        # Submit all HTTP stores concurrently
        for s in http_stores:
            futures.append(('http', executor.submit(_run_single_http, s)))
        # Submit all Browser chunks concurrently at the EXACT same moment
        for c in chunks:
            futures.append(('browser', executor.submit(_run_browser_chunk, c)))

        # Wait up to 55 seconds for ALL stores to respond safely (returns as soon as finished)
        raw_futures = [f for _, f in futures]
        done, not_done = concurrent.futures.wait(raw_futures, timeout=55)

        for ftype, f in futures:
            if f in done:
                try:
                    res_val = f.result(timeout=0.1)
                    if ftype == 'http':
                        k, v = res_val
                        results[k] = v
                    else:
                        for k, v in res_val:
                            results[k] = v
                except Exception:
                    pass
            else:
                try:
                    f.cancel()
                except Exception:
                    pass
    finally:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            executor.shutdown(wait=False)

    # Ensure all stores are present in results and UI is notified
    for s in STORES_REGISTRY:
        if s['key'] not in results:
            res_item = {
                'found': False,
                'error': f'غير متوفر بالباركود في {s["name"]}',
                'site_name': s['name'],
                'domain': s['domain'],
                'color': s.get('color', '#64748B')
            }
            results[s['key']] = res_item
            _safe_on_store(s['key'], res_item)
            if progress_callback:
                progress_callback(s['name'], "اكتمل")

    return results
