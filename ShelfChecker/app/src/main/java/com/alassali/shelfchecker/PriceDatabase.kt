package com.alassali.shelfchecker

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

class PriceDatabase(context: Context) : SQLiteOpenHelper(context, DATABASE_NAME, null, DATABASE_VERSION) {

    companion object {
        private const val DATABASE_NAME = "shelf_prices.db"
        private const val DATABASE_VERSION = 1
    }

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            "CREATE TABLE IF NOT EXISTS prices (" +
                    "barcode TEXT PRIMARY KEY, " +
                    "price REAL, " +
                    "is_taxable INTEGER, " +
                    "tax_rate REAL)"
        )
        db.execSQL(
            "CREATE TABLE IF NOT EXISTS metadata (" +
                    "key TEXT PRIMARY KEY, " +
                    "value TEXT)"
        )
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        db.execSQL("DROP TABLE IF EXISTS prices")
        db.execSQL("DROP TABLE IF EXISTS metadata")
        onCreate(db)
    }

    fun clearPrices() {
        val db = writableDatabase
        db.execSQL("DELETE FROM prices")
    }

    fun insertBatch(batch: List<ProductPrice>) {
        if (batch.isEmpty()) return
        val db = writableDatabase
        db.beginTransaction()
        try {
            val stmt = db.compileStatement(
                "INSERT OR REPLACE INTO prices (barcode, price, is_taxable, tax_rate) VALUES (?, ?, ?, ?)"
            )
            for (p in batch) {
                if (p.barcode.isBlank()) continue
                stmt.bindString(1, p.barcode)
                stmt.bindDouble(2, p.price)
                stmt.bindLong(3, if (p.isTaxable) 1 else 0)
                stmt.bindDouble(4, p.taxRate)
                stmt.executeInsert()
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    fun insertPrices(prices: List<ProductPrice>) {
        clearPrices()
        insertBatch(prices)
    }

    fun getPrice(barcode: String): ProductPrice? {
        val cleanBarcode = barcode.trim()
        if (cleanBarcode.isEmpty()) return null
        val db = readableDatabase
        var price: ProductPrice? = null
        val cursor = db.query(
            "prices",
            arrayOf("barcode", "price", "is_taxable", "tax_rate"),
            "barcode = ?",
            arrayOf(cleanBarcode),
            null, null, null
        )
        if (cursor.moveToFirst()) {
            price = ProductPrice(
                barcode = cursor.getString(0),
                price = cursor.getDouble(1),
                isTaxable = cursor.getInt(2) == 1,
                taxRate = cursor.getDouble(3)
            )
        }
        cursor.close()
        return price
    }

    fun getLastUpdateTime(): String {
        val db = readableDatabase
        var time = ""
        val cursor = db.query("metadata", arrayOf("value"), "key = ?", arrayOf("last_update"), null, null, null)
        if (cursor.moveToFirst()) {
            time = cursor.getString(0) ?: ""
        }
        cursor.close()
        return time
    }

    fun setLastUpdateTime(time: String) {
        val db = writableDatabase
        val values = ContentValues().apply {
            put("key", "last_update")
            put("value", time)
        }
        db.insertWithOnConflict("metadata", null, values, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun getCount(): Int {
        val db = readableDatabase
        val cursor = db.rawQuery("SELECT COUNT(*) FROM prices", null)
        var count = 0
        if (cursor.moveToFirst()) {
            count = cursor.getInt(0)
        }
        cursor.close()
        return count
    }
}
