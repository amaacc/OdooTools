package com.alassali.shelfchecker

import android.content.Context
import android.content.SharedPreferences

class SettingsManager(context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences("shelf_checker_settings_prefs", Context.MODE_PRIVATE)

    fun saveReportEmail(email: String) {
        prefs.edit().putString("report_email", email.trim()).apply()
    }

    fun getServerUrl(): String = AppSecurity.getOdooConfig().url
    fun getDatabase(): String = AppSecurity.getOdooConfig().db
    fun getUsername(): String = AppSecurity.getOdooConfig().user
    fun getPassword(): String = AppSecurity.getOdooConfig().password

    fun getReportEmail(): String {
        val email = prefs.getString("report_email", "") ?: ""
        return if (email.isNotEmpty()) email else "abdullah.k@alassali.net"
    }

    fun isConfigured(): Boolean = true
}
