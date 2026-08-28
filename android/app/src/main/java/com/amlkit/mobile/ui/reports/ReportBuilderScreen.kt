package com.amlkit.mobile.ui.reports

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
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
import com.amlkit.mobile.data.dto.CustomerListItemDto
import com.amlkit.mobile.data.dto.ReportSaveRequest
import com.amlkit.mobile.ui.common.ErrorBanner
import com.amlkit.mobile.ui.common.amlkitViewModel
import com.amlkit.mobile.ui.common.screenContentPadding
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class ReportBuilderUiState(
    val customers: List<CustomerListItemDto> = emptyList(),
    val customerId: Int? = null,
    val reportType: String = "STR",
    val reportingEntityName: String = "",
    val entityReference: String = "",
    val reporterName: String = "",
    val reporterEmail: String = "",
    val firstName: String = "",
    val lastName: String = "",
    val reasonDescription: String = "",
    val actionTaken: String = "",
    val loading: Boolean = false,
    val error: String? = null,
)

class ReportBuilderViewModel(private val repository: AmlkitRepository) : ViewModel() {
    private val _state = MutableStateFlow(ReportBuilderUiState())
    val state: StateFlow<ReportBuilderUiState> = _state

    fun loadCustomers() {
        viewModelScope.launch {
            when (val result = repository.customers()) {
                is ApiResult.Success -> _state.value = _state.value.copy(customers = result.data.customers)
                is ApiResult.Failure -> _state.value = _state.value.copy(error = result.message)
            }
        }
    }

    fun update(transform: (ReportBuilderUiState) -> ReportBuilderUiState) { _state.value = transform(_state.value) }

    fun save(onSaved: (Int) -> Unit) {
        val s = _state.value
        val customerId = s.customerId
        if (customerId == null || s.reportingEntityName.isBlank() || s.entityReference.isBlank() ||
            s.reporterName.isBlank() || s.reporterEmail.isBlank() || s.firstName.isBlank()
        ) {
            _state.value = s.copy(error = "Customer, reporting entity, reference, reporter, and subject first name are required.")
            return
        }
        _state.value = s.copy(loading = true, error = null)
        viewModelScope.launch {
            val body = ReportSaveRequest(
                customer_id = customerId, report_type = s.reportType,
                reporting_entity_name = s.reportingEntityName, entity_reference = s.entityReference,
                reporter_name = s.reporterName, reporter_email = s.reporterEmail,
                first_name = s.firstName, last_name = s.lastName,
                reason_description = s.reasonDescription, action_taken = s.actionTaken,
            )
            when (val result = repository.saveReport(body)) {
                is ApiResult.Success -> { _state.value = _state.value.copy(loading = false); onSaved(result.data.report_id) }
                is ApiResult.Failure -> _state.value = _state.value.copy(loading = false, error = result.message)
            }
        }
    }
}

@Composable
fun ReportBuilderScreen(repository: AmlkitRepository, onSaved: (Int) -> Unit) {
    val viewModel = amlkitViewModel(repository) { ReportBuilderViewModel(it) }
    val state by viewModel.state.collectAsState()
    LaunchedEffect(Unit) { viewModel.loadCustomers() }

    var customerMenuOpen by remember { mutableStateOf(false) }
    val selectedCustomerLabel = state.customers.firstOrNull { it.id == state.customerId }?.full_name ?: "Choose a customer"

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = screenContentPadding,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { Text(text = "New STR/SAR report", style = MaterialTheme.typography.headlineSmall) }
        if (state.error != null) item { ErrorBanner(message = state.error!!) }

        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(selected = state.reportType == "STR", onClick = { viewModel.update { it.copy(reportType = "STR") } }, label = { Text("STR") })
                FilterChip(selected = state.reportType == "SAR", onClick = { viewModel.update { it.copy(reportType = "SAR") } }, label = { Text("SAR") })
            }
        }

        item {
            TextButton(onClick = { customerMenuOpen = true }) { Text(selectedCustomerLabel) }
            DropdownMenu(expanded = customerMenuOpen, onDismissRequest = { customerMenuOpen = false }) {
                state.customers.forEach { c ->
                    DropdownMenuItem(text = { Text("${c.full_name} (${c.reference})") }, onClick = {
                        viewModel.update { it.copy(customerId = c.id) }
                        customerMenuOpen = false
                    })
                }
            }
        }

        item {
            OutlinedTextField(
                value = state.reportingEntityName, onValueChange = { v -> viewModel.update { it.copy(reportingEntityName = v) } },
                label = { Text("Reporting entity name") }, modifier = Modifier.fillMaxWidth(),
            )
        }
        item {
            OutlinedTextField(
                value = state.entityReference, onValueChange = { v -> viewModel.update { it.copy(entityReference = v) } },
                label = { Text("Entity reference") }, modifier = Modifier.fillMaxWidth(),
            )
        }
        item {
            OutlinedTextField(
                value = state.reporterName, onValueChange = { v -> viewModel.update { it.copy(reporterName = v) } },
                label = { Text("Reporter name") }, modifier = Modifier.fillMaxWidth(),
            )
        }
        item {
            OutlinedTextField(
                value = state.reporterEmail, onValueChange = { v -> viewModel.update { it.copy(reporterEmail = v) } },
                label = { Text("Reporter email") }, modifier = Modifier.fillMaxWidth(),
            )
        }
        item {
            OutlinedTextField(
                value = state.firstName, onValueChange = { v -> viewModel.update { it.copy(firstName = v) } },
                label = { Text("Subject first name") }, modifier = Modifier.fillMaxWidth(),
            )
        }
        item {
            OutlinedTextField(
                value = state.lastName, onValueChange = { v -> viewModel.update { it.copy(lastName = v) } },
                label = { Text("Subject last name") }, modifier = Modifier.fillMaxWidth(),
            )
        }
        item {
            OutlinedTextField(
                value = state.reasonDescription, onValueChange = { v -> viewModel.update { it.copy(reasonDescription = v) } },
                label = { Text("Reason for suspicion") }, modifier = Modifier.fillMaxWidth(),
            )
        }
        item {
            OutlinedTextField(
                value = state.actionTaken, onValueChange = { v -> viewModel.update { it.copy(actionTaken = v) } },
                label = { Text("Action taken") }, modifier = Modifier.fillMaxWidth(),
            )
        }

        item {
            Button(onClick = { viewModel.save(onSaved) }, enabled = !state.loading, modifier = Modifier.fillMaxWidth()) {
                if (state.loading) CircularProgressIndicator(modifier = Modifier.size(20.dp)) else Text("Save draft")
            }
        }
    }
}
