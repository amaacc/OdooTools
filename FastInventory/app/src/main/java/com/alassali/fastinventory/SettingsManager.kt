package com.alassali.fastinventory

import android.content.Context
import android.content.SharedPreferences
import androidx.appcompat.app.AppCompatDelegate
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKeys

class SettingsManager(context: Context) {

    private val prefs: SharedPreferences = try {
        val masterKeyAlias = MasterKeys.getOrCreate(MasterKeys.AES256_GCM_SPEC)
        EncryptedSharedPreferences.create(
            "fast_inventory_secure_prefs",
            masterKeyAlias,
            context,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    } catch (e: Exception) {
        // Fallback for devices where keystore encounters issue
        context.getSharedPreferences("fast_inventory_plain_prefs", Context.MODE_PRIVATE)
    }

    init {
        // Security & Cleanup: Purge any legacy saved local IP or exposed credentials from previous versions
        val savedUrl = prefs.getString("server_url", null)
        if (savedUrl != null) {
            prefs.edit()
                .remove("server_url")
                .remove("database")
                .remove("username")
                .remove("password")
                .apply()
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Theme Management (Dark & Light)
    // ─────────────────────────────────────────────────────────────────────────
    fun getThemeMode(): String = prefs.getString("theme_mode", "dark") ?: "dark"

    fun setThemeMode(mode: String) {
        val cleanMode = if (mode.equals("light", ignoreCase = true)) "light" else "dark"
        prefs.edit().putString("theme_mode", cleanMode).apply()
        applyTheme()
    }

    fun applyTheme() {
        if (getThemeMode() == "light") {
            AppCompatDelegate.setDefaultNightMode(AppCompatDelegate.MODE_NIGHT_NO)
        } else {
            AppCompatDelegate.setDefaultNightMode(AppCompatDelegate.MODE_NIGHT_YES)
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Odoo Credentials (Always encrypted in memory, never exposed in UI)
    // ─────────────────────────────────────────────────────────────────────────
    fun isConfigured(): Boolean = true

    fun getServerUrl(): String = AppSecurity.getOdooConfig().url
    fun getDatabase(): String = AppSecurity.getOdooConfig().db
    fun getUsername(): String = AppSecurity.getOdooConfig().user
    fun getPassword(): String = AppSecurity.getOdooConfig().password

    // ─────────────────────────────────────────────────────────────────────────
    // Device & Session
    // ─────────────────────────────────────────────────────────────────────────
    fun getDeviceName(): String = prefs.getString("device_name", "الهاندهيل 1") ?: "الهاندهيل 1"
    fun setDeviceName(name: String) = prefs.edit().putString("device_name", name.trim()).apply()

    fun getDefaultZone(): String = prefs.getString("default_zone", "الرف العام") ?: "الرف العام"
    fun setDefaultZone(zone: String) = prefs.edit().putString("default_zone", zone.trim()).apply()

    fun getActiveSessionName(): String = prefs.getString("active_session_name", "جلسة جرد رئيسية") ?: "جلسة جرد رئيسية"
    fun setActiveSessionName(name: String) = prefs.edit().putString("active_session_name", name.trim()).apply()

    fun getTargetEmail(): String = prefs.getString("target_email", "") ?: ""
    fun setTargetEmail(email: String) = prefs.edit().putString("target_email", email.trim()).apply()

    // SMTP Settings (Optional for background export)
    fun isSmtpEnabled(): Boolean = prefs.getBoolean("smtp_enabled", false)
    fun setSmtpEnabled(enabled: Boolean) = prefs.edit().putBoolean("smtp_enabled", enabled).apply()

    fun getSmtpHost(): String = prefs.getString("smtp_host", "smtp.gmail.com") ?: "smtp.gmail.com"
    fun setSmtpHost(host: String) = prefs.edit().putString("smtp_host", host.trim()).apply()

    fun getSmtpPort(): Int = prefs.getInt("smtp_port", 587)
    fun setSmtpPort(port: Int) = prefs.edit().putInt("smtp_port", port).apply()

    fun getSmtpUser(): String = prefs.getString("smtp_user", "") ?: ""
    fun setSmtpUser(user: String) = prefs.edit().putString("smtp_user", user.trim()).apply()

    fun getSmtpPassword(): String = prefs.getString("smtp_pass", "") ?: ""
    fun setSmtpPassword(pass: String) = prefs.edit().putString("smtp_pass", pass.trim()).apply()

    fun isSmtpSsl(): Boolean = prefs.getBoolean("smtp_ssl", true)
    fun setSmtpSsl(ssl: Boolean) = prefs.edit().putBoolean("smtp_ssl", ssl).apply()

    // Catalog sync metadata
    fun getLastCatalogSync(): String = prefs.getString("last_catalog_sync", "") ?: ""
    fun setLastCatalogSync(timestamp: String) = prefs.edit().putString("last_catalog_sync", timestamp).apply()

    fun getCatalogItemCount(): Int = prefs.getInt("catalog_item_count", 0)
    fun setCatalogItemCount(count: Int) = prefs.edit().putInt("catalog_item_count", count).apply()

    fun getCatalogPackagingCount(): Int = prefs.getInt("catalog_pkg_count", 0)
    fun setCatalogPackagingCount(count: Int) = prefs.edit().putInt("catalog_pkg_count", count).apply()
}
