package com.amlkit.mobile.data

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * Holds the bearer session token amlkit's /api/v1/auth/login issues.
 *
 * It is the exact same opaque token the server would otherwise put in a
 * cookie (see amlkit/api/mobile.py's module docstring) -- so it gets the
 * same treatment a session cookie deserves: encrypted at rest via the
 * platform Keystore (EncryptedSharedPreferences), never logged, and never
 * included in Android's backup/restore (see data_extraction_rules.xml).
 */
class AuthTokenStore(context: Context) {

    private val prefs: SharedPreferences = run {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            "amlkit_secure_prefs",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    private val _token = MutableStateFlow(prefs.getString(KEY_TOKEN, null))
    val token: StateFlow<String?> = _token

    private val _operatorName = MutableStateFlow(prefs.getString(KEY_OPERATOR_NAME, null))
    val operatorName: StateFlow<String?> = _operatorName

    private val _operatorRole = MutableStateFlow(prefs.getString(KEY_OPERATOR_ROLE, null))
    val operatorRole: StateFlow<String?> = _operatorRole

    fun currentToken(): String? = _token.value

    fun save(token: String, operatorName: String, operatorRole: String) {
        prefs.edit()
            .putString(KEY_TOKEN, token)
            .putString(KEY_OPERATOR_NAME, operatorName)
            .putString(KEY_OPERATOR_ROLE, operatorRole)
            .apply()
        _token.value = token
        _operatorName.value = operatorName
        _operatorRole.value = operatorRole
    }

    fun clear() {
        prefs.edit().clear().apply()
        _token.value = null
        _operatorName.value = null
        _operatorRole.value = null
    }

    private companion object {
        const val KEY_TOKEN = "session_token"
        const val KEY_OPERATOR_NAME = "operator_name"
        const val KEY_OPERATOR_ROLE = "operator_role"
    }
}
