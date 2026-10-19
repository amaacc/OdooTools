package com.alassali.fastinventory

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.SystemClock
import android.view.KeyEvent

class ScannerHelper(private val onBarcodeScanned: (String) -> Unit) {

    private val buffer = StringBuilder()
    private var lastKeyTime = 0L

    /**
     * Handles hardware scanner key event wedge.
     */
    fun handleKeyEvent(event: KeyEvent): Boolean {
        if (event.action != KeyEvent.ACTION_DOWN) return false

        val now = SystemClock.uptimeMillis()
        if (now - lastKeyTime > 300 && buffer.isNotEmpty()) {
            buffer.clear()
        }
        lastKeyTime = now

        return when (event.keyCode) {
            KeyEvent.KEYCODE_ENTER -> {
                val barcode = buffer.toString().trim()
                buffer.clear()
                if (barcode.isNotEmpty()) {
                    onBarcodeScanned(barcode)
                    true
                } else false
            }
            else -> {
                val c = event.unicodeChar
                if (c > 0 && !Character.isISOControl(c)) {
                    buffer.append(c.toChar())
                    true
                } else false
            }
        }
    }

    fun reset() {
        buffer.clear()
        lastKeyTime = 0L
    }

    /**
     * BroadcastReceiver for Honeywell and Zebra intent-based scanning.
     */
    val intentReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent == null) return
            val action = intent.action ?: return

            // Honeywell Data Collection intent
            if (action == "com.honeywell.decode.intent.action.SCAN_RESULT") {
                val barcode = intent.getStringExtra("data") ?: return
                if (barcode.isNotBlank()) {
                    onBarcodeScanned(barcode.trim())
                }
            }
            // Zebra DataWedge intent
            else if (action == "com.symbol.datawedge.api.RESULT_ACTION" || action.contains("DATAWEDGE")) {
                val barcode = intent.getStringExtra("com.symbol.datawedge.data_string") ?: return
                if (barcode.isNotBlank()) {
                    onBarcodeScanned(barcode.trim())
                }
            }
        }
    }

    fun getIntentFilter(): IntentFilter {
        return IntentFilter().apply {
            addAction("com.honeywell.decode.intent.action.SCAN_RESULT")
            addAction("com.symbol.datawedge.api.RESULT_ACTION")
            addCategory(Intent.CATEGORY_DEFAULT)
        }
    }
}
