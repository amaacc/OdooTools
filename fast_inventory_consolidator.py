"""
FastInventory PC Consolidator — أداة دمج ومطابقة جرد أجهزة الهاندهيل المتعددة
شركة العسلي للتجارة — برمجة وتطوير: عبدالله الخطيب
"""

import os
import sys
import csv
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

try:
    from security import get_odoo_credentials
    import xmlrpc.client
    HAS_ODOO_LIBS = True
except ImportError:
    HAS_ODOO_LIBS = False


def fetch_odoo_stock_map(barcodes_list):
    """Fetches real-time system stock and standard prices from Odoo for a list of barcodes."""
    if not HAS_ODOO_LIBS or not barcodes_list:
        return {}

    try:
        url, db, user, pwd = get_odoo_credentials()
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        uid = common.authenticate(db, user, pwd, {})
        if not uid:
            return {}

        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        domain = [("barcode", "in", list(barcodes_list))]
        fields = ["id", "barcode", "default_code", "name", "product_name_arabic", "standard_price", "qty_available"]
        records = models.execute_kw(db, uid, pwd, "product.product", "search_read", [domain], {"fields": fields, "limit": len(barcodes_list) + 100})

        res_map = {}
        for r in records:
            bc = str(r.get("barcode", "")).strip()
            if bc:
                res_map[bc] = {
                    "code": str(r.get("default_code", "")).strip(),
                    "name_ar": str(r.get("product_name_arabic", "")).strip() or str(r.get("name", "")).strip(),
                    "name_en": str(r.get("name", "")).strip(),
                    "cost": float(r.get("standard_price", 0.0) or 0.0),
                    "system_qty": float(r.get("qty_available", 0.0) or 0.0)
                }
        return res_map
    except Exception as e:
        print(f"[Odoo Sync Warning] {e}")
        return {}


def consolidate_files(csv_filepaths, output_xlsx_path, use_odoo_live=True):
    consolidated = {}
    raw_scans = []
    all_barcodes = set()

    for fpath in csv_filepaths:
        dev_tag = os.path.splitext(os.path.basename(fpath))[0]
        try:
            with open(fpath, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                header = None
                for row in reader:
                    if not row or row[0].startswith("---") or row[0].startswith("تقرير"):
                        continue
                    if header is None:
                        header = [c.strip().lower() for c in row]
                        continue

                    # Parse row
                    bc = row[0].strip() if len(row) > 0 else ""
                    if not bc or "الباركود" in bc:
                        continue

                    code = row[1].strip() if len(row) > 1 else "-"
                    name_ar = row[2].strip() if len(row) > 2 else ""
                    name_en = row[3].strip() if len(row) > 3 else ""
                    try:
                        qty = float(row[4].strip()) if len(row) > 4 else 1.0
                    except ValueError:
                        qty = 1.0

                    all_barcodes.add(bc)
                    raw_scans.append({
                        "device": dev_tag,
                        "barcode": bc,
                        "code": code,
                        "name_ar": name_ar,
                        "qty": qty
                    })

                    if bc in consolidated:
                        consolidated[bc]["counted"] += qty
                        consolidated[bc]["device_breakdown"][dev_tag] = consolidated[bc]["device_breakdown"].get(dev_tag, 0.0) + qty
                    else:
                        consolidated[bc] = {
                            "barcode": bc,
                            "code": code,
                            "name_ar": name_ar,
                            "name_en": name_en,
                            "counted": qty,
                            "system_qty": 0.0,
                            "cost": 0.0,
                            "device_breakdown": {dev_tag: qty}
                        }
        except Exception as e:
            print(f"Error reading {fpath}: {e}")

    # Fetch live stock from Odoo if requested
    if use_odoo_live:
        odoo_data = fetch_odoo_stock_map(all_barcodes)
        for bc, item in consolidated.items():
            if bc in odoo_data:
                info = odoo_data[bc]
                item["system_qty"] = info["system_qty"]
                item["cost"] = info["cost"]
                if not item["name_ar"] or item["name_ar"] == "صنف يدوي":
                    item["name_ar"] = info["name_ar"]
                if not item["name_en"]:
                    item["name_en"] = info["name_en"]
                if item["code"] == "-":
                    item["code"] = info["code"]

    # Write Master XLSX
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "ملخص الفروقات النهائي"
    ws1.views.sheetView[0].rightToLeft = True

    # Styling
    header_fill = PatternFill(start_color="059669", end_color="059669", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    align_center = Alignment(horizontal="center", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")
    border_thin = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    headers1 = [
        "الباركود", "كود الصنف", "اسم المنتج بالعربي", "اسم المنتج بالإنجليزي",
        "الكمية المحصورة (الفعلي)", "رصيد النظام (Odoo)", "فرق الجرد",
        "سعر التكلفة", "قيمة الفرق (ر.س)", "توزيع الأجهزة والمناطق"
    ]
    ws1.append(headers1)
    for col_idx in range(1, len(headers1) + 1):
        cell = ws1.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align_center

    row_idx = 2
    for bc, item in consolidated.items():
        var_qty = item["counted"] - item["system_qty"]
        var_val = var_qty * item["cost"]
        breakdown_str = " | ".join([f"{dev}: {int(q) if q.is_integer() else q}" for dev, q in item["device_breakdown"].items()])

        row_data = [
            item["barcode"], item["code"], item["name_ar"], item["name_en"],
            item["counted"], item["system_qty"], var_qty,
            item["cost"], round(var_val, 2), breakdown_str
        ]
        ws1.append(row_data)

        # Highlight negative variance with light red, positive with light green
        var_cell = ws1.cell(row=row_idx, column=7)
        if var_qty < 0:
            var_cell.fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
            var_cell.font = Font(name="Segoe UI", color="DC2626", bold=True)
        elif var_qty > 0:
            var_cell.fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
            var_cell.font = Font(name="Segoe UI", color="16A34A", bold=True)

        row_idx += 1

    # Sheet 2: Raw Audit Scans
    ws2 = wb.create_sheet(title="سجل مسح الأجهزة التفصيلي")
    ws2.views.sheetView[0].rightToLeft = True
    headers2 = ["الجهاز / الملف", "الباركود", "كود الصنف", "اسم المنتج", "الكمية الممسوحة"]
    ws2.append(headers2)
    for col_idx in range(1, len(headers2) + 1):
        cell = ws2.cell(row=1, column=col_idx)
        cell.fill = PatternFill(start_color="0284C7", end_color="0284C7", fill_type="solid")
        cell.font = header_font
        cell.alignment = align_center

    for r in raw_scans:
        ws2.append([r["device"], r["barcode"], r["code"], r["name_ar"], r["qty"]])

    # Adjust column widths
    for ws in [ws1, ws2]:
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 45)

    wb.save(output_xlsx_path)
    return len(consolidated), sum(c["counted"] for c in consolidated.values())


class ConsolidatorGui:
    def __init__(self, root):
        self.root = root
        self.root.title("دمج ومطابقة ملفات الجرد — شركة العسلي التجارية")
        self.root.geometry("640x520")
        self.file_paths = []

        # Style
        style = ttk.Style()
        style.theme_use("clam")

        lbl_title = tk.Label(root, text="🔀 دمج ومطابقة جرد أجهزة الهاندهيل المتعددة", font=("Segoe UI", 14, "bold"), fg="#059669")
        lbl_title.pack(pady=(15, 6))

        lbl_desc = tk.Label(root, text="اختر ملفات CSV أو Excel المصدرة من أجهزة FastInventory لدمجها ومقارنة الفروقات مع Odoo", font=("Segoe UI", 10), fg="#475569")
        lbl_desc.pack(pady=(0, 12))

        btn_pick = tk.Button(root, text="➕ اختيار ملفات الجرد", font=("Segoe UI", 11, "bold"), bg="#0284C7", fg="white", padx=15, pady=6, command=self.pick_files)
        btn_pick.pack()

        self.listbox = tk.Listbox(root, height=9, font=("Segoe UI", 10))
        self.listbox.pack(fill="x", padx=25, pady=10)

        self.var_odoo = tk.BooleanVar(value=True)
        chk_odoo = tk.Checkbutton(root, text="🌐 مطابقة الفروقات وجلب رصيد وتكلفة الأصناف مباشرة من سيرفر Odoo", variable=self.var_odoo, font=("Segoe UI", 10, "bold"))
        chk_odoo.pack(pady=4)

        btn_run = tk.Button(root, text="🚀 دمج وإنشاء تقرير الإكسيل الموحد", font=("Segoe UI", 12, "bold"), bg="#059669", fg="white", padx=20, pady=8, command=self.run_merge)
        btn_run.pack(pady=12)

        self.lbl_status = tk.Label(root, text="", font=("Segoe UI", 10, "bold"), fg="#0F766E")
        self.lbl_status.pack(pady=4)

    def pick_files(self):
        paths = filedialog.askopenfilenames(
            title="اختر ملفات الجرد",
            filetypes=[("Inventory CSV", "*.csv"), ("All Files", "*.*")]
        )
        if paths:
            self.file_paths = list(paths)
            self.listbox.delete(0, tk.END)
            for p in self.file_paths:
                self.listbox.insert(tk.END, f"📄 {os.path.basename(p)}")

    def run_merge(self):
        if not self.file_paths:
            messagebox.showwarning("تنبيه", "يرجى اختيار ملفات الجرد أولاً")
            return

        save_path = filedialog.asksaveasfilename(
            title="حفظ تقرير الإكسيل المدمج",
            defaultextension=".xlsx",
            filetypes=[("Excel Workbook", "*.xlsx")],
            initialfile=f"Master_Consolidated_Inventory_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        )
        if not save_path:
            return

        self.lbl_status.config(text="⏳ جاري دمج ومطابقة الملفات وجلب البيانات من Odoo...")
        self.root.update()

        try:
            items_count, units_count = consolidate_files(self.file_paths, save_path, use_odoo_live=self.var_odoo.get())
            self.lbl_status.config(text=f"✅ تم إنشاء التقرير بنجاح: {items_count} صنف ({int(units_count)} حبة)")
            messagebox.showinfo("تم بنجاح", f"✅ تم دمج {len(self.file_paths)} ملفات بنجاح!\n\nإجمالي الأصناف: {items_count}\nإجمالي الحبات المحصورة: {int(units_count)}\n\nتم حفظ التقرير في:\n{save_path}")
            os.startfile(save_path)
        except Exception as e:
            self.lbl_status.config(text=f"❌ خطأ: {e}")
            messagebox.showerror("خطأ", f"حدث خطأ أثناء الدمج:\n{e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = ConsolidatorGui(root)
    root.mainloop()
