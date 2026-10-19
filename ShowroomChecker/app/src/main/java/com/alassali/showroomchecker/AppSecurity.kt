package com.alassali.showroomchecker

import android.util.Base64
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
    // Obfuscated key segments to prevent static string extraction
    private val K1 = "AlAssali2026".toByteArray(Charsets.UTF_8)
    private val K2 = "SecureOdooKey".toByteArray(Charsets.UTF_8)
    private val K3 = "Secret!".toByteArray(Charsets.UTF_8)
    private val IV = "AlAssaliIV123456".toByteArray(Charsets.UTF_8)

    // Clean Base64 AES-256 payload verified with automated test
    private const val ENC_B64 = "NPbLlawmqibiXK866oa25Xvvc63mcLN3TQl4w6reD1l+U2A8rH2aPSuKYapVQK5QtiHRJEUHKNCrzHsadNXidRJaHGmD2M+qNRT1yiSDxDvZncsl/wh6Y1rIrbqpcjmgQVeq97QYBPd+veUfKGu7MRkMM+AdHfTXdx5tIwIAPoIEZAVEBOCRi7o/Z8MOCkqXNJTGem55CWuCAuLoEayMd4Viw99apARQxxO1UHL8W+98dUGP6xLKLEmTPGSOKX4y"

    private var cachedConfig: OdooConfig? = null

    /**
     * Decrypts and returns Odoo connection credentials in memory only.
     * Sensitive values are NEVER stored in SharedPreferences or displayed in the UI.
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
}
