# ReiAnix — Jetpack Compose Foundation

## Scope

Prompt 01 establishes only the Kotlin + Jetpack Compose foundation. It does not migrate Home,
Biblioteca, Buscar, Details, Ajustes, player UI, or navigation routes.

## Current entry boundary

MainActivity remains the existing FlutterFragmentActivity entry used by the Flet-generated Android
host. Compose is enabled in the same Android module but is not attached to that launcher in this
step. The foundation is therefore reversible and does not change the current user-visible UI.

NativePlayerActivity remains a View-based ComponentActivity using Media3. No player migration is
performed here.

## Data and domain boundary

There is no second Kotlin database or duplicate catalog. The existing Python/Flet + SQLite +
scanner/SAF/MediaStore pipeline remains authoritative until a later prompt explicitly moves a
specific screen or capability.

Compose UI must consume state through ViewModels/StateFlow and call application-facing boundaries
rather than embedding scan, persistence, playback, or storage business rules inside Composables.

## Navigation boundary

Navigation Compose 2.9.8 is available in the module, but Prompt 01 creates no route graph and no
artificial destinations. Destination IDs and arguments will be defined only when the corresponding
screen migration is implemented.

## Coroutine/lifecycle boundary

Future screen ViewModels should expose immutable StateFlow and use viewModelScope for cancellable
work. Flow collection in Composables must be lifecycle-aware. Existing Flet callbacks, NativeMailbox
events, scanner tasks, and Media3 lifecycle remain unchanged.

## Toolchain contract

Kotlin: 2.0.21
Compose Compiler Gradle plugin: 2.0.21
Compose BOM: 2026.06.00
Material 3: managed by the BOM
Navigation Compose: 2.9.8
Lifecycle ViewModel Compose: 2.10.0
Activity Compose: 1.13.0
compileSdk/targetSdk: 36
AGP: 8.9.1

Compose 1.12.x requires compileSdk 37 and AGP 9.1.2+, so Prompt 01 intentionally stays on the
2026.06.00 BOM rather than upgrading the application's Android toolchain.
