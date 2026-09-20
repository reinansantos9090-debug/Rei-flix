package com.reiflix.reiflix_local

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeScanControllerTest {
    @Test fun cancelAll_marksActiveScan() {
        val id = "scan-test"
        assertTrue(NativeScanController.begin(id))
        assertTrue(NativeScanController.cancelAll().contains(id))
        assertTrue(NativeScanController.isCancelled(id))
        NativeScanController.finish(id)
        assertFalse(NativeScanController.isCancelled(id))
    }
}
