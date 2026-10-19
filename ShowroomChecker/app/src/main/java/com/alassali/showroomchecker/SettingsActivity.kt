package com.alassali.showroomchecker

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.ImageButton
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import java.util.concurrent.Executors

class SettingsActivity : AppCompatActivity() {

    private lateinit var btnBack: ImageButton
    private lateinit var btnTestConnection: Button
    private lateinit var txtConnectionStatus: TextView
    private lateinit var btnRefreshShowrooms: Button
    private lateinit var txtShowroomsCount: TextView
    private lateinit var spinnerSalesPeriod: Spinner
    private lateinit var spinnerNeedMonths: Spinner
    private lateinit var txtDeviceId: TextView
    private lateinit var btnCopyDeviceId: Button
    private lateinit var txtLicenseStatus: TextView
    private lateinit var btnManageLicense: Button

    private val salesPeriodKeys = listOf(
        "this_year",
        "last_30_days",
        "last_60_days",
        "last_90_days",
        "last_365_days",
        "all"
    )
    private val salesPeriodLabels = listOf(
        "منذ بداية العام الحالي (افتراضي)",
        "آخر 30 يوم",
        "آخر 60 يوم",
        "آخر 90 يوم",
        "آخر 365 يوم",
        "كامل المبيعات التاريخية"
    )

    private val needMonthValues = listOf(1, 2, 3, 4, 6, 12)
    private val needMonthLabels = listOf(
        "1 شهر",
        "2 شهر (افتراضي)",
        "3 شهور",
        "4 شهور",
        "6 شهور",
        "12 شهر (سنة كاملة)"
    )

    private val executor = Executors.newSingleThreadExecutor()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        btnBack = findViewById(R.id.btnBack)
        btnTestConnection = findViewById(R.id.btnTestConnection)
        txtConnectionStatus = findViewById(R.id.txtConnectionStatus)
        btnRefreshShowrooms = findViewById(R.id.btnRefreshShowrooms)
        txtShowroomsCount = findViewById(R.id.txtShowroomsCount)
        spinnerSalesPeriod = findViewById(R.id.spinnerSalesPeriod)
        spinnerNeedMonths = findViewById(R.id.spinnerNeedMonths)
        txtDeviceId = findViewById(R.id.txtDeviceId)
        btnCopyDeviceId = findViewById(R.id.btnCopyDeviceId)
        txtLicenseStatus = findViewById(R.id.txtLicenseStatus)
        btnManageLicense = findViewById(R.id.btnManageLicense)

        btnBack.setOnClickListener { finish() }

        setupSalesAndNeedSpinners()

        // Device ID & License Info
        val deviceId = LicenseManager.getDeviceId(this)
        txtDeviceId.text = deviceId

        btnCopyDeviceId.setOnClickListener {
            val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val clip = ClipData.newPlainText("Device ID", deviceId)
            clipboard.setPrimaryClip(clip)
            Toast.makeText(this, "تم نسخ معرف الجهاز 📋", Toast.LENGTH_SHORT).show()
        }

        updateLicenseUI()

        btnManageLicense.setOnClickListener {
            startActivity(Intent(this, ActivationActivity::class.java))
        }

        // Showrooms count
        updateShowroomsCount()

        // Test Connection
        btnTestConnection.setOnClickListener {
            txtConnectionStatus.text = "جاري اختبار الاتصال بسيرفر أودو..."
            txtConnectionStatus.setTextColor(ContextCompat.getColor(this, R.color.text_secondary))
            btnTestConnection.isEnabled = false

            executor.execute {
                try {
                    val cfg = AppSecurity.getOdooConfig()
                    val client = OdooClient(cfg.url, cfg.db, cfg.user, cfg.password)
                    val (success, msg) = client.testConnection()

                    runOnUiThread {
                        btnTestConnection.isEnabled = true
                        txtConnectionStatus.text = msg
                        if (success) {
                            txtConnectionStatus.setTextColor(ContextCompat.getColor(this@SettingsActivity, R.color.stock_green))
                        } else {
                            txtConnectionStatus.setTextColor(ContextCompat.getColor(this@SettingsActivity, R.color.stock_red))
                        }
                    }
                } catch (e: Exception) {
                    runOnUiThread {
                        btnTestConnection.isEnabled = true
                        txtConnectionStatus.text = "❌ خطأ أثناء الاتصال: ${e.message}"
                        txtConnectionStatus.setTextColor(ContextCompat.getColor(this@SettingsActivity, R.color.stock_red))
                    }
                }
            }
        }

        // Refresh Showrooms
        btnRefreshShowrooms.setOnClickListener {
            btnRefreshShowrooms.isEnabled = false
            btnRefreshShowrooms.text = "جاري التحديث من أودو..."

            executor.execute {
                try {
                    val cfg = AppSecurity.getOdooConfig()
                    val client = OdooClient(cfg.url, cfg.db, cfg.user, cfg.password)
                    val liveShowrooms = client.fetchShowrooms()
                    ShowroomManager.saveShowroomsCache(this@SettingsActivity, liveShowrooms)

                    runOnUiThread {
                        btnRefreshShowrooms.isEnabled = true
                        btnRefreshShowrooms.text = getString(R.string.refresh_showrooms)
                        updateShowroomsCount()
                        Toast.makeText(this@SettingsActivity, "✅ تم تحديث ${liveShowrooms.size} معرض من أودو!", Toast.LENGTH_LONG).show()
                    }
                } catch (e: Exception) {
                    runOnUiThread {
                        btnRefreshShowrooms.isEnabled = true
                        btnRefreshShowrooms.text = getString(R.string.refresh_showrooms)
                        Toast.makeText(this@SettingsActivity, "❌ فشل التحديث: ${e.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        updateLicenseUI()
        updateShowroomsCount()
    }

    private fun updateLicenseUI() {
        val activated = LicenseManager.isActivated(this)
        if (activated) {
            txtLicenseStatus.text = getString(R.string.activated)
            txtLicenseStatus.setTextColor(ContextCompat.getColor(this, R.color.stock_green))
        } else {
            txtLicenseStatus.text = getString(R.string.not_activated)
            txtLicenseStatus.setTextColor(ContextCompat.getColor(this, R.color.stock_red))
        }
    }

    private fun updateShowroomsCount() {
        val count = ShowroomManager.getAllShowrooms(this).size
        txtShowroomsCount.text = "المعارض المحفوظة: $count معرض"
    }

    private fun setupSalesAndNeedSpinners() {
        val periodAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, salesPeriodLabels)
        periodAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        spinnerSalesPeriod.adapter = periodAdapter

        val currentPeriod = ShowroomManager.getSalesPeriod(this)
        val periodIdx = salesPeriodKeys.indexOf(currentPeriod).takeIf { it >= 0 } ?: 0
        spinnerSalesPeriod.setSelection(periodIdx)

        spinnerSalesPeriod.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                val selectedKey = salesPeriodKeys[position]
                if (selectedKey != ShowroomManager.getSalesPeriod(this@SettingsActivity)) {
                    ShowroomManager.setSalesPeriod(this@SettingsActivity, selectedKey)
                    Toast.makeText(this@SettingsActivity, "تم حفظ فترة المبيعات: ${salesPeriodLabels[position]}", Toast.LENGTH_SHORT).show()
                }
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }

        val needAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, needMonthLabels)
        needAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        spinnerNeedMonths.adapter = needAdapter

        val currentMonths = ShowroomManager.getNeedMonths(this)
        val monthIdx = needMonthValues.indexOf(currentMonths).takeIf { it >= 0 } ?: 1
        spinnerNeedMonths.setSelection(monthIdx)

        spinnerNeedMonths.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                val selectedMonths = needMonthValues[position]
                if (selectedMonths != ShowroomManager.getNeedMonths(this@SettingsActivity)) {
                    ShowroomManager.setNeedMonths(this@SettingsActivity, selectedMonths)
                    Toast.makeText(this@SettingsActivity, "تم حفظ شهور الاحتياج: ${needMonthLabels[position]}", Toast.LENGTH_SHORT).show()
                }
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        executor.shutdown()
    }
}
