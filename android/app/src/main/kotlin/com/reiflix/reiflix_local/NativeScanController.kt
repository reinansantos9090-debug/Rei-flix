package com.reiflix.reiflix_local

import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicBoolean

object NativeScanController {
    private val tokens = ConcurrentHashMap<String, AtomicBoolean>()
    fun begin(scanId: String): Boolean = tokens.putIfAbsent(scanId, AtomicBoolean(false)) == null
    fun isCancelled(scanId: String): Boolean = tokens[scanId]?.get() == true
    fun cancelAll(): List<String> {
        val ids = tokens.keys.toList()
        ids.forEach { tokens[it]?.set(true) }
        return ids
    }
    fun finish(scanId: String) { tokens.remove(scanId) }
}
