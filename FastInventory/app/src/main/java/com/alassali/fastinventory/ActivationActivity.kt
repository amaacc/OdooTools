package com.alassali.fastinventory

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.ImageButton
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.textfield.TextInputEditText

class ActivationActivity : AppCompatActivity() {

    private lateinit var btnBack: ImageButton
    private lateinit var txtDeviceId: TextView
    private lateinit var btnCopyId: Button
    private lateinit var etLicenseKey: TextInputEditText
    private lateinit var txtStatus: TextView
    private lateinit var btnSubmit: Button
    private lateinit var btnSyncOdoo: Button
    private lateinit var progressSync: ProgressBar

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_activation)

        btnBack = findViewById(R.id.btnActivationBack)
        txtDeviceId = findViewById(R.id.txtDeviceId)
        btnCopyId = findViewById(R.id.btnCopyDeviceId)
        etLicenseKey = findViewById(R.id.etLicenseKey)
        txtStatus = findViewById(R.id.txtActivationStatus)
        btnSubmit = findViewById(R.id.btnSubmitActivation)
        btnSyncOdoo = findViewById(R.id.btnSyncOdoo)
        progressSync = findViewById(R.id.progressSync)

        btnBack.setOnClickListener { finish() }

        val deviceId = LicenseManager.getDeviceId(this)
        txtDeviceId.text = deviceId

        btnCopyId.setOnClickListener {
            val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val clip = ClipData.newPlainText("Device ID", deviceId)
            clipboard.setPrimaryClip(clip)
            Toast.makeText(this, "📋 تم نسخ معرّف الجهاز إلى الحافظة", Toast.LENGTH_SHORT).show()
        }

        updateStatus()

        btnSubmit.setOnClickListener {
            val inputKey = etLicenseKey.text.toString().trim()
            if (inputKey.isBlank()) {
                Toast.makeText(this, "يرجى إدخال مفتاح التفعيل", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            if (LicenseManager.activate(this, inputKey)) {
                Toast.makeText(this, "🎉 تم التحقق من مفتاح التفعيل محلياً!", Toast.LENGTH_SHORT).show()
                updateStatus()
                // Sync immediately with Odoo
                triggerOdooSync(closeOnSuccess = true)
            } else {
                Toast.makeText(this, getString(R.string.license_invalid), Toast.LENGTH_LONG).show()
            }
        }

        btnSyncOdoo.setOnClickListener {
            triggerOdooSync(closeOnSuccess = false)
        }

        // Background heartbeat check on open
        if (LicenseManager.isActivated(this)) {
            AppSecurity.verifyDeviceStatusAsync(this)
        }
    }

    private fun triggerOdooSync(closeOnSuccess: Boolean) {
        progressSync.visibility = View.VISIBLE
        btnSyncOdoo.isEnabled = false
        btnSubmit.isEnabled = false
        txtStatus.text = "⏳ جاري مزامنة ترخيص الجهاز مع سيرفر Odoo..."
        txtStatus.setTextColor(getColor(R.color.text_cyan))

        val settings = SettingsManager(this)
        val devName = settings.getDeviceName()

        AppSecurity.registerDeviceNow(this, devName) { success, msg ->
            progressSync.visibility = View.GONE
            btnSyncOdoo.isEnabled = true
            btnSubmit.isEnabled = true
            updateStatus()

            if (success) {
                Toast.makeText(this, "✅ تم تسجيل وتفعيل الجهاز في سيرفر Odoo بنجاح!", Toast.LENGTH_LONG).show()
                if (closeOnSuccess) {
                    finish()
                }
            } else {
                Toast.makeText(this, "تنبيه Odoo: $msg", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun updateStatus() {
        if (LicenseManager.isActivated(this)) {
            txtStatus.text = "✅ ${getString(R.string.license_active)}"
            txtStatus.setTextColor(getColor(R.color.text_success))
            btnSubmit.text = "إعادة التفعيل أو التحديث"
            btnSyncOdoo.visibility = View.VISIBLE
        } else {
            txtStatus.text = "⚠️ الجهاز غير مفعل. يتطلب ترخيصاً صالحاً."
            txtStatus.setTextColor(getColor(R.color.text_warning))
            btnSubmit.text = getString(R.string.btn_activate)
            btnSyncOdoo.visibility = View.GONE
        }
    }
}
