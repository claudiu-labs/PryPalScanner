package com.prypal.scanner

import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView

class ScanActivity : AppCompatActivity() {
    private lateinit var adapter: DrumAdapter
    private var material: Material? = null
    private var activeDrums: List<Drum> = emptyList()

    private lateinit var countText: TextView
    private lateinit var scanInput: EditText
    private lateinit var materialInput: EditText
    private lateinit var qtyInput: EditText
    private lateinit var statusText: TextView
    private lateinit var generateButton: Button
    private lateinit var incompleteButton: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_scan)

        countText = findViewById(R.id.count_text)
        scanInput = findViewById(R.id.scan_input)
        materialInput = findViewById(R.id.material_input)
        qtyInput = findViewById(R.id.qty_input)
        statusText = findViewById(R.id.status_text)
        generateButton = findViewById(R.id.generate_button)
        incompleteButton = findViewById(R.id.incomplete_button)

        val list = findViewById<RecyclerView>(R.id.drums_list)
        list.layoutManager = LinearLayoutManager(this)
        adapter = DrumAdapter(emptyList())
        list.adapter = adapter

        val materialCode = intent.getStringExtra("material_code") ?: ""

        scanInput.requestFocus()

        findViewById<Button>(R.id.save_button).setOnClickListener {
            onSaveScan(materialCode)
        }
        findViewById<Button>(R.id.undo_button).setOnClickListener {
            statusText.text = ""
            FirestoreRepo.undoLast(materialCode) { ok ->
                runOnUiThread {
                    statusText.text = if (ok) "Ultimul tambur a fost sters." else "Nu exista scanari active."
                    reload(materialCode)
                }
            }
        }

        generateButton.setOnClickListener {
            confirmGenerate(materialCode, "FULL")
        }
        incompleteButton.setOnClickListener {
            confirmGenerate(materialCode, "INCOMPLETE")
        }

        reload(materialCode)
    }

    private fun reload(materialCode: String) {
        statusText.text = ""
        FirestoreRepo.getMaterial(materialCode) { mat ->
            if (mat == null) return@getMaterial
            material = mat
            runOnUiThread { title = "Material ${mat.materialCode}" }
            materialInput.setText(mat.materialCode)

            FirestoreRepo.getActiveDrums(materialCode) { drums ->
                activeDrums = drums
                runOnUiThread {
                    adapter.update(drums)
                    countText.text = "${drums.size} / ${mat.maxQty}"
                    updateButtons()
                }
            }
        }
    }

    private fun updateButtons() {
        val mat = material ?: return
        val count = activeDrums.size
        generateButton.isEnabled = count >= mat.maxQty && mat.maxQty > 0
        incompleteButton.isEnabled = mat.allowIncomplete && count in 1 until mat.maxQty
    }

    private fun onSaveScan(materialCode: String) {
        statusText.text = ""
        val raw = scanInput.text.toString().trim()
        if (raw.isEmpty()) {
            statusText.text = "Introdu scanul"
            return
        }
        val parsed = parseScan(raw)
        if (parsed == null) {
            statusText.text = "Scan invalid"
            return
        }
        val (drumType, drumNumber) = parsed
        val materialFromLabel = materialInput.text.toString().trim()
        val stdQty = qtyInput.text.toString().trim()
        val mat = material
        if (mat == null) {
            statusText.text = "Material invalid"
            return
        }
        if (materialFromLabel != mat.materialCode) {
            statusText.text = "Material gresit pe eticheta. Nu se poate inregistra pe paletul cu \"${mat.materialCode}\"."
            return
        }
        if (activeDrums.any { it.drumNumber == drumNumber }) {
            statusText.text = "Tambur dublat pe acest palet. Va rugam verificati!"
            return
        }

        FirestoreRepo.getDrum(drumNumber) { existing ->
            if (existing != null) {
                val priorPallet = existing.palletId
                if (priorPallet.isNotBlank()) {
                    FirestoreRepo.getPalletDate(priorPallet) { date ->
                        runOnUiThread {
                            statusText.text = "Tamburul a existat si pe Palletul $priorPallet din data de ${date ?: "N/A"}. Va rugam verificati!"
                        }
                    }
                } else {
                    runOnUiThread {
                        statusText.text = "Tambur dublat pe acest palet. Va rugam verificati!"
                    }
                }
                return@getDrum
            }

            FirestoreRepo.addDrum(mat.materialCode, drumNumber, drumType, stdQty, "android") { ok ->
                runOnUiThread {
                    statusText.text = if (ok) "Scan salvat." else "Eroare la salvare"
                    scanInput.setText("")
                    qtyInput.setText("")
                    scanInput.requestFocus()
                    reload(materialCode)
                }
            }
        }
    }

    private fun confirmGenerate(materialCode: String, type: String) {
        val mat = material ?: return
        val count = activeDrums.size
        if (type == "FULL" && count < mat.maxQty) return
        if (type == "INCOMPLETE" && !(mat.allowIncomplete && count in 1 until mat.maxQty)) return

        val msg = if (type == "FULL") {
            "Aveti pe palet Max Qty / Pallet tamburi?"
        } else {
            "Sigur doriti sa finalizati paletul incomplet?"
        }

        AlertDialog.Builder(this)
            .setMessage(msg)
            .setPositiveButton("DA") { _, _ ->
                FirestoreRepo.generatePallet(mat, type, activeDrums) { ok ->
                    runOnUiThread {
                        statusText.text = if (ok) "Palet generat cu succes!" else "Eroare la generare palet"
                        reload(materialCode)
                    }
                }
            }
            .setNegativeButton("Renunta", null)
            .show()
    }
}
