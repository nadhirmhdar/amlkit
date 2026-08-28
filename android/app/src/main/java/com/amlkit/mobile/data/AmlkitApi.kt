package com.amlkit.mobile.data

import com.amlkit.mobile.data.dto.AdminResponse
import com.amlkit.mobile.data.dto.AlertAssignRequest
import com.amlkit.mobile.data.dto.AlertConfirmRequest
import com.amlkit.mobile.data.dto.AlertDispositionRequest
import com.amlkit.mobile.data.dto.AlertsResponse
import com.amlkit.mobile.data.dto.AuditResponse
import com.amlkit.mobile.data.dto.AuthResponse
import com.amlkit.mobile.data.dto.CloseCustomerResponse
import com.amlkit.mobile.data.dto.CustomerCreateRequest
import com.amlkit.mobile.data.dto.CustomerCreateResponse
import com.amlkit.mobile.data.dto.CustomerDetailResponse
import com.amlkit.mobile.data.dto.CustomersListResponse
import com.amlkit.mobile.data.dto.DashboardResponse
import com.amlkit.mobile.data.dto.DatasetsResponse
import com.amlkit.mobile.data.dto.LoginRequest
import com.amlkit.mobile.data.dto.MeResponse
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
import com.amlkit.mobile.data.dto.SetupCheckResponse
import com.amlkit.mobile.data.dto.SetupSubmitRequest
import com.amlkit.mobile.data.dto.SignatureRequest
import com.amlkit.mobile.data.dto.SignatureResponse
import com.amlkit.mobile.data.dto.ThresholdRequest
import com.amlkit.mobile.data.dto.ThresholdResponse
import com.amlkit.mobile.data.dto.TransactionRequest
import com.amlkit.mobile.data.dto.TransactionResponse
import com.amlkit.mobile.data.dto.TxnAlertDispositionRequest
import com.amlkit.mobile.data.dto.UboAddRequest
import com.amlkit.mobile.data.dto.UboAddResponse
import okhttp3.MultipartBody
import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

/** Every call this app makes to amlkit's JSON API (`amlkit/api/mobile.py`).
 * Auth is not a parameter here -- the bearer token is attached by
 * [AuthInterceptor] on every request that carries one. */
interface AmlkitApi {

    // ------------------------------------------------------------------ auth
    @POST("api/v1/auth/login")
    suspend fun login(@Body body: LoginRequest): Response<AuthResponse>

    @POST("api/v1/auth/logout")
    suspend fun logout(): Response<OkResponse>

    @GET("api/v1/auth/me")
    suspend fun me(): Response<MeResponse>

    @POST("api/v1/auth/register-organization")
    suspend fun registerOrganization(@Body body: RegisterOrgRequest): Response<AuthResponse>

    @GET("api/v1/auth/setup")
    suspend fun setupCheck(@Query("token") token: String): Response<SetupCheckResponse>

    @POST("api/v1/auth/setup")
    suspend fun setupSubmit(@Body body: SetupSubmitRequest): Response<AuthResponse>

    // ------------------------------------------------------------- dashboard
    @GET("api/v1/dashboard")
    suspend fun dashboard(): Response<DashboardResponse>

    @GET("api/v1/datasets")
    suspend fun datasets(): Response<DatasetsResponse>

    @GET("api/v1/reason-codes")
    suspend fun reasonCodes(): Response<ReasonCodesResponse>

    // --------------------------------------------------------------- screen
    @POST("api/v1/screen")
    suspend fun screen(@Body body: ScreenRequest): Response<ScreenResponse>

    // ----------------------------------------------------------- customers
    @GET("api/v1/customers")
    suspend fun customers(): Response<CustomersListResponse>

    @POST("api/v1/customers")
    suspend fun createCustomer(@Body body: CustomerCreateRequest): Response<CustomerCreateResponse>

    @Multipart
    @POST("api/v1/customers/scan-passport")
    suspend fun scanPassport(@Part file: MultipartBody.Part): Response<PassportScanResponse>

    @GET("api/v1/customers/{id}")
    suspend fun customerDetail(@Path("id") id: Int): Response<CustomerDetailResponse>

    @GET("api/v1/customers/{id}/evidence")
    suspend fun customerEvidence(@Path("id") id: Int): Response<CustomerDetailResponse>

    @POST("api/v1/customers/{id}/close")
    suspend fun closeCustomer(@Path("id") id: Int): Response<CloseCustomerResponse>

    @POST("api/v1/customers/{id}/ubo")
    suspend fun addUbo(@Path("id") id: Int, @Body body: UboAddRequest): Response<UboAddResponse>

    @POST("api/v1/customers/{id}/notes")
    suspend fun addNote(@Path("id") id: Int, @Body body: NoteRequest): Response<NoteResponse>

    @POST("api/v1/customers/{id}/transactions")
    suspend fun addTransaction(@Path("id") id: Int, @Body body: TransactionRequest): Response<TransactionResponse>

    @POST("api/v1/transaction-alerts/{id}/disposition")
    suspend fun dispositionTransactionAlert(
        @Path("id") id: Int,
        @Body body: TxnAlertDispositionRequest,
    ): Response<OkResponse>

    @POST("api/v1/customers/{id}/signatures")
    suspend fun addSignature(@Path("id") id: Int, @Body body: SignatureRequest): Response<SignatureResponse>

    // --------------------------------------------------------------- alerts
    @GET("api/v1/alerts")
    suspend fun alerts(@Query("status") status: String = "open"): Response<AlertsResponse>

    @POST("api/v1/alerts/{id}/disposition")
    suspend fun dispositionAlert(
        @Path("id") id: Int,
        @Body body: AlertDispositionRequest,
    ): Response<ReviewOutcomeDto>

    @POST("api/v1/alerts/{id}/confirm")
    suspend fun confirmAlert(@Path("id") id: Int, @Body body: AlertConfirmRequest): Response<ReviewOutcomeDto>

    @POST("api/v1/alerts/{id}/assign")
    suspend fun assignAlert(@Path("id") id: Int, @Body body: AlertAssignRequest): Response<OkResponse>

    @GET("api/v1/alerts.csv")
    suspend fun alertsCsv(@Query("status") status: String = "all"): Response<ResponseBody>

    @GET("api/v1/customers.csv")
    suspend fun customersCsv(): Response<ResponseBody>

    // ---------------------------------------------------------------- audit
    @GET("api/v1/audit")
    suspend fun audit(): Response<AuditResponse>

    // ---------------------------------------------------------------- admin
    @GET("api/v1/admin")
    suspend fun admin(): Response<AdminResponse>

    @POST("api/v1/admin/threshold")
    suspend fun setThreshold(@Body body: ThresholdRequest): Response<ThresholdResponse>

    @POST("api/v1/admin/operators/{id}/reset-password")
    suspend fun resetOperatorPassword(
        @Path("id") id: Int,
        @Body body: PasswordResetRequest,
    ): Response<OkResponse>

    @POST("api/v1/admin/operators")
    suspend fun createOperator(@Body body: OperatorCreateRequest): Response<OperatorCreateResponse>

    @POST("api/v1/admin/operators/{id}/deactivate")
    suspend fun deactivateOperator(@Path("id") id: Int): Response<OkResponse>

    @POST("api/v1/admin/refresh")
    suspend fun refreshSanctions(): Response<RefreshResultDto>

    // -------------------------------------------------------------- reports
    @GET("api/v1/reports")
    suspend fun reports(): Response<ReportsResponse>

    @GET("api/v1/reports/{id}")
    suspend fun reportDetail(@Path("id") id: Int): Response<ReportDetailResponse>

    @POST("api/v1/reports")
    suspend fun saveReport(@Body body: ReportSaveRequest): Response<ReportSaveResponse>

    @POST("api/v1/reports/{id}/submit")
    suspend fun submitReport(@Path("id") id: Int): Response<OkResponse>

    @GET("api/v1/reports/{id}/export")
    suspend fun exportReport(@Path("id") id: Int): Response<ResponseBody>
}
