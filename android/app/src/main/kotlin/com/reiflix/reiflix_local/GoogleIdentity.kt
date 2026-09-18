package com.reiflix.reiflix_local

import android.content.Context
import android.util.Log
import android.util.Base64
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
        if (serverClientId.isBlank()) {
            Log.w(TAG, "Google sign-in requested without a Web client ID")
            NativeMailbox.write(context, JSONObject().put("type", "google_error").put("message", "O login Google ainda não foi configurado neste APK."))
            return
        }
        try {
            Log.i(TAG, "Google Credential Manager sign-in requested")
            NativeMailbox.write(context, JSONObject().put("type", "google_sign_in_started"))
            val option = GetGoogleIdOption.Builder().setServerClientId(serverClientId).setFilterByAuthorizedAccounts(false).setAutoSelectEnabled(false).build()
            val response = CredentialManager.create(context).getCredential(context, GetCredentialRequest.Builder().addCredentialOption(option).build())
            val credential = GoogleIdTokenCredential.createFrom(response.credential.data)
            val subject = validatedSubject(credential.idToken, serverClientId)
            if (subject == null || credential.id.isBlank()) {
                NativeMailbox.write(context, JSONObject().put("type", "google_error").put("message", "A credencial Google recebida é inválida."))
                return
            }
            NativeMailbox.write(context, JSONObject().put("type", "google_account").put("payload", JSONObject()
                .put("id", subject).put("name", credential.displayName ?: "").put("email", credential.id)
                .put("picture", credential.profilePictureUri?.toString() ?: "")))
            Log.i(TAG, "Google account selected")
        } catch (cancelled: GetCredentialCancellationException) {
            Log.i(TAG, "Google sign-in cancelled")
            NativeMailbox.write(context, JSONObject().put("type", "google_cancelled"))
        } catch (exception: Exception) {
            Log.e(TAG, "Google identity failed", exception)
            NativeMailbox.write(context, JSONObject().put("type", "google_error").put("message", "Não foi possível entrar com o Google. Verifique a configuração e a conexão."))
        }
    }

    /** Credential Manager obtains the credential; this only validates claims
     * before reducing it to the token-free profile sent over NativeMailbox. */
    private fun validatedSubject(idToken: String, clientId: String): String? {
        return try {
            val parts = idToken.split('.')
            if (parts.size != 3) return null
            val payload = JSONObject(String(Base64.decode(parts[1], Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)))
            val issuer = payload.optString("iss")
            val audience = payload.opt("aud")
            val audienceMatches = audience == clientId || (audience is org.json.JSONArray && (0 until audience.length()).any { audience.optString(it) == clientId })
            val expiresAt = payload.optLong("exp", 0L)
            val subject = payload.optString("sub").trim()
            if (issuer !in setOf("https://accounts.google.com", "accounts.google.com") || !audienceMatches || expiresAt <= System.currentTimeMillis() / 1000 || subject.isBlank()) null else subject
        } catch (_: Exception) { null }
    }
}
