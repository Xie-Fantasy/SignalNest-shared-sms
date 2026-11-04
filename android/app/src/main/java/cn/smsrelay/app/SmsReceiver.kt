package cn.smsrelay.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject
import java.time.Instant
import java.util.UUID

class SmsReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) return
        val pending = goAsync()
        val app = RelayApp.from(context)
        app.scope.launch {
            try {
                withTimeout(8000) { app.intakeLock.withLock { intake(app, intent) } }
            } catch (_: Exception) {
                try { app.event("INTAKE_ERROR", "短信处理未完成；未输出正文") } catch (_: Exception) { }
            } finally { pending.finish() }
        }
    }
    private suspend fun intake(app: RelayApp, intent: Intent) {
        var c = app.settings.state.value
        if (!SimResolver.permissions(app)) { app.checkBinding(); return }
        if (!c.enabled && c.armId < 0) return
        if (!app.checkBinding()) return
        val lines = SimResolver.active(app)
        val evidence = SimResolver.evidence(intent)
        val decision = SimResolver.resolve(lines, evidence)
        // Metadata only; never read PDU or plaintext for unknown or blocked lines.
        if (decision.id == null) {
            val keys = (SimResolver.subKeys + SimResolver.slotKeys).filter { intent.hasExtra(it) }.joinToString(",")
            app.event(decision.reason, "无法确认接收线路，已阻止；归属字段=$keys，订阅=${evidence.subscriptions}，卡槽=${evidence.slots}；不保存正文")
            return
        }
        c = app.settings.state.value
        val probing = c.armId >= 0 && System.currentTimeMillis() < c.armUntil
        if (probing && decision.id != c.armId) {
            app.event("PROBE_WRONG_SIM", "测试短信进入其他线路，请检查测试接收号码")
            return
        }
        if (!probing && (!c.enabled || decision.id != c.boundId || !SimResolver.ready(c, lines))) {
            if (c.enabled) app.event("SIM_BLOCKED", "非共享卡或未通过双卡验证，已阻止")
            return
        }
        val parts = Telephony.Sms.Intents.getMessagesFromIntent(intent)?.toList().orEmpty()
        if (parts.isEmpty()) { app.event("EMPTY_SMS", "没有可解析的短信分段"); return }
        val senders = parts.map { it.originatingAddress.orEmpty() }.distinct()
        if (senders.size != 1 || senders.single().isBlank()) {
            app.event("MULTIPART_CONFLICT", "短信分段来源冲突，已阻止"); return
        }
        val body = parts.joinToString("") { it.messageBody.orEmpty() }
        if (body.isEmpty() || body.length > 10000 || senders.single().length > 256) {
            app.event("SMS_TOO_LARGE", "短信为空或超出接口限制"); return
        }
        if (probing) {
            if (body.contains(c.armCode)) {
                app.settings.update { current ->
                    if (current.simSignature != c.simSignature || current.armCode != c.armCode) current
                    else current.copy(testedIds = current.testedIds + decision.id, armId = -1,
                        armCode = "", armUntil = 0, lastError = "")
                }
                app.event("PROBE_PASSED", "卡槽 ${lines.first { it.id == decision.id }.slot + 1} 归属测试通过；未上传")
            } else app.event("PROBE_WAIT", "等待包含本次测试标记的短信；未上传")
            return
        }
        if (!RelayRules.matches(body, c.keywords)) {
            app.event("KEYWORD_MISS", "未命中转发关键词；不保存正文"); return
        }
        val now = System.currentTimeMillis()
        val received = parts.minOf { it.timestampMillis }
        if (received <= 0 || received > now + 120000 || now - received >= 600000) {
            app.event("EXPIRED", "短信时间无效或已超过 10 分钟，已阻止"); return
        }
        if (!app.checkBinding()) return
        val current = app.settings.state.value
        if (!current.enabled || RelayRules.configKey(current, app.vault) != RelayRules.configKey(c, app.vault)) return
        val digest = app.vault.digest("${senders.single()}|${decision.id}|$received|$body")
        val id = UUID.randomUUID().toString()
        val payload = JSONObject().put("deviceId", c.deviceId).put("clientMessageId", id)
            .put("sender", senders.single()).put("recipient", c.recipient)
            .put("message", if (c.fullText) body else "[收到匹配规则的短信，正文已隐藏]")
            .put("receivedAt", Instant.ofEpochMilli(received).toString()).put("simVerified", true)
        val row = QueuedMessage(id, digest, app.vault.encrypt(payload.toString()),
            RelayRules.configKey(c, app.vault), now, received + 600000)
        if (app.db.dao().insert(row) != -1L) {
            val after = app.settings.state.value
            if (!after.enabled || row.configKey != RelayRules.configKey(after, app.vault)) {
                app.db.dao().cancelAll()
                return
            }
            app.event("QUEUED", "共享卡短信已加密加入队列")
            RelayApp.enqueue(app)
        } else app.event("DUPLICATE", "重复广播已忽略")
    }
}

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            RelayApp.schedulePeriodic(context)
            RelayApp.enqueue(context)
        }
    }
}
