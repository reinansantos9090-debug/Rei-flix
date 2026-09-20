package com.reiflix.reiflix_local

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeRequestStateTest {
    @Test fun requestIdsRemainIdempotent(){val s=NativeRequestState();assertTrue(s.acceptRequest("one"));assertTrue(s.acceptRequest("two"));assertFalse(s.acceptRequest("one"));assertFalse(s.acceptRequest("two"))}
    @Test fun requestIdsSurviveRestore(){val s=NativeRequestState();assertTrue(s.acceptRequest("saved"));val r=NativeRequestState();r.restoreSeenRequestIds(s.seenRequestIdsState());assertFalse(r.acceptRequest("saved"));assertTrue(r.acceptRequest("new"))}
}
