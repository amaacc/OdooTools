package com.alassali.fastinventory

import android.app.Application

class FastInventoryApp : Application() {
    override fun onCreate() {
        super.onCreate()
        val settings = SettingsManager(this)
        settings.applyTheme()
    }
}
