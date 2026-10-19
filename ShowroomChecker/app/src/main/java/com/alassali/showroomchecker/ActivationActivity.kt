package com.alassali.showroomchecker

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.button.MaterialButton
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout
import java.util.concurrent.Executors

class ActivationActivity : AppCompatActivity() {

    private lateinit var txtDeviceId: TextView
    private lateinit var btnCopyDeviceId: MaterialButton
    private lateinit var btnShareDeviceId: MaterialButton
    private lateinit var editEmployeeName: TextInputEditText
    private lateinit var layoutLicenseKey: TextInputLayout
    private lateinit var editLicenseKey: TextInputEditText
    private lateinit var btnActivate: MaterialButton

    private val executor = Executors.newSingleThreadExecutor()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_activation)

        txtDeviceId = findViewById(R.id.txtDeviceId)
        btnCopyDeviceId = findViewById(R.id.btnCopyDeviceId)
        btnShareDeviceId = findViewById(R.id.btnShareDeviceId)
        editEmployeeName = findViewById(R.id.editEmployeeName)
        layoutLicenseKey = findViewById(R.id.layoutLicenseKey)
        editLicenseKey = findViewById(R.id.editLicenseKey)
        btnActivate = findViewById(R.id.btnActivate)

        // Smart formatting for license key:
        // Allows user to type characters without manual hyphens,
        // and handles paste with or without hyphens cleanly.
        var isFormatting = false
        editLicenseKey.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}

            override fun afterTextChanged(s: Editable?) {
                if (isFormatting || s == null) return
                isFormatting = true

                try {
                    // Extract only alphanumeric characters and uppercase
                    val clean = s.toString()
                        .uppercase()
                        .filter { it in 'A'..'Z' || it in '0'..'9' }
                        .take(16)

                    // Format as XXXX-XXXX-XXXX-XXXX
                    val sb = StringBuilder()
                    for (i in clean.indices) {
                        if (i > 0 && i % 4 == 0) {
                            sb.append('-')
                        }
                        sb.append(clean[i])
                    }
                    val formatted = sb.toString()

                    if (formatted != s.toString()) {
                        s.replace(0, s.length, formatted)
                    }
                } finally {
                    isFormatting = false
                }
            }
        })

        val deviceId = LicenseManager.getDeviceId(this)
        txtDeviceId.text = deviceId

        val savedName = LicenseManager.getEmployeeName(this)
        if (savedName.isNotBlank()) {
            editEmployeeName.setText(savedName)
        }

        btnCopyDeviceId.setOnClickListener {
            val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val clip = ClipData.newPlainText("Device ID", deviceId)
            clipboard.setPrimaryClip(clip)
            Toast.makeText(this, "تم نسخ معرف الجهاز بنجاح 📋", Toast.LENGTH_SHORT).show()
        }

        btnShareDeviceId.setOnClickListener {
            val empName = editEmployeeName.text?.toString()?.trim() ?: ""
            val textToSend = if (empName.isNotEmpty()) {
                "السلام عليكم،\nمعرف جهاز ShowroomChecker الخاص بفرع العسلي:\nاسم الموظف/المعرض: $empName\nالمعرف: $deviceId"
            } else {
                "السلام عليكم،\nمعرف جهاز ShowroomChecker الخاص بفرع العسلي:\nالمعرف: $deviceId"
            }
            val shareIntent = Intent(Intent.ACTION_SEND).apply {
                type = "text/plain"
                putExtra(Intent.EXTRA_SUBJECT, "معرف جهاز فحص رصيد واحتياج المعارض")
                putExtra(Intent.EXTRA_TEXT, textToSend)
            }
            startActivity(Intent.createChooser(shareIntent, "مشاركة معرف الجهاز"))
        }

        btnActivate.setOnClickListener {
            val key = editLicenseKey.text?.toString()?.trim() ?: ""
            val empName = editEmployeeName.text?.toString()?.trim() ?: ""

            if (key.isBlank()) {
                layoutLicenseKey.error = "يرجى إدخال كود التفعيل"
                return@setOnClickListener
            }

            layoutLicenseKey.error = null
            val success = LicenseManager.activate(this, key)
            if (success) {
                if (empName.isNotEmpty()) {
                    LicenseManager.setEmployeeName(this, empName)
                }

                // Register with Odoo in background
                executor.execute {
                    try {
                        val cfg = AppSecurity.getOdooConfig()
                        val client = OdooClient(cfg.url, cfg.db, cfg.user, cfg.password)
                        val model = "${Build.MANUFACTURER} ${Build.MODEL} (Android ${Build.VERSION.RELEASE})"
                        client.registerOrUpdateDevice(deviceId, empName, model, "ShowroomChecker", "1.0")
                    } catch (e: Exception) {
                        e.printStackTrace()
                    }
                }

                Toast.makeText(this, "✅ تم تفعيل ترخيص الجهاز بنجاح!", Toast.LENGTH_LONG).show()
                setResult(RESULT_OK)
                if (isTaskRoot) {
                    startActivity(Intent(this, MainActivity::class.java))
                }
                finish()
            } else {
                layoutLicenseKey.error = "❌ كود التفعيل غير صالح لهذا الجهاز!"
                Toast.makeText(this, "كود التفعيل غير مطابق لمعرف الجهاز", Toast.LENGTH_SHORT).show()
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        executor.shutdown()
    }
}
