package com.alassali.shelfchecker

import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.KeyEvent

class ScannerHelper(private val onBarcodeScanned: (String) -> Unit) {
    private val buffer = StringBuilder()
    private var lastKeyTime = 0L
    private val handler = Handler(Looper.getMainLooper())

    private val autoSubmitRunnable = Runnable {
        synchronized(buffer) {
            val barcode = buffer.toString().trim()
            if (barcode.length >= 4) {
                buffer.clear()
                onBarcodeScanned(barcode)
            }
        }
    }

    fun handleKeyEvent(event: KeyEvent): Boolean {
        if (event.action != KeyEvent.ACTION_DOWN) return false

        val now = SystemClock.uptimeMillis()
        synchronized(buffer) {
            // If gap between keys is > 500ms, start a new barcode scan
            if (now - lastKeyTime > 500 && buffer.isNotEmpty()) {
                buffer.clear()
            }
            lastKeyTime = now

            when (event.keyCode) {
                KeyEvent.KEYCODE_ENTER,
                KeyEvent.KEYCODE_NUMPAD_ENTER,
                KeyEvent.KEYCODE_TAB -> {
                    handler.removeCallbacks(autoSubmitRunnable)
                    val barcode = buffer.toString().trim()
                    buffer.clear()
                    return if (barcode.isNotEmpty()) {
                        onBarcodeScanned(barcode)
                        true
                    } else false
                }
                else -> {
                    val c = event.unicodeChar
                    if (c > 0 && !Character.isISOControl(c)) {
                        buffer.append(c.toChar())
                        handler.removeCallbacks(autoSubmitRunnable)
                        // Hardware scanners send characters rapidly (under 20ms apart).
                        // If no more keys arrive within 120ms, submit automatically (even without Enter suffix).
                        handler.postDelayed(autoSubmitRunnable, 120)
                        return true
                    }
                }
            }
        }
        return false
    }

    fun reset() {
        handler.removeCallbacks(autoSubmitRunnable)
        synchronized(buffer) {
            buffer.clear()
            lastKeyTime = 0L
        }
    }
}
