package com.amlkit.mobile.ui.dashboard

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
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
import com.amlkit.mobile.data.dto.AlertDto
import com.amlkit.mobile.data.dto.DashboardResponse
import com.amlkit.mobile.ui.common.ErrorBanner
import com.amlkit.mobile.ui.common.FullScreenLoading
import com.amlkit.mobile.ui.common.PillTone
import com.amlkit.mobile.ui.common.Resource
import com.amlkit.mobile.ui.common.SectionCard
import com.amlkit.mobile.ui.common.StatusPill
import com.amlkit.mobile.ui.common.alertStatusTone
import com.amlkit.mobile.ui.common.amlkitViewModel
import com.amlkit.mobile.ui.common.categoryTone
import com.amlkit.mobile.ui.common.screenContentPadding
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

class DashboardViewModel(private val repository: AmlkitRepository) : ViewModel() {
    private val _state = MutableStateFlow<Resource<DashboardResponse>>(Resource.Loading)
    val state: StateFlow<Resource<DashboardResponse>> = _state

    fun load() {
        _state.value = Resource.Loading
        viewModelScope.launch {
            when (val result = repository.dashboard()) {
                is ApiResult.Success -> _state.value = Resource.Content(result.data)
                is ApiResult.Failure -> _state.value = Resource.Error(result.message)
            }
        }
    }
}

@Composable
fun DashboardScreen(
    repository: AmlkitRepository,
    onOpenAlert: (Int) -> Unit,
) {
    val viewModel = amlkitViewModel(repository) { DashboardViewModel(it) }
    val state by viewModel.state.collectAsState()
    LaunchedEffect(Unit) { viewModel.load() }

    when (val current = state) {
        is Resource.Loading -> FullScreenLoading(modifier = Modifier.fillMaxSize())
        is Resource.Error -> ErrorBanner(message = current.message, modifier = Modifier.fillMaxSize())
        is Resource.Content -> DashboardContent(current.data, onOpenAlert)
    }
}

@Composable
private fun DashboardContent(data: DashboardResponse, onOpenAlert: (Int) -> Unit) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = screenContentPadding,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            StatusPill(
                text = if (data.compliant) "24-hour list refresh: compliant" else "List refresh breach detected",
                tone = if (data.compliant) PillTone.SUCCESS else PillTone.DANGER,
            )
        }

        item {
            SectionCard(title = "Overview") {
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    StatTile("Customers", data.counts.customers)
                    StatTile("Screenings", data.counts.screenings)
                    StatTile("Alerts", data.counts.alerts_total)
                    StatTile("High risk", data.high_risk_customers)
                }
            }
        }

        if (data.breaches.isNotEmpty()) {
            item {
                SectionCard(title = "Lists past the 24-hour refresh window") {
                    data.breaches.forEach { d ->
                        Text("${d.title} — ${d.hours_since_refresh?.let { "${it}h" } ?: "never refreshed"}")
                    }
                }
            }
        }

        if (data.oldest_open.isNotEmpty()) {
            item { Text(text = "Oldest open alerts", style = MaterialTheme.typography.titleMedium) }
            items(data.oldest_open) { alert -> DashboardAlertRow(alert, onOpenAlert) }
        }

        if (data.due_for_review.isNotEmpty()) {
            item {
                SectionCard(title = "Due for periodic review") {
                    data.due_for_review.forEach { c ->
                        Text("${c.full_name} (${c.reference}) — next review ${c.next_review ?: "—"}")
                    }
                }
            }
        }

        if (data.open_transaction_alerts.isNotEmpty()) {
            item {
                SectionCard(title = "Open transaction-monitoring alerts") {
                    data.open_transaction_alerts.take(5).forEach { t ->
                        Text("${t.rule_key} — ${t.customer_name ?: t.reference ?: "customer #${t.customer_id}"} (${t.severity})")
                    }
                }
            }
        }
    }
}

@Composable
private fun StatTile(label: String, value: Int) {
    Column {
        Text(text = value.toString(), style = MaterialTheme.typography.headlineSmall)
        Text(text = label, style = MaterialTheme.typography.labelSmall)
    }
}

@Composable
private fun DashboardAlertRow(alert: AlertDto, onOpenAlert: (Int) -> Unit) {
    SectionCard(title = alert.matched_party ?: alert.caption) {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            StatusPill(text = alert.category, tone = categoryTone(alert.category))
            StatusPill(text = alert.status, tone = alertStatusTone(alert.status))
        }
        Text(text = "Matched: ${alert.caption} (score ${"%.2f".format(alert.score)})")
        TextButton(onClick = { onOpenAlert(alert.id) }) {
            Text("Open in Alerts")
        }
    }
}
