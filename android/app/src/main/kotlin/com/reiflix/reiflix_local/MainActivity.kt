package com.reiflix.reiflix_local

import android.content.BroadcastReceiver
import android.content.Intent
import android.content.IntentFilter
import android.content.ActivityNotFoundException
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.DocumentsContract
import android.provider.Settings
import android.util.Log
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.ActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
    private var legacyBroadPermissionRequestPending = false
    private var mediaPermissionRequestPending = false
    private var safPickerPending = false
    private var activityResumed = false
    private var pendingMediaRequestId: String? = null
    private var pendingBroadRequestId: String? = null
    private var pendingSafRequestId: String? = null
    private val nativeRequestState = NativeRequestState()

    companion object {
        private const val STATE_LAST_NATIVE_REQUEST_ID = "reiflix.lastNativeRequestId"
        private const val STATE_PENDING_LIFECYCLE_ACTION = "reiflix.pendingLifecycleAction"
        private const val STATE_BROAD_SETTINGS_PENDING = "reiflix.broadSettingsPending"
        private const val STATE_PENDING_LIFECYCLE_REQUEST_ID = "reiflix.pendingLifecycleRequestId"
        private const val STATE_PENDING_MEDIA_REQUEST_ID = "reiflix.pendingMediaRequestId"
        private const val STATE_PENDING_BROAD_REQUEST_ID = "reiflix.pendingBroadRequestId"
        private const val STATE_PENDING_SAF_REQUEST_ID = "reiflix.pendingSafRequestId"
        private const val STATE_SAF_PICKER_PENDING = "reiflix.safPickerPending"
        private const val STATE_SEEN_NATIVE_REQUEST_IDS = "reiflix.seenNativeRequestIds"
    }
    private val activeNativeScanJobs = mutableMapOf<String, Job>()
    private val backCallback = object : OnBackPressedCallback(true) {
        override fun handleOnBackPressed() {
            NativeMailbox.write(this@MainActivity, JSONObject().put("type", "android_back"))
        }
    }
    private var storageReceiverRegistered = false
    private val storageReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: android.content.Context, intent: Intent) {
            val action = intent.action ?: return
            val changes = NativeIndex.updateVolumeSnapshot(
                applicationContext,
                NativeIndex.volumeSnapshot(applicationContext),
            )
            if (!changes.optBoolean("changed")) return
            val payload = JSONObject(changes.toString())
                .put("source", "android_storage")
                .put("reason", action)
                .put("timestamp", System.currentTimeMillis())
                .put("volumeEventUri", intent.data?.toString() ?: "")
            NativeMailbox.write(this@MainActivity, JSONObject()
                .put("type", "volume_changed")
                .put("payload", payload))
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
            addDataScheme("file")
        }
        try {
            if (Build.VERSION.SDK_INT >= 33) {
                registerReceiver(storageReceiver, filter, RECEIVER_NOT_EXPORTED)
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
        NativeMailbox.write(this, JSONObject().put("type", "mediastore_permission")
            .put("requestId", requestId ?: "")
            .put("payload", JSONObject()
                .put("granted", granted)
                .put("access", access)
                .put("source", MediaStoreScanner.SOURCE)
                .put("capabilities", storageCapabilitiesPayload(StorageLifecycleState.REVALIDATED))))
        if (granted) scanMediaStore() else {
            NativeMailbox.write(this, JSONObject().put("type", "mediastore_error")
                .put("requestId", requestId ?: "")
                .put("message", "A permissão para acessar os vídeos do dispositivo foi negada.")
                .put("payload", JSONObject().put("source", MediaStoreScanner.SOURCE)))
        }
    }
    private val legacyBroadPermissionRequester = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { _ ->
        legacyBroadPermissionRequestPending = false
        val requestId = pendingBroadRequestId
        pendingBroadRequestId = null
        val granted = BroadStorageScanner.hasAccess(this)
        NativeMailbox.write(this, JSONObject().put("type", "broad_storage_permission")
            .put("requestId", requestId ?: "")
            .put("payload", JSONObject()
                .put("granted", granted)
                .put("source", BroadStorageScanner.SOURCE)
                .put("capabilities", storageCapabilitiesPayload(StorageLifecycleState.REVALIDATED))))
        if (granted) scanAllStorage(requestId) else publishStorageStatus()
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
        if (uri == null) {
            Log.i(tag, "SAF selection cancelled")
            NativeMailbox.write(this, JSONObject().put("type", "saf_cancelled")
                .put("requestId", requestId ?: "")
                .put("payload", JSONObject().put("source", "saf")))
            return
        }
        try {
            Log.i(tag, "SAF result received")
            SafScanner.persistPermission(this, uri, resultIntent.flags)
            // Register the user's grant before scanning. If the provider later
            // fails or exposes a partial tree, Settings must still remember the
            // authorized SAF tree and let the user retry without selecting it again.
            NativeMailbox.write(this, JSONObject().put("type", "saf_permission")
                .put("requestId", requestId ?: "")
                .put("payload", JSONObject()
                    .put("treeUri", uri.toString())
                    .put("granted", true)
                    .put("selected", true)
                    .put("name", SafScanner.displayName(this, uri))
                    .put("capabilities", storageCapabilitiesPayload(StorageLifecycleState.REVALIDATED))))
            scanTree(uri.toString(), requestId)
        } catch (exception: Exception) {
            Log.e(tag, "SAF selection failed", exception)
            NativeMailbox.write(this, JSONObject().put("type", "saf_error").put("message", "Não foi possível autorizar esta pasta. Escolha-a novamente.")
                .put("payload", JSONObject().put("treeUri", uri.toString())))
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
        nativeRequestState.restore(
            savedInstanceState?.getString(STATE_LAST_NATIVE_REQUEST_ID),
            savedInstanceState?.getString(STATE_PENDING_LIFECYCLE_ACTION),
            savedInstanceState?.getString(STATE_PENDING_LIFECYCLE_REQUEST_ID),
        )
        nativeRequestState.restoreSeenRequestIds(savedInstanceState?.getString(STATE_SEEN_NATIVE_REQUEST_IDS))
        broadStoragePermissionPending = savedInstanceState?.getBoolean(STATE_BROAD_SETTINGS_PENDING) ?: false
        pendingMediaRequestId = savedInstanceState?.getString(STATE_PENDING_MEDIA_REQUEST_ID)
        pendingBroadRequestId = savedInstanceState?.getString(STATE_PENDING_BROAD_REQUEST_ID)
        pendingSafRequestId = savedInstanceState?.getString(STATE_PENDING_SAF_REQUEST_ID)
        safPickerPending = savedInstanceState?.getBoolean(STATE_SAF_PICKER_PENDING) ?: false
        logLifecycle("onCreate", intent)
        systemUiController = SystemUiController(window)
        onBackPressedDispatcher.addCallback(this, backCallback)
        applyImmersiveSystemUi()
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
        logLifecycle("onStart")
    }

    override fun onResume() {
        super.onResume()
        activityResumed = true
        logLifecycle("onResume")
        applyImmersiveSystemUi()

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
            }
            // Established host contract: "request_media_access" -> requestMediaAccess()
            return
        }

        // Settings may revoke access while this activity is paused. Always
        // republish the actual Android state after a real Settings return.
        if (broadStoragePermissionPending) {
            broadStoragePermissionPending = false
            val requestId = pendingBroadRequestId
            pendingBroadRequestId = null
            val granted = BroadStorageScanner.hasAccess(this)
            NativeMailbox.write(this, JSONObject().put("type", "broad_storage_permission")
                .put("requestId", requestId ?: "")
                .put("payload", JSONObject()
                    .put("granted", granted)
                    .put("source", BroadStorageScanner.SOURCE)
                    .put("revalidatedAfterSettings", true)
                    .put("capabilities", storageCapabilitiesPayload(StorageLifecycleState.RETURNED))))
            if (granted) scanAllStorage(requestId)
            publishStorageCapabilities(StorageLifecycleState.REVALIDATED)
            return
        }

        publishStorageStatus()
    }

    override fun onPause() {
        activityResumed = false
        logLifecycle("onPause")
        super.onPause()
    }

    override fun onStop() {
        logLifecycle("onStop")
        unregisterStorageReceiver()
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
        outState.putBoolean(STATE_BROAD_SETTINGS_PENDING, broadStoragePermissionPending)
        outState.putBoolean(STATE_SAF_PICKER_PENDING, safPickerPending)
        outState.putString(STATE_SEEN_NATIVE_REQUEST_IDS, nativeRequestState.seenRequestIdsState())
        super.onSaveInstanceState(outState)
    }

    private fun persistedSafTreeUris(): List<String> =
        contentResolver.persistedUriPermissions
            .asSequence()
            .filter { it.isReadPermission && it.uri.scheme == "content" && DocumentsContract.isTreeUri(it.uri) }
            .map { it.uri.toString() }
            .distinct()
            .sorted()
            .toList()

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
        Log.i(tag, "NATIVE_INTENT action=$action requestId=${requestId ?: "-"} task=$taskId resumed=$activityResumed focus=${window?.decorView?.hasWindowFocus() == true} flags=0x${intent.flags.toString(16)}")
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
            "cancel_scan" -> cancelNativeScans(requestId)
            "google_sign_in" -> signInWithGoogle(intent.data?.getQueryParameter("server_client_id"))
            "play" -> openPlayer(intent.data)
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
        if (!SafScanner.hasPersistedReadPermission(this, treeUri)) {
            Log.w(tag, "SAF permission revoked")
            NativeMailbox.write(this, JSONObject().put("type", "saf_error")
                .put("requestId", requestId ?: "")
                .put("message", "A permissão desta pasta foi removida. Escolha a pasta novamente.")
                .put("payload", JSONObject().put("treeUri", reference).put("scanId", scanId)))
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
            JSONObject().put("treeUri", reference).put("scopeKind", "root").put("scopeRef", reference)
        )
        val appContext = applicationContext
        val job = CoroutineScope(Dispatchers.IO).launch {
            try {
                NativeIndex.markGenerationRunning(appContext, NativeIndex.SOURCE_SAF, scanKey, generationId)
                NativeMailbox.write(appContext, JSONObject().put("type", "saf_scan_progress").put("payload", JSONObject().put("treeUri", reference).put("scanId", scanId).put("requestId", requestId ?: "").put("phase", "started")))
                val result = SafScanner.scan(appContext, treeUri, { progress ->
                    NativeMailbox.write(appContext, JSONObject().put("type", "saf_scan_progress")
                        .put("payload", progress .put("treeUri", reference).put("scanId", scanId).put("requestId", requestId ?: "").put("phase", "scanning"))) }, { NativeScanController.isCancelled(scanId) })
                val partial = result.optBoolean("partial")
                val status = when {
                    result.optBoolean("cancelled") -> NativeIndex.STATUS_CANCELLED
                    partial -> NativeIndex.STATUS_PARTIAL
                    else -> NativeIndex.STATUS_COMPLETED
                }
                val prepared = NativeIndex.prepare(
                    appContext, NativeIndex.SOURCE_SAF, scanKey,
                    result.optJSONArray("documents") ?: JSONArray(), !partial && !result.optBoolean("cancelled"),
                    JSONObject().put("stats", result.optJSONObject("stats") ?: JSONObject()).put("status", status),
                    generationId, status
                )
                result.put("documents", prepared.documents).put("scanGeneration", prepared.generation).put("generationId", "native:" + prepared.generation)
                    .put("generationStatus", prepared.status).put("nativeNew", prepared.newItems).put("nativeChanged", prepared.changedItems)
                    .put("nativeUnchanged", prepared.unchangedItems).put("nativeDuplicates", prepared.duplicates).put("nativeRemoved", prepared.removedItems)
                    .put("requestId", requestId ?: "").put("scanId", scanId).put("scopeKind", "root").put("scopeRef", reference)
                    .put("volumeId", result.optJSONObject("stats")?.optString("volumeId") ?: "")
                NativeMailbox.write(appContext, JSONObject().put("type", "saf_scan").put("requestId", requestId ?: "").put("payload", result))
            } catch (exception: Exception) {
                Log.e(tag, "SAF scan failed", exception)
                NativeIndex.failGeneration(appContext, NativeIndex.SOURCE_SAF, scanKey, generationId,
                    exception.message ?: "SAF scan failed",
                    JSONObject().put("treeUri", reference))
                NativeMailbox.write(appContext, JSONObject().put("type", "saf_error")
                    .put("requestId", requestId ?: "")
                    .put("message", "Não foi possível atualizar esta pasta autorizada.")
                    .put("payload", JSONObject().put("treeUri", reference).put("scanId", scanId)
                        .put("generationId", "native:" + generationId).put("status", NativeIndex.STATUS_FAILED)))
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
            scanMediaStore(requestId)
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
        val trees = JSONArray()
        contentResolver.persistedUriPermissions
            .asSequence()
            .filter { it.isReadPermission }
            .forEach { permission ->
                val uri = permission.uri
                if (uri.scheme != "content" || !DocumentsContract.isTreeUri(uri)) return@forEach
                val treeId = runCatching { DocumentsContract.getTreeDocumentId(uri) }.getOrNull()
                    ?: return@forEach
                // Authorization inventory only needs the persistent URI grant.
                // Avoid provider metadata I/O on the Activity lifecycle thread.
                trees.put(
                    JSONObject()
                        .put("treeUri", uri.toString())
                        .put("documentId", treeId)
                )
            }
        NativeMailbox.write(
            this,
            JSONObject().put("type", "saf_inventory")
                .put("payload", JSONObject()
                    .put("trees", trees)
                    .put("count", trees.length())
                    .put("lifecycle", if (activityResumed) "RESUMED" else "PAUSED"))
        )
    }

    private fun openBroadStorageSettings() {
        if (!activityResumed) {
            nativeRequestState.queueLifecycleAction("open_broad_storage_settings", pendingBroadRequestId)
            Log.i(tag, "Deferring broad-storage Settings launch until Activity is resumed")
            return
        }
        if (BroadStorageScanner.hasAccess(this)) {
            publishStorageStatus()
            return
        }
        if (Build.VERSION.SDK_INT >= 30) {
            broadStoragePermissionPending = true
            NativeMailbox.write(this, JSONObject().put("type", "broad_storage_permission_request")
                .put("requestId", pendingBroadRequestId ?: "")
                .put("payload", JSONObject()
                    .put("source", BroadStorageScanner.SOURCE)
                    .put("state", "requesting")
                    .put("capabilities", storageCapabilitiesPayload(StorageLifecycleState.REQUESTING))))
            val packageIntent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
                .setData(Uri.parse("package:$packageName"))
            val globalIntent = Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION)
            try {
                startActivity(packageIntent)
                Log.i(tag, "Opened app-specific all-files settings")
                return
            } catch (specificException: Exception) {
                Log.w(tag, "App-specific all-files settings unavailable", specificException)
            }
            try {
                startActivity(globalIntent)
                Log.i(tag, "Opened global all-files settings")
                return
            } catch (globalException: Exception) {
                Log.w(tag, "Global all-files settings unavailable", globalException)
            }
            val appDetailsIntent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                .setData(Uri.parse("package:$packageName"))
            try {
                startActivity(appDetailsIntent)
                Log.i(tag, "Opened application details settings as final fallback")
                return
            } catch (detailsException: Exception) {
                broadStoragePermissionPending = false
                pendingBroadRequestId = null
                Log.w(tag, "Application details settings unavailable", detailsException)
            }
            NativeMailbox.write(this, JSONObject().put("type", "broad_storage_error")
                .put("message", "O Android não conseguiu abrir diretamente a tela de acesso amplo. Abra as configurações do aplicativo e procure por acesso a todos os arquivos.")
                .put("payload", JSONObject()
                    .put("api", Build.VERSION.SDK_INT)
                    .put("specificIntent", Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
                    .put("globalIntent", Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION)
                    .put("appDetailsIntent", Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                    .put("hasAccess", BroadStorageScanner.hasAccess(this))
                    .put("fallbackOpened", true)
                    .put("source", BroadStorageScanner.SOURCE)))
        } else {
            if (legacyBroadPermissionRequestPending) {
                Log.i(tag, "Legacy storage permission request already pending")
                return
            }
            broadStoragePermissionPending = false
            legacyBroadPermissionRequestPending = true
            NativeMailbox.write(this, JSONObject().put("type", "broad_storage_permission_request")
                .put("requestId", pendingBroadRequestId ?: "")
                .put("payload", JSONObject()
                    .put("source", BroadStorageScanner.SOURCE)
                    .put("state", "requesting")
                    .put("capabilities", storageCapabilitiesPayload(StorageLifecycleState.REQUESTING))))
            legacyBroadPermissionRequester.launch(arrayOf(android.Manifest.permission.READ_EXTERNAL_STORAGE))
        }
    }

    private fun openSettingsIntent(label: String, intent: Intent): Boolean {
        return try {
            startActivity(intent)
            true
        } catch (exception: ActivityNotFoundException) {
            Log.w(tag, "$label is unavailable; trying the next fallback", exception)
            false
        } catch (exception: SecurityException) {
            Log.w(tag, "$label was blocked; trying the next fallback", exception)
            false
        } catch (exception: Exception) {
            Log.w(tag, "$label failed unexpectedly; trying the next fallback", exception)
            false
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
                )
                val partial = result.optBoolean("partial")
                result.put("requestId", requestId ?: "")
                    .put("scanId", scanId).put("scopeKind", "global").put("scopeRef", "broad-storage")
                    .put("generationId", "native-scoped")
                    .put("generationStatus", if (result.optBoolean("cancelled")) NativeIndex.STATUS_CANCELLED else if (partial) NativeIndex.STATUS_PARTIAL else NativeIndex.STATUS_COMPLETED)
                NativeMailbox.write(appContext, JSONObject().put("type", "broad_storage_scan")
                    .put("requestId", requestId ?: "").put("payload", result))
            } catch (exception: Exception) {
                Log.e(tag, "Broad storage scan failed", exception)
                NativeMailbox.write(appContext, JSONObject().put("type", "broad_storage_error")
                    .put("requestId", requestId ?: "")
                    .put("message", "Não foi possível varrer o armazenamento local.")
                    .put("payload", JSONObject().put("source", BroadStorageScanner.SOURCE).put("scanId", scanId)))
            } finally {
                NativeScanController.finish(scanId)
                synchronized(activeNativeScanJobs) { activeNativeScanJobs.remove(scanId) }
            }
        }
        synchronized(activeNativeScanJobs) { activeNativeScanJobs[scanId] = job }
    }

    private fun scanMediaStore(requestId: String? = null) {
        val scanId = UUID.randomUUID().toString()
        if (!MediaStoreScanner.hasReadPermission(this)) {
            publishStorageStatus()
            NativeMailbox.write(this, JSONObject().put("type", "mediastore_error")
                .put("requestId", requestId ?: "")
                .put("message", "A permissão para ler vídeos ainda não foi concedida.")
                .put("payload", JSONObject().put("source", MediaStoreScanner.SOURCE)))
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
                )
                result.put("requestId", requestId ?: "").put("scanId", scanId)
                    .put("scopeKind", "global").put("scopeRef", MediaStoreScanner.SOURCE)
                NativeMailbox.write(appContext, JSONObject().put("type", "mediastore_scan")
                    .put("requestId", requestId ?: "").put("payload", result))
            } catch (exception: Exception) {
                Log.e(tag, "MediaStore scan failed", exception)
                NativeMailbox.write(appContext, JSONObject().put("type", "mediastore_error")
                    .put("requestId", requestId ?: "")
                    .put("message", "Não foi possível atualizar os vídeos do dispositivo.")
                    .put("payload", JSONObject().put("source", MediaStoreScanner.SOURCE).put("scanId", scanId)))
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
        val granted = SafScanner.hasPersistedReadPermission(this, Uri.parse(reference))
        Log.i(tag, "SAF permission verification: granted=$granted")
        NativeMailbox.write(this, JSONObject().put("type", "saf_permission").put("payload", JSONObject()
            .put("treeUri", reference).put("granted", granted)))
    }
    private fun openPlayer(data: Uri?) {
        val episodeUri = data?.getQueryParameter("uri") ?: return
        val localUri = Uri.parse(episodeUri)
        if (!((localUri.scheme == "content" && SafScanner.isAuthorizedDocument(this, localUri)) || MediaStoreScanner.isAuthorizedDocument(this, localUri) || BroadStorageScanner.isAuthorizedFile(this, localUri))) {
            Log.w(tag, "Rejected unauthorized local media URI")
            NativeMailbox.write(this, JSONObject().put("type", "player_error")
                .put("message", "Este arquivo não pertence a uma pasta autorizada pelo Rei-Flix."))
            return
        }
        startActivity(Intent(this, NativePlayerActivity::class.java)
            .putExtra("uri", episodeUri).putExtra("title", data.getQueryParameter("title") ?: "Episódio")
            .putExtra("positionMs", data.getQueryParameter("position_ms")?.toLongOrNull() ?: 0L)
            .putExtra("canNext", data.getQueryParameter("can_next")?.toBoolean() ?: false)
            .putExtra("canPrevious", data.getQueryParameter("can_previous")?.toBoolean() ?: false))
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
        if (hasFocus) applyImmersiveSystemUi()
    }
    private fun applyImmersiveSystemUi() {
        if (::systemUiController.isInitialized) systemUiController.applyImmersive()
    }
    private fun signInWithGoogle(serverClientId: String?) {
        if (serverClientId.isNullOrBlank()) { NativeMailbox.write(this, JSONObject().put("type", "google_error").put("message", "Configure o Web Client ID do Google.")); return }
        CoroutineScope(Dispatchers.Main).launch { GoogleIdentity.signIn(this@MainActivity, serverClientId) }
    }
}
