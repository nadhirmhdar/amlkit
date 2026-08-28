package com.amlkit.mobile.ui.reports

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.amlkit.mobile.data.AmlkitRepository
import com.amlkit.mobile.data.ApiResult
import com.amlkit.mobile.data.dto.ReportListItemDto
import com.amlkit.mobile.ui.common.ErrorBanner
import com.amlkit.mobile.ui.common.FullScreenLoading
import com.amlkit.mobile.ui.common.PillTone
import com.amlkit.mobile.ui.common.Resource
import com.amlkit.mobile.ui.common.SectionCard
import com.amlkit.mobile.ui.common.StatusPill
import com.amlkit.mobile.ui.common.amlkitViewModel
import com.amlkit.mobile.ui.common.screenContentPadding
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

class ReportsListViewModel(private val repository: AmlkitRepository) : ViewModel() {
    private val _state = MutableStateFlow<Resource<List<ReportListItemDto>>>(Resource.Loading)
    val state: StateFlow<Resource<List<ReportListItemDto>>> = _state

    fun load() {
        _state.value = Resource.Loading
        viewModelScope.launch {
            when (val result = repository.reports()) {
                is ApiResult.Success -> _state.value = Resource.Content(result.data.reports)
                is ApiResult.Failure -> _state.value = Resource.Error(result.message)
            }
        }
    }
}

@Composable
fun ReportsListScreen(
    repository: AmlkitRepository,
    onOpenReport: (Int) -> Unit,
    onNewReport: () -> Unit,
) {
    val viewModel = amlkitViewModel(repository) { ReportsListViewModel(it) }
    val state by viewModel.state.collectAsState()
    LaunchedEffect(Unit) { viewModel.load() }

    Scaffold(
        floatingActionButton = {
            FloatingActionButton(onClick = onNewReport) { Icon(Icons.Filled.Add, contentDescription = "New report") }
        },
    ) { padding ->
        Box(modifier = Modifier.fillMaxSize().padding(padding)) {
            when (val current = state) {
                is Resource.Loading -> FullScreenLoading(modifier = Modifier.fillMaxSize())
                is Resource.Error -> ErrorBanner(message = current.message)
                is Resource.Content -> {
                    if (current.data.isEmpty()) {
                        Text(text = "No STR/SAR reports yet.", modifier = Modifier.padding(24.dp))
                    } else {
                        LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = screenContentPadding,
                            verticalArrangement = Arrangement.spacedBy(10.dp),
                        ) {
                            items(current.data, key = { it.id }) { report ->
                                SectionCard(title = "${report.report_type} — ${report.customer_name ?: "—"}") {
                                    StatusPill(
                                        text = report.status,
                                        tone = if (report.status == "submitted") PillTone.SUCCESS else PillTone.WARNING,
                                    )
                                    Text(text = report.reference ?: "")
                                    TextButton(onClick = { onOpenReport(report.id) }) { Text("Open") }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
