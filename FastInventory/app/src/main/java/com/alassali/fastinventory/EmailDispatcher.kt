package com.alassali.fastinventory

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.widget.Toast
import androidx.core.content.FileProvider
import java.io.BufferedReader
import java.io.File
import java.io.FileInputStream
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.Socket
import javax.net.ssl.SSLSocketFactory

object EmailDispatcher {

    interface DispatchCallback {
        fun onSuccess()
        fun onFailure(error: String)
    }

    /**
     * Sends the report using the standard Android Share/Email Intent (Gmail, Outlook, WhatsApp, etc.).
     */
    fun sendReportViaIntent(
        context: Context,
        subject: String,
        bodyText: String,
        files: List<File>,
        targetEmail: String = ""
    ) {
        try {
            val uris = ArrayList<Uri>()
            for (f in files) {
                if (f.exists()) {
                    val u = FileProvider.getUriForFile(
                        context,
                        "${context.packageName}.fileprovider",
                        f
                    )
                    uris.add(u)
                }
            }

            val intent = if (uris.size > 1) {
                Intent(Intent.ACTION_SEND_MULTIPLE).apply {
                    type = "application/octet-stream"
                    putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris)
                }
            } else {
                Intent(Intent.ACTION_SEND).apply {
                    type = "application/octet-stream"
                    if (uris.isNotEmpty()) {
                        putExtra(Intent.EXTRA_STREAM, uris[0])
                    }
                }
            }

            if (targetEmail.isNotBlank()) {
                val recipients = targetEmail.split(",").map { it.trim() }.toTypedArray()
                intent.putExtra(Intent.EXTRA_EMAIL, recipients)
            }

            intent.putExtra(Intent.EXTRA_SUBJECT, subject)
            intent.putExtra(Intent.EXTRA_TEXT, bodyText)
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)

            val chooser = Intent.createChooser(intent, "إرسال تقرير الجرد عبر:")
            chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(chooser)
        } catch (e: Exception) {
            e.printStackTrace()
            Toast.makeText(context, "خطأ في مشاركة التقرير: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }

    /**
     * Optional Silent Background SMTP Dispatcher.
     * Uses standard Java socket protocol with STARTTLS and Base64 attachment encoding.
     */
    fun sendReportViaSmtpAsync(
        context: Context,
        subject: String,
        bodyText: String,
        files: List<File>,
        callback: DispatchCallback
    ) {
        val settings = SettingsManager(context)
        val host = settings.getSmtpHost()
        val port = settings.getSmtpPort()
        val user = settings.getSmtpUser()
        val pass = settings.getSmtpPassword()
        val recipient = settings.getTargetEmail()

        if (recipient.isBlank() || user.isBlank() || pass.isBlank()) {
            callback.onFailure("بيانات البريد الإلكتروني أو SMTP غير مكتملة في الإعدادات.")
            return
        }

        Thread {
            try {
                // Connect via socket
                val socket = if (settings.isSmtpSsl() && port == 465) {
                    SSLSocketFactory.getDefault().createSocket(host, port)
                } else {
                    Socket(host, port)
                }
                socket.soTimeout = 25000

                val reader = BufferedReader(InputStreamReader(socket.getInputStream()))
                val writer = OutputStreamWriter(socket.getOutputStream(), "UTF-8")

                fun readResponse(): String {
                    val line = reader.readLine() ?: ""
                    return line
                }

                fun sendCmd(cmd: String): String {
                    writer.write(cmd + "\r\n")
                    writer.flush()
                    return readResponse()
                }

                // Initial greeting
                readResponse()
                sendCmd("EHLO FastInventory")

                // STARTTLS if on port 587
                var secureSocket = socket
                var sReader = reader
                var sWriter = writer

                if (port == 587) {
                    sendCmd("STARTTLS")
                    val sslFactory = SSLSocketFactory.getDefault() as SSLSocketFactory
                    secureSocket = sslFactory.createSocket(socket, host, port, true)
                    sReader = BufferedReader(InputStreamReader(secureSocket.getInputStream()))
                    sWriter = OutputStreamWriter(secureSocket.getOutputStream(), "UTF-8")

                    sWriter.write("EHLO FastInventory\r\n")
                    sWriter.flush()
                    sReader.readLine()
                }

                // Auth Login
                sWriter.write("AUTH LOGIN\r\n")
                sWriter.flush()
                sReader.readLine()

                val b64User = Base64.encodeToString(user.toByteArray(), Base64.NO_WRAP)
                sWriter.write("$b64User\r\n")
                sWriter.flush()
                sReader.readLine()

                val b64Pass = Base64.encodeToString(pass.toByteArray(), Base64.NO_WRAP)
                sWriter.write("$b64Pass\r\n")
                sWriter.flush()
                val authRes = sReader.readLine() ?: ""

                if (!authRes.startsWith("235")) {
                    throw IllegalStateException("فشل تسجيل الدخول بخادم SMTP: $authRes")
                }

                // Mail From & Rcpt To
                sWriter.write("MAIL FROM:<$user>\r\n")
                sWriter.flush()
                sReader.readLine()

                val recipients = recipient.split(",").map { it.trim() }
                for (r in recipients) {
                    sWriter.write("RCPT TO:<$r>\r\n")
                    sWriter.flush()
                    sReader.readLine()
                }

                sWriter.write("DATA\r\n")
                sWriter.flush()
                sReader.readLine()

                // MIME Multipart message
                val boundary = "====Boundary_FastInventory_${System.currentTimeMillis()}===="
                val rawSubject = "=?UTF-8?B?" + Base64.encodeToString(subject.toByteArray(), Base64.NO_WRAP) + "?="

                sWriter.write("From: FastInventory <$user>\r\n")
                sWriter.write("To: $recipient\r\n")
                sWriter.write("Subject: $rawSubject\r\n")
                sWriter.write("MIME-Version: 1.0\r\n")
                sWriter.write("Content-Type: multipart/mixed; boundary=\"$boundary\"\r\n\r\n")

                // Body text part
                sWriter.write("--$boundary\r\n")
                sWriter.write("Content-Type: text/plain; charset=UTF-8\r\n")
                sWriter.write("Content-Transfer-Encoding: base64\r\n\r\n")
                sWriter.write(Base64.encodeToString(bodyText.toByteArray(), Base64.DEFAULT) + "\r\n")

                // Attachment files
                for (f in files) {
                    if (!f.exists()) continue
                    val bytes = FileInputStream(f).use { it.readBytes() }
                    val b64Content = Base64.encodeToString(bytes, Base64.DEFAULT)
                    val rawFilename = "=?UTF-8?B?" + Base64.encodeToString(f.name.toByteArray(), Base64.NO_WRAP) + "?="

                    sWriter.write("--$boundary\r\n")
                    sWriter.write("Content-Type: application/octet-stream; name=\"$rawFilename\"\r\n")
                    sWriter.write("Content-Transfer-Encoding: base64\r\n")
                    sWriter.write("Content-Disposition: attachment; filename=\"$rawFilename\"\r\n\r\n")
                    sWriter.write(b64Content + "\r\n")
                }

                sWriter.write("--$boundary--\r\n")
                sWriter.write(".\r\n")
                sWriter.flush()
                sReader.readLine()

                sWriter.write("QUIT\r\n")
                sWriter.flush()
                secureSocket.close()

                Handler(Looper.getMainLooper()).post {
                    callback.onSuccess()
                }
            } catch (e: Exception) {
                e.printStackTrace()
                Handler(Looper.getMainLooper()).post {
                    callback.onFailure(e.message ?: e.javaClass.simpleName)
                }
            }
        }.start()
    }
}
