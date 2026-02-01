package com.prypal.scanner

import java.util.Locale


data class Material(
    val materialCode: String,
    val description: String,
    val maxQty: Long,
    val prefix: String,
    val allowIncomplete: Boolean,
    val active: Boolean,
    val activeCount: Long,
) {
    companion object {
        fun from(id: String, data: Map<String, Any>): Material {
            val maxQty = (data["max_qty"] as? Number)?.toLong() ?: 0L
            val allowIncomplete = data["allow_incomplete"] as? Boolean ?: false
            val active = data["active"] as? Boolean ?: true
            val activeCount = (data["active_count"] as? Number)?.toLong() ?: 0L
            return Material(
                materialCode = (data["material_code"] as? String)?.ifBlank { id } ?: id,
                description = data["description"] as? String ?: "",
                maxQty = maxQty,
                prefix = data["prefix"] as? String ?: "",
                allowIncomplete = allowIncomplete,
                active = active,
                activeCount = activeCount,
            )
        }
    }
}

data class Drum(
    val drumNumber: String,
    val drumType: String,
    val materialCode: String,
    val palletId: String,
    val status: String,
    val timestamp: String,
) {
    companion object {
        fun from(id: String, data: Map<String, Any>): Drum {
            return Drum(
                drumNumber = (data["drum_number"] as? String)?.ifBlank { id } ?: id,
                drumType = data["drum_type"] as? String ?: "",
                materialCode = data["material_code"] as? String ?: "",
                palletId = data["pallet_id"] as? String ?: "",
                status = data["status"] as? String ?: "",
                timestamp = data["timestamp"] as? String ?: "",
            )
        }
    }
}

fun parseScan(input: String): Pair<String, String>? {
    val parts = input.trim().split(" ").filter { it.isNotBlank() }
    if (parts.size < 2) return null
    val drumNumber = parts.last()
    val drumType = parts.dropLast(1).joinToString(" ")
    return drumType to drumNumber
}
