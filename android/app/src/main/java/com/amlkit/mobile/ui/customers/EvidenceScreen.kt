package com.amlkit.mobile.ui.customers

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
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
import com.amlkit.mobile.data.dto.CustomerDetailResponse
import com.amlkit.mobile.ui.common.ErrorBanner
import com.amlkit.mobile.ui.common.FullScreenLoading
import com.amlkit.mobile.ui.common.Resource
import com.amlkit.mobile.ui.common.SectionCard
import com.amlkit.mobile.ui.common.amlkitViewModel
import com.amlkit.mobile.ui.common.screenContentPadding
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/** Evidence pack: the same case-file data the web app's printable evidence
 * page renders, shown as a scrollable read-only summary. There is no PDF
 * export here yet -- see the "Not built yet" list in the repo README --
 * this is the on-device review, not the inspector-ready artifact. */
class EvidenceViewModel(private val repository: AmlkitRepository) : ViewModel() {
    private val _state = MutableStateFlow<Resource<CustomerDetailResponse>>(Resource.Loading)
    val state: StateFlow<Resource<CustomerDetailResponse>> = _state

    fun load(customerId: Int) {
        _state.value = Resource.Loading
        viewModelScope.launch {
            when (val result = repository.customerEvidence(customerId)) {
                is ApiResult.Success -> _state.value = Resource.Content(result.data)
                is ApiResult.Failure -> _state.value = Resource.Error(result.message)
            }
        }
    }
}

@Composable
fun EvidenceScreen(repository: AmlkitRepository, customerId: Int) {
    val viewModel = amlkitViewModel(repository) { EvidenceViewModel(it) }
    val state by viewModel.state.collectAsState()
    LaunchedEffect(customerId) { viewModel.load(customerId) }

    when (val current = state) {
        is Resource.Loading -> FullScreenLoading(modifier = Modifier.fillMaxSize())
        is Resource.Error -> ErrorBanner(message = current.message, modifier = Modifier.fillMaxSize())
        is Resource.Content -> {
            val data = current.data
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = screenContentPadding,
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                item {
                    Text(text = "Evidence pack — ${data.customer.full_name}", style = MaterialTheme.typography.headlineSmall)
                    Text(text = "Generated ${data.generated_at ?: ""}", style = MaterialTheme.typography.labelSmall)
                }
                item {
                    SectionCard(title = "Customer") {
                        Text("Reference: ${data.customer.reference}")
                        Text("Type: ${data.customer.customer_type}")
                        Text("Onboarded: ${data.customer.onboarded_at}")
                        Text("Status: ${data.customer.status}")
                    }
                }
                item {
                    SectionCard(title = "Risk") {
                        Text("Rating: ${data.risk?.rating ?: "—"}   Score: ${data.risk?.score ?: "—"}")
                    }
                }
                if (data.screenings.isNotEmpty()) {
                    item { Text(text = "Screening history", style = MaterialTheme.typography.titleMedium) }
                    items(data.screenings) { s ->
                        Text("${s.run_at} — ${s.trigger} — ${s.hits} hit(s) of ${s.candidates} candidates")
                    }
                }
                if (data.alerts.isNotEmpty()) {
                    item { Text(text = "Alerts & dispositions", style = MaterialTheme.typography.titleMedium) }
                    items(data.alerts) { a ->
                        SectionCard(title = a.caption) {
                            Text("Status: ${a.status}   Reason: ${a.reason_code ?: "—"}")
                            Text("Independent review: ${a.independent_review ?: "n/a"}")
                        }
                    }
                }
                if (data.audit.isNotEmpty()) {
                    item { Text(text = "Audit trail", style = MaterialTheme.typography.titleMedium) }
                    items(data.audit.take(50)) { entry ->
                        Text("${entry.created_at} — ${entry.actor} — ${entry.action}", style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }
    }
}
