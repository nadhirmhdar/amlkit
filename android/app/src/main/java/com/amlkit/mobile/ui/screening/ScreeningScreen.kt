package com.amlkit.mobile.ui.screening

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.amlkit.mobile.data.AmlkitRepository
import com.amlkit.mobile.data.ApiResult
import com.amlkit.mobile.data.dto.ScreenHitDto
import com.amlkit.mobile.data.dto.ScreenResponse
import com.amlkit.mobile.ui.common.ErrorBanner
import com.amlkit.mobile.ui.common.PillTone
import com.amlkit.mobile.ui.common.SectionCard
import com.amlkit.mobile.ui.common.StatusPill
import com.amlkit.mobile.ui.common.amlkitViewModel
import com.amlkit.mobile.ui.common.categoryTone
import com.amlkit.mobile.ui.common.screenContentPadding
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class ScreeningUiState(
    val query: String = "",
    val loading: Boolean = false,
    val result: ScreenResponse? = null,
    val error: String? = null,
)

class ScreeningViewModel(private val repository: AmlkitRepository) : ViewModel() {
    private val _state = MutableStateFlow(ScreeningUiState())
    val state: StateFlow<ScreeningUiState> = _state

    fun onQueryChange(value: String) { _state.value = _state.value.copy(query = value) }

    fun runScreen() {
        val name = _state.value.query.trim()
        if (name.isEmpty()) {
            _state.value = _state.value.copy(error = "Enter a name to screen.")
            return
        }
        _state.value = _state.value.copy(loading = true, error = null)
        viewModelScope.launch {
            when (val result = repository.screen(name)) {
                is ApiResult.Success -> _state.value = _state.value.copy(loading = false, result = result.data)
                is ApiResult.Failure -> _state.value = _state.value.copy(loading = false, error = result.message)
            }
        }
    }
}

@Composable
fun ScreeningScreen(repository: AmlkitRepository) {
    val viewModel = amlkitViewModel(repository) { ScreeningViewModel(it) }
    val state by viewModel.state.collectAsState()

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = screenContentPadding,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Text(text = "Ad-hoc screening", style = MaterialTheme.typography.headlineSmall)
        }
        item {
            OutlinedTextField(
                value = state.query,
                onValueChange = viewModel::onQueryChange,
                label = { Text("Full name") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
        }
        item {
            Button(onClick = viewModel::runScreen, enabled = !state.loading, modifier = Modifier.fillMaxWidth()) {
                if (state.loading) CircularProgressIndicator(modifier = Modifier.size(20.dp))
                else Text("Screen")
            }
        }
        if (state.error != null) {
            item { ErrorBanner(message = state.error!!) }
        }
        state.result?.let { result ->
            item {
                if (result.low_confidence) {
                    ErrorBanner(message = "Single-word name: matching confidence is lower. Add a family name if possible.")
                }
                StatusPill(
                    text = if (result.clear) "CLEAR — no hits" else "${result.hits.size} hit(s)",
                    tone = if (result.clear) PillTone.SUCCESS else PillTone.DANGER,
                )
            }
            items(result.hits) { hit -> ScreeningHitCard(hit) }
        }
    }
}

@Composable
private fun ScreeningHitCard(hit: ScreenHitDto) {
    SectionCard(title = hit.caption) {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            StatusPill(text = hit.category, tone = categoryTone(hit.category))
            Text(text = "score ${"%.3f".format(hit.score)}", style = MaterialTheme.typography.bodySmall)
        }
        Text(text = "Dataset: ${hit.dataset}")
        Text(text = "Matched name: ${hit.matched_name}")
        hit.obligation?.let { Text(text = it, style = MaterialTheme.typography.bodySmall) }
        if (hit.aliases.isNotEmpty()) {
            Text(text = "Aliases: " + hit.aliases.joinToString(", ") { it.name })
        }
    }
}
