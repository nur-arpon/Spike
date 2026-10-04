package com.spacez.spike

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine

class MainActivity : FlutterActivity() {
    private var hotspot: LocalHotspot? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        hotspot = LocalHotspot(applicationContext, flutterEngine.dartExecutor.binaryMessenger) { this }
        // free space before a big download (voice pack, offline brain): "spike/storage" freeBytes -> Long
        io.flutter.plugin.common.MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "spike/storage")
            .setMethodCallHandler { call, result ->
                if (call.method == "freeBytes") result.success(android.os.StatFs(filesDir.path).availableBytes)
                else result.notImplemented()
            }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        hotspot?.onPermissionResult(requestCode)
    }

    override fun onDestroy() {
        hotspot?.dispose()
        hotspot = null
        super.onDestroy()
    }
}
