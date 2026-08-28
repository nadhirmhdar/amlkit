import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

// Release signing, read from android/local.properties (gitignored -- see
// docs/google-play-steps.md). Absent entirely in CI, which only runs
// assembleDebug/lintDebug and never touches this; a local `bundleRelease`
// without it fails with FileNotFoundException on a null storeFile rather
// than silently producing an unsigned/unpublishable bundle.
val localProperties = Properties().apply {
    val file = rootProject.file("local.properties")
    if (file.exists()) file.inputStream().use { load(it) }
}

android {
    namespace = "com.amlkit.mobile"
    // CHANGE BEFORE FIRST RELEASE: the applicationId is permanent once
    // published to Google Play -- pick the real reverse-domain id you want
    // to own before you upload the first AAB. See docs/google-play-steps.md.
    compileSdk = 35

    defaultConfig {
        applicationId = "com.amlkit.mobile"
        minSdk = 26
        targetSdk = 35
        // Overridable at build time: -PversionCode=2 -PversionName=1.0.1
        // (used by .github/workflows/android-release.yml, which dispatches
        // a real value per release; Play requires versionCode to strictly
        // increase between uploads, so the default here is only ever
        // correct for the very first release).
        versionCode = (project.findProperty("versionCode") as String?)?.toIntOrNull() ?: 1
        versionName = (project.findProperty("versionName") as String?) ?: "1.0.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        // Overridable at build time: -PapiBaseUrl=https://your-deployment.example.com/
        // Defaults to the Android emulator's alias for the host machine's
        // localhost, so a debug build talks to `python scripts/serve.py`
        // running on the same machine out of the box.
        val apiBaseUrl = (project.findProperty("apiBaseUrl") as String?)
            ?: "http://10.0.2.2:8000/"
        buildConfigField("String", "API_BASE_URL", "\"$apiBaseUrl\"")
    }

    signingConfigs {
        create("release") {
            val storeFilePath = localProperties.getProperty("RELEASE_STORE_FILE")
            if (storeFilePath != null) {
                storeFile = file(storeFilePath)
                storePassword = localProperties.getProperty("RELEASE_STORE_PASSWORD")
                keyAlias = localProperties.getProperty("RELEASE_KEY_ALIAS")
                keyPassword = localProperties.getProperty("RELEASE_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.getByName("release")
        }
        debug {
            isMinifyEnabled = false
            applicationIdSuffix = ".debug"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
        // Chips, some navigation-bar APIs, and a few Material3 overloads used
        // throughout ui/ are still marked @ExperimentalMaterial3Api at the
        // pinned BOM version -- one module-wide opt-in instead of annotating
        // every screen file individually.
        freeCompilerArgs += listOf("-opt-in=androidx.compose.material3.ExperimentalMaterial3Api")
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.security.crypto)
    implementation(libs.androidx.datastore.preferences)

    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    implementation(libs.androidx.material.icons.extended)
    debugImplementation(libs.androidx.ui.tooling)
    debugImplementation(libs.androidx.ui.test.manifest)

    implementation(libs.retrofit.core)
    implementation(libs.retrofit.kotlinx.serialization)
    implementation(libs.okhttp.core)
    implementation(libs.okhttp.logging.interceptor)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)

    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
}
