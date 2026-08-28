package com.amlkit.mobile.ui.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.amlkit.mobile.data.AmlkitRepository
import com.amlkit.mobile.data.ApiResult
import com.amlkit.mobile.ui.common.ErrorBanner
import com.amlkit.mobile.ui.common.amlkitViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class RegisterOrgUiState(
    val orgName: String = "",
    val name: String = "",
    val email: String = "",
    val password: String = "",
    val loading: Boolean = false,
    val error: String? = null,
)

class RegisterOrgViewModel(private val repository: AmlkitRepository) : ViewModel() {
    private val _state = MutableStateFlow(RegisterOrgUiState())
    val state: StateFlow<RegisterOrgUiState> = _state

    fun onOrgNameChange(v: String) { _state.value = _state.value.copy(orgName = v, error = null) }
    fun onNameChange(v: String) { _state.value = _state.value.copy(name = v, error = null) }
    fun onEmailChange(v: String) { _state.value = _state.value.copy(email = v, error = null) }
    fun onPasswordChange(v: String) { _state.value = _state.value.copy(password = v, error = null) }

    fun register(onSuccess: () -> Unit) {
        val s = _state.value
        if (s.orgName.isBlank() || s.name.isBlank() || s.email.isBlank()) {
            _state.value = s.copy(error = "All fields are required.")
            return
        }
        if (s.password.length < 10) {
            _state.value = s.copy(error = "Password must be at least 10 characters.")
            return
        }
        _state.value = s.copy(loading = true, error = null)
        viewModelScope.launch {
            when (val result = repository.registerOrganization(s.orgName.trim(), s.name.trim(), s.email.trim(), s.password)) {
                is ApiResult.Success -> {
                    _state.value = _state.value.copy(loading = false)
                    onSuccess()
                }
                is ApiResult.Failure -> _state.value = _state.value.copy(loading = false, error = result.message)
            }
        }
    }
}

@Composable
fun RegisterOrgScreen(
    repository: AmlkitRepository,
    onRegistered: () -> Unit,
    onBackToLogin: () -> Unit,
) {
    val viewModel = amlkitViewModel(repository) { RegisterOrgViewModel(it) }
    val state by viewModel.state.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text(text = "Register your firm", style = MaterialTheme.typography.headlineSmall)
        Text(
            text = "You'll be the first MLRO for this organization.",
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(bottom = 20.dp, top = 4.dp),
        )

        if (state.error != null) {
            ErrorBanner(message = state.error!!, modifier = Modifier.padding(bottom = 12.dp))
        }

        OutlinedTextField(
            value = state.orgName, onValueChange = viewModel::onOrgNameChange,
            label = { Text("Organization name") }, singleLine = true,
            modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp),
        )
        OutlinedTextField(
            value = state.name, onValueChange = viewModel::onNameChange,
            label = { Text("Your name") }, singleLine = true,
            modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp),
        )
        OutlinedTextField(
            value = state.email, onValueChange = viewModel::onEmailChange,
            label = { Text("Email") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
            modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp),
        )
        OutlinedTextField(
            value = state.password, onValueChange = viewModel::onPasswordChange,
            label = { Text("Password (min. 10 characters)") }, singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            modifier = Modifier.fillMaxWidth().padding(bottom = 20.dp),
        )

        Button(
            onClick = { viewModel.register(onRegistered) },
            enabled = !state.loading,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (state.loading) CircularProgressIndicator(modifier = Modifier.size(20.dp)) else Text("Register")
        }

        TextButton(onClick = onBackToLogin, modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) {
            Text("Already have an account? Sign in")
        }
    }
}
