import java.io.File

plugins {
    id("com.android.application") version "8.13.2" apply false
    id("org.jetbrains.kotlin.android") version "2.1.20" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.1.20" apply false
    id("org.jetbrains.kotlin.kapt") version "2.1.20" apply false
}

// Keep JVM test classpaths ASCII on Windows; sources remain in the workspace.
if (System.getProperty("os.name").startsWith("Windows")) {
    val output = File(System.getProperty("java.io.tmpdir"),
        "sms-relay-android-" + rootDir.absolutePath.hashCode().toUInt().toString(16))
    layout.buildDirectory.set(File(output, "root"))
    subprojects { layout.buildDirectory.set(File(output, name)) }
    println("SMS Relay build output: " + output.absolutePath)
}
