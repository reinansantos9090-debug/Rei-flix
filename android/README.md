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
