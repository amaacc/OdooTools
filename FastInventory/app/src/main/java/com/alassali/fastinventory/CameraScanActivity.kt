package com.alassali.fastinventory

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.util.Log
import android.view.View
import android.view.animation.Animation
import android.view.animation.TranslateAnimation
import android.widget.Button
import android.widget.ImageButton
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import com.google.mlkit.vision.barcode.BarcodeScanner
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import java.util.Locale
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * Continuous Stream Camera Scanner (الجرد المستمر بالكاميرا).
 * - Stays active and open continuously.
 * - Detects barcodes rapidly with ML Kit.
 * - Records known and unknown products instantly (+1 / carton qty).
 * - Debounces repeated detections to allow continuous rapid sweep scanning.
 * - Live HUD shows counted units and session totals in real time.
 */
class CameraScanActivity : AppCompatActivity() {

    private lateinit var cameraPreviewView: PreviewView
    private lateinit var btnFinishScan: Button
    private lateinit var btnToggleTorch: ImageButton
    private lateinit var txtLiveSummary: TextView
    private lateinit var laserLine: View

    private lateinit var badgeHudPackaging: TextView
    private lateinit var txtHudBarcode: TextView
    private lateinit var txtHudNameAr: TextView
    private lateinit var txtHudStatus: TextView
    private lateinit var txtHudCountInZone: TextView

    private lateinit var sessionManager: SessionManager
    private var camera: Camera? = null
    private var isTorchOn = false
    private lateinit var cameraExecutor: ExecutorService
    private var barcodeScanner: BarcodeScanner? = null

    private var toneGen: ToneGenerator? = null

    private var lastScannedBarcode: String? = null
    private var lastScannedTime: Long = 0L

    companion object {
        const val EXTRA_SCANNED_BARCODE = "scanned_barcode"
        private const val TAG = "CameraScanActivity"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_camera_scan)

        sessionManager = SessionManager(this)

        cameraPreviewView = findViewById(R.id.cameraPreviewView)
        btnFinishScan = findViewById(R.id.btnFinishScan)
        btnToggleTorch = findViewById(R.id.btnToggleTorch)
        txtLiveSummary = findViewById(R.id.txtLiveSummary)
        laserLine = findViewById(R.id.laserLine)

        badgeHudPackaging = findViewById(R.id.badgeHudPackaging)
        txtHudBarcode = findViewById(R.id.txtHudBarcode)
        txtHudNameAr = findViewById(R.id.txtHudNameAr)
        txtHudStatus = findViewById(R.id.txtHudStatus)
        txtHudCountInZone = findViewById(R.id.txtHudCountInZone)

        cameraExecutor = Executors.newSingleThreadExecutor()

        try {
            toneGen = ToneGenerator(AudioManager.STREAM_MUSIC, 95)
        } catch (e: Exception) {
            Log.e(TAG, "ToneGenerator error: ${e.message}")
        }

        val options = BarcodeScannerOptions.Builder()
            .setBarcodeFormats(
                Barcode.FORMAT_EAN_13,
                Barcode.FORMAT_EAN_8,
                Barcode.FORMAT_UPC_A,
                Barcode.FORMAT_UPC_E,
                Barcode.FORMAT_CODE_128,
                Barcode.FORMAT_CODE_39,
                Barcode.FORMAT_CODE_93,
                Barcode.FORMAT_ITF,
                Barcode.FORMAT_QR_CODE
            )
            .build()
        barcodeScanner = BarcodeScanning.getClient(options)

        btnFinishScan.setOnClickListener {
            finishWithResult()
        }

        btnToggleTorch.setOnClickListener {
            toggleTorch()
        }

        updateLiveSummary()
        startLaserAnimation()

        if (checkCameraPermission()) {
            startCamera()
        } else {
            requestCameraPermission()
        }
    }

    override fun onBackPressed() {
        finishWithResult()
    }

    private fun finishWithResult() {
        val resultIntent = Intent().apply {
            if (!lastScannedBarcode.isNullOrBlank()) {
                putExtra(EXTRA_SCANNED_BARCODE, lastScannedBarcode)
            }
        }
        setResult(RESULT_OK, resultIntent)
        finish()
    }

    private fun checkCameraPermission(): Boolean {
        return ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.CAMERA
        ) == PackageManager.PERMISSION_GRANTED
    }

    private fun requestCameraPermission() {
        requestPermissions(arrayOf(Manifest.permission.CAMERA), 1001)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 1001) {
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                startCamera()
            } else {
                Toast.makeText(this, "يرجى منح إذن الكاميرا لمسح الباركود", Toast.LENGTH_LONG).show()
                finish()
            }
        }
    }

    private fun startLaserAnimation() {
        val animation = TranslateAnimation(
            Animation.RELATIVE_TO_PARENT, 0.0f,
            Animation.RELATIVE_TO_PARENT, 0.0f,
            Animation.RELATIVE_TO_PARENT, 0.0f,
            Animation.RELATIVE_TO_PARENT, 0.22f
        ).apply {
            duration = 1200
            repeatCount = Animation.INFINITE
            repeatMode = Animation.REVERSE
        }
        laserLine.startAnimation(animation)
    }

    private fun startCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)
        cameraProviderFuture.addListener({
            val cameraProvider: ProcessCameraProvider = cameraProviderFuture.get()

            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(cameraPreviewView.surfaceProvider)
            }

            val imageAnalyzer = ImageAnalysis.Builder()
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
                .also {
                    it.setAnalyzer(cameraExecutor) { imageProxy ->
                        processImageProxy(imageProxy)
                    }
                }

            val cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA

            try {
                cameraProvider.unbindAll()
                camera = cameraProvider.bindToLifecycle(
                    this,
                    cameraSelector,
                    preview,
                    imageAnalyzer
                )
            } catch (exc: Exception) {
                Log.e(TAG, "Use case binding failed", exc)
            }
        }, ContextCompat.getMainExecutor(this))
    }

    @SuppressLint("UnsafeOptInUsageError")
    private fun processImageProxy(imageProxy: ImageProxy) {
        val mediaImage = imageProxy.image
        if (mediaImage != null) {
            val image = InputImage.fromMediaImage(mediaImage, imageProxy.imageInfo.rotationDegrees)
            barcodeScanner?.process(image)
                ?.addOnSuccessListener { barcodes ->
                    for (barcode in barcodes) {
                        val rawValue = barcode.rawValue?.trim()
                        if (!rawValue.isNullOrBlank()) {
                            onBarcodeDetected(rawValue)
                            break
                        }
                    }
                }
                ?.addOnCompleteListener {
                    imageProxy.close()
                }
        } else {
            imageProxy.close()
        }
    }

    /**
     * Handles detected barcode in continuous scan mode.
     */
    private fun onBarcodeDetected(rawBarcode: String) {
        val now = SystemClock.uptimeMillis()

        // Debounce:
        // Same barcode: 1300ms cooldown to avoid runaway counting.
        // Different barcode: 400ms cooldown for ultra-fast continuous shelf scanning.
        if (rawBarcode == lastScannedBarcode && now - lastScannedTime < 1300L) {
            return
        }
        if (rawBarcode != lastScannedBarcode && now - lastScannedTime < 400L) {
            return
        }

        lastScannedBarcode = rawBarcode
        lastScannedTime = now

        // Record scan immediately in active session
        val result = sessionManager.recordScan(rawBarcode)

        runOnUiThread {
            triggerAudioAndHaptic(result.isPackaging, result.isUnknown)
            updateHudDisplay(result)
            updateLiveSummary()
        }
    }

    private fun updateHudDisplay(result: SessionManager.ScanResult) {
        txtHudBarcode.text = result.barcode
        txtHudNameAr.text = result.nameAr
        txtHudCountInZone.text = "${String.format(Locale.US, "%.0f", result.totalCountedInZone)} حبة"

        if (result.isPackaging) {
            badgeHudPackaging.visibility = View.VISIBLE
            badgeHudPackaging.text = "📦 كرتون = ${String.format(Locale.US, "%.0f", result.packagingQty)} حبة (${result.packagingName})"
            txtHudStatus.text = "✅ تم حصر كرتون (+${String.format(Locale.US, "%.0f", result.addedQty)} حبة) | إجمالي الرف: ${String.format(Locale.US, "%.0f", result.totalCountedInZone)}"
            txtHudStatus.setTextColor(getColor(R.color.text_success))
            laserLine.setBackgroundColor(Color.parseColor("#A855F7")) // Purple for packaging
        } else if (result.isUnknown) {
            badgeHudPackaging.visibility = View.GONE
            txtHudStatus.text = "⚠️ صنف غير معرّف (+1 حبة) | إجمالي الرف: ${String.format(Locale.US, "%.0f", result.totalCountedInZone)}"
            txtHudStatus.setTextColor(getColor(R.color.text_warning))
            laserLine.setBackgroundColor(Color.parseColor("#F59E0B")) // Orange for unknown
        } else {
            badgeHudPackaging.visibility = View.GONE
            txtHudStatus.text = "✅ تمت إضافة 1 حبة | إجمالي الرف: ${String.format(Locale.US, "%.0f", result.totalCountedInZone)}"
            txtHudStatus.setTextColor(getColor(R.color.text_success))
            laserLine.setBackgroundColor(Color.parseColor("#10B981")) // Green for known
        }
    }

    private fun updateLiveSummary() {
        val (uniqueCount, totalUnits) = sessionManager.getSessionSummary()
        txtLiveSummary.text = "الرف: ${sessionManager.currentZone} | $uniqueCount صنف (${String.format(Locale.US, "%.0f", totalUnits)} حبة)"
    }

    private fun triggerAudioAndHaptic(isPackaging: Boolean, isUnknown: Boolean) {
        try {
            when {
                isUnknown -> toneGen?.startTone(ToneGenerator.TONE_CDMA_ALERT_CALL_GUARD, 160)
                isPackaging -> toneGen?.startTone(ToneGenerator.TONE_PROP_BEEP2, 130)
                else -> toneGen?.startTone(ToneGenerator.TONE_PROP_ACK, 80)
            }
        } catch (e: Exception) {
            // Ignore
        }

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val vibratorManager = getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager
                vibratorManager.defaultVibrator.vibrate(
                    VibrationEffect.createOneShot(if (isUnknown) 140 else 60, VibrationEffect.DEFAULT_AMPLITUDE)
                )
            } else {
                @Suppress("DEPRECATION")
                val vibrator = getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    vibrator.vibrate(VibrationEffect.createOneShot(if (isUnknown) 140 else 60, VibrationEffect.DEFAULT_AMPLITUDE))
                } else {
                    @Suppress("DEPRECATION")
                    vibrator.vibrate(if (isUnknown) 140 else 60)
                }
            }
        } catch (e: Exception) {
            // Ignore
        }
    }

    private fun toggleTorch() {
        camera?.let { cam ->
            if (cam.cameraInfo.hasFlashUnit()) {
                isTorchOn = !isTorchOn
                cam.cameraControl.enableTorch(isTorchOn)
                btnToggleTorch.setImageResource(
                    if (isTorchOn) R.drawable.ic_camera else R.drawable.ic_send
                )
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        cameraExecutor.shutdown()
        barcodeScanner?.close()
        toneGen?.release()
    }
}
