package com.reiflix.reiflix_local

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.util.Log
import androidx.activity.result.contract.ActivityResultContracts
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
        val uri = result.data?.data ?: run { NativeMailbox.write(this, JSONObject().put("type", "saf_cancelled")); return@registerForActivityResult }
        try {
            SafScanner.persistPermission(this, uri, result.data?.flags ?: 0)
            val payload = SafScanner.scan(this, uri)
            NativeMailbox.write(this, JSONObject().put("type", "saf_scan").put("payload", payload))
        } catch (exception: Exception) {
            Log.e(tag, "SAF selection failed", exception)
            NativeMailbox.write(this, JSONObject().put("type", "saf_error").put("message", exception.message ?: "Não foi possível acessar a pasta.")
                .put("payload", JSONObject().put("treeUri", uri.toString())))
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) { super.onCreate(savedInstanceState); handleNativeIntent(intent) }
    override fun onNewIntent(intent: Intent) { super.onNewIntent(intent); handleNativeIntent(intent) }

    private fun handleNativeIntent(intent: Intent?) {
        when (intent?.data?.getQueryParameter("action")) {
            "select_tree" -> openTreePicker()
            "scan_tree" -> scanTree(intent.data?.getQueryParameter("tree_uri"))
            "google_sign_in" -> signInWithGoogle(intent.data?.getQueryParameter("server_client_id"))
            "play" -> openPlayer(intent.data)
        }
    }
    private fun scanTree(reference: String?) {
        if (reference.isNullOrBlank()) return
        try { NativeMailbox.write(this, JSONObject().put("type", "saf_scan").put("payload", SafScanner.scan(this, Uri.parse(reference)))) }
        catch (exception: Exception) { NativeMailbox.write(this, JSONObject().put("type", "saf_error").put("message", exception.message ?: "Não foi possível atualizar a pasta.")
            .put("payload", JSONObject().put("treeUri", reference))) }
    }
    private fun openPlayer(data: Uri?) {
        val episodeUri = data?.getQueryParameter("uri") ?: return
        startActivity(Intent(this, NativePlayerActivity::class.java)
            .putExtra("uri", episodeUri).putExtra("title", data.getQueryParameter("title") ?: "Episódio")
            .putExtra("positionMs", data.getQueryParameter("position_ms")?.toLongOrNull() ?: 0L)
            .putExtra("canNext", data.getQueryParameter("can_next")?.toBoolean() ?: false)
            .putExtra("canPrevious", data.getQueryParameter("can_previous")?.toBoolean() ?: false))
    }
    private fun openTreePicker() {
        treePicker.launch(Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).addFlags(
            Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION or Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION or Intent.FLAG_GRANT_PREFIX_URI_PERMISSION))
    }
    private fun signInWithGoogle(serverClientId: String?) {
        if (serverClientId.isNullOrBlank()) { NativeMailbox.write(this, JSONObject().put("type", "google_error").put("message", "Configure o Web Client ID do Google.")); return }
        CoroutineScope(Dispatchers.Main).launch { GoogleIdentity.signIn(this@MainActivity, serverClientId) }
    }
}
