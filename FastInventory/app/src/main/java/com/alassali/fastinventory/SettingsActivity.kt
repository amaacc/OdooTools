package com.alassali.fastinventory

import android.app.AlertDialog
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class SettingsActivity : AppCompatActivity() {

    private lateinit var settingsManager: SettingsManager
    private lateinit var db: InventoryDatabase

    // Views
    private lateinit var btnBack: ImageButton

    private lateinit var rgThemeMode: RadioGroup
    private lateinit var rbThemeDark: RadioButton
    private lateinit var rbThemeLight: RadioButton

    private lateinit var etDeviceName: EditText
    private lateinit var etDefaultZone: EditText
    private lateinit var btnOpenActivation: Button

    private lateinit var btnTestOdoo: Button
    private lateinit var txtSelectedWarehouse: TextView
    private lateinit var btnSelectWarehouse: Button
    private lateinit var btnDownloadCatalog: Button
    private lateinit var txtCatalogStatus: TextView
    private lateinit var progressCatalogSync: ProgressBar

    private lateinit var etTargetEmail: EditText
    private lateinit var chkEnableSmtp: CheckBox
    private lateinit var layoutSmtpFields: LinearLayout
    private lateinit var etSmtpHost: EditText
    private lateinit var etSmtpPort: EditText
    private lateinit var etSmtpUser: EditText
    private lateinit var etSmtpPass: EditText
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

        btnTestOdoo = findViewById(R.id.btnTestOdoo)
        txtSelectedWarehouse = findViewById(R.id.txtSelectedWarehouse)
        btnSelectWarehouse = findViewById(R.id.btnSelectWarehouse)
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

        // Selected Warehouse
        val whName = settingsManager.getSelectedWarehouseName()
        val whCode = settingsManager.getSelectedWarehouseCode()
        txtSelectedWarehouse.text = if (whCode.isNotBlank()) "[$whCode] $whName" else whName

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
        val whName = settingsManager.getSelectedWarehouseName()

        if (lastSync.isBlank()) {
            txtCatalogStatus.text = getString(R.string.catalog_status_never)
            txtCatalogStatus.setTextColor(getColor(R.color.text_secondary))
        } else {
            txtCatalogStatus.text = "تم حفظ $pCount صنف و $pkgCount كرتون لرصيد ($whName) - آخر تحديث: $lastSync"
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

        btnSelectWarehouse.setOnClickListener {
            openWarehouseSelectionDialog()
        }

        btnDownloadCatalog.setOnClickListener {
            syncCatalogFromOdoo()
        }

        btnSaveSettings.setOnClickListener {
            saveAllSettings()
        }
    }

    private fun testOdooConnection() {
        btnTestOdoo.isEnabled = false
        btnTestOdoo.text = "جاري الفحص والتسجيل في Odoo..."

        Thread {
            try {
                val client = AppSecurity.getEffectiveOdooClient(this)
                val (ok, msg) = client.testConnection()
                var regOk = false
                if (ok) {
                    val deviceId = LicenseManager.getDeviceId(this)
                    val devName = etDeviceName.text.toString().trim().ifBlank { "الهاندهيل 1" }
                    val model = "${Build.MANUFACTURER} ${Build.MODEL} (Android ${Build.VERSION.RELEASE})"
                    val status = client.registerOrUpdateDevice(deviceId, devName, model, "FastInventory", "1.04")
                    regOk = (status != "unknown")
                }

                runOnUiThread {
                    btnTestOdoo.isEnabled = true
                    btnTestOdoo.text = "🔗 فحص الاتصال وتحديث تسجيل الجهاز"
                    val feedback = if (ok) {
                        if (regOk) "✅ تم الاتصال بنجاح وتحديث تسجيل الجهاز في Odoo!"
                        else "✅ الاتصال ناجح، ولكن تعذر تحديث بيانات الجهاز: $msg"
                    } else "❌ فشل الاتصال بـ Odoo: $msg"
                    Toast.makeText(this, feedback, Toast.LENGTH_LONG).show()
                }
            } catch (e: Exception) {
                runOnUiThread {
                    btnTestOdoo.isEnabled = true
                    btnTestOdoo.text = "🔗 فحص الاتصال وتحديث تسجيل الجهاز"
                    Toast.makeText(this, "❌ خطأ في الاتصال: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }.start()
    }

    private fun openWarehouseSelectionDialog() {
        btnSelectWarehouse.isEnabled = false
        btnSelectWarehouse.text = "جاري جلب المعارض من Odoo..."

        Thread {
            try {
                val client = AppSecurity.getEffectiveOdooClient(this)
                val warehouses = client.fetchAllWarehouses()

                val arr = JSONArray()
                for (w in warehouses) {
                    val o = JSONObject().apply {
                        put("id", w.id)
                        put("name", w.name)
                        put("code", w.code)
                        w.lotStockId?.let { put("lot_stock_id", it) }
                    }
                    arr.put(o)
                }
                settingsManager.setCachedWarehousesJson(arr.toString())

                runOnUiThread {
                    btnSelectWarehouse.isEnabled = true
                    btnSelectWarehouse.text = "🔄 اختيار وتحديث المعرض من Odoo"

                    val items = mutableListOf<WarehouseItem>()
                    items.add(WarehouseItem(0, "المخزون العام (الشركة بالكامل)", "", null))
                    items.addAll(warehouses)

                    val displayNames = items.map { it.toString() }.toTypedArray()
                    val currentId = settingsManager.getSelectedWarehouseId()
                    val checkedItem = items.indexOfFirst { it.id == currentId }.coerceAtLeast(0)

                    AlertDialog.Builder(this)
                        .setTitle("🏬 اختر المعرض أو المستودع المستهدف للجرد")
                        .setSingleChoiceItems(displayNames, checkedItem) { dialog, which ->
                            val chosen = items[which]
                            settingsManager.setSelectedWarehouse(
                                id = chosen.id,
                                code = chosen.code,
                                name = chosen.name,
                                lotStockId = chosen.lotStockId ?: 0
                            )
                            txtSelectedWarehouse.text = chosen.toString()
                            updateCatalogStatusText()
                            Toast.makeText(this, "تم اختيار: ${chosen.name}", Toast.LENGTH_SHORT).show()
                            dialog.dismiss()
                        }
                        .setNegativeButton("إلغاء", null)
                        .show()
                }
            } catch (e: Exception) {
                runOnUiThread {
                    btnSelectWarehouse.isEnabled = true
                    btnSelectWarehouse.text = "🔄 اختيار وتحديث المعرض من Odoo"
                    Toast.makeText(this, "تعذر جلب المعارض: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }.start()
    }

    private fun syncCatalogFromOdoo() {
        progressCatalogSync.visibility = View.VISIBLE
        btnDownloadCatalog.isEnabled = false
        val targetWhName = settingsManager.getSelectedWarehouseName()
        txtCatalogStatus.text = "جاري الاتصال بـ Odoo وتحميل أصناف ورصيد ($targetWhName)..."

        val whId = settingsManager.getSelectedWarehouseId()
        val lotId = settingsManager.getSelectedWarehouseLotStockId()

        Thread {
            try {
                val client = AppSecurity.getEffectiveOdooClient(this)
                if (!client.authenticate()) {
                    throw IllegalStateException(client.lastError ?: "فشل الاتصال بـ Odoo")
                }

                // 1. Download Packagings
                runOnUiThread { txtCatalogStatus.text = "جاري تحميل باركودات العبوات والكراتين..." }
                val packagings = client.downloadAllPackagings()

                // 2. Download Products with location/warehouse context
                val products = client.downloadAllProducts(
                    warehouseId = whId,
                    warehouseLotStockId = lotId,
                    warehouseName = targetWhName
                ) { fetched, _ ->
                    runOnUiThread {
                        txtCatalogStatus.text = "تم تحميل $fetched صنف مع رصيد $targetWhName..."
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
                    Toast.makeText(this, "✅ تمت مزامنة ${products.size} صنف و ${packagings.size} كرتون بنجاح لمعرض ($targetWhName)!", Toast.LENGTH_LONG).show()
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

        val email = etTargetEmail.text.toString().trim()
        val smtpEnabled = chkEnableSmtp.isChecked
        val smtpHost = etSmtpHost.text.toString().trim()
        val smtpPort = etSmtpPort.text.toString().trim().toIntOrNull() ?: 587
        val smtpUser = etSmtpUser.text.toString().trim()
        val smtpPass = etSmtpPass.text.toString().trim()
        val smtpSsl = chkSmtpSsl.isChecked

        settingsManager.setDeviceName(devName.ifBlank { "الهاندهيل 1" })
        settingsManager.setDefaultZone(defZone.ifBlank { "الرف العام" })

        settingsManager.setTargetEmail(email)
        settingsManager.setSmtpEnabled(smtpEnabled)
        settingsManager.setSmtpHost(smtpHost)
        settingsManager.setSmtpPort(smtpPort)
        settingsManager.setSmtpUser(smtpUser)
        settingsManager.setSmtpPassword(smtpPass)
        settingsManager.setSmtpSsl(smtpSsl)

        // Sync device update with Odoo in background
        AppSecurity.registerDeviceNow(this, devName) { _, _ -> }

        Toast.makeText(this, "✅ تم حفظ الإعدادات بنجاح!", Toast.LENGTH_SHORT).show()
        finish()
    }
}
