# kotlinx.serialization keeps its generated serializers reflectively.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt
-keepclassmembers class kotlinx.serialization.json.** {
    *** Companion;
}
-keepclasseswithmembers class kotlinx.serialization.json.** {
    kotlinx.serialization.KSerializer serializer(...);
}
-keep,includedescriptorclasses class com.amlkit.mobile.**$$serializer { *; }
-keepclassmembers class com.amlkit.mobile.** {
    *** Companion;
}
-keepclasseswithmembers class com.amlkit.mobile.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# androidx.security:security-crypto (used by AuthTokenStore for
# EncryptedSharedPreferences) pulls in Google Tink, whose compiled classes
# carry references to error-prone's compile-time-only annotations
# (@CanIgnoreReturnValue, @CheckReturnValue, @Immutable, @RestrictedApi).
# Nothing calls them at runtime, but R8 in full mode treats an unresolvable
# referenced class as a hard build error rather than a warning, so this
# needs an explicit -dontwarn instead of being silently fine.
-dontwarn com.google.errorprone.annotations.**
