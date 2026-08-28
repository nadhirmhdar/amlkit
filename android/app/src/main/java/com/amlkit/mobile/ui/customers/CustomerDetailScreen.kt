package com.amlkit.mobile.ui.customers

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
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
import com.amlkit.mobile.data.dto.CustomerDetailResponse
import com.amlkit.mobile.data.dto.SignatureRequest
import com.amlkit.mobile.data.dto.TransactionRequest
import com.amlkit.mobile.data.dto.UboAddRequest
import com.amlkit.mobile.ui.common.ErrorBanner
import com.amlkit.mobile.ui.common.FullScreenLoading
import com.amlkit.mobile.ui.common.PillTone
import com.amlkit.mobile.ui.common.Resource
import com.amlkit.mobile.ui.common.SectionCard
import com.amlkit.mobile.ui.common.StatusPill
import com.amlkit.mobile.ui.common.alertStatusTone
import com.amlkit.mobile.ui.common.amlkitViewModel
import com.amlkit.mobile.ui.common.categoryTone
import com.amlkit.mobile.ui.common.riskTone
import com.amlkit.mobile.ui.common.screenContentPadding
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

class CustomerDetailViewModel(private val repository: AmlkitRepository) : ViewModel() {
    private val _state = MutableStateFlow<Resource<CustomerDetailResponse>>(Resource.Loading)
    val state: StateFlow<Resource<CustomerDetailResponse>> = _state

    private var customerId: Int = -1
    private var actionInFlight = false

    fun load(id: Int) {
        customerId = id
        _state.value = Resource.Loading
        viewModelScope.launch {
            fetch()
        }
    }

    private suspend fun fetch() {
        when (val result = repository.customerDetail(customerId)) {
            is ApiResult.Success -> _state.value = Resource.Content(result.data)
            is ApiResult.Failure -> _state.value = Resource.Error(result.message)
        }
    }

    fun addNote(body: String, onDone: (String?) -> Unit) = runAction(onDone) { repository.addNote(customerId, body) }

    fun addUbo(name: String, pct: Double?, controlType: String, onDone: (String?) -> Unit) =
        runAction(onDone) { repository.addUbo(customerId, UboAddRequest(name, pct, controlType)) }

    fun addTransaction(req: TransactionRequest, onDone: (String?) -> Unit) =
        runAction(onDone) { repository.addTransaction(customerId, req) }

    fun addSignature(req: SignatureRequest, onDone: (String?) -> Unit) =
        runAction(onDone) { repository.addSignature(customerId, req) }

    fun closeRelationship(onDone: (String?) -> Unit) = runAction(onDone) { repository.closeCustomer(customerId) }

    private fun <T> runAction(onDone: (String?) -> Unit, call: suspend () -> ApiResult<T>) {
        if (actionInFlight) return
        actionInFlight = true
        viewModelScope.launch {
            when (val result = call()) {
                is ApiResult.Success -> { fetch(); onDone(null) }
                is ApiResult.Failure -> onDone(result.message)
            }
            actionInFlight = false
        }
    }
}

@Composable
fun CustomerDetailScreen(
    repository: AmlkitRepository,
    customerId: Int,
    onOpenEvidence: () -> Unit,
) {
    val viewModel = amlkitViewModel(repository) { CustomerDetailViewModel(it) }
    val state by viewModel.state.collectAsState()
    LaunchedEffect(customerId) { viewModel.load(customerId) }

    when (val current = state) {
        is Resource.Loading -> FullScreenLoading(modifier = Modifier.fillMaxSize())
        is Resource.Error -> ErrorBanner(message = current.message, modifier = Modifier.fillMaxSize())
        is Resource.Content -> CustomerDetailContent(current.data, viewModel, onOpenEvidence)
    }
}

@Composable
private fun CustomerDetailContent(
    data: CustomerDetailResponse,
    viewModel: CustomerDetailViewModel,
    onOpenEvidence: () -> Unit,
) {
    var showNoteDialog by remember { mutableStateOf(false) }
    var showUboDialog by remember { mutableStateOf(false) }
    var showTxnDialog by remember { mutableStateOf(false) }
    var showSignDialog by remember { mutableStateOf(false) }
    var showCloseConfirm by remember { mutableStateOf(false) }
    var actionError by remember { mutableStateOf<String?>(null) }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = screenContentPadding,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Column {
                Text(text = data.customer.full_name, style = MaterialTheme.typography.headlineSmall)
                Text(text = "${data.customer.reference} · ${data.customer.customer_type}", style = MaterialTheme.typography.bodyMedium)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    StatusPill(text = data.risk?.rating ?: "unrated", tone = riskTone(data.risk?.rating))
                    StatusPill(text = data.customer.status, tone = PillTone.NEUTRAL)
                }
            }
        }
        if (actionError != null) {
            item { ErrorBanner(message = actionError!!) }
        }

        item {
            SectionCard(title = "Risk") {
                Text(text = "Score: ${data.risk?.score ?: "—"}")
                Text(text = "Enhanced due diligence: ${if (data.risk?.requires_edd == 1) "required" else "not required"}")
                Text(text = "Next review: ${data.risk?.next_review ?: "—"}")
            }
        }

        if (data.alerts.isNotEmpty()) {
            item { Text(text = "Alerts (${data.alerts.size})", style = MaterialTheme.typography.titleMedium) }
            items(data.alerts) { alert ->
                SectionCard(title = alert.caption) {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        StatusPill(text = alert.category, tone = categoryTone(alert.category))
                        StatusPill(text = alert.status, tone = alertStatusTone(alert.status))
                    }
                    Text(text = "Matched: ${alert.matched_party ?: alert.caption} (score ${"%.2f".format(alert.score)})")
                }
            }
            item { Text(text = "Disposition alerts from the Alerts tab.", style = MaterialTheme.typography.labelSmall) }
        }

        item {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(text = "Beneficial owners", style = MaterialTheme.typography.titleMedium)
                TextButton(onClick = { showUboDialog = true }) { Text("+ Add") }
            }
        }
        items(data.ubos) { ubo ->
            SectionCard(title = ubo.person_name) {
                Text(text = "${ubo.control_type} · ${ubo.ownership_pct?.let { "$it%" } ?: "% unknown"} · ${if (ubo.is_ubo == 1) "UBO" else "recorded owner"}")
            }
        }

        item {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(text = "Transactions", style = MaterialTheme.typography.titleMedium)
                TextButton(onClick = { showTxnDialog = true }) { Text("+ Add") }
            }
        }
        items(data.transactions.take(10)) { txn ->
            Text(text = "${txn.direction} ${txn.amount} ${txn.currency} · ${txn.method} · ${txn.occurred_at}")
        }
        if (data.transaction_alerts.isNotEmpty()) {
            item {
                SectionCard(title = "Transaction-monitoring alerts") {
                    data.transaction_alerts.forEach { t ->
                        StatusPill(text = "${t.rule_key} (${t.severity})", tone = PillTone.WARNING)
                    }
                }
            }
        }

        item {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(text = "Case notes", style = MaterialTheme.typography.titleMedium)
                TextButton(onClick = { showNoteDialog = true }) { Text("+ Add") }
            }
        }
        items(data.notes) { note ->
            SectionCard(title = note.author) {
                Text(text = note.body)
                Text(text = note.created_at, style = MaterialTheme.typography.labelSmall)
            }
        }

        item {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(text = "Signatures", style = MaterialTheme.typography.titleMedium)
                TextButton(onClick = { showSignDialog = true }) { Text("+ Add") }
            }
        }
        items(data.signatures) { sig ->
            Text(text = "${sig.purpose} — signed by ${sig.signer_name} (${sig.signer_role}) on ${sig.signed_at}")
        }

        item {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                TextButton(onClick = onOpenEvidence) { Text("View evidence pack") }
                if (data.customer.status == "active") {
                    TextButton(onClick = { showCloseConfirm = true }) { Text("Close relationship") }
                }
            }
        }
    }

    if (showNoteDialog) {
        TextInputDialog(
            title = "Add case note", label = "Note",
            onDismiss = { showNoteDialog = false },
            onConfirm = { text ->
                viewModel.addNote(text) { err -> actionError = err }
                showNoteDialog = false
            },
        )
    }
    if (showUboDialog) {
        UboDialog(onDismiss = { showUboDialog = false }, onConfirm = { name, pct, type ->
            viewModel.addUbo(name, pct, type) { err -> actionError = err }
            showUboDialog = false
        })
    }
    if (showTxnDialog) {
        TransactionDialog(onDismiss = { showTxnDialog = false }, onConfirm = { req ->
            viewModel.addTransaction(req) { err -> actionError = err }
            showTxnDialog = false
        })
    }
    if (showSignDialog) {
        SignatureDialog(onDismiss = { showSignDialog = false }, onConfirm = { req ->
            viewModel.addSignature(req) { err -> actionError = err }
            showSignDialog = false
        })
    }
    if (showCloseConfirm) {
        AlertDialog(
            onDismissRequest = { showCloseConfirm = false },
            title = { Text("Close this relationship?") },
            text = { Text("Records are retained for 5 years per Cabinet Res. 134/2025.") },
            confirmButton = {
                TextButton(onClick = {
                    viewModel.closeRelationship { err -> actionError = err }
                    showCloseConfirm = false
                }) { Text("Close relationship") }
            },
            dismissButton = { TextButton(onClick = { showCloseConfirm = false }) { Text("Cancel") } },
        )
    }
}

@Composable
private fun TextInputDialog(title: String, label: String, onDismiss: () -> Unit, onConfirm: (String) -> Unit) {
    var text by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = { OutlinedTextField(value = text, onValueChange = { text = it }, label = { Text(label) }) },
        confirmButton = { TextButton(onClick = { if (text.isNotBlank()) onConfirm(text) }) { Text("Save") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun UboDialog(onDismiss: () -> Unit, onConfirm: (String, Double?, String) -> Unit) {
    var name by remember { mutableStateOf("") }
    var pct by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add beneficial owner") },
        text = {
            Column {
                OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Name") })
                OutlinedTextField(value = pct, onValueChange = { pct = it }, label = { Text("% owned") })
            }
        },
        confirmButton = {
            TextButton(onClick = { if (name.isNotBlank()) onConfirm(name, pct.toDoubleOrNull(), "ownership") }) { Text("Add & screen") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun TransactionDialog(onDismiss: () -> Unit, onConfirm: (TransactionRequest) -> Unit) {
    var direction by remember { mutableStateOf("in") }
    var method by remember { mutableStateOf("cash") }
    var amount by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Record transaction") },
        text = {
            Column {
                OutlinedTextField(value = direction, onValueChange = { direction = it }, label = { Text("Direction (in/out)") })
                OutlinedTextField(value = method, onValueChange = { method = it }, label = { Text("Method (cash/wire/...)") })
                OutlinedTextField(value = amount, onValueChange = { amount = it }, label = { Text("Amount (AED)") })
            }
        },
        confirmButton = {
            TextButton(onClick = {
                val amt = amount.toDoubleOrNull()
                if (amt != null) onConfirm(TransactionRequest(direction, method, amt, "AED", amt))
            }) { Text("Record") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun SignatureDialog(onDismiss: () -> Unit, onConfirm: (SignatureRequest) -> Unit) {
    var purpose by remember { mutableStateOf("") }
    var statement by remember { mutableStateOf("") }
    var signerName by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Record signature") },
        text = {
            Column {
                OutlinedTextField(value = purpose, onValueChange = { purpose = it }, label = { Text("Purpose") })
                OutlinedTextField(value = statement, onValueChange = { statement = it }, label = { Text("Statement") })
                OutlinedTextField(value = signerName, onValueChange = { signerName = it }, label = { Text("Signer name") })
            }
        },
        confirmButton = {
            TextButton(onClick = {
                if (purpose.isNotBlank() && statement.isNotBlank() && signerName.isNotBlank()) {
                    onConfirm(SignatureRequest(purpose, statement, signerName))
                }
            }) { Text("Sign") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
