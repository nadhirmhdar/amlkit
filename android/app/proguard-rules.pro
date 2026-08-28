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
