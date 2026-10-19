package com.alassali.fastinventory

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.widget.Toast

object AppSecurity {

    interface SecurityCallback {
        fun onDeviceBlocked()
        fun onDeviceActive()
    }

    /**
     * Checks if this device has been revoked or blocked remotely from Odoo.
     */
    fun verifyDeviceStatusAsync(context: Context, callback: SecurityCallback? = null) {
        val settings = SettingsManager(context)
        if (!settings.isConfigured()) {
            callback?.onDeviceActive()
            return
        }

        Thread {
            try {
                val client = OdooClient(
                    settings.getServerUrl(),
                    settings.getDatabase(),
                    settings.getUsername(),
                    settings.getPassword()
                )

                val deviceId = LicenseManager.getDeviceId(context)
                val deviceName = settings.getDeviceName()
                val status = client.registerOrUpdateDevice(
                    deviceId = deviceId,
                    deviceName = deviceName,
                    deviceModel = "${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL}",
                    appName = "FastInventory",
                    appVersion = "1.00"
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
}
