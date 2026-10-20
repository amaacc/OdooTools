package com.alassali.fastinventory

import android.content.Context
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class SessionManager(private val context: Context) {

    private val db = InventoryDatabase(context)
    private val settings = SettingsManager(context)

    var currentSession: InventorySession
        private set

    var currentZone: String
        private set

    var currentShelfLevel: String = ""

    init {
        currentZone = settings.getDefaultZone()
        currentSession = db.getOrOpenActiveSession(
            name = settings.getActiveSessionName(),
            defaultZone = currentZone,
            warehouseId = settings.getSelectedWarehouseId(),
            warehouseCode = settings.getSelectedWarehouseCode(),
            warehouseName = settings.getSelectedWarehouseName()
        )
    }

    fun reloadActiveSession() {
        currentZone = settings.getDefaultZone()
        currentSession = db.getOrOpenActiveSession(
            name = settings.getActiveSessionName(),
            defaultZone = currentZone,
            warehouseId = settings.getSelectedWarehouseId(),
            warehouseCode = settings.getSelectedWarehouseCode(),
            warehouseName = settings.getSelectedWarehouseName()
        )
    }

    fun updateZone(newZone: String, level: String = "") {
        val clean = newZone.trim().ifBlank { "الرف العام" }
        currentZone = clean
        currentShelfLevel = level.trim()
        settings.setDefaultZone(clean)
    }

    fun switchSession(sessionId: Long) {
        val switched = db.switchActiveSession(sessionId)
        if (switched != null) {
            currentSession = switched
            currentZone = switched.zoneName.ifBlank { "الرف العام" }
            settings.setActiveSessionName(switched.name)
            settings.setDefaultZone(currentZone)
        }
    }

    fun createNewSession(
        name: String,
        warehouseId: Int,
        warehouseCode: String,
        warehouseName: String,
        defaultZone: String
    ): InventorySession {
        val newSession = db.createNewSession(name, warehouseId, warehouseCode, warehouseName, defaultZone)
        currentSession = newSession
        currentZone = defaultZone.ifBlank { "الرف العام" }
        settings.setActiveSessionName(newSession.name)
        settings.setDefaultZone(currentZone)
        return newSession
    }

    data class ScanResult(
        val barcode: String,
        val defaultCode: String,
        val nameAr: String,
        val nameEn: String,
        val isPackaging: Boolean,
        val packagingName: String,
        val packagingQty: Double,
        val addedQty: Double,
        val totalCountedInZone: Double,
        val totalCountedInSession: Double,
        val isUnknown: Boolean,
        val shelfSeq: Int,
        val scanMethod: String
    )

    /**
     * Processes a scanned or manually entered barcode during the session.
     * Records exact barcode string, shelf sequence order, and entry method.
     */
    fun recordScan(
        barcode: String,
        customQty: Double? = null,
        scanMethod: String = "SCAN", // SCAN, MANUAL, OVERRIDE
        shelfLevel: String = currentShelfLevel
    ): ScanResult {
        val cleanBarcode = barcode.trim()
        val (product, packaging) = db.lookupBarcode(cleanBarcode)

        val isPackaging = packaging != null
        val packagingName = packaging?.name ?: ""
        val packagingQty = packaging?.qty ?: 1.0

        val addedQty = customQty ?: if (isPackaging) packagingQty else 1.0

        val resolvedBarcode = product?.barcode?.ifBlank { cleanBarcode } ?: cleanBarcode
        val defaultCode = product?.defaultCode ?: "-"
        val nameAr = product?.nameAr ?: "صنف غير معرّف (${cleanBarcode})"
        val nameEn = product?.nameEn ?: ""
        val isUnknown = product == null

        val nextSeq = db.getNextShelfSequence(currentSession.id, currentZone)
        val now = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())

        val record = ScanRecord(
            sessionId = currentSession.id,
            barcode = resolvedBarcode,
            defaultCode = defaultCode,
            nameAr = nameAr,
            nameEn = nameEn,
            qty = addedQty,
            zoneName = currentZone,
            deviceId = LicenseManager.getDeviceId(context),
            deviceName = settings.getDeviceName(),
            timestamp = now,
            isPackaging = isPackaging,
            packagingQty = packagingQty,
            packagingName = packagingName,
            scanMethod = scanMethod,
            shelfSeq = nextSeq,
            shelfLevel = shelfLevel
        )

        db.addScan(record)

        val totalInZone = db.getItemCountInZone(currentSession.id, resolvedBarcode, currentZone)
        val totalInSession = db.getItemCountInSession(currentSession.id, resolvedBarcode)

        return ScanResult(
            barcode = resolvedBarcode,
            defaultCode = defaultCode,
            nameAr = nameAr,
            nameEn = nameEn,
            isPackaging = isPackaging,
            packagingName = packagingName,
            packagingQty = packagingQty,
            addedQty = addedQty,
            totalCountedInZone = totalInZone,
            totalCountedInSession = totalInSession,
            isUnknown = isUnknown,
            shelfSeq = nextSeq,
            scanMethod = scanMethod
        )
    }

    fun addManualDelta(barcode: String, delta: Double): Double {
        if (delta == 0.0) return db.getItemCountInZone(currentSession.id, barcode, currentZone)
        recordScan(barcode = barcode, customQty = delta, scanMethod = "OVERRIDE")
        return db.getItemCountInZone(currentSession.id, barcode, currentZone)
    }

    fun setExactQuantity(barcode: String, targetQty: Double) {
        db.setExactItemQuantity(currentSession.id, barcode, currentZone, targetQty)
    }

    fun deleteItem(barcode: String) {
        db.deleteItemFromSession(currentSession.id, barcode)
    }

    fun getSessionSummary(): Pair<Int, Double> {
        return db.getSessionSummary(currentSession.id)
    }

    fun getAggregatedItems(): List<ScanRecord> {
        return db.getAggregatedSessionItems(currentSession.id)
    }

    fun getAllRawScans(): List<ScanRecord> {
        return db.getAllScansForSession(currentSession.id)
    }
}
