package com.amlkit.mobile.data

/** Outcome of one API call, collapsed to the three shapes the UI actually
 * needs to branch on -- see `safeApiCall` for how a Retrofit `Response<T>`
 * (or a thrown [java.io.IOException]) becomes one of these. */
sealed interface ApiResult<out T> {
    data class Success<T>(val data: T) : ApiResult<T>
    data class Failure(val code: Int?, val message: String) : ApiResult<Nothing>
}

inline fun <T> ApiResult<T>.onSuccess(action: (T) -> Unit): ApiResult<T> {
    if (this is ApiResult.Success) action(data)
    return this
}

inline fun <T> ApiResult<T>.onFailure(action: (ApiResult.Failure) -> Unit): ApiResult<T> {
    if (this is ApiResult.Failure) action(this)
    return this
}
