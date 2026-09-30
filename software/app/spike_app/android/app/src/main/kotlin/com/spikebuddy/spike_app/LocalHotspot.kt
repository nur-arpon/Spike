package com.spikebuddy.spike_app

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.wifi.SoftApConfiguration
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel

/**
 * Android's LocalOnlyHotspot for Spike's camera link away from home (PROTOCOL.md 11.5).
 *
 * Third-party apps cannot switch on the normal tethering hotspot; startLocalOnlyHotspot is the
 * supported way. The OS picks the name and the WPA2 password (we read them from the
 * reservation), there is no internet on it (the robot only talks to the phone), and it stays up
 * only while this app holds the reservation. Needs NEARBY_WIFI_DEVICES (Android 13+) or
 * ACCESS_FINE_LOCATION (12 and older), asked by the app at the moment of use.
 *
 * Channel "spike/hotspot": start -> {ssid, pass, band ("2.4", "5", "6", "any", "unknown")},
 * stop, state; events "spike/hotspot/events": {"event":"stopped"} | {"event":"failed","reason":...}.
 */
class LocalHotspot(private val context: Context, messenger: BinaryMessenger, private val activity: () -> android.app.Activity?) :
    MethodChannel.MethodCallHandler, EventChannel.StreamHandler {

    private val wifi = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
    private val main = Handler(Looper.getMainLooper())
    private val methods = MethodChannel(messenger, "spike/hotspot")
    private val events = EventChannel(messenger, "spike/hotspot/events")
    private var sink: EventChannel.EventSink? = null
    private var reservation: WifiManager.LocalOnlyHotspotReservation? = null
    private var pending: MethodChannel.Result? = null

    init {
        methods.setMethodCallHandler(this)
        events.setStreamHandler(this)
    }

    override fun onListen(arguments: Any?, events: EventChannel.EventSink?) { sink = events }
    override fun onCancel(arguments: Any?) { sink = null }

    private fun emit(map: Map<String, Any?>) = main.post { sink?.success(map) }

    private fun hasPermission(): Boolean {
        val perm = if (Build.VERSION.SDK_INT >= 33) Manifest.permission.NEARBY_WIFI_DEVICES
        else Manifest.permission.ACCESS_FINE_LOCATION
        return context.checkSelfPermission(perm) == PackageManager.PERMISSION_GRANTED
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "start" -> start(result)
            "stop" -> { stop(); result.success(true) }
            "state" -> result.success(mapOf("on" to (reservation != null), "permission" to hasPermission()))
            "requestPermission" -> requestPermission(result)
            else -> result.notImplemented()
        }
    }

    private var permResult: MethodChannel.Result? = null

    /** Shows Android's own permission prompt (the owner decides); answers true/false. */
    private fun requestPermission(result: MethodChannel.Result) {
        if (hasPermission()) { result.success(true); return }
        val a = activity() ?: run { result.success(false); return }
        permResult?.success(false)
        permResult = result
        val perm = if (Build.VERSION.SDK_INT >= 33) Manifest.permission.NEARBY_WIFI_DEVICES
        else Manifest.permission.ACCESS_FINE_LOCATION
        a.requestPermissions(arrayOf(perm), PERMISSION_REQUEST)
    }

    fun onPermissionResult(requestCode: Int): Boolean {
        if (requestCode != PERMISSION_REQUEST) return false
        val r = permResult; permResult = null
        r?.success(hasPermission())
        return true
    }

    companion object { const val PERMISSION_REQUEST = 7301 }

    private fun start(result: MethodChannel.Result) {
        reservation?.let { result.success(describe(it)); return }
        if (pending != null) { result.error("busy", "already starting", null); return }
        if (!hasPermission()) { result.error("permission", "nearby Wi-Fi / location permission not granted", null); return }
        pending = result
        try {
            wifi.startLocalOnlyHotspot(object : WifiManager.LocalOnlyHotspotCallback() {
                override fun onStarted(r: WifiManager.LocalOnlyHotspotReservation) {
                    reservation = r
                    val p = pending; pending = null
                    p?.success(describe(r))
                }

                override fun onStopped() {
                    reservation = null
                    emit(mapOf("event" to "stopped"))
                }

                override fun onFailed(reason: Int) {
                    val why = when (reason) {
                        ERROR_NO_CHANNEL -> "no_channel"
                        ERROR_INCOMPATIBLE_MODE -> "incompatible_mode" // e.g. the normal hotspot is on
                        ERROR_TETHERING_DISALLOWED -> "disallowed"
                        else -> "generic"
                    }
                    val p = pending; pending = null
                    if (p != null) p.error(why, "local-only hotspot failed: $why", null)
                    else emit(mapOf("event" to "failed", "reason" to why))
                }
            }, main)
        } catch (e: SecurityException) {
            pending = null
            result.error("permission", e.message, null)
        } catch (e: IllegalStateException) {
            pending = null
            result.error("busy", e.message, null) // a request from this app is already outstanding
        }
    }

    private fun describe(r: WifiManager.LocalOnlyHotspotReservation): Map<String, Any?> {
        if (Build.VERSION.SDK_INT >= 30) {
            val c: SoftApConfiguration = r.softApConfiguration
            val ssid = if (Build.VERSION.SDK_INT >= 33) c.wifiSsid?.toString()?.trim('"') else @Suppress("DEPRECATION") c.ssid
            // the band is not public API (SoftApConfiguration.getBand is @SystemApi): the robot
            // reports "not_found" if it can't see a 5 GHz-only hotspot, and the app falls back
            return mapOf("ssid" to ssid, "pass" to c.passphrase, "band" to "unknown")
        }
        @Suppress("DEPRECATION")
        val w = r.wifiConfiguration
        @Suppress("DEPRECATION")
        return mapOf("ssid" to w?.SSID?.trim('"'), "pass" to w?.preSharedKey?.trim('"'), "band" to "unknown")
    }

    fun stop() {
        reservation?.close()
        reservation = null
    }

    fun dispose() {
        stop()
        methods.setMethodCallHandler(null)
        events.setStreamHandler(null)
    }
}
