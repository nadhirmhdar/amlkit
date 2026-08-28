package com.amlkit.mobile.ui.customers

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.amlkit.mobile.data.AmlkitRepository
import com.amlkit.mobile.data.ApiResult
import com.amlkit.mobile.data.dto.CustomerCreateRequest
import com.amlkit.mobile.data.dto.UboIn
import com.amlkit.mobile.ui.common.ErrorBanner
import com.amlkit.mobile.ui.common.amlkitViewModel
import com.amlkit.mobile.ui.common.screenContentPadding
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class DraftUbo(val personName: String = "", val ownershipPct: String = "", val controlType: String = "ownership")

data class CustomerNewUiState(
    val reference: String = "",
    val fullName: String = "",
    val customerType: String = "natural",
    val nationality: String = "",
    val sector: String = "other",
    val ubos: List<DraftUbo> = emptyList(),
    val loading: Boolean = false,
    val error: String? = null,
    val blockedWarning: String? = null,
)

class CustomerNewViewModel(private val repository: AmlkitRepository) : ViewModel() {
    private val _state = MutableStateFlow(CustomerNewUiState())
    val state: StateFlow<CustomerNewUiState> = _state

    fun onReferenceChange(v: String) { _state.value = _state.value.copy(reference = v) }
    fun onFullNameChange(v: String) { _state.value = _state.value.copy(fullName = v) }
    fun onCustomerTypeChange(v: String) { _state.value = _state.value.copy(customerType = v) }
    fun onNationalityChange(v: String) { _state.value = _state.value.copy(nationality = v) }
    fun onSectorChange(v: String) { _state.value = _state.value.copy(sector = v) }

    fun addUbo() { _state.value = _state.value.copy(ubos = _state.value.ubos + DraftUbo()) }
    fun removeUbo(index: Int) {
        _state.value = _state.value.copy(ubos = _state.value.ubos.toMutableList().apply { removeAt(index) })
    }
    fun updateUbo(index: Int, ubo: DraftUbo) {
        _state.value = _state.value.copy(ubos = _state.value.ubos.toMutableList().apply { set(index, ubo) })
    }

    fun submit(onCreated: (Int) -> Unit) {
        val s = _state.value
        if (s.reference.isBlank() || s.fullName.isBlank()) {
            _state.value = s.copy(error = "Reference and full name are required.")
            return
        }
        _state.value = s.copy(loading = true, error = null)
        viewModelScope.launch {
            val body = CustomerCreateRequest(
                reference = s.reference.trim(),
                full_name = s.fullName.trim(),
                customer_type = s.customerType,
                nationality = s.nationality.trim(),
                sector = s.sector,
                ubos = s.ubos.filter { it.personName.isNotBlank() }.map {
                    UboIn(it.personName.trim(), it.ownershipPct.toDoubleOrNull(), it.controlType)
                },
            )
            when (val result = repository.createCustomer(body)) {
                is ApiResult.Success -> {
                    _state.value = _state.value.copy(loading = false)
                    if (result.data.blocked) {
                        _state.value = _state.value.copy(
                            blockedWarning = "MATCH FOUND during onboarding screening — review the alert before proceeding.",
                        )
                    }
                    onCreated(result.data.customer_id)
                }
                is ApiResult.Failure -> _state.value = _state.value.copy(loading = false, error = result.message)
            }
        }
    }
}

@Composable
fun CustomerNewScreen(repository: AmlkitRepository, onCreated: (Int) -> Unit) {
    val viewModel = amlkitViewModel(repository) { CustomerNewViewModel(it) }
    val state by viewModel.state.collectAsState()

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = screenContentPadding,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { Text(text = "Onboard a customer", style = MaterialTheme.typography.headlineSmall) }
        if (state.error != null) {
            item { ErrorBanner(message = state.error!!) }
        }
        item {
            OutlinedTextField(
                value = state.reference, onValueChange = viewModel::onReferenceChange,
                label = { Text("Reference") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
            )
        }
        item {
            OutlinedTextField(
                value = state.fullName, onValueChange = viewModel::onFullNameChange,
                label = { Text("Full legal name") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
            )
        }
        item {
            OutlinedTextField(
                value = state.nationality, onValueChange = viewModel::onNationalityChange,
                label = { Text("Nationality (optional)") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
            )
        }
        item {
            OutlinedTextField(
                value = state.sector, onValueChange = viewModel::onSectorChange,
                label = { Text("Sector") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
            )
        }

        item {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(text = "Beneficial owners (25%+ or senior official)", style = MaterialTheme.typography.titleSmall)
                TextButton(onClick = viewModel::addUbo) { Text("+ Add") }
            }
        }
        itemsIndexed(state.ubos) { index, ubo ->
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = ubo.personName,
                    onValueChange = { viewModel.updateUbo(index, ubo.copy(personName = it)) },
                    label = { Text("Name") },
                    modifier = Modifier.weight(1f),
                )
                OutlinedTextField(
                    value = ubo.ownershipPct,
                    onValueChange = { viewModel.updateUbo(index, ubo.copy(ownershipPct = it)) },
                    label = { Text("% owned") },
                    modifier = Modifier.weight(0.5f),
                )
                TextButton(onClick = { viewModel.removeUbo(index) }) { Text("Remove") }
            }
        }

        item {
            Button(onClick = { viewModel.submit(onCreated) }, enabled = !state.loading, modifier = Modifier.fillMaxWidth()) {
                if (state.loading) CircularProgressIndicator(modifier = Modifier.size(20.dp)) else Text("Onboard & screen")
            }
        }

        state.blockedWarning?.let { warning -> item { ErrorBanner(message = warning) } }
    }
}
