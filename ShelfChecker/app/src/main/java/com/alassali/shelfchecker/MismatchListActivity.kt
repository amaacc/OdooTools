package com.alassali.shelfchecker

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.ImageButton
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import java.io.File
import java.io.FileWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MismatchListActivity : AppCompatActivity() {

    private lateinit var recyclerMismatches: RecyclerView
    private lateinit var txtEmpty: TextView
    private lateinit var btnSendReport: Button
    private lateinit var btnClearList: Button

    private var mismatches = ArrayList<String>()
    private var unknowns = ArrayList<String>()
    private lateinit var adapter: BarcodeAdapter
    private lateinit var settingsManager: SettingsManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_mismatch_list)

        settingsManager = SettingsManager(this)

        mismatches = intent.getStringArrayListExtra("mismatches") ?: ArrayList()
        unknowns = intent.getStringArrayListExtra("unknowns") ?: ArrayList()

        recyclerMismatches = findViewById(R.id.recyclerMismatches)
        txtEmpty = findViewById(R.id.txtEmpty)
        btnSendReport = findViewById(R.id.btnSendReport)
        btnClearList = findViewById(R.id.btnClearList)

        findViewById<ImageButton>(R.id.btnBack).setOnClickListener {
            onBackPressed()
        }

        adapter = BarcodeAdapter(mismatches, unknowns) { listType, index ->
            if (listType == 0) mismatches.removeAt(index)
            else unknowns.removeAt(index)
            adapter.notifyDataSetChanged()
            updateUI()
        }

        recyclerMismatches.layoutManager = LinearLayoutManager(this)
        recyclerMismatches.adapter = adapter

        btnSendReport.setOnClickListener { sendEmail() }
        btnClearList.setOnClickListener { confirmClear() }

        updateUI()
    }

    private fun updateUI() {
        if (mismatches.isEmpty() && unknowns.isEmpty()) {
            recyclerMismatches.visibility = View.GONE
            txtEmpty.visibility = View.VISIBLE
            btnSendReport.isEnabled = false
        } else {
            recyclerMismatches.visibility = View.VISIBLE
            txtEmpty.visibility = View.GONE
            btnSendReport.isEnabled = true
        }
    }

    private fun confirmClear() {
        AlertDialog.Builder(this)
            .setTitle("تأكيد")
            .setMessage("هل أنت متأكد من مسح القائمة بالكامل؟")
            .setPositiveButton("نعم") { _, _ ->
                mismatches.clear()
                unknowns.clear()
                val result = Intent()
                result.putStringArrayListExtra("mismatches", mismatches)
                result.putStringArrayListExtra("unknowns", unknowns)
                setResult(RESULT_OK, result)
                finish()
            }
            .setNegativeButton("إلغاء", null)
            .show()
    }

    private fun sendEmail() {
        val totalScanned = intent.getIntExtra("scannedCount", mismatches.size + unknowns.size)
        val sb = StringBuilder()
        sb.append("الباركودات التالية تحتاج تحديث بطاقة السعر على الرف:\n\n")
        mismatches.forEach { sb.append(it).append("\n") }
        sb.append("\nأصناف غير معرّفة:\n")
        unknowns.forEach { sb.append(it).append("\n") }
        sb.append("\nـــــــــــ\n")
        sb.append("إجمالي المفحوص: $totalScanned\n")
        sb.append("غير مطابق: ${mismatches.size}\n")
        sb.append("غير معرّف: ${unknowns.size}\n")

        val dateStr = SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date())
        val subject = "فحص أسعار الأرفف — $dateStr"
        val email = settingsManager.getReportEmail()

        // Create CSV File
        val csvFile = File(cacheDir, "mismatches_$dateStr.csv")
        try {
            FileWriter(csvFile).use { writer ->
                writer.append("Barcode,Type\n")
                mismatches.forEach { writer.append("$it,Mismatch\n") }
                unknowns.forEach { writer.append("$it,Unknown\n") }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }

        val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", csvFile)

        val emailIntent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_EMAIL, arrayOf(email))
            putExtra(Intent.EXTRA_SUBJECT, subject)
            putExtra(Intent.EXTRA_TEXT, sb.toString())
            putExtra(Intent.EXTRA_STREAM, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        startActivity(Intent.createChooser(emailIntent, "إرسال التقرير..."))
    }

    override fun onBackPressed() {
        val result = Intent()
        result.putStringArrayListExtra("mismatches", mismatches)
        result.putStringArrayListExtra("unknowns", unknowns)
        setResult(RESULT_OK, result)
        super.onBackPressed()
    }

    class BarcodeAdapter(
        private val mismatches: List<String>,
        private val unknowns: List<String>,
        private val onDelete: (Int, Int) -> Unit // listType (0=mismatch, 1=unknown), index
    ) : RecyclerView.Adapter<RecyclerView.ViewHolder>() {

        private val TYPE_HEADER_MISMATCH = 0
        private val TYPE_ITEM_MISMATCH = 1
        private val TYPE_HEADER_UNKNOWN = 2
        private val TYPE_ITEM_UNKNOWN = 3

        override fun getItemViewType(position: Int): Int {
            if (position == 0) return TYPE_HEADER_MISMATCH
            if (position <= mismatches.size) return TYPE_ITEM_MISMATCH
            if (position == mismatches.size + 1) return TYPE_HEADER_UNKNOWN
            return TYPE_ITEM_UNKNOWN
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): RecyclerView.ViewHolder {
            val inflater = LayoutInflater.from(parent.context)
            return when (viewType) {
                TYPE_HEADER_MISMATCH -> HeaderViewHolder(inflater.inflate(android.R.layout.simple_list_item_1, parent, false))
                TYPE_HEADER_UNKNOWN -> HeaderViewHolder(inflater.inflate(android.R.layout.simple_list_item_1, parent, false))
                else -> ItemViewHolder(inflater.inflate(R.layout.item_mismatch, parent, false))
            }
        }

        override fun onBindViewHolder(holder: RecyclerView.ViewHolder, position: Int) {
            when (holder.itemViewType) {
                TYPE_HEADER_MISMATCH -> {
                    (holder as HeaderViewHolder).textView.text = "أسعار غير مطابقة"
                    holder.textView.setTextColor(0xFFD32F2F.toInt()) // Red
                }
                TYPE_HEADER_UNKNOWN -> {
                    (holder as HeaderViewHolder).textView.text = "أصناف غير معرّفة"
                    holder.textView.setTextColor(0xFFF57C00.toInt()) // Orange
                }
                TYPE_ITEM_MISMATCH -> {
                    val index = position - 1
                    val itemHolder = holder as ItemViewHolder
                    itemHolder.txtBarcode.text = mismatches[index]
                    itemHolder.btnDelete.setOnClickListener { onDelete(0, index) }
                }
                TYPE_ITEM_UNKNOWN -> {
                    val index = position - 2 - mismatches.size
                    val itemHolder = holder as ItemViewHolder
                    itemHolder.txtBarcode.text = unknowns[index]
                    itemHolder.btnDelete.setOnClickListener { onDelete(1, index) }
                }
            }
        }

        override fun getItemCount(): Int = mismatches.size + unknowns.size + 2

        class HeaderViewHolder(view: View) : RecyclerView.ViewHolder(view) {
            val textView: TextView = view.findViewById(android.R.id.text1)
        }

        class ItemViewHolder(view: View) : RecyclerView.ViewHolder(view) {
            val txtBarcode: TextView = view.findViewById(R.id.txtBarcode)
            val btnDelete: ImageButton = view.findViewById(R.id.btnDelete)
        }
    }
}
