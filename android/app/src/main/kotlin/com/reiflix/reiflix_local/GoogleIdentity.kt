package com.reiflix.reiflix_local

import android.content.Context
import android.util.Base64
import android.util.Log
import androidx.credentials.CredentialManager
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
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
            val claims = verifiedProfile(credential, serverClientId)
            NativeMailbox.write(context, JSONObject().put("type", "google_sign_in_success").put("payload", claims))
            Log.i(TAG, "Google account selected")
        } catch (cancelled: GetCredentialCancellationException) {
            Log.i(TAG, "Google sign-in cancelled")
            NativeMailbox.write(context, JSONObject().put("type", "google_cancelled"))
        } catch (exception: Exception) {
            Log.e(TAG, "Google identity failed", exception)
            NativeMailbox.write(context, JSONObject().put("type", "google_error").put("message", readableError(exception)))
        }
    }

    /**
     * Credential Manager obtains the signed Google ID token. We only decode the
     * resulting claims locally to obtain the minimum profile projection; the
     * token itself is never logged, mailed to Python, or persisted.
     */
    private fun verifiedProfile(credential: GoogleIdTokenCredential, clientId: String): JSONObject {
        val tokenParts = credential.idToken.split('.')
        require(tokenParts.size == 3) { "Credencial Google inválida." }
        val claims = JSONObject(String(Base64.decode(tokenParts[1], Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING), Charsets.UTF_8))
        val issuer = claims.optString("iss")
        require(issuer == "https://accounts.google.com" || issuer == "accounts.google.com") { "Emissor da credencial inválido." }
        require(claims.optString("aud") == clientId) { "A credencial não pertence a este aplicativo." }
        require(claims.optLong("exp", 0L) > System.currentTimeMillis() / 1000L) { "Credencial Google expirada." }
        val subject = claims.optString("sub")
        val email = claims.optString("email", credential.id)
        require(subject.isNotBlank() && email.isNotBlank()) { "A conta Google não contém identificação suficiente." }
        return JSONObject().put("id", subject).put("name", claims.optString("name", credential.displayName ?: ""))
            .put("email", email).put("picture", claims.optString("picture", credential.profilePictureUri?.toString() ?: ""))
    }

    private fun readableError(exception: Exception): String = when (exception::class.java.simpleName) {
        "NoCredentialException" -> "Nenhuma conta Google disponível foi encontrada neste dispositivo."
        "GetCredentialProviderConfigurationException", "GetCredentialUnsupportedException" -> "O login Google não está disponível neste dispositivo."
        else -> "Não foi possível entrar com o Google. Verifique a configuração e a conexão."
    }
}
