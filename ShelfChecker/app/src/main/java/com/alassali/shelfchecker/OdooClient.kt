package com.alassali.shelfchecker

import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

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
        conn.connectTimeout = 25000
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

    fun lookupByBarcode(barcode: String): ProductPrice? {
        val cleanBarcode = barcode.trim()
        if (cleanBarcode.isEmpty()) return null
        if (uid <= 0 && !authenticate()) return null

        return try {
            // 1. Search primary barcode in product.product
            val domain = JSONArray().apply {
                put(JSONArray().apply {
                    put("barcode")
                    put("=")
                    put(cleanBarcode)
                })
            }

            val fields = JSONArray().apply {
                put("barcode")
                put("list_price")
                put("taxes_id")
            }

            val kwargs = JSONObject().apply {
                put("fields", fields)
                put("limit", 1)
            }

            val args = JSONArray().apply {
                put(db)
                put(uid)
                put(password)
                put("product.product")
                put("search_read")
                put(JSONArray().apply { put(domain) })
                put(kwargs)
            }

            var result = postJsonRpc("object", "execute_kw", args) as? JSONArray
            var productObj = if (result != null && result.length() > 0) result.getJSONObject(0) else null

            // 2. Search packaging barcode if not found
            if (productObj == null) {
                val pkgDomain = JSONArray().apply {
                    put(JSONArray().apply {
                        put("barcode")
                        put("=")
                        put(cleanBarcode)
                    })
                }
                val pkgKwargs = JSONObject().apply {
                    put("fields", JSONArray().apply { put("product_id") })
                    put("limit", 1)
                }
                val pkgArgs = JSONArray().apply {
                    put(db)
                    put(uid)
                    put(password)
                    put("product.packaging")
                    put("search_read")
                    put(JSONArray().apply { put(pkgDomain) })
                    put(pkgKwargs)
                }

                val pkgResult = postJsonRpc("object", "execute_kw", pkgArgs) as? JSONArray
                if (pkgResult != null && pkgResult.length() > 0) {
                    val pkgData = pkgResult.getJSONObject(0)
                    val prodIdArr = pkgData.optJSONArray("product_id")
                    val prodId = prodIdArr?.optInt(0)
                    if (prodId != null && prodId > 0) {
                        val prodDomain = JSONArray().apply {
                            put(JSONArray().apply {
                                put("id")
                                put("=")
                                put(prodId)
                            })
                        }
                        val fetchArgs = JSONArray().apply {
                            put(db)
                            put(uid)
                            put(password)
                            put("product.product")
                            put("search_read")
                            put(JSONArray().apply { put(prodDomain) })
                            put(kwargs)
                        }
                        val fetchRes = postJsonRpc("object", "execute_kw", fetchArgs) as? JSONArray
                        if (fetchRes != null && fetchRes.length() > 0) {
                            productObj = fetchRes.getJSONObject(0)
                        }
                    }
                }
            }

            if (productObj != null) {
                createProductPrice(productObj)
            } else null
        } catch (e: Exception) {
            e.printStackTrace()
            lastError = e.message
            null
        }
    }

    private fun createProductPrice(productData: JSONObject): ProductPrice {
        val barcode = productData.optString("barcode", "")
        val price = productData.optDouble("list_price", 0.0)
        val taxesId = productData.optJSONArray("taxes_id")
        var isTaxable = false
        var taxRate = 0.0

        if (taxesId != null && taxesId.length() > 0) {
            val taxId = taxesId.optInt(0)
            if (taxId > 0) {
                isTaxable = true
                try {
                    val taxDomain = JSONArray().apply {
                        put(JSONArray().apply {
                            put("id")
                            put("=")
                            put(taxId)
                        })
                    }
                    val taxKwargs = JSONObject().apply {
                        put("fields", JSONArray().apply { put("amount") })
                        put("limit", 1)
                    }
                    val taxArgs = JSONArray().apply {
                        put(db)
                        put(uid)
                        put(password)
                        put("account.tax")
                        put("search_read")
                        put(JSONArray().apply { put(taxDomain) })
                        put(taxKwargs)
                    }
                    val taxResult = postJsonRpc("object", "execute_kw", taxArgs) as? JSONArray
                    if (taxResult != null && taxResult.length() > 0) {
                        val taxObj = taxResult.getJSONObject(0)
                        taxRate = taxObj.optDouble("amount", 15.0)
                    } else {
                        taxRate = 15.0
                    }
                } catch (e: Exception) {
                    taxRate = 15.0
                }
            }
        }
        return ProductPrice(barcode, price, isTaxable, taxRate)
    }

    fun downloadAllPrices(onBatch: ((batch: List<ProductPrice>, downloaded: Int, total: Int) -> Unit)? = null): List<ProductPrice> {
        lastError = null
        if (uid <= 0 && !authenticate()) {
            throw IllegalStateException(lastError ?: "فشل تسجيل الدخول إلى سيرفر Odoo")
        }

        val prices = mutableListOf<ProductPrice>()

        // 1. Fetch Taxes mapping
        val taxesMap = mutableMapOf<Int, Double>()
        try {
            val taxDomain = JSONArray().apply {
                put(JSONArray().apply {
                    put("active")
                    put("=")
                    put(true)
                })
            }
            val taxKwargs = JSONObject().apply {
                put("fields", JSONArray().apply { put("id"); put("amount") })
            }
            val taxArgs = JSONArray().apply {
                put(db)
                put(uid)
                put(password)
                put("account.tax")
                put("search_read")
                put(JSONArray().apply { put(taxDomain) })
                put(taxKwargs)
            }
            val taxResult = postJsonRpc("object", "execute_kw", taxArgs) as? JSONArray
            if (taxResult != null) {
                for (i in 0 until taxResult.length()) {
                    val t = taxResult.getJSONObject(i)
                    val id = t.optInt("id")
                    val amount = t.optDouble("amount", 15.0)
                    if (id > 0) {
                        taxesMap[id] = amount
                    }
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }

        // 2. Count total active products with barcode
        val countDomain = JSONArray().apply {
            put(JSONArray().apply { put("active"); put("="); put(true) })
            put(JSONArray().apply { put("sale_ok"); put("="); put(true) })
            put(JSONArray().apply { put("barcode"); put("!="); put(false) })
        }
        val countArgs = JSONArray().apply {
            put(db)
            put(uid)
            put(password)
            put("product.product")
            put("search_count")
            put(JSONArray().apply { put(countDomain) })
        }
        val totalCount = try {
            (postJsonRpc("object", "execute_kw", countArgs) as? Number)?.toInt() ?: 10000
        } catch (e: Exception) {
            10000
        }

        // 3. Batch download products (2500 per request)
        val batchSize = 2500
        var offset = 0

        val prodFields = JSONArray().apply {
            put("barcode")
            put("list_price")
            put("taxes_id")
        }

        while (true) {
            val kwargs = JSONObject().apply {
                put("fields", prodFields)
                put("limit", batchSize)
                put("offset", offset)
            }
            val prodArgs = JSONArray().apply {
                put(db)
                put(uid)
                put(password)
                put("product.product")
                put("search_read")
                put(JSONArray().apply { put(countDomain) })
                put(kwargs)
            }

            val productResult = postJsonRpc("object", "execute_kw", prodArgs) as? JSONArray
            if (productResult == null || productResult.length() == 0) break

            val batch = mutableListOf<ProductPrice>()
            for (i in 0 until productResult.length()) {
                val pData = productResult.getJSONObject(i)
                val barcode = pData.optString("barcode", "").trim()
                if (barcode.isBlank()) continue

                val price = pData.optDouble("list_price", 0.0)
                val taxesId = pData.optJSONArray("taxes_id")
                var isTaxable = false
                var taxRate = 0.0
                if (taxesId != null && taxesId.length() > 0) {
                    val taxId = taxesId.optInt(0)
                    if (taxId > 0 && taxesMap.containsKey(taxId)) {
                        isTaxable = true
                        taxRate = taxesMap[taxId] ?: 15.0
                    }
                }
                val pp = ProductPrice(barcode, price, isTaxable, taxRate)
                batch.add(pp)
                prices.add(pp)
            }

            offset += productResult.length()
            onBatch?.invoke(batch, prices.size, totalCount)

            if (productResult.length() < batchSize) break
        }

        return prices
    }

    /**
     * Checks if this device is active or blocked in Odoo's device registry.
     * Returns: "active", "blocked", "not_found", or "unknown"
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
     * Registers a device or updates heartbeat/last_seen in Odoo's registry.
     * Preserves "blocked" status if the device has already been revoked by admin.
     * Returns the current device status ("active", "blocked", or "unknown").
     */
    fun registerOrUpdateDevice(
        deviceId: String,
        deviceName: String,
        deviceModel: String,
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

            val now = java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", java.util.Locale.US).format(java.util.Date())

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
            devObj.put("app_name", "ShelfChecker")
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

    fun fetchRawParam(paramName: String): String? {
        if (uid <= 0 && !authenticate()) return null
        return try {
            val getArgs = JSONArray().apply {
                put(db)
                put(uid)
                put(password)
                put("ir.config_parameter")
                put("get_param")
                put(JSONArray().apply { put(paramName) })
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

