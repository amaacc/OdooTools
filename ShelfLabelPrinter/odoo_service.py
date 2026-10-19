"""
خدمة الاتصال بنظام Odoo لجلب بيانات الأصناف والأسعار
تعتمد بروتوكول JSON-RPC عالي السرعة والتشفير المعتمد في الشركة
"""
import sys
import os
import json
import urllib.request
from typing import Optional, List, Dict

# استدعاء بيانات الاعتماد المشفرة من نظام الأمان (Fernet AES)
from security import get_odoo_credentials

from label_model import LabelItem

class OdooService:
    def __init__(self):
        self.url, self.db, self.user, self.pwd = get_odoo_credentials()
        self.endpoint = f"{self.url}/jsonrpc" if not self.url.endswith("/") else f"{self.url}jsonrpc"
        self.uid = None

    def _call(self, service: str, method: str, args: list) -> any:
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": service,
                "method": method,
                "args": args
            },
            "id": 1
        }
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "error" in data:
                err_msg = data["error"].get("data", {}).get("message") or data["error"].get("message", "Odoo Error")
                raise RuntimeError(err_msg)
            return data.get("result")

    def authenticate(self) -> bool:
        if self.uid:
            return True
        try:
            res = self._call("common", "authenticate", [self.db, self.user, self.pwd, {}])
            if isinstance(res, int) and res > 0:
                self.uid = res
                return True
            return False
        except Exception as e:
            print(f"[OdooService] Auth Error: {e}")
            return False

    def get_product_by_barcode(self, barcode: str) -> Optional[LabelItem]:
        clean = barcode.strip()
        if not clean:
            return None
        if not self.authenticate():
            return None

        try:
            # 1. البحث في product.product
            fields = ["id", "name", "product_name_arabic", "barcode", "list_price"]
            res = self._call("object", "execute_kw", [
                self.db, self.uid, self.pwd,
                "product.product", "search_read",
                [[["barcode", "=", clean]]],
                {"fields": fields, "limit": 1}
            ])

            if res and len(res) > 0:
                p = res[0]
                return LabelItem(
                    barcode=clean,
                    name_ar=(p.get("product_name_arabic") or p.get("name") or "").strip(),
                    name_en=(p.get("name") or "").strip(),
                    price=float(p.get("list_price") or 0.0),
                    product_id=p.get("id", 0)
                )

            # 2. البحث في باركودات التعبئة product.packaging
            pkg_res = self._call("object", "execute_kw", [
                self.db, self.uid, self.pwd,
                "product.packaging", "search_read",
                [[["barcode", "=", clean]]],
                {"fields": ["product_id"], "limit": 1}
            ])
            if pkg_res and len(pkg_res) > 0:
                prod_id = pkg_res[0].get("product_id")
                if isinstance(prod_id, (list, tuple)) and len(prod_id) > 0:
                    prod_id = prod_id[0]
                if prod_id:
                    p_res = self._call("object", "execute_kw", [
                        self.db, self.uid, self.pwd,
                        "product.product", "read",
                        [prod_id],
                        {"fields": fields}
                    ])
                    if p_res and len(p_res) > 0:
                        p = p_res[0]
                        return LabelItem(
                            barcode=clean,
                            name_ar=(p.get("product_name_arabic") or p.get("name") or "").strip(),
                            name_en=(p.get("name") or "").strip(),
                            price=float(p.get("list_price") or 0.0),
                            product_id=p.get("id", 0)
                        )

            return None
        except Exception as e:
            print(f"[OdooService] Lookup error for {clean}: {e}")
            return None

    def get_products_bulk(self, barcodes: List[str]) -> List[LabelItem]:
        """جلب مجموعة باركودات دفعة واحدة بسرعة فائقة"""
        if not self.authenticate():
            return []
        clean_list = [b.strip() for b in barcodes if b.strip()]
        if not clean_list:
            return []

        results: Dict[str, LabelItem] = {}
        fields = ["id", "name", "product_name_arabic", "barcode", "list_price"]

        try:
            # تقسيم إلى دفعات من 100 لتفادي كبر الطلب
            batch_size = 100
            for i in range(0, len(clean_list), batch_size):
                chunk = clean_list[i:i + batch_size]
                res = self._call("object", "execute_kw", [
                    self.db, self.uid, self.pwd,
                    "product.product", "search_read",
                    [[["barcode", "in", chunk]]],
                    {"fields": fields}
                ])
                if res:
                    for p in res:
                        bc = (p.get("barcode") or "").strip()
                        if bc and bc not in results:
                            results[bc] = LabelItem(
                                barcode=bc,
                                name_ar=(p.get("product_name_arabic") or p.get("name") or "").strip(),
                                name_en=(p.get("name") or "").strip(),
                                price=float(p.get("list_price") or 0.0),
                                product_id=p.get("id", 0)
                            )

            # فحص الباركودات الناقصة (قد تكون باركودات تعبئة)
            missing = [bc for bc in clean_list if bc not in results]
            for m in missing:
                single = self.get_product_by_barcode(m)
                if single:
                    results[m] = single

        except Exception as e:
            print(f"[OdooService] Bulk error: {e}")

        # إعادة النتائج بنفس ترتيب القائمة المطلوبة
        ordered = []
        for bc in clean_list:
            if bc in results:
                ordered.append(results[bc])
            else:
                # صنف غير موجود في Odoo
                ordered.append(LabelItem(
                    barcode=bc,
                    name_ar="صنف غير معرّف في Odoo",
                    name_en="Unknown Item",
                    price=0.0
                ))
        return ordered
