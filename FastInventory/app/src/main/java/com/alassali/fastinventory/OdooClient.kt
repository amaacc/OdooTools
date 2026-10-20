package com.alassali.fastinventory

import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class OdooClient(
    private val url: String,
    private val db: String,
    private val username: String,
    private val password: String
) {
    var uid: Int = 0
        private set
    var lastError: String? = null
        private set

    private fun postJsonRpc(service: String, method: String, args: JSONArray): Any? {
        val endpoint = if (url.endsWith("/")) "${url}jsonrpc" else "$url/jsonrpc"
        val requestUrl = URL(endpoint)
        val conn = requestUrl.openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.setRequestProperty("Content-Type", "application/json")
        conn.setRequestProperty("Accept", "application/json")
        conn.connectTimeout = 20000
        conn.readTimeout = 45000
        conn.doOutput = true
        conn.doInput = true

        val params = JSONObject().apply {
            put("service", service)
            put("method", method)
            put("args", args)
        }

        val requestBody = JSONObject().apply {
            put("jsonrpc", "2.0")
            put("method", "call")
            put("params", params)
            put("id", System.currentTimeMillis())
        }

        OutputStreamWriter(conn.outputStream, "UTF-8").use { writer ->
            writer.write(requestBody.toString())
            writer.flush()
        }

        val responseCode = conn.responseCode
        val stream = if (responseCode in 200..299) conn.inputStream else conn.errorStream
            ?: throw IllegalStateException("HTTP error $responseCode from Odoo")

        val responseText = BufferedReader(InputStreamReader(stream, "UTF-8")).use { it.readText() }
        val jsonResponse = JSONObject(responseText)

        if (jsonResponse.has("error")) {
            val errObj = jsonResponse.getJSONObject("error")
            val message = errObj.optString("message", "Odoo error")
            val dataObj = errObj.optJSONObject("data")
            val detail = dataObj?.optString("message") ?: message
            throw IllegalStateException(detail)
        }

        return jsonResponse.opt("result")
    }

    fun authenticate(): Boolean {
        lastError = null
        return try {
            val args = JSONArray().apply {
                put(db)
                put(username)
                put(password)
                put(JSONObject())
            }
            val result = postJsonRpc("common", "authenticate", args)
            if (result is Int && result > 0) {
                uid = result
                true
            } else {
                lastError = "بيانات الاعتماد غير صحيحة"
                false
            }
        } catch (e: Exception) {
            e.printStackTrace()
            lastError = e.message ?: e.javaClass.simpleName
            false
        }
    }

    fun testConnection(): Pair<Boolean, String> {
        val ok = authenticate()
        return if (ok) {
            Pair(true, "✅ تم الاتصال بنجاح بـ Odoo (UID: $uid)")
        } else {
            Pair(false, "❌ فشل الاتصال: ${lastError ?: "خطأ غير معروف"}")
        }
    }

    fun fetchRawParam(paramKey: String): String? {
        if (uid <= 0 && !authenticate()) return null
        return try {
            val args = JSONArray().apply {
                put(db)
                put(uid)
                put(password)
                put("ir.config_parameter")
                put("get_param")
                put(JSONArray().apply { put(paramKey) })
            }
            val res = postJsonRpc("object", "execute_kw", args)
            when (res) {
                is String -> res
                is Boolean -> null
                else -> res?.toString()
            }
        } catch (e: Exception) {
            null
        }
    }

    fun registerOrUpdateDevice(
        deviceId: String,
        deviceName: String,
        deviceModel: String,
        appName: String,
        appVersion: String
    ): String {
        val cleanId = deviceId.trim().uppercase()
        if (uid <= 0 && !authenticate()) return "unknown"

        return try {
            val getArgs = JSONArray().apply {
                put(db)
                put(uid)
                put(password)
                put("ir.config_parameter")
                put("get_param")
                put(JSONArray().apply { put("shelfchecker.device_registry") })
            }
            val res = postJsonRpc("object", "execute_kw", getArgs)
            val jsonStr = when (res) {
                is String -> res
                is Boolean -> "{}"
                else -> res?.toString() ?: "{}"
            }
            val registry = JSONObject(jsonStr)
            val now = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())

            val devObj = if (registry.has(cleanId)) {
                registry.getJSONObject(cleanId)
            } else {
                JSONObject().apply {
                    put("device_id", cleanId)
                    put("registered_at", now)
                    put("status", "active")
                }
            }

            if (deviceName.isNotBlank()) {
                devObj.put("device_name", deviceName.trim())
            }
            devObj.put("model", deviceModel)
            devObj.put("app_name", appName)
            devObj.put("app_version", appVersion)
            devObj.put("last_seen", now)

            val currentStatus = devObj.optString("status", "active")
            registry.put(cleanId, devObj)

            val setArgs = JSONArray().apply {
                put(db)
                put(uid)
                put(password)
                put("ir.config_parameter")
                put("set_param")
                put(JSONArray().apply {
                    put("shelfchecker.device_registry")
                    put(registry.toString())
                })
            }
            postJsonRpc("object", "execute_kw", setArgs)
            currentStatus
        } catch (e: Exception) {
            e.printStackTrace()
            "unknown"
        }
    }

    /**
     * Fetches all active showrooms and warehouses from stock.warehouse.
     */
    fun fetchAllWarehouses(): List<WarehouseItem> {
        if (uid <= 0 && !authenticate()) {
            throw IllegalStateException(lastError ?: "تعذر الاتصال بـ Odoo")
        }

        val domain = JSONArray().apply {
            put(JSONArray().apply { put("active"); put("="); put(true) })
        }

        val fields = JSONArray().apply {
            put("id")
            put("name")
            put("code")
            put("lot_stock_id")
        }

        val kwargs = JSONObject().apply {
            put("fields", fields)
            put("order", "code asc, name asc")
        }

        val args = JSONArray().apply {
            put(db); put(uid); put(password)
            put("stock.warehouse")
            put("search_read")
            put(JSONArray().apply { put(domain) })
            put(kwargs)
        }

        val result = postJsonRpc("object", "execute_kw", args) as? JSONArray ?: return emptyList()
        val list = mutableListOf<WarehouseItem>()

        for (i in 0 until result.length()) {
            val obj = result.getJSONObject(i)
            val id = obj.optInt("id")
            val name = obj.optString("name", "").trim()
            val code = obj.optString("code", "").trim()
            val lotArr = obj.optJSONArray("lot_stock_id")
            val lotId = lotArr?.optInt(0)

            list.add(WarehouseItem(id, name, code, lotId))
        }

        return list
    }

    /**
     * Downloads active products from Odoo in paginated batches for offline fast lookup.
     * If warehouseId or warehouseLotStockId is supplied, Odoo calculates stock specifically for that showroom!
     */
    fun downloadAllProducts(
        warehouseId: Int = 0,
        warehouseLotStockId: Int? = null,
        warehouseName: String = "",
        onProgress: (fetchedCount: Int, totalEst: Int) -> Unit
    ): List<ProductItem> {
        if (uid <= 0 && !authenticate()) {
            throw IllegalStateException(lastError ?: "تعذر الاتصال بـ Odoo")
        }

        val domain = JSONArray().apply {
            put(JSONArray().apply { put("active"); put("="); put(true) })
            put(JSONArray().apply { put("sale_ok"); put("="); put(true) })
        }

        val fields = JSONArray().apply {
            put("id")
            put("barcode")
            put("default_code")
            put("name")
            put("product_name_arabic")
            put("standard_price")
            put("list_price")
            put("qty_available")
        }

        val contextObj = JSONObject()
        if (warehouseId > 0) {
            contextObj.put("warehouse", warehouseId)
        }
        if (warehouseLotStockId != null && warehouseLotStockId > 0) {
            contextObj.put("location", warehouseLotStockId)
        }

        val batchSize = 1000
        var offset = 0
        val allProducts = mutableListOf<ProductItem>()

        while (true) {
            val kwargs = JSONObject().apply {
                put("fields", fields)
                put("offset", offset)
                put("limit", batchSize)
                if (contextObj.length() > 0) {
                    put("context", contextObj)
                }
            }

            val args = JSONArray().apply {
                put(db); put(uid); put(password)
                put("product.product")
                put("search_read")
                put(JSONArray().apply { put(domain) })
                put(kwargs)
            }

            val result = postJsonRpc("object", "execute_kw", args) as? JSONArray ?: break
            val length = result.length()
            if (length == 0) break

            for (i in 0 until length) {
                val obj = result.getJSONObject(i)
                val id = obj.optInt("id")
                val barcode = obj.optString("barcode", "").trim()
                val code = obj.optString("default_code", "").trim()
                val nameEn = obj.optString("name", "").trim()
                val nameAr = obj.optString("product_name_arabic", "").trim().ifBlank { nameEn }
                val cost = obj.optDouble("standard_price", 0.0)
                val price = obj.optDouble("list_price", 0.0)
                val qty = obj.optDouble("qty_available", 0.0)

                allProducts.add(
                    ProductItem(
                        id = id,
                        barcode = barcode,
                        defaultCode = code,
                        nameAr = nameAr,
                        nameEn = nameEn,
                        standardPrice = cost,
                        listPrice = price,
                        systemQty = qty,
                        warehouseId = warehouseId,
                        warehouseName = warehouseName
                    )
                )
            }

            offset += length
            onProgress(offset, offset + batchSize)

            if (length < batchSize) break
        }

        return allProducts
    }

    /**
     * Downloads ALL carton/box packaging records from product.packaging in paginated batches.
     */
    fun downloadAllPackagings(onProgress: ((Int) -> Unit)? = null): List<PackagingItem> {
        if (uid <= 0 && !authenticate()) {
            throw IllegalStateException(lastError ?: "تعذر الاتصال بـ Odoo")
        }

        val domain = JSONArray().apply {
            put(JSONArray().apply { put("barcode"); put("!="); put(false) })
        }

        val fields = JSONArray().apply {
            put("id")
            put("barcode")
            put("name")
            put("qty")
            put("product_id")
        }

        val batchSize = 2000
        var offset = 0
        val allPackagings = mutableListOf<PackagingItem>()

        while (true) {
            val kwargs = JSONObject().apply {
                put("fields", fields)
                put("offset", offset)
                put("limit", batchSize)
            }

            val args = JSONArray().apply {
                put(db); put(uid); put(password)
                put("product.packaging")
                put("search_read")
                put(JSONArray().apply { put(domain) })
                put(kwargs)
            }

            val result = postJsonRpc("object", "execute_kw", args) as? JSONArray ?: break
            val length = result.length()
            if (length == 0) break

            for (i in 0 until length) {
                val obj = result.getJSONObject(i)
                val id = obj.optInt("id")
                val barcode = obj.optString("barcode", "").trim()
                if (barcode.isBlank()) continue

                val name = obj.optString("name", "كرتون").trim()
                val qty = obj.optDouble("qty", 1.0)

                val prodArr = obj.optJSONArray("product_id")
                val prodId = prodArr?.optInt(0, 0) ?: 0

                allPackagings.add(
                    PackagingItem(
                        id = id,
                        barcode = barcode,
                        productId = prodId,
                        productBarcode = "",
                        name = name,
                        qty = qty
                    )
                )
            }

            offset += length
            onProgress?.invoke(offset)
            if (length < batchSize) break
        }

        return allPackagings
    }
}
