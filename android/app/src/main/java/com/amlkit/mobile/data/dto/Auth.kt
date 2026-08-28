package com.amlkit.mobile.data.dto

import kotlinx.serialization.Serializable

@Serializable
data class OperatorDto(
    val operator_id: Int,
    val org_id: Int,
    val name: String,
    val role: String,
    val email: String,
)

@Serializable
data class AuthResponse(
    val token: String,
    val operator: OperatorDto,
)

@Serializable
data class LoginRequest(val email: String, val password: String)

@Serializable
data class RegisterOrgRequest(
    val org_name: String,
    val name: String,
    val email: String,
    val password: String,
)

@Serializable
data class SetupCheckResponse(val valid: Boolean, val org_name: String? = null)

@Serializable
data class SetupSubmitRequest(
    val token: String,
    val name: String,
    val email: String,
    val password: String,
)

@Serializable
data class MeResponse(val operator: OperatorDto)

/** Body of every non-2xx response from the API -- FastAPI's default HTTPException shape. */
@Serializable
data class ApiErrorBody(val detail: String? = null)
