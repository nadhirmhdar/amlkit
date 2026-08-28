package com.amlkit.mobile.ui.customers

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
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
import com.amlkit.mobile.data.dto.CustomerListItemDto
import com.amlkit.mobile.ui.common.ErrorBanner
import com.amlkit.mobile.ui.common.FullScreenLoading
import com.amlkit.mobile.ui.common.PillTone
import com.amlkit.mobile.ui.common.Resource
import com.amlkit.mobile.ui.common.SectionCard
import com.amlkit.mobile.ui.common.StatusPill
import com.amlkit.mobile.ui.common.amlkitViewModel
import com.amlkit.mobile.ui.common.riskTone
import com.amlkit.mobile.ui.common.screenContentPadding
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

class CustomersListViewModel(private val repository: AmlkitRepository) : ViewModel() {
    private val _state = MutableStateFlow<Resource<List<CustomerListItemDto>>>(Resource.Loading)
    val state: StateFlow<Resource<List<CustomerListItemDto>>> = _state

    fun load() {
        _state.value = Resource.Loading
        viewModelScope.launch {
            when (val result = repository.customers()) {
                is ApiResult.Success -> _state.value = Resource.Content(result.data.customers)
                is ApiResult.Failure -> _state.value = Resource.Error(result.message)
            }
        }
    }
}

@Composable
fun CustomersListScreen(
    repository: AmlkitRepository,
    onOpenCustomer: (Int) -> Unit,
    onNewCustomer: () -> Unit,
) {
    val viewModel = amlkitViewModel(repository) { CustomersListViewModel(it) }
    val state by viewModel.state.collectAsState()
    LaunchedEffect(Unit) { viewModel.load() }

    Scaffold(
        floatingActionButton = {
            FloatingActionButton(onClick = onNewCustomer) {
                Icon(Icons.Filled.Add, contentDescription = "Onboard customer")
            }
        },
    ) { padding ->
        Box(modifier = Modifier.fillMaxSize().padding(padding)) {
            when (val current = state) {
                is Resource.Loading -> FullScreenLoading(modifier = Modifier.fillMaxSize())
                is Resource.Error -> ErrorBanner(message = current.message)
                is Resource.Content -> {
                    if (current.data.isEmpty()) {
                        Text(
                            text = "No customers yet. Tap + to onboard one.",
                            modifier = Modifier.padding(24.dp),
                        )
                    } else {
                        LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = screenContentPadding,
                            verticalArrangement = Arrangement.spacedBy(10.dp),
                        ) {
                            items(current.data, key = { it.id }) { customer ->
                                CustomerRow(customer, onClick = { onOpenCustomer(customer.id) })
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun CustomerRow(customer: CustomerListItemDto, onClick: () -> Unit) {
    SectionCard(title = customer.full_name, modifier = Modifier.fillMaxWidth()) {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            StatusPill(text = customer.rating ?: "unrated", tone = riskTone(customer.rating))
            if (customer.open_alerts > 0) {
                StatusPill(text = "${customer.open_alerts} open alert(s)", tone = PillTone.DANGER)
            }
            if (customer.review_overdue) {
                StatusPill(text = "review overdue", tone = PillTone.WARNING)
            }
        }
        Text(text = "${customer.reference} · ${customer.customer_type} · ${customer.status}", style = MaterialTheme.typography.bodySmall)
        TextButton(onClick = onClick) { Text("Open case file") }
    }
}
