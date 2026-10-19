package com.alassali.fastinventory

import android.app.Activity
import android.app.AlertDialog
import android.app.ProgressDialog
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL

object AppUpdateManager {

    private const val APP_KEY = "FastInventory"

    fun checkForUpdate(activity: Activity, odooClient: OdooClient, currentVersionName: String) {
        Thread {
            try {
                val raw = odooClient.fetchRawParam("app.updates_manifest") ?: return@Thread
                val manifest = JSONObject(raw)
                val appInfo = manifest.optJSONObject(APP_KEY) ?: return@Thread

                val latestVer = appInfo.optString("latest_version", "")
                val dlUrl = appInfo.optString("download_url", "")
                val notes = appInfo.optString("release_notes", "• تحسينات عامة في الأداء والسرعة وتوافق البيانات.")
                val isMandatory = appInfo.optBoolean("is_mandatory", false)

                if (dlUrl.isBlank() || latestVer.isBlank()) return@Thread

                if (isNewer(latestVer, currentVersionName)) {
                    activity.runOnUiThread {
                        showUpdateDialog(activity, latestVer, currentVersionName, dlUrl, notes, isMandatory)
                    }
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }.start()
    }

    private fun isNewer(remote: String, local: String): Boolean {
        try {
            val rParts = remote.trim().removePrefix("v").removePrefix("V").split(".").map { it.toIntOrNull() ?: 0 }
            val lParts = local.trim().removePrefix("v").removePrefix("V").split(".").map { it.toIntOrNull() ?: 0 }
            val maxLen = maxOf(rParts.size, lParts.size)
            for (i in 0 until maxLen) {
                val r = rParts.getOrElse(i) { 0 }
                val l = lParts.getOrElse(i) { 0 }
                if (r > l) return true
                if (r < l) return false
            }
            return false
        } catch (e: Exception) {
            return false
        }
    }

    private fun showUpdateDialog(
        activity: Activity,
        latestVer: String,
        currentVer: String,
        dlUrl: String,
        notes: String,
        isMandatory: Boolean
    ) {
        val builder = AlertDialog.Builder(activity)
            .setTitle("🚀 يتوفر تحديث جديد لـ FastInventory: v$latestVer")
            .setMessage("الإصدار الحالي: v$currentVer\n\nما الجديد في هذا التحديث:\n$notes")
            .setCancelable(!isMandatory)
            .setPositiveButton("🚀 تحديث الآن") { _, _ ->
                downloadAndInstallApk(activity, dlUrl, latestVer)
            }

        if (!isMandatory) {
            builder.setNegativeButton("تذكيري لاحقاً", null)
        }

        builder.show()
    }

    private fun downloadAndInstallApk(activity: Activity, dlUrl: String, version: String) {
        @Suppress("DEPRECATION")
        val progressDialog = ProgressDialog(activity).apply {
            setTitle("جاري تنزيل التحديث...")
            setMessage("يرجى الانتظار أثناء تحميل ملف التحديث...")
            setProgressStyle(ProgressDialog.STYLE_HORIZONTAL)
            max = 100
            setCancelable(false)
            show()
        }

        Thread {
            try {
                val url = URL(dlUrl)
                val conn = url.openConnection() as HttpURLConnection
                conn.setRequestProperty("User-Agent", "FastInventory-Android/1.00")
                conn.connectTimeout = 20000
                conn.readTimeout = 60000
                conn.connect()

                val fileLength = conn.contentLength
                val apkDir = File(activity.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS), "updates")
                if (!apkDir.exists()) apkDir.mkdirs()
                val outputFile = File(apkDir, "FastInventory_v$version.apk")

                conn.inputStream.use { input ->
                    FileOutputStream(outputFile).use { output ->
                        val data = ByteArray(4096)
                        var total: Long = 0
                        var count: Int
                        while (input.read(data).also { count = it } != -1) {
                            total += count
                            if (fileLength > 0) {
                                val progress = (total * 100 / fileLength).toInt()
                                activity.runOnUiThread { progressDialog.progress = progress }
                            }
                            output.write(data, 0, count)
                        }
                    }
                }

                activity.runOnUiThread {
                    progressDialog.dismiss()
                    promptInstallApk(activity, outputFile)
                }
            } catch (e: Exception) {
                activity.runOnUiThread {
                    progressDialog.dismiss()
                    AlertDialog.Builder(activity)
                        .setTitle("خطأ في التنزيل")
                        .setMessage("تعذر تنزيل ملف التحديث: ${e.message}")
                        .setPositiveButton("موافق", null)
                        .show()
                }
            }
        }.start()
    }

    private fun promptInstallApk(context: Context, apkFile: File) {
        try {
            val contentUri: Uri = FileProvider.getUriForFile(
                context,
                "${context.packageName}.fileprovider",
                apkFile
            )

            val installIntent = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(contentUri, "application/vnd.android.package-archive")
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION
            }
            context.startActivity(installIntent)
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }
}
