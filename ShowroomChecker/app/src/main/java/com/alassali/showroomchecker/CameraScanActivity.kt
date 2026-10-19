package com.alassali.showroomchecker

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.Bundle
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.util.Log
import android.view.View
import android.view.animation.Animation
import android.view.animation.TranslateAnimation
import android.widget.ImageButton
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
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

class CameraScanActivity : AppCompatActivity() {

    private lateinit var cameraPreviewView: PreviewView
    private lateinit var btnCloseScan: ImageButton
    private lateinit var btnToggleTorch: ImageButton
    private lateinit var laserLine: View

    private var camera: Camera? = null
    private var isTorchOn = false
    private lateinit var cameraExecutor: ExecutorService
    private var barcodeScanner: BarcodeScanner? = null

    private val isBarcodeDetected = AtomicBoolean(false)
    private var toneGen: ToneGenerator? = null

    companion object {
        const val EXTRA_SCANNED_BARCODE = "scanned_barcode"
        private const val TAG = "CameraScanActivity"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_camera_scan)

        cameraPreviewView = findViewById(R.id.cameraPreviewView)
        btnCloseScan = findViewById(R.id.btnCloseScan)
        btnToggleTorch = findViewById(R.id.btnToggleTorch)
        laserLine = findViewById(R.id.laserLine)

        cameraExecutor = Executors.newSingleThreadExecutor()

        try {
            toneGen = ToneGenerator(AudioManager.STREAM_MUSIC, 90)
        } catch (e: Exception) {
            Log.e(TAG, "ToneGenerator error: ${e.message}")
        }

        // Initialize BarcodeScanner with retail barcode formats
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

        btnCloseScan.setOnClickListener {
            setResult(RESULT_CANCELED)
            finish()
        }

        btnToggleTorch.setOnClickListener {
            toggleTorch()
        }

        startLaserAnimation()

        if (allPermissionsGranted()) {
            startCamera()
        } else {
            Toast.makeText(this, "إذن الكاميرا غير متوفر", Toast.LENGTH_SHORT).show()
            finish()
        }
    }

    private fun startLaserAnimation() {
        val animation = TranslateAnimation(
            Animation.RELATIVE_TO_PARENT, 0.0f,
            Animation.RELATIVE_TO_PARENT, 0.0f,
            Animation.RELATIVE_TO_PARENT, -0.4f,
            Animation.RELATIVE_TO_PARENT, 0.4f
        ).apply {
            duration = 1200
            repeatCount = Animation.INFINITE
            repeatMode = Animation.REVERSE
        }
        laserLine.startAnimation(animation)
    }

    private fun toggleTorch() {
        val cam = camera ?: return
        if (cam.cameraInfo.hasFlashUnit()) {
            isTorchOn = !isTorchOn
            cam.cameraControl.enableTorch(isTorchOn)
            btnToggleTorch.setImageResource(
                if (isTorchOn) R.drawable.ic_flash_on else R.drawable.ic_flash_off
            )
        } else {
            Toast.makeText(this, "الكشاف غير مدعوم في هذا الجهاز", Toast.LENGTH_SHORT).show()
        }
    }

    private fun startCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)
        cameraProviderFuture.addListener({
            try {
                val cameraProvider = cameraProviderFuture.get()

                val preview = Preview.Builder()
                    .build()
                    .also {
                        it.setSurfaceProvider(cameraPreviewView.surfaceProvider)
                    }

                val imageAnalysis = ImageAnalysis.Builder()
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .build()
                    .also {
                        it.setAnalyzer(cameraExecutor) { imageProxy ->
                            processImageProxy(imageProxy)
                        }
                    }

                val cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA

                cameraProvider.unbindAll()
                camera = cameraProvider.bindToLifecycle(
                    this,
                    cameraSelector,
                    preview,
                    imageAnalysis
                )

            } catch (e: Exception) {
                Log.e(TAG, "Use case binding failed", e)
                Toast.makeText(this, "تعذر تشغيل الكاميرا: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        }, ContextCompat.getMainExecutor(this))
    }

    @SuppressLint("UnsafeOptInUsageError")
    private fun processImageProxy(imageProxy: ImageProxy) {
        if (isBarcodeDetected.get()) {
            imageProxy.close()
            return
        }

        val mediaImage = imageProxy.image
        if (mediaImage != null) {
            val image = InputImage.fromMediaImage(mediaImage, imageProxy.imageInfo.rotationDegrees)
            barcodeScanner?.process(image)
                ?.addOnSuccessListener { barcodes ->
                    if (!isBarcodeDetected.get()) {
                        for (barcode in barcodes) {
                            val rawValue = barcode.rawValue?.trim()
                            if (!rawValue.isNullOrEmpty()) {
                                if (isBarcodeDetected.compareAndSet(false, true)) {
                                    triggerHapticAndSound()
                                    runOnUiThread {
                                        returnBarcodeResult(rawValue)
                                    }
                                    break
                                }
                            }
                        }
                    }
                }
                ?.addOnFailureListener { e ->
                    Log.e(TAG, "Barcode analysis failed", e)
                }
                ?.addOnCompleteListener {
                    imageProxy.close()
                }
        } else {
            imageProxy.close()
        }
    }

    private fun triggerHapticAndSound() {
        try {
            toneGen?.startTone(ToneGenerator.TONE_PROP_ACK, 80)
        } catch (e: Exception) {
            Log.e(TAG, "Tone error: ${e.message}")
        }

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val vibratorManager = getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager
                vibratorManager?.defaultVibrator?.vibrate(
                    VibrationEffect.createOneShot(50, VibrationEffect.DEFAULT_AMPLITUDE)
                )
            } else {
                @Suppress("DEPRECATION")
                val vibrator = getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    vibrator?.vibrate(VibrationEffect.createOneShot(50, VibrationEffect.DEFAULT_AMPLITUDE))
                } else {
                    @Suppress("DEPRECATION")
                    vibrator?.vibrate(50)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Vibrate error: ${e.message}")
        }
    }

    private fun returnBarcodeResult(barcode: String) {
        val resultIntent = Intent().apply {
            putExtra(EXTRA_SCANNED_BARCODE, barcode)
        }
        setResult(RESULT_OK, resultIntent)
        finish()
    }

    private fun allPermissionsGranted() = ContextCompat.checkSelfPermission(
        this, Manifest.permission.CAMERA
    ) == PackageManager.PERMISSION_GRANTED

    override fun onDestroy() {
        super.onDestroy()
        laserLine.clearAnimation()
        cameraExecutor.shutdown()
        barcodeScanner?.close()
        toneGen?.release()
    }
}
