"""Conservative evidence-based identities for local media discoveries."""
from __future__ import annotations

from urllib.parse import unquote, urlparse


def _shared_relative(value: str) -> str | None:
    value = unquote(value or "").replace("\\", "/").strip("/")
    for marker in ("storage/emulated/0/", "sdcard/"):
        if value.startswith(marker):
            value = value[len(marker):]
            break
    return value.casefold() or None


def local_media_identity(*, uri: str, source_kind: str | None, relative_path: str | None,
                         size: object = None, modified_at: object = None) -> str | None:
    """Identify one shared local file, never an arbitrary cloud document.

    A handle from MediaStore/SAF is not enough to infer that two files match.
    Cross-scanner identity therefore requires a shared relative path plus size
    and modification time. Cloud DocumentsProviders stay source-isolated.
    """
    try:
        size, modified_at = int(size), int(float(modified_at))
    except (TypeError, ValueError):
        return None
    if size <= 0 or modified_at <= 0:
        return None
    parsed = urlparse(uri or "")
    candidate = relative_path or ""
    if parsed.scheme == "file":
        candidate = unquote(parsed.path)
    elif source_kind == "saf":
        if parsed.netloc != "com.android.externalstorage.documents":
            return None
        document = unquote(parsed.path)
        if "/document/" in document:
            document = document.split("/document/", 1)[1]
        candidate = document.split(":", 1)[1] if ":" in document else ""
    elif source_kind not in {"mediastore", "broad_storage"}:
        return None
    relative = _shared_relative(candidate)
    return f"shared-local:{relative}|{size}|{modified_at}" if relative else None
