package com.prypal.scanner

import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView

class MaterialsActivity : AppCompatActivity() {
    private lateinit var adapter: MaterialAdapter

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_materials)

        val list = findViewById<RecyclerView>(R.id.materials_list)
        list.layoutManager = LinearLayoutManager(this)
        adapter = MaterialAdapter(emptyList()) { material ->
            val intent = Intent(this, ScanActivity::class.java)
            intent.putExtra("material_code", material.materialCode)
            startActivity(intent)
        }
        list.adapter = adapter
    }

    override fun onResume() {
        super.onResume()
        FirestoreRepo.getMaterials { materials ->
            runOnUiThread { adapter.update(materials) }
        }
    }
}
