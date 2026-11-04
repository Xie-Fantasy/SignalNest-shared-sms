package cn.smsrelay.app

import android.content.Context
import android.util.Base64
import kotlinx.coroutines.flow.MutableStateFlow
import org.json.JSONObject
import java.util.UUID

data class RelayConfig(
    val endpoint: String = "https://example.com",
    val token: String = "",
    val recipient: String = "",
    val connected: Boolean = false,
    val enabled: Boolean = false,
    val keywords: String = "验证码",
    val fullText: Boolean = true,
    val boundId: Int = -1,
    val simSignature: String = "",
    val testedIds: Set<Int> = emptySet(),
    val deviceId: String = UUID.randomUUID().toString(),
    val lastSync: Long = 0,
    val lastError: String = "",
    val armId: Int = -1,
    val armCode: String = "",
    val armUntil: Long = 0
)

class Settings(context: Context, private val vault: Vault) {
    private val prefs = context.getSharedPreferences("relay-secure", Context.MODE_PRIVATE)
    val state = MutableStateFlow(read())
    init { update { it } }
    private fun read(): RelayConfig = try {
        val encoded = prefs.getString("cipher", null)
        if (encoded == null) RelayConfig() else {
            val j = JSONObject(vault.decrypt(Base64.decode(encoded, Base64.NO_WRAP)))
            RelayConfig(endpoint = j.getString("endpoint"), token = j.getString("token"),
                recipient = j.getString("recipient"), connected = j.getBoolean("connected"),
                enabled = j.getBoolean("enabled"), keywords = j.getString("keywords"),
                fullText = j.optBoolean("fullText", true), boundId = j.getInt("boundId"),
                simSignature = j.getString("simSignature"),
                testedIds = j.optString("testedIds").split(',').mapNotNull { it.toIntOrNull() }.toSet(),
                deviceId = j.getString("deviceId"), lastSync = j.optLong("lastSync"),
                lastError = j.optString("lastError"), armId = j.optInt("armId", -1),
                armCode = j.optString("armCode"), armUntil = j.optLong("armUntil"))
        }
    } catch (_: Exception) { RelayConfig(lastError = "加密配置无法读取，请重新配对") }

    @Synchronized fun update(change: (RelayConfig) -> RelayConfig): RelayConfig {
        val c = change(state.value)
        val j = JSONObject().put("endpoint", c.endpoint).put("token", c.token)
            .put("recipient", c.recipient).put("connected", c.connected).put("enabled", c.enabled)
            .put("keywords", c.keywords).put("fullText", c.fullText).put("boundId", c.boundId)
            .put("simSignature", c.simSignature).put("testedIds", c.testedIds.sorted().joinToString(","))
            .put("deviceId", c.deviceId).put("lastSync", c.lastSync).put("lastError", c.lastError)
            .put("armId", c.armId).put("armCode", c.armCode).put("armUntil", c.armUntil)
        check(prefs.edit().putString("cipher", Base64.encodeToString(vault.encrypt(j.toString()), Base64.NO_WRAP)).commit())
        state.value = c
        return c
    }
}
