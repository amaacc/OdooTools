package com.alassali.shelfchecker

import android.Manifest
import android.animation.ArgbEvaluator
import android.animation.ValueAnimator
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.Editable
import android.text.TextWatcher
import android.view.KeyEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.EditText
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {

    private val mismatchBarcodes = mutableListOf<String>()
    private val unknownBarcodes = mutableListOf<String>()
    private var scannedCount = 0

    private lateinit var scannerHelper: ScannerHelper
    private lateinit var priceDb: PriceDatabase
    private lateinit var settingsManager: SettingsManager

    private lateinit var editBarcodeCatch: EditText
    private lateinit var btnManualLookup: Button
    private lateinit var btnCameraScan: View
    private lateinit var scanResultArea: View
    private lateinit var promptContainer: View
    private lateinit var txtPrompt: TextView
    private lateinit var resultLayout: LinearLayout
    private lateinit var txtBarcode: TextView
    private lateinit var txtPrice: TextView
    private lateinit var txtTaxInfo: TextView
    private lateinit var txtStatus: TextView
    private lateinit var btnMismatch: Button
    private lateinit var txtMismatchCount: TextView
    private lateinit var txtScannedCount: TextView

    private val executor = Executors.newSingleThreadExecutor()
    private val uiHandler = Handler(Looper.getMainLooper())
    private var toneGen: ToneGenerator? = null

    // BroadcastReceiver for Honeywell hardware scanner intents (e.g. EDA51 / ScanPal)
    private val honeywellReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            intent ?: return
            val barcode = intent.getStringExtra("data")
                ?: intent.getStringExtra("barcode")
                ?: intent.getStringExtra("scanner_data")
                ?: intent.getStringExtra("version")
                ?: intent.getByteArrayExtra("dataBytes")?.let { String(it) }
            if (!barcode.isNullOrBlank()) {
                runOnUiThread {
                    handleBarcodeScanned(barcode.trim())
                }
            }
        }
    }

    // Camera Scan Activity Launcher
    private val cameraScanLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            val barcode = result.data?.getStringExtra(CameraScanActivity.EXTRA_SCANNED_BARCODE)
            if (!barcode.isNullOrBlank()) {
                handleBarcodeScanned(barcode.trim())
            }
        }
    }

    // Camera Permission Launcher
    private val cameraPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            launchCameraScannerActivity()
        } else {
            Toast.makeText(this, "يرجى منح صلاحية الكاميرا لمسح الباركود", Toast.LENGTH_SHORT).show()
        }
    }

    private val mismatchListLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            val data = result.data
            mismatchBarcodes.clear()
            mismatchBarcodes.addAll(data?.getStringArrayListExtra("mismatches") ?: emptyList())
            unknownBarcodes.clear()
            unknownBarcodes.addAll(data?.getStringArrayListExtra("unknowns") ?: emptyList())
            updateBottomBar()
        }
    }

    private val inputDebounceHandler = Handler(Looper.getMainLooper())
    private val inputDebounceRunnable = Runnable {
        val text = editBarcodeCatch.text.toString().trim()
        if (text.length >= 4) {
            editBarcodeCatch.setText("")
            handleBarcodeScanned(text)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        priceDb = PriceDatabase(this)
        settingsManager = SettingsManager(this)

        try {
            toneGen = ToneGenerator(AudioManager.STREAM_MUSIC, 100)
        } catch (e: Exception) {
            e.printStackTrace()
        }

        // License check
        if (!LicenseManager.isActivated(this)) {
            startActivity(Intent(this, ActivationActivity::class.java))
        }

        editBarcodeCatch = findViewById(R.id.editBarcodeCatch)
        btnManualLookup = findViewById(R.id.btnManualLookup)
        btnCameraScan = findViewById(R.id.btnCameraScan)
        scanResultArea = findViewById(R.id.scanResultArea)
        promptContainer = findViewById(R.id.promptContainer)
        txtPrompt = findViewById(R.id.txtPrompt)
        resultLayout = findViewById(R.id.resultLayout)
        txtBarcode = findViewById(R.id.txtBarcode)
        txtPrice = findViewById(R.id.txtPrice)
        txtTaxInfo = findViewById(R.id.txtTaxInfo)
        txtStatus = findViewById(R.id.txtStatus)
        btnMismatch = findViewById(R.id.btnMismatch)
        txtMismatchCount = findViewById(R.id.txtMismatchCount)
        txtScannedCount = findViewById(R.id.txtScannedCount)

        scannerHelper = ScannerHelper { barcode ->
            runOnUiThread {
                handleBarcodeScanned(barcode)
            }
        }

        // Setup input box for keyboard wedge capture
        editBarcodeCatch.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun afterTextChanged(s: Editable?) {
                val str = s?.toString() ?: ""
                if (str.contains("\n") || str.contains("\r")) {
                    inputDebounceHandler.removeCallbacks(inputDebounceRunnable)
                    val clean = str.replace("\n", "").replace("\r", "").trim()
                    editBarcodeCatch.setText("")
                    if (clean.isNotEmpty()) {
                        handleBarcodeScanned(clean)
                    }
                } else if (str.length >= 4) {
                    inputDebounceHandler.removeCallbacks(inputDebounceRunnable)
                    inputDebounceHandler.postDelayed(inputDebounceRunnable, 150)
                }
            }
        })

        editBarcodeCatch.setOnEditorActionListener { _, actionId, event ->
            if (actionId == EditorInfo.IME_ACTION_SEARCH ||
                actionId == EditorInfo.IME_ACTION_DONE ||
                (event != null && event.keyCode == KeyEvent.KEYCODE_ENTER && event.action == KeyEvent.ACTION_DOWN)
            ) {
                inputDebounceHandler.removeCallbacks(inputDebounceRunnable)
                val text = editBarcodeCatch.text.toString().trim()
                if (text.isNotEmpty()) {
                    editBarcodeCatch.setText("")
                    handleBarcodeScanned(text)
                }
                true
            } else false
        }

        btnManualLookup.setOnClickListener {
            inputDebounceHandler.removeCallbacks(inputDebounceRunnable)
            val text = editBarcodeCatch.text.toString().trim()
            if (text.isNotEmpty()) {
                editBarcodeCatch.setText("")
                handleBarcodeScanned(text)
            } else {
                Toast.makeText(this, "يرجى مسح أو إدخال الباركود", Toast.LENGTH_SHORT).show()
                refocusInput()
            }
        }

        // Camera Scanner Button Click
        btnCameraScan.setOnClickListener {
            openCameraScanner()
        }

        // Tapping scanResultArea when idle opens camera scan on smartphones
        scanResultArea.setOnClickListener {
            if (promptContainer.visibility == View.VISIBLE) {
                openCameraScanner()
            }
        }

        btnMismatch.setOnClickListener {
            handleMismatchReported()
        }

        findViewById<ImageButton>(R.id.btnSettings).setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }

        findViewById<ImageButton>(R.id.btnSend).setOnClickListener {
            val intent = Intent(this, MismatchListActivity::class.java)
            intent.putStringArrayListExtra("mismatches", ArrayList(mismatchBarcodes))
            intent.putStringArrayListExtra("unknowns", ArrayList(unknownBarcodes))
            intent.putExtra("scannedCount", scannedCount)
            mismatchListLauncher.launch(intent)
        }

        resetToReadyState()
        updateBottomBar()
    }

    private fun openCameraScanner() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            launchCameraScannerActivity()
        } else {
            cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    private fun launchCameraScannerActivity() {
        val intent = Intent(this, CameraScanActivity::class.java)
        cameraScanLauncher.launch(intent)
    }

    override fun onResume() {
        super.onResume()

        if (!LicenseManager.isActivated(this)) {
            startActivity(Intent(this, ActivationActivity::class.java))
            return
        }

        checkDeviceStatusWithOdoo()

        editBarcodeCatch.post {
            editBarcodeCatch.requestFocus()
        }

        val filter = IntentFilter().apply {
            addAction("com.honeywell.aidc.action.BARCODE_DATA")
            addAction("com.honeywell.decode.intent.action.DEFAULT")
            addAction("com.honeywell.decode.intent.action.EDIT_DATA")
            addAction("hsm.RECV_DATA")
        }
        try {
            registerReceiver(honeywellReceiver, filter)
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    private fun checkDeviceStatusWithOdoo() {
        executor.execute {
            try {
                val config = AppSecurity.getOdooConfig()
                val client = OdooClient(config.url, config.db, config.user, config.password)
                val deviceId = LicenseManager.getDeviceId(this)
                val empName = LicenseManager.getEmployeeName(this)
                val model = "${Build.MANUFACTURER} ${Build.MODEL} (Android ${Build.VERSION.RELEASE})"

                val status = client.registerOrUpdateDevice(deviceId, empName, model, "1.0")
                if (status == "blocked") {
                    uiHandler.post {
                        handleDeviceBlockedByAdmin()
                    }
                } else {
                    // Check for App Updates in background
                    AppUpdateManager.checkForUpdate(this, client, "1.0")
                }
            } catch (e: Exception) {
                // If device is offline, keep functioning smoothly
                e.printStackTrace()
            }
        }
    }

    private fun handleDeviceBlockedByAdmin() {
        try {
            // 1. Wipe offline price database completely to protect company data
            priceDb.clearPrices()

            // 2. Clear activation license in preferences
            LicenseManager.deactivate(this)

            // 3. Show blocked alert and redirect to ActivationActivity
            AlertDialog.Builder(this)
                .setTitle("🚫 تم إلغاء ترخيص هذا الجهاز")
                .setMessage("تم إنهاء وتجميد ترخيص هذا الجهاز من قبل إدارة النظام.\nتم مسح قاعدة بيانات الأسعار المحلية لحماية سرية المعلومات.")
                .setCancelable(false)
                .setPositiveButton("إغلاق التطبيق") { _, _ ->
                    val intent = Intent(this, ActivationActivity::class.java)
                    intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
                    startActivity(intent)
                    finish()
                }
                .show()
        } catch (e: Exception) {
            e.printStackTrace()
            finish()
        }
    }

    override fun onPause() {
        super.onPause()
        try {
            unregisterReceiver(honeywellReceiver)
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (scannerHelper.handleKeyEvent(event)) {
            return true
        }
        return super.dispatchKeyEvent(event)
    }

    private fun handleBarcodeScanned(barcode: String) {
        val cleanBarcode = barcode.trim()
        if (cleanBarcode.isEmpty()) return

        scannedCount++
        updateBottomBar()

        promptContainer.visibility = View.GONE
        resultLayout.visibility = View.VISIBLE
        txtBarcode.text = cleanBarcode
        txtPrice.text = "جاري البحث..."
        txtTaxInfo.text = ""
        btnMismatch.visibility = View.GONE
        txtStatus.visibility = View.GONE

        scanResultArea.setBackgroundColor(0xFFE0E0E0.toInt()) // Gray loading

        // 1. Check local offline database first
        val offlinePrice = priceDb.getPrice(cleanBarcode)
        if (offlinePrice != null) {
            showSuccess(cleanBarcode, offlinePrice)
            refocusInput()
            return
        }

        // 2. Query Odoo directly via network
        executor.execute {
            try {
                val config = AppSecurity.getOdooConfig()
                val client = OdooClient(
                    config.url,
                    config.db,
                    config.user,
                    config.password
                )
                val price = client.lookupByBarcode(cleanBarcode)
                uiHandler.post {
                    if (price != null) {
                        showSuccess(cleanBarcode, price)
                    } else {
                        val err = client.lastError ?: "غير موجود في Odoo"
                        showError(cleanBarcode, err)
                    }
                    refocusInput()
                }
            } catch (e: Exception) {
                uiHandler.post {
                    showError(cleanBarcode, e.message ?: "خطأ في الشبكة")
                    refocusInput()
                }
            }
        }
    }

    private fun refocusInput() {
        editBarcodeCatch.post {
            editBarcodeCatch.requestFocus()
        }
    }

    private fun showSuccess(barcode: String, productPrice: ProductPrice) {
        toneGen?.startTone(ToneGenerator.TONE_PROP_ACK, 100)

        txtPrice.text = String.format(java.util.Locale.US, "%.2f ر.س", productPrice.price)
        txtTaxInfo.text = if (productPrice.isTaxable) {
            "شامل الضريبة (${productPrice.taxRate.toInt()}%)"
        } else {
            "معفى من الضريبة"
        }

        btnMismatch.visibility = View.VISIBLE
        btnMismatch.tag = barcode

        animateBackgroundColor(scanResultArea, 0xFFE0E0E0.toInt(), 0xFF2E7D32.toInt()) // Green
    }

    private fun showError(barcode: String, message: String) {
        toneGen?.startTone(ToneGenerator.TONE_CDMA_ALERT_CALL_GUARD, 300)

        txtPrice.text = "صنف غير معرّف"
        txtTaxInfo.text = message
        btnMismatch.visibility = View.GONE

        if (!unknownBarcodes.contains(barcode)) {
            unknownBarcodes.add(barcode)
        }

        updateBottomBar()
        animateBackgroundColor(scanResultArea, 0xFFE0E0E0.toInt(), 0xFFE65100.toInt()) // Orange
    }

    private fun handleMismatchReported() {
        val barcode = btnMismatch.tag as? String ?: return
        if (!mismatchBarcodes.contains(barcode)) {
            mismatchBarcodes.add(barcode)
        }

        updateBottomBar()

        toneGen?.startTone(ToneGenerator.TONE_PROP_NACK, 200)
        btnMismatch.visibility = View.GONE
        txtStatus.visibility = View.VISIBLE
        txtStatus.text = "✅ تمت الإضافة"

        animateBackgroundColor(scanResultArea, 0xFF2E7D32.toInt(), 0xFFC62828.toInt()) // Red

        uiHandler.postDelayed({
            resetToReadyState()
            refocusInput()
        }, 1000)
    }

    private fun resetToReadyState() {
        promptContainer.visibility = View.VISIBLE
        resultLayout.visibility = View.GONE
        btnMismatch.visibility = View.GONE
        txtStatus.visibility = View.GONE
        scanResultArea.setBackgroundColor(0xFFEEEEEE.toInt())
        refocusInput()
    }

    private fun updateBottomBar() {
        txtMismatchCount.text = "📋 ${mismatchBarcodes.size + unknownBarcodes.size}"
        txtScannedCount.text = "✅ $scannedCount"
    }

    private fun animateBackgroundColor(view: View, colorFrom: Int, colorTo: Int) {
        val colorAnimation = ValueAnimator.ofObject(ArgbEvaluator(), colorFrom, colorTo)
        colorAnimation.duration = 250
        colorAnimation.addUpdateListener { animator ->
            view.setBackgroundColor(animator.animatedValue as Int)
        }
        colorAnimation.start()
    }

    override fun onDestroy() {
        super.onDestroy()
        toneGen?.release()
    }
}
