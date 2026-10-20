package com.alassali.fastinventory

import android.app.AlertDialog
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.ImageButton
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import org.json.JSONArray
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class SessionsActivity : AppCompatActivity() {

    private lateinit var db: InventoryDatabase
    private lateinit var settingsManager: SettingsManager
    private lateinit var sessionManager: SessionManager

    private lateinit var btnBack: ImageButton
    private lateinit var btnNewSession: Button
    private lateinit var recyclerSessions: RecyclerView
    private lateinit var txtEmptySessions: TextView

    private lateinit var adapter: SessionsAdapter
    private var sessionsList = mutableListOf<InventorySession>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_sessions)

        db = InventoryDatabase(this)
        settingsManager = SettingsManager(this)
        sessionManager = SessionManager(this)

        btnBack = findViewById(R.id.btnBackSessions)
        btnNewSession = findViewById(R.id.btnNewSession)
        recyclerSessions = findViewById(R.id.recyclerSessions)
        txtEmptySessions = findViewById(R.id.txtEmptySessions)

        btnBack.setOnClickListener { finish() }

        btnNewSession.setOnClickListener { showCreateNewSessionDialog() }

        recyclerSessions.layoutManager = LinearLayoutManager(this)
        adapter = SessionsAdapter(
            onActivate = { session -> activateSession(session) },
            onExport = { session -> exportSession(session) },
            onDelete = { session -> confirmDeleteSessionStep1(session) }
        )
        recyclerSessions.adapter = adapter

        loadSessions()
    }

    override fun onResume() {
        super.onResume()
        loadSessions()
    }

    private fun loadSessions() {
        sessionsList.clear()
        sessionsList.addAll(db.getAllSessions())
        adapter.submitList(sessionsList)

        txtEmptySessions.visibility = if (sessionsList.isEmpty()) View.VISIBLE else View.GONE
    }

    private fun activateSession(session: InventorySession) {
        sessionManager.switchSession(session.id)
        Toast.makeText(this, "تم تفعيل الجلسة: ${session.name}", Toast.LENGTH_SHORT).show()
        setResult(RESULT_OK)
        finish()
    }

    private fun exportSession(session: InventorySession) {
        val items = db.getAggregatedSessionItems(session.id)
        if (items.isEmpty()) {
            Toast.makeText(this, "هذه الجلسة فارغة لا تحتوي على أصناف محصورة للتصدير", Toast.LENGTH_SHORT).show()
            return
        }

        val res = ReportExportEngine.exportSessionReport(
            context = this,
            sessionName = session.name,
            zoneName = session.zoneName,
            items = items,
            db = db,
            warehouseName = session.warehouseName
        )

        EmailDispatcher.sendReportViaIntent(
            context = this,
            subject = "تقرير الجرد: ${session.name} — ${session.warehouseName}",
            bodyText = res.summaryText,
            files = listOf(res.xlsxFile, res.csvFile),
            targetEmail = settingsManager.getTargetEmail()
        )
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Safe 2-Step Deletion Process
    // ─────────────────────────────────────────────────────────────────────────
    private fun confirmDeleteSessionStep1(session: InventorySession) {
        val (itemsCount, totalUnits) = db.getSessionSummary(session.id)

        AlertDialog.Builder(this)
            .setTitle("⚠️ تحذير: حذف جلسة الجرد (خطوة 1 من 2)")
            .setMessage("هل أنت متأكد تماماً من رغبتك في حذف جلسة:\n\"${session.name}\"؟\n\nتحتوي هذه الجلسة على:\n• $itemsCount صنف فريد\n• ${String.format(Locale.US, "%.0f", totalUnits)} حبة محصورة\n\nالمسح سيؤدي إلى فقدان هذه البيانات نهائياً!")
            .setPositiveButton("متابعة الحذف") { _, _ ->
                confirmDeleteSessionStep2(session)
            }
            .setNegativeButton("إلغاء التراجع", null)
            .show()
    }

    private fun confirmDeleteSessionStep2(session: InventorySession) {
        val container = android.widget.FrameLayout(this).apply {
            setPadding(48, 20, 48, 10)
        }
        val input = EditText(this).apply {
            hint = "اكتب كلمة 'حذف' هنا لتأكيد المسح"
            setTextColor(getColor(R.color.text_primary))
            setHintTextColor(getColor(R.color.text_secondary))
            setBackgroundResource(R.drawable.bg_zone_pill)
            setPadding(28, 20, 28, 20)
        }
        container.addView(input)

        AlertDialog.Builder(this)
            .setTitle("🚨 تأكيد نهائي وإلزامي (خطوة 2 من 2)")
            .setMessage("لتأكيد حذف الجلسة ومسحها من قاعدة البيانات، يرجى كتابة كلمة 'حذف' في المربع أدناه:")
            .setView(container)
            .setPositiveButton("تأكيد المسح النهائي") { _, _ ->
                val typed = input.text.toString().trim()
                if (typed == "حذف" || typed.equals("delete", ignoreCase = true)) {
                    val ok = db.deleteSessionWithConfirmation(session.id)
                    if (ok) {
                        Toast.makeText(this, "✅ تم حذف الجلسة بنجاح", Toast.LENGTH_SHORT).show()
                        // If we deleted the currently active session, reload/switch to remaining or open default
                        sessionManager.reloadActiveSession()
                        loadSessions()
                    } else {
                        Toast.makeText(this, "تعذر حذف الجلسة", Toast.LENGTH_SHORT).show()
                    }
                } else {
                    Toast.makeText(this, "❌ تم إلغاء الحذف لعدم تطابق كلمة التأكيد", Toast.LENGTH_LONG).show()
                }
            }
            .setNegativeButton("إلغاء", null)
            .show()
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Create New Session Dialog
    // ─────────────────────────────────────────────────────────────────────────
    private fun showCreateNewSessionDialog() {
        val view = LayoutInflater.from(this).inflate(R.layout.dialog_new_session, null)
        val etName = view.findViewById<EditText>(R.id.etNewSessionName)
        val spWarehouse = view.findViewById<Spinner>(R.id.spNewSessionWarehouse)
        val etZone = view.findViewById<EditText>(R.id.etNewSessionZone)

        // Suggest a default session name with today's date
        val dateStamp = SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())
        val defaultWhName = settingsManager.getSelectedWarehouseName()
        etName.setText("جرد $defaultWhName - $dateStamp")
        etZone.setText("الرف العام")

        // Populate warehouses from cached JSON
        val cachedJson = settingsManager.getCachedWarehousesJson()
        val warehouseItems = parseCachedWarehouses(cachedJson)

        val spinnerItems = if (warehouseItems.isNotEmpty()) {
            warehouseItems
        } else {
            listOf(
                WarehouseItem(
                    id = settingsManager.getSelectedWarehouseId(),
                    name = settingsManager.getSelectedWarehouseName(),
                    code = settingsManager.getSelectedWarehouseCode(),
                    lotStockId = settingsManager.getSelectedWarehouseLotStockId()
                )
            )
        }

        val spinnerAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, spinnerItems)
        spWarehouse.adapter = spinnerAdapter

        // Pre-select current warehouse
        val currentWhId = settingsManager.getSelectedWarehouseId()
        val selectIdx = spinnerItems.indexOfFirst { it.id == currentWhId }
        if (selectIdx >= 0) {
            spWarehouse.setSelection(selectIdx)
        }

        AlertDialog.Builder(this)
            .setTitle("➕ إنشاء جلسة جرد جديدة")
            .setView(view)
            .setPositiveButton("بدء الجلسة") { _, _ ->
                val sName = etName.text.toString().trim().ifBlank { "جلسة جرد $dateStamp" }
                val sZone = etZone.text.toString().trim().ifBlank { "الرف العام" }
                val selectedWh = spWarehouse.selectedItem as? WarehouseItem
                    ?: WarehouseItem(0, "المخزون العام", "", null)

                // Save selected warehouse
                settingsManager.setSelectedWarehouse(
                    id = selectedWh.id,
                    code = selectedWh.code,
                    name = selectedWh.name,
                    lotStockId = selectedWh.lotStockId ?: 0
                )

                // Create new session in DB and set active
                sessionManager.createNewSession(
                    name = sName,
                    warehouseId = selectedWh.id,
                    warehouseCode = selectedWh.code,
                    warehouseName = selectedWh.name,
                    defaultZone = sZone
                )

                Toast.makeText(this, "✅ تم إنشاء وتفعيل الجلسة: $sName", Toast.LENGTH_SHORT).show()
                setResult(RESULT_OK)
                finish()
            }
            .setNegativeButton("إلغاء", null)
            .show()
    }

    private fun parseCachedWarehouses(json: String): List<WarehouseItem> {
        return try {
            val arr = JSONArray(json)
            val list = mutableListOf<WarehouseItem>()
            for (i in 0 until arr.length()) {
                val o = arr.getJSONObject(i)
                list.add(
                    WarehouseItem(
                        id = o.optInt("id"),
                        name = o.optString("name"),
                        code = o.optString("code"),
                        lotStockId = if (o.has("lot_stock_id")) o.optInt("lot_stock_id") else null
                    )
                )
            }
            list
        } catch (e: Exception) {
            emptyList()
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Adapter
    // ─────────────────────────────────────────────────────────────────────────
    inner class SessionsAdapter(
        private val onActivate: (InventorySession) -> Unit,
        private val onExport: (InventorySession) -> Unit,
        private val onDelete: (InventorySession) -> Unit
    ) : RecyclerView.Adapter<SessionsAdapter.ViewHolder>() {

        private val items = mutableListOf<InventorySession>()

        fun submitList(list: List<InventorySession>) {
            items.clear()
            items.addAll(list)
            notifyDataSetChanged()
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
            val v = LayoutInflater.from(parent.context).inflate(R.layout.item_inventory_session, parent, false)
            return ViewHolder(v)
        }

        override fun onBindViewHolder(holder: ViewHolder, position: Int) {
            holder.bind(items[position])
        }

        override fun getItemCount(): Int = items.size

        inner class ViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
            val txtStatus: TextView = itemView.findViewById(R.id.sessionTxtStatusBadge)
            val txtDate: TextView = itemView.findViewById(R.id.sessionTxtDate)
            val txtName: TextView = itemView.findViewById(R.id.sessionTxtName)
            val txtWarehouse: TextView = itemView.findViewById(R.id.sessionTxtWarehouse)
            val txtItemsCount: TextView = itemView.findViewById(R.id.sessionTxtItemsCount)
            val txtUnitsCount: TextView = itemView.findViewById(R.id.sessionTxtUnitsCount)
            val btnActivate: Button = itemView.findViewById(R.id.sessionBtnActivate)
            val btnExport: Button = itemView.findViewById(R.id.sessionBtnExport)
            val btnDelete: ImageButton = itemView.findViewById(R.id.sessionBtnDelete)

            fun bind(session: InventorySession) {
                txtName.text = session.name
                txtDate.text = session.createdAt
                txtWarehouse.text = if (session.warehouseName.isNotBlank()) session.warehouseName else "المخزون العام للشركة"

                val isActive = session.status == "active"
                if (isActive) {
                    txtStatus.text = "🟢 نشطة حالياً"
                    txtStatus.setTextColor(itemView.context.getColor(R.color.badge_text))
                    btnActivate.visibility = View.GONE
                } else {
                    txtStatus.text = "مكتملة / سابقة"
                    txtStatus.setTextColor(itemView.context.getColor(R.color.text_secondary))
                    btnActivate.visibility = View.VISIBLE
                }

                val (uniqueCount, totalUnits) = db.getSessionSummary(session.id)
                txtItemsCount.text = "الأصناف: $uniqueCount صنف"
                txtUnitsCount.text = "إجمالي الحبات: ${String.format(Locale.US, "%.0f", totalUnits)} حبة"

                btnActivate.setOnClickListener { onActivate(session) }
                btnExport.setOnClickListener { onExport(session) }
                btnDelete.setOnClickListener { onDelete(session) }
            }
        }
    }
}
