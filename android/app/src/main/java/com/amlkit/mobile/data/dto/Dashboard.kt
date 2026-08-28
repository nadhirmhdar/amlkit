package com.amlkit.mobile.data.dto

import kotlinx.serialization.Serializable

@Serializable
data class DatasetStalenessDto(
    val key: String,
    val title: String,
    val mandatory: Boolean,
    val entities: Int? = null,
    val hours_since_refresh: Double? = null,
    val breach: Boolean,
)

@Serializable
data class DueForReviewDto(
    val id: Int,
    val reference: String,
    val full_name: String,
    val rating: String? = null,
    val next_review: String? = null,
)

@Serializable
data class DashboardCountsDto(
    val customers: Int = 0,
    val entities: Int = 0,
    val screenings: Int = 0,
    val alerts_total: Int = 0,
)

@Serializable
data class DashboardResponse(
    val staleness: List<DatasetStalenessDto> = emptyList(),
    val breaches: List<DatasetStalenessDto> = emptyList(),
    val compliant: Boolean = true,
    val open_alerts: List<AlertDto> = emptyList(),
    val open_by_category: Map<String, Int> = emptyMap(),
    val oldest_open: List<AlertDto> = emptyList(),
    val high_risk_customers: Int = 0,
    val pending_review: List<AlertDto> = emptyList(),
    val due_for_review: List<DueForReviewDto> = emptyList(),
    val open_transaction_alerts: List<TransactionAlertDto> = emptyList(),
    val oldest_open_transaction_alerts: List<TransactionAlertDto> = emptyList(),
    val counts: DashboardCountsDto = DashboardCountsDto(),
    val generated_at: String? = null,
)

@Serializable
data class DatasetDto(
    val key: String,
    val title: String,
    val publisher: String? = null,
    val licence: String? = null,
    val is_mandatory: Int = 0,
    val last_refresh: String? = null,
    val entity_count: Int? = null,
)

@Serializable
data class DatasetsResponse(val datasets: List<DatasetDto> = emptyList())
