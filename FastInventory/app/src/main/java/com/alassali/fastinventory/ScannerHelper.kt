package com.alassali.fastinventory

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.KeyEvent

/**
 * High-performance hardware barcode scanner helper.
 * Supports:
 * 1. Hardware Keystroke Wedge (Honeywell EDA51, Zebra, Datalogic, Urovo, etc.)
 *    with instant Enter/Tab submission AND 120ms debounce auto-submission
 *    for scanners configured with NO Enter suffix.
 * 2. Android Broadcast Intents (Honeywell Data Collection, Zebra DataWedge, Newland, Chainway).
 */
class ScannerHelper(private val onBarcodeScanned: (String) -> Unit) {

    private val buffer = StringBuilder()
    private var lastKeyTime = 0L
    private val handler = Handler(Looper.getMainLooper())

    /**
     * Debounce auto-submit for hardware scanners in keyboard wedge mode without ENTER suffix.
     * Hardware scanners type keystrokes with <20ms between characters.
     * If no keystroke arrives for 120ms and buffer length >= 3, automatically submit.
     */
    private val autoSubmitRunnable = Runnable {
        synchronized(buffer) {
            val barcode = buffer.toString().trim()
            if (barcode.length >= 3) {
                buffer.clear()
                onBarcodeScanned(barcode)
            }
        }
    }

    /**
     * Handles hardware scanner key event wedge.
     */
    fun handleKeyEvent(event: KeyEvent): Boolean {
        // Handle ACTION_MULTIPLE (some wedge drivers send full string at once)
        if (event.action == KeyEvent.ACTION_MULTIPLE) {
            val chars = event.characters
            if (!chars.isNullOrBlank()) {
                handler.removeCallbacks(autoSubmitRunnable)
                synchronized(buffer) {
                    buffer.clear()
                }
                onBarcodeScanned(chars.trim())
                return true
            }
        }

        if (event.action != KeyEvent.ACTION_DOWN) return false

        // Do not intercept system navigation / volume keys
        when (event.keyCode) {
            KeyEvent.KEYCODE_BACK,
            KeyEvent.KEYCODE_VOLUME_UP,
            KeyEvent.KEYCODE_VOLUME_DOWN,
            KeyEvent.KEYCODE_POWER,
            KeyEvent.KEYCODE_HOME,
            KeyEvent.KEYCODE_MENU -> return false
        }

        val now = SystemClock.uptimeMillis()
        synchronized(buffer) {
            // If gap between keys is > 400ms, start a new barcode scan
            if (now - lastKeyTime > 400 && buffer.isNotEmpty()) {
                buffer.clear()
            }
            lastKeyTime = now

            return when (event.keyCode) {
                KeyEvent.KEYCODE_ENTER,
                KeyEvent.KEYCODE_NUMPAD_ENTER,
                KeyEvent.KEYCODE_TAB -> {
                    handler.removeCallbacks(autoSubmitRunnable)
                    val barcode = buffer.toString().trim()
                    buffer.clear()
                    if (barcode.isNotEmpty()) {
                        onBarcodeScanned(barcode)
                        true
                    } else false
                }
                else -> {
                    val c = if (event.unicodeChar > 0 && !Character.isISOControl(event.unicodeChar)) {
                        event.unicodeChar.toChar()
                    } else when (event.keyCode) {
                        KeyEvent.KEYCODE_0 -> '0'
                        KeyEvent.KEYCODE_1 -> '1'
                        KeyEvent.KEYCODE_2 -> '2'
                        KeyEvent.KEYCODE_3 -> '3'
                        KeyEvent.KEYCODE_4 -> '4'
                        KeyEvent.KEYCODE_5 -> '5'
                        KeyEvent.KEYCODE_6 -> '6'
                        KeyEvent.KEYCODE_7 -> '7'
                        KeyEvent.KEYCODE_8 -> '8'
                        KeyEvent.KEYCODE_9 -> '9'
                        else -> 0.toChar()
                    }

                    if (c != 0.toChar()) {
                        buffer.append(c)
                        handler.removeCallbacks(autoSubmitRunnable)
                        // Hardware scanners send characters rapidly (<20ms).
                        // If no more keys arrive within 120ms, submit automatically.
                        handler.postDelayed(autoSubmitRunnable, 120)
                        true
                    } else false
                }
            }
        }
    }

    fun reset() {
        handler.removeCallbacks(autoSubmitRunnable)
        synchronized(buffer) {
            buffer.clear()
            lastKeyTime = 0L
        }
    }

    /**
     * BroadcastReceiver for Honeywell, Zebra, and generic OEM intent-based scanning.
     */
    val intentReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent == null) return
            val action = intent.action ?: return

            var barcode: String? = null

            // 1. Honeywell Data Collection intent
            if (action == "com.honeywell.decode.intent.action.SCAN_RESULT" ||
                action == "com.honeywell.action.BARCODE_DATA" ||
                action == "honeywell.scan.action"
            ) {
                barcode = intent.getStringExtra("data")
                if (barcode.isNullOrBlank()) {
                    val bytes = intent.getByteArrayExtra("dataBytes")
                    if (bytes != null) {
                        barcode = String(bytes, Charsets.UTF_8)
                    }
                }
                if (barcode.isNullOrBlank()) {
                    barcode = intent.getStringExtra("barcode") ?: intent.getStringExtra("barcodeString")
                }
            }
            // 2. Zebra DataWedge intent
            else if (action == "com.symbol.datawedge.api.RESULT_ACTION" || action.contains("DATAWEDGE")) {
                barcode = intent.getStringExtra("com.symbol.datawedge.data_string")
            }
            // 3. Newland
            else if (action == "nlscan.action.SCANNER_RESULT") {
                barcode = intent.getStringExtra("scan_result")
            }
            // 4. Chainway / PointMobile
            else if (action == "device.scanner.EVENT") {
                barcode = intent.getStringExtra("scannerdata")
            }
            // 5. Generic OEM Decode
            else if (action == "android.intent.ACTION_DECODE_DATA") {
                barcode = intent.getStringExtra("barcode_string") ?: intent.getStringExtra("barcode")
            }

            // Fallback: check standard extra keys if not found yet
            if (barcode.isNullOrBlank()) {
                barcode = intent.getStringExtra("data")
                    ?: intent.getStringExtra("barcode")
                    ?: intent.getStringExtra("value")
            }

            if (!barcode.isNullOrBlank()) {
                val clean = barcode.trim()
                if (clean.isNotEmpty()) {
                    onBarcodeScanned(clean)
                }
            }
        }
    }

    fun getIntentFilter(): IntentFilter {
        return IntentFilter().apply {
            addAction("com.honeywell.decode.intent.action.SCAN_RESULT")
            addAction("com.honeywell.action.BARCODE_DATA")
            addAction("honeywell.scan.action")
            addAction("com.symbol.datawedge.api.RESULT_ACTION")
            addAction("android.intent.ACTION_DECODE_DATA")
            addAction("nlscan.action.SCANNER_RESULT")
            addAction("device.scanner.EVENT")
            addCategory(Intent.CATEGORY_DEFAULT)
        }
    }
}
