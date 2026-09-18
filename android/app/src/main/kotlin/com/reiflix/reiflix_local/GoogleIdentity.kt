package com.reiflix.reiflix_local

import android.content.Context
import android.util.Log
import androidx.credentials.CredentialManager
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject

/** Uses Android Credential Manager. The ID token is never written to disk. */
object GoogleIdentity {
    private const val TAG = "[REIFLIX][AUTH]"
    suspend fun signIn(context: Context, serverClientId: String) {
        try {
            val option = GetGoogleIdOption.Builder().setServerClientId(serverClientId).setFilterByAuthorizedAccounts(false).setAutoSelectEnabled(false).build()
            val response = CredentialManager.create(context).getCredential(context, GetCredentialRequest.Builder().addCredentialOption(option).build())
            val credential = GoogleIdTokenCredential.createFrom(response.credential.data)
            NativeMailbox.write(context, JSONObject().put("type", "google_account").put("payload", JSONObject()
                .put("id", credential.id).put("name", credential.displayName ?: "").put("email", credential.id)
                .put("picture", credential.profilePictureUri?.toString() ?: "")))
            Log.i(TAG, "Google account selected")
        } catch (cancelled: GetCredentialCancellationException) {
            NativeMailbox.write(context, JSONObject().put("type", "google_cancelled"))
        } catch (exception: Exception) {
            Log.e(TAG, "Google identity failed", exception)
            NativeMailbox.write(context, JSONObject().put("type", "google_error").put("message", "Não foi possível entrar com o Google. Verifique a configuração e a conexão."))
        }
    }
}
