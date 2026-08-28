package com.amlkit.mobile.data

import com.amlkit.mobile.BuildConfig
import kotlinx.serialization.json.Json
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import retrofit2.Retrofit

/** Attaches the stored bearer token to every outgoing request. A 401 means
 * the token is gone (expired, revoked, or the operator was deactivated) --
 * handled by the repository layer via [safeApiCall], not here, since
 * clearing the token store is a plain synchronous call either place would
 * make, but only the repository knows which UI flows care about the
 * result. */
private class AuthInterceptor(private val tokenStore: AuthTokenStore) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): okhttp3.Response {
        val request = chain.request()
        val token = tokenStore.currentToken()
        return if (token != null) {
            chain.proceed(request.newBuilder().addHeader("Authorization", "Bearer $token").build())
        } else {
            chain.proceed(request)
        }
    }
}

object ApiClient {

    private val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
    }

    fun create(tokenStore: AuthTokenStore): AmlkitApi {
        val logging = HttpLoggingInterceptor().apply {
            // Headers only, not bodies -- request/response bodies carry
            // regulated customer PII and session tokens that must never land
            // in logcat, even in a debug build.
            level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.HEADERS
                    else HttpLoggingInterceptor.Level.NONE
        }
        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(tokenStore))
            .addInterceptor(logging)
            .build()

        val contentType = "application/json".toMediaType()
        return Retrofit.Builder()
            .baseUrl(BuildConfig.API_BASE_URL)
            .client(client)
            .addConverterFactory(json.asConverterFactory(contentType))
            .build()
            .create(AmlkitApi::class.java)
    }
}
