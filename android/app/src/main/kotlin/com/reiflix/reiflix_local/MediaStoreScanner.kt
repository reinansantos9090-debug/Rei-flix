package com.reiflix.reiflix_local

import android.Manifest
import android.content.Context
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
    private fun has(context: Context,p:String)=context.checkSelfPermission(p)==android.content.pm.PackageManager.PERMISSION_GRANTED

    fun accessLevelValue(context: Context): MediaAccessLevel =
        StorageAuthorization.mediaAccess(
            Build.VERSION.SDK_INT,
            readExternalStorage = Build.VERSION.SDK_INT in 23..32 &&
                has(context, Manifest.permission.READ_EXTERNAL_STORAGE),
            readMediaVideo = Build.VERSION.SDK_INT >= 33 &&
                has(context, Manifest.permission.READ_MEDIA_VIDEO),
            readSelectedVisualMedia = Build.VERSION.SDK_INT >= 34 &&
                has(context, Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED),
        )

    fun hasReadPermission(context: Context): Boolean =
        StorageAuthorization.canScanMediaStore(accessLevelValue(context))

    fun accessLevel(context: Context): String = when (accessLevelValue(context)) {
        MediaAccessLevel.FULL -> "full"
        MediaAccessLevel.PARTIAL -> "partial"
        MediaAccessLevel.DENIED -> "denied"
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
    fun scan(context: Context,onProgress:((JSONObject)->Unit)?=null,shouldCancel:()->Boolean={false},scanId:String?=null,onBatch:((JSONObject)->Unit)?=null):JSONObject {
        check(hasReadPermission(context)){"Permissão de vídeos não concedida."}
        val resolver=context.contentResolver
        val volumeNames=if(Build.VERSION.SDK_INT>=29)MediaStore.getExternalVolumeNames(context).ifEmpty{setOf(MediaStore.VOLUME_EXTERNAL_PRIMARY)}else setOf(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        val projection=mutableListOf(MediaStore.Video.Media._ID,MediaStore.Video.Media.DISPLAY_NAME,MediaStore.Video.Media.MIME_TYPE,MediaStore.Video.Media.SIZE,MediaStore.Video.Media.DATE_MODIFIED)
        if(Build.VERSION.SDK_INT>=29){projection+=MediaStore.Video.Media.RELATIVE_PATH;projection+=MediaStore.MediaColumns.VOLUME_NAME}
        if(Build.VERSION.SDK_INT>=30){projection+=MediaStore.MediaColumns.GENERATION_ADDED;projection+=MediaStore.MediaColumns.GENERATION_MODIFIED}
        val volumeScopes=JSONArray();val errors=JSONArray()
        val access=accessLevel(context)
        val accessState = accessLevelValue(context)
        check(StorageAuthorization.canScanMediaStore(accessState)) { "Permissão de vídeos não concedida." }
        var files=0;var videos=0;var cancelled=false
        onProgress?.invoke(JSONObject().put("phase","started").put("source",SOURCE).put("files",0).put("videos",0))
        for(volumeName in volumeNames){
            if(shouldCancel()){cancelled=true;break}
            var activeGeneration=0L
            var activeScopeKey="mediastore:"+volumeName
            try{
                val version=if(Build.VERSION.SDK_INT>=29)runCatching{MediaStore.getVersion(context,volumeName)}.getOrDefault("") else ""
                val generation=if(Build.VERSION.SDK_INT>=30)runCatching{MediaStore.getGeneration(context,volumeName)}.getOrDefault(0L) else 0L
                val scopeKey=activeScopeKey
                if(NativeIndex.canReuseMediaStoreVolume(context,volumeName,access,version,generation)){
                    val cachedGeneration=NativeIndex.cachedGeneration(context,scopeKey)
                    val cachedCount=NativeIndex.forEachCachedBatch(context,scopeKey,NativeBatch.DEFAULT_SIZE) { batch,batchNumber ->
                        onBatch?.invoke(JSONObject()
                            .put("volumeId",volumeName)
                            .put("batchId","reused:" + NativeIndex.generationId(SOURCE,scopeKey,cachedGeneration) + ":" + batchNumber)
                            .put("batchNumber",batchNumber)
                            .put("batchSize",batch.length())
                            .put("reused",true)
                            .put("documents",batch))
                    }
                    files+=cachedCount;videos+=cachedCount
                    volumeScopes.put(JSONObject().put("volumeId",volumeName).put("scanGeneration",cachedGeneration).put("complete",true).put("reused",true).put("status",if(cachedCount==0) NativeIndex.STATUS_EMPTY_COMPLETE else NativeIndex.STATUS_COMPLETED)
                        .put("generationId",NativeIndex.generationId(SOURCE,scopeKey,cachedGeneration))
                        .put("scopeKind","volume").put("scopeRef",volumeName)
                        .put("batchCount",if(cachedCount==0) 0 else (cachedCount + NativeBatch.DEFAULT_SIZE - 1) / NativeBatch.DEFAULT_SIZE)
                        .put("processed",cachedCount).put("duplicates",0).put("removed",0))
                    onProgress?.invoke(JSONObject().put("phase","reused").put("source",SOURCE).put("volumeId",volumeName).put("files",files).put("videos",videos))
                    continue
                }
                val scopeMetadata=JSONObject().put("mediaStoreVersion",version).put("mediaStoreGeneration",generation).put("scanId",scanId ?: "")
                    .put("accessLevel",access).put("volumeId",volumeName)
                val generationId=NativeIndex.startGeneration(context,SOURCE,scopeKey,scopeMetadata)
                activeGeneration=generationId
                val localErrors=JSONArray()
                val batches=NativeBatch.Accumulator(NativeBatch.DEFAULT_SIZE) { batch,batchId,batchNumber ->
                    onBatch?.invoke(JSONObject()
                        .put("volumeId",volumeName)
                        .put("generation",generationId)
                        .put("batchId",batchId)
                        .put("batchNumber",batchNumber)
                        .put("batchSize",batch.length())
                        .put("reused",false)
                        .put("documents",batch))
                }
                var localCancelled=false
                val collection=if(Build.VERSION.SDK_INT>=29)MediaStore.Video.Media.getContentUri(volumeName)else MediaStore.Video.Media.EXTERNAL_CONTENT_URI
                resolver.query(collection,projection.toTypedArray(),null,null,MediaStore.Video.Media.DISPLAY_NAME+" COLLATE NOCASE ASC")?.use{cursor->
                    val idCol=cursor.getColumnIndex(MediaStore.Video.Media._ID);val nameCol=cursor.getColumnIndex(MediaStore.Video.Media.DISPLAY_NAME)
                    val mimeCol=cursor.getColumnIndex(MediaStore.Video.Media.MIME_TYPE);val sizeCol=cursor.getColumnIndex(MediaStore.Video.Media.SIZE)
                    val modCol=cursor.getColumnIndex(MediaStore.Video.Media.DATE_MODIFIED);val relCol=if(Build.VERSION.SDK_INT>=29)cursor.getColumnIndex(MediaStore.Video.Media.RELATIVE_PATH)else -1
                    val volCol=if(Build.VERSION.SDK_INT>=29)cursor.getColumnIndex(MediaStore.MediaColumns.VOLUME_NAME)else -1
                    val gaCol=if(Build.VERSION.SDK_INT>=30)cursor.getColumnIndex(MediaStore.MediaColumns.GENERATION_ADDED)else -1
                    val gmCol=if(Build.VERSION.SDK_INT>=30)cursor.getColumnIndex(MediaStore.MediaColumns.GENERATION_MODIFIED)else -1
                    if(idCol<0||nameCol<0)localErrors.put("O MediaStore não retornou os dados necessários.")else while(cursor.moveToNext()){
                        if(shouldCancel()){cancelled=true;localCancelled=true;break}
                        files++;val id=cursor.getLong(idCol);val name=cursor.getString(nameCol)?:"video-"+id
                        val mime=if(mimeCol>=0&&!cursor.isNull(mimeCol))cursor.getString(mimeCol) else "video/*"
                        val ext=name.substringAfterLast('.',"").lowercase();if(!mime.startsWith("video/")&&ext !in videoExtensions)continue
                        val relDir=if(relCol>=0&&!cursor.isNull(relCol))cursor.getString(relCol).orEmpty().trimEnd('/')else ""
                        val rel=if(relDir.isBlank())name else relDir+"/"+name
                        val actualVol=if(volCol>=0&&!cursor.isNull(volCol))cursor.getString(volCol)else volumeName
                        val uri=if(Build.VERSION.SDK_INT>=29)MediaStore.Video.Media.getContentUri(actualVol,id)else android.content.ContentUris.withAppendedId(MediaStore.Video.Media.EXTERNAL_CONTENT_URI,id)
                        val item=JSONObject().put("uri",uri.toString()).put("name",name).put("relativePath",rel).put("volumeName",actualVol).put("volumeId",actualVol).put("volumeUuid",volumeUuid(context,actualVol))
                            .put("mediaId",id).put("mimeType",mime).put("size",if(sizeCol>=0&&!cursor.isNull(sizeCol))cursor.getLong(sizeCol)else 0L).put("modifiedAt",if(modCol>=0&&!cursor.isNull(modCol))cursor.getLong(modCol)*1000L else 0L)
                        if(gaCol>=0&&!cursor.isNull(gaCol))item.put("generationAdded",cursor.getLong(gaCol))
                        if(gmCol>=0&&!cursor.isNull(gmCol))item.put("generationModified",cursor.getLong(gmCol))
                        batches.add(item);videos++
                        if(videos%100==0)onProgress?.invoke(JSONObject().put("phase","scanning").put("source",SOURCE).put("volumeId",volumeName).put("files",files).put("videos",videos))
                    }
                }?:localErrors.put("O MediaStore não conseguiu consultar o volume "+volumeName+".")
                for(i in 0 until localErrors.length())errors.put(localErrors.getString(i))
                if(shouldCancel()){cancelled=true;localCancelled=true}
                val complete=StorageAuthorization.canReconcileMediaStore(accessState) &&
                    localErrors.length()==0 && !localCancelled && !cancelled
                val status=when {
                    localCancelled||cancelled->NativeIndex.STATUS_CANCELLED
                    !complete->NativeIndex.STATUS_PARTIAL
                    else->NativeIndex.STATUS_COMPLETED
                }
                batches.flush()
                val stagedDocuments=NativeIndex.stagedDocumentCount(context,SOURCE,scopeKey,generationId)
                val batchCount=NativeIndex.batchCount(context,SOURCE,scopeKey,generationId)
                val finished=NativeIndex.finishGeneration(
                    context,SOURCE,scopeKey,generationId,status,
                    JSONObject(scopeMetadata.toString()).put("errors",localErrors).put("status",status)
                        .put("batchCount",batchCount).put("processed",stagedDocuments)
                )
                volumeScopes.put(JSONObject().put("volumeId",volumeName).put("scanGeneration",generationId).put("generationId",NativeIndex.generationId(SOURCE, scopeKey, generationId)).put("status",status)
                    .put("complete",complete).put("reused",false).put("batchCount",batchCount).put("processed",stagedDocuments)
                    .put("duplicates",finished.optInt("duplicates",0)).put("removed",0).put("errors",localErrors))
                if(cancelled)break
            }catch(security:SecurityException){
                Log.w(TAG,"MediaStore permission/query denied for volume $volumeName",security)
                errors.put("O acesso ao volume $volumeName foi negado.")
                if(activeGeneration>0) NativeIndex.finishGeneration(context,SOURCE,activeScopeKey,activeGeneration,NativeIndex.STATUS_FAILED,JSONObject().put("error",security.message ?: "MediaStore permission/query denied"))
            }catch(exception:Exception){
                Log.w(TAG,"MediaStore query failed for volume $volumeName",exception)
                errors.put("Não foi possível consultar o volume $volumeName.")
                if(activeGeneration>0) NativeIndex.finishGeneration(context,SOURCE,activeScopeKey,activeGeneration,NativeIndex.STATUS_FAILED,JSONObject().put("error",exception.message ?: "MediaStore query failed"))
            }
        }
        onProgress?.invoke(JSONObject().put("phase","finished").put("source",SOURCE).put("files",files).put("videos",videos))
        return JSONObject().put("source",SOURCE).put("name",DISPLAY_NAME).put("volumeScopes",volumeScopes)
            .put("stats",JSONObject().put("files",files).put("videos",videos).put("errors",errors).put("access",access)
                .put("canScan", StorageAuthorization.canScanMediaStore(accessState))
                .put("canReconcile", StorageAuthorization.canReconcileMediaStore(accessState)))
            .put("partial",errors.length()>0||cancelled||access!="full").put("cancelled",cancelled)
    }
}
