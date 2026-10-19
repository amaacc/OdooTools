"""
batch_excel_pricer.py — High-Speed Multi-Store Batch Excel Pricing & Catalog Scraper Engine
Designed & Developed for: Al-Assali Trading Co. (شركة العسلي للتجارة)
Architect: Abdullah Al-Khatib (عبدالله الخطيب)
Part of: Odoo Price Comparator & Competitor Intelligence Suite
"""

import os
import sys
import re
import html
import json
import time
import math
import urllib.request
import urllib.parse
import ssl
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from competitor_scraper import (
    STORES_REGISTRY, STORES_MAP, BROWSER_HEADERS, SSL_CTX,
    _search_store_single_barcode, _clean_barcode, is_valid_gtin_barcode
)

# ─────────────────────────────────────────────────────────────────────────────
# 🎨 Excel Styles & Palettes
# ─────────────────────────────────────────────────────────────────────────────
FONT_NAME = "Segoe UI"

FONT_HEADER = Font(name=FONT_NAME, size=11, bold=True, color="FFFFFF")
FONT_TITLE = Font(name=FONT_NAME, size=14, bold=True, color="1E3A8A")
FONT_BOLD = Font(name=FONT_NAME, size=10, bold=True)
FONT_BODY = Font(name=FONT_NAME, size=10)
FONT_LINK = Font(name=FONT_NAME, size=10, underline="single", color="1D4ED8")

FILL_TITLE = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid")
FILL_HEADER_DEFAULT = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
FILL_CHEAPER = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")  # We are cheaper
FILL_MORE_EXPENSIVE = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")  # We are more expensive
FILL_EQUAL = PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid")

ALIGN_CENTER = Alignment(horizontal="center", vertical="center")
ALIGN_RIGHT = Alignment(horizontal="right", vertical="center")
ALIGN_LEFT = Alignment(horizontal="left", vertical="center")

THIN_BORDER_VAL = Side(border_style="thin", color="CBD5E1")
CELL_BORDER = Border(left=THIN_BORDER_VAL, right=THIN_BORDER_VAL, top=THIN_BORDER_VAL, bottom=THIN_BORDER_VAL)


# ─────────────────────────────────────────────────────────────────────────────
# 🔍 1. Excel File Inspection & Barcode Column Auto-Detection
# ─────────────────────────────────────────────────────────────────────────────
PRIMARY_BARCODE_KEYWORDS = [
    "barcode", "الباركود", "باركود", "الرمز الدولي", "gtin", "ean", "ean13", "upc",
    "رقم الباركود", "international barcode", "item barcode"
]

FALLBACK_BARCODE_KEYWORDS = [
    "كود الصنف", "رقم الصنف", "رمز الصنف"
]

OUR_PRICE_HEADER_KEYWORDS = [
    "سعر البيع", "سعرنا", "سعر التجزئة", "السعر الحالي", "السعر", "retail price",
    "sales price", "our price", "list_price", "price", "سعر الشاطئ", "سعر الكاشير"
]


def inspect_excel_file(excel_path):
    """
    Inspects an Excel file:
    - Lists sheet names
    - Inspects headers of the active sheet
    - Auto-detects the probable barcode column and our-price column
    - Returns a preview of the first 5 data rows
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"ملف الإكسيل غير موجود: {excel_path}")

    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    sheets = wb.sheetnames
    if not sheets:
        wb.close()
        raise ValueError("ملف الإكسيل لا يحتوي على أي صفحات (Sheets).")

    active_sheet_name = sheets[0]
    ws = wb[active_sheet_name]

    headers = []
    rows_preview = []
    total_rows = 0

    detected_barcode_col = None
    detected_price_col = None

    row_count = 0
    header_row_idx = 1

    for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
        # Find first non-empty row as header
        if not headers:
            non_empty = [c for c in row if c is not None and str(c).strip() != ""]
            if non_empty:
                headers = [str(c).strip() if c is not None else f"Column_{i+1}" for i, c in enumerate(row)]
                header_row_idx = row_idx
                continue

        # Data rows
        if any(c is not None and str(c).strip() != "" for c in row):
            row_count += 1
            if len(rows_preview) < 5:
                rows_preview.append([str(c) if c is not None else "" for c in row[:len(headers)]])

    wb.close()
    total_rows = row_count

    # 1. Detect Barcode Column
    if headers:
        # Check primary barcode keywords first
        for idx, h in enumerate(headers):
            h_lower = h.lower()
            if any(k in h_lower for k in PRIMARY_BARCODE_KEYWORDS):
                detected_barcode_col = idx
                break

        # Check sample row values (digits 8 to 14) to confirm or find barcode column
        if rows_preview:
            col_scores = [0] * len(headers)
            for row in rows_preview:
                for c_idx, val in enumerate(row):
                    clean_v = re.sub(r'[\s\.\,]', '', str(val))
                    if is_valid_gtin_barcode(clean_v):
                        col_scores[c_idx] += 1
            max_score = max(col_scores) if col_scores else 0
            if max_score > 0:
                # If content clearly has barcodes, trust content
                detected_barcode_col = col_scores.index(max_score)

        # Fallback to secondary keywords if not yet detected
        if detected_barcode_col is None:
            for idx, h in enumerate(headers):
                h_lower = h.lower()
                if any(k in h_lower for k in FALLBACK_BARCODE_KEYWORDS):
                    detected_barcode_col = idx
                    break

        # 2. Detect Our Price Column
        for idx, h in enumerate(headers):
            if idx == detected_barcode_col:
                continue
            h_lower = h.lower()
            if any(k in h_lower for k in OUR_PRICE_HEADER_KEYWORDS):
                detected_price_col = idx
                break

    return {
        "sheets": sheets,
        "active_sheet": active_sheet_name,
        "headers": headers,
        "header_row_idx": header_row_idx,
        "total_data_rows": total_rows,
        "detected_barcode_col": detected_barcode_col,
        "detected_price_col": detected_price_col,
        "rows_preview": rows_preview
    }


# ─────────────────────────────────────────────────────────────────────────────
# ⚡ 2. High-Performance Batch Excel Pricing Engine
# ─────────────────────────────────────────────────────────────────────────────
class BatchExcelPricer:
    """
    Orchestrates reading an Excel file, querying 1 or more competitor stores in parallel,
    and appending new styled columns into the workbook.
    """

    def __init__(self, excel_path, selected_store_keys, barcode_col_idx,
                 our_price_col_idx=None, output_path=None, sheet_name=None,
                 max_workers=10):
        self.excel_path = excel_path
        self.selected_store_keys = selected_store_keys
        self.barcode_col_idx = barcode_col_idx
        self.our_price_col_idx = our_price_col_idx
        self.sheet_name = sheet_name
        self.max_workers = max_workers

        if not output_path:
            base, ext = os.path.splitext(excel_path)
            output_path = f"{base}_تسعيرة_المنافسين{ext}"
        self.output_path = output_path

        # Control flags
        self.is_paused = False
        self.is_cancelled = False
        self._pause_cond = threading.Condition()

        # Stats
        self.total_rows = 0
        self.processed_rows = 0
        self.prices_found_count = 0
        self.out_of_stock_count = 0
        self.not_found_count = 0
        self.start_time = 0

    def pause(self):
        with self._pause_cond:
            self.is_paused = True

    def resume(self):
        with self._pause_cond:
            self.is_paused = False
            self._pause_cond.notify_all()

    def cancel(self):
        self.is_cancelled = True
        self.resume()

    def _check_pause_cancel(self):
        if self.is_cancelled:
            return False
        with self._pause_cond:
            while self.is_paused and not self.is_cancelled:
                self._pause_cond.wait(timeout=0.5)
        return not self.is_cancelled

    def run(self, progress_callback=None, status_callback=None):
        """
        Executes the batch pricing workflow.
        progress_callback(processed_count, total_count, current_barcode, stats_dict)
        status_callback(status_text)
        Returns (success_bool, result_summary_or_error)
        """
        self.start_time = time.time()
        if status_callback:
            status_callback("📖 جاري قراءة وتحميل ملف الإكسيل...")

        try:
            wb = openpyxl.load_workbook(self.excel_path)
        except Exception as e:
            return False, f"فشل فتح ملف الإكسيل: {e}"

        ws = wb[self.sheet_name] if self.sheet_name and self.sheet_name in wb.sheetnames else wb.active

        # Identify header row and all data rows
        header_row_idx = 1
        headers = []
        for r_idx in range(1, 10):
            row_vals = [ws.cell(row=r_idx, column=c).value for c in range(1, ws.max_column + 1)]
            if any(v is not None and str(v).strip() != "" for v in row_vals):
                header_row_idx = r_idx
                headers = [str(v).strip() if v is not None else "" for v in row_vals]
                break

        if not headers:
            wb.close()
            return False, "تعذر تحديد صف العناوين (Headers) في ملف الإكسيل."

        # Collect data rows
        data_rows = []
        unique_barcodes_set = set()

        for r_idx in range(header_row_idx + 1, ws.max_row + 1):
            bc_cell = ws.cell(row=r_idx, column=self.barcode_col_idx + 1).value
            if bc_cell is None:
                continue
            bc_str = str(bc_cell).strip().split(".")[0]  # strip any floating point .0
            clean_bc = _clean_barcode(bc_str)
            if clean_bc:
                our_price = 0.0
                if self.our_price_col_idx is not None:
                    p_val = ws.cell(row=r_idx, column=self.our_price_col_idx + 1).value
                    try:
                        our_price = float(re.sub(r'[^\d\.]', '', str(p_val))) if p_val is not None else 0.0
                    except Exception:
                        our_price = 0.0

                data_rows.append({
                    "row_idx": r_idx,
                    "barcode": clean_bc,
                    "our_price": our_price
                })
                unique_barcodes_set.add(clean_bc)

        self.total_rows = len(data_rows)
        if self.total_rows == 0:
            wb.close()
            return False, "لم يتم العثور على أي باركودات صالحة في العمود المحدد."

        if status_callback:
            status_callback(f"🎯 تم استخراج {self.total_rows} صنفاً ({len(unique_barcodes_set)} باركود فريد). جاري إعداد أعمدة المتاجر...")

        # Setup New Columns in the Excel sheet for each selected store
        start_col = ws.max_column + 1
        current_col = start_col
        store_col_map = {}

        selected_stores = [STORES_MAP[k] for k in self.selected_store_keys if k in STORES_MAP]
        if not selected_stores:
            wb.close()
            return False, "لم يتم اختيار أي متجر منافس للبحث."

        for store in selected_stores:
            s_name = store['name']
            s_color = store.get('color', '#1E3A8A').lstrip('#')

            try:
                fill_store = PatternFill(start_color=s_color, end_color=s_color, fill_type="solid")
            except Exception:
                fill_store = FILL_HEADER_DEFAULT

            # 1. Price column
            c_price = current_col
            h_cell = ws.cell(row=header_row_idx, column=c_price, value=f"سعر {s_name} (ر.س)")
            h_cell.font = FONT_HEADER
            h_cell.fill = fill_store
            h_cell.alignment = ALIGN_CENTER
            h_cell.border = CELL_BORDER

            # 2. Availability column
            c_avail = current_col + 1
            h_cell = ws.cell(row=header_row_idx, column=c_avail, value=f"توفر {s_name}")
            h_cell.font = FONT_HEADER
            h_cell.fill = fill_store
            h_cell.alignment = ALIGN_CENTER
            h_cell.border = CELL_BORDER

            # 3. URL column
            c_url = current_col + 2
            h_cell = ws.cell(row=header_row_idx, column=c_url, value=f"رابط الصنف في {s_name}")
            h_cell.font = FONT_HEADER
            h_cell.fill = fill_store
            h_cell.alignment = ALIGN_CENTER
            h_cell.border = CELL_BORDER

            # 4. Price Difference column (if our price exists)
            c_diff = None
            if self.our_price_col_idx is not None:
                c_diff = current_col + 3
                h_cell = ws.cell(row=header_row_idx, column=c_diff, value=f"فارق السعر عن {s_name}")
                h_cell.font = FONT_HEADER
                h_cell.fill = fill_store
                h_cell.alignment = ALIGN_CENTER
                h_cell.border = CELL_BORDER
                current_col += 4
            else:
                current_col += 3

            store_col_map[store['key']] = {
                "price_col": c_price,
                "avail_col": c_avail,
                "url_col": c_url,
                "diff_col": c_diff,
                "store_name": s_name
            }

        # ─────────────────────────────────────────────────────────────────────
        # 🚀 Cache & Concurrent Store Querying
        # ─────────────────────────────────────────────────────────────────────
        # price_cache: (store_key, barcode) -> {found, price, in_stock, url, error}
        price_cache = {}
        cache_lock = threading.Lock()

        def _fetch_single_store_barcode(store, barcode):
            key = store['key']
            cache_key = (key, barcode)
            with cache_lock:
                if cache_key in price_cache:
                    return key, barcode, price_cache[cache_key]

            try:
                res = _search_store_single_barcode(store, barcode)
            except Exception as ex:
                res = {"found": False, "error": str(ex)}

            with cache_lock:
                price_cache[cache_key] = res
            return key, barcode, res

        # Process each row
        if status_callback:
            status_callback(f"🚀 بدء الاستعلام المتزامن في {len(selected_stores)} متجراً...")

        executor = ThreadPoolExecutor(max_workers=self.max_workers)

        try:
            for item in data_rows:
                if not self._check_pause_cancel():
                    break

                r_idx = item["row_idx"]
                barcode = item["barcode"]
                our_price = item["our_price"]

                # Submit searches for all selected stores for this barcode
                futures = [executor.submit(_fetch_single_store_barcode, store, barcode) for store in selected_stores]

                row_has_price = False

                for fut in as_completed(futures):
                    s_key, s_bc, res = fut.result()
                    cols = store_col_map[s_key]

                    # 1. Price Cell
                    price_cell = ws.cell(row=r_idx, column=cols["price_col"])
                    price_cell.border = CELL_BORDER
                    price_cell.alignment = ALIGN_CENTER

                    # 2. Availability Cell
                    avail_cell = ws.cell(row=r_idx, column=cols["avail_col"])
                    avail_cell.border = CELL_BORDER
                    avail_cell.alignment = ALIGN_CENTER

                    # 3. URL Cell
                    url_cell = ws.cell(row=r_idx, column=cols["url_col"])
                    url_cell.border = CELL_BORDER
                    url_cell.alignment = ALIGN_CENTER

                    # 4. Diff Cell
                    diff_cell = ws.cell(row=r_idx, column=cols["diff_col"]) if cols["diff_col"] else None
                    if diff_cell:
                        diff_cell.border = CELL_BORDER
                        diff_cell.alignment = ALIGN_CENTER

                    if res.get("found") and float(res.get("price") or 0) > 0.5:
                        row_has_price = True
                        p_val = round(float(res["price"]), 2)
                        price_cell.value = p_val
                        price_cell.number_format = '#,##0.00 "ر.س"'
                        price_cell.font = FONT_BOLD

                        in_stock = res.get("in_stock", True)
                        if in_stock:
                            avail_cell.value = "متوفر ✅"
                            avail_cell.fill = FILL_CHEAPER
                        else:
                            avail_cell.value = "نفد المخزون ⚠️"
                            avail_cell.fill = FILL_MORE_EXPENSIVE
                            self.out_of_stock_count += 1

                        p_url = res.get("url", "")
                        if p_url:
                            url_cell.value = "عرض في المتجر 🔗"
                            url_cell.hyperlink = p_url
                            url_cell.font = FONT_LINK
                        else:
                            url_cell.value = "—"

                        # Price difference logic
                        if diff_cell and our_price > 0.5:
                            diff_val = round(p_val - our_price, 2)
                            diff_pct = round((diff_val / our_price) * 100, 1)

                            if diff_val > 0.1:  # Competitor is more expensive -> We are cheaper
                                diff_cell.value = f"+{diff_val:.2f} ر.س (+{diff_pct:.0f}%) نحن أرخص ✅"
                                diff_cell.fill = FILL_CHEAPER
                                diff_cell.font = FONT_BOLD
                            elif diff_val < -0.1:  # Competitor is cheaper -> We are more expensive
                                diff_cell.value = f"{diff_val:.2f} ر.س ({diff_pct:.0f}%) نحن أغلى ⚠️"
                                diff_cell.fill = FILL_MORE_EXPENSIVE
                                diff_cell.font = FONT_BOLD
                            else:
                                diff_cell.value = "متطابق بالسعر ⚖️"
                                diff_cell.fill = FILL_EQUAL
                                diff_cell.font = FONT_BOLD
                    else:
                        price_cell.value = "غير متوفر"
                        price_cell.font = FONT_BODY
                        avail_cell.value = "غير معروض"
                        url_cell.value = "—"
                        if diff_cell:
                            diff_cell.value = "—"

                if row_has_price:
                    self.prices_found_count += 1
                else:
                    self.not_found_count += 1

                self.processed_rows += 1

                # Periodically save every 30 rows to guarantee zero data loss
                if self.processed_rows % 30 == 0:
                    try:
                        wb.save(self.output_path)
                    except Exception:
                        pass

                if progress_callback:
                    elapsed = time.time() - self.start_time
                    speed = self.processed_rows / elapsed if elapsed > 0 else 0
                    rem_sec = int((self.total_rows - self.processed_rows) / speed) if speed > 0 else 0
                    stats = {
                        "processed": self.processed_rows,
                        "total": self.total_rows,
                        "found": self.prices_found_count,
                        "out_of_stock": self.out_of_stock_count,
                        "not_found": self.not_found_count,
                        "speed": speed,
                        "remaining_sec": rem_sec
                    }
                    progress_callback(self.processed_rows, self.total_rows, barcode, stats)

        finally:
            executor.shutdown(wait=False)

        # Auto-fit new column widths
        for col_i in range(start_col, current_col):
            col_letter = get_column_letter(col_i)
            ws.column_dimensions[col_letter].width = 22

        # Final Save
        try:
            wb.save(self.output_path)
            wb.close()
        except Exception as e:
            return False, f"تم الفحص بنجاح ولكن تعذر حفظ الملف النهائي (تأكد من إغلاقه إن كان مفتوحاً):\n{e}"

        elapsed_total = round(time.time() - self.start_time, 1)
        summary = (
            f"🎉 تم إكمال التسعير وحفظ ملف الإكسيل بنجاح!\n\n"
            f"• الملف الناتج: {self.output_path}\n"
            f"• إجمالي الصفوف: {self.processed_rows} من أصل {self.total_rows}\n"
            f"• أصناف عُثر على أسعار منافسين لها: {self.prices_found_count}\n"
            f"• أصناف غير متوفرة في المتاجر: {self.not_found_count}\n"
            f"• الوقت المستغرق: {elapsed_total} ثانية"
        )
        return True, summary


# ─────────────────────────────────────────────────────────────────────────────
# 🌐 3. Full Store Catalog Scraper (سحب كتالوج متجر كامل إلى إكسيل)
# ─────────────────────────────────────────────────────────────────────────────
def split_bilingual_title(title, slug=""):
    """
    Separates a product title into Arabic Name and English Name.
    If the title contains both (e.g. 'عطر لا بتيت - Guerlain La Petite'), splits them.
    If English is missing, formats English name cleanly from the URL slug if present.
    """
    if not title:
        return "", ""

    has_ar = bool(re.search(r'[\u0600-\u06FF]', title))
    has_en = bool(re.search(r'[a-zA-Z]{3,}', title))

    name_ar = ""
    name_en = ""

    if has_ar and has_en:
        parts = re.split(r'\s*[-/|–—]\s*|\n+', title)
        ar_parts = [p.strip() for p in parts if re.search(r'[\u0600-\u06FF]', p)]
        en_parts = [p.strip() for p in parts if re.search(r'[a-zA-Z]', p) and not re.search(r'[\u0600-\u06FF]', p)]

        name_ar = " - ".join(ar_parts) if ar_parts else title
        name_en = " - ".join(en_parts) if en_parts else ""
    elif has_ar:
        name_ar = title.strip()
    else:
        name_en = title.strip()

    if not name_en and slug:
        clean_slug = urllib.parse.unquote(slug).strip()
        clean_slug = re.sub(r'/p\d+$|/pdp/\d+$|/products/|\.html$', '', clean_slug)
        clean_slug = clean_slug.split('/')[-1].split('?')[0]
        # Ignore purely numeric or short random hashes
        if re.search(r'^[a-zA-Z0-9\-_]+$', clean_slug) and len(clean_slug) > 3 and not clean_slug.isdigit():
            # If slug contains English words
            if re.search(r'[a-zA-Z]{3,}', clean_slug):
                words = re.split(r'[-_+]', clean_slug)
                name_en = " ".join(w.capitalize() for w in words if w and not w.isdigit())

    return name_ar.strip(), name_en.strip()


def scrape_store_catalog_to_excel(store_key, output_path=None, target_count=500,
                                  days_limit=None, progress_callback=None, cancel_event=None):
    """
    Scrapes a store's catalog into a fresh Excel file.
    Supports Shopify, Salla, Zid, Magento 2 (Nazih), WooCommerce (BeautyCloud), and more.
    Includes Arabic & English product names, Barcodes (SKU), Active Price, Old Price,
    Discount %, Availability, Date Added / Last Modified, and Direct Hyperlinks.

    If days_limit is specified (e.g. 7), only products added/modified within the last
    specified days (>= now - timedelta(days=days_limit)) will be extracted.
    """
    store = STORES_MAP.get(store_key)
    if not store:
        return False, "المتجر المحدد غير موجود في السجل.", None

    domain = store['domain']
    name = store['name']
    platform = store['platform']

    cutoff_date = None
    if days_limit is not None and str(days_limit).strip().isdigit() and int(days_limit) > 0:
        days_limit = int(days_limit)
        cutoff_dt = datetime.now() - timedelta(days=days_limit)
        cutoff_date = cutoff_dt.strftime("%Y-%m-%d")

    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        clean_name = re.sub(r'[\\/*?:"<>|]', '_', name)
        if cutoff_date:
            output_path = os.path.join(os.path.expanduser("~"), "Desktop", f"أحدث_منتجات_{clean_name}_آخر_{days_limit}_أيام_{ts}.xlsx")
        else:
            output_path = os.path.join(os.path.expanduser("~"), "Desktop", f"كتالوج_{clean_name}_{ts}.xlsx")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"كتالوج {name}"[:31]
    ws.sheet_view.rightToLeft = True

    # Title Banner (Columns A to I)
    ws.merge_cells("A1:I1")
    if cutoff_date:
        banner_txt = f"🛒 أحدث منتجات: {name} ({domain}) — المضافة/المحدثة خلال آخر {days_limit} يوم (منذ {cutoff_date})"
    else:
        banner_txt = f"🛒 كتالوج وتسعيرة منتجات: {name} ({domain})"
    title_cell = ws.cell(row=1, column=1, value=banner_txt)
    title_cell.font = FONT_TITLE
    title_cell.alignment = ALIGN_CENTER
    title_cell.fill = FILL_TITLE
    ws.row_dimensions[1].height = 36

    # 9 Distinct Columns
    headers = [
        "اسم المنتج (بالعربي)",
        "اسم المنتج (بالإنجليزي)",
        "الباركود / الكود (SKU)",
        "السعر الحالي (ر.س)",
        "السعر السابق (Old Price)",
        "نسبة الخصم",
        "حالة التوفر",
        "تاريخ الإضافة / التحديث",
        "رابط المنتج"
    ]
    for c_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=3, column=c_idx, value=h)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER_DEFAULT
        cell.alignment = ALIGN_CENTER
        cell.border = CELL_BORDER
    ws.row_dimensions[3].height = 28

    current_row = 4
    extracted_count = 0
    start_time = time.time()

    def _write_item(name_ar, name_en, sku, price, old_price, in_stock, date_val, url):
        nonlocal current_row, extracted_count
        p_val = float(price or 0)
        old_val = float(old_price or 0) if old_price else 0.0

        discount_str = "—"
        if old_val > p_val > 0:
            pct = round(((old_val - p_val) / old_val) * 100)
            discount_str = f"{pct}%"

        avail_str = "متوفر ✅" if in_stock else "نفد المخزون ⚠️"

        # Format date cleanly
        date_str = "—"
        if date_val:
            m_d = re.search(r'\b(\d{4}[-/]\d{1,2}[-/]\d{1,2})\b', str(date_val))
            if m_d:
                date_str = m_d.group(1).replace('/', '-')
            else:
                date_str = str(date_val)[:10]

        # Filter strictly if days_limit is set
        if cutoff_date:
            if date_str == "—" or date_str < cutoff_date:
                return

        ws.cell(row=current_row, column=1, value=name_ar or "—").font = FONT_BOLD
        ws.cell(row=current_row, column=2, value=name_en or "—").font = FONT_BODY
        ws.cell(row=current_row, column=3, value=str(sku or "—")).font = FONT_BODY
        ws.cell(row=current_row, column=4, value=p_val).number_format = '#,##0.00 "ر.س"'
        ws.cell(row=current_row, column=5, value=old_val if old_val > 0 else "—")
        ws.cell(row=current_row, column=6, value=discount_str).alignment = ALIGN_CENTER
        ws.cell(row=current_row, column=7, value=avail_str).alignment = ALIGN_CENTER
        ws.cell(row=current_row, column=8, value=date_str).alignment = ALIGN_CENTER

        u_cell = ws.cell(row=current_row, column=9, value="رابط المنتج 🔗")
        if url:
            u_cell.hyperlink = url
            u_cell.font = FONT_LINK
        u_cell.alignment = ALIGN_CENTER

        for c_i in range(1, 10):
            ws.cell(row=current_row, column=c_i).border = CELL_BORDER

        current_row += 1
        extracted_count += 1

        if progress_callback:
            elapsed = time.time() - start_time
            spd = extracted_count / elapsed if elapsed > 0 else 0
            progress_callback(extracted_count, target_count, name_ar or name_en, spd)

    # ── A. Shopify Platform (/products.json) ─────────────────────────────────
    if platform == "shopify":
        page = 1
        while extracted_count < target_count:
            if cancel_event and cancel_event.is_set():
                break

            url = f"https://{domain}/products.json?limit=250&page={page}"
            req = urllib.request.Request(url, headers=BROWSER_HEADERS)
            try:
                with urllib.request.urlopen(req, context=SSL_CTX, timeout=12) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    products = data.get("products", [])
                    if not products:
                        break

                    for p in products:
                        if extracted_count >= target_count:
                            break
                        if cancel_event and cancel_event.is_set():
                            break

                        raw_title = p.get("title", "")
                        handle = p.get("handle", "")
                        prod_url = f"https://{domain}/products/{handle}" if handle else ""
                        name_ar, name_en = split_bilingual_title(raw_title, handle)
                        created_date = p.get("created_at") or p.get("published_at") or ""

                        variants = p.get("variants", [])
                        for v in variants:
                            if extracted_count >= target_count:
                                break
                            v_price = float(v.get("price") or 0)
                            compare_at = float(v.get("compare_at_price") or 0) if v.get("compare_at_price") else 0.0
                            sku = v.get("sku") or v.get("barcode") or ""
                            avail = bool(v.get("available", True))

                            _write_item(name_ar, name_en, sku, v_price, compare_at, avail, created_date, prod_url)

                    page += 1
                    time.sleep(0.2)
            except Exception:
                break

    # ── B. Nahdi Online (sitemap_index_ar.xml -> JSON-LD) ────────────────────
    elif platform == "nahdi" or store_key == "nahdi":
        nahdi_urls = []
        try:
            r_idx = urllib.request.urlopen(urllib.request.Request("https://www.nahdionline.com/sitemap_index_ar.xml", headers=BROWSER_HEADERS), context=SSL_CTX, timeout=8)
            sub_maps = re.findall(r'<loc>(?:<!\[CDATA\[)?(https?://[^\]<]+)(?:\]\]>)?</loc>', r_idx.read().decode('utf-8', errors='ignore'))
            # Query sub-sitemaps (sitemap1.xml to sitemap7.xml)
            for sm in (sub_maps[:3] if sub_maps else ["https://www.nahdionline.com/ar/sitemap1.xml"]):
                try:
                    r_sm = urllib.request.urlopen(urllib.request.Request(sm, headers=BROWSER_HEADERS), context=SSL_CTX, timeout=10)
                    all_locs = re.findall(r'<loc>(?:<!\[CDATA\[)?(https?://[^\]<]+)(?:\]\]>)?</loc>', r_sm.read().decode('utf-8', errors='ignore'))
                    for u in all_locs:
                        if '/pdp/' in u:
                            nahdi_urls.append(u)
                    if len(nahdi_urls) >= target_count * 2:
                        break
                except Exception:
                    continue
        except Exception:
            pass

        def _fetch_nahdi(u):
            if cancel_event and cancel_event.is_set():
                return None
            try:
                time.sleep(0.06)
                qu = urllib.parse.quote(u, safe=':/?&=#')
                req_p = urllib.request.Request(qu, headers=BROWSER_HEADERS)
                with urllib.request.urlopen(req_p, context=SSL_CTX, timeout=8) as resp:
                    h_data = resp.read().decode('utf-8', errors='ignore')
                ld = re.findall(r'<script\b[^>]*\btype=["\']application/ld\+json["\'][^>]*>(.*?)</script>', h_data, flags=re.DOTALL)
                for b in ld:
                    try:
                        d = json.loads(b)
                        if d.get('@type') == 'Product':
                            off = d.get('offers', {})
                            if isinstance(off, list) and off:
                                off = off[0]
                            price = float(off.get('price') or 0)
                            if price > 0.1:
                                sku = str(d.get('sku') or '')
                                raw_title = d.get('name') or ''
                                date_val = off.get('validFrom') or ''
                                is_in_stock = 'InStock' in str(off.get('availability', ''))
                                name_ar, name_en = split_bilingual_title(raw_title, u)
                                return {
                                    'name_ar': name_ar, 'name_en': name_en, 'sku': sku,
                                    'price': price, 'old_price': 0.0, 'in_stock': is_in_stock,
                                    'date_val': date_val, 'url': u
                                }
                    except Exception:
                        continue
            except Exception:
                return None
            return None

        with ThreadPoolExecutor(max_workers=4) as executor:
            for item in executor.map(_fetch_nahdi, nahdi_urls):
                if cancel_event and cancel_event.is_set():
                    break
                if extracted_count >= target_count:
                    break
                if item:
                    _write_item(
                        item['name_ar'], item['name_en'], item['sku'],
                        item['price'], item['old_price'], item['in_stock'], item['date_val'], item['url']
                    )

    # ── C. Magento 2 Platforms (Nazih, United Pharmacy) ───────────────────────
    elif platform == "magento" or store_key in ["nazih", "unitedpharmacy"]:
        magento_urls = []
        if store_key == "nazih":
            try:
                req_sm = urllib.request.Request("https://nazih.sa/media/sitemapksaae.xml", headers=BROWSER_HEADERS)
                with urllib.request.urlopen(req_sm, context=SSL_CTX, timeout=10) as r:
                    sm_txt = r.read().decode('utf-8', errors='ignore')
                all_locs = re.findall(r'<loc>(?:<!\[CDATA\[)?(https?://[^\]<]+\.html)(?:\]\]>)?</loc>', sm_txt)
                for u in all_locs:
                    path = u.replace("https://nazih.sa/", "")
                    if "/" not in path and path.count('-') >= 2 and not any(k in path for k in ['skin.html', 'hair.html', 'nails.html', 'men.html', 'brands.html', 'sale.html']):
                        magento_urls.append(u)
            except Exception:
                pass
        elif store_key == "unitedpharmacy":
            try:
                req_sm = urllib.request.Request("https://unitedpharmacy-livenew.s3.ap-southeast-1.amazonaws.com/live/sitemap_ar.xml", headers=BROWSER_HEADERS)
                with urllib.request.urlopen(req_sm, context=SSL_CTX, timeout=12) as r:
                    sm_txt = r.read().decode('utf-8', errors='ignore')
                all_locs = re.findall(r'<loc>(?:<!\[CDATA\[)?(https?://[^\]<]+)(?:\]\]>)?</loc>', sm_txt)
                for u in all_locs:
                    if u.startswith('https://unitedpharmacy.sa/ar/') and u.endswith('.html'):
                        sub = u.replace('https://unitedpharmacy.sa/ar/', '')
                        if '/' not in sub and re.search(r'\d', sub):
                            magento_urls.append(u)
                            if len(magento_urls) >= max(300, target_count * 3):
                                break
            except Exception:
                pass

        def _fetch_magento(u):
            if cancel_event and cancel_event.is_set():
                return None
            try:
                time.sleep(0.06)
                qu = urllib.parse.quote(u, safe=':/?&=#')
                req_p = urllib.request.Request(qu, headers=BROWSER_HEADERS)
                with urllib.request.urlopen(req_p, context=SSL_CTX, timeout=8) as resp:
                    h_data = resp.read().decode('utf-8', errors='ignore')

                meta_t = re.search(r'property="og:title"\s+content="([^"]+)"', h_data)
                raw_title = html.unescape(meta_t.group(1).strip()) if meta_t else ""

                meta_p = re.search(r'property="product:price:amount"\s+content="([0-9\.]+)"', h_data)
                price = float(meta_p.group(1)) if meta_p else 0.0

                sku_m = re.search(r'itemprop="sku">\s*([^<]+)', h_data) or re.search(r'"sku":\s*"([^"]+)"', h_data)
                sku = sku_m.group(1).strip() if sku_m else ""

                old_p_m = re.search(r'data-price-type="oldPrice"[^>]*>.*?<span[^>]*class="price"[^>]*>([^<]+)', h_data, flags=re.DOTALL)
                old_price = 0.0
                if old_p_m:
                    nums = re.findall(r'(\d+(?:\.\d+)?)', old_p_m.group(1).replace('٫', '.'))
                    if nums:
                        old_price = float(nums[0])

                # Check JSON-LD fallback for missing price or sku
                if price <= 0.1:
                    ld = re.findall(r'<script\b[^>]*\btype=["\']application/ld\+json["\'][^>]*>(.*?)</script>', h_data, flags=re.DOTALL)
                    for b in ld:
                        if 'Product' in b:
                            try:
                                d = json.loads(b)
                                if not raw_title: raw_title = d.get('name', '')
                                if not sku: sku = str(d.get('sku') or '')
                                off = d.get('offers', {})
                                if isinstance(off, list) and off: off = off[0]
                                price = float(off.get('price') or 0)
                            except Exception:
                                pass

                in_stock = 'in stock' in h_data.lower() or 'stock available' in h_data.lower()
                name_ar, name_en = split_bilingual_title(raw_title, u)

                if price > 0.1:
                    return {
                        'name_ar': name_ar, 'name_en': name_en, 'sku': sku,
                        'price': price, 'old_price': old_price, 'in_stock': in_stock,
                        'date_val': "", 'url': u
                    }
            except Exception:
                return None
            return None

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_fetch_magento, u) for u in magento_urls[:min(len(magento_urls), max(50, target_count * 2 + 10))]]
            for fut in as_completed(futures):
                if cancel_event and cancel_event.is_set():
                    break
                if extracted_count >= target_count:
                    break
                try:
                    item = fut.result()
                    if item:
                        _write_item(
                            item['name_ar'], item['name_en'], item['sku'],
                            item['price'], item['old_price'], item['in_stock'], item['date_val'], item['url']
                        )
                except Exception:
                    pass

    # ── D. OpenCart Platform (Spama) ──────────────────────────────────────────
    elif platform == "opencart" or store_key == "spama":
        oc_urls = []
        try:
            req_sm = urllib.request.Request(f"https://{domain}/sitemap-product-ar-1.xml", headers=BROWSER_HEADERS)
            with urllib.request.urlopen(req_sm, context=SSL_CTX, timeout=15) as r:
                sm_txt = r.read().decode('utf-8', errors='ignore')
            oc_urls = re.findall(r'<loc>(?:<!\[CDATA\[)?(https?://[^\]<]+)(?:\]\]>)?</loc>', sm_txt)
        except Exception:
            try:
                req_sm = urllib.request.Request(f"https://{domain}/sitemap.xml", headers=BROWSER_HEADERS)
                with urllib.request.urlopen(req_sm, context=SSL_CTX, timeout=10) as r:
                    sm_txt = r.read().decode('utf-8', errors='ignore')
                oc_urls = re.findall(r'<loc>(?:<!\[CDATA\[)?(https?://[^\]<]+)(?:\]\]>)?</loc>', sm_txt)
            except Exception:
                pass

        def _fetch_opencart(u):
            if cancel_event and cancel_event.is_set():
                return None
            try:
                time.sleep(0.06)
                qu = urllib.parse.quote(u, safe=':/?&=#')
                req_p = urllib.request.Request(qu, headers=BROWSER_HEADERS)
                with urllib.request.urlopen(req_p, context=SSL_CTX, timeout=8) as resp:
                    h_data = resp.read().decode('utf-8', errors='ignore')
                ld = re.findall(r'<script\b[^>]*\btype=["\']application/ld\+json["\'][^>]*>(.*?)</script>', h_data, flags=re.DOTALL)
                for b in ld:
                    if 'Product' in b:
                        try:
                            d = json.loads(b)
                            raw_title = d.get('name', '')
                            sku = str(d.get('sku') or '')
                            off = d.get('offers', {})
                            if isinstance(off, list) and off: off = off[0]
                            price = float(off.get('price') or 0)
                            is_in_stock = 'InStock' in str(off.get('availability', ''))
                            date_val = off.get('validFrom') or ""
                            name_ar, name_en = split_bilingual_title(raw_title, u)
                            if price > 0.1:
                                return {
                                    'name_ar': name_ar, 'name_en': name_en, 'sku': sku,
                                    'price': price, 'old_price': 0.0, 'in_stock': is_in_stock,
                                    'date_val': date_val, 'url': u
                                }
                        except Exception:
                            pass
            except Exception:
                return None
            return None

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(_fetch_opencart, u) for u in oc_urls[:min(len(oc_urls), max(50, target_count * 2 + 10))]]
            for fut in as_completed(futures):
                if cancel_event and cancel_event.is_set():
                    break
                if extracted_count >= target_count:
                    break
                try:
                    item = fut.result()
                    if item:
                        _write_item(
                            item['name_ar'], item['name_en'], item['sku'],
                            item['price'], item['old_price'], item['in_stock'], item['date_val'], item['url']
                        )
                except Exception:
                    pass

    # ── E. Salla Platform (Sitemaps + Paced Resilient JSON-LD) ────────────────
    elif platform == "salla":
        product_items = []  # list of (url, lastmod, en_slug)

        # Special case: Tdalal Care (Sitemaps disabled, crawl category endpoints)
        if domain == "tdalalcare.com":
            try:
                r_home = urllib.request.urlopen(urllib.request.Request("https://tdalalcare.com/", headers=BROWSER_HEADERS), context=SSL_CTX, timeout=8)
                home_txt = r_home.read().decode('utf-8', errors='ignore')
                found_cats = set(re.findall(r'href="(https://tdalalcare\.com/-/[cp]\d+)"', home_txt))
                p_urls = set(u for u in found_cats if '/-/' in u and '/p' in u)
                c_urls = [u for u in found_cats if '/c' in u]

                for c_u in c_urls[:6]:
                    if len(p_urls) >= target_count * 2:
                        break
                    try:
                        r_c = urllib.request.urlopen(urllib.request.Request(c_u, headers=BROWSER_HEADERS), context=SSL_CTX, timeout=6)
                        c_txt = r_c.read().decode('utf-8', errors='ignore')
                        new_p = re.findall(r'href="(https://tdalalcare\.com/-/[^"]*p\d+)"', c_txt)
                        p_urls.update(new_p)
                    except Exception:
                        pass
                for pu in p_urls:
                    product_items.append((pu, "", ""))
            except Exception:
                pass
        else:
            # Standard Salla Sitemap Discovery
            try:
                req_index = urllib.request.Request(f"https://{domain}/sitemap.xml", headers=BROWSER_HEADERS)
                with urllib.request.urlopen(req_index, context=SSL_CTX, timeout=10) as r:
                    idx_txt = r.read().decode('utf-8', errors='ignore')

                sub_maps = re.findall(r'<loc>(?:<!\[CDATA\[)?(https?://[^\]<]+sitemap[^\]<]*\.xml)(?:\]\]>)?</loc>', idx_txt, flags=re.I)
                if not sub_maps:
                    sub_maps = [f"https://{domain}/sitemap.xml"]
                else:
                    # In Salla, sitemap-2.xml & sitemap-3.xml contain products, prioritize them
                    sub_maps.sort(reverse=True)

                en_slug_lookup = {}
                raw_prod_urls = []

                for sm_url in sub_maps:
                    try:
                        req_sm = urllib.request.Request(sm_url, headers=BROWSER_HEADERS)
                        with urllib.request.urlopen(req_sm, context=SSL_CTX, timeout=10) as sm_r:
                            sm_content = sm_r.read().decode('utf-8', errors='ignore')

                        url_blocks = re.findall(r'<url>(.*?)</url>', sm_content, flags=re.DOTALL)
                        if not url_blocks:
                            url_blocks = [f"<loc>{u}</loc>" for u in re.findall(r'<loc>(?:<!\[CDATA\[)?(https?://[^\]<]+)(?:\]\]>)?</loc>', sm_content)]

                        for ub in url_blocks:
                            loc_m = re.search(r'<loc>(?:<!\[CDATA\[)?(https?://[^\]<]+)(?:\]\]>)?</loc>', ub)
                            if not loc_m:
                                continue
                            pu = loc_m.group(1).strip()
                            mod_m = re.search(r'<lastmod>([^<]+)</lastmod>', ub)
                            l_mod = mod_m.group(1).strip() if mod_m else ""

                            # Filter strictly by cutoff_date if requested
                            if cutoff_date and l_mod:
                                if l_mod[:10] < cutoff_date:
                                    continue

                            # Skip static policy & blog pages
                            if any(k in pu for k in ['/blog', '/p/%', '/p/من', '/p/الشروط', '/p/سياسة', '/p/about', '/p/terms']):
                                continue
                            if pu.rstrip('/') in [f"https://{domain}", f"https://{domain}/ar", f"https://{domain}/en"]:
                                continue

                            # Detect product URL pattern (p\d+, short codes, products/, /-/)
                            path = pu.replace(f"https://{domain}", "").rstrip('/')
                            parts = [p for p in path.split('/') if p]
                            if not parts:
                                continue
                            last_part = parts[-1]
                            is_prod = (
                                re.search(r'p\d+$', last_part) or
                                re.search(r'^[a-zA-Z0-9]{5,8}$', last_part) or
                                '/products/' in path or
                                '/-/' in path
                            )
                            if is_prod:
                                if "/en/" in pu:
                                    ar_key = pu.replace("/en/", "/ar/")
                                    en_slug_lookup[ar_key] = last_part
                                else:
                                    raw_prod_urls.append((pu, l_mod))
                        if len(raw_prod_urls) >= max(300, target_count * 3):
                            break
                    except Exception:
                        continue
                    if len(raw_prod_urls) >= max(300, target_count * 3):
                        break

                # Deduplicate and build final queue
                seen_urls = set()
                for pu, lmod in raw_prod_urls:
                    if pu not in seen_urls:
                        seen_urls.add(pu)
                        en_slug = en_slug_lookup.get(pu, "")
                        product_items.append((pu, lmod, en_slug))

            except Exception:
                pass

        def _fetch_salla_product(item_tuple):
            if cancel_event and cancel_event.is_set():
                return None
            u, date_val, en_slug = item_tuple
            qu = urllib.parse.quote(u, safe=':/?&=#')

            # Rate limit backoff (up to 3 attempts with progressive delay)
            for attempt in range(3):
                if cancel_event and cancel_event.is_set():
                    return None
                try:
                    time.sleep(0.10)
                    req_p = urllib.request.Request(qu, headers=BROWSER_HEADERS)
                    with urllib.request.urlopen(req_p, context=SSL_CTX, timeout=8) as resp:
                        h_data = resp.read().decode('utf-8', errors='ignore')

                    ld = re.findall(r'<script\b[^>]*\btype=["\']application/ld\+json["\'][^>]*>(.*?)</script>', h_data, flags=re.DOTALL)
                    for block in ld:
                        if 'Product' in block:
                            d = json.loads(block)
                            graph = d.get('@graph', [d])
                            for item in graph:
                                if item.get('@type') == 'Product':
                                    raw_title = item.get('name', '')
                                    sku = item.get('sku') or item.get('gtin13') or item.get('barcode') or ''
                                    offers = item.get('offers', {})
                                    if isinstance(offers, list) and offers:
                                        offers = offers[0]
                                    raw_p = str(offers.get('price') or '0').replace(',', '').strip()
                                    price = float(raw_p) if raw_p else 0.0
                                    is_in_stock = 'InStock' in str(offers.get('availability', ''))
                                    release_d = offers.get('validFrom') or date_val
                                    name_ar, name_en = split_bilingual_title(raw_title, en_slug or u)
                                    return {
                                        'name_ar': name_ar,
                                        'name_en': name_en,
                                        'sku': sku,
                                        'price': price,
                                        'old_price': 0.0,
                                        'in_stock': is_in_stock,
                                        'date_val': release_d,
                                        'url': u
                                    }
                    return None
                except urllib.error.HTTPError as he:
                    if he.code == 429:
                        time.sleep(1.5 + attempt * 1.5)
                        continue
                    return None
                except Exception:
                    return None
            return None

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(_fetch_salla_product, it) for it in product_items[:min(len(product_items), max(50, target_count * 2 + 10))]]
            for fut in as_completed(futures):
                if cancel_event and cancel_event.is_set():
                    break
                if extracted_count >= target_count:
                    break
                try:
                    item = fut.result()
                    if item and float(item.get('price', 0)) > 0.1:
                        _write_item(
                            item['name_ar'], item['name_en'], item['sku'],
                            item['price'], item['old_price'], item['in_stock'], item['date_val'], item['url']
                        )
                except Exception:
                    pass

    # ── F. Zid Platform (Sitemaps + Quoted JSON-LD) ──────────────────────────
    elif platform == "zid":
        zid_items = []
        try:
            req_sm = urllib.request.Request(f"https://{domain}/sitemap_products.xml", headers=BROWSER_HEADERS)
            with urllib.request.urlopen(req_sm, context=SSL_CTX, timeout=10) as r:
                sm_txt = r.read().decode('utf-8', errors='ignore')
            urls_with_dates = re.findall(r'<url>(.*?)</url>', sm_txt, flags=re.DOTALL)
            for ub in urls_with_dates:
                loc_m = re.search(r'<loc>(?:<!\[CDATA\[)?(https?://[^\]<]+)(?:\]\]>)?</loc>', ub)
                if loc_m:
                    u = loc_m.group(1).strip()
                    if '/products/' in u or re.search(r'/p\d+$', u) or not any(k in u for k in ['/category', '/blog', '/pages']):
                        d_m = re.search(r'<lastmod>([^<]+)</lastmod>', ub)
                        lmod = d_m.group(1).strip() if d_m else ""
                        if cutoff_date and lmod:
                            if lmod[:10] < cutoff_date:
                                continue
                        zid_items.append((u, lmod))
                if len(zid_items) >= max(300, target_count * 3):
                    break
        except Exception:
            try:
                req_sm = urllib.request.Request(f"https://{domain}/sitemap.xml", headers=BROWSER_HEADERS)
                with urllib.request.urlopen(req_sm, context=SSL_CTX, timeout=10) as r:
                    sm_txt = r.read().decode('utf-8', errors='ignore')
                urls_with_dates = re.findall(r'<url>(.*?)</url>', sm_txt, flags=re.DOTALL)
                for ub in urls_with_dates:
                    loc_m = re.search(r'<loc>(?:<!\[CDATA\[)?(https?://[^\]<]+)(?:\]\]>)?</loc>', ub)
                    if loc_m:
                        u = loc_m.group(1).strip()
                        if '/products/' in u or re.search(r'/p\d+$', u):
                            d_m = re.search(r'<lastmod>([^<]+)</lastmod>', ub)
                            lmod = d_m.group(1).strip() if d_m else ""
                            if cutoff_date and lmod:
                                if lmod[:10] < cutoff_date:
                                    continue
                            zid_items.append((u, lmod))
                    if len(zid_items) >= max(300, target_count * 3):
                        break
            except Exception:
                pass

        def _fetch_zid_product(tup):
            if cancel_event and cancel_event.is_set():
                return None
            u, date_val = tup
            try:
                time.sleep(0.05)
                qu = urllib.parse.quote(u, safe=':/?&=#')
                req_p = urllib.request.Request(qu, headers=BROWSER_HEADERS)
                with urllib.request.urlopen(req_p, context=SSL_CTX, timeout=8) as resp:
                    h_data = resp.read().decode('utf-8', errors='ignore')
                ld = re.findall(r'<script\b[^>]*\btype=["\']application/ld\+json["\'][^>]*>(.*?)</script>', h_data, flags=re.DOTALL)
                for block in ld:
                    if 'Product' in block:
                        d = json.loads(block)
                        raw_title = d.get('name', '')
                        sku = d.get('sku') or ''
                        offers = d.get('offers', {})
                        if isinstance(offers, list) and offers:
                            offers = offers[0]
                        raw_p = str(offers.get('price') or '0').replace(',', '').strip()
                        price = float(raw_p) if raw_p else 0.0
                        is_in_stock = 'InStock' in str(offers.get('availability', ''))
                        name_ar, name_en = split_bilingual_title(raw_title, u)
                        return {
                            'name_ar': name_ar,
                            'name_en': name_en,
                            'sku': sku,
                            'price': price,
                            'old_price': 0.0,
                            'in_stock': is_in_stock,
                            'date_val': date_val,
                            'url': u
                        }
            except Exception:
                return None
            return None

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_fetch_zid_product, it) for it in zid_items[:min(len(zid_items), max(50, target_count * 2 + 10))]]
            for fut in as_completed(futures):
                if cancel_event and cancel_event.is_set():
                    break
                if extracted_count >= target_count:
                    break
                try:
                    item = fut.result()
                    if item and float(item.get('price', 0)) > 0.1:
                        _write_item(
                            item['name_ar'], item['name_en'], item['sku'],
                            item['price'], item['old_price'], item['in_stock'], item['date_val'], item['url']
                        )
                except Exception:
                    pass

    # ── G. Fallback Generic & WooCommerce & Custom Platforms ──────────────────
    else:
        cand_items = []
        sm_candidates = [
            f"https://{domain}/product-sitemap.xml",
            f"https://{domain}/sitemap_ar.xml",
            f"https://{domain}/sitemap.xml"
        ]
        for sm_url in sm_candidates:
            try:
                req_sm = urllib.request.Request(sm_url, headers=BROWSER_HEADERS)
                with urllib.request.urlopen(req_sm, context=SSL_CTX, timeout=10) as r:
                    sm_txt = r.read().decode('utf-8', errors='ignore')
                urls_with_dates = re.findall(r'<url>(.*?)</url>', sm_txt, flags=re.DOTALL)
                for ub in urls_with_dates:
                    loc_m = re.search(r'<loc>(?:<!\[CDATA\[)?(https?://[^\]<]+)(?:\]\]>)?</loc>', ub)
                    if loc_m:
                        u = loc_m.group(1).strip()
                        # Skip shop landing, categories, and tags
                        if u.rstrip('/') in [f"https://{domain}", f"https://{domain}/shop", f"https://{domain}/ar", f"https://{domain}/en"]:
                            continue
                        if any(k in u for k in ['/category/', '/tag/', '/cart', '/checkout', '/my-account']):
                            continue
                        if any(k in u for k in ['/product/', '/item/', '/shop/', '.html']) or 'product-sitemap' in sm_url:
                            d_m = re.search(r'<lastmod>([^<]+)</lastmod>', ub)
                            lmod = d_m.group(1).strip() if d_m else ""
                            cand_items.append((u, lmod))
                if cand_items:
                    break
            except Exception:
                continue

        def _fetch_generic(tup):
            if cancel_event and cancel_event.is_set():
                return None
            u, date_val = tup
            try:
                time.sleep(0.08)
                qu = urllib.parse.quote(u, safe=':/?&=#')
                req_p = urllib.request.Request(qu, headers=BROWSER_HEADERS)
                with urllib.request.urlopen(req_p, context=SSL_CTX, timeout=8) as resp:
                    h_data = resp.read().decode('utf-8', errors='ignore')

                # 1. Try JSON-LD Product Schema
                ld = re.findall(r'<script\b[^>]*\btype=["\']application/ld\+json["\'][^>]*>(.*?)</script>', h_data, flags=re.DOTALL)
                for block in ld:
                    if 'Product' in block:
                        try:
                            d = json.loads(block)
                            graph = d.get('@graph', [d])
                            for it in graph:
                                if it.get('@type') == 'Product':
                                    raw_title = it.get('name', '')
                                    sku = it.get('sku') or ''
                                    offers = it.get('offers', {})
                                    if isinstance(offers, list) and offers:
                                        offers = offers[0]
                                    price = float(offers.get('price') or 0)
                                    is_in_stock = 'InStock' in str(offers.get('availability', ''))
                                    name_ar, name_en = split_bilingual_title(raw_title, u)
                                    if price > 0.1:
                                        return {
                                            'name_ar': name_ar, 'name_en': name_en, 'sku': sku,
                                            'price': price, 'old_price': 0.0, 'in_stock': is_in_stock,
                                            'date_val': date_val, 'url': u
                                        }
                        except Exception:
                            pass

                # 2. Fallback for WooCommerce & Custom HTML Stores (e.g. Beauty Cloud)
                og_t = re.search(r'property="og:title"\s+content="([^"]+)"', h_data)
                raw_t = og_t.group(1).strip() if og_t else ""
                raw_t = re.sub(r'\s*\|\s*Beauty\s*Cloud.*$', '', raw_t, flags=re.I)

                ins_p = re.search(r'<ins\b[^>]*>.*?([0-9]+(?:\.[0-9]+)?)', h_data, flags=re.DOTALL)
                price = 0.0
                if ins_p:
                    price = float(ins_p.group(1))
                else:
                    p_m = re.findall(r'woocommerce-Price-amount amount[^>]*>.*?([0-9\.]+)', h_data)
                    if p_m:
                        valid = [float(x) for x in p_m if float(x) > 0.1]
                        if valid: price = valid[0]

                del_p = re.search(r'<del\b[^>]*>.*?([0-9]+(?:\.[0-9]+)?)', h_data, flags=re.DOTALL)
                old_price = float(del_p.group(1)) if del_p else 0.0

                sku_m = re.search(r'class="sku">([^<]+)', h_data) or re.search(r'itemprop="sku">\s*([^<]+)', h_data)
                sku = sku_m.group(1).strip() if sku_m else ""

                in_stock = 'instock' in h_data.lower() or 'in stock' in h_data.lower()
                name_ar, name_en = split_bilingual_title(raw_t, u)

                if price > 0.1:
                    return {
                        'name_ar': name_ar, 'name_en': name_en, 'sku': sku,
                        'price': price, 'old_price': old_price, 'in_stock': in_stock,
                        'date_val': date_val, 'url': u
                    }
            except Exception:
                pass
            return None

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(_fetch_generic, it) for it in cand_items[:min(len(cand_items), max(50, target_count * 2 + 10))]]
            for fut in as_completed(futures):
                if cancel_event and cancel_event.is_set():
                    break
                if extracted_count >= target_count:
                    break
                try:
                    item = fut.result()
                    if item and item.get('price', 0) > 0.1:
                        _write_item(
                            item['name_ar'], item['name_en'], item['sku'],
                            item['price'], item['old_price'], item['in_stock'], item['date_val'], item['url']
                        )
                except Exception:
                    pass

    # Auto-adjust all 9 column widths
    ws.column_dimensions['A'].width = 38
    ws.column_dimensions['B'].width = 38
    ws.column_dimensions['C'].width = 20
    ws.column_dimensions['D'].width = 18
    ws.column_dimensions['E'].width = 18
    ws.column_dimensions['F'].width = 14
    ws.column_dimensions['G'].width = 16
    ws.column_dimensions['H'].width = 20
    ws.column_dimensions['I'].width = 22

    if extracted_count == 0:
        wb.close()
        if cutoff_date:
            return False, f"لم يتم العثور على أي منتجات مضافة أو محدثة في متجر {name} خلال آخر {days_limit} يوم (منذ {cutoff_date}).\n\n💡 يمكنك تجربة زيادة عدد الأيام (مثلاً 14 أو 30 يوماً) أو سحب الكتالوج العام.", None
        return False, f"تعذر استخراج منتجات من {name}. يرجى التحقق من اتصال الإنترنت أو تجربة متجر آخر.", None

    try:
        wb.save(output_path)
        wb.close()
        elapsed_t = round(time.time() - start_time, 1)
        if cutoff_date:
            summary = (
                f"🎉 تم استخراج أحدث منتجات {name} بنجاح!\n\n"
                f"• عدد المنتجات المضافة/المحدثة: {extracted_count} منتجاً\n"
                f"• الفترة الزمنية: آخر {days_limit} يوم (منذ {cutoff_date} وحتى اليوم)\n"
                f"• الوقت المستغرق: {elapsed_t} ثانية\n"
                f"• مسار الملف المحفوظ:\n{output_path}"
            )
        else:
            summary = (
                f"🎉 تم سحب كتالوج {name} بنجاح!\n\n"
                f"• إجمالي المنتجات المستخرجة: {extracted_count} منتجاً\n"
                f"• الوقت المستغرق: {elapsed_t} ثانية\n"
                f"• مسار الملف المحفوظ:\n{output_path}"
            )
        return True, summary, output_path
    except Exception as e:
        return False, f"تعذر حفظ ملف الإكسيل:\n{e}", None


