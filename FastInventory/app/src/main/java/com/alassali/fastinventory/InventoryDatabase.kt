package com.alassali.fastinventory

import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class InventoryDatabase(context: Context) : SQLiteOpenHelper(context, DATABASE_NAME, null, DATABASE_VERSION) {

    companion object {
        const val DATABASE_NAME = "fast_inventory.db"
        const val DATABASE_VERSION = 2

        const val TABLE_PRODUCTS = "products"
        const val TABLE_PACKAGINGS = "packagings"
        const val TABLE_SCANS = "scan_records"
        const val TABLE_SESSIONS = "sessions"
    }

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("""
            CREATE TABLE $TABLE_PRODUCTS (
                id INTEGER PRIMARY KEY,
                barcode TEXT,
                default_code TEXT,
                name_ar TEXT,
                name_en TEXT,
                standard_price REAL,
                list_price REAL,
                system_qty REAL DEFAULT 0.0,
                warehouse_id INTEGER DEFAULT 0,
                warehouse_name TEXT DEFAULT ''
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX idx_products_barcode ON $TABLE_PRODUCTS(barcode)")
        db.execSQL("CREATE INDEX idx_products_code ON $TABLE_PRODUCTS(default_code)")

        db.execSQL("""
            CREATE TABLE $TABLE_PACKAGINGS (
                id INTEGER PRIMARY KEY,
                barcode TEXT,
                product_id INTEGER,
                product_barcode TEXT,
                name TEXT,
                qty REAL
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX idx_packagings_barcode ON $TABLE_PACKAGINGS(barcode)")

        db.execSQL("""
            CREATE TABLE $TABLE_SCANS (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                barcode TEXT,
                default_code TEXT,
                name_ar TEXT,
                name_en TEXT,
                qty REAL,
                zone_name TEXT,
                device_id TEXT,
                device_name TEXT,
                timestamp TEXT,
                is_packaging INTEGER DEFAULT 0,
                packaging_qty REAL DEFAULT 1.0,
                packaging_name TEXT DEFAULT '',
                scan_method TEXT DEFAULT 'SCAN',
                shelf_seq INTEGER DEFAULT 1,
                shelf_level TEXT DEFAULT ''
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX idx_scans_session_barcode ON $TABLE_SCANS(session_id, barcode)")
        db.execSQL("CREATE INDEX idx_scans_session_zone ON $TABLE_SCANS(session_id, zone_name)")

        db.execSQL("""
            CREATE TABLE $TABLE_SESSIONS (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                zone_name TEXT,
                created_at TEXT,
                status TEXT DEFAULT 'active',
                warehouse_id INTEGER DEFAULT 0,
                warehouse_code TEXT DEFAULT '',
                warehouse_name TEXT DEFAULT '',
                closed_at TEXT DEFAULT ''
            )
        """.trimIndent())
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if (oldVersion < 2) {
            try { db.execSQL("ALTER TABLE $TABLE_SCANS ADD COLUMN scan_method TEXT DEFAULT 'SCAN'") } catch (e: Exception) {}
            try { db.execSQL("ALTER TABLE $TABLE_SCANS ADD COLUMN shelf_seq INTEGER DEFAULT 1") } catch (e: Exception) {}
            try { db.execSQL("ALTER TABLE $TABLE_SCANS ADD COLUMN shelf_level TEXT DEFAULT ''") } catch (e: Exception) {}
            try { db.execSQL("ALTER TABLE $TABLE_SESSIONS ADD COLUMN warehouse_id INTEGER DEFAULT 0") } catch (e: Exception) {}
            try { db.execSQL("ALTER TABLE $TABLE_SESSIONS ADD COLUMN warehouse_code TEXT DEFAULT ''") } catch (e: Exception) {}
            try { db.execSQL("ALTER TABLE $TABLE_SESSIONS ADD COLUMN warehouse_name TEXT DEFAULT ''") } catch (e: Exception) {}
            try { db.execSQL("ALTER TABLE $TABLE_SESSIONS ADD COLUMN closed_at TEXT DEFAULT ''") } catch (e: Exception) {}
            try { db.execSQL("ALTER TABLE $TABLE_PRODUCTS ADD COLUMN warehouse_id INTEGER DEFAULT 0") } catch (e: Exception) {}
            try { db.execSQL("ALTER TABLE $TABLE_PRODUCTS ADD COLUMN warehouse_name TEXT DEFAULT ''") } catch (e: Exception) {}
            try { db.execSQL("CREATE INDEX IF NOT EXISTS idx_scans_session_zone ON $TABLE_SCANS(session_id, zone_name)") } catch (e: Exception) {}
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Catalog Bulk Ingestion
    // ─────────────────────────────────────────────────────────────────────────
    fun insertProductsBatch(products: List<ProductItem>) {
        val db = writableDatabase
        db.beginTransaction()
        try {
            db.delete(TABLE_PRODUCTS, null, null)
            val stmt = db.compileStatement(
                "INSERT OR REPLACE INTO $TABLE_PRODUCTS (id, barcode, default_code, name_ar, name_en, standard_price, list_price, system_qty, warehouse_id, warehouse_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
            for (p in products) {
                stmt.bindLong(1, p.id.toLong())
                stmt.bindString(2, p.barcode)
                stmt.bindString(3, p.defaultCode)
                stmt.bindString(4, p.nameAr)
                stmt.bindString(5, p.nameEn)
                stmt.bindDouble(6, p.standardPrice)
                stmt.bindDouble(7, p.listPrice)
                stmt.bindDouble(8, p.systemQty)
                stmt.bindLong(9, p.warehouseId.toLong())
                stmt.bindString(10, p.warehouseName)
                stmt.executeInsert()
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    fun insertPackagingsBatch(packagings: List<PackagingItem>) {
        val db = writableDatabase
        db.beginTransaction()
        try {
            db.delete(TABLE_PACKAGINGS, null, null)
            val stmt = db.compileStatement(
                "INSERT OR REPLACE INTO $TABLE_PACKAGINGS (id, barcode, product_id, product_barcode, name, qty) VALUES (?, ?, ?, ?, ?, ?)"
            )
            for (pkg in packagings) {
                stmt.bindLong(1, pkg.id.toLong())
                stmt.bindString(2, pkg.barcode)
                stmt.bindLong(3, pkg.productId.toLong())
                stmt.bindString(4, pkg.productBarcode)
                stmt.bindString(5, pkg.name)
                stmt.bindDouble(6, pkg.qty)
                stmt.executeInsert()
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Fast Barcode Lookup (Exact String Match, Preserving Leading Zeros)
    // ─────────────────────────────────────────────────────────────────────────
    fun lookupBarcode(barcode: String): Pair<ProductItem?, PackagingItem?> {
        val clean = barcode.trim()
        if (clean.isEmpty()) return Pair(null, null)

        val db = readableDatabase

        // 1. Check if this barcode is a carton packaging
        var packaging: PackagingItem? = null
        val pkgCursor = db.rawQuery(
            "SELECT id, barcode, product_id, product_barcode, name, qty FROM $TABLE_PACKAGINGS WHERE barcode = ? LIMIT 1",
            arrayOf(clean)
        )
        if (pkgCursor.moveToFirst()) {
            packaging = PackagingItem(
                id = pkgCursor.getInt(0),
                barcode = pkgCursor.getString(1) ?: "",
                productId = pkgCursor.getInt(2),
                productBarcode = pkgCursor.getString(3) ?: "",
                name = pkgCursor.getString(4) ?: "",
                qty = pkgCursor.getDouble(5)
            )
        }
        pkgCursor.close()

        // 2. Query product by ID if packaging matched, or by barcode/code directly
        val product: ProductItem? = if (packaging != null && packaging.productId > 0) {
            getProductById(packaging.productId)
        } else {
            getProductByBarcodeOrCode(clean)
        }

        return Pair(product, packaging)
    }

    fun getProductById(productId: Int): ProductItem? {
        val db = readableDatabase
        val c = db.rawQuery(
            "SELECT id, barcode, default_code, name_ar, name_en, standard_price, list_price, system_qty, warehouse_id, warehouse_name FROM $TABLE_PRODUCTS WHERE id = ? LIMIT 1",
            arrayOf(productId.toString())
        )
        val p = if (c.moveToFirst()) mapProduct(c) else null
        c.close()
        return p
    }

    fun getProductByBarcodeOrCode(barcodeOrCode: String): ProductItem? {
        val clean = barcodeOrCode.trim()
        val db = readableDatabase
        val c = db.rawQuery(
            "SELECT id, barcode, default_code, name_ar, name_en, standard_price, list_price, system_qty, warehouse_id, warehouse_name FROM $TABLE_PRODUCTS WHERE barcode = ? OR default_code = ? LIMIT 1",
            arrayOf(clean, clean)
        )
        val p = if (c.moveToFirst()) mapProduct(c) else null
        c.close()
        return p
    }

    fun searchProducts(query: String, limit: Int = 30): List<ProductItem> {
        val q = query.trim()
        if (q.isBlank()) return emptyList()
        val db = readableDatabase
        val list = mutableListOf<ProductItem>()
        val pattern = "%$q%"
        val c = db.rawQuery(
            """
            SELECT id, barcode, default_code, name_ar, name_en, standard_price, list_price, system_qty, warehouse_id, warehouse_name
            FROM $TABLE_PRODUCTS
            WHERE barcode LIKE ? OR default_code LIKE ? OR name_ar LIKE ? OR name_en LIKE ?
            LIMIT ?
            """.trimIndent(),
            arrayOf(pattern, pattern, pattern, pattern, limit.toString())
        )
        while (c.moveToNext()) {
            list.add(mapProduct(c))
        }
        c.close()
        return list
    }

    private fun mapProduct(c: Cursor): ProductItem {
        return ProductItem(
            id = c.getInt(0),
            barcode = c.getString(1) ?: "",
            defaultCode = c.getString(2) ?: "",
            nameAr = c.getString(3) ?: "",
            nameEn = c.getString(4) ?: "",
            standardPrice = c.getDouble(5),
            listPrice = c.getDouble(6),
            systemQty = c.getDouble(7),
            warehouseId = c.getInt(8),
            warehouseName = c.getString(9) ?: ""
        )
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Inventory Sessions & Scan Records (Historical Sessions Retention)
    // ─────────────────────────────────────────────────────────────────────────
    fun getOrOpenActiveSession(
        name: String,
        defaultZone: String,
        warehouseId: Int = 0,
        warehouseCode: String = "",
        warehouseName: String = ""
    ): InventorySession {
        val db = writableDatabase
        val c = db.rawQuery(
            "SELECT id, name, zone_name, created_at, status, warehouse_id, warehouse_code, warehouse_name, closed_at FROM $TABLE_SESSIONS WHERE status = 'active' ORDER BY id DESC LIMIT 1",
            null
        )
        if (c.moveToFirst()) {
            val session = mapSession(c)
            c.close()
            return session
        }
        c.close()

        val now = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())
        val cv = ContentValues().apply {
            put("name", name)
            put("zone_name", defaultZone)
            put("created_at", now)
            put("status", "active")
            put("warehouse_id", warehouseId)
            put("warehouse_code", warehouseCode)
            put("warehouse_name", warehouseName)
            put("closed_at", "")
        }
        val id = db.insert(TABLE_SESSIONS, null, cv)
        return InventorySession(id, name, defaultZone, now, "active", warehouseId, warehouseCode, warehouseName, "")
    }

    fun getAllSessions(): List<InventorySession> {
        val db = readableDatabase
        val list = mutableListOf<InventorySession>()
        val c = db.rawQuery(
            "SELECT id, name, zone_name, created_at, status, warehouse_id, warehouse_code, warehouse_name, closed_at FROM $TABLE_SESSIONS ORDER BY id DESC",
            null
        )
        while (c.moveToNext()) {
            list.add(mapSession(c))
        }
        c.close()
        return list
    }

    fun getSessionById(sessionId: Long): InventorySession? {
        val db = readableDatabase
        val c = db.rawQuery(
            "SELECT id, name, zone_name, created_at, status, warehouse_id, warehouse_code, warehouse_name, closed_at FROM $TABLE_SESSIONS WHERE id = ? LIMIT 1",
            arrayOf(sessionId.toString())
        )
        val s = if (c.moveToFirst()) mapSession(c) else null
        c.close()
        return s
    }

    fun createNewSession(
        name: String,
        warehouseId: Int,
        warehouseCode: String,
        warehouseName: String,
        defaultZone: String
    ): InventorySession {
        val db = writableDatabase
        // Mark previous active sessions as completed to keep them safe
        db.execSQL("UPDATE $TABLE_SESSIONS SET status = 'completed' WHERE status = 'active'")

        val now = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())
        val cv = ContentValues().apply {
            put("name", name)
            put("zone_name", defaultZone)
            put("created_at", now)
            put("status", "active")
            put("warehouse_id", warehouseId)
            put("warehouse_code", warehouseCode)
            put("warehouse_name", warehouseName)
            put("closed_at", "")
        }
        val id = db.insert(TABLE_SESSIONS, null, cv)
        return InventorySession(id, name, defaultZone, now, "active", warehouseId, warehouseCode, warehouseName, "")
    }

    fun switchActiveSession(sessionId: Long): InventorySession? {
        val db = writableDatabase
        db.execSQL("UPDATE $TABLE_SESSIONS SET status = 'completed' WHERE status = 'active'")
        db.execSQL("UPDATE $TABLE_SESSIONS SET status = 'active' WHERE id = ?", arrayOf(sessionId.toString()))
        return getSessionById(sessionId)
    }

    fun closeSession(sessionId: Long) {
        val db = writableDatabase
        val now = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())
        val cv = ContentValues().apply {
            put("status", "completed")
            put("closed_at", now)
        }
        db.update(TABLE_SESSIONS, cv, "id = ?", arrayOf(sessionId.toString()))
    }

    fun deleteSessionWithConfirmation(sessionId: Long): Boolean {
        val db = writableDatabase
        db.beginTransaction()
        try {
            db.delete(TABLE_SCANS, "session_id = ?", arrayOf(sessionId.toString()))
            db.delete(TABLE_SESSIONS, "id = ?", arrayOf(sessionId.toString()))
            db.setTransactionSuccessful()
            return true
        } catch (e: Exception) {
            return false
        } finally {
            db.endTransaction()
        }
    }

    private fun mapSession(c: Cursor): InventorySession {
        return InventorySession(
            id = c.getLong(0),
            name = c.getString(1) ?: "",
            zoneName = c.getString(2) ?: "",
            createdAt = c.getString(3) ?: "",
            status = c.getString(4) ?: "active",
            warehouseId = c.getInt(5),
            warehouseCode = c.getString(6) ?: "",
            warehouseName = c.getString(7) ?: "",
            closedAt = c.getString(8) ?: ""
        )
    }

    /**
     * Calculates the next physical sequence number for an item scanned in a specific zone/shelf.
     */
    fun getNextShelfSequence(sessionId: Long, zoneName: String): Int {
        val db = readableDatabase
        val c = db.rawQuery(
            "SELECT MAX(shelf_seq) FROM $TABLE_SCANS WHERE session_id = ? AND zone_name = ?",
            arrayOf(sessionId.toString(), zoneName)
        )
        val maxSeq = if (c.moveToFirst()) c.getInt(0) else 0
        c.close()
        return maxSeq + 1
    }

    fun addScan(record: ScanRecord): Long {
        val db = writableDatabase
        val cv = ContentValues().apply {
            put("session_id", record.sessionId)
            put("barcode", record.barcode)
            put("default_code", record.defaultCode)
            put("name_ar", record.nameAr)
            put("name_en", record.nameEn)
            put("qty", record.qty)
            put("zone_name", record.zoneName)
            put("device_id", record.deviceId)
            put("device_name", record.deviceName)
            put("timestamp", record.timestamp)
            put("is_packaging", if (record.isPackaging) 1 else 0)
            put("packaging_qty", record.packagingQty)
            put("packaging_name", record.packagingName)
            put("scan_method", record.scanMethod)
            put("shelf_seq", record.shelfSeq)
            put("shelf_level", record.shelfLevel)
        }
        return db.insert(TABLE_SCANS, null, cv)
    }

    fun getItemCountInZone(sessionId: Long, barcode: String, zoneName: String): Double {
        val db = readableDatabase
        val c = db.rawQuery(
            "SELECT SUM(qty) FROM $TABLE_SCANS WHERE session_id = ? AND barcode = ? AND zone_name = ?",
            arrayOf(sessionId.toString(), barcode, zoneName)
        )
        val sum = if (c.moveToFirst()) c.getDouble(0) else 0.0
        c.close()
        return sum
    }

    fun getItemCountInSession(sessionId: Long, barcode: String): Double {
        val db = readableDatabase
        val c = db.rawQuery(
            "SELECT SUM(qty) FROM $TABLE_SCANS WHERE session_id = ? AND barcode = ?",
            arrayOf(sessionId.toString(), barcode)
        )
        val sum = if (c.moveToFirst()) c.getDouble(0) else 0.0
        c.close()
        return sum
    }

    fun setExactItemQuantity(sessionId: Long, barcode: String, zoneName: String, targetTotalQty: Double) {
        val current = getItemCountInZone(sessionId, barcode, zoneName)
        val delta = targetTotalQty - current
        if (delta != 0.0) {
            val db = writableDatabase
            val now = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())
            val existing = getProductByBarcodeOrCode(barcode)
            val nextSeq = getNextShelfSequence(sessionId, zoneName)
            val cv = ContentValues().apply {
                put("session_id", sessionId)
                put("barcode", barcode)
                put("default_code", existing?.defaultCode ?: "")
                put("name_ar", existing?.nameAr ?: "صنف يدوي")
                put("name_en", existing?.nameEn ?: "")
                put("qty", delta)
                put("zone_name", zoneName)
                put("device_id", "")
                put("device_name", "تعديل كمية")
                put("timestamp", now)
                put("scan_method", "OVERRIDE")
                put("shelf_seq", nextSeq)
                put("shelf_level", "")
            }
            db.insert(TABLE_SCANS, null, cv)
        }
    }

    fun deleteItemFromSession(sessionId: Long, barcode: String) {
        val db = writableDatabase
        db.delete(TABLE_SCANS, "session_id = ? AND barcode = ?", arrayOf(sessionId.toString(), barcode))
    }

    fun clearSession(sessionId: Long) {
        val db = writableDatabase
        db.delete(TABLE_SCANS, "session_id = ?", arrayOf(sessionId.toString()))
    }

    fun getAggregatedSessionItems(sessionId: Long): List<ScanRecord> {
        val db = readableDatabase
        val list = mutableListOf<ScanRecord>()
        val query = """
            SELECT barcode, default_code, name_ar, name_en, SUM(qty) as total_qty, zone_name, MAX(timestamp), MAX(scan_method), MAX(shelf_seq), MAX(shelf_level)
            FROM $TABLE_SCANS
            WHERE session_id = ?
            GROUP BY barcode
            HAVING total_qty > 0
            ORDER BY id DESC
        """.trimIndent()

        val c = db.rawQuery(query, arrayOf(sessionId.toString()))
        while (c.moveToNext()) {
            list.add(
                ScanRecord(
                    sessionId = sessionId,
                    barcode = c.getString(0) ?: "",
                    defaultCode = c.getString(1) ?: "",
                    nameAr = c.getString(2) ?: "",
                    nameEn = c.getString(3) ?: "",
                    qty = c.getDouble(4),
                    zoneName = c.getString(5) ?: "",
                    deviceId = "",
                    deviceName = "",
                    timestamp = c.getString(6) ?: "",
                    scanMethod = c.getString(7) ?: "SCAN",
                    shelfSeq = c.getInt(8),
                    shelfLevel = c.getString(9) ?: ""
                )
            )
        }
        c.close()
        return list
    }

    fun getAllScansForSession(sessionId: Long): List<ScanRecord> {
        val db = readableDatabase
        val list = mutableListOf<ScanRecord>()
        val c = db.rawQuery(
            "SELECT id, session_id, barcode, default_code, name_ar, name_en, qty, zone_name, device_id, device_name, timestamp, is_packaging, packaging_qty, packaging_name, scan_method, shelf_seq, shelf_level FROM $TABLE_SCANS WHERE session_id = ? ORDER BY id ASC",
            arrayOf(sessionId.toString())
        )
        while (c.moveToNext()) {
            list.add(
                ScanRecord(
                    id = c.getLong(0),
                    sessionId = c.getLong(1),
                    barcode = c.getString(2) ?: "",
                    defaultCode = c.getString(3) ?: "",
                    nameAr = c.getString(4) ?: "",
                    nameEn = c.getString(5) ?: "",
                    qty = c.getDouble(6),
                    zoneName = c.getString(7) ?: "",
                    deviceId = c.getString(8) ?: "",
                    deviceName = c.getString(9) ?: "",
                    timestamp = c.getString(10) ?: "",
                    isPackaging = c.getInt(11) == 1,
                    packagingQty = c.getDouble(12),
                    packagingName = c.getString(13) ?: "",
                    scanMethod = c.getString(14) ?: "SCAN",
                    shelfSeq = c.getInt(15),
                    shelfLevel = c.getString(16) ?: ""
                )
            )
        }
        c.close()
        return list
    }

    fun getScansForZone(sessionId: Long, zoneName: String): List<ScanRecord> {
        val db = readableDatabase
        val list = mutableListOf<ScanRecord>()
        val c = db.rawQuery(
            "SELECT id, session_id, barcode, default_code, name_ar, name_en, qty, zone_name, device_id, device_name, timestamp, is_packaging, packaging_qty, packaging_name, scan_method, shelf_seq, shelf_level FROM $TABLE_SCANS WHERE session_id = ? AND zone_name = ? ORDER BY shelf_seq ASC, id ASC",
            arrayOf(sessionId.toString(), zoneName)
        )
        while (c.moveToNext()) {
            list.add(
                ScanRecord(
                    id = c.getLong(0),
                    sessionId = c.getLong(1),
                    barcode = c.getString(2) ?: "",
                    defaultCode = c.getString(3) ?: "",
                    nameAr = c.getString(4) ?: "",
                    nameEn = c.getString(5) ?: "",
                    qty = c.getDouble(6),
                    zoneName = c.getString(7) ?: "",
                    deviceId = c.getString(8) ?: "",
                    deviceName = c.getString(9) ?: "",
                    timestamp = c.getString(10) ?: "",
                    isPackaging = c.getInt(11) == 1,
                    packagingQty = c.getDouble(12),
                    packagingName = c.getString(13) ?: "",
                    scanMethod = c.getString(14) ?: "SCAN",
                    shelfSeq = c.getInt(15),
                    shelfLevel = c.getString(16) ?: ""
                )
            )
        }
        c.close()
        return list
    }

    fun getZonesForSession(sessionId: Long): List<ZoneSummary> {
        val db = readableDatabase
        val list = mutableListOf<ZoneSummary>()
        val c = db.rawQuery(
            "SELECT zone_name, COUNT(DISTINCT barcode), SUM(qty) FROM $TABLE_SCANS WHERE session_id = ? GROUP BY zone_name ORDER BY zone_name ASC",
            arrayOf(sessionId.toString())
        )
        while (c.moveToNext()) {
            list.add(
                ZoneSummary(
                    zoneName = c.getString(0) ?: "",
                    itemsCount = c.getInt(1),
                    totalUnits = c.getDouble(2)
                )
            )
        }
        c.close()
        return list
    }

    fun getShelfAuditComparison(sessionId: Long, zoneName: String? = null): List<ShelfAuditItem> {
        val db = readableDatabase
        val list = mutableListOf<ShelfAuditItem>()

        val whereClause = if (!zoneName.isNullOrBlank()) {
            "WHERE session_id = ? AND zone_name = ?"
        } else {
            "WHERE session_id = ?"
        }
        val args = if (!zoneName.isNullOrBlank()) {
            arrayOf(sessionId.toString(), zoneName)
        } else {
            arrayOf(sessionId.toString())
        }

        val query = """
            SELECT 
                barcode, 
                default_code, 
                name_ar, 
                name_en, 
                SUM(qty) as counted_zone,
                MAX(timestamp),
                MAX(scan_method)
            FROM $TABLE_SCANS
            $whereClause
            GROUP BY barcode
            ORDER BY MAX(shelf_seq) ASC, MAX(id) ASC
        """.trimIndent()

        val c = db.rawQuery(query, args)
        while (c.moveToNext()) {
            val barcode = c.getString(0) ?: ""
            val code = c.getString(1) ?: ""
            val nameAr = c.getString(2) ?: ""
            val nameEn = c.getString(3) ?: ""
            val countedInZone = c.getDouble(4)
            val lastScanTime = c.getString(5) ?: ""
            val lastMethod = c.getString(6) ?: "SCAN"

            val totalInSession = getItemCountInSession(sessionId, barcode)
            val prod = getProductByBarcodeOrCode(barcode)

            list.add(
                ShelfAuditItem(
                    barcode = barcode,
                    defaultCode = prod?.defaultCode ?: code,
                    nameAr = prod?.nameAr ?: nameAr,
                    nameEn = prod?.nameEn ?: nameEn,
                    countedInZone = countedInZone,
                    totalCountedInSession = totalInSession,
                    systemQty = prod?.systemQty ?: 0.0,
                    costPrice = prod?.standardPrice ?: 0.0,
                    lastScanTime = lastScanTime,
                    lastScanMethod = lastMethod,
                    isUnknown = prod == null
                )
            )
        }
        c.close()
        return list
    }

    fun getSessionSummary(sessionId: Long): Pair<Int, Double> {
        val db = readableDatabase
        val c = db.rawQuery(
            "SELECT COUNT(DISTINCT barcode), SUM(qty) FROM $TABLE_SCANS WHERE session_id = ?",
            arrayOf(sessionId.toString())
        )
        var itemsCount = 0
        var totalUnits = 0.0
        if (c.moveToFirst()) {
            itemsCount = c.getInt(0)
            totalUnits = c.getDouble(1)
        }
        c.close()
        return Pair(itemsCount, totalUnits)
    }
}
