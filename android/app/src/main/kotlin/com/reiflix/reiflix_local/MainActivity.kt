package com.reiflix.reiflix_local

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.util.Log
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import io.flutter.embedding.android.FlutterActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * Flet's generated Android template must use this activity instead of its default
 * FlutterActivity. It owns SAF and Google identity because only Android has a
 * ContentResolver/Credential Manager.
 */
class MainActivity : FlutterActivity() {
    private val tag = "[REIFLIX][ANDROID]"
    private val treePicker = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val uri = result.data?.data ?: run {
            Log.i(tag, "SAF selection cancelled")
            NativeMailbox.write(this, JSONObject().put("type", "saf_cancelled"))
            return@registerForActivityResult
        }
        try {
            Log.i(tag, "SAF result received")
            SafScanner.persistPermission(this, uri, result.data?.flags ?: 0)
            scanTree(uri.toString())
        } catch (exception: Exception) {
            Log.e(tag, "SAF selection failed", exception)
            NativeMailbox.write(this, JSONObject().put("type", "saf_error").put("message", "Não foi possível autorizar esta pasta. Escolha-a novamente.")
                .put("payload", JSONObject().put("treeUri", uri.toString())))
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        configureSystemBars()
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                // Flet owns screen history.  Do not let FlutterActivity finish
                // before its Python navigation policy receives this event.
                NativeMailbox.write(this@MainActivity, JSONObject().put("type", "android_back"))
            }
        })
        handleNativeIntent(intent)
    }
    override fun onNewIntent(intent: Intent) { super.onNewIntent(intent); handleNativeIntent(intent) }

    private fun handleNativeIntent(intent: Intent?) {
        when (intent?.data?.getQueryParameter("action")) {
            "select_tree" -> openTreePicker()
            "scan_tree" -> scanTree(intent.data?.getQueryParameter("tree_uri"))
            "verify_tree" -> verifyTree(intent.data?.getQueryParameter("tree_uri"))
            "google_sign_in" -> signInWithGoogle(intent.data?.getQueryParameter("server_client_id"))
            "play" -> openPlayer(intent.data)
        }
    }
    private fun scanTree(reference: String?) {
        if (reference.isNullOrBlank()) return
        val treeUri = Uri.parse(reference)
        if (!SafScanner.hasPersistedReadPermission(this, treeUri)) {
            Log.w(tag, "SAF permission revoked")
            NativeMailbox.write(this, JSONObject().put("type", "saf_error").put("message", "A permissão desta pasta foi removida. Escolha a pasta novamente.")
                .put("payload", JSONObject().put("treeUri", reference)))
            return
        }
        CoroutineScope(Dispatchers.IO).launch {
            try {
                NativeMailbox.write(this@MainActivity, JSONObject().put("type", "saf_scan").put("payload", SafScanner.scan(this@MainActivity, treeUri)))
            } catch (exception: Exception) {
                Log.e(tag, "SAF scan failed", exception)
                NativeMailbox.write(this@MainActivity, JSONObject().put("type", "saf_error").put("message", "Não foi possível atualizar esta pasta autorizada.")
                    .put("payload", JSONObject().put("treeUri", reference)))
            }
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
        if (localUri.scheme !in setOf("content", "file")) {
            NativeMailbox.write(this, JSONObject().put("type", "player_error")
                .put("message", "A reprodução aceita somente arquivos locais autorizados."))
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
            Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION or Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION or Intent.FLAG_GRANT_PREFIX_URI_PERMISSION))
    }
    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) configureSystemBars()
    }
    private fun configureSystemBars() {
        // The Flet host is a normal application screen.  Keeping decor fitted
        // prevents its header and controls from being drawn below the status
        // bar on targetSdk 35.  Only NativePlayerActivity is immersive.
        WindowCompat.setDecorFitsSystemWindows(window, true)
        WindowInsetsControllerCompat(window, window.decorView).apply {
            show(WindowInsetsCompat.Type.systemBars())
        }
    }
    private fun signInWithGoogle(serverClientId: String?) {
        if (serverClientId.isNullOrBlank()) { NativeMailbox.write(this, JSONObject().put("type", "google_error").put("message", "Configure o Web Client ID do Google.")); return }
        CoroutineScope(Dispatchers.Main).launch { GoogleIdentity.signIn(this@MainActivity, serverClientId) }
    }
}
