package cn.smsrelay.app

import okhttp3.OkHttpClient
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.net.URI
import java.util.concurrent.TimeUnit

enum class UploadResult { ACCEPTED, REJECTED, AUTH, RETRY, INVALID }
class RelayApi {
    private val client = OkHttpClient.Builder().connectTimeout(8, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS).writeTimeout(10, TimeUnit.SECONDS)
        .callTimeout(25, TimeUnit.SECONDS).followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false).build()
    fun validateEndpoint(value: String): String {
        val uri = URI(value.trim().trimEnd('/'))
        require(uri.scheme == "https" && !uri.host.isNullOrBlank() && uri.userInfo == null &&
            uri.query == null && uri.fragment == null && uri.path.orEmpty().isEmpty()) { "需要 HTTPS 服务器地址" }
        return uri.toString()
    }
    fun check(c: RelayConfig): String {
        val base = validateEndpoint(c.endpoint)
        require(c.token.length in 32..256 && c.token.none { it.isWhitespace() })
        val request = Request.Builder().url("$base/api/android/status")
            .header("Authorization", "Bearer ${c.token}").build()
        client.newCall(request).execute().use { response ->
            require(response.isSuccessful) { "连接或授权失败" }
            val body = response.body?.string().orEmpty()
            require(body.length < 16384)
            val json = JSONObject(body)
            require(json.optString("status") == "ok" && json.optInt("protocol") == 2)
            require(json.optBoolean("qqConfigured")) { "服务器 QQ 转发未配置" }
            val recipient = json.getString("recipient")
            require(Regex("1[3-9][0-9]{9}").matches(recipient))
            return recipient
        }
    }
    fun upload(c: RelayConfig, payload: String): UploadResult {
        val base = validateEndpoint(c.endpoint)
        val request = Request.Builder().url("$base/api/android/message/push")
            .header("Authorization", "Bearer ${c.token}")
            .post(payload.toRequestBody("application/json; charset=utf-8".toMediaType())).build()
        client.newCall(request).execute().use { response ->
            if (response.code in listOf(401, 403)) return UploadResult.AUTH
            if (response.code == 429 || response.code >= 500) return UploadResult.RETRY
            if (!response.isSuccessful) return UploadResult.INVALID
            val text = response.body?.string().orEmpty()
            if (text.length > 16384) return UploadResult.INVALID
            val json = JSONObject(text)
            if (!json.optBoolean("success")) return UploadResult.INVALID
            return if (json.optBoolean("accepted")) UploadResult.ACCEPTED else UploadResult.REJECTED
        }
    }
    fun delivery(c: RelayConfig, messageId: String): String {
        val base = validateEndpoint(c.endpoint)
        require(java.util.UUID.fromString(messageId).toString() == messageId)
        require(java.util.UUID.fromString(c.deviceId).toString() == c.deviceId)
        val request = Request.Builder().url("$base/api/android/message/status?deviceId=${c.deviceId}&clientMessageId=$messageId")
            .header("Authorization", "Bearer ${c.token}").build()
        client.newCall(request).execute().use { response ->
            if (response.code == 404) return "missing"
            require(response.isSuccessful)
            val body = response.body?.string().orEmpty()
            require(body.length <= 16384)
            return JSONObject(body).getString("delivery")
        }
    }
}
