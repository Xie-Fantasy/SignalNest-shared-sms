package cn.smsrelay.app

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlin.random.Random

class UploadWorker(context: Context, parameters: WorkerParameters) : CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val app = RelayApp.from(applicationContext)
        app.uploadLock.withLock {
            val dao = app.db.dao()
            val now = System.currentTimeMillis()
            dao.expire(now)
            dao.prune(now - 86400000)
            if (!app.checkBinding() || !app.settings.state.value.enabled) return@withLock Result.success()
            var retry = false
            for (row in dao.pending()) {
                val c = app.settings.state.value
                if (!c.enabled || !app.checkBinding()) break
                if (row.expires <= System.currentTimeMillis()) {
                    dao.update(row.copy(status = "EXPIRED", payload = byteArrayOf())); continue
                }
                if (row.configKey != RelayRules.configKey(c, app.vault)) {
                    dao.update(row.copy(status = "CANCELLED", payload = byteArrayOf())); continue
                }
                if (row.nextRetry > System.currentTimeMillis()) { retry = true; continue }
                val payload = try { app.vault.decrypt(row.payload) } catch (_: Exception) {
                    dao.update(row.copy(status = "INVALID", payload = byteArrayOf()))
                    app.event("DECRYPT_ERROR", "队列密钥不可用，已清除该条正文"); continue
                }
                val uploadConfig = app.settings.state.value
                if (!uploadConfig.enabled || row.configKey != RelayRules.configKey(uploadConfig, app.vault)) {
                    dao.update(row.copy(status = "CANCELLED", payload = byteArrayOf())); continue
                }
                val result = try { app.api.upload(uploadConfig, payload) }
                    catch (_: Exception) { UploadResult.RETRY }
                when (result) {
                    UploadResult.ACCEPTED -> {
                        dao.update(row.copy(status = "ACKED", payload = byteArrayOf()))
                        app.settings.update { it.copy(lastSync = System.currentTimeMillis(), lastError = "") }
                        app.event("ACKED", "服务器已持久接收；群投递由服务器处理")
                    }
                    UploadResult.AUTH -> {
                        app.settings.update { it.copy(enabled = false, connected = false,
                            lastError = "授权已失效，请重新配对并测试连接") }
                        dao.cancelAll()
                        app.event("AUTH_ERROR", "上传授权被拒绝，已暂停并清除待上传正文")
                        return@withLock Result.success()
                    }
                    UploadResult.REJECTED, UploadResult.INVALID -> {
                        dao.update(row.copy(status = "REJECTED", payload = byteArrayOf()))
                        app.settings.update { it.copy(lastError = "服务器拒绝消息，请检查绑定或接口") }
                        app.event("SERVER_REJECTED", "消息被拒绝；不再重试")
                    }
                    UploadResult.RETRY -> {
                        val delay = (15000L shl row.attempts.coerceAtMost(4)) + Random.nextLong(0, 4000)
                        dao.retry(row.id, row.attempts + 1, System.currentTimeMillis() + delay)
                        app.settings.update { it.copy(lastError = "网络暂不可用，队列等待重试") }
                        app.event("NETWORK_ERROR", "上传未确认，保留原消息 ID 等待重试")
                        retry = true
                    }
                }
            }
            for (row in dao.acknowledged()) {
                val c = app.settings.state.value
                if (row.configKey != RelayRules.configKey(c, app.vault)) {
                    dao.update(row.copy(status = "CANCELLED")); continue
                }
                try {
                    when (app.api.delivery(c, row.id)) {
                        "delivered" -> {
                            dao.update(row.copy(status = "DELIVERED"))
                            app.event("QQ_DELIVERED", "QQ 接口已确认群投递成功")
                        }
                        "delivery_unknown" -> {
                            dao.update(row.copy(status = "DELIVERY_UNKNOWN"))
                            app.settings.update { it.copy(lastError = "QQ 投递结果不明，服务器未重复发送") }
                            app.event("QQ_UNKNOWN", "QQ 投递结果不明，请检查群；未自动重发")
                        }
                        "expired", "missing" -> {
                            dao.update(row.copy(status = "SERVER_EXPIRED"))
                            app.settings.update { it.copy(lastError = "该条短信未确认群投递，已过期") }
                            app.event("QQ_EXPIRED", "服务器待投递短信已过期或记录不存在")
                        }
                        else -> retry = true
                    }
                } catch (_: Exception) {
                    if (System.currentTimeMillis() - row.created < 900000) retry = true
                    else {
                        dao.update(row.copy(status = "DELIVERY_UNCONFIRMED"))
                        app.event("QQ_UNCONFIRMED", "未能查询群投递结果，请检查诊断与群消息")
                    }
                }
            }
            if (dao.pending().isNotEmpty()) retry = true
            if (retry) Result.retry() else Result.success()
        }
    }
}
