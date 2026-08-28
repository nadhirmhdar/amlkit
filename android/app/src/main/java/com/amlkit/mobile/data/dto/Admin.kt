package com.amlkit.mobile.data.dto

import kotlinx.serialization.Serializable

@Serializable
data class OperatorRowDto(
    val id: Int,
    val name: String,
    val email: String,
    val role: String,
    val is_active: Int = 1,
)

@Serializable
data class OrgDto(val name: String, val slug: String)

@Serializable
data class AdminResponse(
    val org: OrgDto,
    val operators: List<OperatorRowDto> = emptyList(),
    val threshold: Double? = null,
    val default_threshold: Double,
    val sanctions: List<DatasetStalenessDto> = emptyList(),
)

@Serializable
data class ThresholdRequest(val threshold: Double? = null)

@Serializable
data class ThresholdResponse(val threshold: Double? = null)

@Serializable
data class PasswordResetRequest(val new_password: String)

@Serializable
data class OperatorCreateRequest(
    val name: String,
    val email: String,
    val password: String,
    val role: String = "officer",
)

@Serializable
data class OperatorCreateResponse(val operator_id: Int)

@Serializable
data class RefreshResultDto(
    val loaded: List<String> = emptyList(),
    val failures: List<String> = emptyList(),
    val orgs_screened: Int = 0,
    val new_alerts: Int = 0,
)

@Serializable
data class OkResponse(val ok: Boolean = true)

@Serializable
data class AuditResponse(val entries: List<AuditEntryDto> = emptyList())
