package cn.smsrelay.app

import android.content.Context
import androidx.room.*
import kotlinx.coroutines.flow.Flow

@Entity(tableName = "messages", indices = [Index(value = ["digest"], unique = true)])
data class QueuedMessage(
    @PrimaryKey val id: String,
    val digest: String,
    val payload: ByteArray,
    val configKey: String,
    val created: Long,
    val expires: Long,
    val status: String = "PENDING",
    val attempts: Int = 0,
    val nextRetry: Long = 0
)
@Entity(tableName = "events")
data class RelayEvent(@PrimaryKey(autoGenerate = true) val id: Long = 0,
                      val at: Long = System.currentTimeMillis(), val code: String, val detail: String)

@Dao interface RelayDao {
    @Insert(onConflict = OnConflictStrategy.IGNORE) suspend fun insert(row: QueuedMessage): Long
    @Update suspend fun update(row: QueuedMessage)
    @Query("UPDATE messages SET status='RETRY_WAIT', attempts=:attempts, nextRetry=:next WHERE id=:id AND length(payload)>0 AND status IN ('PENDING','RETRY_WAIT')")
    suspend fun retry(id: String, attempts: Int, next: Long)
    @Query("SELECT * FROM messages WHERE status IN ('PENDING','RETRY_WAIT') ORDER BY created LIMIT 100")
    suspend fun pending(): List<QueuedMessage>
    @Query("SELECT * FROM messages WHERE status='ACKED' ORDER BY created LIMIT 100")
    suspend fun acknowledged(): List<QueuedMessage>
    @Query("SELECT COUNT(*) FROM messages WHERE status IN ('PENDING','RETRY_WAIT')")
    fun count(): Flow<Int>
    @Query("UPDATE messages SET payload=X'', status='EXPIRED' WHERE expires<=:now AND length(payload)>0")
    suspend fun expire(now: Long)
    @Query("DELETE FROM messages WHERE created<:before") suspend fun prune(before: Long)
    @Query("UPDATE messages SET payload=X'', status='CANCELLED' WHERE length(payload)>0")
    suspend fun cancelAll()
    @Insert suspend fun event(row: RelayEvent)
    @Query("SELECT * FROM events ORDER BY id DESC LIMIT 100") fun events(): Flow<List<RelayEvent>>
    @Query("DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 200)")
    suspend fun pruneEvents()
    @Query("DELETE FROM events") suspend fun clearEvents()
}
@Database(entities = [QueuedMessage::class, RelayEvent::class], version = 1, exportSchema = false)
abstract class RelayDatabase : RoomDatabase() {
    abstract fun dao(): RelayDao
    companion object {
        fun create(context: Context) = Room.databaseBuilder(context, RelayDatabase::class.java, "relay.db").build()
    }
}
