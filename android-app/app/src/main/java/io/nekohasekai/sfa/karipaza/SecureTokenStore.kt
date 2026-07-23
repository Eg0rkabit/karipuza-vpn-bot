package io.nekohasekai.sfa.karipaza

import android.content.Context
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class SecureTokenStore(context: Context) {
    private val preferences =
        context.getSharedPreferences("karipaza_secure_session", Context.MODE_PRIVATE)

    fun readToken(): String? {
        val encoded = preferences.getString(KEY_TOKEN, null) ?: return null
        return runCatching {
            val parts = encoded.split(":", limit = 2)
            require(parts.size == 2)
            val cipher =
                Cipher.getInstance(TRANSFORMATION).apply {
                    init(
                        Cipher.DECRYPT_MODE,
                        getOrCreateKey(),
                        GCMParameterSpec(128, Base64.decode(parts[0], Base64.NO_WRAP)),
                    )
                }
            String(
                cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP)),
                Charsets.UTF_8,
            )
        }.getOrElse {
            clear()
            null
        }
    }

    fun writeToken(token: String) {
        val cipher =
            Cipher.getInstance(TRANSFORMATION).apply {
                init(Cipher.ENCRYPT_MODE, getOrCreateKey())
            }
        val encrypted = cipher.doFinal(token.toByteArray(Charsets.UTF_8))
        val encoded =
            "${Base64.encodeToString(cipher.iv, Base64.NO_WRAP)}:" +
                Base64.encodeToString(encrypted, Base64.NO_WRAP)
        preferences.edit().putString(KEY_TOKEN, encoded).apply()
    }

    fun clear() {
        preferences.edit().remove(KEY_TOKEN).apply()
    }

    fun deviceId(): String {
        preferences.getString(KEY_DEVICE_ID, null)?.let { return it }
        val bytes = ByteArray(18).also(SecureRandom()::nextBytes)
        val id =
            Base64.encodeToString(
                bytes,
                Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING,
            )
        preferences.edit().putString(KEY_DEVICE_ID, id).apply()
        return id
    }

    private fun getOrCreateKey(): SecretKey {
        require(Build.VERSION.SDK_INT >= Build.VERSION_CODES.M)
        val keyStore =
            KeyStore.getInstance("AndroidKeyStore").apply {
                load(null)
            }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        return KeyGenerator
            .getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
            .apply {
                init(
                    KeyGenParameterSpec
                        .Builder(
                            KEY_ALIAS,
                            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
                        ).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                        .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                        .build(),
                )
            }.generateKey()
    }

    private companion object {
        const val KEY_ALIAS = "karipaza_froxy_session_v1"
        const val KEY_TOKEN = "token"
        const val KEY_DEVICE_ID = "device_id"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
    }
}
