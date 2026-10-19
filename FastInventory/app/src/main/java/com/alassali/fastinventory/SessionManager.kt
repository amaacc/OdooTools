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

    init {
        currentZone = settings.getDefaultZone()
        currentSession = db.getOrOpenActiveSession(settings.getActiveSessionName(), currentZone)
    }

    fun updateZone(newZone: String) {
        val clean = newZone.trim().ifBlank { "الرف العام" }
        currentZone = clean
        settings.setDefaultZone(clean)
    }

    fun updateSessionName(newName: String) {
        val clean = newName.trim().ifBlank { "جلسة جرد" }
        settings.setActiveSessionName(clean)
        currentSession = db.getOrOpenActiveSession(clean, currentZone)
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
        val isUnknown: Boolean
    )

    /**
     * Processes a scanned barcode during the session.
     * Auto-detects cartons and increments by carton quantity.
     * Records the scan instantly in SQLite.
     */
    fun recordScan(barcode: String, customQty: Double? = null): ScanResult {
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
            packagingName = packagingName
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
            isUnknown = isUnknown
        )
    }

    fun addManualDelta(barcode: String, delta: Double): Double {
        if (delta == 0.0) return db.getItemCountInZone(currentSession.id, barcode, currentZone)
        recordScan(barcode, delta)
        return db.getItemCountInZone(currentSession.id, barcode, currentZone)
    }

    fun setExactQuantity(barcode: String, targetQty: Double) {
        db.setExactItemQuantity(currentSession.id, barcode, currentZone, targetQty)
    }

    fun deleteItem(barcode: String) {
        db.deleteItemFromSession(currentSession.id, barcode)
    }

    fun clearActiveSession() {
        db.clearSession(currentSession.id)
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
