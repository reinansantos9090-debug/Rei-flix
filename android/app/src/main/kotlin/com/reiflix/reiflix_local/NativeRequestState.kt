package com.reiflix.reiflix_local

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

    fun acceptRequest(requestId:String?):Boolean{
        val id=requestId?.trim().orEmpty()
        if(id.isEmpty())return true
        if(!seenRequestIds.add(id))return false
        while(seenRequestIds.size>64)seenRequestIds.iterator().apply{next();remove()}
        lastHandledRequestId=id
        return true
    }

    fun seenRequestIdsState():String=JSONArray(seenRequestIds.toList()).toString()

    fun restoreSeenRequestIds(serialized:String?){
        seenRequestIds.clear()
        if(serialized.isNullOrBlank())return
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
        return true
    }

    @Synchronized
    fun consumeLifecycleRequest():LifecycleAction?{
        val action=pendingLifecycleAction ?: return null
        val result=LifecycleAction(action,pendingLifecycleRequestId)
        pendingLifecycleAction=null
        pendingLifecycleRequestId=null
        lastConsumedLifecycleRequest=result
        return result
    }

    fun consumeLifecycleAction():String?=consumeLifecycleRequest()?.action
    fun consumedLifecycleRequestId():String?=lastConsumedLifecycleRequest?.requestId

    fun restore(lastRequestId:String?,pendingAction:String?,pendingRequestId:String?=null){
        lastHandledRequestId=lastRequestId
        pendingLifecycleAction=pendingAction?.takeIf{isSupportedAction(it)}
        pendingLifecycleRequestId=if(pendingLifecycleAction!=null) pendingRequestId else null
    }

    companion object{
        fun isSupportedAction(action:String?):Boolean=
            action!=null&&NativeRequestState().supportedActions.contains(action)
    }
}
