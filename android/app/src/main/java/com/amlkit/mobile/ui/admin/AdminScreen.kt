package com.amlkit.mobile.ui.admin

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
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
import com.amlkit.mobile.data.dto.AdminResponse
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

class AdminViewModel(private val repository: AmlkitRepository) : ViewModel() {
    private val _state = MutableStateFlow<Resource<AdminResponse>>(Resource.Loading)
    val state: StateFlow<Resource<AdminResponse>> = _state
    private val _message = MutableStateFlow<String?>(null)
    val message: StateFlow<String?> = _message

    fun load() {
        _state.value = Resource.Loading
        viewModelScope.launch {
            when (val result = repository.admin()) {
                is ApiResult.Success -> _state.value = Resource.Content(result.data)
                is ApiResult.Failure -> _state.value = Resource.Error(result.message)
            }
        }
    }

    fun setThreshold(value: Double?) {
        viewModelScope.launch {
            when (val result = repository.setThreshold(value)) {
                is ApiResult.Success -> load()
                is ApiResult.Failure -> _message.value = result.message
            }
        }
    }

    fun createOperator(name: String, email: String, password: String, role: String) {
        viewModelScope.launch {
            when (val result = repository.createOperator(name, email, password, role)) {
                is ApiResult.Success -> load()
                is ApiResult.Failure -> _message.value = result.message
            }
        }
    }

    fun resetPassword(operatorId: Int, newPassword: String) {
        viewModelScope.launch {
            when (val result = repository.resetOperatorPassword(operatorId, newPassword)) {
                is ApiResult.Success -> _message.value = "Password reset. All that operator's sessions were signed out."
                is ApiResult.Failure -> _message.value = result.message
            }
        }
    }

    fun deactivateOperator(operatorId: Int) {
        viewModelScope.launch {
            when (val result = repository.deactivateOperator(operatorId)) {
                is ApiResult.Success -> load()
                is ApiResult.Failure -> _message.value = result.message
            }
        }
    }

    fun refreshSanctions() {
        viewModelScope.launch {
            when (val result = repository.refreshSanctions()) {
                is ApiResult.Success -> {
                    _message.value = "Refreshed: " + result.data.loaded.joinToString("; ")
                    load()
                }
                is ApiResult.Failure -> _message.value = result.message
            }
        }
    }

    fun dismissMessage() { _message.value = null }
}

@Composable
fun AdminScreen(repository: AmlkitRepository) {
    val viewModel = amlkitViewModel(repository) { AdminViewModel(it) }
    val state by viewModel.state.collectAsState()
    val message by viewModel.message.collectAsState()
    LaunchedEffect(Unit) { viewModel.load() }

    var showCreateOperator by remember { mutableStateOf(false) }
    var thresholdText by remember { mutableStateOf("") }

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
                item { Text(text = "Admin — ${data.org.name}", style = MaterialTheme.typography.headlineSmall) }
                if (message != null) item { ErrorBanner(message = message!!) }

                item {
                    SectionCard(title = "Alert threshold") {
                        Text(text = "Current: ${data.threshold ?: "engine default (${data.default_threshold})"}")
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedTextField(
                                value = thresholdText, onValueChange = { thresholdText = it },
                                label = { Text("0.0 – 1.0") }, modifier = Modifier.fillMaxWidth(),
                            )
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            TextButton(onClick = { viewModel.setThreshold(thresholdText.toDoubleOrNull()) }) { Text("Save") }
                            TextButton(onClick = { thresholdText = ""; viewModel.setThreshold(null) }) { Text("Reset to default") }
                        }
                    }
                }

                item {
                    SectionCard(title = "Sanctions & PEP lists") {
                        data.sanctions.forEach { d ->
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text(text = d.title, modifier = Modifier.fillMaxWidth())
                                StatusPill(
                                    text = if (d.breach) "BREACH" else "OK",
                                    tone = if (d.breach) PillTone.DANGER else PillTone.SUCCESS,
                                )
                            }
                        }
                        Button(onClick = viewModel::refreshSanctions) { Text("Refresh now") }
                    }
                }

                item {
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(text = "Operators", style = MaterialTheme.typography.titleMedium)
                        TextButton(onClick = { showCreateOperator = true }) { Text("+ Add") }
                    }
                }
                items(data.operators) { op ->
                    SectionCard(title = op.name) {
                        Text(text = "${op.email} · ${op.role} · ${if (op.is_active == 1) "active" else "deactivated"}")
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            if (op.is_active == 1) {
                                TextButton(onClick = { viewModel.deactivateOperator(op.id) }) { Text("Deactivate") }
                            }
                        }
                    }
                }
            }
        }
    }

    if (showCreateOperator) {
        CreateOperatorDialog(
            onDismiss = { showCreateOperator = false },
            onConfirm = { name, email, password, role ->
                viewModel.createOperator(name, email, password, role)
                showCreateOperator = false
            },
        )
    }
}

@Composable
private fun CreateOperatorDialog(onDismiss: () -> Unit, onConfirm: (String, String, String, String) -> Unit) {
    var name by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var role by remember { mutableStateOf("officer") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add operator") },
        text = {
            Column {
                OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Name") })
                OutlinedTextField(value = email, onValueChange = { email = it }, label = { Text("Email") })
                OutlinedTextField(value = password, onValueChange = { password = it }, label = { Text("Password (min. 10 chars)") })
                OutlinedTextField(value = role, onValueChange = { role = it }, label = { Text("Role (mlro/officer)") })
            }
        },
        confirmButton = {
            TextButton(onClick = {
                if (name.isNotBlank() && email.isNotBlank() && password.length >= 10) onConfirm(name, email, password, role)
            }) { Text("Create") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
