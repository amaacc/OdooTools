package com.alassali.fastinventory

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.view.View
import android.widget.Button
import android.widget.ImageButton
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.cardview.widget.CardView
import java.io.BufferedReader
import java.io.File
import java.io.InputStreamReader
import java.util.Locale

class ConsolidatorActivity : AppCompatActivity() {

    private lateinit var btnBack: ImageButton
    private lateinit var btnPickFiles: Button
    private lateinit var txtFilesCount: TextView
    private lateinit var txtFilesList: TextView
    private lateinit var btnRunConsolidation: Button
    private lateinit var progressConsolidation: ProgressBar
    private lateinit var cardResult: CardView
    private lateinit var txtSummary: TextView
    private lateinit var btnExportEmail: Button
    private lateinit var btnShareReport: Button

    private val selectedFileUris = mutableListOf<Uri>()
    private val selectedFileNames = mutableListOf<String>()

    private val consolidatedMap = mutableMapOf<String, ConsolidatedItem>()
    private val allParsedRawRecords = mutableListOf<ScanRecord>()

    private var lastExportResult: ReportExportEngine.ExportResult? = null
    private lateinit var db: InventoryDatabase

    private val filePickerLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            val data = result.data ?: return@registerForActivityResult
            selectedFileUris.clear()
            selectedFileNames.clear()

            // Multiple files selected
            val clipData = data.clipData
            if (clipData != null) {
                for (i in 0 until clipData.itemCount) {
                    val uri = clipData.getItemAt(i).uri
                    selectedFileUris.add(uri)
                    selectedFileNames.add(getFileName(uri))
                }
            } else {
                data.data?.let { uri ->
                    selectedFileUris.add(uri)
                    selectedFileNames.add(getFileName(uri))
                }
            }

            updateFilesUi()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_consolidator)

        db = InventoryDatabase(this)

        btnBack = findViewById(R.id.btnConsolidatorBack)
        btnPickFiles = findViewById(R.id.btnPickFiles)
        txtFilesCount = findViewById(R.id.txtSelectedFilesCount)
        txtFilesList = findViewById(R.id.txtSelectedFilesList)
        btnRunConsolidation = findViewById(R.id.btnRunConsolidation)
        progressConsolidation = findViewById(R.id.progressConsolidation)
        cardResult = findViewById(R.id.cardConsolidationResult)
        txtSummary = findViewById(R.id.txtConsolidationSummary)
        btnExportEmail = findViewById(R.id.btnExportConsolidatedEmail)
        btnShareReport = findViewById(R.id.btnShareConsolidated)

        btnBack.setOnClickListener { finish() }

        btnPickFiles.setOnClickListener {
            val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE)
                type = "*/*"
                putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                putExtra(Intent.EXTRA_MIME_TYPES, arrayOf("text/csv", "text/comma-separated-values", "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
            }
            filePickerLauncher.launch(intent)
        }

        btnRunConsolidation.setOnClickListener {
            runConsolidation()
        }

        btnExportEmail.setOnClickListener {
            val res = lastExportResult ?: return@setOnClickListener
            val settings = SettingsManager(this)
            EmailDispatcher.sendReportViaIntent(
                context = this,
                subject = "تقرير الجرد المدمج لكافة الأجهزة — شركة العسلي",
                bodyText = res.summaryText,
                files = listOf(res.xlsxFile, res.csvFile),
                targetEmail = settings.getTargetEmail()
            )
        }

        btnShareReport.setOnClickListener {
            val res = lastExportResult ?: return@setOnClickListener
            EmailDispatcher.sendReportViaIntent(
                context = this,
                subject = "تقرير الجرد الموحد لكافة أجهزة الهاندهيل",
                bodyText = res.summaryText,
                files = listOf(res.xlsxFile, res.csvFile)
            )
        }
    }

    private fun updateFilesUi() {
        txtFilesCount.text = "الملفات المحددة للدمج (${selectedFileUris.size} ملفات)"
        if (selectedFileNames.isEmpty()) {
            txtFilesList.text = "لم يتم اختيار أي ملفات بعد.\nاضغط على الزر أعلاه لتحديد ملفات الجرد."
            btnRunConsolidation.isEnabled = false
        } else {
            val sb = StringBuilder()
            for ((idx, name) in selectedFileNames.withIndex()) {
                sb.append("• [${idx + 1}] $name\n")
            }
            txtFilesList.text = sb.toString().trim()
            btnRunConsolidation.isEnabled = true
        }
    }

    private fun getFileName(uri: Uri): String {
        var name = "inventory_file.csv"
        contentResolver.query(uri, null, null, null, null)?.use { cursor ->
            val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (nameIndex != -1 && cursor.moveToFirst()) {
                name = cursor.getString(nameIndex) ?: name
            }
        }
        return name
    }

    private fun runConsolidation() {
        if (selectedFileUris.isEmpty()) {
            Toast.makeText(this, "يرجى اختيار ملف أو أكثر أولاً", Toast.LENGTH_SHORT).show()
            return
        }

        progressConsolidation.visibility = View.VISIBLE
        btnRunConsolidation.isEnabled = false
        cardResult.visibility = View.GONE

        Thread {
            consolidatedMap.clear()
            allParsedRawRecords.clear()

            try {
                for ((idx, uri) in selectedFileUris.withIndex()) {
                    val defaultDevName = selectedFileNames.getOrNull(idx) ?: "جهاز $idx"
                    parseFileUri(uri, defaultDevName)
                }

                // Match with catalog to populate System Quantity and Cost
                for ((barcode, item) in consolidatedMap) {
                    val prod = db.getProductByBarcodeOrCode(barcode)
                    if (prod != null) {
                        item.systemQty = prod.systemQty
                    }
                }

                // Generate Master Consolidated Excel and CSV
                val exportRes = ReportExportEngine.exportConsolidatedReport(
                    context = this,
                    reportTitle = "الجرد المدمج (${selectedFileUris.size} ملفات)",
                    consolidatedMap = consolidatedMap,
                    rawRecords = allParsedRawRecords
                )
                lastExportResult = exportRes

                runOnUiThread {
                    progressConsolidation.visibility = View.GONE
                    btnRunConsolidation.isEnabled = true
                    cardResult.visibility = View.VISIBLE
                    txtSummary.text = exportRes.summaryText
                    Toast.makeText(this, "✅ تم دمج ومطابقة الملفات بنجاح!", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                e.printStackTrace()
                runOnUiThread {
                    progressConsolidation.visibility = View.GONE
                    btnRunConsolidation.isEnabled = true
                    Toast.makeText(this, "خطأ أثناء قراءة الملفات: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }.start()
    }

    private fun parseFileUri(uri: Uri, deviceTag: String) {
        contentResolver.openInputStream(uri)?.use { stream ->
            BufferedReader(InputStreamReader(stream, "UTF-8")).use { reader ->
                var line: String?
                var isHeader = true
                var barcodeCol = 0
                var codeCol = 1
                var nameArCol = 2
                var nameEnCol = 3
                var qtyCol = 4

                while (reader.readLine().also { line = it } != null) {
                    val l = line?.trim() ?: continue
                    if (l.isEmpty() || l.startsWith("---") || l.startsWith("تقرير الجرد")) continue

                    val parts = parseCsvLine(l)
                    if (parts.isEmpty()) continue

                    // Detect Header
                    if (isHeader) {
                        for (i in parts.indices) {
                            val lower = parts[i].trim()
                            if (lower.contains("الباركود") || lower.equals("barcode", true)) barcodeCol = i
                            if (lower.contains("كود") || lower.equals("code", true)) codeCol = i
                            if (lower.contains("بالعربي") || lower.equals("name_ar", true)) nameArCol = i
                            if (lower.contains("بالإنجليزي") || lower.equals("name_en", true)) nameEnCol = i
                            if (lower.contains("الكمية") || lower.contains("الفعلي") || lower.equals("qty", true)) qtyCol = i
                        }
                        isHeader = false
                        continue
                    }

                    if (barcodeCol >= parts.size) continue
                    val barcode = parts[barcodeCol].trim()
                    if (barcode.isBlank() || barcode.equals("الباركود", true)) continue

                    val code = parts.getOrNull(codeCol)?.trim() ?: "-"
                    val nameAr = parts.getOrNull(nameArCol)?.trim() ?: ""
                    val nameEn = parts.getOrNull(nameEnCol)?.trim() ?: ""
                    val qtyStr = parts.getOrNull(qtyCol)?.trim() ?: "1"
                    val qty = qtyStr.toDoubleOrNull() ?: 1.0

                    // Insert or aggregate into consolidatedMap
                    val existing = consolidatedMap[barcode]
                    if (existing != null) {
                        existing.countedQty += qty
                        existing.deviceCounts[deviceTag] = (existing.deviceCounts[deviceTag] ?: 0.0) + qty
                    } else {
                        val prod = db.getProductByBarcodeOrCode(barcode)
                        val cost = prod?.standardPrice ?: 0.0
                        val listP = prod?.listPrice ?: 0.0
                        val sysQ = prod?.systemQty ?: 0.0

                        val newItem = ConsolidatedItem(
                            barcode = barcode,
                            defaultCode = if (code != "-") code else (prod?.defaultCode ?: "-"),
                            nameAr = if (nameAr.isNotBlank()) nameAr else (prod?.nameAr ?: "صنف غير معرّف"),
                            nameEn = if (nameEn.isNotBlank()) nameEn else (prod?.nameEn ?: ""),
                            countedQty = qty,
                            systemQty = sysQ,
                            costPrice = cost,
                            listPrice = listP
                        )
                        newItem.deviceCounts[deviceTag] = qty
                        consolidatedMap[barcode] = newItem
                    }

                    allParsedRawRecords.add(
                        ScanRecord(
                            sessionId = 0,
                            barcode = barcode,
                            defaultCode = code,
                            nameAr = nameAr,
                            nameEn = nameEn,
                            qty = qty,
                            zoneName = deviceTag,
                            deviceId = "",
                            deviceName = deviceTag,
                            timestamp = ""
                        )
                    )
                }
            }
        }
    }

    private fun parseCsvLine(line: String): List<String> {
        val result = mutableListOf<String>()
        val sb = StringBuilder()
        var inQuotes = false

        for (c in line) {
            when (c) {
                '"' -> inQuotes = !inQuotes
                ',' -> {
                    if (inQuotes) {
                        sb.append(c)
                    } else {
                        result.add(sb.toString().trim())
                        sb.clear()
                    }
                }
                else -> sb.append(c)
            }
        }
        result.add(sb.toString().trim())
        return result
    }
}
