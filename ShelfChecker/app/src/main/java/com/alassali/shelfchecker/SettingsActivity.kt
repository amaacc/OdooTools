package com.alassali.shelfchecker

import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.Executors

class SettingsActivity : AppCompatActivity() {

    private lateinit var etReportEmail: EditText
    private lateinit var txtLastUpdate: TextView
    private lateinit var txtDownloadProgress: TextView
    private lateinit var txtConnectionStatus: TextView
    private lateinit var progressDownload: ProgressBar
    private lateinit var btnDownloadPrices: Button
    private lateinit var btnTestConnection: Button
    private lateinit var settingsManager: SettingsManager
    private lateinit var priceDb: PriceDatabase

    private val executor = Executors.newSingleThreadExecutor()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        settingsManager = SettingsManager(this)
        priceDb = PriceDatabase(this)

        etReportEmail = findViewById(R.id.editReportEmail)
        txtLastUpdate = findViewById(R.id.txtLastUpdate)
        txtDownloadProgress = findViewById(R.id.txtDownloadProgress)
        txtConnectionStatus = findViewById(R.id.txtConnectionStatus)
        progressDownload = findViewById(R.id.progressDownload)
        btnDownloadPrices = findViewById(R.id.btnDownloadPrices)
        btnTestConnection = findViewById(R.id.btnTestConnection)

        etReportEmail.setText(settingsManager.getReportEmail())
        updateLastUpdateText()

        btnTestConnection.setOnClickListener {
            runConnectionTest()
        }

        btnDownloadPrices.setOnClickListener {
            downloadPrices()
        }

        findViewById<Button>(R.id.btnSave).setOnClickListener {
            saveSettings()
        }
    }

    private fun runConnectionTest() {
        txtConnectionStatus.visibility = View.VISIBLE
        txtConnectionStatus.text = "جاري الاتصال بـ Odoo..."
        txtConnectionStatus.setTextColor(0xFF555555.toInt())
        btnTestConnection.isEnabled = false

        executor.execute {
            try {
                val config = AppSecurity.getOdooConfig()
                val client = OdooClient(config.url, config.db, config.user, config.password)
                val (success, message) = client.testConnection()
                runOnUiThread {
                    btnTestConnection.isEnabled = true
                    txtConnectionStatus.text = message
                    txtConnectionStatus.setTextColor(
                        if (success) 0xFF2E7D32.toInt() else 0xFFD32F2F.toInt()
                    )
                }
            } catch (e: Exception) {
                runOnUiThread {
                    btnTestConnection.isEnabled = true
                    txtConnectionStatus.text = "❌ خطأ: ${e.message}"
                    txtConnectionStatus.setTextColor(0xFFD32F2F.toInt())
                }
            }
        }
    }

    private fun downloadPrices() {
        progressDownload.visibility = View.VISIBLE
        txtDownloadProgress.visibility = View.VISIBLE
        txtDownloadProgress.text = "جاري تهيئة الاتصال..."
        btnDownloadPrices.isEnabled = false

        executor.execute {
            try {
                val config = AppSecurity.getOdooConfig()
                val client = OdooClient(config.url, config.db, config.user, config.password)

                priceDb.clearPrices()

                val prices = client.downloadAllPrices { batch, downloaded, total ->
                    priceDb.insertBatch(batch)
                    runOnUiThread {
                        txtDownloadProgress.text = "جاري تنزيل الأسعار: $downloaded من $total صنف..."
                    }
                }

                val savedCount = priceDb.getCount()
                if (savedCount > 0) {
                    val sdf = SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.getDefault())
                    val timeStr = sdf.format(Date())
                    priceDb.setLastUpdateTime(timeStr)

                    runOnUiThread {
                        progressDownload.visibility = View.GONE
                        txtDownloadProgress.visibility = View.GONE
                        btnDownloadPrices.isEnabled = true
                        updateLastUpdateText()

                        AlertDialog.Builder(this@SettingsActivity)
                            .setTitle("تم التحميل بنجاح ✅")
                            .setMessage("تم تنزيل وحفظ $savedCount صنف في قاعدة البيانات المحلية لجهاز Honeywell بنجاح.\n\nيمكنك الآن فحص الأرفف في أي وقت وبدون إنترنت.")
                            .setPositiveButton("حسناً", null)
                            .show()
                    }
                } else {
                    runOnUiThread {
                        progressDownload.visibility = View.GONE
                        txtDownloadProgress.visibility = View.GONE
                        btnDownloadPrices.isEnabled = true
                        Toast.makeText(this@SettingsActivity, "لم يتم العثور على أي أصناف للتحميل", Toast.LENGTH_LONG).show()
                    }
                }
            } catch (e: Exception) {
                runOnUiThread {
                    progressDownload.visibility = View.GONE
                    txtDownloadProgress.visibility = View.GONE
                    btnDownloadPrices.isEnabled = true

                    AlertDialog.Builder(this@SettingsActivity)
                        .setTitle("خطأ أثناء التحميل ❌")
                        .setMessage("تعذر استكمال تنزيل الأسعار:\n\n${e.message ?: e.javaClass.simpleName}\n\nيرجى التأكد من اتصال الجهاز بشبكة الـ Wi-Fi والضغط على 'فحص الاتصال'.")
                        .setPositiveButton("حسناً", null)
                        .show()
                }
            }
        }
    }

    private fun updateLastUpdateText() {
        val lastUpdate = priceDb.getLastUpdateTime()
        val count = priceDb.getCount()
        txtLastUpdate.text = if (lastUpdate.isNotEmpty()) {
            "آخر تحديث: $lastUpdate ($count صنف محفوظ محلياً)"
        } else {
            "لم يتم تنزيل الأسعار بعد"
        }
    }

    private fun saveSettings() {
        val email = etReportEmail.text.toString().trim()
        if (email.isEmpty()) {
            Toast.makeText(this, "يرجى إدخال البريد الإلكتروني للتقارير", Toast.LENGTH_SHORT).show()
            return
        }

        settingsManager.saveReportEmail(email)
        Toast.makeText(this, "تم حفظ الإعدادات", Toast.LENGTH_SHORT).show()
        finish()
    }
}
