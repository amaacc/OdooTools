package com.alassali.shelfchecker

import android.content.Context
import android.os.Build
import android.provider.Settings
import java.security.MessageDigest
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

object LicenseManager {
    // Secret salt shared with Abdullah Al-Khatib's license generator
    private val SALT = "AL_KHATIB_SECURE_ODOO_2026_PROD_SALT".toByteArray(Charsets.UTF_8)
    private const val MASTER_PASS = "KHATIB@MASTER#2026"

    /**
     * Generates a unique, immutable hardware identifier for this Android device.
     */
    fun getDeviceId(context: Context): String {
        val androidId = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID) ?: "UNKNOWN"
        val raw = "${Build.MANUFACTURER}-${Build.MODEL}-${Build.HARDWARE}-$androidId".uppercase()
        val md = MessageDigest.getInstance("SHA-256")
        val hash = md.digest(raw.toByteArray(Charsets.UTF_8))
        val sb = StringBuilder()
        for (b in hash) {
            sb.append(String.format("%02X", b))
        }
        val hex = sb.toString()
        return "${hex.substring(0, 4)}-${hex.substring(4, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}"
    }

    /**
     * Computes the HMAC-SHA256 signature for this device ID.
     */
    fun generateExpectedKey(deviceId: String): String {
        val clean = deviceId.trim().uppercase().replace(" ", "").replace("-", "")
        val mac = Mac.getInstance("HmacSHA256")
        val secretKey = SecretKeySpec(SALT, "HmacSHA256")
        mac.init(secretKey)
        val hmacBytes = mac.doFinal(clean.toByteArray(Charsets.UTF_8))
        val sb = StringBuilder()
        for (b in hmacBytes) {
            sb.append(String.format("%02X", b))
        }
        val hex = sb.toString()
        return "${hex.substring(0, 4)}-${hex.substring(4, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}"
    }

    /**
     * Validates whether inputKey matches the expected license or Master Password.
     * Accepts key with or without hyphens, case-insensitive, trimmed of whitespace.
     */
    fun verifyKey(deviceId: String, inputKey: String): Boolean {
        val cleanInput = inputKey.trim().uppercase().replace(" ", "").replace("-", "")
        if (cleanInput.isEmpty()) return false
        val cleanMaster = MASTER_PASS.replace(" ", "").replace("-", "")
        if (cleanInput == cleanMaster || inputKey.trim().uppercase() == MASTER_PASS) return true
        val expectedRaw = generateExpectedKey(deviceId).replace("-", "")
        return cleanInput == expectedRaw
    }

    /**
     * Checks if this device has been activated with a valid license.
     */
    fun isActivated(context: Context): Boolean {
        val prefs = context.getSharedPreferences("shelf_license_prefs", Context.MODE_PRIVATE)
        val savedMid = prefs.getString("device_id", "") ?: ""
        val savedKey = prefs.getString("license_key", "") ?: ""
        val currentMid = getDeviceId(context)

        if (savedMid.replace("-", "") != currentMid.replace("-", "") || savedKey.isEmpty()) return false
        return verifyKey(currentMid, savedKey)
    }

    /**
     * Verifies and saves license activation for this device.
     */
    fun activate(context: Context, inputKey: String): Boolean {
        val deviceId = getDeviceId(context)
        if (!verifyKey(deviceId, inputKey)) return false

        val cleanRaw = inputKey.trim().uppercase().replace(" ", "").replace("-", "")
        val formattedKey = if (cleanRaw.length == 16) {
            "${cleanRaw.substring(0, 4)}-${cleanRaw.substring(4, 8)}-${cleanRaw.substring(8, 12)}-${cleanRaw.substring(12, 16)}"
        } else {
            inputKey.trim().uppercase()
        }

        val prefs = context.getSharedPreferences("shelf_license_prefs", Context.MODE_PRIVATE)
        prefs.edit().apply {
            putString("device_id", deviceId)
            putString("license_key", formattedKey)
        }.apply()
        return true
    }

    /**
     * Deactivates this device by clearing stored license information.
     */
    fun deactivate(context: Context) {
        val prefs = context.getSharedPreferences("shelf_license_prefs", Context.MODE_PRIVATE)
        prefs.edit().remove("license_key").apply()
    }

    /**
     * Retrieves the employee/branch name associated with this device.
     */
    fun getEmployeeName(context: Context): String {
        val prefs = context.getSharedPreferences("shelf_license_prefs", Context.MODE_PRIVATE)
        return prefs.getString("employee_name", "") ?: ""
    }

    /**
     * Saves the employee/branch name associated with this device.
     */
    fun setEmployeeName(context: Context, name: String) {
        val prefs = context.getSharedPreferences("shelf_license_prefs", Context.MODE_PRIVATE)
        prefs.edit().putString("employee_name", name.trim()).apply()
    }
}

