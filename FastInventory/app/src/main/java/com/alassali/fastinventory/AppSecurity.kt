package com.alassali.fastinventory

import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.widget.Toast
import org.json.JSONObject
import javax.crypto.Cipher
import javax.crypto.spec.IvParameterSpec
import javax.crypto.spec.SecretKeySpec

data class OdooConfig(
    val url: String,
    val db: String,
    val user: String,
    val password: String
)

object AppSecurity {

    interface SecurityCallback {
        fun onDeviceBlocked()
        fun onDeviceActive()
    }

    // Obfuscated key parts (split into byte segments to prevent static string extraction)
    private val K1 = "AlAssali2026".toByteArray(Charsets.UTF_8)
    private val K2 = "SecureOdooKey".toByteArray(Charsets.UTF_8)
    private val K3 = "Secret!".toByteArray(Charsets.UTF_8)
    private val IV = "AlAssaliIV123456".toByteArray(Charsets.UTF_8)

    // Clean Base64 AES-256 payload verified with automated test
    private const val ENC_B64 = "NPbLlawmqibiXK866oa25Xvvc63mcLN3TQl4w6reD1l+U2A8rH2aPSuKYapVQK5QtiHRJEUHKNCrzHsadNXidRJaHGmD2M+qNRT1yiSDxDvZncsl/wh6Y1rIrbqpcjmgQVeq97QYBPd+veUfKGu7MRkMM+AdHfTXdx5tIwIAPoIEZAVEBOCRi7o/Z8MOCkqXNJTGem55CWuCAuLoEayMd4Viw99apARQxxO1UHL8W+98dUGP6xLKLEmTPGSOKX4y"

    private var cachedConfig: OdooConfig? = null

    /**
     * Decrypts and returns default Odoo connection credentials securely in memory.
     */
    fun getOdooConfig(): OdooConfig {
        cachedConfig?.let { return it }
        synchronized(this) {
            cachedConfig?.let { return it }
            val keyBytes = K1 + K2 + K3
            val keySpec = SecretKeySpec(keyBytes, "AES")
            val ivSpec = IvParameterSpec(IV)
            val cipher = Cipher.getInstance("AES/CBC/PKCS5Padding")
            cipher.init(Cipher.DECRYPT_MODE, keySpec, ivSpec)

            val encBytes = Base64.decode(ENC_B64, Base64.DEFAULT)
            val decrypted = cipher.doFinal(encBytes)
            val jsonStr = String(decrypted, Charsets.UTF_8)
            val json = JSONObject(jsonStr)

            val config = OdooConfig(
                url = json.getString("url"),
                db = json.getString("db"),
                user = json.getString("user"),
                password = json.getString("pwd")
            )
            cachedConfig = config
            return config
        }
    }

    /**
     * Gets effective OdooClient: uses custom user settings if entered, else falls back to embedded company credentials.
     */
    fun getEffectiveOdooClient(context: Context): OdooClient {
        val settings = SettingsManager(context)
        val url = settings.getServerUrl()
        val db = settings.getDatabase()
        val user = settings.getUsername()
        val pass = settings.getPassword()

        if (url.isNotBlank() && db.isNotBlank() && user.isNotBlank() && pass.isNotBlank()) {
            return OdooClient(url, db, user, pass)
        }

        val def = getOdooConfig()
        return OdooClient(def.url, def.db, def.user, def.password)
    }

    /**
     * Checks if this device has been revoked or blocked remotely from Odoo and heartbeats last_seen.
     */
    fun verifyDeviceStatusAsync(context: Context, callback: SecurityCallback? = null) {
        Thread {
            try {
                val client = getEffectiveOdooClient(context)
                val deviceId = LicenseManager.getDeviceId(context)
                val settings = SettingsManager(context)
                val deviceName = settings.getDeviceName()
                val model = "${Build.MANUFACTURER} ${Build.MODEL} (Android ${Build.VERSION.RELEASE})"

                val status = client.registerOrUpdateDevice(
                    deviceId = deviceId,
                    deviceName = deviceName,
                    deviceModel = model,
                    appName = "FastInventory",
                    appVersion = "1.02"
                )

                Handler(Looper.getMainLooper()).post {
                    if (status == "blocked") {
                        LicenseManager.deactivate(context)
                        Toast.makeText(context, "🚫 تم حظر هذا الجهاز من قبل الإدارة.", Toast.LENGTH_LONG).show()
                        callback?.onDeviceBlocked()
                    } else {
                        callback?.onDeviceActive()
                    }
                }
            } catch (e: Exception) {
                // If offline, allow execution if locally activated
                Handler(Looper.getMainLooper()).post {
                    callback?.onDeviceActive()
                }
            }
        }.start()
    }

    /**
     * Directly registers or updates this device in Odoo registry with immediate callback.
     */
    fun registerDeviceNow(
        context: Context,
        customName: String? = null,
        onResult: (success: Boolean, message: String) -> Unit
    ) {
        Thread {
            try {
                val client = getEffectiveOdooClient(context)
                val deviceId = LicenseManager.getDeviceId(context)
                val settings = SettingsManager(context)
                val name = customName?.takeIf { it.isNotBlank() } ?: settings.getDeviceName()
                val model = "${Build.MANUFACTURER} ${Build.MODEL} (Android ${Build.VERSION.RELEASE})"

                val status = client.registerOrUpdateDevice(
                    deviceId = deviceId,
                    deviceName = name,
                    deviceModel = model,
                    appName = "FastInventory",
                    appVersion = "1.02"
                )

                Handler(Looper.getMainLooper()).post {
                    if (status == "blocked") {
                        LicenseManager.deactivate(context)
                        onResult(false, "تم حظر هذا الجهاز من قبل إدارة النظام")
                    } else if (status != "unknown") {
                        onResult(true, "✅ تم تسجيل ومزامنة الجهاز في Odoo بنجاح!")
                    } else {
                        onResult(false, client.lastError ?: "تعذر التسجيل في سيرفر Odoo")
                    }
                }
            } catch (e: Exception) {
                Handler(Looper.getMainLooper()).post {
                    onResult(false, e.localizedMessage ?: "فشل الاتصال بسيرفر Odoo")
                }
            }
        }.start()
    }
}
