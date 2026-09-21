# ReiFlix native Android host

This directory is the **native host overlay** for the Flet Android client. It
is not a standalone Flutter application and, by itself, it is not a complete
Android project: it intentionally relies on the Flutter embedding supplied by
the Flet-generated host. The overlay replaces that host's `MainActivity` with
`com.reiflix.reiflix_local.MainActivity` and adds the classes and dependencies
that cannot be implemented by Python:

* `SafScanner` uses `ACTION_OPEN_DOCUMENT_TREE`, preserves URI grants and
  enumerates `DocumentFile` objects as `content://` references;
* `NativeMailbox` transfers small JSON events through the app-private files
  directory without copying media files;
* `NativePlayerActivity` plays a persisted document URI through Media3;
* `GoogleIdentity` invokes Credential Manager and sends only profile fields to
  the mailbox.

## Toolchain contract

| Component | Version/configuration |
| --- | --- |
| Flet | `0.86.5` (`pyproject.toml`) |
| Flutter required by installed Flet | `3.44.8` (`flet.version.flutter_version`) |
| Android Gradle Plugin | `8.6.1` |
| Kotlin | `2.0.21` |
| Java toolchain | 17 |
| compile / target SDK | 36 / 36 |
| minimum SDK | 23 |
| Media3 | `1.5.1` for ExoPlayer and UI |

The repository does **not** commit an APK. The workflow builds one and refuses
to publish it unless DEX contains `MainActivity`, `NativeMailbox`,
`SafScanner`, `MediaStoreScanner`, `BroadStorageScanner`,
`NativePlayerActivity`, and `GoogleIdentity`. This prevents accidentally
releasing the stock Flet client, which would not understand `reiflix://native`.

## Required Flet host integration

A build template must merge `android/app` into Flet's generated Android host,
retain the Flet Flutter embedding, and use this module's manifest/activity and
dependencies. The standalone `android/` directory deliberately cannot be built
with `gradle :app:compileDebugKotlin` because `FlutterActivity` is supplied by
that generated host. Do not replace it with a plain Android app or fabricate a
filesystem path for a SAF URI.

`flet build apk --yes` is followed by `scripts/verify_android_host.py` in CI.
If this check reports missing descriptors, the selected Flet template did not
merge this overlay; the build must be fixed before an APK can be published.

## Validação física e escalabilidade de bibliotecas

O caminho Android de descoberta usa lotes de **250 documentos** por padrão. Esse
valor limita a memória temporária da ponte e do scanner sem transformar cada
arquivo em um evento individual. O limite configurável é restringido a 25..1000.

Broad Storage, SAF e MediaStore não retornam mais um `JSONArray` com toda a
biblioteca. Cada lote é preparado pelo `NativeIndex` em NDJSON temporário,
identificado por `scanId`, `generationId`, `batchId` e número do lote. O
snapshot anterior só é substituído quando a geração termina em
`COMPLETED` ou `EMPTY_COMPLETE`. PARTIAL, CANCELLED, UNAVAILABLE e FAILED
preservam o snapshot anterior e não executam reconciliação destrutiva.

A instrumentação Android está em
`app/src/androidTest/kotlin/com/reiflix/reiflix_local/DeviceFlowInstrumentedTest.kt`.
O executor físico está em `scripts/validate_android_device.py` e exige `adb`;
ele nunca registra um teste físico como concluído quando não existe dispositivo
autorizado.

No ambiente de desenvolvimento usado para esta alteração não há `adb`
nem um dispositivo/emulador Android conectado. Portanto, os fluxos que
dependem do seletor SAF, Settings, volumes removíveis/USB e reprodução física
dos arquivos `66619.mp4`, `66621.mp4` e `66625.mp4` continuam como
**AINDA NÃO VALIDADO** até execução no dispositivo.

Os testes de carga Python de escalabilidade simulam 10.000, 50.000 e 100.000
documentos alimentando `LibraryService.ingest_documents_batch()` em blocos
de 250, verificando que nenhum lote ultrapassa esse limite e que cada lote
atualiza o progresso persistido.
