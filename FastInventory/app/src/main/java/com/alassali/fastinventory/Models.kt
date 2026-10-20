package com.alassali.fastinventory

import java.io.Serializable

data class WarehouseItem(
    val id: Int,
    val name: String,
    val code: String,
    val lotStockId: Int? = null
) : Serializable {
    override fun toString(): String = if (code.isNotBlank()) "[$code] $name" else name
}

data class ProductItem(
    val id: Int,
    val barcode: String,
    val defaultCode: String,
    val nameAr: String,
    val nameEn: String,
    val standardPrice: Double,
    val listPrice: Double,
    val systemQty: Double = 0.0,
    val warehouseId: Int = 0,
    val warehouseName: String = ""
) : Serializable

data class PackagingItem(
    val id: Int,
    val barcode: String,
    val productId: Int,
    val productBarcode: String,
    val name: String,
    val qty: Double
) : Serializable

data class ScanRecord(
    val id: Long = 0,
    val sessionId: Long,
    val barcode: String,
    val defaultCode: String,
    val nameAr: String,
    val nameEn: String,
    val qty: Double,
    val zoneName: String,
    val deviceId: String,
    val deviceName: String,
    val timestamp: String,
    val isPackaging: Boolean = false,
    val packagingQty: Double = 1.0,
    val packagingName: String = "",
    val scanMethod: String = "SCAN", // SCAN (laser/camera), MANUAL (typed), OVERRIDE
    val shelfSeq: Int = 1,           // 1, 2, 3... order on shelf
    val shelfLevel: String = ""      // e.g. علوي, أوسط, سفلي
) : Serializable

data class InventorySession(
    val id: Long = 0,
    val name: String,
    val zoneName: String,
    val createdAt: String,
    val status: String = "active", // active, completed
    val warehouseId: Int = 0,
    val warehouseCode: String = "",
    val warehouseName: String = "",
    val closedAt: String = ""
) : Serializable

data class ShelfAuditItem(
    val barcode: String,
    val defaultCode: String,
    val nameAr: String,
    val nameEn: String,
    val countedInZone: Double,
    val totalCountedInSession: Double,
    val systemQty: Double,
    val costPrice: Double,
    val lastScanTime: String = "",
    val lastScanMethod: String = "SCAN",
    val isUnknown: Boolean = false
) : Serializable {
    val varianceInSession: Double
        get() = totalCountedInSession - systemQty

    val varianceValue: Double
        get() = varianceInSession * costPrice
}

data class ZoneSummary(
    val zoneName: String,
    val itemsCount: Int,
    val totalUnits: Double
) : Serializable

data class ConsolidatedItem(
    val barcode: String,
    val defaultCode: String,
    val nameAr: String,
    val nameEn: String,
    var countedQty: Double,
    var systemQty: Double,
    val costPrice: Double,
    val listPrice: Double,
    val deviceCounts: MutableMap<String, Double> = mutableMapOf(),
    val zoneCounts: MutableMap<String, Double> = mutableMapOf(),
    var scanMethod: String = "SCAN"
) : Serializable {
    val varianceQty: Double
        get() = countedQty - systemQty

    val varianceValue: Double
        get() = varianceQty * costPrice
}

data class InventoryReportMetadata(
    val sessionName: String,
    val sessionId: Long = 0,
    val warehouseId: Int = 0,
    val warehouseCode: String = "",
    val warehouseName: String = "",
    val lotStockId: Int = 0,
    val zoneName: String = "",
    val deviceName: String = "",
    val createdAt: String = "",
    val exportTimestamp: String = "",
    val isConsolidated: Boolean = false,
    val deviceList: List<String> = emptyList()
) : Serializable
