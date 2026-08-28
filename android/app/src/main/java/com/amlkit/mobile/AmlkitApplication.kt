package com.amlkit.mobile

import android.app.Application
import com.amlkit.mobile.data.AmlkitRepository
import com.amlkit.mobile.data.ApiClient
import com.amlkit.mobile.data.AuthTokenStore

/** Manual dependency container -- no DI framework. The dependency graph here
 * is small and static (one repository, one token store) and this project is
 * never compiled locally in development (no Android SDK in this sandbox;
 * see docs/google-play-steps.md), so a hand-written container that fails at
 * compile time rather than at annotation-processing time is the safer
 * choice until there's an actual reason to reach for Hilt. */
class AmlkitApplication : Application() {

    lateinit var tokenStore: AuthTokenStore
        private set
    lateinit var repository: AmlkitRepository
        private set

    override fun onCreate() {
        super.onCreate()
        tokenStore = AuthTokenStore(this)
        repository = AmlkitRepository(ApiClient.create(tokenStore), tokenStore)
    }
}
