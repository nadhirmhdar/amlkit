package com.amlkit.mobile.data.dto

import kotlinx.serialization.Serializable

@Serializable
data class ReportListItemDto(
    val id: Int,
    val report_type: String,
    val reference: String? = null,
    val status: String,
    val created_at: String,
    val submitted_at: String? = null,
    val customer_name: String? = null,
)

@Serializable
data class ReportsResponse(val reports: List<ReportListItemDto> = emptyList())

@Serializable
data class ReportPayloadDto(
    val customer_id: Int? = null,
    val customer_type: String? = null,
    val report_type: String? = null,
    val reporting_entity_name: String? = null,
    val entity_reference: String? = null,
    val reporter_name: String? = null,
    val reporter_email: String? = null,
    val first_name: String? = null,
    val last_name: String? = null,
    val nationality: String? = null,
    val birth_date: String? = null,
    val gender: String? = null,
    val id_type: String? = null,
    val id_number: String? = null,
    val amount: Double? = null,
    val transaction_type: String? = null,
    val transaction_date: String? = null,
    val source_account: String? = null,
    val destination_account: String? = null,
    val reason_description: String? = null,
    val action_taken: String? = null,
    val evidence_pack_attached: Boolean = false,
)

@Serializable
data class ReportDetailResponse(
    val id: Int,
    val org_id: Int? = null,
    val customer_id: Int? = null,
    val alert_id: Int? = null,
    val report_type: String,
    val reference: String? = null,
    val status: String,
    val created_at: String,
    val submitted_at: String? = null,
    val customer_name: String? = null,
    val payload: ReportPayloadDto = ReportPayloadDto(),
)

@Serializable
data class ReportSaveRequest(
    val customer_id: Int,
    val report_type: String,
    val reporting_entity_name: String,
    val entity_reference: String,
    val reporter_name: String,
    val reporter_email: String,
    val first_name: String,
    val last_name: String = "",
    val nationality: String = "AE",
    val birth_date: String = "",
    val gender: String = "",
    val id_type: String = "",
    val id_number: String = "",
    val amount: Double? = null,
    val transaction_type: String = "",
    val transaction_date: String = "",
    val source_account: String = "",
    val destination_account: String = "",
    val reason_description: String = "",
    val action_taken: String = "",
    val evidence_pack_attached: Boolean = false,
    val report_id: Int? = null,
)

@Serializable
data class ReportSaveResponse(val report_id: Int)
