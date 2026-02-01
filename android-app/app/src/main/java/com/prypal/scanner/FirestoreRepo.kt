package com.prypal.scanner

import com.google.firebase.firestore.FieldValue
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.Query

object FirestoreRepo {
    private val db: FirebaseFirestore = FirebaseFirestore.getInstance()

    fun getSettings(onResult: (Map<String, Any>) -> Unit) {
        db.collection("settings").document("global").get()
            .addOnSuccessListener { doc ->
                onResult(doc.data ?: emptyMap())
            }
            .addOnFailureListener { onResult(emptyMap()) }
    }

    fun getMaterials(onResult: (List<Material>) -> Unit) {
        db.collection("materials").get()
            .addOnSuccessListener { snap ->
                val list = snap.documents.mapNotNull { d ->
                    val data = d.data ?: return@mapNotNull null
                    Material.from(d.id, data)
                }.filter { it.active }
                onResult(list)
            }
            .addOnFailureListener { onResult(emptyList()) }
    }

    fun getMaterial(materialCode: String, onResult: (Material?) -> Unit) {
        db.collection("materials").document(materialCode).get()
            .addOnSuccessListener { doc ->
                val data = doc.data
                if (data == null) {
                    onResult(null)
                } else {
                    onResult(Material.from(doc.id, data))
                }
            }
            .addOnFailureListener { onResult(null) }
    }

    fun getActiveDrums(materialCode: String, onResult: (List<Drum>) -> Unit) {
        db.collection("drums")
            .whereEqualTo("material_code", materialCode)
            .whereEqualTo("status", "ACTIVE")
            .orderBy("timestamp", Query.Direction.ASCENDING)
            .get()
            .addOnSuccessListener { snap ->
                val list = snap.documents.mapNotNull { d ->
                    val data = d.data ?: return@mapNotNull null
                    Drum.from(d.id, data)
                }
                onResult(list)
            }
            .addOnFailureListener { onResult(emptyList()) }
    }

    fun getDrum(drumNumber: String, onResult: (Drum?) -> Unit) {
        db.collection("drums").document(drumNumber).get()
            .addOnSuccessListener { doc ->
                val data = doc.data
                if (data == null) onResult(null) else onResult(Drum.from(doc.id, data))
            }
            .addOnFailureListener { onResult(null) }
    }

    fun addDrum(materialCode: String, drumNumber: String, drumType: String?, standardQty: String?, operatorName: String, onDone: (Boolean) -> Unit) {
        val payload = hashMapOf(
            "timestamp" to System.currentTimeMillis().toString(),
            "material_code" to materialCode,
            "drum_number" to drumNumber,
            "drum_type" to (drumType ?: ""),
            "standard_qty" to (standardQty ?: ""),
            "pallet_id" to "",
            "status" to "ACTIVE",
            "device_id" to "android",
            "operator" to operatorName,
        )
        db.collection("drums").document(drumNumber).set(payload)
            .addOnSuccessListener {
                db.collection("materials").document(materialCode)
                    .set(mapOf("active_count" to FieldValue.increment(1)), com.google.firebase.firestore.SetOptions.merge())
                onDone(true)
            }
            .addOnFailureListener { onDone(false) }
    }

    fun undoLast(materialCode: String, onDone: (Boolean) -> Unit) {
        db.collection("drums")
            .whereEqualTo("material_code", materialCode)
            .whereEqualTo("status", "ACTIVE")
            .orderBy("timestamp", Query.Direction.DESCENDING)
            .limit(1)
            .get()
            .addOnSuccessListener { snap ->
                val doc = snap.documents.firstOrNull()
                if (doc == null) {
                    onDone(false)
                    return@addOnSuccessListener
                }
                doc.reference.delete().addOnSuccessListener {
                    db.collection("materials").document(materialCode)
                        .set(mapOf("active_count" to FieldValue.increment(-1)), com.google.firebase.firestore.SetOptions.merge())
                    onDone(true)
                }.addOnFailureListener { onDone(false) }
            }
            .addOnFailureListener { onDone(false) }
    }

    fun getPalletDate(palletId: String, onResult: (String?) -> Unit) {
        if (palletId.isBlank()) {
            onResult(null)
            return
        }
        db.collection("pallets").document(palletId).get()
            .addOnSuccessListener { doc ->
                val data = doc.data
                onResult(data?.get("created_at") as? String)
            }
            .addOnFailureListener { onResult(null) }
    }

    fun generatePallet(material: Material, completeType: String, activeDrums: List<Drum>, onDone: (Boolean) -> Unit) {
        db.collection("settings").document("global").get()
            .addOnSuccessListener { doc ->
                val data = doc.data ?: emptyMap()
                val counter = (data["global_pallet_counter"] as? Number)?.toLong() ?: 0L
                val palletId = "${material.prefix}${counter}"

                val batch = db.batch()
                for (drum in activeDrums) {
                    val ref = db.collection("drums").document(drum.drumNumber)
                    batch.set(ref, mapOf("pallet_id" to palletId, "status" to "COMPLETED"), com.google.firebase.firestore.SetOptions.merge())
                }
                val palletRef = db.collection("pallets").document(palletId)
                val palletPayload = hashMapOf(
                    "pallet_id" to palletId,
                    "material_code" to material.materialCode,
                    "description" to material.description,
                    "created_at" to System.currentTimeMillis().toString(),
                    "count" to activeDrums.size,
                    "complete_type" to completeType,
                )
                batch.set(palletRef, palletPayload, com.google.firebase.firestore.SetOptions.merge())
                val settingsRef = db.collection("settings").document("global")
                batch.set(settingsRef, mapOf("global_pallet_counter" to (counter + 1)), com.google.firebase.firestore.SetOptions.merge())
                val matRef = db.collection("materials").document(material.materialCode)
                batch.set(matRef, mapOf("active_count" to 0), com.google.firebase.firestore.SetOptions.merge())

                batch.commit()
                    .addOnSuccessListener { onDone(true) }
                    .addOnFailureListener { onDone(false) }
            }
            .addOnFailureListener { onDone(false) }
    }
}
