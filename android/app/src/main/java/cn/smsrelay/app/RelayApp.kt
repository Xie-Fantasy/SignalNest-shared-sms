package cn.smsrelay.app

import android.app.Application
import android.content.Context
import android.telephony.SubscriptionManager
import android.os.Build
import androidx.core.content.ContextCompat
import androidx.work.*
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Mutex
import java.util.concurrent.TimeUnit

class RelayApp : Application() {
    lateinit var vault: Vault
    lateinit var settings: Settings
    lateinit var db: RelayDatabase
    val api = RelayApi()
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    val intakeLock = Mutex()
    val uploadLock = Mutex()
    private var subscriptionListener: SubscriptionManager.OnSubscriptionsChangedListener? = null
    override fun onCreate() {
        super.onCreate()
        vault = Vault()
        settings = Settings(this, vault)
        db = RelayDatabase.create(this)
        scope.launch {
            db.dao().expire(System.currentTimeMillis())
            db.dao().prune(System.currentTimeMillis() - 86400000)
        }
        schedulePeriodic(this)
        observeSims()
    }
    fun observeSims() {
        if (!SimResolver.permissions(this) || subscriptionListener != null) return
        val listener = object : SubscriptionManager.OnSubscriptionsChangedListener() {
            override fun onSubscriptionsChanged() { scope.launch { checkBinding() } }
        }
        try {
            val manager = getSystemService(SubscriptionManager::class.java)
            if (Build.VERSION.SDK_INT >= 30) manager.addOnSubscriptionsChangedListener(ContextCompat.getMainExecutor(this), listener)
            else {
                @Suppress("DEPRECATION")
                manager.addOnSubscriptionsChangedListener(listener)
            }
            subscriptionListener = listener
        } catch (_: Exception) { /* Each intake and worker independently checks the binding. */ }
    }
    suspend fun checkBinding(): Boolean {
        val c = settings.state.value
        if (c.boundId < 0) return false
        val valid = SimResolver.permissions(this) && SimResolver.bindingValid(c, SimResolver.active(this))
        if (!valid) {
            settings.update { it.copy(enabled = false, boundId = -1, testedIds = emptySet(),
                armId = -1, armCode = "", lastError = "SIM 或系统状态变化，请重新绑定") }
            db.dao().cancelAll()
            event("BINDING_CHANGED", "已暂停转发并清除待上传正文")
        }
        return valid
    }
    suspend fun event(code: String, detail: String) {
        db.dao().event(RelayEvent(code = code, detail = detail))
        db.dao().pruneEvents()
    }
    companion object {
        fun from(context: Context) = context.applicationContext as RelayApp
        private fun constraints() = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
        fun enqueue(context: Context) {
            val builder = OneTimeWorkRequestBuilder<UploadWorker>().setConstraints(constraints())
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 15, TimeUnit.SECONDS)
            if (Build.VERSION.SDK_INT >= 31) builder.setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
            val request = builder.build()
            WorkManager.getInstance(context).enqueueUniqueWork("relay-upload", ExistingWorkPolicy.APPEND_OR_REPLACE, request)
        }
        fun schedulePeriodic(context: Context) {
            val work = PeriodicWorkRequestBuilder<UploadWorker>(15, TimeUnit.MINUTES)
                .setConstraints(constraints()).build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork("relay-recovery", ExistingPeriodicWorkPolicy.KEEP, work)
        }
    }
}
