package cn.smsrelay.app

import android.Manifest
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.Settings as SystemSettings
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID

class MainActivity : ComponentActivity() {
    private val app get() = RelayApp.from(this)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE == 0)
            window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        enableEdgeToEdge()
        setContent { RelayScreen(app) }
    }
    override fun onResume() {
        super.onResume()
        app.observeSims()
        lifecycleScope.launch(Dispatchers.IO) { app.checkBinding() }
    }
}

private val blue = Color(0xFF2563EB)
private fun time(value: Long): String = if (value == 0L) "暂无" else
    SimpleDateFormat("MM-dd HH:mm:ss", Locale.CHINA).format(Date(value))
private fun masked(value: String): String = if (value.length < 7) "未配对" else value.take(3) + "****" + value.takeLast(4)

@Composable private fun RelayScreen(app: RelayApp) {
    val c by app.settings.state.collectAsState()
    val events by app.db.dao().events().collectAsState(initial = emptyList())
    val queue by app.db.dao().count().collectAsState(initial = 0)
    var page by remember { mutableIntStateOf(0) }
    var permissionEpoch by remember { mutableIntStateOf(0) }
    var feedback by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var confirmSim by remember { mutableStateOf<SimLine?>(null) }
    var endpoint by remember(c.endpoint) { mutableStateOf(c.endpoint) }
    var token by remember { mutableStateOf("") }
    var keywords by remember(c.keywords) { mutableStateOf(c.keywords) }
    val scope = rememberCoroutineScope()
    // Re-read the system list on recomposition; it is never treated as permanent.
    @Suppress("UNUSED_VARIABLE") val epoch = permissionEpoch
    val lines = SimResolver.active(app)
    val permissions = SimResolver.permissions(app)
    val ready = permissions && SimResolver.ready(c, lines) && c.connected &&
        c.token.isNotEmpty() && RelayRules.keywords(c.keywords).isNotEmpty()
    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        permissionEpoch++
        app.observeSims()
        feedback = if (SimResolver.permissions(app)) "权限已授权，请绑定共享 SIM" else "需要接收短信和电话状态权限才能识别线路"
    }
    fun saveServer(base: String, secret: String) {
        scope.launch {
            busy = true
            try {
                val normalized = app.api.validateEndpoint(base)
                val cleaned = secret.trim().removePrefix("Bearer ").trim()
                require(cleaned.length in 32..256 && cleaned.none { it.isWhitespace() })
                withContext(Dispatchers.IO) {
                    app.settings.update { it.copy(endpoint = normalized, token = cleaned,
                        connected = false, enabled = false, recipient = "", lastError = "") }
                    app.db.dao().cancelAll()
                }
                token = ""
                feedback = "配对信息已加密保存，请测试连接"
            } catch (_: Exception) { feedback = "配对失败：请检查 HTTPS 地址和 Token" }
            busy = false
        }
    }
    val importer = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) scope.launch {
            try {
                val json = withContext(Dispatchers.IO) {
                    app.contentResolver.openInputStream(uri)!!.use {
                        val buffer = ByteArray(16385)
                        var size = 0
                        while (size < buffer.size) {
                            val read = it.read(buffer, size, buffer.size - size)
                            if (read < 0) break
                            size += read
                        }
                        require(size <= 16384)
                        JSONObject(buffer.copyOf(size).toString(Charsets.UTF_8))
                    }
                }
                saveServer(json.getString("endpoint"), json.getString("token"))
            } catch (_: Exception) { feedback = "无法读取配对文件，请选择 server-credentials.local.smsrelay" }
        }
    }
    MaterialTheme(colorScheme = lightColorScheme(primary = blue, background = Color(0xFFF5F7FC),
        surface = Color.White, secondaryContainer = Color(0xFFE6EDFF))) {
        Scaffold(containerColor = MaterialTheme.colorScheme.background, bottomBar = {
            NavigationBar(containerColor = Color.White) {
                listOf("首页", "SIM", "规则", "服务器", "诊断").forEachIndexed { index, title ->
                    NavigationBarItem(selected = page == index, onClick = { page = index; feedback = "" },
                        icon = { Text(listOf("◉", "▣", "≡", "⇄", "◎")[index]) }, label = { Text(title) })
                }
            }
        }) { padding ->
            Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Text("共享短信", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
                Text(listOf("把共享卡的短信，送到原来的 QQ 群", "仅允许你明确选择的线路", "先筛选，再上传", "连接你原来的短信网关", "只记录状态，不展示短信内容")[page],
                    style = MaterialTheme.typography.bodyMedium, color = Color(0xFF64748B))
                if (feedback.isNotBlank()) Note(feedback)
                when (page) {
                    0 -> {
                        Panel(if (c.enabled) "自动转发已开启" else "自动转发已暂停") {
                            Text(if (c.enabled) "仅转发绑定线路、匹配关键词的短信" else "完成配对、权限和 SIM 绑定后即可开启")
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text("自动转发", Modifier.padding(top = 14.dp))
                                Switch(c.enabled, enabled = c.enabled || ready, onCheckedChange = { value ->
                                    scope.launch(Dispatchers.IO) {
                                        val fresh = app.settings.state.value
                                        val active = SimResolver.active(app)
                                        if (value && !(SimResolver.permissions(app) && SimResolver.ready(fresh, active) &&
                                            fresh.connected && RelayRules.keywords(fresh.keywords).isNotEmpty())) return@launch
                                        app.settings.update { it.copy(enabled = value, armId = -1, armCode = "", lastError = "") }
                                        if (value) RelayApp.enqueue(app) else app.db.dao().cancelAll()
                                    }
                                })
                            }
                        }
                        Panel("当前状态") {
                            StatusRow("共享 SIM", lines.firstOrNull { it.id == c.boundId }?.let { "卡槽 ${it.slot + 1} · ${it.label}" } ?: "未绑定")
                            StatusRow("接收号码", masked(c.recipient))
                            StatusRow("服务器", if (c.connected) "授权连接已验证" else "需要配对 / 测试连接")
                            StatusRow("待同步", "$queue 条")
                            StatusRow("最近接收确认", time(c.lastSync))
                            if (c.lastError.isNotBlank()) Text(c.lastError, color = MaterialTheme.colorScheme.error)
                        }
                        if (!permissions) Button(onClick = {
                            permissionLauncher.launch(arrayOf(Manifest.permission.RECEIVE_SMS, Manifest.permission.READ_PHONE_STATE))
                        }, modifier = Modifier.fillMaxWidth()) { Text("授予短信与 SIM 权限") }
                        if (!ready) Note(when {
                            !c.connected -> "先进入「服务器」导入配对文件并测试连接。"
                            c.boundId < 0 -> "进入「SIM」选择共享卡。"
                            lines.size > 1 && !SimResolver.ready(c, lines) -> "双卡需要逐卡接收测试短信，验证通过后才能开启。"
                            else -> "请检查短信权限、SIM 状态和转发关键词。"
                        })
                        Panel("后台使用提示") {
                            Text("小米 / 一加：允许自启动，电池设为无限制。荣耀 / 鸿蒙：应用启动管理允许自动启动、关联启动、后台活动。设置名称因系统版本不同而变化。")
                            Text("首次安装、重启或强行停止后请打开一次应用。验证码超过 10 分钟不再发送。")
                            OutlinedButton(onClick = {
                                app.startActivity(Intent(SystemSettings.ACTION_APPLICATION_DETAILS_SETTINGS,
                                    Uri.parse("package:${app.packageName}")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                            }) { Text("打开应用系统设置") }
                        }
                    }
                    1 -> {
                        if (!permissions) Button(onClick = {
                            permissionLauncher.launch(arrayOf(Manifest.permission.RECEIVE_SMS, Manifest.permission.READ_PHONE_STATE))
                        }) { Text("授予读取 SIM 状态权限") }
                        OutlinedButton(onClick = { permissionEpoch++; app.observeSims() }) { Text("刷新 SIM 列表") }
                        if (lines.isEmpty()) Note("尚未识别到活动 SIM。请检查电话状态权限、SIM 是否启用。")
                        lines.forEach { line ->
                            Panel("卡槽 ${line.slot + 1} · ${line.label.ifBlank { line.carrier.ifBlank { "SIM" } }}") {
                                Text("当前订阅 ${line.id} · ${if (line.id == c.boundId) "共享线路" else "不转发"}")
                                if (line.id != c.boundId) Button(onClick = { confirmSim = line }, enabled = c.connected) { Text("仅共享此 SIM") }
                                else Text("已绑定服务器号码 ${masked(c.recipient)}", color = blue)
                                if (c.boundId >= 0 && lines.size > 1) {
                                    Text(if (line.id in c.testedIds) "归属测试已通过" else "归属测试待完成")
                                    OutlinedButton(onClick = {
                                        scope.launch(Dispatchers.IO) {
                                            val code = "SIMTEST-" + UUID.randomUUID().toString().take(8).uppercase()
                                            app.settings.update { it.copy(enabled = false, armId = line.id,
                                                armCode = code, armUntil = System.currentTimeMillis() + 300000,
                                                testedIds = it.testedIds - line.id) }
                                            app.db.dao().cancelAll()
                                        }
                                    }) { Text("接收本卡测试短信") }
                                }
                            }
                        }
                        if (c.armId >= 0 && c.armCode.isNotEmpty()) Panel("正在验证卡槽 ${lines.firstOrNull { it.id == c.armId }?.slot?.plus(1) ?: "?"}") {
                            Text("用另一部手机，给这张卡的真实号码发送下面的完整标记。测试短信只用于本地验证，不会传服务器。5 分钟内有效。")
                            Text(c.armCode, style = MaterialTheme.typography.titleLarge, color = blue)
                            OutlinedButton(onClick = {
                                app.getSystemService(ClipboardManager::class.java)
                                    .setPrimaryClip(ClipData.newPlainText("SIM 测试标记", c.armCode))
                                feedback = "测试标记已复制"
                            }) { Text("复制测试标记") }
                        }
                        Note("单卡：确认唯一活动卡就是共享卡。双卡：共享卡和私人卡分别测试；无法识别归属的系统只可使用单卡模式。换卡、换槽或系统更新后需要重新绑定。")
                    }
                    2 -> {
                        Panel("关键词匹配") {
                            Text("多个词以逗号或换行分隔，命中任意一个即可。默认只转发包含「验证码」的短信。")
                            OutlinedTextField(keywords, { keywords = it }, label = { Text("关键词") },
                                modifier = Modifier.fillMaxWidth(), minLines = 3)
                            Button(enabled = RelayRules.keywords(keywords).isNotEmpty(), onClick = {
                                scope.launch(Dispatchers.IO) {
                                    app.settings.update { it.copy(keywords = keywords, enabled = false) }
                                    app.db.dao().cancelAll()
                                }
                                feedback = "规则已保存，请回首页重新开启"
                            }) { Text("保存规则") }
                        }
                        Panel("正文选择") {
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text("转发短信全文", Modifier.padding(top = 14.dp))
                                Switch(c.fullText, onCheckedChange = { full ->
                                    scope.launch(Dispatchers.IO) {
                                        app.settings.update { it.copy(fullText = full, enabled = false) }
                                        app.db.dao().cancelAll()
                                    }
                                })
                            }
                            Text("关闭后只发送“收到匹配规则的短信，正文已隐藏”。QQ 群内成员可以看到发送到群里的内容。")
                        }
                    }
                    3 -> {
                        Panel("导入配对信息") {
                            Text("把根目录的 server-credentials.local.smsrelay 传到手机，然后选择它。Token 会在手机内加密保存。")
                            Button(onClick = { importer.launch(arrayOf("*/*")) }, enabled = !busy) { Text("导入配对文件") }
                            Text(if (c.token.isEmpty()) "尚未保存凭据" else "凭据已加密保存", color = blue)
                        }
                        Panel("服务器设置") {
                            OutlinedTextField(endpoint, { endpoint = it }, label = { Text("HTTPS 地址") },
                                modifier = Modifier.fillMaxWidth(), singleLine = true)
                            OutlinedTextField(token, { token = it }, label = { Text("新 Token（留空则沿用）") },
                                visualTransformation = PasswordVisualTransformation(),
                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                                modifier = Modifier.fillMaxWidth(), singleLine = true)
                            OutlinedButton(onClick = { saveServer(endpoint, token.ifBlank { c.token }) }, enabled = !busy) { Text("保存设置") }
                            Button(enabled = !busy && c.token.isNotEmpty(), onClick = {
                                scope.launch {
                                    busy = true
                                    val before = app.settings.state.value
                                    try {
                                        val recipient = withContext(Dispatchers.IO) { app.api.check(before) }
                                        withContext(Dispatchers.IO) {
                                            app.settings.update { current ->
                                                if (current.endpoint == before.endpoint && current.token == before.token)
                                                    current.copy(connected = true, recipient = recipient, lastError = "") else current
                                            }
                                            app.event("CONNECTION_OK", "HTTPS 与授权校验成功；未发送群消息")
                                        }
                                        feedback = "连接成功，接收号码 ${masked(recipient)}"
                                    } catch (_: Exception) {
                                        withContext(Dispatchers.IO) {
                                            app.settings.update { it.copy(connected = false, enabled = false,
                                                lastError = "连接失败，请检查网络、证书或凭据") }
                                            app.db.dao().cancelAll()
                                        }
                                        feedback = "连接失败，请检查网络、服务器地址和 Token"
                                    }
                                    busy = false
                                }
                            }) { Text(if (busy) "正在检查…" else "测试连接（不发送短信）") }
                        }
                        Note("当前连接使用应用专用证书校验，不需要给手机安装根证书。禁止明文 HTTP，不会忽略证书错误。")
                        OutlinedButton(onClick = {
                            scope.launch(Dispatchers.IO) {
                                app.settings.update { it.copy(token = "", recipient = "", connected = false,
                                    enabled = false, boundId = -1, testedIds = emptySet(), armId = -1, armCode = "") }
                                app.db.dao().cancelAll()
                            }
                            feedback = "配对已清除"
                        }) { Text("清除配对和待上传正文") }
                    }
                    4 -> {
                        Panel("诊断概览") {
                            StatusRow("应用版本", "1.0.0")
                            StatusRow("设备", "${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL}")
                            StatusRow("系统", "Android ${android.os.Build.VERSION.RELEASE} · API ${android.os.Build.VERSION.SDK_INT}")
                            StatusRow("短信 / SIM 权限", if (permissions) "已授权" else "未授权")
                            StatusRow("活动 SIM", "${lines.size} 张")
                            StatusRow("待同步", "$queue 条")
                            OutlinedButton(onClick = {
                                val report = "共享短信 1.0.0\n${android.os.Build.MANUFACTURER} / API ${android.os.Build.VERSION.SDK_INT}\n" +
                                    "型号=${android.os.Build.MODEL}\n权限=$permissions SIM=${lines.size} 队列=$queue\n" +
                                    events.take(50).joinToString("\n") { "${time(it.at)} ${it.code} ${it.detail}" }
                                app.getSystemService(ClipboardManager::class.java)
                                    .setPrimaryClip(ClipData.newPlainText("共享短信诊断", report))
                                feedback = "已复制脱敏诊断报告"
                            }) { Text("复制诊断报告") }
                            OutlinedButton(onClick = { scope.launch(Dispatchers.IO) { app.db.dao().clearEvents() } }) { Text("清空日志") }
                        }
                        if (events.isEmpty()) Note("暂无诊断事件。这里不会保存短信正文、完整号码或 Token。")
                        events.take(50).forEach { event -> Panel("${time(event.at)} · ${event.code}") { Text(event.detail) } }
                    }
                }
                Spacer(Modifier.height(12.dp))
            }
        }
        confirmSim?.let { line ->
            AlertDialog(onDismissRequest = { confirmSim = null }, title = { Text("确认共享线路") },
                text = { Text("只允许卡槽 ${line.slot + 1}（${line.label}）的短信转发为服务器号码 ${masked(c.recipient)}。请确认这张卡的实际号码就是该号码。另一张卡不会共享。") },
                confirmButton = { TextButton(onClick = {
                    scope.launch(Dispatchers.IO) {
                        val currentLines = SimResolver.active(app)
                        if (currentLines.any { it.id == line.id }) {
                            app.settings.update { it.copy(boundId = line.id, simSignature = SimResolver.signature(currentLines),
                                testedIds = emptySet(), enabled = false, armId = -1, armCode = "", lastError = "") }
                            app.db.dao().cancelAll()
                        }
                    }
                    confirmSim = null
                }) { Text("确认，仅共享此卡") } },
                dismissButton = { TextButton(onClick = { confirmSim = null }) { Text("取消") } })
        }
    }
}

@Composable private fun Panel(title: String, content: @Composable ColumnScope.() -> Unit) {
    Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            content()
        }
    }
}
@Composable private fun StatusRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = Color(0xFF64748B), modifier = Modifier.weight(1f))
        Text(value, modifier = Modifier.weight(1.4f))
    }
}
@Composable private fun Note(value: String) {
    Text(value, modifier = Modifier.fillMaxWidth().background(Color(0xFFE9EFFF), MaterialTheme.shapes.medium).padding(14.dp),
        style = MaterialTheme.typography.bodyMedium, color = Color(0xFF334B73))
}
