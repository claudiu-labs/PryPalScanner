package com.prypal.scanner

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView

class DrumAdapter(
    private var items: List<Drum>,
) : RecyclerView.Adapter<DrumAdapter.DrumViewHolder>() {

    fun update(newItems: List<Drum>) {
        items = newItems
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): DrumViewHolder {
        val view = LayoutInflater.from(parent.context).inflate(R.layout.item_drum, parent, false)
        return DrumViewHolder(view)
    }

    override fun onBindViewHolder(holder: DrumViewHolder, position: Int) {
        holder.bind(items[position])
    }

    override fun getItemCount(): Int = items.size

    class DrumViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val number: TextView = itemView.findViewById(R.id.drum_number)

        fun bind(drum: Drum) {
            number.text = drum.drumNumber
        }
    }
}
