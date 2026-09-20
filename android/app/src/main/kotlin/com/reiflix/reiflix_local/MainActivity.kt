package com.reiflix.reiflix_local

import android.content.Intent
import android.content.ActivityNotFoundException
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.util.Log
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.ActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import io.flutter.embedding.android.FlutterFragmentActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * Flet's generated Android template must use this activity instead of its default
 * FlutterActivity. It owns SAF and Google identity because only Android has a
 * ContentResolver/Credential Manager.
 */
class MainActivity : FlutterFragmentActivity() {
    private val tag = "[REIFLIX][ANDROID]"
    private lateinit var systemUiController: SystemUiController
    private var broadStoragePermissionPending = false
    private val activeNativeScans = mutableSetOf<String>()

    @Synchronized
    private fun tryBeginNativeScan(key: String): Boolean = activeNativeScans.add(key)

    @Synchronized
    private fun endNativeScan(key: String) {
        activeNativeScans.remove(key)
    }
    private val backCallback = object : OnBackPressedCallback(true) {
        override fun handleOnBackPressed() {
            NativeMailbox.write(this@MainActivity, JSONObject().put("type", "android_back"))
        }
    }
    private val mediaPermissionRequester = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { grants ->
        val granted = grants.any { it.value } && MediaStoreScanner.hasReadPermission(this)
        NativeMailbox.write(this, JSONObject().put("type", "mediastore_permission").put("payload", JSONObject()
            .put("granted", granted)
            .put("access", MediaStoreScanner.accessLevel(this))
            .put("source", MediaStoreScanner.SOURCE)))
        if (granted) scanMediaStore() else {
            NativeMailbox.write(this, JSONObject().put("type", "mediastore_error")
                .put("message", "A permissão para acessar os vídeos do dispositivo foi negada.")
                .put("payload", JSONObject().put("source", MediaStoreScanner.SOURCE)))
        }
    }
    private val legacyBroadPermissionRequester = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { grants ->
        val granted = grants.any { it.value } && BroadStorageScanner.hasAccess(this)
        NativeMailbox.write(this, JSONObject().put("type", "broad_storage_permission").put("payload", JSONObject()
            .put("granted", granted)
            .put("source", BroadStorageScanner.SOURCE)))
        if (granted) {
            scanAllStorage()
        } else {
            publishStorageStatus()
        }
    }
    private val treePicker = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result: ActivityResult ->
        handleTreePickerResult(result)
    }

    private fun handleTreePickerResult(result: androidx.activity.result.ActivityResult) {
        val resultIntent = result.data
        val uri = resultIntent?.data
        if (uri == null) {
            Log.i(tag, "SAF selection cancelled")
            NativeMailbox.write(this, JSONObject().put("type", "saf_cancelled"))
            return
        }
        try {
            Log.i(tag, "SAF result received")
            SafScanner.persistPermission(this, uri, resultIntent.flags)
            // Register the user's grant before scanning. If the provider later
            // fails or exposes a partial tree, Settings must still remember the
            // authorized SAF tree and let the user retry without selecting it again.
            NativeMailbox.write(this, JSONObject().put("type", "saf_permission").put("payload", JSONObject()
                .put("treeUri", uri.toString())
                .put("granted", true)
                .put("selected", true)
                .put("name", SafScanner.displayName(this, uri))))
            scanTree(uri.toString())
        } catch (exception: Exception) {
            Log.e(tag, "SAF selection failed", exception)
            NativeMailbox.write(this, JSONObject().put("type", "saf_error").put("message", "Não foi possível autorizar esta pasta. Escolha-a novamente.")
                .put("payload", JSONObject().put("treeUri", uri.toString())))
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        systemUiController = SystemUiController(window)
        onBackPressedDispatcher.addCallback(this, backCallback)
        applyImmersiveSystemUi()
        // Flet owns screen history. Do not let FlutterActivity finish before
        // its Python navigation policy receives this event.
        handleNativeIntent(intent)
    }
    override fun onNewIntent(intent: Intent) { super.onNewIntent(intent); handleNativeIntent(intent) }
    override fun onResume() {
        super.onResume()
        applyImmersiveSystemUi()
        // Settings may revoke access while this activity is paused. Always
        // republish the actual Android state; a button click is never proof.
        publishStorageStatus()
        if (broadStoragePermissionPending) {
            broadStoragePermissionPending = false
            if (BroadStorageScanner.hasAccess(this)) {
                scanAllStorage()
            } else {
                NativeMailbox.write(this, JSONObject().put("type", "broad_storage_status")
                    .put("payload", BroadStorageScanner.accessSnapshot(this)))
            }
        }
    }

    private fun handleNativeIntent(intent: Intent?) {
        when (intent?.data?.getQueryParameter("action")) {
            "select_tree" -> openTreePicker()
            "scan_tree" -> scanTree(intent.data?.getQueryParameter("tree_uri"))
            "verify_tree" -> verifyTree(intent.data?.getQueryParameter("tree_uri"))
            "release_tree" -> releaseTree(intent.data?.getQueryParameter("tree_uri"))
            "scan_media_store" -> scanMediaStore()
            "request_media_access" -> requestMediaAccess()
            "check_storage_access" -> publishStorageStatus()
            "open_broad_storage_settings" -> openBroadStorageSettings()
            "scan_all_storage" -> scanAllStorage()
            "google_sign_in" -> signInWithGoogle(intent.data?.getQueryParameter("server_client_id"))
            "play" -> openPlayer(intent.data)
        }
    }
    private fun scanTree(reference: String?) {
        if (reference.isNullOrBlank()) {
            NativeMailbox.write(this, JSONObject().put("type", "saf_error")
                .put("message", "A pasta SAF não foi informada corretamente.")
                .put("payload", JSONObject()))
            return
        }
        val treeUri = Uri.parse(reference)
        if (!SafScanner.hasPersistedReadPermission(this, treeUri)) {
            Log.w(tag, "SAF permission revoked")
            NativeMailbox.write(this, JSONObject().put("type", "saf_error").put("message", "A permissão desta pasta foi removida. Escolha a pasta novamente.")
                .put("payload", JSONObject().put("treeUri", reference)))
            return
        }
        val scanKey = "saf:$reference"
        if (!tryBeginNativeScan(scanKey)) {
            NativeMailbox.write(this, JSONObject().put("type", "saf_scan_progress")
                .put("payload", JSONObject().put("treeUri", reference).put("phase", "already_running")))
            return
        }
        CoroutineScope(Dispatchers.IO).launch {
            try {
                NativeMailbox.write(this@MainActivity, JSONObject().put("type", "saf_scan_progress").put("payload", JSONObject().put("treeUri", reference).put("phase", "started")))
                val result = SafScanner.scan(this@MainActivity, treeUri) { progress ->
                    NativeMailbox.write(this@MainActivity, JSONObject().put("type", "saf_scan_progress")
                        .put("payload", progress.put("treeUri", reference).put("phase", "scanning")))
                }
                NativeMailbox.write(this@MainActivity, JSONObject().put("type", "saf_scan").put("payload", result))
            } catch (exception: Exception) {
                Log.e(tag, "SAF scan failed", exception)
                NativeMailbox.write(this@MainActivity, JSONObject().put("type", "saf_error").put("message", "Não foi possível atualizar esta pasta autorizada.")
                    .put("payload", JSONObject().put("treeUri", reference)))
            } finally {
                endNativeScan(scanKey)
            }
        }
    }
    private fun requestMediaAccess() {
        if (MediaStoreScanner.hasReadPermission(this)) {
            NativeMailbox.write(this, JSONObject().put("type", "mediastore_permission").put("payload", JSONObject()
                .put("granted", true)
                .put("access", MediaStoreScanner.accessLevel(this))
                .put("source", MediaStoreScanner.SOURCE)))
            return
        }
        val permissions = MediaStoreScanner.requiredPermissions()
        if (permissions.isEmpty()) {
            NativeMailbox.write(this, JSONObject().put("type", "mediastore_error")
                .put("message", "Este Android não disponibiliza permissão de leitura de vídeos.")
                .put("payload", JSONObject().put("source", MediaStoreScanner.SOURCE)))
            return
        }
        mediaPermissionRequester.launch(permissions)
    }

    private fun publishStorageStatus() {
        NativeMailbox.write(this, JSONObject().put("type", "broad_storage_status")
            .put("payload", BroadStorageScanner.accessSnapshot(this)))
        NativeMailbox.write(this, JSONObject().put("type", "mediastore_permission").put("payload", JSONObject()
            .put("granted", MediaStoreScanner.hasReadPermission(this))
            .put("access", MediaStoreScanner.accessLevel(this))
            .put("source", MediaStoreScanner.SOURCE)))
    }

    private fun openBroadStorageSettings() {
        if (BroadStorageScanner.hasAccess(this)) {
            publishStorageStatus()
            return
        }
        NativeMailbox.write(this, JSONObject().put("type", "broad_storage_permission")
            .put("payload", JSONObject().put("granted", false).put("source", BroadStorageScanner.SOURCE)))
        if (Build.VERSION.SDK_INT >= 30) {
            broadStoragePermissionPending = true
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
            broadStoragePermissionPending = false
            val appDetailsIntent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                .setData(Uri.parse("package:$packageName"))
            runCatching { startActivity(appDetailsIntent) }
                .onFailure { Log.w(tag, "Application details settings unavailable", it) }
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
            broadStoragePermissionPending = false
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

    private fun scanAllStorage() {
        if (!BroadStorageScanner.hasAccess(this)) {
            publishStorageStatus()
            NativeMailbox.write(this, JSONObject().put("type", "broad_storage_permission")
                .put("payload", JSONObject().put("granted", false).put("source", BroadStorageScanner.SOURCE)))
            return
        }
        NativeMailbox.write(this, JSONObject().put("type", "broad_storage_permission")
            .put("payload", JSONObject().put("granted", true).put("source", BroadStorageScanner.SOURCE)))
        if (!tryBeginNativeScan(BroadStorageScanner.SOURCE)) {
            NativeMailbox.write(this, JSONObject().put("type", "broad_storage_scan_progress")
                .put("payload", JSONObject().put("phase", "already_running").put("source", BroadStorageScanner.SOURCE)))
            return
        }
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val result = BroadStorageScanner.scan(this@MainActivity) { progress ->
                    NativeMailbox.write(this@MainActivity, JSONObject().put("type", "broad_storage_scan_progress")
                        .put("payload", progress))
                }
                NativeMailbox.write(this@MainActivity, JSONObject().put("type", "broad_storage_scan")
                    .put("payload", result))
            } catch (exception: Exception) {
                Log.e(tag, "Broad storage scan failed", exception)
                NativeMailbox.write(this@MainActivity, JSONObject().put("type", "broad_storage_error")
                    .put("message", "Não foi possível varrer o armazenamento local.")
                    .put("payload", JSONObject().put("source", BroadStorageScanner.SOURCE)))
            } finally {
                endNativeScan(BroadStorageScanner.SOURCE)
            }
        }
    }
    private fun scanMediaStore() {
        if (!MediaStoreScanner.hasReadPermission(this)) {
            val permissions = MediaStoreScanner.requiredPermissions()
            if (permissions.isEmpty()) {
                NativeMailbox.write(this, JSONObject().put("type", "mediastore_error")
                    .put("message", "Este Android não disponibiliza acesso ao MediaStore.")
                    .put("payload", JSONObject().put("source", MediaStoreScanner.SOURCE)))
            } else {
                mediaPermissionRequester.launch(permissions)
            }
            return
        }
        if (!tryBeginNativeScan(MediaStoreScanner.SOURCE)) {
            NativeMailbox.write(this, JSONObject().put("type", "mediastore_scan_progress")
                .put("payload", JSONObject().put("phase", "already_running").put("source", MediaStoreScanner.SOURCE)))
            return
        }
        CoroutineScope(Dispatchers.IO).launch {
            try {
                NativeMailbox.write(this@MainActivity, JSONObject().put("type", "mediastore_scan_progress")
                    .put("payload", JSONObject().put("source", MediaStoreScanner.SOURCE).put("phase", "started")))
                val result = MediaStoreScanner.scan(this@MainActivity) { progress ->
                    NativeMailbox.write(this@MainActivity, JSONObject().put("type", "mediastore_scan_progress")
                        .put("payload", progress))
                }
                NativeMailbox.write(this@MainActivity, JSONObject().put("type", "mediastore_scan")
                    .put("payload", result))
            } catch (exception: Exception) {
                Log.e(tag, "MediaStore scan failed", exception)
                NativeMailbox.write(this@MainActivity, JSONObject().put("type", "mediastore_error")
                    .put("message", "Não foi possível atualizar os vídeos do dispositivo.")
                    .put("payload", JSONObject().put("source", MediaStoreScanner.SOURCE)))
            } finally {
                endNativeScan(MediaStoreScanner.SOURCE)
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
        Log.i(tag, "SAF launch requested")
        treePicker.launch(Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).addFlags(
            Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION or Intent.FLAG_GRANT_PREFIX_URI_PERMISSION))
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
