package com.amlkit.mobile.ui.more

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.amlkit.mobile.data.AuthTokenStore

private data class MoreItem(val title: String, val subtitle: String, val onClick: () -> Unit)

@Composable
fun MoreScreen(
    tokenStore: AuthTokenStore,
    onAlerts: () -> Unit,
    onAudit: () -> Unit,
    onAdmin: () -> Unit,
    onReports: () -> Unit,
    onLogout: () -> Unit,
) {
    val role by tokenStore.operatorRole.collectAsState()
    val items = buildList {
        add(MoreItem("Alerts", "Screening queue and disposition", onAlerts))
        add(MoreItem("Reports", "STR/SAR reports to the UAE FIU", onReports))
        add(MoreItem("Audit trail", "Every action taken on this organization's data", onAudit))
        if (role == "mlro") {
            add(MoreItem("Admin", "Operators, alert threshold, sanctions refresh", onAdmin))
        }
    }

    Column(modifier = Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(text = "More", style = MaterialTheme.typography.headlineSmall)
        items.forEach { item ->
            Card(
                onClick = item.onClick,
                modifier = Modifier.fillMaxWidth(),
                elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(text = item.title, style = MaterialTheme.typography.titleMedium)
                    Text(text = item.subtitle, style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
        OutlinedButton(onClick = onLogout, modifier = Modifier.fillMaxWidth()) { Text("Sign out") }
    }
}
