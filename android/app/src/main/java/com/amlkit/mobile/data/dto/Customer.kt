package com.amlkit.mobile.data.dto

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

@Serializable
data class CustomerListItemDto(
    val id: Int,
    val reference: String,
    val full_name: String,
    val name_arabic: String? = null,
    val customer_type: String,
    val nationality: String? = null,
    val sector: String? = null,
    val status: String,
    val onboarded_at: String,
    val rating: String? = null,
    val risk_score: Double? = null,
    val requires_edd: Int? = null,
    val next_review: String? = null,
    val last_screened: String? = null,
    val open_alerts: Int = 0,
    val review_overdue: Boolean = false,
)

@Serializable
data class CustomersListResponse(val customers: List<CustomerListItemDto> = emptyList())

@Serializable
data class CustomerRecordDto(
    val id: Int,
    val reference: String,
    val customer_type: String,
    val full_name: String,
    val name_arabic: String? = null,
    val nationality: String? = null,
    val country: String? = null,
    val birth_date: String? = null,
    val gender: String? = null,
    val id_number: String? = null,
    val id_type: String? = null,
    val trade_licence: String? = null,
    val sector: String? = null,
    val delivery_channel: String? = null,
    val is_cash_intensive: Int = 0,
    val status: String,
    val onboarded_at: String,
    val retention_until: String? = null,
    val created_at: String,
    val updated_at: String,
)

@Serializable
data class UboDto(
    val id: Int,
    val customer_id: Int,
    val person_name: String,
    val name_arabic: String? = null,
    val nationality: String? = null,
    val birth_date: String? = null,
    val ownership_pct: Double? = null,
    val control_type: String,
    val is_ubo: Int = 0,
    val notes: String? = null,
    val created_at: String,
)

@Serializable
data class RiskAssessmentDto(
    val id: Int? = null,
    val customer_id: Int? = null,
    val score: Double,
    val rating: String,
    val requires_edd: Int = 0,
    val factors: JsonElement? = null,
    val ruleset_version: String? = null,
    val next_review: String? = null,
    val assessed_at: String? = null,
)

@Serializable
data class ScreeningRecordDto(
    val id: Int,
    val customer_id: Int? = null,
    val ubo_id: Int? = null,
    val query_name: String,
    val trigger: String,
    val algorithm: String? = null,
    val threshold: Double,
    val candidates: Int = 0,
    val hits: Int = 0,
    val datasets_used: List<String> = emptyList(),
    val run_at: String,
)

@Serializable
data class TransactionDto(
    val id: Int,
    val customer_id: Int,
    val reference: String? = null,
    val direction: String,
    val method: String,
    val amount: Double,
    val currency: String,
    val amount_aed: Double? = null,
    val counterparty_name: String? = null,
    val counterparty_country: String? = null,
    val occurred_at: String,
    val recorded_by: String? = null,
    val created_at: String,
)

@Serializable
data class CaseNoteDto(
    val id: Int,
    val customer_id: Int,
    val author: String,
    val body: String,
    val created_at: String,
)

@Serializable
data class SignatureDto(
    val id: Int,
    val customer_id: Int,
    val purpose: String,
    val statement: String,
    val signer_name: String,
    val signer_role: String,
    val content_hash: String,
    val signed_by: String? = null,
    val signed_at: String,
)

@Serializable
data class AuditEntryDto(
    val id: Int,
    val actor: String,
    val action: String,
    val object_type: String? = null,
    val object_id: String? = null,
    val detail: JsonElement? = null,
    val created_at: String,
)

@Serializable
data class CustomerDetailResponse(
    val customer: CustomerRecordDto,
    val ubos: List<UboDto> = emptyList(),
    val risk: RiskAssessmentDto? = null,
    val risk_history: List<RiskAssessmentDto> = emptyList(),
    val screenings: List<ScreeningRecordDto> = emptyList(),
    val alerts: List<AlertDto> = emptyList(),
    val notes: List<CaseNoteDto> = emptyList(),
    val transactions: List<TransactionDto> = emptyList(),
    val transaction_alerts: List<TransactionAlertDto> = emptyList(),
    val signatures: List<SignatureDto> = emptyList(),
    val audit: List<AuditEntryDto> = emptyList(),
    val generated_at: String? = null,
)

@Serializable
data class UboIn(
    val person_name: String,
    val ownership_pct: Double? = null,
    val control_type: String = "ownership",
)

@Serializable
data class CustomerCreateRequest(
    val reference: String,
    val full_name: String,
    val customer_type: String = "natural",
    val name_arabic: String = "",
    val nationality: String = "",
    val birth_date: String = "",
    val gender: String = "",
    val sector: String = "other",
    val delivery_channel: String = "face_to_face",
    val cash_level: String = "non_cash",
    val jurisdiction_tier: String = "standard",
    val structure: String = "natural_person",
    val ubos: List<UboIn> = emptyList(),
)

@Serializable
data class CustomerCreateResponse(
    val customer_id: Int,
    val reference: String,
    val blocked: Boolean,
    val risk_rating: String,
    val risk_score: Double,
    val requires_edd: Boolean,
)

@Serializable
data class CloseCustomerResponse(val retention_until: String)

@Serializable
data class UboAddRequest(
    val person_name: String,
    val ownership_pct: Double? = null,
    val control_type: String = "ownership",
)

@Serializable
data class UboAddResponse(val ubo_id: Int, val hits: List<ScreenHitDto> = emptyList())

@Serializable
data class NoteRequest(val body: String)

@Serializable
data class NoteResponse(val note_id: Int)

@Serializable
data class TransactionRequest(
    val direction: String,
    val method: String,
    val amount: Double,
    val currency: String = "AED",
    val amount_aed: Double? = null,
    val counterparty_name: String = "",
    val counterparty_country: String = "",
    val occurred_at: String = "",
)

@Serializable
data class TriggeredRuleDto(val rule_key: String, val severity: String)

@Serializable
data class TransactionResponse(
    val transaction_id: Int,
    val triggered_rules: List<TriggeredRuleDto> = emptyList(),
)

@Serializable
data class SignatureRequest(
    val purpose: String,
    val statement: String,
    val signer_name: String,
    val signer_role: String = "customer",
)

@Serializable
data class SignatureResponse(val signature_id: Int)

@Serializable
data class PassportScanResponse(
    val full_name: String? = null,
    val name_arabic: String? = null,
    val nationality: String? = null,
    val birth_date: String? = null,
    val expiry_date: String? = null,
    val gender: String? = null,
    val id_number: String? = null,
    val id_type: String? = null,
    val authenticity: JsonElement? = null,
    val expiry_check: JsonElement? = null,
)
