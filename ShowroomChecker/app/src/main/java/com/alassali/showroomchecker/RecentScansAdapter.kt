package com.alassali.showroomchecker

import android.content.res.ColorStateList
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.RecyclerView
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class RecentScansAdapter(
    private val scans: MutableList<ProductStock>,
    private val onItemClicked: (ProductStock) -> Unit
) : RecyclerView.Adapter<RecentScansAdapter.ViewHolder>() {

    private val timeFormat = SimpleDateFormat("HH:mm", Locale.getDefault())

    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val txtNameAr: TextView = view.findViewById(R.id.txtRecentNameAr)
        val txtBarcode: TextView = view.findViewById(R.id.txtRecentBarcode)
        val txtTime: TextView = view.findViewById(R.id.txtRecentTime)
        val txtStockPill: TextView = view.findViewById(R.id.txtRecentStockPill)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context).inflate(R.layout.item_recent_scan, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val item = scans[position]
        val context = holder.itemView.context

        holder.txtNameAr.text = item.nameAr.ifBlank { item.barcode }
        holder.txtBarcode.text = item.barcode
        holder.txtTime.text = timeFormat.format(Date(item.timestamp))

        // Stock formatting & color coding
        val qtyText = if (item.stockQty % 1.0 == 0.0) {
            String.format(Locale.US, "%.0f حبة", item.stockQty)
        } else {
            String.format(Locale.US, "%.2f حبة", item.stockQty)
        }
        holder.txtStockPill.text = qtyText

        if (item.stockQty > 0) {
            holder.txtStockPill.setTextColor(ContextCompat.getColor(context, R.color.stock_green_text))
            holder.txtStockPill.backgroundTintList = ColorStateList.valueOf(
                ContextCompat.getColor(context, R.color.stock_green_bg)
            )
        } else {
            holder.txtStockPill.setTextColor(ContextCompat.getColor(context, R.color.stock_red_text))
            holder.txtStockPill.backgroundTintList = ColorStateList.valueOf(
                ContextCompat.getColor(context, R.color.stock_red_bg)
            )
        }

        holder.itemView.setOnClickListener {
            onItemClicked(item)
        }
    }

    override fun getItemCount(): Int = scans.size

    fun addScan(product: ProductStock) {
        // Remove prior entry of same barcode if already exists to keep top fresh
        val existingIndex = scans.indexOfFirst { it.barcode == product.barcode }
        if (existingIndex >= 0) {
            scans.removeAt(existingIndex)
            notifyItemRemoved(existingIndex)
        }
        scans.add(0, product)
        notifyItemInserted(0)
    }

    fun clearAll() {
        val count = scans.size
        scans.clear()
        notifyItemRangeRemoved(0, count)
    }
}
