package com.amlkit.mobile.ui.common

/** Screen-level load state -- distinct from [com.amlkit.mobile.data.ApiResult],
 * which is a one-shot call outcome. Most screens fetch once on entry and
 * need to render "loading" / "here's the data" / "here's why it failed",
 * so every list/detail ViewModel in this app converges on this shape. */
sealed interface Resource<out T> {
    data object Loading : Resource<Nothing>
    data class Content<T>(val data: T) : Resource<T>
    data class Error(val message: String) : Resource<Nothing>
}
