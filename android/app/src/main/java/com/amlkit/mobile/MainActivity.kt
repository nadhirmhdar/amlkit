package com.amlkit.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.amlkit.mobile.ui.nav.AmlkitApp
import com.amlkit.mobile.ui.theme.AmlkitTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val app = application as AmlkitApplication
        setContent {
            AmlkitTheme {
                AmlkitApp(repository = app.repository, tokenStore = app.tokenStore)
            }
        }
    }
}
