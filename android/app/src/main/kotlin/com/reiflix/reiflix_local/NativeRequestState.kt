package com.reiflix.reiflix_local

/**
 * Small deterministic state holder for lifecycle-sensitive native requests.
 *
 * Keeping this contract independent of Activity lets JVM tests cover the
 * request de-duplication and pending-action semantics without launching Flet.
 */
class NativeRequestState {
    var lastHandledRequestId: String? = null
        private set

    var pendingLifecycleAction: String? = null
        private set

    fun restore(lastRequestId: String?, pendingAction: String?) {
        lastHandledRequestId = lastRequestId?.takeIf { it.isNotBlank() }
        pendingLifecycleAction = pendingAction?.takeIf { it.isNotBlank() }
    }

    fun acceptRequest(requestId: String?): Boolean {
        val normalized = requestId?.trim().takeUnless { it.isNullOrEmpty() } ?: return true
        if (normalized == lastHandledRequestId) return false
        lastHandledRequestId = normalized
        return true
    }

    fun queueLifecycleAction(action: String): Boolean {
        if (action.isBlank() || pendingLifecycleAction != null) return false
        pendingLifecycleAction = action
        return true
    }

    fun consumeLifecycleAction(): String? =
        pendingLifecycleAction.also { pendingLifecycleAction = null }
}
