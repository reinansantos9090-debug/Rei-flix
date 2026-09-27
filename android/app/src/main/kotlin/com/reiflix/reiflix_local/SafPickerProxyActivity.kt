package com.reiflix.reiflix_local

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity

/**
 * Isolates ACTION_OPEN_DOCUMENT_TREE from the Flutter/Flet MainActivity lifecycle.
 *
 * MainActivity remains the single owner of the SAF result/state machine; this
 * Activity only launches DocumentsUI and faithfully forwards the result URI +
 * grant flags back to MainActivity.
 */
class SafPickerProxyActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (savedInstanceState?.getBoolean(STATE_LAUNCHED, false) == true) {
            return
        }
        launchPicker()
    }

    private fun launchPicker() {
        val pickerIntent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).apply {
            addFlags(
                Intent.FLAG_GRANT_READ_URI_PERMISSION or
                    Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION or
                    Intent.FLAG_GRANT_PREFIX_URI_PERMISSION,
            )
        }
        try {
            Log.i(TAG, "SAF_PROXY_LAUNCH action=" + pickerIntent.action)
            startActivityForResult(pickerIntent, REQUEST_PICK_TREE)
        } catch (exception: Exception) {
            Log.e(TAG, "SAF_PROXY_LAUNCH_FAILED", exception)
            setResult(
                Activity.RESULT_CANCELED,
                Intent().putExtra(ERROR_EXTRA, exception.javaClass.simpleName),
            )
            finish()
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putBoolean(STATE_LAUNCHED, true)
        super.onSaveInstanceState(outState)
    }

    @Deprecated("The platform callback is retained here because this Activity exists only as a SAF proxy.")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQUEST_PICK_TREE) return

        if (resultCode == Activity.RESULT_OK && data?.data != null) {
            val forwarded = Intent().apply {
                action = data.action
                data.data?.let { this.data = it }
                addFlags(data.flags)
            }
            Log.i(TAG, "SAF_PROXY_RESULT_OK uri=" + data.data)
            setResult(Activity.RESULT_OK, forwarded)
        } else {
            Log.i(TAG, "SAF_PROXY_RESULT_CANCELLED resultCode=" + resultCode)
            setResult(Activity.RESULT_CANCELED)
        }
        finish()
    }

    companion object {
        private const val TAG = "[REIFLIX][SAF_PROXY]"
        private const val REQUEST_PICK_TREE = 4701
        private const val STATE_LAUNCHED = "reiflix.safProxy.launched"
        const val ERROR_EXTRA = "reiflix.safPicker.error"
    }
}
