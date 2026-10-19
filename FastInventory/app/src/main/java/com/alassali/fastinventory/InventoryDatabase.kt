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
        const val DATABASE_VERSION = 1

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
                system_qty REAL DEFAULT 0.0
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
                packaging_name TEXT DEFAULT ''
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX idx_scans_session_barcode ON $TABLE_SCANS(session_id, barcode)")

        db.execSQL("""
            CREATE TABLE $TABLE_SESSIONS (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                zone_name TEXT,
                created_at TEXT,
                status TEXT DEFAULT 'active'
            )
        """.trimIndent())
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        db.execSQL("DROP TABLE IF EXISTS $TABLE_SCANS")
        db.execSQL("DROP TABLE IF EXISTS $TABLE_PACKAGINGS")
        db.execSQL("DROP TABLE IF EXISTS $TABLE_PRODUCTS")
        db.execSQL("DROP TABLE IF EXISTS $TABLE_SESSIONS")
        onCreate(db)
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
                "INSERT OR REPLACE INTO $TABLE_PRODUCTS (id, barcode, default_code, name_ar, name_en, standard_price, list_price, system_qty) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
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
    // Fast Barcode Lookup (Resolves packaging to product if carton)
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
            "SELECT id, barcode, default_code, name_ar, name_en, standard_price, list_price, system_qty FROM $TABLE_PRODUCTS WHERE id = ? LIMIT 1",
            arrayOf(productId.toString())
        )
        val p = if (c.moveToFirst()) mapProduct(c) else null
        c.close()
        return p
    }

    fun getProductByBarcodeOrCode(barcodeOrCode: String): ProductItem? {
        val db = readableDatabase
        val c = db.rawQuery(
            "SELECT id, barcode, default_code, name_ar, name_en, standard_price, list_price, system_qty FROM $TABLE_PRODUCTS WHERE barcode = ? OR default_code = ? LIMIT 1",
            arrayOf(barcodeOrCode, barcodeOrCode)
        )
        val p = if (c.moveToFirst()) mapProduct(c) else null
        c.close()
        return p
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
            systemQty = c.getDouble(7)
        )
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Inventory Sessions & Scan Records
    // ─────────────────────────────────────────────────────────────────────────
    fun getOrOpenActiveSession(name: String, defaultZone: String): InventorySession {
        val db = writableDatabase
        val c = db.rawQuery(
            "SELECT id, name, zone_name, created_at, status FROM $TABLE_SESSIONS WHERE status = 'active' ORDER BY id DESC LIMIT 1",
            null
        )
        if (c.moveToFirst()) {
            val session = InventorySession(
                id = c.getLong(0),
                name = c.getString(1) ?: name,
                zoneName = c.getString(2) ?: defaultZone,
                createdAt = c.getString(3) ?: "",
                status = c.getString(4) ?: "active"
            )
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
        }
        val id = db.insert(TABLE_SESSIONS, null, cv)
        return InventorySession(id, name, defaultZone, now, "active")
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
        }
        return db.insert(TABLE_SCANS, null, cv)
    }

    /**
     * Returns total counted units for a specific barcode in the given session and zone.
     */
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

    /**
     * Returns total counted units for a specific barcode across all zones in the session.
     */
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

    /**
     * Adjusts the quantity for a specific barcode in a zone by overriding or delta.
     */
    fun setExactItemQuantity(sessionId: Long, barcode: String, zoneName: String, targetTotalQty: Double) {
        val current = getItemCountInZone(sessionId, barcode, zoneName)
        val delta = targetTotalQty - current
        if (delta != 0.0) {
            val db = writableDatabase
            val now = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())
            // Retrieve item details from existing scan or catalog
            val existing = getProductByBarcodeOrCode(barcode)
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

    /**
     * Returns aggregated items in session (one row per barcode with total counted qty and zone tags).
     */
    fun getAggregatedSessionItems(sessionId: Long): List<ScanRecord> {
        val db = readableDatabase
        val list = mutableListOf<ScanRecord>()
        val query = """
            SELECT barcode, default_code, name_ar, name_en, SUM(qty) as total_qty, zone_name, MAX(timestamp)
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
                    timestamp = c.getString(6) ?: ""
                )
            )
        }
        c.close()
        return list
    }

    /**
     * Returns full audit trail of every individual scan in the session.
     */
    fun getAllScansForSession(sessionId: Long): List<ScanRecord> {
        val db = readableDatabase
        val list = mutableListOf<ScanRecord>()
        val c = db.rawQuery(
            "SELECT id, session_id, barcode, default_code, name_ar, name_en, qty, zone_name, device_id, device_name, timestamp, is_packaging, packaging_qty, packaging_name FROM $TABLE_SCANS WHERE session_id = ? ORDER BY id ASC",
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
                    packagingName = c.getString(13) ?: ""
                )
            )
        }
        c.close()
        return list
    }

    /**
     * Returns pair of: (Unique Items Count, Total Pieces Count)
     */
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
