package com.alassali.fastinventory

import android.app.AlertDialog
import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.ImageButton
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import java.util.Locale

class AuditListActivity : AppCompatActivity() {

    private lateinit var sessionManager: SessionManager
    private lateinit var db: InventoryDatabase
    private lateinit var recycler: RecyclerView
    private lateinit var adapter: AuditListAdapter
    private lateinit var etSearch: EditText
    private lateinit var txtStats: TextView
    private lateinit var txtZoneTag: TextView
    private lateinit var txtEmpty: TextView
    private lateinit var btnClearSession: Button
    private lateinit var btnExport: Button
    private lateinit var btnBack: ImageButton

    private var allItems = listOf<ScanRecord>()
    private var filteredItems = mutableListOf<ScanRecord>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_audit_list)

        sessionManager = SessionManager(this)
        db = InventoryDatabase(this)

        btnBack = findViewById(R.id.btnBack)
        recycler = findViewById(R.id.recyclerAuditItems)
        etSearch = findViewById(R.id.etSearchAudit)
        txtStats = findViewById(R.id.txtAuditStats)
        txtZoneTag = findViewById(R.id.txtAuditZoneTag)
        txtEmpty = findViewById(R.id.txtEmptyAudit)
        btnClearSession = findViewById(R.id.btnClearSession)
        btnExport = findViewById(R.id.btnExportFromAudit)

        btnBack.setOnClickListener { finish() }

        recycler.layoutManager = LinearLayoutManager(this)
        adapter = AuditListAdapter(
            onItemClicked = { item -> showEditQuantityDialog(item) },
            onDeleteClicked = { item -> confirmDeleteItem(item) }
        )
        recycler.adapter = adapter

        btnClearSession.setOnClickListener {
            startActivity(Intent(this, SessionsActivity::class.java))
        }

        btnExport.setOnClickListener { exportAndSend() }

        etSearch.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                filterList(s.toString())
            }
            override fun afterTextChanged(s: Editable?) {}
        })

        loadData()
    }

    override fun onResume() {
        super.onResume()
        loadData()
    }

    private fun loadData() {
        allItems = sessionManager.getAggregatedItems()
        filterList(etSearch.text.toString())
        updateStats()
    }

    private fun filterList(query: String) {
        val q = query.trim().lowercase(Locale.ROOT)
        filteredItems.clear()
        if (q.isEmpty()) {
            filteredItems.addAll(allItems)
        } else {
            for (item in allItems) {
                if (item.barcode.lowercase(Locale.ROOT).contains(q) ||
                    item.defaultCode.lowercase(Locale.ROOT).contains(q) ||
                    item.nameAr.lowercase(Locale.ROOT).contains(q) ||
                    item.nameEn.lowercase(Locale.ROOT).contains(q) ||
                    item.zoneName.lowercase(Locale.ROOT).contains(q)
                ) {
                    filteredItems.add(item)
                }
            }
        }
        adapter.submitList(filteredItems)
        txtEmpty.visibility = if (filteredItems.isEmpty()) View.VISIBLE else View.GONE
    }

    private fun updateStats() {
        val (uniqueCount, totalUnits) = sessionManager.getSessionSummary()
        txtStats.text = "الأصناف: $uniqueCount | الحبات: ${String.format(Locale.US, "%.0f", totalUnits)}"
        txtZoneTag.text = "المنطقة: ${sessionManager.currentZone} | ${sessionManager.currentSession.name}"
    }

    private fun showEditQuantityDialog(item: ScanRecord) {
        val input = EditText(this).apply {
            inputType = android.text.InputType.TYPE_CLASS_NUMBER or android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL
            setText(String.format(Locale.US, "%.0f", item.qty))
            setSelection(text.length)
        }

        AlertDialog.Builder(this)
            .setTitle("✏️ تعديل كمية الصنف")
            .setMessage("${item.nameAr}\nباركود: ${item.barcode}")
            .setView(input)
            .setPositiveButton("حفظ") { _, _ ->
                val newQty = input.text.toString().toDoubleOrNull()
                if (newQty != null && newQty >= 0) {
                    sessionManager.setExactQuantity(item.barcode, newQty)
                    loadData()
                    Toast.makeText(this, "تم تحديث الكمية إلى $newQty", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("إلغاء", null)
            .show()
    }

    private fun confirmDeleteItem(item: ScanRecord) {
        AlertDialog.Builder(this)
            .setTitle("تأكيد الحذف")
            .setMessage("هل تريد حذف الصنف (${item.nameAr}) من جلسة الجرد؟")
            .setPositiveButton("حذف") { _, _ ->
                sessionManager.deleteItem(item.barcode)
                loadData()
                Toast.makeText(this, "تم حذف الصنف", Toast.LENGTH_SHORT).show()
            }
            .setNegativeButton("إلغاء", null)
            .show()
    }

    private fun confirmClearSession() {
        startActivity(Intent(this, SessionsActivity::class.java))
    }

    private fun exportAndSend() {
        if (allItems.isEmpty()) {
            Toast.makeText(this, "لا توجد أصناف لتصديرها", Toast.LENGTH_SHORT).show()
            return
        }

        val exportRes = ReportExportEngine.exportSessionReport(
            context = this,
            sessionName = sessionManager.currentSession.name,
            zoneName = sessionManager.currentZone,
            items = allItems,
            db = db,
            warehouseName = sessionManager.currentSession.warehouseName
        )

        val settings = SettingsManager(this)
        EmailDispatcher.sendReportViaIntent(
            context = this,
            subject = "تقرير الجرد: ${sessionManager.currentSession.name} — ${sessionManager.currentZone}",
            bodyText = exportRes.summaryText,
            files = listOf(exportRes.xlsxFile, exportRes.csvFile),
            targetEmail = settings.getTargetEmail()
        )
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Adapter
    // ─────────────────────────────────────────────────────────────────────────
    inner class AuditListAdapter(
        private val onItemClicked: (ScanRecord) -> Unit,
        private val onDeleteClicked: (ScanRecord) -> Unit
    ) : RecyclerView.Adapter<AuditListAdapter.ViewHolder>() {

        private val itemsList = mutableListOf<ScanRecord>()

        fun submitList(list: List<ScanRecord>) {
            itemsList.clear()
            itemsList.addAll(list)
            notifyDataSetChanged()
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
            val v = LayoutInflater.from(parent.context).inflate(R.layout.item_inventory_record, parent, false)
            return ViewHolder(v)
        }

        override fun onBindViewHolder(holder: ViewHolder, position: Int) {
            val item = itemsList[position]
            holder.bind(item)
        }

        override fun getItemCount(): Int = itemsList.size

        inner class ViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
            val txtQty: TextView = itemView.findViewById(R.id.itemTxtQty)
            val txtNameAr: TextView = itemView.findViewById(R.id.itemTxtNameAr)
            val txtNameEn: TextView = itemView.findViewById(R.id.itemTxtNameEn)
            val txtBarcode: TextView = itemView.findViewById(R.id.itemTxtBarcode)
            val txtCode: TextView = itemView.findViewById(R.id.itemTxtCode)
            val txtZone: TextView = itemView.findViewById(R.id.itemTxtZone)
            val btnDelete: ImageButton = itemView.findViewById(R.id.itemBtnDelete)

            fun bind(item: ScanRecord) {
                txtQty.text = String.format(Locale.US, "%.0f", item.qty)
                txtNameAr.text = item.nameAr
                txtNameEn.text = item.nameEn
                txtBarcode.text = item.barcode
                txtCode.text = if (item.defaultCode.isNotBlank()) "كود: ${item.defaultCode}" else ""
                txtZone.text = item.zoneName

                itemView.setOnClickListener { onItemClicked(item) }
                btnDelete.setOnClickListener { onDeleteClicked(item) }
            }
        }
    }
}
