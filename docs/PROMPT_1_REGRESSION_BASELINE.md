# Rei-Flix — Prompt 1 Regression Baseline

Baseline commit: b1f5bb8636f85c341d2d57c477973765c9ca1ca9
Diagnostic branch: diagnostic/prompt-1-regression-baseline

## Scope
Diagnosis, reproduction contracts, regression guards and documentation only. No definitive fixes from later prompts were implemented.

## Architecture found
Python/Flet -> AndroidBridge -> MainActivity -> Android APIs -> NativeMailbox -> Python polling -> LibraryService/LibraryStore -> SQLite/catalog -> Home/Organize/Details/Settings.

The inspected HEAD contains NativeMailbox, NativeIndex, LibraryStore, LibraryService, MainActivity, NativePlayerActivity, MediaStoreScanner, SafScanner, BroadStorageScanner, Media3 and an existing ArtworkEngine.

## Regression matrix

| ID | Problem | Current evidence | State | Later owner |
|---|---|---|---|---|
| RF-001 | Android Back | MainActivity uses OnBackPressedCallback, writes android_back to NativeMailbox; main.py consumes it with navigate_back. | REGRESSÃO / ANÁLISE ESTÁTICA | Prompt 2 |
| RF-002 | Library reload | MainActivity.onResume contains authorized scanMediaStore(null) / scanAllStorage(null); observers can also schedule scans. | REGRESSÃO POTENCIAL / ANÁLISE ESTÁTICA | Prompt 3 |
| RF-003 | Organize click | open_collection is async def while category/genre cards bind directly to on_click lambdas. | REGRESSÃO POTENCIAL / ANÁLISE ESTÁTICA | Prompt 5 |
| RF-004 | Genre limitation | Local GenreClassifier has 7 heuristic rules; AniList stores provider genres separately. The reported 16-item display limit is not proven to be a global hardcoded limit. | PARCIAL / INCONCLUSIVO | Prompt 6 |
| RF-005 | AniList/artwork | LibraryService already owns AniListClient and ArtworkEngine; cover_url/cover_cache and SQLite artwork persistence exist. | EXISTE / PARCIAL | Prompts 7-8 |
| RF-006 | Navigation lag | Home/Organize already use asyncio.to_thread/page.run_task in relevant paths; full attribution requires runtime profiling. | PARCIAL / INCONCLUSIVO | Prompt 9 |
| RF-007 | Player | Media3 NativePlayerActivity, player_error/player_exited contracts and Python event handling already exist. | EXISTE / PARCIAL | Prompts 11-13 |
| RF-008 | Horizontal seek | Prompt 12 removed horizontal swipe-to-seek; the current GestureLayer classifies horizontal movement and explicitly ignores it. | CORRIGIDO POR ANÁLISE ESTÁTICA | Prompt 12 |
| RF-009 | Player/lifecycle coupling | MainActivity and NativePlayerActivity have lifecycle handling; MainActivity also has resume discovery and storage/media observer scan paths. | REGRESSÃO POTENCIAL / INCONCLUSIVO | Prompt 3 |

## Key findings

### Android Back
The current MainActivity intercepts Android Back with AndroidX OnBackPressedCallback, generates a request ID, writes an android_back NativeMailbox event and lets Python call navigate_back(). The player has its own OnBackPressedCallback and finishes itself with android_back.

This is an existing cross-layer contract, not a missing feature. Prompt 2 should decide whether it remains mailbox-mediated or moves toward direct/native navigation while preserving the Flet stack.

AndroidX documents OnBackPressedDispatcher/OnBackPressedCallback and integration with OnBackInvokedDispatcher for Android 13+ predictive Back. citeturn0search3turn0search13

### Library reload
Lifecycle-aware scan state and duplicate-scan guards already exist, but MainActivity.onResume participates in authorized discovery. Media/volume broadcasts can schedule additional scans. This justifies a lifecycle/scan regression baseline, but does not prove every reload symptom has one cause.

### Organize
The source contains async open_collection() plus direct Flet click bindings to that coroutine. This is a concrete callback-contract risk worth preserving as a regression target. Prompt 1 does not change the production handler.

### Genres
There are two concepts: local GenreClassifier.RULES and AniList metadata genres. Therefore the reported 16-genre symptom cannot safely be attributed to GenreClassifier alone.

### Artwork
Artwork is not missing. ArtworkEngine exists and is connected to LibraryService; LibraryStore has artwork persistence and a covers cache. Prompt 1 therefore does not create another artwork subsystem.

### Player
Media3 remains the player engine. NativePlayerActivity already has player_error/player_exited contracts, immersive handling, gesture code, aspect-ratio support and track UI. Prompt 12 now removes horizontal swipe-to-seek and keeps seek on explicit controls/seekbar; vertical gestures are optional and touch-arbitrated.

## External references

CloudStream repository metadata identifies GPL-3.0; use it as a behavioral reference, not as source to copy. urlCloudStream repositoryhttps://github.com/recloudstream/cloudstream

NOVA aos-AVP is Apache-2.0 and separates Video UI, MediaLib, FileCoreLibrary and native multimedia components. This is a useful reference for later hardening, not a reason to replace Rei-Flix architecture. citeturn0search2turn0search6

Animiru is Apache-2.0 and describes itself as a video player and library manager; it is useful as an anime-library/settings reference. urlAnimiru repositoryhttps://github.com/quickdesh/Animiru

GitHub currently reports no license metadata for Rei-Flix, so no third-party license should be assumed for the project. urlRei-Flix repositoryhttps://github.com/reinansantos9090-debug/Rei-flix

## Validation classification

ANÁLISE ESTÁTICA: architecture, source contracts, callback patterns, lifecycle paths, genre implementation, artwork pipeline, player contracts and gesture path.

TESTE AUTOMATIZADO: tests/test_prompt1_regression_baseline.py is the new deterministic source-level regression guard.

NÃO VALIDADO EM DISPOSITIVO: Android Back, lifecycle recreation, real Flet clicks, MediaStore observer behavior, artwork/network timing, player opening/playback and physical swipe gestures.

BUILD/CI: not claimed as validated because the available repository connector can inspect/mutate GitHub but cannot execute local Python, pytest, Gradle or APK commands from a checkout.

## Explicit non-goals

No Scan Coordinator, GenreRegistry, Artwork Engine replacement, navigation rewrite, player UI rewrite, Settings Center, backup system or database rewrite was introduced by Prompt 1.
