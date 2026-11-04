package cn.smsrelay.app

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.Mac
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class Vault {
    private fun key(alias: String, hmac: Boolean = false): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(
            if (hmac) KeyProperties.KEY_ALGORITHM_HMAC_SHA256 else KeyProperties.KEY_ALGORITHM_AES,
            "AndroidKeyStore")
        val builder = KeyGenParameterSpec.Builder(alias,
            if (hmac) KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY
            else KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
        if (hmac) builder.setDigests(KeyProperties.DIGEST_SHA256)
        else builder.setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
        generator.init(builder.build())
        return generator.generateKey()
    }
    @Synchronized fun encrypt(value: String): ByteArray {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key("relay-aes-v1"))
        cipher.updateAAD("smsrelay-v1".toByteArray())
        return cipher.iv + cipher.doFinal(value.toByteArray(Charsets.UTF_8))
    }
    @Synchronized fun decrypt(value: ByteArray): String {
        require(value.size > 28)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key("relay-aes-v1"), GCMParameterSpec(128, value.copyOfRange(0, 12)))
        cipher.updateAAD("smsrelay-v1".toByteArray())
        return cipher.doFinal(value.copyOfRange(12, value.size)).toString(Charsets.UTF_8)
    }
    @Synchronized fun digest(value: String): String {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(key("relay-hmac-v1", true))
        return mac.doFinal(value.toByteArray()).joinToString("") { "%02x".format(it) }
    }
}
