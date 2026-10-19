package com.alassali.fastinventory

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.textfield.TextInputEditText
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class SettingsActivity : AppCompatActivity() {

    private lateinit var settingsManager: SettingsManager
    private lateinit var db: InventoryDatabase

    private lateinit var btnBack: ImageButton
    private lateinit var rgThemeMode: RadioGroup
    private lateinit var rbThemeDark: RadioButton
    private lateinit var rbThemeLight: RadioButton

    private lateinit var etDeviceName: TextInputEditText
    private lateinit var etDefaultZone: TextInputEditText
    private lateinit var btnOpenActivation: Button

    private lateinit var etServerUrl: TextInputEditText
    private lateinit var etDatabase: TextInputEditText
    private lateinit var etUsername: TextInputEditText
    private lateinit var etPassword: TextInputEditText
    private lateinit var btnTestOdoo: Button
    private lateinit var btnDownloadCatalog: Button
    private lateinit var txtCatalogStatus: TextView
    private lateinit var progressCatalogSync: ProgressBar

    private lateinit var etTargetEmail: TextInputEditText
    private lateinit var chkEnableSmtp: CheckBox
    private lateinit var layoutSmtpFields: LinearLayout
    private lateinit var etSmtpHost: TextInputEditText
    private lateinit var etSmtpPort: TextInputEditText
    private lateinit var etSmtpUser: TextInputEditText
    private lateinit var etSmtpPass: TextInputEditText
    private lateinit var chkSmtpSsl: CheckBox

    private lateinit var btnSaveSettings: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        settingsManager = SettingsManager(this)
        db = InventoryDatabase(this)

        setContentView(R.layout.activity_settings)

        bindViews()
        loadSavedValues()
        setupListeners()
    }

    private fun bindViews() {
        btnBack = findViewById(R.id.btnSettingsBack)

        rgThemeMode = findViewById(R.id.rgThemeMode)
        rbThemeDark = findViewById(R.id.rbThemeDark)
        rbThemeLight = findViewById(R.id.rbThemeLight)

        etDeviceName = findViewById(R.id.etDeviceName)
        etDefaultZone = findViewById(R.id.etDefaultZone)
        btnOpenActivation = findViewById(R.id.btnOpenActivation)

        etServerUrl = findViewById(R.id.etServerUrl)
        etDatabase = findViewById(R.id.etDatabase)
        etUsername = findViewById(R.id.etUsername)
        etPassword = findViewById(R.id.etPassword)
        btnTestOdoo = findViewById(R.id.btnTestOdoo)
        btnDownloadCatalog = findViewById(R.id.btnDownloadCatalog)
        txtCatalogStatus = findViewById(R.id.txtCatalogStatus)
        progressCatalogSync = findViewById(R.id.progressCatalogSync)

        etTargetEmail = findViewById(R.id.etTargetEmail)
        chkEnableSmtp = findViewById(R.id.chkEnableSmtp)
        layoutSmtpFields = findViewById(R.id.layoutSmtpFields)
        etSmtpHost = findViewById(R.id.etSmtpHost)
        etSmtpPort = findViewById(R.id.etSmtpPort)
        etSmtpUser = findViewById(R.id.etSmtpUser)
        etSmtpPass = findViewById(R.id.etSmtpPass)
        chkSmtpSsl = findViewById(R.id.chkSmtpSsl)

        btnSaveSettings = findViewById(R.id.btnSaveSettings)
    }

    private fun loadSavedValues() {
        // Theme
        if (settingsManager.getThemeMode() == "light") {
            rbThemeLight.isChecked = true
        } else {
            rbThemeDark.isChecked = true
        }

        // Device
        etDeviceName.setText(settingsManager.getDeviceName())
        etDefaultZone.setText(settingsManager.getDefaultZone())

        // Odoo (Uses company defaults if not entered)
        etServerUrl.setText(settingsManager.getServerUrl())
        etDatabase.setText(settingsManager.getDatabase())
        etUsername.setText(settingsManager.getUsername())
        etPassword.setText(settingsManager.getPassword())

        // Email & SMTP
        etTargetEmail.setText(settingsManager.getTargetEmail())

        val isSmtp = settingsManager.isSmtpEnabled()
        chkEnableSmtp.isChecked = isSmtp
        layoutSmtpFields.visibility = if (isSmtp) View.VISIBLE else View.GONE

        etSmtpHost.setText(settingsManager.getSmtpHost())
        etSmtpPort.setText(settingsManager.getSmtpPort().toString())
        etSmtpUser.setText(settingsManager.getSmtpUser())
        etSmtpPass.setText(settingsManager.getSmtpPassword())
        chkSmtpSsl.isChecked = settingsManager.isSmtpSsl()

        updateCatalogStatusText()
    }

    private fun updateCatalogStatusText() {
        val lastSync = settingsManager.getLastCatalogSync()
        val pCount = settingsManager.getCatalogItemCount()
        val pkgCount = settingsManager.getCatalogPackagingCount()

        if (lastSync.isBlank()) {
            txtCatalogStatus.text = getString(R.string.catalog_status_never)
            txtCatalogStatus.setTextColor(getColor(R.color.text_secondary))
        } else {
            txtCatalogStatus.text = getString(R.string.catalog_status_updated, pCount, pkgCount, lastSync)
            txtCatalogStatus.setTextColor(getColor(R.color.text_success))
        }
    }

    private fun setupListeners() {
        btnBack.setOnClickListener { finish() }

        rgThemeMode.setOnCheckedChangeListener { _, checkedId ->
            val targetMode = if (checkedId == R.id.rbThemeLight) "light" else "dark"
            if (targetMode != settingsManager.getThemeMode()) {
                settingsManager.setThemeMode(targetMode)
            }
        }

        btnOpenActivation.setOnClickListener {
            startActivity(Intent(this, ActivationActivity::class.java))
        }

        chkEnableSmtp.setOnCheckedChangeListener { _, isChecked ->
            layoutSmtpFields.visibility = if (isChecked) View.VISIBLE else View.GONE
        }

        btnTestOdoo.setOnClickListener {
            testOdooConnection()
        }

        btnDownloadCatalog.setOnClickListener {
            syncCatalogFromOdoo()
        }

        btnSaveSettings.setOnClickListener {
            saveAllSettings()
        }
    }

    private fun testOdooConnection() {
        val url = etServerUrl.text.toString().trim()
        val dbName = etDatabase.text.toString().trim()
        val user = etUsername.text.toString().trim()
        val pass = etPassword.text.toString().trim()

        if (url.isBlank() || dbName.isBlank() || user.isBlank() || pass.isBlank()) {
            Toast.makeText(this, "يرجى تعبئة كافة حقول الاتصال بـ Odoo", Toast.LENGTH_SHORT).show()
            return
        }

        btnTestOdoo.isEnabled = false
        btnTestOdoo.text = "جاري الفحص والتسجيل..."

        Thread {
            val client = OdooClient(url, dbName, user, pass)
            val (ok, msg) = client.testConnection()
            var regOk = false
            if (ok) {
                try {
                    val deviceId = LicenseManager.getDeviceId(this)
                    val devName = etDeviceName.text.toString().trim().ifBlank { "الهاندهيل 1" }
                    val model = "${Build.MANUFACTURER} ${Build.MODEL} (Android ${Build.VERSION.RELEASE})"
                    val status = client.registerOrUpdateDevice(deviceId, devName, model, "FastInventory", "1.02")
                    regOk = (status != "unknown")
                } catch (e: Exception) {
                    e.printStackTrace()
                }
            }

            runOnUiThread {
                btnTestOdoo.isEnabled = true
                btnTestOdoo.text = "🔗 اختبار وتسجيل الجهاز"
                val feedback = if (ok) {
                    if (regOk) "✅ تم الاتصال بنجاح وتحديث تسجيل الجهاز في Odoo!"
                    else "✅ الاتصال ناجح، ولكن تعذر تحديث بيانات الجهاز: $msg"
                } else msg
                Toast.makeText(this, feedback, Toast.LENGTH_LONG).show()
            }
        }.start()
    }

    private fun syncCatalogFromOdoo() {
        val url = etServerUrl.text.toString().trim()
        val dbName = etDatabase.text.toString().trim()
        val user = etUsername.text.toString().trim()
        val pass = etPassword.text.toString().trim()

        if (url.isBlank() || dbName.isBlank() || user.isBlank() || pass.isBlank()) {
            Toast.makeText(this, "يرجى تعبئة كافة حقول Odoo أولاً", Toast.LENGTH_SHORT).show()
            return
        }

        progressCatalogSync.visibility = View.VISIBLE
        btnDownloadCatalog.isEnabled = false
        txtCatalogStatus.text = "جاري الاتصال بـ Odoo وتحميل الأصناف والعبوات..."

        Thread {
            try {
                val client = OdooClient(url, dbName, user, pass)
                if (!client.authenticate()) {
                    throw IllegalStateException(client.lastError ?: "فشل الاتصال بـ Odoo")
                }

                // 1. Download Packagings
                runOnUiThread { txtCatalogStatus.text = "جاري تحميل باركودات العبوات والكراتين..." }
                val packagings = client.downloadAllPackagings()

                // 2. Download Products
                val products = client.downloadAllProducts { fetched, _ ->
                    runOnUiThread {
                        txtCatalogStatus.text = "تم تحميل $fetched صنف من أودو..."
                    }
                }

                // 3. Save to SQLite in batch transactions
                runOnUiThread { txtCatalogStatus.text = "جاري حفظ البيانات في قاعدة البيانات المحلية..." }
                db.insertPackagingsBatch(packagings)
                db.insertProductsBatch(products)

                val now = SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.US).format(Date())
                settingsManager.setLastCatalogSync(now)
                settingsManager.setCatalogItemCount(products.size)
                settingsManager.setCatalogPackagingCount(packagings.size)

                runOnUiThread {
                    progressCatalogSync.visibility = View.GONE
                    btnDownloadCatalog.isEnabled = true
                    updateCatalogStatusText()
                    Toast.makeText(this, "✅ تمت مزامنة ${products.size} صنف و ${packagings.size} كرتون بنجاح!", Toast.LENGTH_LONG).show()
                }
            } catch (e: Exception) {
                e.printStackTrace()
                runOnUiThread {
                    progressCatalogSync.visibility = View.GONE
                    btnDownloadCatalog.isEnabled = true
                    txtCatalogStatus.text = "❌ خطأ أثناء المزامنة: ${e.message}"
                    txtCatalogStatus.setTextColor(getColor(R.color.text_danger))
                    Toast.makeText(this, "فشلت المزامنة: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }.start()
    }

    private fun saveAllSettings() {
        val devName = etDeviceName.text.toString().trim()
        val defZone = etDefaultZone.text.toString().trim()

        val url = etServerUrl.text.toString().trim()
        val dbName = etDatabase.text.toString().trim()
        val user = etUsername.text.toString().trim()
        val pass = etPassword.text.toString().trim()

        val email = etTargetEmail.text.toString().trim()
        val smtpEnabled = chkEnableSmtp.isChecked
        val smtpHost = etSmtpHost.text.toString().trim()
        val smtpPort = etSmtpPort.text.toString().trim().toIntOrNull() ?: 587
        val smtpUser = etSmtpUser.text.toString().trim()
        val smtpPass = etSmtpPass.text.toString().trim()
        val smtpSsl = chkSmtpSsl.isChecked

        settingsManager.setDeviceName(devName.ifBlank { "الهاندهيل 1" })
        settingsManager.setDefaultZone(defZone.ifBlank { "الرف العام" })

        settingsManager.saveOdooCredentials(url, dbName, user, pass)

        settingsManager.setTargetEmail(email)
        settingsManager.setSmtpEnabled(smtpEnabled)
        settingsManager.setSmtpHost(smtpHost)
        settingsManager.setSmtpPort(smtpPort)
        settingsManager.setSmtpUser(smtpUser)
        settingsManager.setSmtpPassword(smtpPass)
        settingsManager.setSmtpSsl(smtpSsl)

        // Sync device update with Odoo in background
        AppSecurity.registerDeviceNow(this, devName) { _, _ -> }

        Toast.makeText(this, "✅ تم حفظ كافة الإعدادات ومزامنة الجهاز!", Toast.LENGTH_SHORT).show()
        finish()
    }
}
