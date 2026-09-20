package com.reiflix.reiflix_local

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeRequestStateTest {
    @Test
    fun duplicate_request_id_is_ignored() {
        val state = NativeRequestState()

        assertTrue(state.acceptRequest("abc"))
        assertFalse(state.acceptRequest("abc"))
        assertTrue(state.acceptRequest("def"))
        assertEquals("def", state.lastHandledRequestId)
    }

    @Test
    fun blank_request_ids_are_not_treated_as_duplicates() {
        val state = NativeRequestState()

        assertTrue(state.acceptRequest(null))
        assertTrue(state.acceptRequest(""))
        assertTrue(state.acceptRequest("   "))
    }

    @Test
    fun lifecycle_action_is_queued_once_and_consumed_once() {
        val state = NativeRequestState()

        assertTrue(state.queueLifecycleAction("request_media_access"))
        assertFalse(state.queueLifecycleAction("open_broad_storage_settings"))
        assertEquals("request_media_access", state.consumeLifecycleAction())
        assertNull(state.consumeLifecycleAction())
    }

    @Test
    fun saved_request_and_pending_action_can_be_restored() {
        val state = NativeRequestState()

        state.restore("abc", "open_broad_storage_settings")

        assertEquals("abc", state.lastHandledRequestId)
        assertEquals("open_broad_storage_settings", state.pendingLifecycleAction)
        assertFalse(state.acceptRequest("abc"))
        assertEquals("open_broad_storage_settings", state.consumeLifecycleAction())
    }
}
