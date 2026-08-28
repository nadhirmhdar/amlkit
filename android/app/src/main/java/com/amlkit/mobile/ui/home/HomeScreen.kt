package com.amlkit.mobile.ui.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.amlkit.mobile.data.AuthTokenStore
import java.time.LocalTime

private data class QuickAction(val title: String, val subtitle: String, val onClick: () -> Unit)

@Composable
fun HomeScreen(
    tokenStore: AuthTokenStore,
    onScreenName: () -> Unit,
    onViewCustomers: () -> Unit,
    onViewAlerts: () -> Unit,
    onViewDashboard: () -> Unit,
) {
    val operatorName by tokenStore.operatorName.collectAsState()
    val firstName = operatorName?.trim()?.split(" ")?.firstOrNull() ?: operatorName

    val greeting = remember { currentGreeting() }

    val actions = listOf(
        QuickAction("Screen a name", "Run an ad-hoc sanctions/PEP check", onScreenName),
        QuickAction("Customers", "Onboard or review a customer's case file", onViewCustomers),
        QuickAction("Alerts", "Triage the open screening queue", onViewAlerts),
        QuickAction("Dashboard", "Compliance overview and list staleness", onViewDashboard),
    )

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Column(modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp)) {
                Text(text = "$greeting${if (firstName != null) ", $firstName" else ""}", style = MaterialTheme.typography.headlineSmall)
                Text(text = "What would you like to do?", style = MaterialTheme.typography.bodyMedium)
            }
        }
        items(actions) { action ->
            Card(
                onClick = action.onClick,
                modifier = Modifier.fillMaxWidth(),
                elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(text = action.title, style = MaterialTheme.typography.titleMedium)
                    Text(text = action.subtitle, style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
    }
}

private fun currentGreeting(): String {
    val hour = LocalTime.now().hour
    return when {
        hour < 12 -> "Good morning"
        hour < 18 -> "Good afternoon"
        else -> "Good evening"
    }
}
