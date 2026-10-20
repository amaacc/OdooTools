package com.alassali.fastinventory

import android.app.AlertDialog
import android.content.Context
import android.graphics.Color
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.Bundle
import android.view.KeyEvent
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import java.util.Locale

class ShelfAuditActivity : AppCompatActivity() {

    private lateinit var db: InventoryDatabase
    private lateinit var settingsManager: SettingsManager
    private lateinit var sessionManager: SessionManager
    private lateinit var scannerHelper: ScannerHelper

    private lateinit var btnBack: ImageButton
    private lateinit var btnRefresh: ImageButton
    private lateinit var txtShowroomBanner: TextView
    private lateinit var spAuditZone: Spinner

    // Spot-Check views
    private lateinit var txtSpotCheckPrompt: TextView
    private lateinit var layoutSpotCheckResult: LinearLayout
    private lateinit var txtSpotCheckNameAr: TextView
    private lateinit var txtSpotCheckBarcode: TextView
    private lateinit var txtSpotCheckShelfCount: TextView
    private lateinit var txtSpotCheckTotalCount: TextView
    private lateinit var txtSpotCheckSystemQty: TextView
    private lateinit var txtSpotCheckStatusBanner: TextView
    private lateinit var btnSpotCheckEditQty: Button

    // Shelf Walk views
    private lateinit var txtAuditShelfStats: TextView
    private lateinit var recyclerShelfWalk: RecyclerView
    private lateinit var txtEmptyShelfWalk: TextView

    private lateinit var adapter: ShelfWalkAdapter
    private var currentZoneName: String = ""
    private var lastInspectedBarcode: String? = null
    private var toneGen: ToneGenerator? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_shelf_audit)

        db = InventoryDatabase(this)
        settingsManager = SettingsManager(this)
        sessionManager = SessionManager(this)

        initViews()
        setupScanner()
        setupListeners()

        try {
            toneGen = ToneGenerator(AudioManager.STREAM_MUSIC, 95)
        } catch (e: Exception) {
            // Ignore
        }

        loadZonesAndData()
    }

    override fun onResume() {
        super.onResume()
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                registerReceiver(scannerHelper.intentReceiver, scannerHelper.getIntentFilter(), Context.RECEIVER_EXPORTED)
            } else {
                registerReceiver(scannerHelper.intentReceiver, scannerHelper.getIntentFilter())
            }
        } catch (e: Exception) {
            // Ignore
        }
        loadZonesAndData()
    }

    override fun onPause() {
        super.onPause()
        try {
            unregisterReceiver(scannerHelper.intentReceiver)
        } catch (e: Exception) {
            // Ignore
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        toneGen?.release()
    }

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (scannerHelper.handleKeyEvent(event)) {
            return true
        }
        return super.dispatchKeyEvent(event)
    }

    private fun initViews() {
        btnBack = findViewById(R.id.btnBackAudit)
        btnRefresh = findViewById(R.id.btnRefreshAudit)
        txtShowroomBanner = findViewById(R.id.txtAuditShowroomBanner)
        spAuditZone = findViewById(R.id.spAuditZone)

        txtSpotCheckPrompt = findViewById(R.id.txtSpotCheckPrompt)
        layoutSpotCheckResult = findViewById(R.id.layoutSpotCheckResult)
        txtSpotCheckNameAr = findViewById(R.id.txtSpotCheckNameAr)
        txtSpotCheckBarcode = findViewById(R.id.txtSpotCheckBarcode)
        txtSpotCheckShelfCount = findViewById(R.id.txtSpotCheckShelfCount)
        txtSpotCheckTotalCount = findViewById(R.id.txtSpotCheckTotalCount)
        txtSpotCheckSystemQty = findViewById(R.id.txtSpotCheckSystemQty)
        txtSpotCheckStatusBanner = findViewById(R.id.txtSpotCheckStatusBanner)
        btnSpotCheckEditQty = findViewById(R.id.btnSpotCheckEditQty)

        txtAuditShelfStats = findViewById(R.id.txtAuditShelfStats)
        recyclerShelfWalk = findViewById(R.id.recyclerShelfWalk)
        txtEmptyShelfWalk = findViewById(R.id.txtEmptyShelfWalk)

        recyclerShelfWalk.layoutManager = LinearLayoutManager(this)
        adapter = ShelfWalkAdapter { scanRecord ->
            showEditQuantityDialog(scanRecord.barcode, scanRecord.zoneName)
        }
        recyclerShelfWalk.adapter = adapter
    }

    private fun setupScanner() {
        scannerHelper = ScannerHelper { barcode ->
            runOnUiThread {
                inspectBarcode(barcode)
            }
        }
    }

    private fun setupListeners() {
        btnBack.setOnClickListener { finish() }
        btnRefresh.setOnClickListener { loadZonesAndData() }

        btnSpotCheckEditQty.setOnClickListener {
            lastInspectedBarcode?.let { bc ->
                showEditQuantityDialog(bc, currentZoneName)
            }
        }

        spAuditZone.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                val selected = parent?.getItemAtPosition(position)?.toString() ?: ""
                currentZoneName = if (selected.startsWith("جميع الرفوف")) "" else selected
                loadShelfWalkData()
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }
    }

    private fun loadZonesAndData() {
        val session = sessionManager.currentSession
        val whName = if (session.warehouseName.isNotBlank()) session.warehouseName else settingsManager.getSelectedWarehouseName()
        txtShowroomBanner.text = "المعرض: $whName | الجلسة: ${session.name}"

        val zones = db.getZonesForSession(session.id)
        val zoneList = mutableListOf<String>()

        if (zones.size > 1) {
            zoneList.add("جميع الرفوف والمناطق (${zones.size} رف)")
        }
        for (z in zones) {
            zoneList.add(z.zoneName)
        }
        if (zoneList.isEmpty()) {
            zoneList.add(sessionManager.currentZone)
        }

        val spinnerAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, zoneList)
        spAuditZone.adapter = spinnerAdapter

        // Default to active zone
        val currentIdx = zoneList.indexOfFirst { it == sessionManager.currentZone }
        if (currentIdx >= 0) {
            spAuditZone.setSelection(currentIdx)
            currentZoneName = sessionManager.currentZone
        } else {
            currentZoneName = if (zoneList.isNotEmpty() && !zoneList[0].startsWith("جميع")) zoneList[0] else ""
        }

        loadShelfWalkData()
    }

    private fun loadShelfWalkData() {
        val session = sessionManager.currentSession
        val scans = if (currentZoneName.isNotBlank()) {
            db.getScansForZone(session.id, currentZoneName)
        } else {
            db.getAllScansForSession(session.id)
        }

        adapter.submitList(scans)
        txtEmptyShelfWalk.visibility = if (scans.isEmpty()) View.VISIBLE else View.GONE
        txtAuditShelfStats.text = "${scans.size} مسح مسجل"
    }

    /**
     * Spot-check inspection triggered by scanning a barcode on the shelf.
     */
    private fun inspectBarcode(barcode: String) {
        val cleanBarcode = barcode.trim()
        val session = sessionManager.currentSession
        val (prod, pkg) = db.lookupBarcode(cleanBarcode)
        val resolvedBarcode = prod?.barcode?.ifBlank { cleanBarcode } ?: cleanBarcode
        lastInspectedBarcode = resolvedBarcode

        txtSpotCheckPrompt.visibility = View.GONE
        layoutSpotCheckResult.visibility = View.VISIBLE

        val targetZone = if (currentZoneName.isNotBlank()) currentZoneName else sessionManager.currentZone
        val shelfCount = db.getItemCountInZone(session.id, resolvedBarcode, targetZone)
        val totalCount = db.getItemCountInSession(session.id, resolvedBarcode)
        val systemStock = prod?.systemQty ?: 0.0

        txtSpotCheckBarcode.text = resolvedBarcode
        txtSpotCheckNameAr.text = prod?.nameAr ?: "صنف غير معرّف (${resolvedBarcode})"
        txtSpotCheckShelfCount.text = "${String.format(Locale.US, "%.0f", shelfCount)} حبة"
        txtSpotCheckTotalCount.text = "${String.format(Locale.US, "%.0f", totalCount)} حبة"
        txtSpotCheckSystemQty.text = "${String.format(Locale.US, "%.0f", systemStock)} حبة"

        val diff = totalCount - systemStock

        when {
            prod == null -> {
                txtSpotCheckStatusBanner.text = "⚠️ صنف غير معرّف في أودو لهذا المعرض"
                txtSpotCheckStatusBanner.setBackgroundColor(Color.parseColor("#33F59E0B"))
                txtSpotCheckStatusBanner.setTextColor(Color.parseColor("#F59E0B"))
                toneGen?.startTone(ToneGenerator.TONE_CDMA_ALERT_CALL_GUARD, 150)
            }
            diff == 0.0 -> {
                txtSpotCheckStatusBanner.text = "🟢 مطابق تماماً مع رصيد المعرض (فرق 0)"
                txtSpotCheckStatusBanner.setBackgroundColor(Color.parseColor("#3310B981"))
                txtSpotCheckStatusBanner.setTextColor(Color.parseColor("#10B981"))
                toneGen?.startTone(ToneGenerator.TONE_PROP_ACK, 80)
            }
            diff < 0 -> {
                txtSpotCheckStatusBanner.text = "🔴 عجز في الرصيد بمقدار: ${String.format(Locale.US, "%.0f", diff)} حبة"
                txtSpotCheckStatusBanner.setBackgroundColor(Color.parseColor("#33EF4444"))
                txtSpotCheckStatusBanner.setTextColor(Color.parseColor("#EF4444"))
                toneGen?.startTone(ToneGenerator.TONE_PROP_BEEP2, 120)
            }
            else -> {
                txtSpotCheckStatusBanner.text = "🔵 زيادة في المحصور بمقدار: +${String.format(Locale.US, "%.0f", diff)} حبة"
                txtSpotCheckStatusBanner.setBackgroundColor(Color.parseColor("#3338BDF8"))
                txtSpotCheckStatusBanner.setTextColor(Color.parseColor("#38BDF8"))
                toneGen?.startTone(ToneGenerator.TONE_PROP_ACK, 100)
            }
        }
    }

    private fun showEditQuantityDialog(barcode: String, zone: String) {
        val targetZone = if (zone.isNotBlank()) zone else sessionManager.currentZone
        val session = sessionManager.currentSession
        val currentQty = db.getItemCountInZone(session.id, barcode, targetZone)

        val container = android.widget.FrameLayout(this).apply {
            setPadding(48, 20, 48, 10)
        }
        val input = EditText(this).apply {
            inputType = android.text.InputType.TYPE_CLASS_NUMBER or android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL
            setText(String.format(Locale.US, "%.0f", currentQty))
            setSelection(text.length)
            hint = "أدخل الكمية الصحيحة لهذا الرف"
            setTextColor(getColor(R.color.text_primary))
            setHintTextColor(getColor(R.color.text_secondary))
            setBackgroundResource(R.drawable.bg_zone_pill)
            setPadding(28, 20, 28, 20)
        }
        container.addView(input)

        AlertDialog.Builder(this)
            .setTitle("✏️ تصحيح كمية الصنف في الرف")
            .setMessage("الباركود: $barcode\nالرف: $targetZone\nالكمية المحصورة حالياً: ${String.format(Locale.US, "%.0f", currentQty)}")
            .setView(container)
            .setPositiveButton("حفظ التصحيح") { _, _ ->
                val newQty = input.text.toString().toDoubleOrNull()
                if (newQty != null && newQty >= 0) {
                    db.setExactItemQuantity(session.id, barcode, targetZone, newQty)
                    Toast.makeText(this, "✅ تم تصحيح الكمية إلى: ${String.format(Locale.US, "%.0f", newQty)} حبة", Toast.LENGTH_SHORT).show()
                    inspectBarcode(barcode)
                    loadShelfWalkData()
                }
            }
            .setNegativeButton("إلغاء", null)
            .show()
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Adapter for Physical Shelf Walk
    // ─────────────────────────────────────────────────────────────────────────
    inner class ShelfWalkAdapter(
        private val onItemClick: (ScanRecord) -> Unit
    ) : RecyclerView.Adapter<ShelfWalkAdapter.ViewHolder>() {

        private val items = mutableListOf<ScanRecord>()

        fun submitList(list: List<ScanRecord>) {
            items.clear()
            items.addAll(list)
            notifyDataSetChanged()
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
            val v = LayoutInflater.from(parent.context).inflate(R.layout.item_shelf_audit, parent, false)
            return ViewHolder(v)
        }

        override fun onBindViewHolder(holder: ViewHolder, position: Int) {
            holder.bind(items[position])
        }

        override fun getItemCount(): Int = items.size

        inner class ViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
            val txtSeq: TextView = itemView.findViewById(R.id.auditTxtShelfSeq)
            val txtMethod: TextView = itemView.findViewById(R.id.auditTxtMethodBadge)
            val txtTimestamp: TextView = itemView.findViewById(R.id.auditTxtTimestamp)
            val txtNameAr: TextView = itemView.findViewById(R.id.auditTxtNameAr)
            val txtBarcode: TextView = itemView.findViewById(R.id.auditTxtBarcode)
            val txtCode: TextView = itemView.findViewById(R.id.auditTxtCode)
            val txtCountedInZone: TextView = itemView.findViewById(R.id.auditTxtCountedInZone)
            val txtSystemQty: TextView = itemView.findViewById(R.id.auditTxtSystemQty)
            val txtVarianceBadge: TextView = itemView.findViewById(R.id.auditTxtVarianceBadge)

            fun bind(scan: ScanRecord) {
                txtSeq.text = "#${scan.shelfSeq}"
                txtTimestamp.text = scan.timestamp.takeLast(8) // Just the HH:mm:ss
                txtNameAr.text = scan.nameAr
                txtBarcode.text = scan.barcode
                txtCode.text = if (scan.defaultCode.isNotBlank()) "كود: ${scan.defaultCode}" else ""

                val methodDesc = when (scan.scanMethod) {
                    "MANUAL" -> "إدخال يدوي ✏️"
                    "OVERRIDE" -> "تعديل كمية 🔄"
                    else -> "مسح ليزر ⚡"
                }
                txtMethod.text = methodDesc

                val totalInSession = db.getItemCountInSession(scan.sessionId, scan.barcode)
                val prod = db.getProductByBarcodeOrCode(scan.barcode)
                val sysStock = prod?.systemQty ?: 0.0

                txtCountedInZone.text = "${String.format(Locale.US, "%.0f", scan.qty)} حبة"
                txtSystemQty.text = String.format(Locale.US, "%.0f", sysStock)

                val diff = totalInSession - sysStock
                when {
                    prod == null -> {
                        txtVarianceBadge.text = "غير معرّف"
                        txtVarianceBadge.setTextColor(Color.parseColor("#F59E0B"))
                    }
                    diff == 0.0 -> {
                        txtVarianceBadge.text = "مطابق"
                        txtVarianceBadge.setTextColor(Color.parseColor("#10B981"))
                    }
                    diff < 0 -> {
                        txtVarianceBadge.text = "عجز ${String.format(Locale.US, "%.0f", diff)}"
                        txtVarianceBadge.setTextColor(Color.parseColor("#EF4444"))
                    }
                    else -> {
                        txtVarianceBadge.text = "فائض +${String.format(Locale.US, "%.0f", diff)}"
                        txtVarianceBadge.setTextColor(Color.parseColor("#38BDF8"))
                    }
                }

                itemView.setOnClickListener { onItemClick(scan) }
            }
        }
    }
}
