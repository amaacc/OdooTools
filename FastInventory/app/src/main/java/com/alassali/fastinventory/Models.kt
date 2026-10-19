package com.alassali.fastinventory

import java.io.Serializable

data class ProductItem(
    val id: Int,
    val barcode: String,
    val defaultCode: String,
    val nameAr: String,
    val nameEn: String,
    val standardPrice: Double,
    val listPrice: Double,
    val systemQty: Double = 0.0
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
    val packagingName: String = ""
) : Serializable

data class InventorySession(
    val id: Long = 0,
    val name: String,
    val zoneName: String,
    val createdAt: String,
    val status: String = "active" // active, completed
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
    val zoneCounts: MutableMap<String, Double> = mutableMapOf()
) : Serializable {
    val varianceQty: Double
        get() = countedQty - systemQty

    val varianceValue: Double
        get() = varianceQty * costPrice
}
