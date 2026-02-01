package com.prypal.scanner

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView

class MaterialAdapter(
    private var items: List<Material>,
    private val onClick: (Material) -> Unit,
) : RecyclerView.Adapter<MaterialAdapter.MaterialViewHolder>() {

    fun update(newItems: List<Material>) {
        items = newItems
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): MaterialViewHolder {
        val view = LayoutInflater.from(parent.context).inflate(R.layout.item_material, parent, false)
        return MaterialViewHolder(view)
    }

    override fun onBindViewHolder(holder: MaterialViewHolder, position: Int) {
        val item = items[position]
        holder.bind(item)
        holder.itemView.setOnClickListener { onClick(item) }
    }

    override fun getItemCount(): Int = items.size

    class MaterialViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val code: TextView = itemView.findViewById(R.id.material_code)
        private val desc: TextView = itemView.findViewById(R.id.material_desc)
        private val count: TextView = itemView.findViewById(R.id.material_count)

        fun bind(material: Material) {
            code.text = "Material ${material.materialCode}"
            desc.text = material.description
            count.text = "${material.activeCount} / ${material.maxQty}"
        }
    }
}
