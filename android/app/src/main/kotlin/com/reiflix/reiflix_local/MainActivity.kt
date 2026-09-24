package com.reiflix.reiflix_local

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.ActivityNotFoundException
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.DocumentsContract
import android.provider.MediaStore
import android.provider.Settings
import android.util.Log
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.ActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.view.ViewCompat
import io.flutter.embedding.android.FlutterFragmentActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/**
 * Flet's generated Android template must use this activity instead of its default
 * FlutterActivity. It owns SAF and Google identity because only Android has a
 * ContentResolver/Credential Manager.
 */
class MainActivity : FlutterFragmentActivity() {
    private val tag = "[REIFLIX][ANDROID]"
    private lateinit var systemUiController: SystemUiController
    private var broadStoragePermissionPending = false
    private var mediaPermissionRequestPending = false
    private var safPickerPending = false
    private var activityResumed = false
    private var pendingMediaRequestId: String? = null
    private var pendingBroadRequestId: String? = null
    private var pendingSafRequestId: String? = null
    private var pendingPlayUri: String? = null
    private var pendingPlayTitle: String? = null
    private var pendingPlayPositionMs: Long = 0L
    private var pendingPlayCanNext = false
    private var pendingPlayCanPrevious = false
    private var pendingPlayAutoplay = true
    private var pendingPlayRequestId: String? = null
    private var activePlayerRequestId: String? = null
    private var startupDiscoveryTriggered = false
    private var lastObservedMediaAccess: String? = null
    private var lastObservedBroadAccess: Boolean? = null
    private val nativeRequestState = NativeRequestState()

    private val playerActivityLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result: ActivityResult ->
            val requestId = result.data?.getStringExtra("requestId") ?: activePlayerRequestId
            val reason = result.data?.getStringExtra("reason").orEmpty()
            val controlled = result.resultCode == RESULT_OK && reason.isNotBlank()
            Log.i(
                tag,
                "PLAYER_ACTIVITY_RESULT requestId=" + (requestId ?: "-") + " " +
                    "resultCode=" + result.resultCode + " controlled=" + controlled +
                    " reason=" + reason.ifBlank { "-" },
            )
            NativeMailbox.write(
                this,
                JSONObject()
                    .put("type", "diagnostic")
                    .put("requestId", requestId ?: "")
                    .put(
                        "payload",
                        JSONObject()
                            .put("event", "PLAYER_ACTIVITY_RESULT")
                            .put("resultCode", result.resultCode)
                            .put("controlled", controlled)
                            .put("reason", reason)
                            .put("unexpectedCancellation", result.resultCode == RESULT_CANCELED && !controlled),
                    ),
            )
            if (result.resultCode == RESULT_CANCELED && !controlled) {
                Log.e(
                    tag,
                    "PLAYER_ACTIVITY_UNEXPECTED_CANCELED requestId=" + (requestId ?: "-") +
                        " child ended without a controlled result; inspect NativePlayerActivity logcat for FATAL EXCEPTION/Media3 details.",
                )
            }
            if (requestId != null && activePlayerRequestId == requestId) {
                activePlayerRequestId = null
            }
        }

    companion object {
        private const val STATE_LAST_NATIVE_REQUEST_ID = "reiflix.lastNativeRequestId"
        private const val STATE_PENDING_LIFECYCLE_ACTION = "reiflix.pendingLifecycleAction"
        private const val STATE_BROAD_SETTINGS_PENDING = "reiflix.broadSettingsPending"
        private const val STATE_PENDING_LIFECYCLE_REQUEST_ID = "reiflix.pendingLifecycleRequestId"
        private const val STATE_PENDING_MEDIA_REQUEST_ID = "reiflix.pendingMediaRequestId"
        private const val STATE_PENDING_BROAD_REQUEST_ID = "reiflix.pendingBroadRequestId"
        private const val STATE_PENDING_SAF_REQUEST_ID = "reiflix.pendingSafRequestId"
        private const val STATE_PENDING_PLAY_URI = "reiflix.pendingPlayUri"
        private const val STATE_PENDING_PLAY_TITLE = "reiflix.pendingPlayTitle"
        private const val STATE_PENDING_PLAY_POSITION_MS = "reiflix.pendingPlayPositionMs"
        private const val STATE_PENDING_PLAY_CAN_NEXT = "reiflix.pendingPlayCanNext"
        private const val STATE_PENDING_PLAY_CAN_PREVIOUS = "reiflix.pendingPlayCanPrevious"
        private const val STATE_PENDING_PLAY_AUTOPLAY = "reiflix.pendingPlayAutoplay"
        private const val STATE_PENDING_PLAY_REQUEST_ID = "reiflix.pendingPlayRequestId"
        private const val STATE_ACTIVE_PLAYER_REQUEST_ID = "reiflix.activePlayerRequestId"
        private const val STATE_SAF_PICKER_PENDING = "reiflix.safPickerPending"
        private const val STATE_SEEN_NATIVE_REQUEST_IDS = "reiflix.seenNativeRequestIds"
        private const val STATE_STARTUP_DISCOVERY_TRIGGERED = "reiflix.startupDiscoveryTriggered"
        private const val STATE_LAST_OBSERVED_MEDIA_ACCESS = "reiflix.lastObservedMediaAccess"
        private const val STATE_LAST_OBSERVED_BROAD_ACCESS = "reiflix.lastObservedBroadAccess"
    }
    private val activeNativeScanJobs = mutableMapOf<String, Job>()

    /** Native lifecycle/observer events only request a logical scan. The Python
     * ScanCoordinator decides whether and when a scanner actually runs. */
    private fun publishScanRequest(
        origin: String,
        source: String? = null,
        scopeRef: String? = null,
        full: Boolean = false,
        reason: String = "",
        triggerRequestId: String? = null,
    ) {
        val requestId = UUID.randomUUID().toString()
        NativeMailbox.write(
            this,
            JSONObject()
                .put("type", "scan_request")
                .put("requestId", requestId)
                .put(
                    "payload",
                    JSONObject()
                        .put("origin", origin)
                        .put("source", source ?: "")
                        .put("scopeRef", scopeRef ?: "")
                        .put("full", full)
                        .put("reason", reason)
                        .put("triggerRequestId", triggerRequestId ?: ""),
                ),
        )
        Log.i(
            tag,
            "SCAN_REQUEST requestId=" + requestId +
                " origin=" + origin +
                " source=" + (source ?: "all") +
                " scopeRef=" + (scopeRef ?: "-") +
                " full=" + full +
                " reason=" + (reason.ifBlank { "-" }),
        )
    }
    private var storageReceiverRegistered = false
    private var safInventoryRunning = false
    private var lastBackEventAt = 0L
    private val backEventDebounceMs = 300L
    private val mediaStoreRescanHandler = Handler(Looper.getMainLooper())
    private var mediaStoreRescanScheduled = false
    private var externalSettingsKind: String? = null
    private var externalSettingsRequestId: String? = null
    private val externalSettingsLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result: ActivityResult ->
            val kind = externalSettingsKind
            val requestId = externalSettingsRequestId
            externalSettingsKind = null
            externalSettingsRequestId = null
            Log.i(
                tag,
                "SETTINGS_RETURN kind=" + (kind ?: "-") +
                    " resultCode=" + result.resultCode +
                    " requestId=" + (requestId ?: "-") +
                    " broad=" + BroadStorageScanner.hasAccess(this) +
                    " media=" + MediaStoreScanner.accessLevel(this),
            )
            when (kind) {
                "broad_storage" -> handleBroadSettingsReturn(requestId, "activity_result")
                else -> {
                    // App Info and other Android permission surfaces must still
                    // converge to the authoritative native snapshot on return.
                    Log.i(tag, "SETTINGS_RETURN revalidating non-broad surface kind=" + (kind ?: "-"))
                    publishStorageStatus()
                }
            }
        }

    private fun scheduleMediaStoreIncrementalRescan() {
        if (mediaStoreRescanScheduled) return
        mediaStoreRescanScheduled = true
        mediaStoreRescanHandler.postDelayed({
            mediaStoreRescanScheduled = false
            if (!activityResumed || !MediaStoreScanner.hasReadPermission(this)) return@postDelayed
            Log.i(tag, "MEDIASTORE_OBSERVER_CHANGE forwarded to ScanCoordinator")
            publishScanRequest(
                "MEDIASTORE_CHANGE",
                source = "mediastore",
                full = false,
                reason = "content_observer_debounce",
            )
        }, 750L)
    }
    private val storageReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: android.content.Context, intent: Intent) {
            val action = intent.action ?: return
            val changes = NativeIndex.updateVolumeSnapshot(
                applicationContext,
                NativeIndex.volumeSnapshot(applicationContext),
            )
            if (changes.optBoolean("changed")) {
                val payload = JSONObject(changes.toString())
                    .put("source", "android_storage")
                    .put("reason", action)
                    .put("timestamp", System.currentTimeMillis())
                    .put("volumeEventUri", intent.data?.toString() ?: "")
                NativeMailbox.write(this@MainActivity, JSONObject()
                    .put("type", "volume_changed")
                    .put("payload", payload))
            }

            // Mirror Nova's media/volume lifecycle integration: a mount or the
            // completion of Android's MediaScanner is a discovery trigger. Never
            // launch a permission UI from a broadcast; only start scans when the
            // current Activity is RESUMED and the corresponding source is actually
            // authorized.
            val discoveryEvent = action == Intent.ACTION_MEDIA_MOUNTED ||
                action == Intent.ACTION_MEDIA_SCANNER_FINISHED
            if (discoveryEvent && activityResumed) {
                publishScanRequest(
                    "VOLUME_MOUNT",
                    source = null,
                    full = false,
                    reason = action,
                )
            } else if (action == Intent.ACTION_MEDIA_UNMOUNTED ||
                action == Intent.ACTION_MEDIA_EJECT ||
                action == Intent.ACTION_MEDIA_REMOVED ||
                action == Intent.ACTION_MEDIA_BAD_REMOVAL) {
                publishStorageStatus()
            }
        }
    }

    private fun registerStorageReceiver() {
        if (storageReceiverRegistered) return
        val filter = IntentFilter().apply {
            addAction(Intent.ACTION_MEDIA_MOUNTED)
            addAction(Intent.ACTION_MEDIA_UNMOUNTED)
            addAction(Intent.ACTION_MEDIA_REMOVED)
            addAction(Intent.ACTION_MEDIA_EJECT)
            addAction(Intent.ACTION_MEDIA_BAD_REMOVAL)
            addAction(Intent.ACTION_MEDIA_CHECKING)
            addAction(Intent.ACTION_MEDIA_SCANNER_FINISHED)
            addDataScheme("file")
        }
        try {
            if (Build.VERSION.SDK_INT >= 33) {
                registerReceiver(storageReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
            } else {
                @Suppress("DEPRECATION")
                registerReceiver(storageReceiver, filter)
            }
            storageReceiverRegistered = true
        } catch (exception: Exception) {
            Log.w(tag, "Unable to register storage volume receiver", exception)
        }
    }

    private fun unregisterStorageReceiver() {
        if (!storageReceiverRegistered) return
        runCatching { unregisterReceiver(storageReceiver) }
        storageReceiverRegistered = false
    }
    private val mediaPermissionRequester = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { grants ->
        mediaPermissionRequestPending = false
        val requestId = pendingMediaRequestId
        pendingMediaRequestId = null
        val access = MediaStoreScanner.accessLevel(this)
        // Android's callback map is only a notification; the current package permissions are authoritative.
        val granted = access != "denied"
        Log.i(tag, "MEDIA_PERMISSION_CALLBACK grants=" + grants + " access=" + access + " granted=" + granted)
        NativeMailbox.write(this, JSONObject().put("type", "diagnostic").put("payload", JSONObject().put("event", "PERMISSION_RESULT").put("source", MediaStoreScanner.SOURCE).put("access", access)))
        NativeMailbox.write(this, JSONObject().put("type", "mediastore_permission")
            .put("requestId", requestId ?: "")
            .put("payload", JSONObject()
                .put("granted", granted)
                .put("access", access)
                .put("source", MediaStoreScanner.SOURCE)
                .put("capabilities", storageCapabilitiesPayload(StorageLifecycleState.REVALIDATED))))
        if (granted) publishScanRequest("PERMISSION_CHANGE", "mediastore", null, false, "media_permission_granted", requestId) else {
            NativeMailbox.write(this, JSONObject().put("type", "mediastore_error")
                .put("requestId", requestId ?: "")
                .put("message", "A permissão para acessar os vídeos do dispositivo foi negada.")
                .put("payload", JSONObject().put("source", MediaStoreScanner.SOURCE).put("status", NativeIndex.STATUS_FAILED).put("access", access)))
        }
    }
    private val treePicker = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result: ActivityResult ->
        handleTreePickerResult(result)
    }

    private fun handleTreePickerResult(result: androidx.activity.result.ActivityResult) {
        val resultIntent = result.data
        val uri = resultIntent?.data
        val requestId = pendingSafRequestId
        pendingSafRequestId = null
        safPickerPending = false
        Log.i(
            tag,
            "SETTINGS_RETURN kind=saf_picker resultCode=" + result.resultCode +
                " requestId=" + (requestId ?: "-"),
        )
        if (result.resultCode != RESULT_OK || uri == null) {
            Log.i(tag, "SAF selection cancelled resultCode=" + result.resultCode)
            NativeMailbox.write(this, JSONObject().put("type", "saf_cancelled")
                .put("requestId", requestId ?: "")
                .put("payload", JSONObject().put("source", "saf").put("reason", "picker_cancelled")))
            return
        }
        try {
            Log.i(tag, "SAF result received")
            val identity = SafScanner.treeIdentity(uri)
            val transientInspection = SafScanner.inspectTree(this, uri, requirePersisted = false)
            val transientStatus = transientInspection.optString("status")
            if (transientStatus != SafScanner.STATUS_COMPLETED) {
                val status = if (transientStatus == SafScanner.STATUS_REVOKED) SafScanner.STATUS_REVOKED else SafScanner.STATUS_UNAVAILABLE
                NativeMailbox.write(this, JSONObject().put("type", "saf_error")
                    .put("requestId", requestId ?: "")
                    .put("message", "O provedor não conseguiu abrir a pasta selecionada.")
                    .put("payload", SafScanner.identityPayload(uri)
                        .put("scanId", "")
                        .put("status", status)
                        .put("stage", "selection_validation")
                        .put("error", transientInspection.optString("error", "provider_unavailable"))))
                return
            }
            val flags = resultIntent.flags
            SafScanner.persistPermission(this, uri, flags)
            val persistedInspection = SafScanner.inspectTree(this, uri, requirePersisted = true)
            val persistedStatus = persistedInspection.optString("status")
            if (persistedStatus != SafScanner.STATUS_COMPLETED) {
                val status = if (!SafScanner.hasPersistedReadPermission(this, uri)) SafScanner.STATUS_REVOKED else SafScanner.STATUS_UNAVAILABLE
                NativeMailbox.write(this, JSONObject().put("type", "saf_error")
                    .put("requestId", requestId ?: "")
                    .put("message", "A autorização da pasta não pôde ser validada.")
                    .put("payload", SafScanner.identityPayload(uri)
                        .put("status", status)
                        .put("stage", "persisted_validation")
                        .put("error", persistedInspection.optString("error", "provider_unavailable"))))
                return
            }
            val payload = SafScanner.identityPayload(uri)
                .put("granted", true)
                .put("selected", true)
                .put("status", SafScanner.STATUS_COMPLETED)
                .put("name", SafScanner.displayName(this, uri))
                .put("capabilities", storageCapabilitiesPayload(StorageLifecycleState.REVALIDATED))
            NativeMailbox.write(this, JSONObject().put("type", "saf_permission")
                .put("requestId", requestId ?: "")
                .put("payload", payload))
            publishScanRequest("PERMISSION_CHANGE", "saf", uri.toString(), false, "saf_granted", requestId)
        } catch (exception: IllegalArgumentException) {
            Log.e(tag, "Invalid SAF selection", exception)
            NativeMailbox.write(this, JSONObject().put("type", "saf_error")
                .put("requestId", requestId ?: "")
                .put("message", "A pasta selecionada não é uma árvore SAF válida.")
                .put("payload", JSONObject().put("source", "saf").put("status", SafScanner.STATUS_FAILED)
                    .put("stage", "selection_validation")))
        } catch (exception: Exception) {
            Log.e(tag, "SAF selection failed", exception)
            NativeMailbox.write(this, JSONObject().put("type", "saf_error")
                .put("requestId", requestId ?: "")
                .put("message", "Não foi possível autorizar esta pasta. Escolha-a novamente.")
                .put("payload", SafScanner.identityPayload(uri)
                    .put("status", if (SafScanner.hasPersistedReadPermission(this, uri)) SafScanner.STATUS_UNAVAILABLE else SafScanner.STATUS_FAILED)
                    .put("stage", "persist")))
        }
    }

    private fun logLifecycle(event: String, intent: Intent? = null) {
        val data = intent?.data
        val action = data?.getQueryParameter("action")
        val requestId = data?.getQueryParameter("request_id")
        Log.i(
            tag,
            "LIFECYCLE $event instance=${System.identityHashCode(this)} task=$taskId resumed=$activityResumed " +
                "focused=${window?.decorView?.hasWindowFocus() == true} finishing=$isFinishing " +
                "action=${action ?: "-"} requestId=${requestId ?: "-"} flags=0x${intent?.flags?.toString(16) ?: "0"}"
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        installSystemBackHandler()
        nativeRequestState.bind(this)
        nativeRequestState.restore(
            savedInstanceState?.getString(STATE_LAST_NATIVE_REQUEST_ID),
            savedInstanceState?.getString(STATE_PENDING_LIFECYCLE_ACTION),
            savedInstanceState?.getString(STATE_PENDING_LIFECYCLE_REQUEST_ID),
        )
        nativeRequestState.restoreSeenRequestIds(savedInstanceState?.getString(STATE_SEEN_NATIVE_REQUEST_IDS))
        broadStoragePermissionPending = savedInstanceState?.getBoolean(STATE_BROAD_SETTINGS_PENDING) ?: false
        externalSettingsKind = savedInstanceState?.getString("reiflix.externalSettingsKind")
        externalSettingsRequestId = savedInstanceState?.getString("reiflix.externalSettingsRequestId")
        pendingMediaRequestId = savedInstanceState?.getString(STATE_PENDING_MEDIA_REQUEST_ID)
        pendingBroadRequestId = savedInstanceState?.getString(STATE_PENDING_BROAD_REQUEST_ID)
        pendingSafRequestId = savedInstanceState?.getString(STATE_PENDING_SAF_REQUEST_ID)
        pendingPlayUri = savedInstanceState?.getString(STATE_PENDING_PLAY_URI)
        pendingPlayTitle = savedInstanceState?.getString(STATE_PENDING_PLAY_TITLE)
        pendingPlayPositionMs = savedInstanceState?.getLong(STATE_PENDING_PLAY_POSITION_MS, 0L) ?: 0L
        pendingPlayCanNext = savedInstanceState?.getBoolean(STATE_PENDING_PLAY_CAN_NEXT) ?: false
        pendingPlayCanPrevious = savedInstanceState?.getBoolean(STATE_PENDING_PLAY_CAN_PREVIOUS) ?: false
        pendingPlayAutoplay = savedInstanceState?.getBoolean(STATE_PENDING_PLAY_AUTOPLAY) ?: true
        pendingPlayRequestId = savedInstanceState?.getString(STATE_PENDING_PLAY_REQUEST_ID)
        activePlayerRequestId = savedInstanceState?.getString(STATE_ACTIVE_PLAYER_REQUEST_ID)?.trim()?.takeIf { it.isNotEmpty() }
        safPickerPending = savedInstanceState?.getBoolean(STATE_SAF_PICKER_PENDING) ?: false
        startupDiscoveryTriggered = savedInstanceState?.getBoolean(STATE_STARTUP_DISCOVERY_TRIGGERED) ?: false
        lastObservedMediaAccess = savedInstanceState?.getString(STATE_LAST_OBSERVED_MEDIA_ACCESS)
        if (savedInstanceState?.containsKey(STATE_LAST_OBSERVED_BROAD_ACCESS) == true) {
            lastObservedBroadAccess = savedInstanceState.getBoolean(STATE_LAST_OBSERVED_BROAD_ACCESS)
        }
        logLifecycle("onCreate", intent)
        NativeMailbox.write(this, JSONObject().put("type", "diagnostic").put("payload", JSONObject().put("event", "APP_START").put("lifecycle", "onCreate")))
        systemUiController = SystemUiController(window)
        applyNormalSystemUi()
        // Permission-sensitive actions are queued until the Activity is resumed.
        handleNativeIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        logLifecycle("onNewIntent", intent)
        handleNativeIntent(intent)
    }

    override fun onStart() {
        super.onStart()
        registerStorageReceiver()
        MediaStoreScanner.startChangeObserver(this) { scheduleMediaStoreIncrementalRescan() }
        logLifecycle("onStart")
    }

    override fun onResume() {
        super.onResume()
        activityResumed = true
        logLifecycle("onResume")
        NativeMailbox.write(this, JSONObject().put("type", "diagnostic").put("payload", JSONObject().put("event", "ON_RESUME").put("lifecycle", "onResume")))
        applyNormalSystemUi()

        // A lifecycle-sensitive command may have been queued because the
        // Activity was not resumed when Python delivered the request. Do not
        // publish an intermediate "denied" snapshot first: Python could treat
        // that snapshot as the final result and close the onboarding while the
        // real Android permission/settings UI is only about to open.
        val pending = nativeRequestState.consumeLifecycleAction()
        val pendingRequestId = nativeRequestState.consumedLifecycleRequestId()
        if (pending != null) {
            pendingMediaRequestId = pendingRequestId
            pendingBroadRequestId = pendingRequestId
            pendingSafRequestId = pendingRequestId
            when (pending) {
                "select_tree" -> openTreePicker()
                "request_media_access" -> requestMediaAccess()
                "open_broad_storage_settings" -> openBroadStorageSettings()
                "play" -> {
                    val uri = pendingPlayUri
                    if (!uri.isNullOrBlank()) {
                        val playData = Uri.parse("reiflix://native").buildUpon()
                            .appendQueryParameter("action", "play")
                            .appendQueryParameter("request_id", pendingPlayRequestId.orEmpty())
                            .appendQueryParameter("uri", uri)
                            .appendQueryParameter("title", pendingPlayTitle ?: "Episódio")
                            .appendQueryParameter("position_ms", pendingPlayPositionMs.toString())
                            .appendQueryParameter("can_next", pendingPlayCanNext.toString())
                            .appendQueryParameter("can_previous", pendingPlayCanPrevious.toString())
                            .appendQueryParameter("autoplay", pendingPlayAutoplay.toString())
                            .build()
                        clearPendingPlay()
                        openPlayer(playData)
                    } else {
                        clearPendingPlay()
                    }
                }
            }
            // Established host contract: "request_media_access" -> requestMediaAccess()
            return
        }

        // Settings may revoke access while this activity is paused. Always
        // republish the actual Android state after a real Settings return.
        if (broadStoragePermissionPending) {
            // Revalidate the real Android state on every Settings return. This is
            // safe even when ActivityResult is delivered afterward because the
            // return handler is idempotent once the pending flag is cleared.
            handleBroadSettingsReturn(pendingBroadRequestId, "onResume")
            return
        }

        val currentMediaAccess = MediaStoreScanner.accessLevel(this)
        val currentBroadAccess = BroadStorageScanner.hasAccess(this)
        val mediaAccessChangedToUsable = lastObservedMediaAccess != null &&
            lastObservedMediaAccess != currentMediaAccess &&
            currentMediaAccess != "denied"
        val broadBecameAvailable = lastObservedBroadAccess == false && currentBroadAccess
        val shouldDiscover = !startupDiscoveryTriggered
        startupDiscoveryTriggered = true
        lastObservedMediaAccess = currentMediaAccess
        lastObservedBroadAccess = currentBroadAccess

        publishStorageStatus()

        // Activity resume is a lifecycle signal, not a scan command. Only the
        // first real startup or a permission transition produces a coordinator
        // request; ordinary player/background returns do nothing.
        if (shouldDiscover) {
            publishScanRequest(
                "STARTUP",
                source = null,
                full = false,
                reason = "first_activity_resume",
            )
        } else if (mediaAccessChangedToUsable || broadBecameAvailable) {
            val source = when {
                mediaAccessChangedToUsable && broadBecameAvailable -> null
                mediaAccessChangedToUsable -> "mediastore"
                else -> "broad_storage"
            }
            publishScanRequest(
                "PERMISSION_CHANGE",
                source = source,
                full = false,
                reason = "permission_available_after_resume",
            )
        }
    }

    override fun onPause() {
        activityResumed = false
        logLifecycle("onPause")
        super.onPause()
    }

    override fun onStop() {
        logLifecycle("onStop")
        unregisterStorageReceiver()
        MediaStoreScanner.stopChangeObserver(this)
        mediaStoreRescanHandler.removeCallbacksAndMessages(null)
        mediaStoreRescanScheduled = false
        super.onStop()
    }

    override fun onDestroy() {
        logLifecycle("onDestroy")
        if (isFinishing) NativeScanController.cancelAll()
        unregisterStorageReceiver()
        super.onDestroy()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putString(STATE_LAST_NATIVE_REQUEST_ID, nativeRequestState.lastHandledRequestId)
        outState.putString(STATE_PENDING_LIFECYCLE_ACTION, nativeRequestState.pendingLifecycleAction)
        outState.putString(STATE_PENDING_LIFECYCLE_REQUEST_ID, nativeRequestState.pendingLifecycleRequestId)
        outState.putString(STATE_PENDING_MEDIA_REQUEST_ID, pendingMediaRequestId)
        outState.putString(STATE_PENDING_BROAD_REQUEST_ID, pendingBroadRequestId)
        outState.putString(STATE_PENDING_SAF_REQUEST_ID, pendingSafRequestId)
        outState.putString(STATE_PENDING_PLAY_URI, pendingPlayUri)
        outState.putString(STATE_PENDING_PLAY_TITLE, pendingPlayTitle)
        outState.putLong(STATE_PENDING_PLAY_POSITION_MS, pendingPlayPositionMs)
        outState.putBoolean(STATE_PENDING_PLAY_CAN_NEXT, pendingPlayCanNext)
        outState.putBoolean(STATE_PENDING_PLAY_CAN_PREVIOUS, pendingPlayCanPrevious)
        outState.putBoolean(STATE_PENDING_PLAY_AUTOPLAY, pendingPlayAutoplay)
        outState.putString(STATE_PENDING_PLAY_REQUEST_ID, pendingPlayRequestId)
        outState.putString(STATE_ACTIVE_PLAYER_REQUEST_ID, activePlayerRequestId)
        outState.putBoolean(STATE_BROAD_SETTINGS_PENDING, broadStoragePermissionPending)
        outState.putBoolean(STATE_SAF_PICKER_PENDING, safPickerPending)
        outState.putString("reiflix.externalSettingsKind", externalSettingsKind)
        outState.putString("reiflix.externalSettingsRequestId", externalSettingsRequestId)
        outState.putBoolean(STATE_STARTUP_DISCOVERY_TRIGGERED, startupDiscoveryTriggered)
        outState.putString(STATE_LAST_OBSERVED_MEDIA_ACCESS, lastObservedMediaAccess)
        lastObservedBroadAccess?.let { outState.putBoolean(STATE_LAST_OBSERVED_BROAD_ACCESS, it) }
        outState.putString(STATE_SEEN_NATIVE_REQUEST_IDS, nativeRequestState.seenRequestIdsState())
        super.onSaveInstanceState(outState)
    }

    /**
     * Android owns the physical Back dispatch, while Flutter/Flet remains the
     * single logical navigation owner. The callback deliberately never calls
     * finish() and never emits a NativeMailbox back event; it forwards platform
     * Back to Flutter so page.on_view_pop / NavigationController stay
     * authoritative, including the double-back exit policy.
     */
    private fun installSystemBackHandler() {
        onBackPressedDispatcher.addCallback(
            this,
            object : OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    Log.i(tag, "SYSTEM_BACK forward_to_flet route_dispatch")
                    flutterEngine?.navigationChannel?.popRoute()
                }
            },
        )
    }

    private fun persistedSafTreeUris(): List<String> =
        contentResolver.persistedUriPermissions
            .asSequence()
            .filter { it.isReadPermission && it.uri.scheme == "content" && DocumentsContract.isTreeUri(it.uri) }
            .map { it.uri.toString() }
            .distinct()
            .sorted()
            .toList()

    private fun applyNormalSystemUi() {
        if (::systemUiController.isInitialized) {
            systemUiController.applyNormal()
        }
    }

    private fun storageCapabilitiesPayload(
        lifecycleState: StorageLifecycleState = StorageLifecycleState.REVALIDATED
    ): JSONObject {
        val broadSnapshot = BroadStorageScanner.accessSnapshot(this)
        val mediaState = MediaStoreScanner.accessLevelValue(this)
        val broadState = BroadStorageScanner.accessLevel(this)
        val safRoots = persistedSafTreeUris()
        val removableVolumes = mutableListOf<String>()
        val volumes = broadSnapshot.optJSONArray("volumes")
        if (volumes != null) {
            for (i in 0 until volumes.length()) {
                val volume = volumes.optJSONObject(i) ?: continue
                if (volume.optBoolean("removable", false)) {
                    val id = volume.optString("volumeId").ifBlank { volume.optString("uuid") }
                    if (id.isNotBlank()) removableVolumes += id
                }
            }
        }
        val capabilities = StorageAuthorization.capabilities(
            mediaState, broadState, safRoots, removableVolumes, lifecycleState
        )
        return JSONObject()
            .put("mediaReadState", capabilities.mediaReadState.name.lowercase())
            .put("broadStorageState", capabilities.broadStorageState.name.lowercase())
            .put("safRoots", JSONArray(capabilities.safRoots))
            .put("removableVolumes", JSONArray(capabilities.removableVolumes))
            .put("scannerCapabilities", JSONArray(capabilities.scannerCapabilities.toList()))
            .put("reconciliationCapabilities", JSONArray(capabilities.reconciliationCapabilities.toList()))
            .put("lifecycleState", capabilities.lifecycleState.name.lowercase())
            .put("api", Build.VERSION.SDK_INT)
    }

    private fun publishStorageCapabilities(
        lifecycleState: StorageLifecycleState = StorageLifecycleState.REVALIDATED
    ) {
        NativeMailbox.write(
            this,
            JSONObject().put("type", "storage_capabilities")
                .put("payload", storageCapabilitiesPayload(lifecycleState))
        )
    }

    private fun handleNativeIntent(intent: Intent?) {
        val data = intent?.data ?: return
        if (data.scheme != "reiflix" || data.host != "native") {
            Log.w(tag, "Ignoring unsupported native intent: $data")
            return
        }
        val action = data.getQueryParameter("action")
        if (!NativeRequestState.isSupportedAction(action)) {
            Log.w(tag, "Ignoring malformed or unsupported native action: " + (action ?: "-"))
            return
        }
        val requestId = data.getQueryParameter("request_id")?.trim()?.takeIf { it.isNotEmpty() }
        if (!nativeRequestState.acceptRequest(requestId)) {
            Log.i(tag, "Ignoring duplicate native request: action=$action requestId=$requestId")
            return
        }
        Log.i(
            tag,
            "NATIVE_INTENT action=$action requestId=${requestId ?: "-"} " +
                "data=${intent.dataString ?: "-"} task=$taskId resumed=$activityResumed " +
                "focus=${window?.decorView?.hasWindowFocus() == true} " +
                "flags=0x${intent.flags.toString(16)} " +
                "extras=${intent.extras?.keySet()?.joinToString(",") ?: "-"}",
        )
        when (action) {
            "select_tree" -> {
                if (!activityResumed) {
                    if (nativeRequestState.queueLifecycleAction("select_tree", requestId)) {
                        Log.i(tag, "Queued SAF picker until Activity is resumed")
                    }
                    return
                }
                pendingSafRequestId = requestId
                openTreePicker()
            }
            "scan_tree" -> scanTree(intent.data?.getQueryParameter("tree_uri"), requestId)
            "verify_tree" -> verifyTree(intent.data?.getQueryParameter("tree_uri"))
            "release_tree" -> releaseTree(intent.data?.getQueryParameter("tree_uri"))
            "scan_media_store" -> scanMediaStore(requestId)
            "request_media_access", "open_broad_storage_settings" -> {
                if (!activityResumed) {
                    if (nativeRequestState.queueLifecycleAction(action, requestId)) {
                        Log.i(tag, "Queued lifecycle-sensitive action until Activity is resumed: $action")
                    } else {
                        Log.i(tag, "Ignoring duplicate lifecycle-sensitive action: $action")
                    }
                    return
                }
                if (action == "request_media_access") {
                    pendingMediaRequestId = requestId
                    requestMediaAccess()
                } else {
                    pendingBroadRequestId = requestId
                    openBroadStorageSettings()
                }
            }
            "check_storage_access" -> publishStorageStatus()
            "scan_all_storage" -> scanAllStorage(requestId)
            "extract_thumbnail" -> requestThumbnail(intent.data, requestId)
            "cancel_scan" -> cancelNativeScans(requestId)
            "google_sign_in" -> signInWithGoogle(intent.data?.getQueryParameter("server_client_id"))
            "play" -> {
                if (!activityResumed) {
                    pendingPlayUri = data.getQueryParameter("uri")
                    pendingPlayTitle = data.getQueryParameter("title") ?: "Episódio"
                    pendingPlayPositionMs = data.getQueryParameter("position_ms")?.toLongOrNull()?.coerceAtLeast(0L) ?: 0L
                    pendingPlayCanNext = data.getQueryParameter("can_next")?.toBooleanStrictOrNull() ?: false
                    pendingPlayCanPrevious = data.getQueryParameter("can_previous")?.toBooleanStrictOrNull() ?: false
                    pendingPlayAutoplay = data.getQueryParameter("autoplay")?.toBooleanStrictOrNull() ?: true
                    pendingPlayRequestId = requestId
                    if (!nativeRequestState.queueLifecycleAction("play", requestId)) {
                        Log.i(tag, "PLAY request could not be queued because another lifecycle action is pending; requestId=" + requestId)
                    } else {
                        Log.i(tag, "PLAY queued until Activity is resumed requestId=" + requestId)
                    }
                } else {
                    openPlayer(data)
                }
            }
        }
    }
    /**
     * Publishes one bounded native scan batch. Android prepares the batch into
     * NativeIndex staging before the mailbox event is emitted; Python ingests the
     * same bounded payload and only performs destructive reconciliation on final.
     */
    private fun publishNativeScanBatch(
        appContext: Context,
        eventType: String,
        source: String,
        scanId: String,
        requestId: String?,
        scopeKind: String,
        scopeRef: String,
        scopeKey: String,
        generation: Long,
        batchEvent: JSONObject,
    ) {
        try {
            val raw = batchEvent.optJSONArray("documents") ?: JSONArray()
            val batchId = batchEvent.optString("batchId").ifBlank { UUID.randomUUID().toString() }
            val batchNumber = batchEvent.optInt("batchNumber", 0)
            val reused = batchEvent.optBoolean("reused", false)
            val prepared = if (reused) null else NativeIndex.prepareBatch(
                appContext,
                source,
                scopeKey,
                raw,
                generation,
                batchId,
                batchNumber,
                JSONObject()
                    .put("scanId", scanId)
                    .put("requestId", requestId ?: "")
                    .put("source", source)
                    .put("scopeKind", scopeKind)
                    .put("scopeRef", scopeRef),
            )
            val documents = prepared?.documents ?: raw
            val effectiveGeneration = prepared?.generation ?: generation
            val effectiveGenerationId = prepared?.generationId
                ?: NativeIndex.generationId(source, scopeKey, effectiveGeneration)
            val payload = JSONObject()
                .put("scanId", if (scopeKind == "volume" && scopeRef.isNotBlank()) "$scanId:$scopeRef" else scanId)
                .put("scopeScanId", if (scopeKind == "volume" && scopeRef.isNotBlank()) "$scanId:$scopeRef" else scanId)
                .put("requestId", requestId ?: "")
                .put("source", source)
                .put("scope", scopeRef)
                .put("scopeKind", scopeKind)
                .put("scopeRef", scopeRef)
                .put("volumeId", batchEvent.optString("volumeId"))
                .put("generationId", effectiveGenerationId)
                .put("scanGeneration", effectiveGeneration)
                .put("batchId", batchId)
                .put("batchNumber", batchNumber)
                .put("batchSize", documents.length())
                .put("processed", documents.length())
                .put("discovered", raw.length())
                .put("duplicates", prepared?.duplicates ?: 0)
                .put("reused", reused)
                .put("documents", documents)
            NativeMailbox.writeOrThrow(
                appContext,
                JSONObject().put("type", eventType).put("requestId", requestId ?: "").put("payload", payload)
            )
        } catch (exception: Exception) {
            Log.e(tag, "Native batch publication failed", exception)
            NativeMailbox.write(
                appContext,
                JSONObject().put("type", eventType.replace("_batch", "_error"))
                    .put("requestId", requestId ?: "")
                    .put("message", "Não foi possível preparar um lote da biblioteca.")
                    .put("payload", JSONObject()
                        .put("scanId", scanId)
                        .put("requestId", requestId ?: "")
                        .put("source", source)
                        .put("scopeKind", scopeKind)
                        .put("scopeRef", scopeRef)
                        .put("generationId", NativeIndex.generationId(source, scopeKey, generation))
                        .put("status", NativeIndex.STATUS_FAILED)
                        .put("batchId", batchEvent.optString("batchId"))
                        .put("batchNumber", batchEvent.optInt("batchNumber", 0))
                        .put("error", exception.message ?: "native_batch_failed"))
            )
            throw exception
        }
    }

    private fun scanTree(reference: String?, requestId: String? = null) {
        val scanId = UUID.randomUUID().toString()
        if (reference.isNullOrBlank()) {
            NativeMailbox.write(this, JSONObject().put("type", "saf_error")
                .put("requestId", requestId ?: "")
                .put("message", "A pasta SAF não foi informada corretamente.")
                .put("payload", JSONObject().put("scanId", scanId)))
            return
        }
        val treeUri = Uri.parse(reference)
        val persistedInspection = SafScanner.inspectTree(this, treeUri, requirePersisted = true)
        val persistedStatus = persistedInspection.optString("status")
        if (persistedStatus == SafScanner.STATUS_REVOKED) {
            Log.w(tag, "SAF permission revoked")
            NativeMailbox.write(this, JSONObject().put("type", "saf_permission")
                .put("requestId", requestId ?: "")
                .put("payload", SafScanner.identityPayload(treeUri)
                    .put("granted", false).put("status", SafScanner.STATUS_REVOKED)
                    .put("error", persistedInspection.optString("error", "persisted_permission_missing"))))
            NativeMailbox.write(this, JSONObject().put("type", "saf_error")
                .put("requestId", requestId ?: "")
                .put("message", "A permissão desta pasta foi removida. Escolha a pasta novamente.")
                .put("payload", SafScanner.identityPayload(treeUri).put("scanId", scanId).put("status", SafScanner.STATUS_REVOKED)))
            return
        }
        if (persistedStatus != SafScanner.STATUS_COMPLETED) {
            NativeMailbox.write(this, JSONObject().put("type", "saf_error")
                .put("requestId", requestId ?: "")
                .put("message", if (persistedStatus == SafScanner.STATUS_UNAVAILABLE) {
                    "O provedor desta pasta está indisponível no momento."
                } else {
                    "A árvore SAF não pôde ser validada."
                })
                .put("payload", SafScanner.identityPayload(treeUri).put("scanId", scanId)
                    .put("status", if (persistedStatus == SafScanner.STATUS_UNAVAILABLE) SafScanner.STATUS_UNAVAILABLE else SafScanner.STATUS_FAILED)
                    .put("error", persistedInspection.optString("error", "provider_unavailable"))))
            return
        }
        val scanKey = "saf:$reference"
        if (!NativeScanController.begin(scanId, scanKey)) {
            NativeMailbox.write(this, JSONObject().put("type", "saf_scan_progress")
                .put("payload", JSONObject().put("treeUri", reference).put("requestId", requestId ?: "").put("phase", "already_running")))
            return
        }
        val generationId = NativeIndex.startGeneration(
            this, NativeIndex.SOURCE_SAF, scanKey,
            SafScanner.identityPayload(treeUri).put("scopeKind", "root").put("scopeRef", SafScanner.treeIdentity(treeUri).identity).put("scanId", scanId)
        )
        val appContext = applicationContext
        val job = CoroutineScope(Dispatchers.IO).launch {
            try {
                NativeIndex.markGenerationRunning(appContext, NativeIndex.SOURCE_SAF, scanKey, generationId)
                NativeMailbox.write(appContext, JSONObject().put("type", "saf_scan_progress")
                    .put("requestId", requestId ?: "")
                    .put("payload", SafScanner.identityPayload(treeUri).put("scanId", scanId).put("phase", "started")
                        .put("source", "saf").put("generationId", NativeIndex.generationId(NativeIndex.SOURCE_SAF, scanKey, generationId))))
                val onScanProgress: (JSONObject) -> Unit = { progress ->
                    NativeMailbox.write(
                        appContext,
                        JSONObject()
                            .put("type", "saf_scan_progress")
                            .put(
                                "payload",
                                progress
                                    .put("treeUri", reference)
                                    .put("scanId", scanId)
                                    .put("requestId", requestId ?: "")
                                    .put("phase", "scanning")
                            )
                    )
                }
                val shouldCancelScan: () -> Boolean = { NativeScanController.isCancelled(scanId) }
                val result = SafScanner.scan(
                    appContext,
                    treeUri,
                    onScanProgress,
                    shouldCancelScan,
                    scanId,
                ) { batch ->
                    publishNativeScanBatch(
                        appContext,
                        "saf_scan_batch",
                        "saf",
                        scanId,
                        requestId,
                        "root",
                        reference,
                        scanKey,
                        generationId,
                        batch,
                    )
                }
                val partial = result.optBoolean("partial")
                val scanStatus = result.optString("status").uppercase()
                val status = when (scanStatus) {
                    SafScanner.STATUS_REVOKED, SafScanner.STATUS_UNAVAILABLE -> NativeIndex.STATUS_UNAVAILABLE
                    SafScanner.STATUS_CANCELLED -> NativeIndex.STATUS_CANCELLED
                    SafScanner.STATUS_PARTIAL -> NativeIndex.STATUS_PARTIAL
                    SafScanner.STATUS_EMPTY_COMPLETE -> NativeIndex.STATUS_EMPTY_COMPLETE
                    else -> NativeIndex.STATUS_COMPLETED
                }
                val finished = NativeIndex.finishGeneration(
                    appContext,
                    NativeIndex.SOURCE_SAF,
                    scanKey,
                    generationId,
                    status,
                    JSONObject()
                        .put("treeUri", reference)
                        .put("stats", result.optJSONObject("stats") ?: JSONObject())
                        .put("status", status)
                        .put("scanId", scanId),
                )
                result.put("scanGeneration", generationId)
                    .put("generationId", NativeIndex.generationId(NativeIndex.SOURCE_SAF, scanKey, generationId))
                    .put("generationStatus", status)
                    .put("batchCount", finished.optInt("batchCount", 0))
                    .put("processed", finished.optInt("processed", 0))
                    .put("nativeDuplicates", finished.optInt("duplicates", 0))
                    .put("requestId", requestId ?: "")
                    .put("scanId", scanId)
                    .put("scopeKind", "root")
                    .put("scopeRef", reference)
                    .put("source", "saf")
                    .put("scope", SafScanner.treeIdentity(treeUri).identity)
                    .put("volumeId", result.optString("volumeId"))
                    .put("status", scanStatus.ifBlank { SafScanner.STATUS_COMPLETED })
                NativeMailbox.writeOrThrow(appContext, JSONObject().put("type", "saf_scan").put("requestId", requestId ?: "").put("payload", result))
            } catch (exception: Exception) {
                Log.e(tag, "SAF scan failed", exception)
                NativeIndex.failGeneration(appContext, NativeIndex.SOURCE_SAF, scanKey, generationId,
                    exception.message ?: "SAF scan failed",
                    JSONObject().put("treeUri", reference))
                NativeMailbox.write(appContext, JSONObject().put("type", "saf_error")
                    .put("requestId", requestId ?: "")
                    .put("message", "Não foi possível atualizar esta pasta autorizada.")
                    .put("payload", SafScanner.identityPayload(treeUri).put("scanId", scanId)
                        .put("generationId", "native:" + generationId).put("status", NativeIndex.STATUS_FAILED)
                        .put("source", "saf")))
            } finally {
                NativeScanController.finish(scanId)
                synchronized(activeNativeScanJobs) { activeNativeScanJobs.remove(scanId) }
            }
        }
        synchronized(activeNativeScanJobs) { activeNativeScanJobs[scanId] = job }
    }
    private fun requestMediaAccess() {
        if (!activityResumed) {
            // queueLifecycleAction("request_media_access") remains the lifecycle contract;
            // the overload additionally carries the request correlation id.
            nativeRequestState.queueLifecycleAction("request_media_access", pendingMediaRequestId)
            Log.i(tag, "Deferring media permission request until Activity is resumed")
            return
        }
        if (mediaPermissionRequestPending) {
            Log.i(tag, "Media permission request already pending")
            return
        }
        val currentAccess = MediaStoreScanner.accessLevel(this)
        if (currentAccess != "denied") {
            Log.i(tag, "Media access already present; continuing directly to scan access=" + currentAccess)
            NativeMailbox.write(this, JSONObject().put("type", "mediastore_permission")
                .put("requestId", pendingMediaRequestId ?: "")
                .put("payload", JSONObject()
                    .put("granted", true)
                    .put("access", currentAccess)
                    .put("source", MediaStoreScanner.SOURCE)
                    .put("capabilities", storageCapabilitiesPayload(StorageLifecycleState.REVALIDATED))))
            // Existing access must converge to the same permission -> scan -> index -> mailbox path.
            val requestId = pendingMediaRequestId
            pendingMediaRequestId = null
            publishScanRequest("PERMISSION_CHANGE", "mediastore", null, false, "media_permission_already_granted", requestId)
            return
        }
        val permissions = MediaStoreScanner.requiredPermissions()
        if (permissions.isEmpty()) {
            NativeMailbox.write(this, JSONObject().put("type", "mediastore_error")
                .put("requestId", pendingMediaRequestId ?: "")
                .put("message", "Este Android não disponibiliza permissão de leitura de vídeos.")
                .put("payload", JSONObject().put("source", MediaStoreScanner.SOURCE)))
            return
        }
        mediaPermissionRequestPending = true
        NativeMailbox.write(this, JSONObject().put("type", "mediastore_permission_request")
            .put("requestId", pendingMediaRequestId ?: "")
            .put("payload", JSONObject()
                .put("source", MediaStoreScanner.SOURCE)
                .put("state", "requesting")
                .put("capabilities", storageCapabilitiesPayload(StorageLifecycleState.REQUESTING))))
        try {
            mediaPermissionRequester.launch(permissions)
        } catch (exception: Exception) {
            mediaPermissionRequestPending = false
            pendingMediaRequestId = null
            Log.e(tag, "Media permission launcher failed", exception)
            NativeMailbox.write(this, JSONObject().put("type", "mediastore_error")
                .put("message", "Não foi possível abrir a solicitação de permissão para vídeos.")
                .put("payload", JSONObject().put("source", MediaStoreScanner.SOURCE)))
        }
    }

    private fun publishStorageStatus() {
        val broadAccess = BroadStorageScanner.accessSnapshot(this)
        val mediaAccess = MediaStoreScanner.accessLevel(this)
        val broadGranted = BroadStorageScanner.hasAccess(this)
        val capabilities = storageCapabilitiesPayload(StorageLifecycleState.REVALIDATED)
        NativeMailbox.write(
            this,
            JSONObject().put("type", "broad_storage_status")
                .put("payload", broadAccess)
                .put("diagnostics", JSONObject()
                    .put("activity", javaClass.name)
                    .put("taskId", taskId)
                    .put("lifecycle", if (activityResumed) "RESUMED" else "PAUSED")
                    .put("permissionState", if (broadGranted) "BROAD_STORAGE_AVAILABLE" else "BROAD_STORAGE_UNAVAILABLE")
                    .put("capabilities", capabilities))
        )
        NativeMailbox.write(
            this,
            JSONObject().put("type", "mediastore_permission")
                .put("payload", JSONObject()
                    .put("granted", mediaAccess != "denied")
                    .put("access", mediaAccess)
                    .put("source", MediaStoreScanner.SOURCE)
                    .put("capabilities", capabilities))
                .put("diagnostics", JSONObject()
                    .put("activity", javaClass.name)
                    .put("taskId", taskId)
                    .put("lifecycle", if (activityResumed) "RESUMED" else "PAUSED")
                    .put("permissionState", when (mediaAccess) {
                        "full" -> "MEDIA_FULL"
                        "partial" -> "MEDIA_PARTIAL"
                        else -> "MEDIA_DENIED"
                    }))
        )
        val volumeChanges = NativeIndex.updateVolumeSnapshot(this, NativeIndex.volumeSnapshot(this))
        if (volumeChanges.optBoolean("changed")) {
            NativeMailbox.write(this, JSONObject().put("type","volume_changed").put("payload",
                JSONObject(volumeChanges.toString())
                    .put("source", "android_storage")
                    .put("reason", "lifecycle")
                    .put("timestamp", System.currentTimeMillis())))
        }
        NativeMailbox.write(this, JSONObject().put("type", "storage_capabilities").put("payload", capabilities))
        publishSafInventory()
    }

    /**
     * Publish the authoritative SAF grant set after Activity resume/recreation.
     *
     * Python previously tried to verify every persisted tree by launching the
     * app's own reiflix://native intent during startup. That is an avoidable
     * task/lifecycle transition: with MainActivity singleTask, Android may
     * bring the existing task to the foreground and route the new intent to
     * onNewIntent(). The native Activity already owns the persisted grant set,
     * so publish it directly through the existing NativeMailbox instead.
     */
    private fun publishSafInventory() {
        if (safInventoryRunning) return
        safInventoryRunning = true
        val appContext = applicationContext
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val trees = JSONArray()
                val permissions = appContext.contentResolver.persistedUriPermissions
                    .asSequence()
                    .filter { it.isReadPermission }
                    .map { it.uri }
                    .filter { it.scheme == "content" && DocumentsContract.isTreeUri(it) }
                    .distinct()
                    .sortedBy { it.toString() }
                    .toList()
                for (uri in permissions) {
                    val inspection = SafScanner.inspectTree(appContext, uri, requirePersisted = true)
                    trees.put(inspection.put("persisted", true))
                }
                NativeMailbox.write(appContext, JSONObject().put("type", "saf_inventory")
                    .put("payload", JSONObject()
                        .put("trees", trees)
                        .put("count", trees.length())
                        .put("inventoryComplete", true)
                        .put("lifecycle", if (activityResumed) "RESUMED" else "PAUSED")))
            } catch (exception: Exception) {
                Log.e(tag, "SAF inventory failed", exception)
                NativeMailbox.write(appContext, JSONObject().put("type", "saf_error")
                    .put("message", "Não foi possível validar as pastas SAF persistidas.")
                    .put("payload", JSONObject().put("source", "saf").put("status", SafScanner.STATUS_UNAVAILABLE)
                        .put("stage", "inventory")))
            } finally {
                safInventoryRunning = false
            }
        }
    }
    private fun handleBroadSettingsReturn(requestId: String?, origin: String) {
        if (!broadStoragePermissionPending) {
            Log.i(tag, "SETTINGS_RETURN ignored kind=broad_storage origin=" + origin + " reason=no_pending_request")
            return
        }
        broadStoragePermissionPending = false
        val resolvedRequestId = requestId ?: pendingBroadRequestId
        pendingBroadRequestId = null
        val granted = BroadStorageScanner.hasAccess(this)
        Log.i(
            tag,
            "SETTINGS_RETURN kind=broad_storage origin=" + origin +
                " granted=" + granted +
                " requestId=" + (resolvedRequestId ?: "-"),
        )
        NativeMailbox.write(
            this,
            JSONObject().put("type", "broad_storage_permission")
                .put("requestId", resolvedRequestId ?: "")
                .put("payload", JSONObject()
                    .put("granted", granted)
                    .put("source", BroadStorageScanner.SOURCE)
                    .put("revalidatedAfterSettings", true)
                    .put("capabilities", storageCapabilitiesPayload(StorageLifecycleState.RETURNED)))
        )
        if (granted) {
            publishScanRequest("PERMISSION_CHANGE", "broad_storage", null, false, "broad_storage_settings_return", resolvedRequestId)
        }
        publishStorageCapabilities(StorageLifecycleState.REVALIDATED)
    }

    private fun launchExternalSettings(kind: String, requestId: String?, intents: List<Pair<String, Intent>>): Boolean {
        if (!activityResumed) {
            Log.i(tag, "Deferring external Settings launch kind=" + kind + " until Activity is resumed")
            return false
        }
        if (externalSettingsKind != null) {
            Log.i(tag, "External Settings already active kind=" + externalSettingsKind)
            return false
        }
        for ((label, intent) in intents) {
            externalSettingsKind = kind
            externalSettingsRequestId = requestId
            var launched = false
            try {
                Log.i(tag, "SETTINGS_LAUNCH kind=" + kind + " label=" + label + " requestId=" + (requestId ?: "-"))
                externalSettingsLauncher.launch(intent)
                launched = true
                return true
            } catch (exception: ActivityNotFoundException) {
                Log.w(tag, "Settings intent unavailable label=" + label, exception)
            } catch (exception: SecurityException) {
                Log.w(tag, "Settings intent blocked label=" + label, exception)
            } catch (exception: Exception) {
                Log.w(tag, "Settings intent failed label=" + label, exception)
            } finally {
                if (!launched) {
                    externalSettingsKind = null
                    externalSettingsRequestId = null
                }
            }
        }
        return false
    }

    private fun openBroadStorageSettings() {
        if (!activityResumed) {
            nativeRequestState.queueLifecycleAction("open_broad_storage_settings", pendingBroadRequestId)
            Log.i(tag, "Deferring broad-storage Settings launch until Activity is resumed")
            return
        }
        val requestId = pendingBroadRequestId
        if (BroadStorageScanner.hasAccess(this)) {
            pendingBroadRequestId = null
            NativeMailbox.write(
                this,
                JSONObject().put("type", "broad_storage_permission")
                    .put("requestId", requestId ?: "")
                    .put("payload", JSONObject()
                        .put("granted", true)
                        .put("source", BroadStorageScanner.SOURCE)
                        .put("revalidatedAfterSettings", true)
                        .put("capabilities", storageCapabilitiesPayload(StorageLifecycleState.REVALIDATED)))
            )
            publishScanRequest("PERMISSION_CHANGE", "broad_storage", null, false, "broad_storage_already_granted", requestId)
            publishStorageCapabilities(StorageLifecycleState.REVALIDATED)
            return
        }
        if (Build.VERSION.SDK_INT < 30) {
            broadStoragePermissionPending = false
            pendingBroadRequestId = null
            NativeMailbox.write(this, JSONObject().put("type", "broad_storage_error")
                .put("message", "A varredura Broad Storage exige Android 11 (API 30) ou superior, onde o Android expõe a autoridade MANAGE_EXTERNAL_STORAGE.")
                .put("payload", JSONObject()
                    .put("source", BroadStorageScanner.SOURCE)
                    .put("status", "UNAVAILABLE")
                    .put("reason", "manage_external_storage_not_available")
                    .put("api", Build.VERSION.SDK_INT)
                    .put("permissionAuthority", "Environment.isExternalStorageManager")))
            return
        }

        broadStoragePermissionPending = true
        NativeMailbox.write(
            this,
            JSONObject().put("type", "broad_storage_permission_request")
                .put("requestId", requestId ?: "")
                .put("payload", JSONObject()
                    .put("source", BroadStorageScanner.SOURCE)
                    .put("state", "requesting")
                    .put("capabilities", storageCapabilitiesPayload(StorageLifecycleState.REQUESTING)))
        )

        val launched = launchExternalSettings(
            "broad_storage",
            requestId,
            listOf(
                "app_specific_all_files" to Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
                    .setData(Uri.parse("package:$packageName")),
                "global_all_files" to Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION),
                "app_details" to Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                    .setData(Uri.parse("package:$packageName")),
            ),
        )
        if (!launched) {
            broadStoragePermissionPending = false
            pendingBroadRequestId = null
            NativeMailbox.write(this, JSONObject().put("type", "broad_storage_error")
                .put("message", "O Android não conseguiu abrir diretamente a tela de acesso amplo. Abra as configurações do aplicativo e procure por acesso a todos os arquivos.")
                .put("payload", JSONObject()
                    .put("api", Build.VERSION.SDK_INT)
                    .put("specificIntent", Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
                    .put("globalIntent", Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION)
                    .put("appDetailsIntent", Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                    .put("hasAccess", BroadStorageScanner.hasAccess(this))
                    .put("fallbackOpened", false)
                    .put("source", BroadStorageScanner.SOURCE)))
        } else {
            Log.i(tag, "SETTINGS_LAUNCH accepted kind=broad_storage requestId=" + (requestId ?: "-"))
        }
    }

    private fun scanAllStorage(requestId: String? = null) {
        val scanId = UUID.randomUUID().toString()
        if (!BroadStorageScanner.hasAccess(this)) {
            publishStorageStatus()
            NativeMailbox.write(this, JSONObject().put("type", "broad_storage_permission")
                .put("requestId", requestId ?: "")
                .put("payload", JSONObject().put("granted", false).put("source", BroadStorageScanner.SOURCE)))
            return
        }
        NativeMailbox.write(this, JSONObject().put("type", "broad_storage_permission")
            .put("requestId", requestId ?: "")
            .put("payload", JSONObject().put("granted", true).put("source", BroadStorageScanner.SOURCE)))
        if (!NativeScanController.begin(scanId, BroadStorageScanner.SOURCE)) {
            NativeMailbox.write(this, JSONObject().put("type", "broad_storage_scan_progress")
                .put("payload", JSONObject().put("source", BroadStorageScanner.SOURCE).put("requestId", requestId ?: "").put("phase", "already_running")))
            return
        }
        val appContext = applicationContext
        val job = CoroutineScope(Dispatchers.IO).launch {
            try {
                val result = BroadStorageScanner.scan(
                    appContext,
                    { progress ->
                        NativeMailbox.write(appContext, JSONObject().put("type", "broad_storage_scan_progress")
                            .put("payload", progress.put("scanId", scanId).put("requestId", requestId ?: "").put("scopeKind", "global")))
                    },
                    { NativeScanController.isCancelled(scanId) },
                    scanId,
                ) { batch ->
                    val volume = batch.optString("volumeId")
                    publishNativeScanBatch(
                        appContext,
                        "broad_storage_scan_batch",
                        "broad_storage",
                        scanId,
                        requestId,
                        "volume",
                        volume,
                        "broad-storage:" + volume,
                        batch.optLong("generation", 0L),
                        batch,
                    )
                }
                val partial = result.optBoolean("partial")
                result.put("requestId", requestId ?: "")
                    .put("scanId", scanId).put("scopeKind", "global").put("scopeRef", "broad-storage")
                    .put("generationId", "native-scoped")
                    .put("generationStatus", if (result.optBoolean("cancelled")) NativeIndex.STATUS_CANCELLED else if (partial) NativeIndex.STATUS_PARTIAL else NativeIndex.STATUS_COMPLETED)
                NativeMailbox.writeOrThrow(appContext, JSONObject().put("type", "broad_storage_scan")
                    .put("requestId", requestId ?: "").put("payload", result))
            } catch (exception: Exception) {
                Log.e(tag, "Broad storage scan failed", exception)
                NativeIndex.failActiveGenerations(
                    appContext,
                    NativeIndex.SOURCE_BROAD,
                    exception.message ?: "Broad storage scan failed",
                )
                NativeMailbox.write(appContext, JSONObject().put("type", "broad_storage_error")
                    .put("requestId", requestId ?: "")
                    .put("message", "Não foi possível concluir a varredura do armazenamento local.")
                    .put("payload", JSONObject()
                        .put("source", BroadStorageScanner.SOURCE)
                        .put("scanId", scanId)
                        .put("status", NativeIndex.STATUS_FAILED)
                        .put("generationStatus", NativeIndex.STATUS_FAILED)
                        .put("partial", true)
                        .put("errorType", exception::class.java.simpleName)
                        .put("error", exception.message ?: "Broad storage scan failed")))
            } finally {
                NativeScanController.finish(scanId)
                synchronized(activeNativeScanJobs) { activeNativeScanJobs.remove(scanId) }
            }
        }
        synchronized(activeNativeScanJobs) { activeNativeScanJobs[scanId] = job }
    }

    private fun scanMediaStore(requestId: String? = null) {
        MediaStoreScanner.clearChangeNotification()
        val scanId = UUID.randomUUID().toString()
        if (!MediaStoreScanner.hasReadPermission(this)) {
            publishStorageStatus()
            NativeMailbox.write(this, JSONObject().put("type", "mediastore_error")
                .put("requestId", requestId ?: "")
                .put("message", "A permissão para ler vídeos ainda não foi concedida.")
                .put("payload", JSONObject().put("source", MediaStoreScanner.SOURCE).put("status", "DENIED").put("access", "denied")))
            return
        }
        if (!NativeScanController.begin(scanId, MediaStoreScanner.SOURCE)) {
            NativeMailbox.write(this, JSONObject().put("type", "mediastore_scan_progress")
                .put("payload", JSONObject().put("source", MediaStoreScanner.SOURCE).put("requestId", requestId ?: "").put("phase", "already_running")))
            return
        }
        val appContext = applicationContext
        val job = CoroutineScope(Dispatchers.IO).launch {
            try {
                NativeMailbox.write(appContext, JSONObject().put("type", "mediastore_scan_progress")
                    .put("payload", JSONObject().put("source", MediaStoreScanner.SOURCE).put("scanId", scanId)
                        .put("requestId", requestId ?: "").put("phase", "started")))
                val result = MediaStoreScanner.scan(
                    appContext,
                    { progress ->
                        NativeMailbox.write(appContext, JSONObject().put("type", "mediastore_scan_progress")
                            .put("payload", progress.put("scanId", scanId).put("requestId", requestId ?: "").put("scopeKind", "global")))
                    },
                    { NativeScanController.isCancelled(scanId) },
                    scanId,
                ) { batch ->
                    val volume = batch.optString("volumeId")
                    publishNativeScanBatch(
                        appContext,
                        "mediastore_scan_batch",
                        "mediastore",
                        scanId,
                        requestId,
                        "volume",
                        volume,
                        "mediastore:" + volume,
                        batch.optLong("generation", NativeIndex.cachedGeneration(appContext, "mediastore:" + volume)),
                        batch,
                    )
                }
                result.put("requestId", requestId ?: "").put("scanId", scanId)
                    .put("scopeKind", "global").put("scopeRef", MediaStoreScanner.SOURCE)
                val finalStatus = result.optJSONObject("stats")?.optString("status").orEmpty().uppercase()
                if (finalStatus == NativeIndex.STATUS_WAITING_FOR_MEDIASTORE) {
                    NativeMailbox.write(appContext, JSONObject().put("type", "diagnostic")
                        .put("payload", JSONObject().put("event", "WAITING_FOR_MEDIASTORE").put("scanId", scanId).put("requestId", requestId ?: "")))
                    mediaStoreRescanHandler.postDelayed({
                        if (activityResumed && MediaStoreScanner.hasReadPermission(this@MainActivity)) {
                            publishScanRequest(
                                "MEDIASTORE_CHANGE",
                                source = "mediastore",
                                full = false,
                                reason = "media_store_indexing_completed",
                                triggerRequestId = requestId,
                            )
                        }
                    }, 900L)
                }
                NativeMailbox.writeOrThrow(appContext, JSONObject().put("type", "mediastore_scan")
                    .put("requestId", requestId ?: "").put("payload", result))
            } catch (exception: Exception) {
                Log.e(tag, "MediaStore scan failed", exception)
                NativeIndex.failActiveGenerations(appContext, NativeIndex.SOURCE_MEDIASTORE, exception.message ?: "MediaStore scan failed")
                NativeMailbox.write(appContext, JSONObject().put("type", "mediastore_error")
                    .put("requestId", requestId ?: "")
                    .put("message", "Não foi possível atualizar os vídeos do dispositivo.")
                    .put("payload", JSONObject()
                        .put("source", MediaStoreScanner.SOURCE)
                        .put("scanId", scanId)
                        .put("status", NativeIndex.STATUS_FAILED)
                        .put("access", MediaStoreScanner.accessLevel(appContext))))
            } finally {
                NativeScanController.finish(scanId)
                synchronized(activeNativeScanJobs) { activeNativeScanJobs.remove(scanId) }
            }
        }
        synchronized(activeNativeScanJobs) { activeNativeScanJobs[scanId] = job }
    }

    private fun cancelNativeScans(requestId: String? = null) {
        val ids = NativeScanController.cancelAll()
        // Do not cancel the coroutine immediately: scanners need to observe the flag,
        // emit a final CANCELLED generation, and keep the last good snapshot intact.
        NativeMailbox.write(this, JSONObject().put("type", "scan_cancel_requested").put("requestId", requestId ?: "")
            .put("payload", JSONObject().put("scanIds", JSONArray(ids)).put("count", ids.size)
                .put("status", NativeIndex.STATUS_CANCELLED)))
    }
    private fun requestThumbnail(data: Uri?, requestId: String?) {
        val source = data ?: return
        val raw = source.getQueryParameter("uri")?.trim().orEmpty()
        if (raw.isBlank()) return
        val localUri = runCatching { Uri.parse(raw) }.getOrNull()
        if (localUri == null || !(
            (localUri.scheme == "content" &&
                (SafScanner.isAuthorizedDocument(this, localUri) || MediaStoreScanner.isAuthorizedDocument(this, localUri))) ||
            (localUri.scheme == "file" && BroadStorageScanner.isAuthorizedFile(this, localUri))
        )) {
            NativeMailbox.write(this, JSONObject().put("type", "thumbnail_error")
                .put("requestId", requestId ?: "")
                .put("message", "A mídia local não está autorizada para extração de capa.")
                .put("payload", JSONObject().put("uri", raw).put("status", "UNAUTHORIZED")))
            return
        }

        val size = source.getQueryParameter("size")?.toLongOrNull()?.coerceAtLeast(0L) ?: 0L
        val modifiedAt = source.getQueryParameter("modified_at")?.toLongOrNull()?.coerceAtLeast(0L) ?: 0L
        val appContext = applicationContext
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val thumbnailPath = VideoThumbnailExtractor.extract(appContext, localUri, size, modifiedAt)
                if (thumbnailPath.isNullOrBlank()) {
                    NativeMailbox.write(appContext, JSONObject().put("type", "thumbnail_error")
                        .put("requestId", requestId ?: "")
                        .put("message", "Não foi possível extrair uma miniatura deste vídeo.")
                        .put("payload", JSONObject().put("uri", raw).put("size", size).put("modifiedAt", modifiedAt).put("status", "EXTRACTION_FAILED")))
                    return@launch
                }
                NativeMailbox.write(appContext, JSONObject().put("type", "thumbnail_ready")
                    .put("requestId", requestId ?: "")
                    .put("payload", JSONObject()
                        .put("uri", raw)
                        .put("thumbnailPath", thumbnailPath)
                        .put("size", size)
                        .put("modifiedAt", modifiedAt)
                        .put("source", "media_metadata_retriever")))
            } catch (exception: Exception) {
                Log.e(tag, "Thumbnail extraction failed", exception)
                NativeMailbox.write(appContext, JSONObject().put("type", "thumbnail_error")
                    .put("requestId", requestId ?: "")
                    .put("message", "Não foi possível gerar a miniatura do vídeo.")
                    .put("payload", JSONObject().put("uri", raw).put("status", "EXTRACTION_FAILED").put("error", exception.message ?: "")))
            }
        }
    }

    private fun releaseTree(reference: String?) {
        if (reference.isNullOrBlank()) return
        val treeUri = Uri.parse(reference)
        try {
            contentResolver.releasePersistableUriPermission(
                treeUri,
                Intent.FLAG_GRANT_READ_URI_PERMISSION
            )
            Log.i(tag, "SAF permission released")
            NativeMailbox.write(this, JSONObject().put("type", "saf_released")
                .put("payload", JSONObject().put("treeUri", reference)))
        } catch (exception: Exception) {
            Log.e(tag, "Failed to release SAF permission", exception)
            NativeMailbox.write(this, JSONObject().put("type", "saf_error")
                .put("message", "Não foi possível liberar a permissão desta pasta.")
                .put("payload", JSONObject().put("treeUri", reference)))
        }
    }
    private fun verifyTree(reference: String?) {
        if (reference.isNullOrBlank()) return
        val uri = runCatching { Uri.parse(reference) }.getOrNull()
        if (uri == null) return
        val inspection = SafScanner.inspectTree(this, uri, requirePersisted = true)
        val status = inspection.optString("status")
        Log.i(tag, "SAF permission verification: status=" + status + " uri=" + reference)
        if (status == SafScanner.STATUS_COMPLETED) {
            NativeMailbox.write(this, JSONObject().put("type", "saf_permission")
                .put("payload", inspection.put("granted", true).put("selected", false).put("status", status)))
        } else {
            NativeMailbox.write(this, JSONObject().put("type", "saf_error")
                .put("message", when (status) {
                    SafScanner.STATUS_REVOKED -> "A autorização desta pasta foi removida."
                    SafScanner.STATUS_UNAVAILABLE -> "O provedor desta pasta está indisponível no momento."
                    else -> "Não foi possível validar esta pasta SAF."
                })
                .put("payload", inspection.put("status", status)))
        }
    }
    private fun openPlayer(data: Uri?) {
        val source = data ?: return
        val episodeUri = source.getQueryParameter("uri")?.trim().orEmpty()
        val requestId = source.getQueryParameter("request_id")?.trim().orEmpty()
        if (episodeUri.isBlank()) {
            Log.e(tag, "PLAY_HANDOFF_FAILED requestId=" + requestId + " reason=missing_uri")
            NativeMailbox.write(this, JSONObject().put("type", "player_error")
                .put("requestId", requestId)
                .put("message", "Este episódio não possui uma referência local válida.")
                .put("payload", JSONObject().put("stage", "handoff").put("reason", "missing_uri")))
            return
        }

        val localUri = runCatching { Uri.parse(episodeUri) }.getOrNull()
        if (localUri == null || localUri.scheme?.lowercase() !in setOf("content", "file")) {
            Log.e(tag, "PLAY_HANDOFF_FAILED requestId=" + requestId + " uri=" + episodeUri + " reason=unsupported_scheme")
            NativeMailbox.write(this, JSONObject().put("type", "player_error")
                .put("requestId", requestId)
                .put("message", "O Rei-Flix aceita somente mídias locais autorizadas.")
                .put("payload", JSONObject().put("uri", episodeUri).put("stage", "handoff").put("reason", "unsupported_scheme")))
            return
        }

        val authority = localUri.authority.orEmpty()
        val authorized = when {
            localUri.scheme.equals("content", true) -> {
                SafScanner.isAuthorizedDocument(this, localUri) ||
                    MediaStoreScanner.isAuthorizedDocument(this, localUri)
            }
            localUri.scheme.equals("file", true) -> BroadStorageScanner.isAuthorizedFile(this, localUri)
            else -> false
        }
        if (!authorized) {
            Log.e(tag, "PLAY_HANDOFF_FAILED requestId=$requestId uri=$episodeUri reason=unauthorized")
            NativeMailbox.write(this, JSONObject().put("type", "player_error")
                .put("requestId", requestId)
                .put("message", "Este arquivo local não está mais autorizado.")
                .put("payload", JSONObject().put("uri", episodeUri).put("stage", "handoff").put("reason", "unauthorized")))
            return
        }

        val preflightError = validatePlayerSource(localUri)
        if (preflightError != null) {
            Log.e(tag, "PLAY_HANDOFF_FAILED requestId=$requestId reason=preflight error=$preflightError")
            NativeMailbox.write(this, JSONObject().put("type", "player_error")
                .put("requestId", requestId)
                .put("message", "O arquivo local não está disponível para reprodução.")
                .put("payload", JSONObject()
                    .put("uri", episodeUri)
                    .put("stage", "preflight")
                    .put("reason", preflightError)))
            return
        }

        val mediaSource = when {
            localUri.scheme.equals("content", true) && authority == MediaStore.AUTHORITY -> "mediastore"
            localUri.scheme.equals("content", true) -> "saf_or_local_provider"
            else -> "broad_storage"
        }
        Log.i(tag, "PLAY_HANDOFF requestId=" + requestId.ifEmpty { "-" } +
            " uri_original=" + episodeUri + " uri_normalized=" + localUri +
            " scheme=" + localUri.scheme + " authority=" + authority.ifEmpty { "-" } +
            " source=" + mediaSource + " activityResumed=" + activityResumed + " task=" + taskId)

        val previousActiveRequestId = activePlayerRequestId
        val reusingPlayerActivity = !previousActiveRequestId.isNullOrBlank()
        if (reusingPlayerActivity && previousActiveRequestId == requestId && requestId.isNotBlank()) {
            Log.i(tag, "PLAY_HANDOFF_DUPLICATE requestId=$requestId ignored=true")
            return
        }

        activePlayerRequestId = requestId.takeIf { it.isNotBlank() }
        Log.i(
            tag,
            "PLAY_HANDOFF_ACCEPTED requestId=" + requestId.ifEmpty { "-" } +
                " reusePlayerActivity=" + reusingPlayerActivity,
        )

        try {
            val intent = Intent(this, NativePlayerActivity::class.java)
                .putExtra("requestId", requestId)
                .putExtra("uri", localUri.toString())
                .putExtra("mediaId", localUri.toString())
                .putExtra("episodeId", source.getQueryParameter("episode_id").orEmpty())
                .putExtra("title", source.getQueryParameter("title") ?: "Episódio")
                .putExtra("positionMs", source.getQueryParameter("position_ms")?.toLongOrNull()?.coerceAtLeast(0L) ?: 0L)
                .putExtra("canNext", source.getQueryParameter("can_next")?.toBooleanStrictOrNull() ?: false)
                .putExtra("canPrevious", source.getQueryParameter("can_previous")?.toBooleanStrictOrNull() ?: false)
                .putExtra("autoplay", source.getQueryParameter("autoplay")?.toBooleanStrictOrNull() ?: true)
                .putExtra("setting_player_default_speed", source.getQueryParameter("setting_player_default_speed")?.toFloatOrNull() ?: 1f)
                .putExtra("setting_player_aspect_ratio", source.getQueryParameter("setting_player_aspect_ratio") ?: "fit")
                .putExtra("setting_player_immersive", source.getQueryParameter("setting_player_immersive") ?: "always")
                .putExtra("setting_player_rotation", source.getQueryParameter("setting_player_rotation") ?: "auto")
                .putExtra("setting_player_pip", source.getQueryParameter("setting_player_pip")?.toBooleanStrictOrNull() ?: true)
                .putExtra("setting_player_auto_hide_seconds", source.getQueryParameter("setting_player_auto_hide_seconds")?.toIntOrNull() ?: 5)
                .putExtra("setting_player_double_tap_seek_seconds", source.getQueryParameter("setting_player_double_tap_seek_seconds")?.toLongOrNull() ?: 10L)
                .putExtra("setting_player_long_press_speed", source.getQueryParameter("setting_player_long_press_speed")?.toFloatOrNull() ?: 2f)
                .putExtra("setting_player_max_video_resolution", source.getQueryParameter("setting_player_max_video_resolution") ?: "auto")
                .putExtra("setting_player_max_video_frame_rate", source.getQueryParameter("setting_player_max_video_frame_rate")?.toIntOrNull() ?: 0)
                .putExtra("setting_player_max_audio_channels", source.getQueryParameter("setting_player_max_audio_channels")?.toIntOrNull() ?: 0)
                .putExtra("setting_gestures_volume", source.getQueryParameter("setting_gestures_volume")?.toBooleanStrictOrNull() ?: false)
                .putExtra("setting_gestures_brightness", source.getQueryParameter("setting_gestures_brightness")?.toBooleanStrictOrNull() ?: false)
                .putExtra("setting_gestures_double_tap", source.getQueryParameter("setting_gestures_double_tap")?.toBooleanStrictOrNull() ?: false)
                .putExtra("setting_gestures_long_press", source.getQueryParameter("setting_gestures_long_press")?.toBooleanStrictOrNull() ?: false)
                .putExtra("setting_audio_preferred_language", source.getQueryParameter("setting_audio_preferred_language").orEmpty())
                .putExtra("setting_audio_preferred_subtitle_language", source.getQueryParameter("setting_audio_preferred_subtitle_language").orEmpty())
                .putExtra("setting_audio_subtitles", source.getQueryParameter("setting_audio_subtitles") ?: "auto")
                .putExtra("setting_audio_subtitle_scale", source.getQueryParameter("setting_audio_subtitle_scale")?.toFloatOrNull() ?: 1f)
                .putExtra("setting_audio_subtitle_bottom_padding", source.getQueryParameter("setting_audio_subtitle_bottom_padding")?.toIntOrNull() ?: 8)
                .putExtra("setting_audio_subtitle_embedded_style", source.getQueryParameter("setting_audio_subtitle_embedded_style")?.toBooleanStrictOrNull() ?: true)

            val resolvedActivity = intent.resolveActivity(packageManager)
            if (resolvedActivity == null) {
                activePlayerRequestId = previousActiveRequestId
                Log.e(
                    tag,
                    "PLAY_HANDOFF_FAILED requestId=" + requestId.ifEmpty { "-" } +
                        " reason=activity_not_resolvable component=" + intent.component,
                )
                NativeMailbox.write(
                    this,
                    JSONObject()
                        .put("type", "player_error")
                        .put("requestId", requestId)
                        .put("message", "O player nativo não está disponível nesta instalação.")
                        .put(
                            "payload",
                            JSONObject()
                                .put("stage", "resolve_intent")
                                .put("reason", "activity_not_resolvable")
                                .put("component", intent.component?.flattenToShortString() ?: ""),
                        ),
                )
                return
            }
            Log.i(
                tag,
                "PLAY_INTENT_RESOLVED requestId=" + requestId.ifEmpty { "-" } +
                    " resolved=" + resolvedActivity.flattenToShortString() +
                    " flags=0x" + intent.flags.toString(16) +
                    " reuse=" + reusingPlayerActivity,
            )
            NativeMailbox.write(
                this,
                JSONObject()
                    .put("type", "diagnostic")
                    .put("requestId", requestId)
                    .put(
                        "payload",
                        JSONObject()
                            .put("event", "PLAYER_HANDOFF_START")
                            .put("stage", "start_activity")
                            .put("uri", localUri.toString())
                            .put("component", resolvedActivity.flattenToShortString())
                            .put("reuse", reusingPlayerActivity),
                    ),
            )
            Log.i(tag, "PLAY_HANDOFF_START requestId=" + requestId.ifEmpty { "-" } + " component=" + intent.component)

            if (reusingPlayerActivity) {
            if (reusingPlayerActivity) {
                startActivity(
                    intent.addFlags(
                        Intent.FLAG_ACTIVITY_SINGLE_TOP or
                            Intent.FLAG_ACTIVITY_REORDER_TO_FRONT,
                    ),
                )
            } else {
                playerActivityLauncher.launch(intent)
                Log.i(
                    tag,
                    "PLAY_HANDOFF_DISPATCHED requestId=" + requestId.ifEmpty { "-" } +
                        " launcher=activity_result",
                )
            }
        } catch (exception: Exception) {
            activePlayerRequestId = previousActiveRequestId
            Log.e(tag, "PLAY_HANDOFF_FAILED requestId=" + requestId.ifEmpty { "-" } + " reason=start_activity", exception)
            NativeMailbox.write(this, JSONObject().put("type", "player_error")
                .put("requestId", requestId)
                .put("message", "Não foi possível abrir o player local.")
                .put("payload", JSONObject()
                    .put("uri", localUri.toString())
                    .put("stage", "start_activity")
                    .put("error", exception.message ?: exception::class.java.simpleName)))
        }
    }

    private fun validatePlayerSource(uri: Uri): String? {
        return try {
            when {
                uri.scheme.equals("file", true) -> {
                    val file = java.io.File(uri.path.orEmpty())
                    when {
                        !file.isFile -> "file_not_found"
                        !file.canRead() -> "file_not_readable"
                        file.length() <= 0L -> "file_empty"
                        else -> null
                    }
                }
                uri.scheme.equals("content", true) -> {
                    val mime = contentResolver.getType(uri)
                    if (!mime.isNullOrBlank() && !mime.startsWith("video/", ignoreCase = true) &&
                        mime != "application/octet-stream"
                    ) {
                        return "mime_not_video"
                    }
                    contentResolver.openFileDescriptor(uri, "r")?.use { descriptor ->
                        val statSize = descriptor.statSize
                        if (statSize == 0L) "file_empty" else null
                    } ?: "file_open_failed"
                }
                else -> "unsupported_scheme"
            }
        } catch (exception: SecurityException) {
            "permission_denied"
        } catch (exception: Exception) {
            "preflight_exception"
        }
    }

    private fun clearPendingPlay() {
        pendingPlayUri = null
        pendingPlayTitle = null
        pendingPlayPositionMs = 0L
        pendingPlayCanNext = false
        pendingPlayCanPrevious = false
        pendingPlayAutoplay = true
        pendingPlayRequestId = null
    }

    private fun openTreePicker() {
        if (!activityResumed) {
            if (nativeRequestState.queueLifecycleAction("select_tree")) {
                Log.i(tag, "Deferring SAF picker until Activity is resumed")
            }
            return
        }
        if (safPickerPending) {
            Log.i(tag, "SAF picker request already pending")
            return
        }
        safPickerPending = true
        NativeMailbox.write(this, JSONObject().put("type", "saf_permission_request")
            .put("requestId", pendingSafRequestId ?: "")
            .put("payload", JSONObject()
                .put("source", "saf")
                .put("state", "requesting")
                .put("capabilities", storageCapabilitiesPayload(StorageLifecycleState.REQUESTING))))
        Log.i(tag, "SAF launch requested taskId=" + taskId)
        try {
            treePicker.launch(Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).addFlags(
                Intent.FLAG_GRANT_READ_URI_PERMISSION or
                    Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION or
                    Intent.FLAG_GRANT_PREFIX_URI_PERMISSION))
        } catch (exception: Exception) {
            safPickerPending = false
            pendingSafRequestId = null
            Log.e(tag, "SAF picker launcher failed", exception)
            NativeMailbox.write(this, JSONObject().put("type", "saf_error")
                .put("message", "Não foi possível abrir o seletor de pasta.")
                .put("payload", JSONObject().put("stage", "launch")))
        }
    }
    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        logLifecycle("onWindowFocusChanged")
        if (hasFocus) {
            applyNormalSystemUi()
            ViewCompat.requestApplyInsets(window.decorView)
        }
    }

    override fun onConfigurationChanged(newConfig: android.content.res.Configuration) {
        super.onConfigurationChanged(newConfig)
        Log.i(tag, "CONFIGURATION_CHANGED orientation=${newConfig.orientation}")
        applyNormalSystemUi()
        ViewCompat.requestApplyInsets(window.decorView)
    }
    private fun signInWithGoogle(serverClientId: String?) {
        if (serverClientId.isNullOrBlank()) { NativeMailbox.write(this, JSONObject().put("type", "google_error").put("message", "Configure o Web Client ID do Google.")); return }
        CoroutineScope(Dispatchers.Main).launch { GoogleIdentity.signIn(this@MainActivity, serverClientId) }
    }
}
