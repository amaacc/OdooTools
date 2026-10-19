package com.alassali.showroomchecker

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.graphics.Color
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.text.Editable
import android.text.TextWatcher
import android.view.KeyEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import java.util.Locale
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {

    // Views
    private lateinit var txtCurrentShowroom: TextView
    private lateinit var btnChangeShowroom: Button
    private lateinit var btnChangeShowroomArea: View
    private lateinit var btnSettings: ImageButton

    // Hardware Scanner Wedge & Camera Input Box
    private lateinit var editBarcodeCatch: EditText
    private lateinit var btnManualLookup: Button
    private lateinit var btnCameraScan: ImageButton

    // Full screen scan area
    private lateinit var mainScanArea: FrameLayout
    private lateinit var layoutPrompt: LinearLayout
    private lateinit var layoutLoading: LinearLayout
    private lateinit var txtLoadingLabel: TextView
    private lateinit var layoutResult: ScrollView
    private lateinit var txtProductNameEn: TextView
    private lateinit var txtProductNameAr: TextView
    private lateinit var txtResultBarcode: TextView
    private lateinit var txtStockQty: TextView
    private lateinit var txtUnitLabel: TextView
    private lateinit var txtStockStatus: TextView

    // Sales & Need Cards
    private lateinit var cardSales: View
    private lateinit var txtSalesCardTitle: TextView
    private lateinit var txtSoldQtyVal: TextView
    private lateinit var txtSoldRateVal: TextView

    private lateinit var cardNeed: View
    private lateinit var txtNeedCardTitle: TextView
    private lateinit var txtNetNeedVal: TextView
    private lateinit var txtNetNeedBadge: TextView

    private lateinit var layoutNotFound: LinearLayout
    private lateinit var txtNotFoundBarcode: TextView
    private lateinit var txtScanCount: TextView

    // Camera Scan Activity Launchers
    private val cameraPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            launchCameraScan()
        } else {
            Toast.makeText(this, "يرجى منح إذن استخدام الكاميرا لمسح الباركود", Toast.LENGTH_SHORT).show()
        }
    }

    private val cameraScanLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            val barcode = result.data?.getStringExtra(CameraScanActivity.EXTRA_SCANNED_BARCODE)
            if (!barcode.isNullOrBlank()) {
                processBarcode(barcode.trim())
            }
        }
    }

    // State & Helpers
    private var activeShowroom: Showroom? = null
    private var scannedTotalCount = 0
    private lateinit var scannerHelper: ScannerHelper
    private var toneGen: ToneGenerator? = null
    private var vibrator: Vibrator? = null
    private val executor = Executors.newSingleThreadExecutor()
    private val uiHandler = Handler(Looper.getMainLooper())

    // Debounce guard to prevent duplicate rapid scans of same barcode
    private var lastScannedBarcode = ""
    private var lastScannedTime = 0L

    // Honeywell Hardware Scanner Broadcast Intent Actions
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
                    processBarcode(barcode.trim())
                }
            }
        }
    }

    private val inputDebounceHandler = Handler(Looper.getMainLooper())
    private val inputDebounceRunnable = Runnable {
        val text = editBarcodeCatch.text.toString().trim()
        if (text.length >= 3) {
            editBarcodeCatch.setText("")
            processBarcode(text)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        initViews()
        initAudioAndHaptics()
        initScanner()
        loadActiveShowroom()

        // License check
        if (!LicenseManager.isActivated(this)) {
            startActivity(Intent(this, ActivationActivity::class.java))
        }
    }

    private fun initViews() {
        txtCurrentShowroom = findViewById(R.id.txtCurrentShowroom)
        btnChangeShowroom = findViewById(R.id.btnChangeShowroom)
        btnChangeShowroomArea = findViewById(R.id.btnChangeShowroomArea)
        btnSettings = findViewById(R.id.btnSettings)

        editBarcodeCatch = findViewById(R.id.editBarcodeCatch)
        btnManualLookup = findViewById(R.id.btnManualLookup)
        btnCameraScan = findViewById(R.id.btnCameraScan)

        mainScanArea = findViewById(R.id.mainScanArea)
        layoutPrompt = findViewById(R.id.layoutPrompt)
        layoutLoading = findViewById(R.id.layoutLoading)
        txtLoadingLabel = findViewById(R.id.txtLoadingLabel)
        layoutResult = findViewById(R.id.layoutResult)
        txtProductNameEn = findViewById(R.id.txtProductNameEn)
        txtProductNameAr = findViewById(R.id.txtProductNameAr)
        txtResultBarcode = findViewById(R.id.txtResultBarcode)
        txtStockQty = findViewById(R.id.txtStockQty)
        txtUnitLabel = findViewById(R.id.txtUnitLabel)
        txtStockStatus = findViewById(R.id.txtStockStatus)

        cardSales = findViewById(R.id.cardSales)
        txtSalesCardTitle = findViewById(R.id.txtSalesCardTitle)
        txtSoldQtyVal = findViewById(R.id.txtSoldQtyVal)
        txtSoldRateVal = findViewById(R.id.txtSoldRateVal)

        cardNeed = findViewById(R.id.cardNeed)
        txtNeedCardTitle = findViewById(R.id.txtNeedCardTitle)
        txtNetNeedVal = findViewById(R.id.txtNetNeedVal)
        txtNetNeedBadge = findViewById(R.id.txtNetNeedBadge)

        layoutNotFound = findViewById(R.id.layoutNotFound)
        txtNotFoundBarcode = findViewById(R.id.txtNotFoundBarcode)
        txtScanCount = findViewById(R.id.txtScanCount)

        btnChangeShowroom.setOnClickListener { showShowroomSelectionDialog() }
        btnChangeShowroomArea.setOnClickListener { showShowroomSelectionDialog() }
        btnSettings.setOnClickListener { startActivity(Intent(this, SettingsActivity::class.java)) }

        btnCameraScan.setOnClickListener { checkAndLaunchCamera() }
        layoutPrompt.setOnClickListener { checkAndLaunchCamera() }

        // Setup input box for Honeywell keyboard wedge capture
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
                        processBarcode(clean)
                    }
                } else if (str.length >= 3) {
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
                    processBarcode(text)
                }
                true
            } else false
        }

        btnManualLookup.setOnClickListener {
            inputDebounceHandler.removeCallbacks(inputDebounceRunnable)
            val text = editBarcodeCatch.text.toString().trim()
            if (text.isNotEmpty()) {
                editBarcodeCatch.setText("")
                processBarcode(text)
            } else {
                Toast.makeText(this, "يرجى مسح أو إدخال الباركود", Toast.LENGTH_SHORT).show()
                refocusInput()
            }
        }
    }

    private fun initAudioAndHaptics() {
        try {
            toneGen = ToneGenerator(AudioManager.STREAM_MUSIC, 100)
        } catch (e: Exception) {
            e.printStackTrace()
        }
        vibrator = getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
    }

    private fun playSoundAndVibration(type: AlertType) {
        try {
            when (type) {
                AlertType.IN_STOCK -> {
                    // Crisp short success beep
                    toneGen?.startTone(ToneGenerator.TONE_PROP_ACK, 120)
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        vibrator?.vibrate(VibrationEffect.createOneShot(60, VibrationEffect.DEFAULT_AMPLITUDE))
                    } else {
                        vibrator?.vibrate(60)
                    }
                }
                AlertType.OUT_OF_STOCK -> {
                    // Distinct deep double alert tone for zero or deficit
                    toneGen?.startTone(ToneGenerator.TONE_CDMA_SOFT_ERROR_LITE, 280)
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        val waveform = longArrayOf(0, 120, 80, 160)
                        vibrator?.vibrate(VibrationEffect.createWaveform(waveform, -1))
                    } else {
                        vibrator?.vibrate(250)
                    }
                }
                AlertType.NOT_FOUND -> {
                    // Loud distinct warble alert for unrecognized barcode
                    toneGen?.startTone(ToneGenerator.TONE_CDMA_ALERT_CALL_GUARD, 350)
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        val waveform = longArrayOf(0, 100, 70, 100, 70, 150)
                        vibrator?.vibrate(VibrationEffect.createWaveform(waveform, -1))
                    } else {
                        vibrator?.vibrate(350)
                    }
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    private enum class AlertType {
        IN_STOCK,
        OUT_OF_STOCK,
        NOT_FOUND
    }

    private fun initScanner() {
        scannerHelper = ScannerHelper { scannedBarcode ->
            runOnUiThread {
                processBarcode(scannedBarcode)
            }
        }
    }

    private fun loadActiveShowroom() {
        var showroom = ShowroomManager.getActiveShowroom(this)
        if (showroom == null) {
            val all = ShowroomManager.getAllShowrooms(this)
            if (all.isNotEmpty()) {
                showroom = all[0] // Default to first showroom immediately so user is never blocked
                ShowroomManager.setActiveShowroom(this, showroom)
            }
        }
        activeShowroom = showroom
        if (showroom != null) {
            updateShowroomUI(showroom)
        } else {
            txtCurrentShowroom.text = getString(R.string.no_showroom_selected)
            showShowroomSelectionDialog()
        }
    }

    private fun updateShowroomUI(showroom: Showroom) {
        txtCurrentShowroom.text = if (showroom.code.isNotBlank()) {
            "${showroom.name} (${showroom.code})"
        } else {
            showroom.name
        }
    }

    private fun showShowroomSelectionDialog() {
        val dialogView = layoutInflater.inflate(R.layout.dialog_select_showroom, null)
        val dialog = AlertDialog.Builder(this)
            .setView(dialogView)
            .setCancelable(true)
            .create()

        val etSearch = dialogView.findViewById<EditText>(R.id.etSearchShowroom)
        val btnClear = dialogView.findViewById<ImageButton>(R.id.btnClearShowroomFilter)
        val btnClose = dialogView.findViewById<ImageButton>(R.id.btnDialogClose)
        val recycler = dialogView.findViewById<RecyclerView>(R.id.recyclerDialogShowrooms)
        val txtEmpty = dialogView.findViewById<TextView>(R.id.txtNoShowroomsFound)

        val allShowrooms = ShowroomManager.getAllShowrooms(this)
        val adapter = ShowroomAdapter(allShowrooms, activeShowroom?.id ?: -1) { selected ->
            activeShowroom = selected
            ShowroomManager.setActiveShowroom(this, selected)
            updateShowroomUI(selected)
            dialog.dismiss()
            Toast.makeText(this, "تم اختيار: ${selected.name}", Toast.LENGTH_SHORT).show()
            refocusInput()
        }

        recycler.layoutManager = LinearLayoutManager(this)
        recycler.adapter = adapter

        etSearch.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {
                val q = s?.toString() ?: ""
                btnClear.visibility = if (q.isEmpty()) View.GONE else View.VISIBLE
                adapter.filter(q)
                txtEmpty.visibility = if (adapter.itemCount == 0) View.VISIBLE else View.GONE
            }
            override fun afterTextChanged(s: Editable?) {}
        })

        btnClear.setOnClickListener { etSearch.text.clear() }
        btnClose.setOnClickListener { dialog.dismiss() }

        dialog.show()
    }

    private fun refocusInput() {
        editBarcodeCatch.post {
            editBarcodeCatch.requestFocus()
        }
    }

    private fun checkAndLaunchCamera() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            launchCameraScan()
        } else {
            cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    private fun launchCameraScan() {
        val intent = Intent(this, CameraScanActivity::class.java)
        cameraScanLauncher.launch(intent)
    }

    private fun processBarcode(barcode: String) {
        val cleanBarcode = barcode.trim()
        if (cleanBarcode.isEmpty()) return

        // Prevent duplicate processing of the same scan within 500ms
        val now = System.currentTimeMillis()
        if (cleanBarcode == lastScannedBarcode && now - lastScannedTime < 500) {
            return
        }
        lastScannedBarcode = cleanBarcode
        lastScannedTime = now

        val showroom = activeShowroom
        if (showroom == null) {
            Toast.makeText(this, "⚠️ يرجى اختيار المعرض أولاً!", Toast.LENGTH_LONG).show()
            showShowroomSelectionDialog()
            return
        }

        // Show Ultra-fast Loading State
        layoutPrompt.visibility = View.GONE
        layoutResult.visibility = View.GONE
        layoutNotFound.visibility = View.GONE
        layoutLoading.visibility = View.VISIBLE
        mainScanArea.setBackgroundColor(ContextCompat.getColor(this, R.color.primary))

        executor.execute {
            try {
                val cfg = AppSecurity.getOdooConfig()
                val client = OdooClient(cfg.url, cfg.db, cfg.user, cfg.password)
                val period = ShowroomManager.getSalesPeriod(this@MainActivity)
                val needMonths = ShowroomManager.getNeedMonths(this@MainActivity)

                val details = client.queryProductAndNeeds(
                    barcode = cleanBarcode,
                    showroomLocationId = showroom.locationId,
                    posConfigIds = showroom.posConfigIds,
                    period = period,
                    needMonths = needMonths
                )

                runOnUiThread {
                    layoutLoading.visibility = View.GONE
                    scannedTotalCount++
                    txtScanCount.text = "الأصناف: $scannedTotalCount"

                    if (details != null) {
                        displayProductAndNeedResult(details)
                    } else {
                        displayNotFound(cleanBarcode)
                    }
                    refocusInput()
                }
            } catch (e: Exception) {
                runOnUiThread {
                    layoutLoading.visibility = View.GONE
                    Toast.makeText(this@MainActivity, "خطأ في الاتصال: ${e.message}", Toast.LENGTH_SHORT).show()
                    displayNotFound(cleanBarcode)
                    refocusInput()
                }
            }
        }
    }

    private fun displayProductAndNeedResult(details: ProductNeedDetails) {
        layoutPrompt.visibility = View.GONE
        layoutNotFound.visibility = View.GONE
        layoutResult.visibility = View.VISIBLE

        // 1. English Product Name (Top)
        txtProductNameEn.text = details.nameEn

        // 2. Arabic Product Name (Under English Name)
        txtProductNameAr.text = details.nameAr

        // 3. Barcode Number (Under Arabic Name)
        txtResultBarcode.text = details.barcode

        // 4. Stock Quantity & Unit
        txtStockQty.text = formatQty(details.stockQty)
        txtUnitLabel.text = details.uom

        // 5. Availability Status Pill
        if (details.stockQty > 0) {
            mainScanArea.setBackgroundColor(ContextCompat.getColor(this, R.color.bg_in_stock))
            txtStockStatus.text = "متوفر في المعرض ✅"
            txtStockStatus.setTextColor(ContextCompat.getColor(this, R.color.white))
            playSoundAndVibration(AlertType.IN_STOCK)
        } else if (details.stockQty == 0.0) {
            mainScanArea.setBackgroundColor(ContextCompat.getColor(this, R.color.bg_out_of_stock))
            txtStockStatus.text = "غير متوفر في المعرض (نفد) ❌"
            txtStockStatus.setTextColor(ContextCompat.getColor(this, R.color.white))
            playSoundAndVibration(AlertType.OUT_OF_STOCK)
        } else {
            mainScanArea.setBackgroundColor(ContextCompat.getColor(this, R.color.bg_out_of_stock))
            txtStockStatus.text = "عجز مخزني بالسالب ⚠️"
            txtStockStatus.setTextColor(ContextCompat.getColor(this, R.color.white))
            playSoundAndVibration(AlertType.OUT_OF_STOCK)
        }

        // 6. Box 1: Sales in Period Card
        txtSalesCardTitle.text = "📈 المبيعات (${details.periodLabel})"
        txtSoldQtyVal.text = "${formatQty(details.soldQty)} ${details.uom}"
        txtSoldRateVal.text = "معدل: ${formatQty(details.monthlyRate)} ${details.uom}/شهر (${details.periodDays} يوم)"

        // 7. Box 2: Net Showroom Need After Balance Deduction
        val need = details.netNeed
        val target = details.targetNeed
        val nMonths = details.needMonths
        val uom = details.uom

        if (need > 0) {
            // DEFICIT -> GREEN (+X بحاجة لطلب تزويد)
            txtNetNeedVal.text = "+${formatQty(need)} $uom"
            txtNetNeedVal.setTextColor(Color.parseColor("#10B981"))
            txtNetNeedBadge.text = "🟢 بحاجة لطلب تزويد (+${formatQty(need)} $uom)"
            txtNetNeedBadge.setTextColor(Color.parseColor("#D1FAE5"))
            txtNetNeedBadge.setBackgroundColor(Color.parseColor("#064E3B"))
        } else if (need < 0) {
            // SURPLUS -> RED (-X فائض عن الحاجة)
            val absNeed = Math.abs(need)
            txtNetNeedVal.text = "-${formatQty(absNeed)} $uom"
            txtNetNeedVal.setTextColor(Color.parseColor("#EF4444"))
            txtNetNeedBadge.text = "🔴 فائض عن الحاجة (-${formatQty(absNeed)} $uom)"
            txtNetNeedBadge.setTextColor(Color.parseColor("#FEE2E2"))
            txtNetNeedBadge.setBackgroundColor(Color.parseColor("#7F1D1D"))
        } else {
            // BALANCED -> NEUTRAL SLATE
            txtNetNeedVal.text = "0 $uom"
            txtNetNeedVal.setTextColor(Color.parseColor("#94A3B8"))
            txtNetNeedBadge.text = "⚪ المخزون متوازن (0 $uom)"
            txtNetNeedBadge.setTextColor(Color.parseColor("#F1F5F9"))
            txtNetNeedBadge.setBackgroundColor(Color.parseColor("#1E293B"))
        }
    }

    private fun formatQty(qty: Double): String {
        return if (qty % 1.0 == 0.0) {
            String.format(Locale.US, "%.0f", qty)
        } else {
            String.format(Locale.US, "%.2f", qty)
        }
    }

    private fun displayNotFound(barcode: String) {
        layoutPrompt.visibility = View.GONE
        layoutResult.visibility = View.GONE
        layoutNotFound.visibility = View.VISIBLE

        // UNRECOGNIZED BARCODE -> VIBRANT ORANGE/AMBER SCREEN + ALERT TONE
        mainScanArea.setBackgroundColor(ContextCompat.getColor(this, R.color.bg_not_found))
        txtNotFoundBarcode.text = barcode

        playSoundAndVibration(AlertType.NOT_FOUND)
    }

    // Hardware Scanner Wedge Interceptor
    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (scannerHelper.handleKeyEvent(event)) {
            return true
        }
        return super.dispatchKeyEvent(event)
    }

    override fun onResume() {
        super.onResume()
        refocusInput()
        checkDeviceStatusWithOdoo()

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
                val deviceId = LicenseManager.getDeviceId(this@MainActivity)
                val empName = LicenseManager.getEmployeeName(this@MainActivity)
                val model = "${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL} (Android ${android.os.Build.VERSION.RELEASE})"
                val cfg = AppSecurity.getOdooConfig()
                val client = OdooClient(cfg.url, cfg.db, cfg.user, cfg.password)
                val status = client.registerOrUpdateDevice(deviceId, empName, model, "ShowroomChecker", "1.0")
                if (status == "blocked") {
                    runOnUiThread {
                        LicenseManager.deactivate(this@MainActivity)
                        Toast.makeText(this@MainActivity, "⚠️ تم إلغاء تفعيل هذا الجهاز من قبل الإدارة", Toast.LENGTH_LONG).show()
                        val intent = Intent(this@MainActivity, ActivationActivity::class.java)
                        intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
                        startActivity(intent)
                        finish()
                    }
                } else {
                    // Check for updates in background
                    AppUpdateManager.checkForUpdate(this@MainActivity, client, "1.0")
                }
            } catch (e: Exception) {
                // Ignore background heartbeat network errors
            }
        }
    }

    override fun onPause() {
        super.onPause()
        try {
            unregisterReceiver(honeywellReceiver)
        } catch (e: Exception) {
            // receiver not registered
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        toneGen?.release()
        executor.shutdown()
    }
}
