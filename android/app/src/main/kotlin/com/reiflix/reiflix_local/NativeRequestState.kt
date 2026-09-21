package com.reiflix.reiflix_local

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray

class NativeRequestState {
    data class LifecycleAction(val action: String, val requestId: String?)

    private val supportedActions=setOf(
        "select_tree","scan_tree","verify_tree","release_tree","scan_media_store",
        "request_media_access","open_broad_storage_settings","check_storage_access",
        "scan_all_storage","cancel_scan","google_sign_in","play"
    )
    private val seenRequestIds=LinkedHashSet<String>()
    var lastHandledRequestId:String?=null
        private set
    var pendingLifecycleAction:String?=null
        private set
    var pendingLifecycleRequestId:String?=null
        private set
    private var lastConsumedLifecycleRequest:LifecycleAction?=null
    private var preferences:SharedPreferences?=null

    fun bind(context:Context){
        preferences=context.applicationContext.getSharedPreferences("reiflix_native_request_state",Context.MODE_PRIVATE)
        val serialized=preferences?.getString("seen_request_ids",null)
        if(!serialized.isNullOrBlank()) restoreSeenRequestIds(serialized)
        val persistedLast=preferences?.getString("last_handled_request_id",null)?.trim().orEmpty()
        if(persistedLast.isNotEmpty()) lastHandledRequestId=persistedLast
        val persistedAction=preferences?.getString("pending_lifecycle_action",null)
        val persistedRequestId=preferences?.getString("pending_lifecycle_request_id",null)
        if(pendingLifecycleAction==null && isSupportedAction(persistedAction)){
            pendingLifecycleAction=persistedAction
            pendingLifecycleRequestId=persistedRequestId?.trim()?.takeIf{it.isNotEmpty()}
        }
    }

    private fun persist(){
        preferences?.edit()
            ?.putString("seen_request_ids",seenRequestIdsState())
            ?.putString("last_handled_request_id",lastHandledRequestId)
            ?.putString("pending_lifecycle_action",pendingLifecycleAction)
            ?.putString("pending_lifecycle_request_id",pendingLifecycleRequestId)
            ?.apply()
    }

    fun acceptRequest(requestId:String?):Boolean{
        val id=requestId?.trim().orEmpty()
        if(id.isEmpty())return true
        if(!seenRequestIds.add(id))return false
        while(seenRequestIds.size>64)seenRequestIds.iterator().apply{next();remove()}
        lastHandledRequestId=id
        persist()
        return true
    }

    fun seenRequestIdsState():String=JSONArray(seenRequestIds.toList()).toString()

    fun restoreSeenRequestIds(serialized:String?){
        if(serialized.isNullOrBlank())return
        seenRequestIds.clear()
        runCatching{
            val a=JSONArray(serialized)
            for(i in 0 until a.length()){
                a.optString(i).trim().takeIf{it.isNotEmpty()}?.let(seenRequestIds::add)
            }
        }
        while(seenRequestIds.size>64)seenRequestIds.iterator().apply{next();remove()}
    }

    @Synchronized
    fun queueLifecycleAction(action:String,requestId:String?=null):Boolean{
        if(!isSupportedAction(action) || pendingLifecycleAction!=null)return false
        pendingLifecycleAction=action
        pendingLifecycleRequestId=requestId?.trim()?.takeIf{it.isNotEmpty()}
        persist()
        return true
    }

    @Synchronized
    fun consumeLifecycleRequest():LifecycleAction?{
        val action=pendingLifecycleAction ?: return null
        val result=LifecycleAction(action,pendingLifecycleRequestId)
        pendingLifecycleAction=null
        pendingLifecycleRequestId=null
        lastConsumedLifecycleRequest=result
        persist()
        return result
    }

    fun consumeLifecycleAction():String?=consumeLifecycleRequest()?.action
    fun consumedLifecycleRequestId():String?=lastConsumedLifecycleRequest?.requestId

    fun restore(lastRequestId:String?,pendingAction:String?,pendingRequestId:String?=null){
        val restoredId=lastRequestId?.trim().orEmpty()
        if(restoredId.isNotEmpty()) seenRequestIds.add(restoredId)
        if(restoredId.isNotEmpty()) lastHandledRequestId=restoredId
        if(isSupportedAction(pendingAction)){
            pendingLifecycleAction=pendingAction
            pendingLifecycleRequestId=pendingRequestId?.trim()?.takeIf{it.isNotEmpty()}
        }
        while(seenRequestIds.size>64)seenRequestIds.iterator().apply{next();remove()}
        persist()
    }

    companion object{
        fun isSupportedAction(action:String?):Boolean=
            action!=null&&NativeRequestState().supportedActions.contains(action)
    }
}
