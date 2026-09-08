import os
import sys
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from licensing import generate_license_key, _MASTER_PASS

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("green")

class KeygenApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("أداة توليد مفاتيح التفعيل - عبدالله الخطيب")
        self.geometry("600x420")
        self.minsize(550, 380)

        self.setup_ui()

    def setup_ui(self):
        # Header
        header = ctk.CTkFrame(self, corner_radius=10, fg_color=("#14532D", "#064E3B"))
        header.pack(fill="x", padx=15, pady=12)

        ctk.CTkLabel(
            header,
            text="🔑 أداة ترخيص وتفعيل نظام تقارير Odoo",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color="#86EFAC"
        ).pack(side="right", padx=15, pady=10)

        ctk.CTkLabel(
            header,
            text="خاصة بـ: عبدالله الخطيب",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#D1FAE5"
        ).pack(side="left", padx=15, pady=10)

        # Body
        body = ctk.CTkFrame(self, corner_radius=10)
        body.pack(fill="both", expand=True, padx=15, pady=(0, 12))

        ctk.CTkLabel(
            body,
            text="أدخل معرّف الجهاز (Machine ID) الخاص بالموظف:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
        ).pack(anchor="e", padx=20, pady=(15, 6))

        self.mid_entry = ctk.CTkEntry(
            body,
            placeholder_text="مثال: B575-D008-319B-29E5",
            font=ctk.CTkFont(family="Consolas", size=15),
            height=40
        )
        self.mid_entry.pack(fill="x", padx=20, pady=(0, 10))

        # Generate Button
        self.btn_gen = ctk.CTkButton(
            body,
            text="⚡ توليد مفتاح التفعيل للجهاز",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            height=40,
            command=self.generate_key
        )
        self.btn_gen.pack(fill="x", padx=20, pady=6)

        # Result Frame
        res_frame = ctk.CTkFrame(body, fg_color=("#1E293B", "#0F172A"), corner_radius=8)
        res_frame.pack(fill="x", padx=20, pady=12)

        ctk.CTkLabel(
            res_frame,
            text="مفتاح التفعيل الخاص بالجهاز (Activation Key):",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#94A3B8"
        ).pack(anchor="e", padx=15, pady=(8, 2))

        self.key_display = ctk.CTkEntry(
            res_frame,
            font=ctk.CTkFont(family="Consolas", size=16, weight="bold"),
            text_color="#4ADE80",
            justify="center",
            height=40
        )
        self.key_display.pack(fill="x", padx=15, pady=(0, 8))

        btn_copy = ctk.CTkButton(
            res_frame,
            text="📋 نسخ المفتاح لإرساله للموظف",
            fg_color="#0F766E",
            hover_color="#115E59",
            height=32,
            command=self.copy_key
        )
        btn_copy.pack(pady=(0, 10))

    def generate_key(self):
        raw_mid = self.mid_entry.get().strip().upper()
        if not raw_mid:
            messagebox.showwarning("تنبيه", "يرجى إدخال معرّف الجهاز (Machine ID) أولاً.")
            return

        key = generate_license_key(raw_mid)
        self.key_display.delete(0, "end")
        self.key_display.insert(0, key)

    def copy_key(self):
        k = self.key_display.get().strip()
        if k:
            self.clipboard_clear()
            self.clipboard_append(k)
            messagebox.showinfo("تم النسخ", f"تم نسخ المفتاح للحافظة بنجاح:\n\n{k}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # CLI Mode: python keygen.py <MACHINE_ID>
        input_mid = sys.argv[1].strip().upper()
        print(f"Machine ID     : {input_mid}")
        print(f"Activation Key : {generate_license_key(input_mid)}")
        print(f"Master Password: {_MASTER_PASS}")
    else:
        app = KeygenApp()
        app.mainloop()
