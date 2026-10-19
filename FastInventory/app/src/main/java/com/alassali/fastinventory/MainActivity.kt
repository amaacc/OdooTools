package com.alassali.fastinventory

import android.animation.ArgbEvaluator
import android.animation.ValueAnimator
import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.Bundle
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.view.KeyEvent
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import java.util.Locale

class MainActivity : AppCompatActivity() {

    private lateinit var settingsManager: SettingsManager
    private lateinit var sessionManager: SessionManager
    private lateinit var db: InventoryDatabase
    private lateinit var scannerHelper: ScannerHelper

    // UI elements
    private lateinit var btnSettings: ImageButton
    private lateinit var btnCameraScan: ImageButton
    private lateinit var txtDeviceAndSession: TextView
    private lateinit var txtActiveZone: TextView
    private lateinit var btnChangeZone: Button

    private lateinit var viewIdlePrompt: LinearLayout
    private lateinit var viewScannedProduct: ScrollView
    private lateinit var layoutScanFlashArea: LinearLayout

    private lateinit var badgePackaging: TextView
    private lateinit var txtBarcode: TextView
    private lateinit var txtDefaultCode: TextView
    private lateinit var txtProductNameAr: TextView
    private lateinit var txtProductNameEn: TextView
    private lateinit var txtCountedQty: TextView
    private lateinit var txtLastAddedStatus: TextView

    private lateinit var btnQuickPlus1: Button
    private lateinit var btnQuickPlus5: Button
    private lateinit var btnQuickPlus10: Button
    private lateinit var btnCustomQty: Button
    private lateinit var btnQuickUndo: Button

    private lateinit var txtTotalItemsCount: TextView
    private lateinit var txtTotalUnitsCount: TextView

    private lateinit var btnViewAuditList: Button
    private lateinit var btnConsolidator: Button
    private lateinit var btnExportReport: Button

    private var currentScannedBarcode: String? = null
    private var toneGen: ToneGenerator? = null

    private val cameraScanLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            val barcode = result.data?.getStringExtra(CameraScanActivity.EXTRA_SCANNED_BARCODE)
            if (!barcode.isNullOrBlank()) {
                handleBarcodeScanned(barcode)
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        settingsManager = SettingsManager(this)
        sessionManager = SessionManager(this)
        db = InventoryDatabase(this)

        initViews()
        setupScanner()
        setupListeners()
        updateSessionUi()

        try {
            toneGen = ToneGenerator(AudioManager.STREAM_MUSIC, 95)
        } catch (e: Exception) {
            // Ignore
        }

        // License Check
        if (!LicenseManager.isActivated(this)) {
            startActivity(Intent(this, ActivationActivity::class.java))
        } else {
            // Background Security & Update Check
            AppSecurity.verifyDeviceStatusAsync(this)
            checkForUpdatesAsync()
        }
    }

    override fun onResume() {
        super.onResume()
        try {
            registerReceiver(scannerHelper.intentReceiver, scannerHelper.getIntentFilter())
        } catch (e: Exception) {
            // Ignore if already registered
        }
        updateSessionUi()

        // Heartbeat & status sync with Odoo
        if (LicenseManager.isActivated(this)) {
            AppSecurity.verifyDeviceStatusAsync(this)
        }
    }

    override fun onPause() {
        super.onPause()
        try {
            unregisterReceiver(scannerHelper.intentReceiver)
        } catch (e: Exception) {
            // Ignore
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        toneGen?.release()
    }

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (scannerHelper.handleKeyEvent(event)) {
            return true
        }
        return super.dispatchKeyEvent(event)
    }

    private fun initViews() {
        btnSettings = findViewById(R.id.btnSettings)
        btnCameraScan = findViewById(R.id.btnCameraScan)
        txtDeviceAndSession = findViewById(R.id.txtDeviceAndSession)
        txtActiveZone = findViewById(R.id.txtActiveZone)
        btnChangeZone = findViewById(R.id.btnChangeZone)

        viewIdlePrompt = findViewById(R.id.viewIdlePrompt)
        viewScannedProduct = findViewById(R.id.viewScannedProduct)
        layoutScanFlashArea = findViewById(R.id.layoutScanFlashArea)

        badgePackaging = findViewById(R.id.badgePackaging)
        txtBarcode = findViewById(R.id.txtBarcode)
        txtDefaultCode = findViewById(R.id.txtDefaultCode)
        txtProductNameAr = findViewById(R.id.txtProductNameAr)
        txtProductNameEn = findViewById(R.id.txtProductNameEn)
        txtCountedQty = findViewById(R.id.txtCountedQty)
        txtLastAddedStatus = findViewById(R.id.txtLastAddedStatus)

        btnQuickPlus1 = findViewById(R.id.btnQuickPlus1)
        btnQuickPlus5 = findViewById(R.id.btnQuickPlus5)
        btnQuickPlus10 = findViewById(R.id.btnQuickPlus10)
        btnCustomQty = findViewById(R.id.btnCustomQty)
        btnQuickUndo = findViewById(R.id.btnQuickUndo)

        txtTotalItemsCount = findViewById(R.id.txtTotalItemsCount)
        txtTotalUnitsCount = findViewById(R.id.txtTotalUnitsCount)

        btnViewAuditList = findViewById(R.id.btnViewAuditList)
        btnConsolidator = findViewById(R.id.btnConsolidator)
        btnExportReport = findViewById(R.id.btnExportReport)
    }

    private fun setupScanner() {
        scannerHelper = ScannerHelper { barcode ->
            runOnUiThread {
                handleBarcodeScanned(barcode)
            }
        }
    }

    private fun setupListeners() {
        btnCameraScan.setOnClickListener {
            val intent = Intent(this, CameraScanActivity::class.java)
            cameraScanLauncher.launch(intent)
        }

        btnSettings.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }

        btnChangeZone.setOnClickListener {
            showChangeZoneDialog()
        }

        btnViewAuditList.setOnClickListener {
            startActivity(Intent(this, AuditListActivity::class.java))
        }

        btnConsolidator.setOnClickListener {
            startActivity(Intent(this, ConsolidatorActivity::class.java))
        }

        btnExportReport.setOnClickListener {
            exportCurrentSessionReport()
        }

        // Quick Count Buttons
        btnQuickPlus1.setOnClickListener {
            currentScannedBarcode?.let { bc ->
                val newTotal = sessionManager.addManualDelta(bc, 1.0)
                updateProductCountDisplay(newTotal, 1.0)
                triggerAudioAndHaptic(isPackaging = false, isUnknown = false)
            }
        }

        btnQuickPlus5.setOnClickListener {
            currentScannedBarcode?.let { bc ->
                val newTotal = sessionManager.addManualDelta(bc, 5.0)
                updateProductCountDisplay(newTotal, 5.0)
                triggerAudioAndHaptic(isPackaging = false, isUnknown = false)
            }
        }

        btnQuickPlus10.setOnClickListener {
            currentScannedBarcode?.let { bc ->
                val newTotal = sessionManager.addManualDelta(bc, 10.0)
                updateProductCountDisplay(newTotal, 10.0)
                triggerAudioAndHaptic(isPackaging = false, isUnknown = false)
            }
        }

        btnCustomQty.setOnClickListener {
            showCustomQuantityDialog()
        }

        btnQuickUndo.setOnClickListener {
            currentScannedBarcode?.let { bc ->
                val newTotal = sessionManager.addManualDelta(bc, -1.0)
                updateProductCountDisplay(newTotal, -1.0)
            }
        }
    }

    private fun handleBarcodeScanned(barcode: String) {
        val result = sessionManager.recordScan(barcode)
        currentScannedBarcode = result.barcode

        // Blind Count Display Update (Never shows system stock!)
        viewIdlePrompt.visibility = View.GONE
        viewScannedProduct.visibility = View.VISIBLE

        txtBarcode.text = result.barcode
        txtDefaultCode.text = if (result.defaultCode != "-") "كود: ${result.defaultCode}" else ""
        txtProductNameAr.text = result.nameAr
        txtProductNameEn.text = result.nameEn

        if (result.isPackaging) {
            badgePackaging.visibility = View.VISIBLE
            badgePackaging.text = "📦 كرتون = ${String.format(Locale.US, "%.0f", result.packagingQty)} حبة (${result.packagingName})"
        } else {
            badgePackaging.visibility = View.GONE
        }

        txtCountedQty.text = String.format(Locale.US, "%.0f", result.totalCountedInZone)

        val statusText = if (result.isPackaging) {
            "✅ تم حصر كرتون (+${String.format(Locale.US, "%.0f", result.addedQty)} حبة) | إجمالي الرف: ${String.format(Locale.US, "%.0f", result.totalCountedInZone)}"
        } else if (result.isUnknown) {
            "⚠️ صنف غير معرّف (+1 حبة) | إجمالي الرف: ${String.format(Locale.US, "%.0f", result.totalCountedInZone)}"
        } else {
            "✅ تمت إضافة 1 حبة | إجمالي الرف: ${String.format(Locale.US, "%.0f", result.totalCountedInZone)}"
        }
        txtLastAddedStatus.text = statusText
        txtLastAddedStatus.setTextColor(
            if (result.isUnknown) getColor(R.color.text_warning) else getColor(R.color.text_success)
        )

        // Audio & Visual flash
        triggerAudioAndHaptic(result.isPackaging, result.isUnknown)
        flashScanCard(result.isPackaging, result.isUnknown)

        updateSessionUi()
    }

    private fun updateProductCountDisplay(newTotal: Double, delta: Double) {
        txtCountedQty.text = String.format(Locale.US, "%.0f", newTotal)
        val sign = if (delta >= 0) "+${String.format(Locale.US, "%.0f", delta)}" else String.format(Locale.US, "%.0f", delta)
        txtLastAddedStatus.text = "تعديل: $sign حبة | الإجمالي الآن: ${String.format(Locale.US, "%.0f", newTotal)}"
        updateSessionUi()
    }

    private fun showCustomQuantityDialog() {
        val bc = currentScannedBarcode
        if (bc == null) {
            Toast.makeText(this, "امسح صنفاً أولاً لإدخال كميته", Toast.LENGTH_SHORT).show()
            return
        }

        val container = android.widget.FrameLayout(this).apply {
            setPadding(48, 20, 48, 10)
        }
        val input = EditText(this).apply {
            inputType = android.text.InputType.TYPE_CLASS_NUMBER or android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL
            hint = "أدخل الكمية المحصورة"
            setTextColor(getColor(R.color.text_primary))
            setHintTextColor(getColor(R.color.text_secondary))
            setBackgroundResource(R.drawable.bg_zone_pill)
            setPadding(28, 20, 28, 20)
        }
        container.addView(input)

        AlertDialog.Builder(this)
            .setTitle("✏️ إدخال كمية الصنف")
            .setMessage("أدخل الكمية الإجمالية في هذا الرف للباركود:\n$bc")
            .setView(container)
            .setPositiveButton("تثبيت") { _, _ ->
                val qty = input.text.toString().toDoubleOrNull()
                if (qty != null && qty >= 0) {
                    sessionManager.setExactQuantity(bc, qty)
                    updateProductCountDisplay(qty, 0.0)
                }
            }
            .setNegativeButton("إلغاء", null)
            .show()
    }

    private fun showChangeZoneDialog() {
        val container = android.widget.FrameLayout(this).apply {
            setPadding(48, 20, 48, 10)
        }
        val input = EditText(this).apply {
            setText(sessionManager.currentZone)
            setSelection(text.length)
            hint = "مثال: رف A-12 أو صالة العرض"
            setTextColor(getColor(R.color.text_primary))
            setHintTextColor(getColor(R.color.text_secondary))
            setBackgroundResource(R.drawable.bg_zone_pill)
            setPadding(28, 20, 28, 20)
        }
        container.addView(input)

        AlertDialog.Builder(this)
            .setTitle("🏷️ تغيير المنطقة أو الرف الحالي")
            .setMessage("سيتم تسجيل كافة الباركودات القادمة تحت اسم هذه المنطقة:")
            .setView(container)
            .setPositiveButton("تغيير") { _, _ ->
                val newZone = input.text.toString().trim()
                if (newZone.isNotBlank()) {
                    sessionManager.updateZone(newZone)
                    updateSessionUi()
                    Toast.makeText(this, "تم تغيير المنطقة إلى: $newZone", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("إلغاء", null)
            .show()
    }

    private fun updateSessionUi() {
        txtActiveZone.text = "المنطقة: ${sessionManager.currentZone}"
        txtDeviceAndSession.text = "${settingsManager.getDeviceName()} | ${sessionManager.currentSession.name}"

        val (uniqueCount, totalUnits) = sessionManager.getSessionSummary()
        txtTotalItemsCount.text = uniqueCount.toString()
        txtTotalUnitsCount.text = String.format(Locale.US, "%.0f", totalUnits)
    }

    private fun triggerAudioAndHaptic(isPackaging: Boolean, isUnknown: Boolean) {
        try {
            when {
                isUnknown -> toneGen?.startTone(ToneGenerator.TONE_CDMA_ALERT_CALL_GUARD, 180)
                isPackaging -> toneGen?.startTone(ToneGenerator.TONE_PROP_BEEP2, 140)
                else -> toneGen?.startTone(ToneGenerator.TONE_PROP_ACK, 90)
            }
        } catch (e: Exception) {
            // Ignore
        }

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val vibratorManager = getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager
                vibratorManager.defaultVibrator.vibrate(
                    VibrationEffect.createOneShot(if (isUnknown) 150 else 70, VibrationEffect.DEFAULT_AMPLITUDE)
                )
            } else {
                @Suppress("DEPRECATION")
                val vibrator = getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    vibrator.vibrate(VibrationEffect.createOneShot(if (isUnknown) 150 else 70, VibrationEffect.DEFAULT_AMPLITUDE))
                } else {
                    @Suppress("DEPRECATION")
                    vibrator.vibrate(if (isUnknown) 150 else 70)
                }
            }
        } catch (e: Exception) {
            // Ignore
        }
    }

    private fun flashScanCard(isPackaging: Boolean, isUnknown: Boolean) {
        val defaultBg = getColor(R.color.bg_card)
        val flashColor = when {
            isUnknown -> getColor(R.color.scan_warning_flash)
            isPackaging -> getColor(R.color.scan_packaging_flash)
            else -> getColor(R.color.scan_success_flash)
        }

        val colorAnimation = ValueAnimator.ofObject(ArgbEvaluator(), flashColor, defaultBg)
        colorAnimation.duration = 450
        colorAnimation.addUpdateListener { animator ->
            layoutScanFlashArea.setBackgroundColor(animator.animatedValue as Int)
        }
        colorAnimation.start()
    }

    private fun exportCurrentSessionReport() {
        val items = sessionManager.getAggregatedItems()
        if (items.isEmpty()) {
            Toast.makeText(this, "جلسة الجرد فارغة حالياً. امسح أصنافاً أولاً للتصدير.", Toast.LENGTH_LONG).show()
            return
        }

        val res = ReportExportEngine.exportSessionReport(
            context = this,
            sessionName = sessionManager.currentSession.name,
            zoneName = sessionManager.currentZone,
            items = items,
            db = db
        )

        // Silent SMTP if enabled, otherwise native share/email intent
        if (settingsManager.isSmtpEnabled()) {
            Toast.makeText(this, "جاري الإرسال الصامت عبر خادم SMTP...", Toast.LENGTH_SHORT).show()
            EmailDispatcher.sendReportViaSmtpAsync(
                context = this,
                subject = "تقرير الجرد السريع: ${sessionManager.currentSession.name}",
                bodyText = res.summaryText,
                files = listOf(res.xlsxFile, res.csvFile),
                callback = object : EmailDispatcher.DispatchCallback {
                    override fun onSuccess() {
                        Toast.makeText(this@MainActivity, "✅ تم إرسال التقرير بنجاح عبر البريد الإلكتروني!", Toast.LENGTH_LONG).show()
                    }
                    override fun onFailure(error: String) {
                        Toast.makeText(this@MainActivity, "تعذر الإرسال الصامت ($error)، سيتم فتح شاشة الإرسال الافتراضية.", Toast.LENGTH_LONG).show()
                        EmailDispatcher.sendReportViaIntent(
                            context = this@MainActivity,
                            subject = "تقرير الجرد السريع: ${sessionManager.currentSession.name}",
                            bodyText = res.summaryText,
                            files = listOf(res.xlsxFile, res.csvFile),
                            targetEmail = settingsManager.getTargetEmail()
                        )
                    }
                }
            )
        } else {
            EmailDispatcher.sendReportViaIntent(
                context = this,
                subject = "تقرير الجرد السريع: ${sessionManager.currentSession.name} — ${sessionManager.currentZone}",
                bodyText = res.summaryText,
                files = listOf(res.xlsxFile, res.csvFile),
                targetEmail = settingsManager.getTargetEmail()
            )
        }
    }

    private fun checkForUpdatesAsync() {
        if (!settingsManager.isConfigured()) return
        Thread {
            try {
                val client = OdooClient(
                    settingsManager.getServerUrl(),
                    settingsManager.getDatabase(),
                    settingsManager.getUsername(),
                    settingsManager.getPassword()
                )
                AppUpdateManager.checkForUpdate(this, client, "1.00")
            } catch (e: Exception) {
                // Ignore update failure
            }
        }.start()
    }
}
