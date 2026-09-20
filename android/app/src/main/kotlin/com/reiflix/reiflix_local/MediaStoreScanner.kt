package com.reiflix.reiflix_local

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.storage.StorageManager
import android.provider.MediaStore
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject

object MediaStoreScanner {
    const val SOURCE = "mediastore:external:video"
    const val DISPLAY_NAME = "Vídeos do dispositivo"
    private const val TAG = "[REIFLIX][MEDIASTORE]"
    private val videoExtensions = setOf("mp4","mkv","webm","avi","mov","m4v","ts","m2ts","flv","wmv")

    fun requiredPermissions(): Array<String> = when {
        Build.VERSION.SDK_INT >= 34 -> arrayOf(Manifest.permission.READ_MEDIA_VIDEO, Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED)
        Build.VERSION.SDK_INT >= 33 -> arrayOf(Manifest.permission.READ_MEDIA_VIDEO)
        Build.VERSION.SDK_INT >= 23 -> arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE)
        else -> emptyArray()
    }
    fun hasReadPermission(context: Context): Boolean = when {
        Build.VERSION.SDK_INT >= 34 -> has(context,Manifest.permission.READ_MEDIA_VIDEO) || has(context,Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED)
        Build.VERSION.SDK_INT >= 33 -> has(context,Manifest.permission.READ_MEDIA_VIDEO)
        Build.VERSION.SDK_INT >= 23 -> has(context,Manifest.permission.READ_EXTERNAL_STORAGE)
        else -> true
    }
    private fun has(context: Context,p:String)=context.checkSelfPermission(p)==PackageManager.PERMISSION_GRANTED
    fun accessLevel(context: Context): String = when {
        Build.VERSION.SDK_INT>=34&&has(context,Manifest.permission.READ_MEDIA_VIDEO)->"full"
        Build.VERSION.SDK_INT>=34&&has(context,Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED)->"partial"
        Build.VERSION.SDK_INT>=33&&has(context,Manifest.permission.READ_MEDIA_VIDEO)->"full"
        Build.VERSION.SDK_INT>=23&&has(context,Manifest.permission.READ_EXTERNAL_STORAGE)->"full"
        Build.VERSION.SDK_INT<23->"full"
        else->"denied"
    }
    fun isAuthorizedDocument(context: Context,uri:Uri):Boolean {
        if(uri.scheme!="content"||uri.authority!=MediaStore.AUTHORITY||!hasReadPermission(context))return false
        return runCatching{context.contentResolver.query(uri,arrayOf(MediaStore.Video.Media._ID),null,null,null)?.use{it.moveToFirst()}==true}.getOrDefault(false)
    }
    private fun volumeUuid(context: Context, volumeName: String): String {
        if(Build.VERSION.SDK_INT<24)return ""
        val manager=context.getSystemService(StorageManager::class.java) ?: return ""
        return manager.storageVolumes.firstOrNull {
            (Build.VERSION.SDK_INT>=30&&it.mediaStoreVolumeName==volumeName) ||
                (Build.VERSION.SDK_INT<30&&it.isPrimary&&volumeName==MediaStore.VOLUME_EXTERNAL_PRIMARY)
        }?.uuid.orEmpty()
    }
    fun scan(context: Context,onProgress:((JSONObject)->Unit)?=null,shouldCancel:()->Boolean={false}):JSONObject {
        check(hasReadPermission(context)){"Permissão de vídeos não concedida."}
        val resolver=context.contentResolver
        val volumeNames=if(Build.VERSION.SDK_INT>=29)MediaStore.getExternalVolumeNames(context).ifEmpty{setOf(MediaStore.VOLUME_EXTERNAL_PRIMARY)}else setOf(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        val projection=mutableListOf(MediaStore.Video.Media._ID,MediaStore.Video.Media.DISPLAY_NAME,MediaStore.Video.Media.MIME_TYPE,MediaStore.Video.Media.SIZE,MediaStore.Video.Media.DATE_MODIFIED)
        if(Build.VERSION.SDK_INT>=29){projection+=MediaStore.Video.Media.RELATIVE_PATH;projection+=MediaStore.MediaColumns.VOLUME_NAME}
        if(Build.VERSION.SDK_INT>=30){projection+=MediaStore.MediaColumns.GENERATION_ADDED;projection+=MediaStore.MediaColumns.GENERATION_MODIFIED}
        val documents=JSONArray();val volumeScopes=JSONArray();val errors=JSONArray()
        var files=0;var videos=0;var cancelled=false
        onProgress?.invoke(JSONObject().put("phase","started").put("source",SOURCE).put("files",0).put("videos",0))
        try{
            for(volumeName in volumeNames){
                if(shouldCancel()){cancelled=true;break}
                val version=if(Build.VERSION.SDK_INT>=29)runCatching{MediaStore.getVersion(context,volumeName)}.getOrDefault("") else ""
                val generation=if(Build.VERSION.SDK_INT>=30)runCatching{MediaStore.getGeneration(context,volumeName)}.getOrDefault(0L) else 0L
                val access=accessLevel(context);val scopeKey="mediastore:"+volumeName
                if(NativeIndex.canReuseMediaStoreVolume(context,volumeName,access,version,generation)){
                    val cached=NativeIndex.cachedDocuments(context,scopeKey)
                    for(i in 0 until cached.length())documents.put(cached.getJSONObject(i))
                    files+=cached.length();videos+=cached.length()
                    volumeScopes.put(JSONObject().put("volumeId",volumeName).put("scanGeneration",NativeIndex.cachedGeneration(context,scopeKey)).put("documents",cached).put("complete",true).put("reused",true).put("new",0).put("changed",0).put("unchanged",cached.length()).put("duplicates",0).put("removed",0))
                    onProgress?.invoke(JSONObject().put("phase","reused").put("source",SOURCE).put("volumeId",volumeName).put("files",files).put("videos",videos))
                    continue
                }
                val raw=JSONArray();val localErrors=JSONArray()
                val collection=if(Build.VERSION.SDK_INT>=29)MediaStore.Video.Media.getContentUri(volumeName)else MediaStore.Video.Media.EXTERNAL_CONTENT_URI
                resolver.query(collection,projection.toTypedArray(),null,null,MediaStore.Video.Media.DISPLAY_NAME+" COLLATE NOCASE ASC")?.use{cursor->
                    val idCol=cursor.getColumnIndex(MediaStore.Video.Media._ID);val nameCol=cursor.getColumnIndex(MediaStore.Video.Media.DISPLAY_NAME)
                    val mimeCol=cursor.getColumnIndex(MediaStore.Video.Media.MIME_TYPE);val sizeCol=cursor.getColumnIndex(MediaStore.Video.Media.SIZE)
                    val modCol=cursor.getColumnIndex(MediaStore.Video.Media.DATE_MODIFIED);val relCol=if(Build.VERSION.SDK_INT>=29)cursor.getColumnIndex(MediaStore.Video.Media.RELATIVE_PATH)else -1
                    val volCol=if(Build.VERSION.SDK_INT>=29)cursor.getColumnIndex(MediaStore.MediaColumns.VOLUME_NAME)else -1
                    val gaCol=if(Build.VERSION.SDK_INT>=30)cursor.getColumnIndex(MediaStore.MediaColumns.GENERATION_ADDED)else -1
                    val gmCol=if(Build.VERSION.SDK_INT>=30)cursor.getColumnIndex(MediaStore.MediaColumns.GENERATION_MODIFIED)else -1
                    if(idCol<0||nameCol<0)localErrors.put("O MediaStore não retornou os dados necessários.")else while(cursor.moveToNext()){
                        if(shouldCancel()){cancelled=true;break}
                        files++;val id=cursor.getLong(idCol);val name=cursor.getString(nameCol)?:"video-"+id
                        val mime=if(mimeCol>=0&&!cursor.isNull(mimeCol))cursor.getString(mimeCol) else "video/*"
                        val ext=name.substringAfterLast('.',"").lowercase();if(!mime.startsWith("video/")&&ext !in videoExtensions)continue
                        val relDir=if(relCol>=0&&!cursor.isNull(relCol))cursor.getString(relCol).orEmpty().trimEnd('/')else ""
                        val rel=if(relDir.isBlank())name else relDir+"/"+name
                        val actualVol=if(volCol>=0&&!cursor.isNull(volCol))cursor.getString(volCol)else volumeName
                        val uri=if(Build.VERSION.SDK_INT>=29)MediaStore.Video.Media.getContentUri(actualVol,id)else android.content.ContentUris.withAppendedId(MediaStore.Video.Media.EXTERNAL_CONTENT_URI,id)
                        val item=JSONObject().put("uri",uri.toString()).put("name",name).put("relativePath",rel).put("volumeName",actualVol).put("volumeId",actualVol).put("volumeUuid",volumeUuid(context,actualVol)).put("mimeType",mime).put("size",if(sizeCol>=0&&!cursor.isNull(sizeCol))cursor.getLong(sizeCol)else 0L).put("modifiedAt",if(modCol>=0&&!cursor.isNull(modCol))cursor.getLong(modCol)*1000L else 0L)
                        if(gaCol>=0&&!cursor.isNull(gaCol))item.put("generationAdded",cursor.getLong(gaCol))
                        if(gmCol>=0&&!cursor.isNull(gmCol))item.put("generationModified",cursor.getLong(gmCol))
                        raw.put(item);videos++
                        if(videos%100==0)onProgress?.invoke(JSONObject().put("phase","scanning").put("source",SOURCE).put("volumeId",volumeName).put("files",files).put("videos",videos))
                    }
                }?:localErrors.put("O MediaStore não conseguiu consultar o volume "+volumeName+".")
                for(i in 0 until localErrors.length())errors.put(localErrors.getString(i))
                val complete=localErrors.length()==0&&!shouldCancel();if(shouldCancel())cancelled=true
                val prepared=NativeIndex.prepare(context,SOURCE,scopeKey,raw,complete,JSONObject().put("mediaStoreVersion",version).put("mediaStoreGeneration",generation).put("accessLevel",access).put("volumeId",volumeName))
                for(i in 0 until prepared.documents.length())documents.put(prepared.documents.getJSONObject(i))
                volumeScopes.put(JSONObject().put("volumeId",volumeName).put("scanGeneration",prepared.generation).put("documents",prepared.documents).put("complete",complete).put("reused",false).put("new",prepared.newItems).put("changed",prepared.changedItems).put("unchanged",prepared.unchangedItems).put("duplicates",prepared.duplicates).put("removed",prepared.removedItems))
                if(cancelled)break
            }
        }catch(security:SecurityException){Log.w(TAG,"MediaStore permission/query denied",security);errors.put("O acesso aos vídeos do dispositivo foi negado.")}
        catch(exception:Exception){Log.w(TAG,"MediaStore query failed",exception);errors.put("Não foi possível consultar os vídeos do dispositivo.")}
        onProgress?.invoke(JSONObject().put("phase","finished").put("source",SOURCE).put("files",files).put("videos",videos))
        return JSONObject().put("source",SOURCE).put("name",DISPLAY_NAME).put("documents",documents).put("volumeScopes",volumeScopes).put("stats",JSONObject().put("files",files).put("videos",videos).put("errors",errors)).put("partial",errors.length()>0||cancelled).put("cancelled",cancelled)
    }
}
