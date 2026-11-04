package cn.smsrelay.app

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.telephony.SubscriptionManager
import androidx.core.content.ContextCompat

data class SimLine(val id: Int, val slot: Int, val label: String, val carrier: String)
data class SimEvidence(val subscriptions: List<Int>, val slots: List<Int>, val malformed: Boolean = false)
data class SimDecision(val id: Int? = null, val reason: String = "SIM_UNKNOWN")

object SimResolver {
    val subKeys = listOf("subscription", "subscription_id", "sub_id", "subId", "android.telephony.extra.SUBSCRIPTION_INDEX")
    val slotKeys = listOf("slot", "slot_id", "slotId", "simId", "phone", "phone_id", "android.telephony.extra.SLOT_INDEX")
    fun permissions(context: Context) = listOf(Manifest.permission.RECEIVE_SMS, Manifest.permission.READ_PHONE_STATE)
        .all { ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED }
    @Suppress("MissingPermission")
    fun active(context: Context): List<SimLine> {
        if (!permissions(context)) return emptyList()
        return try {
            context.getSystemService(SubscriptionManager::class.java).activeSubscriptionInfoList.orEmpty()
                .filter { it.subscriptionId >= 0 && it.simSlotIndex >= 0 }
                .map { SimLine(it.subscriptionId, it.simSlotIndex, it.displayName?.toString().orEmpty(),
                    it.carrierName?.toString().orEmpty()) }.sortedBy { it.id }
        } catch (_: Exception) { emptyList() }
    }
    fun signature(lines: List<SimLine>) = Build.FINGERPRINT + "|" + lines.sortedBy { it.id }
        .joinToString(";") { "${it.id}:${it.slot}:${it.carrier}:${it.label}" }
    fun evidence(intent: Intent): SimEvidence {
        var malformed = false
        fun values(keys: List<String>): List<Int> = keys.mapNotNull { key ->
            if (!intent.hasExtra(key)) return@mapNotNull null
            @Suppress("DEPRECATION") val raw = intent.extras?.get(key)
            val value = when (raw) {
                is Int -> raw
                is Long -> raw.takeIf { it in Int.MIN_VALUE..Int.MAX_VALUE }?.toInt()
                else -> null
            }
            if (value == null) malformed = true
            // Explicit invalid metadata is not a license to infer a SIM.
            if (value != null && value < 0) malformed = true
            value
        }
        return SimEvidence(values(subKeys), values(slotKeys), malformed)
    }
    fun resolve(lines: List<SimLine>, evidence: SimEvidence): SimDecision {
        if (lines.isEmpty() || lines.map { it.id }.distinct().size != lines.size ||
            lines.map { it.slot }.distinct().size != lines.size) return SimDecision(reason = "SIM_UNAVAILABLE")
        if (evidence.malformed) return SimDecision(reason = "SIM_CONFLICT")
        val candidates = mutableListOf<Int>()
        for (sub in evidence.subscriptions) {
            if (lines.count { it.id == sub } != 1) return SimDecision(reason = "SIM_CONFLICT")
            candidates += sub
        }
        for (slot in evidence.slots) {
            val match = lines.singleOrNull { it.slot == slot } ?: return SimDecision(reason = "SIM_CONFLICT")
            candidates += match.id
        }
        if (candidates.distinct().size > 1) return SimDecision(reason = "SIM_CONFLICT")
        if (candidates.isNotEmpty()) return SimDecision(candidates.first(), "SIM_RESOLVED")
        return if (lines.size == 1) SimDecision(lines.single().id, "SINGLE_SIM") else SimDecision()
    }
    fun bindingValid(c: RelayConfig, lines: List<SimLine>) =
        lines.isNotEmpty() && c.boundId in lines.map { it.id } && c.simSignature == signature(lines)
    fun ready(c: RelayConfig, lines: List<SimLine>) = bindingValid(c, lines) &&
        (lines.size == 1 || lines.all { it.id in c.testedIds })
}
