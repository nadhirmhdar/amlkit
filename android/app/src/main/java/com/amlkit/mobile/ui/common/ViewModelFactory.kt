package com.amlkit.mobile.ui.common

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.compose.runtime.Composable
import com.amlkit.mobile.data.AmlkitRepository

/** One-liner ViewModel construction from Compose, avoiding a DI framework
 * (see AmlkitApplication's docstring for why): `amlkitViewModel(repo) { MyViewModel(it) }`. */
@Composable
inline fun <reified VM : ViewModel> amlkitViewModel(
    repository: AmlkitRepository,
    crossinline create: (AmlkitRepository) -> VM,
): VM {
    val factory = viewModelFactory {
        initializer { create(repository) }
    }
    return viewModel(factory = factory)
}
