package com.amlkit.mobile.data.dto

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

@Serializable
data class AlertDto(
    val id: Int,
    val score: Double,
    val matched_name: String,
    val status: String,
    val disposition: String? = null,
    val reason_code: String? = null,
    val independent_review: String? = null,
    val assigned_to: String? = null,
    val dispositioned_by: String? = null,
    val dispositioned_at: String? = null,
    val created_at: String,
    val entity_id: Int,
    val caption: String,
    val schema_type: String? = null,
    val topics: List<String> = emptyList(),
    val programs: List<String> = emptyList(),
    val countries: List<String> = emptyList(),
    val dataset: String? = null,
    val dataset_title: String? = null,
    val category: String = "other",
    val obligation: String? = null,
    val customer_id: Int? = null,
    val reference: String? = null,
    val customer_name: String? = null,
    val ubo_name: String? = null,
    val matched_party: String? = null,
    val via_ubo: Boolean = false,
    val aliases: List<EntityNameDto> = emptyList(),
    val reviews: List<ReviewDto> = emptyList(),
)

@Serializable
data class EntityNameDto(val name: String, val type: String? = null, val script: String? = null)

@Serializable
data class ReviewDto(
    val action: String,
    val status: String,
    val reason_code: String? = null,
    val reason_label: String? = null,
    val narrative: String? = null,
    val operator: String,
    val created_at: String,
)

@Serializable
data class ScreenRequest(
    val name: String,
    val country: String = "",
    val birth_date: String = "",
    val gender: String = "",
)

@Serializable
data class ScreenHitDto(
    val score: Double,
    val caption: String,
    val dataset: String,
    val schema_type: String? = null,
    val matched_name: String,
    val category: String,
    val obligation: String? = null,
    val programs: List<String> = emptyList(),
    val detail: JsonElement? = null,
    val entity_id: Int,
    val aliases: List<EntityNameDto> = emptyList(),
)

@Serializable
data class ScreenResponse(
    val query: String,
    val clear: Boolean,
    val candidates: Int,
    val threshold: Double,
    val low_confidence: Boolean = false,
    val hits: List<ScreenHitDto> = emptyList(),
)

@Serializable
data class AlertsResponse(val alerts: List<AlertDto> = emptyList())

@Serializable
data class AlertDispositionRequest(
    val status: String,
    val reason_code: String = "",
    val narrative: String = "",
)

@Serializable
data class AlertConfirmRequest(val agree: Boolean = true, val narrative: String = "")

@Serializable
data class AlertAssignRequest(val operator: String? = null)

@Serializable
data class ReviewOutcomeDto(
    val alert_id: Int,
    val status: String,
    val awaiting_second_review: Boolean,
    val independent_review: String,
    val message: String,
)

@Serializable
data class TransactionAlertDto(
    val id: Int,
    val rule_key: String,
    val severity: String,
    val status: String,
    val disposition: String? = null,
    val dispositioned_by: String? = null,
    val dispositioned_at: String? = null,
    val assigned_to: String? = null,
    val created_at: String,
    val transaction_id: Int,
    val amount: Double,
    val currency: String,
    val amount_aed: Double? = null,
    val method: String,
    val direction: String,
    val counterparty_name: String? = null,
    val counterparty_country: String? = null,
    val occurred_at: String,
    val customer_id: Int,
    val reference: String? = null,
    val customer_name: String? = null,
)

@Serializable
data class TxnAlertDispositionRequest(val status: String, val note: String = "")

@Serializable
data class ReasonCodesResponse(
    val reason_codes: Map<String, String> = emptyMap(),
    val single_operator_mode: Boolean = false,
)
