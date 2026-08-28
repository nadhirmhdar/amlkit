package com.amlkit.mobile.ui.reports

import android.content.Context
import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.amlkit.mobile.data.AmlkitRepository
import com.amlkit.mobile.data.ApiResult
import com.amlkit.mobile.data.dto.ReportDetailResponse
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

class ReportDetailViewModel(private val repository: AmlkitRepository) : ViewModel() {
    private val _state = MutableStateFlow<Resource<ReportDetailResponse>>(Resource.Loading)
    val state: StateFlow<Resource<ReportDetailResponse>> = _state

    private var reportId: Int = -1

    fun load(id: Int) {
        reportId = id
        _state.value = Resource.Loading
        viewModelScope.launch {
            when (val result = repository.reportDetail(id)) {
                is ApiResult.Success -> _state.value = Resource.Content(result.data)
                is ApiResult.Failure -> _state.value = Resource.Error(result.message)
            }
        }
    }

    fun submit() {
        viewModelScope.launch {
            when (repository.submitReport(reportId)) {
                is ApiResult.Success -> load(reportId)
                is ApiResult.Failure -> Unit
            }
        }
    }
}

@Composable
fun ReportDetailScreen(repository: AmlkitRepository, reportId: Int) {
    val viewModel = amlkitViewModel(repository) { ReportDetailViewModel(it) }
    val state by viewModel.state.collectAsState()
    val context = LocalContext.current
    val coroutineScope = rememberCoroutineScope()
    LaunchedEffect(reportId) { viewModel.load(reportId) }

    when (val current = state) {
        is Resource.Loading -> FullScreenLoading(modifier = Modifier.fillMaxSize())
        is Resource.Error -> ErrorBanner(message = current.message, modifier = Modifier.fillMaxSize())
        is Resource.Content -> {
            val report = current.data
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = screenContentPadding,
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                item {
                    Text(text = "${report.report_type} — ${report.reference ?: ""}", style = MaterialTheme.typography.headlineSmall)
                    StatusPill(
                        text = report.status,
                        tone = if (report.status == "submitted") PillTone.SUCCESS else PillTone.WARNING,
                    )
                }
                item {
                    SectionCard(title = "Subject") {
                        Text("${report.payload.first_name ?: ""} ${report.payload.last_name ?: ""}")
                        Text("Nationality: ${report.payload.nationality ?: "—"}")
                        Text("ID: ${report.payload.id_type ?: "—"} ${report.payload.id_number ?: ""}")
                    }
                }
                item {
                    SectionCard(title = "Filing") {
                        Text("Reporting entity: ${report.payload.reporting_entity_name ?: "—"}")
                        Text("Entity reference: ${report.payload.entity_reference ?: "—"}")
                        Text("Reporter: ${report.payload.reporter_name ?: "—"} (${report.payload.reporter_email ?: "—"})")
                    }
                }
                item {
                    SectionCard(title = "Narrative") {
                        Text(report.payload.reason_description ?: "—")
                        Text("Action taken: ${report.payload.action_taken ?: "—"}")
                    }
                }
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        if (report.status != "submitted") {
                            TextButton(onClick = viewModel::submit) { Text("Submit to UAE FIU") }
                        }
                        TextButton(onClick = {
                            coroutineScope.launch {
                                when (val result = repository.exportReportXml(reportId)) {
                                    is ApiResult.Success -> shareXml(context, result.data)
                                    is ApiResult.Failure -> Unit
                                }
                            }
                        }) { Text("Export goAML XML") }
                    }
                }
            }
        }
    }
}

private fun shareXml(context: Context, xml: String) {
    val intent = Intent(Intent.ACTION_SEND).apply {
        type = "application/xml"
        putExtra(Intent.EXTRA_TEXT, xml)
    }
    context.startActivity(Intent.createChooser(intent, "Share goAML XML"))
}
