# ReiFlix Android native overlay

This directory is the Android part of ReiFlix. `MainActivity` is intentionally a
`FlutterActivity` replacement for the activity emitted by the Flet Android
template. It has three real Android responsibilities that Python cannot
perform:

* launch `ACTION_OPEN_DOCUMENT_TREE`, call `takePersistableUriPermission()`,
  recursively enumerate `DocumentFile` children with `ContentResolver` grants,
  and return document URIs/name/MIME/size/modified date;
* start Android Credential Manager with Google Identity (`GetGoogleIdOption`)
  and return only profile fields (not an ID token) to the app mailbox;
* play a persisted document URI with Media3 ExoPlayer in an immersive,
  landscape `NativePlayerActivity`, periodically emitting position/duration.

`NativeMailbox` is a deliberately small, token-free bridge file in `filesDir`.
The Python `AndroidBridge` drains it from the private Flet data directory and
writes library/profile/progress data to SQLite. Flet actions use an app-owned
`reiflix://native?action=…` deep link to call the Android host; no URI is
converted into a filesystem path and videos are never copied.

## Template integration

The Flet Android build template must merge this `android/app` module and use
`com.reiflix.reiflix_local.MainActivity` in its manifest. It also needs the
listed Media3, Credential Manager and Google Identity dependencies. This is a
native overlay rather than a broad-storage workaround. The CI build in this
repository currently uses the stock Flet client, so its APK template must be
configured to include this overlay before device delivery.
