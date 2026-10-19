package com.alassali.fastinventory

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.Bundle
import android.widget.Button
import android.widget.ImageButton
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

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_activation)

        btnBack = findViewById(R.id.btnActivationBack)
        txtDeviceId = findViewById(R.id.txtDeviceId)
        btnCopyId = findViewById(R.id.btnCopyDeviceId)
        etLicenseKey = findViewById(R.id.etLicenseKey)
        txtStatus = findViewById(R.id.txtActivationStatus)
        btnSubmit = findViewById(R.id.btnSubmitActivation)

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
                Toast.makeText(this, "🎉 تم تفعيل وترخيص الجهاز بنجاح!", Toast.LENGTH_LONG).show()
                updateStatus()
                finish()
            } else {
                Toast.makeText(this, getString(R.string.license_invalid), Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun updateStatus() {
        if (LicenseManager.isActivated(this)) {
            txtStatus.text = "✅ ${getString(R.string.license_active)}"
            txtStatus.setTextColor(getColor(R.color.text_success))
            btnSubmit.text = "إعادة التفعيل أو التحديث"
        } else {
            txtStatus.text = "⚠️ الجهاز غير مفعل. يتطلب ترخيصاً صالحاً."
            txtStatus.setTextColor(getColor(R.color.text_warning))
            btnSubmit.text = getString(R.string.btn_activate)
        }
    }
}
