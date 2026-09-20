package com.reiflix.reiflix_local

import org.json.JSONArray

class NativeRequestState {
    private val supportedActions=setOf("select_tree","scan_tree","verify_tree","release_tree","scan_media_store","request_media_access","open_broad_storage_settings","check_storage_access","scan_all_storage","cancel_scan","google_sign_in","play")
    private val seenRequestIds=LinkedHashSet<String>()
    var lastHandledRequestId:String?=null;private set
    var pendingLifecycleAction:String?=null;private set
    fun acceptRequest(requestId:String?):Boolean{
        val id=requestId?.trim().orEmpty()
        if(id.isEmpty())return true
        if(!seenRequestIds.add(id))return false
        while(seenRequestIds.size>64)seenRequestIds.iterator().apply{next();remove()}
        lastHandledRequestId=id;return true
    }
    fun seenRequestIdsState():String=JSONArray(seenRequestIds.toList()).toString()
    fun restoreSeenRequestIds(serialized:String?){
        seenRequestIds.clear();if(serialized.isNullOrBlank())return
        runCatching{val a=JSONArray(serialized);for(i in 0 until a.length())a.optString(i).trim().takeIf{it.isNotEmpty()}?.let(seenRequestIds::add)}
        while(seenRequestIds.size>64)seenRequestIds.iterator().apply{next();remove()}
    }
    fun queueLifecycleAction(action:String):Boolean{if(!isSupportedAction(action))return false;if(pendingLifecycleAction==action)return false;pendingLifecycleAction=action;return true}
    fun consumeLifecycleAction():String?=pendingLifecycleAction.also{pendingLifecycleAction=null}
    fun restore(lastRequestId:String?,pendingAction:String?){lastHandledRequestId=lastRequestId;pendingLifecycleAction=pendingAction?.takeIf{isSupportedAction(it)}}
    companion object{fun isSupportedAction(action:String?):Boolean=action!=null&&NativeRequestState().supportedActions.contains(action)}
}
