"""
نموذج بيانات ملصق الصنف (LabelItem)
"""
from dataclasses import dataclass

@dataclass
class LabelItem:
    barcode: str
    name_ar: str
    name_en: str
    price: float  # السعر من list_price شامل الضريبة
    quantity: int = 1
    product_id: int = 0

    @property
    def formatted_price(self) -> str:
        return f"{self.price:.2f}"
