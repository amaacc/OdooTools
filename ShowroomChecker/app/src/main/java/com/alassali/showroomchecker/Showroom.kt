package com.alassali.showroomchecker

/**
 * Data model for an Al-Assali showroom / branch.
 */
data class Showroom(
    val id: Int,              // Warehouse ID in Odoo (e.g. 48, 53)
    val name: String,         // Display Name (e.g. "معرض الصفاء")
    val code: String,         // Short branch code (e.g. "101", "106")
    val locationId: Int,      // Stock Location ID (lot_stock_id, e.g. 336)
    val posConfigIds: List<Int> = emptyList() // POS config IDs belonging to this warehouse
) {
    override fun toString(): String {
        return if (code.isNotBlank()) "[$code] $name" else name
    }
}

/**
 * Data model for a scanned product, its stock, sales, and calculated net needs.
 */
data class ProductNeedDetails(
    val id: Int,
    val defaultCode: String,
    val barcode: String,
    val nameEn: String,
    val nameAr: String,
    val uom: String,
    val stockQty: Double,
    val soldQty: Double,
    val monthlyRate: Double,
    val targetNeed: Double,
    val needMonths: Int,
    val netNeed: Double,
    val periodDays: Int,
    val periodLabel: String,
    val timestamp: Long = System.currentTimeMillis()
)

typealias ProductStock = ProductNeedDetails

