package com.amlkit.mobile.ui.alerts

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.amlkit.mobile.data.AmlkitRepository
import com.amlkit.mobile.data.ApiResult
import com.amlkit.mobile.data.dto.AlertDto
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

data class AlertsUiState(
    val status: String = "open",
    val alerts: Resource<List<AlertDto>> = Resource.Loading,
    val reasonCodes: Map<String, String> = emptyMap(),
    val actionError: String? = null,
    val actionMessage: String? = null,
)

class AlertsViewModel(private val repository: AmlkitRepository) : ViewModel() {
    private val _state = MutableStateFlow(AlertsUiState())
    val state: StateFlow<AlertsUiState> = _state

    init {
        viewModelScope.launch {
            when (val result = repository.reasonCodes()) {
                is ApiResult.Success -> _state.value = _state.value.copy(reasonCodes = result.data.reason_codes)
                is ApiResult.Failure -> Unit
            }
        }
    }

    fun setStatus(status: String) {
        _state.value = _state.value.copy(status = status)
        load()
    }

    fun load() {
        _state.value = _state.value.copy(alerts = Resource.Loading)
        viewModelScope.launch {
            when (val result = repository.alerts(_state.value.status)) {
                is ApiResult.Success -> _state.value = _state.value.copy(alerts = Resource.Content(result.data.alerts))
                is ApiResult.Failure -> _state.value = _state.value.copy(alerts = Resource.Error(result.message))
            }
        }
    }

    fun disposition(alertId: Int, status: String, reasonCode: String, narrative: String) {
        viewModelScope.launch {
            when (val result = repository.dispositionAlert(alertId, status, reasonCode, narrative)) {
                is ApiResult.Success -> {
                    _state.value = _state.value.copy(actionMessage = result.data.message, actionError = null)
                    load()
                }
                is ApiResult.Failure -> _state.value = _state.value.copy(actionError = result.message)
            }
        }
    }

    fun confirm(alertId: Int, agree: Boolean, narrative: String) {
        viewModelScope.launch {
            when (val result = repository.confirmAlert(alertId, agree, narrative)) {
                is ApiResult.Success -> {
                    _state.value = _state.value.copy(actionMessage = result.data.message, actionError = null)
                    load()
                }
                is ApiResult.Failure -> _state.value = _state.value.copy(actionError = result.message)
            }
        }
    }

    fun assign(alertId: Int, operator: String?) {
        viewModelScope.launch {
            when (val result = repository.assignAlert(alertId, operator)) {
                is ApiResult.Success -> load()
                is ApiResult.Failure -> _state.value = _state.value.copy(actionError = result.message)
            }
        }
    }

    fun dismissBanner() { _state.value = _state.value.copy(actionMessage = null, actionError = null) }
}

@Composable
fun AlertsScreen(repository: AmlkitRepository) {
    val viewModel = amlkitViewModel(repository) { AlertsViewModel(it) }
    val state by viewModel.state.collectAsState()
    LaunchedEffect(Unit) { viewModel.load() }

    var dispositionTarget by remember { mutableStateOf<AlertDto?>(null) }
    var confirmTarget by remember { mutableStateOf<AlertDto?>(null) }
    var assignTarget by remember { mutableStateOf<AlertDto?>(null) }

    Column(modifier = Modifier.fillMaxSize()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(screenContentPadding),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            listOf("open" to "Open", "pending_review" to "Pending review", "all" to "All").forEach { (value, label) ->
                FilterChip(selected = state.status == value, onClick = { viewModel.setStatus(value) }, label = { Text(label) })
            }
        }

        if (state.actionMessage != null) {
            SectionCard(title = "Done") { Text(state.actionMessage!!) }
        }
        if (state.actionError != null) {
            ErrorBanner(message = state.actionError!!)
        }

        when (val resource = state.alerts) {
            is Resource.Loading -> FullScreenLoading(modifier = Modifier.fillMaxSize())
            is Resource.Error -> ErrorBanner(message = resource.message, modifier = Modifier.fillMaxSize())
            is Resource.Content -> {
                if (resource.data.isEmpty()) {
                    Text(text = "No alerts in this view.", modifier = Modifier.fillMaxSize())
                } else {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = screenContentPadding,
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        items(resource.data, key = { it.id }) { alert ->
                            AlertRow(
                                alert = alert,
                                onDisposition = { dispositionTarget = alert },
                                onConfirm = { confirmTarget = alert },
                                onAssign = { assignTarget = alert },
                            )
                        }
                    }
                }
            }
        }
    }

    dispositionTarget?.let { alert ->
        DispositionDialog(
            reasonCodes = state.reasonCodes,
            onDismiss = { dispositionTarget = null },
            onConfirm = { status, code, narrative ->
                viewModel.disposition(alert.id, status, code, narrative)
                dispositionTarget = null
            },
        )
    }
    confirmTarget?.let { alert ->
        ConfirmReviewDialog(
            onDismiss = { confirmTarget = null },
            onConfirm = { agree, narrative ->
                viewModel.confirm(alert.id, agree, narrative)
                confirmTarget = null
            },
        )
    }
    assignTarget?.let { alert ->
        AssignDialog(
            initial = alert.assigned_to ?: "",
            onDismiss = { assignTarget = null },
            onConfirm = { operator ->
                viewModel.assign(alert.id, operator.ifBlank { null })
                assignTarget = null
            },
        )
    }
}

@Composable
private fun AlertRow(
    alert: AlertDto,
    onDisposition: () -> Unit,
    onConfirm: () -> Unit,
    onAssign: () -> Unit,
) {
    SectionCard(title = alert.matched_party ?: alert.caption) {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            StatusPill(text = alert.category, tone = categoryTone(alert.category))
            StatusPill(text = alert.status, tone = alertStatusTone(alert.status))
        }
        Text(text = "Matched: ${alert.caption} · score ${"%.2f".format(alert.score)} · ${alert.dataset_title ?: alert.dataset}")
        if (alert.customer_name != null) Text(text = "Customer: ${alert.customer_name} (${alert.reference})")
        Text(text = "Assigned: ${alert.assigned_to ?: "unassigned"}", style = MaterialTheme.typography.labelSmall)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (alert.status == "pending_review") {
                TextButton(onClick = onConfirm) { Text("Confirm review") }
            } else if (alert.status == "open") {
                TextButton(onClick = onDisposition) { Text("Disposition") }
            }
            TextButton(onClick = onAssign) { Text("Assign") }
        }
    }
}

@Composable
private fun DispositionDialog(
    reasonCodes: Map<String, String>,
    onDismiss: () -> Unit,
    onConfirm: (status: String, reasonCode: String, narrative: String) -> Unit,
) {
    var status by remember { mutableStateOf("false_positive") }
    var reasonCode by remember { mutableStateOf(reasonCodes.keys.firstOrNull() ?: "") }
    var reasonMenuOpen by remember { mutableStateOf(false) }
    var narrative by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Disposition alert") },
        text = {
            Column {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    listOf("false_positive", "true_positive", "escalated").forEach { option ->
                        FilterChip(selected = status == option, onClick = { status = option }, label = { Text(option) })
                    }
                }
                Text(text = "Reason: ${reasonCodes[reasonCode] ?: reasonCode}", modifier = Modifier.fillMaxWidth())
                TextButton(onClick = { reasonMenuOpen = true }) { Text("Choose reason") }
                DropdownMenu(expanded = reasonMenuOpen, onDismissRequest = { reasonMenuOpen = false }) {
                    reasonCodes.forEach { (code, label) ->
                        DropdownMenuItem(text = { Text(label) }, onClick = { reasonCode = code; reasonMenuOpen = false })
                    }
                }
                OutlinedTextField(
                    value = narrative, onValueChange = { narrative = it },
                    label = { Text("Narrative (required for true positive / escalated)") },
                )
            }
        },
        confirmButton = { TextButton(onClick = { onConfirm(status, reasonCode, narrative) }) { Text("Submit") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun ConfirmReviewDialog(onDismiss: () -> Unit, onConfirm: (agree: Boolean, narrative: String) -> Unit) {
    var narrative by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Independent review") },
        text = {
            Column {
                Text("Confirming requires a different operator than the one who proposed the disposition.")
                OutlinedTextField(value = narrative, onValueChange = { narrative = it }, label = { Text("Narrative (optional)") })
            }
        },
        confirmButton = { TextButton(onClick = { onConfirm(true, narrative) }) { Text("Agree & confirm") } },
        dismissButton = { TextButton(onClick = { onConfirm(false, narrative) }) { Text("Override & escalate") } },
    )
}

@Composable
private fun AssignDialog(initial: String, onDismiss: () -> Unit, onConfirm: (String) -> Unit) {
    var operator by remember { mutableStateOf(initial) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Assign alert") },
        text = { OutlinedTextField(value = operator, onValueChange = { operator = it }, label = { Text("Operator name (blank to clear)") }) },
        confirmButton = { TextButton(onClick = { onConfirm(operator) }) { Text("Save") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
