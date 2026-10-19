package com.alassali.showroomchecker

import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap

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

    companion object {
        // In-memory cache for ultra-fast repeated scanning: barcode -> productId
        private val barcodeToProductIdCache = ConcurrentHashMap<String, Int>()
    }

    private fun postJsonRpc(service: String, method: String, args: JSONArray): Any? {
        val endpoint = if (url.endsWith("/")) "${url}jsonrpc" else "$url/jsonrpc"
        val requestUrl = URL(endpoint)
        val conn = requestUrl.openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.setRequestProperty("Content-Type", "application/json")
        conn.setRequestProperty("Accept", "application/json")
        conn.connectTimeout = 15000
        conn.readTimeout = 25000
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

    /**
     * Checks if this device is active or blocked in Odoo's device registry.
     */
    fun checkDeviceStatus(deviceId: String): String {
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
            if (registry.has(cleanId)) {
                val devObj = registry.getJSONObject(cleanId)
                devObj.optString("status", "active")
            } else {
                "not_found"
            }
        } catch (e: Exception) {
            e.printStackTrace()
            "unknown"
        }
    }

    /**
     * Registers device or updates heartbeat in Odoo's device registry.
     */
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
            } else if (!devObj.has("device_name") || devObj.optString("device_name").isBlank()) {
                devObj.put("device_name", "نقطة بيع غير مسماة")
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
     * Looks up an item in Odoo by barcode (primary, packaging, or default_code),
     * fetches real-time stock in showroom location and POS sales, and computes net need.
     */
    fun queryProductAndNeeds(
        barcode: String,
        showroomLocationId: Int,
        posConfigIds: List<Int>,
        period: String,
        needMonths: Int
    ): ProductNeedDetails? {
        val cleanBarcode = barcode.trim()
        if (cleanBarcode.isEmpty()) return null
        if (uid <= 0 && !authenticate()) {
            throw IllegalStateException(lastError ?: "تعذر الاتصال بسيرفر أودو")
        }

        var productId = barcodeToProductIdCache[cleanBarcode]

        // 1. Search product by primary barcode or default_code
        if (productId == null) {
            val domain = JSONArray().apply {
                put(JSONArray().apply { put("active"); put("="); put(true) })
                put("|")
                put(JSONArray().apply { put("barcode"); put("="); put(cleanBarcode) })
                put(JSONArray().apply { put("default_code"); put("=ilike"); put(cleanBarcode) })
            }
            val kwargs = JSONObject().apply {
                put("fields", JSONArray().apply { put("id") })
                put("limit", 1)
            }
            val args = JSONArray().apply {
                put(db); put(uid); put(password)
                put("product.product")
                put("search_read")
                put(JSONArray().apply { put(domain) })
                put(kwargs)
            }
            val res = postJsonRpc("object", "execute_kw", args) as? JSONArray
            if (res != null && res.length() > 0) {
                productId = res.getJSONObject(0).optInt("id", 0).takeIf { it > 0 }
            }
        }

        // 2. Search product.packaging if not found
        if (productId == null) {
            val pkgDomain = JSONArray().apply {
                put(JSONArray().apply { put("barcode"); put("=ilike"); put(cleanBarcode) })
            }
            val pkgKwargs = JSONObject().apply {
                put("fields", JSONArray().apply { put("product_id") })
                put("limit", 1)
            }
            val pkgArgs = JSONArray().apply {
                put(db); put(uid); put(password)
                put("product.packaging")
                put("search_read")
                put(JSONArray().apply { put(pkgDomain) })
                put(pkgKwargs)
            }
            val pkgRes = postJsonRpc("object", "execute_kw", pkgArgs) as? JSONArray
            if (pkgRes != null && pkgRes.length() > 0) {
                val prodArr = pkgRes.getJSONObject(0).optJSONArray("product_id")
                productId = prodArr?.optInt(0, 0)?.takeIf { it > 0 }
            }
        }

        if (productId == null) return null
        barcodeToProductIdCache[cleanBarcode] = productId

        // 3. Read Product Details
        val prodFields = JSONArray().apply {
            put("id"); put("name"); put("product_name_arabic")
            put("default_code"); put("barcode"); put("uom_id")
        }
        val prodArgs = JSONArray().apply {
            put(db); put(uid); put(password)
            put("product.product")
            put("read")
            put(JSONArray().apply { put(JSONArray().apply { put(productId) }) })
            put(JSONObject().apply { put("fields", prodFields) })
        }
        val prodRes = postJsonRpc("object", "execute_kw", prodArgs) as? JSONArray
        if (prodRes == null || prodRes.length() == 0) return null
        val pObj = prodRes.getJSONObject(0)

        val nameEn = pObj.optString("name", "-").ifBlank { "-" }
        val nameAr = pObj.optString("product_name_arabic", "").ifBlank { nameEn }
        val defaultCode = pObj.optString("default_code", "-").ifBlank { "-" }
        val mainBarcode = pObj.optString("barcode", cleanBarcode).ifBlank { cleanBarcode }
        val uomArr = pObj.optJSONArray("uom_id")
        val uom = if (uomArr != null && uomArr.length() > 1) uomArr.optString(1, "حبة") else "حبة"

        // 4. Query Stock Quantity in showroom location
        var stockQty = 0.0
        if (showroomLocationId > 0) {
            val quantDomain = JSONArray().apply {
                put(JSONArray().apply { put("product_id"); put("="); put(productId) })
                put(JSONArray().apply { put("location_id"); put("="); put(showroomLocationId) })
            }
            val quantKwargs = JSONObject().apply {
                put("fields", JSONArray().apply { put("quantity") })
            }
            val quantArgs = JSONArray().apply {
                put(db); put(uid); put(password)
                put("stock.quant")
                put("search_read")
                put(JSONArray().apply { put(quantDomain) })
                put(quantKwargs)
            }
            val quantRes = postJsonRpc("object", "execute_kw", quantArgs) as? JSONArray
            if (quantRes != null) {
                for (i in 0 until quantRes.length()) {
                    stockQty += quantRes.getJSONObject(i).optDouble("quantity", 0.0)
                }
            }
        }

        // 5. Query Sales Quantity in POS Orders
        var soldQty = 0.0
        val today = Calendar.getInstance()
        val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US)
        var periodDays = 365
        var periodLabel = "منذ بداية العام"
        val dateFilter = JSONArray()

        when (period) {
            "last_30_days" -> {
                val cal = Calendar.getInstance().apply { add(Calendar.DAY_OF_YEAR, -30) }
                dateFilter.put(JSONArray().apply { put("date"); put(">="); put(dateFormat.format(cal.time)) })
                periodDays = 30
                periodLabel = "آخر 30 يوم"
            }
            "last_60_days" -> {
                val cal = Calendar.getInstance().apply { add(Calendar.DAY_OF_YEAR, -60) }
                dateFilter.put(JSONArray().apply { put("date"); put(">="); put(dateFormat.format(cal.time)) })
                periodDays = 60
                periodLabel = "آخر 60 يوم"
            }
            "last_90_days" -> {
                val cal = Calendar.getInstance().apply { add(Calendar.DAY_OF_YEAR, -90) }
                dateFilter.put(JSONArray().apply { put("date"); put(">="); put(dateFormat.format(cal.time)) })
                periodDays = 90
                periodLabel = "آخر 90 يوم"
            }
            "last_365_days" -> {
                val cal = Calendar.getInstance().apply { add(Calendar.DAY_OF_YEAR, -365) }
                dateFilter.put(JSONArray().apply { put("date"); put(">="); put(dateFormat.format(cal.time)) })
                periodDays = 365
                periodLabel = "آخر 365 يوم"
            }
            "all" -> {
                periodDays = 365
                periodLabel = "كامل المبيعات"
            }
            else -> { // Default: this_year
                val startYear = Calendar.getInstance().apply {
                    set(Calendar.MONTH, Calendar.JANUARY)
                    set(Calendar.DAY_OF_MONTH, 1)
                    set(Calendar.HOUR_OF_DAY, 0)
                    set(Calendar.MINUTE, 0)
                    set(Calendar.SECOND, 0)
                }
                dateFilter.put(JSONArray().apply { put("date"); put(">="); put(dateFormat.format(startYear.time)) })
                val diffDays = ((today.timeInMillis - startYear.timeInMillis) / (1000 * 60 * 60 * 24)).toInt() + 1
                periodDays = if (diffDays > 0) diffDays else 1
                periodLabel = "منذ بداية العام"
            }
        }

        if (posConfigIds.isNotEmpty()) {
            val dom = JSONArray().apply {
                put(JSONArray().apply { put("product_id"); put("="); put(productId) })
                put(JSONArray().apply {
                    put("state")
                    put("in")
                    put(JSONArray().apply { put("paid"); put("done"); put("invoiced") })
                })
                put(JSONArray().apply {
                    put("config_id")
                    put("in")
                    put(JSONArray(posConfigIds))
                })
                for (i in 0 until dateFilter.length()) {
                    put(dateFilter.getJSONArray(i))
                }
            }
            val salesKwargs = JSONObject().apply {
                put("lazy", false)
            }
            val methodArgs = JSONArray().apply {
                put(dom)
                put(JSONArray().apply { put("product_qty:sum") })
                put(JSONArray())
            }
            val salesArgs = JSONArray().apply {
                put(db); put(uid); put(password)
                put("report.pos.order")
                put("read_group")
                put(methodArgs)
                put(salesKwargs)
            }
            val salesRes = postJsonRpc("object", "execute_kw", salesArgs) as? JSONArray
            if (salesRes != null && salesRes.length() > 0) {
                soldQty = salesRes.getJSONObject(0).optDouble("product_qty", 0.0)
            }
        }

        // 6. Calculations identical to PC ShowroomChecker
        val monthlyRate = if (periodDays > 0) (soldQty / periodDays.toDouble()) * 30.0 else (soldQty / 12.0)
        val targetNeed = Math.round(monthlyRate * needMonths.toDouble() * 100.0) / 100.0
        val netNeed = Math.round((targetNeed - stockQty) * 100.0) / 100.0

        return ProductNeedDetails(
            id = productId,
            defaultCode = defaultCode,
            barcode = mainBarcode,
            nameEn = nameEn,
            nameAr = nameAr,
            uom = uom,
            stockQty = Math.round(stockQty * 100.0) / 100.0,
            soldQty = Math.round(soldQty * 100.0) / 100.0,
            monthlyRate = Math.round(monthlyRate * 100.0) / 100.0,
            targetNeed = targetNeed,
            needMonths = needMonths,
            netNeed = netNeed,
            periodDays = periodDays,
            periodLabel = periodLabel
        )
    }

    /**
     * Fetches live active showrooms with their warehouse and POS config IDs.
     */
    fun fetchShowrooms(): List<Showroom> {
        if (uid <= 0 && !authenticate()) {
            throw IllegalStateException(lastError ?: "تعذر تسجيل الدخول إلى أودو")
        }

        val posDomain = JSONArray().apply {
            put(JSONArray().apply { put("active"); put("="); put(true) })
        }
        val posKwargs = JSONObject().apply {
            put("fields", JSONArray().apply { put("id"); put("name"); put("picking_type_id") })
        }
        val posArgs = JSONArray().apply {
            put(db); put(uid); put(password)
            put("pos.config")
            put("search_read")
            put(JSONArray().apply { put(posDomain) })
            put(posKwargs)
        }
        val posConfigs = postJsonRpc("object", "execute_kw", posArgs) as? JSONArray ?: JSONArray()

        val pickingTypeIds = mutableSetOf<Int>()
        for (i in 0 until posConfigs.length()) {
            val cfg = posConfigs.getJSONObject(i)
            val ptArr = cfg.optJSONArray("picking_type_id")
            if (ptArr != null && ptArr.length() > 0) {
                pickingTypeIds.add(ptArr.getInt(0))
            }
        }
        if (pickingTypeIds.isEmpty()) return ShowroomManager.DEFAULT_SHOWROOMS

        val ptIdsJson = JSONArray(pickingTypeIds.toList())
        val ptKwargs = JSONObject().apply {
            put("fields", JSONArray().apply { put("id"); put("warehouse_id") })
        }
        val ptArgs = JSONArray().apply {
            put(db); put(uid); put(password)
            put("stock.picking.type")
            put("read")
            put(JSONArray().apply { put(ptIdsJson) })
            put(ptKwargs)
        }
        val pickingTypes = postJsonRpc("object", "execute_kw", ptArgs) as? JSONArray ?: JSONArray()

        val ptMap = mutableMapOf<Int, Int>() // pickingTypeId -> warehouseId
        val warehouseIds = mutableSetOf<Int>()
        for (i in 0 until pickingTypes.length()) {
            val pt = pickingTypes.getJSONObject(i)
            val ptId = pt.getInt("id")
            val whArr = pt.optJSONArray("warehouse_id")
            if (whArr != null && whArr.length() > 0) {
                val whId = whArr.getInt(0)
                ptMap[ptId] = whId
                warehouseIds.add(whId)
            }
        }
        if (warehouseIds.isEmpty()) return ShowroomManager.DEFAULT_SHOWROOMS

        val whIdsJson = JSONArray(warehouseIds.toList())
        val whKwargs = JSONObject().apply {
            put("fields", JSONArray().apply {
                put("id"); put("name"); put("code"); put("lot_stock_id")
            })
        }
        val whArgs = JSONArray().apply {
            put(db); put(uid); put(password)
            put("stock.warehouse")
            put("read")
            put(JSONArray().apply { put(whIdsJson) })
            put(whKwargs)
        }
        val warehouses = postJsonRpc("object", "execute_kw", whArgs) as? JSONArray ?: JSONArray()
        val showrooms = mutableListOf<Showroom>()

        for (i in 0 until warehouses.length()) {
            val w = warehouses.getJSONObject(i)
            val wid = w.getInt("id")
            val name = w.getString("name")
            val code = w.optString("code", "")
            val lotArr = w.optJSONArray("lot_stock_id")
            val lotStockId = if (lotArr != null && lotArr.length() > 0) lotArr.getInt(0) else 0

            if (lotStockId > 0) {
                // Find pos config IDs for this warehouse
                val cfgIds = mutableListOf<Int>()
                for (j in 0 until posConfigs.length()) {
                    val cfg = posConfigs.getJSONObject(j)
                    val ptArr = cfg.optJSONArray("picking_type_id")
                    if (ptArr != null && ptArr.length() > 0) {
                        val ptId = ptArr.getInt(0)
                        if (ptMap[ptId] == wid) {
                            cfgIds.add(cfg.getInt("id"))
                        }
                    }
                }
                showrooms.add(Showroom(wid, name, code, lotStockId, cfgIds))
            }
        }

        showrooms.sortBy { it.code }
        return if (showrooms.isNotEmpty()) showrooms else ShowroomManager.DEFAULT_SHOWROOMS
    }

    fun fetchRawParam(paramName: String): String? {
        if (uid <= 0 && !authenticate()) return null
        return try {
            val getArgs = org.json.JSONArray().apply {
                put(db)
                put(uid)
                put(password)
                put("ir.config_parameter")
                put("get_param")
                put(org.json.JSONArray().apply { put(paramName) })
            }
            val res = postJsonRpc("object", "execute_kw", getArgs)
            when (res) {
                is String -> res
                is Boolean -> if (res) "true" else null
                else -> res?.toString()
            }
        } catch (e: Exception) {
            null
        }
    }
}
