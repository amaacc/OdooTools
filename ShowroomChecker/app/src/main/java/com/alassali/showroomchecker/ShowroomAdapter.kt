package com.alassali.showroomchecker

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView

class ShowroomAdapter(
    private var allShowrooms: List<Showroom>,
    private val selectedShowroomId: Int,
    private val onShowroomSelected: (Showroom) -> Unit
) : RecyclerView.Adapter<ShowroomAdapter.ViewHolder>() {

    private var filteredList: List<Showroom> = allShowrooms

    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val root: View = view.findViewById(R.id.showroomItemRoot)
        val txtName: TextView = view.findViewById(R.id.txtShowroomName)
        val txtCode: TextView = view.findViewById(R.id.txtShowroomCode)
        val txtBadge: TextView = view.findViewById(R.id.txtSelectedBadge)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context).inflate(R.layout.item_showroom, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val showroom = filteredList[position]
        holder.txtName.text = showroom.name
        holder.txtCode.text = if (showroom.code.isNotBlank()) "كود: ${showroom.code}" else ""
        holder.txtBadge.visibility = if (showroom.id == selectedShowroomId) View.VISIBLE else View.GONE

        holder.root.setOnClickListener {
            onShowroomSelected(showroom)
        }
    }

    override fun getItemCount(): Int = filteredList.size

    fun updateList(newList: List<Showroom>) {
        allShowrooms = newList
        filteredList = newList
        notifyDataSetChanged()
    }

    fun filter(query: String) {
        val q = query.trim().lowercase()
        filteredList = if (q.isEmpty()) {
            allShowrooms
        } else {
            allShowrooms.filter {
                it.name.lowercase().contains(q) || it.code.lowercase().contains(q)
            }
        }
        notifyDataSetChanged()
    }
}
