package com.amlkit.mobile.data

import com.amlkit.mobile.data.dto.AdminResponse
import com.amlkit.mobile.data.dto.AlertAssignRequest
import com.amlkit.mobile.data.dto.AlertConfirmRequest
import com.amlkit.mobile.data.dto.AlertDispositionRequest
import com.amlkit.mobile.data.dto.AlertsResponse
import com.amlkit.mobile.data.dto.ApiErrorBody
import com.amlkit.mobile.data.dto.AuditResponse
import com.amlkit.mobile.data.dto.AuthResponse
import com.amlkit.mobile.data.dto.CloseCustomerResponse
import com.amlkit.mobile.data.dto.CustomerCreateRequest
import com.amlkit.mobile.data.dto.CustomerCreateResponse
import com.amlkit.mobile.data.dto.CustomerDetailResponse
import com.amlkit.mobile.data.dto.CustomersListResponse
import com.amlkit.mobile.data.dto.DashboardResponse
import com.amlkit.mobile.data.dto.LoginRequest
import com.amlkit.mobile.data.dto.NoteRequest
import com.amlkit.mobile.data.dto.NoteResponse
import com.amlkit.mobile.data.dto.OkResponse
import com.amlkit.mobile.data.dto.OperatorCreateRequest
import com.amlkit.mobile.data.dto.OperatorCreateResponse
import com.amlkit.mobile.data.dto.PassportScanResponse
import com.amlkit.mobile.data.dto.PasswordResetRequest
import com.amlkit.mobile.data.dto.ReasonCodesResponse
import com.amlkit.mobile.data.dto.RefreshResultDto
import com.amlkit.mobile.data.dto.RegisterOrgRequest
import com.amlkit.mobile.data.dto.ReportDetailResponse
import com.amlkit.mobile.data.dto.ReportSaveRequest
import com.amlkit.mobile.data.dto.ReportSaveResponse
import com.amlkit.mobile.data.dto.ReportsResponse
import com.amlkit.mobile.data.dto.ReviewOutcomeDto
import com.amlkit.mobile.data.dto.ScreenRequest
import com.amlkit.mobile.data.dto.ScreenResponse
import com.amlkit.mobile.data.dto.SignatureRequest
import com.amlkit.mobile.data.dto.SignatureResponse
import com.amlkit.mobile.data.dto.ThresholdRequest
import com.amlkit.mobile.data.dto.ThresholdResponse
import com.amlkit.mobile.data.dto.TransactionRequest
import com.amlkit.mobile.data.dto.TransactionResponse
import com.amlkit.mobile.data.dto.TxnAlertDispositionRequest
import com.amlkit.mobile.data.dto.UboAddRequest
import com.amlkit.mobile.data.dto.UboAddResponse
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import retrofit2.Response
import java.io.File
import java.io.IOException

/** One place all screens go through to reach the server. Every call returns
 * [ApiResult] rather than throwing -- ViewModels branch on Success/Failure
 * instead of wrapping every call site in try/catch. */
class AmlkitRepository(
    private val api: AmlkitApi,
    private val tokenStore: AuthTokenStore,
) {
    private val errorJson = Json { ignoreUnknownKeys = true }

    private suspend fun <T> safeApiCall(block: suspend () -> Response<T>): ApiResult<T> {
        return try {
            val response = block()
            if (response.isSuccessful) {
                val body = response.body()
                if (body != null) {
                    ApiResult.Success(body)
                } else {
                    ApiResult.Failure(response.code(), "Server returned an empty response.")
                }
            } else {
                if (response.code() == 401) tokenStore.clear()
                val detail = response.errorBody()?.string()?.let {
                    runCatching { errorJson.decodeFromString(ApiErrorBody.serializer(), it).detail }
                        .getOrNull()
                }
                ApiResult.Failure(response.code(), detail ?: "Request failed (${response.code()}).")
            }
        } catch (e: IOException) {
            ApiResult.Failure(null, "Couldn't reach the server. Check your connection and the server address in Settings.")
        } catch (e: Exception) {
            ApiResult.Failure(null, e.message ?: "Unexpected error.")
        }
    }

    // ------------------------------------------------------------------ auth
    suspend fun login(email: String, password: String): ApiResult<AuthResponse> =
        safeApiCall { api.login(LoginRequest(email, password)) }
            .also { if (it is ApiResult.Success) persistSession(it.data) }

    suspend fun registerOrganization(orgName: String, name: String, email: String, password: String): ApiResult<AuthResponse> =
        safeApiCall { api.registerOrganization(RegisterOrgRequest(orgName, name, email, password)) }
            .also { if (it is ApiResult.Success) persistSession(it.data) }

    suspend fun logout(): ApiResult<OkResponse> {
        val result = safeApiCall { api.logout() }
        tokenStore.clear()
        return result
    }

    private fun persistSession(auth: AuthResponse) {
        tokenStore.save(auth.token, auth.operator.name, auth.operator.role)
    }

    // ------------------------------------------------------------- dashboard
    suspend fun dashboard(): ApiResult<DashboardResponse> = safeApiCall { api.dashboard() }

    suspend fun reasonCodes(): ApiResult<ReasonCodesResponse> = safeApiCall { api.reasonCodes() }

    // --------------------------------------------------------------- screen
    suspend fun screen(name: String, country: String = "", birthDate: String = "", gender: String = ""): ApiResult<ScreenResponse> =
        safeApiCall { api.screen(ScreenRequest(name, country, birthDate, gender)) }

    // ----------------------------------------------------------- customers
    suspend fun customers(): ApiResult<CustomersListResponse> = safeApiCall { api.customers() }

    suspend fun createCustomer(body: CustomerCreateRequest): ApiResult<CustomerCreateResponse> =
        safeApiCall { api.createCustomer(body) }

    suspend fun scanPassport(imageFile: File): ApiResult<PassportScanResponse> {
        val part = MultipartBody.Part.createFormData(
            "passport_file", imageFile.name, imageFile.asRequestBody("image/*".toMediaTypeOrNull()),
        )
        return safeApiCall { api.scanPassport(part) }
    }

    suspend fun customerDetail(id: Int): ApiResult<CustomerDetailResponse> = safeApiCall { api.customerDetail(id) }

    suspend fun customerEvidence(id: Int): ApiResult<CustomerDetailResponse> = safeApiCall { api.customerEvidence(id) }

    suspend fun closeCustomer(id: Int): ApiResult<CloseCustomerResponse> = safeApiCall { api.closeCustomer(id) }

    suspend fun addUbo(id: Int, body: UboAddRequest): ApiResult<UboAddResponse> = safeApiCall { api.addUbo(id, body) }

    suspend fun addNote(id: Int, body: String): ApiResult<NoteResponse> = safeApiCall { api.addNote(id, NoteRequest(body)) }

    suspend fun addTransaction(id: Int, body: TransactionRequest): ApiResult<TransactionResponse> =
        safeApiCall { api.addTransaction(id, body) }

    suspend fun dispositionTransactionAlert(id: Int, status: String, note: String): ApiResult<OkResponse> =
        safeApiCall { api.dispositionTransactionAlert(id, TxnAlertDispositionRequest(status, note)) }

    suspend fun addSignature(id: Int, body: SignatureRequest): ApiResult<SignatureResponse> =
        safeApiCall { api.addSignature(id, body) }

    // --------------------------------------------------------------- alerts
    suspend fun alerts(status: String = "open"): ApiResult<AlertsResponse> = safeApiCall { api.alerts(status) }

    suspend fun dispositionAlert(id: Int, status: String, reasonCode: String, narrative: String): ApiResult<ReviewOutcomeDto> =
        safeApiCall { api.dispositionAlert(id, AlertDispositionRequest(status, reasonCode, narrative)) }

    suspend fun confirmAlert(id: Int, agree: Boolean, narrative: String): ApiResult<ReviewOutcomeDto> =
        safeApiCall { api.confirmAlert(id, AlertConfirmRequest(agree, narrative)) }

    suspend fun assignAlert(id: Int, operator: String?): ApiResult<OkResponse> =
        safeApiCall { api.assignAlert(id, AlertAssignRequest(operator)) }

    // ---------------------------------------------------------------- audit
    suspend fun audit(): ApiResult<AuditResponse> = safeApiCall { api.audit() }

    // ---------------------------------------------------------------- admin
    suspend fun admin(): ApiResult<AdminResponse> = safeApiCall { api.admin() }

    suspend fun setThreshold(threshold: Double?): ApiResult<ThresholdResponse> =
        safeApiCall { api.setThreshold(ThresholdRequest(threshold)) }

    suspend fun resetOperatorPassword(id: Int, newPassword: String): ApiResult<OkResponse> =
        safeApiCall { api.resetOperatorPassword(id, PasswordResetRequest(newPassword)) }

    suspend fun createOperator(name: String, email: String, password: String, role: String): ApiResult<OperatorCreateResponse> =
        safeApiCall { api.createOperator(OperatorCreateRequest(name, email, password, role)) }

    suspend fun deactivateOperator(id: Int): ApiResult<OkResponse> = safeApiCall { api.deactivateOperator(id) }

    suspend fun refreshSanctions(): ApiResult<RefreshResultDto> = safeApiCall { api.refreshSanctions() }

    // -------------------------------------------------------------- reports
    suspend fun reports(): ApiResult<ReportsResponse> = safeApiCall { api.reports() }

    suspend fun reportDetail(id: Int): ApiResult<ReportDetailResponse> = safeApiCall { api.reportDetail(id) }

    suspend fun saveReport(body: ReportSaveRequest): ApiResult<ReportSaveResponse> = safeApiCall { api.saveReport(body) }

    suspend fun submitReport(id: Int): ApiResult<OkResponse> = safeApiCall { api.submitReport(id) }

    /** The export endpoint returns raw XML, not JSON, so it can't go through
     * [safeApiCall]'s body decoding -- this reads the ResponseBody directly. */
    suspend fun exportReportXml(id: Int): ApiResult<String> {
        return try {
            val response = api.exportReport(id)
            if (response.isSuccessful) {
                val body = response.body()
                if (body != null) ApiResult.Success(body.string()) else ApiResult.Failure(response.code(), "Empty export.")
            } else {
                if (response.code() == 401) tokenStore.clear()
                ApiResult.Failure(response.code(), "Export failed (${response.code()}).")
            }
        } catch (e: IOException) {
            ApiResult.Failure(null, "Couldn't reach the server.")
        }
    }
}
