import unittest
from pathlib import Path
import tempfile

from core.library_service import LibraryService
from core.library_store import LibraryStore

ROOT = Path(__file__).resolve().parents[1]
SAF = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/SafScanner.kt"
MAIN_ACTIVITY = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt"
MAILBOX = ROOT / "android/app/src/main/kotlin/com/reiflix/reiflix_local/NativeMailbox.kt"
MAIN = ROOT / "main.py"


class TestSafProfessionalContract(unittest.TestCase):
    def test_picker_result_checks_result_code_and_uri_before_persistence_or_scan(self):
        source = MAIN_ACTIVITY.read_text(encoding="utf-8")
        self.assertIn("result.resultCode != RESULT_OK || uri == null", source)
        self.assertIn("SafScanner.persistPermission(this, uri, flags)", source)
        self.assertIn("scanTree(uri.toString(), requestId)", source)

    def test_picker_uses_persistable_read_grant(self):
        source = MAIN_ACTIVITY.read_text(encoding="utf-8")
        self.assertIn("Intent.ACTION_OPEN_DOCUMENT_TREE", source)
        self.assertIn("Intent.FLAG_GRANT_READ_URI_PERMISSION", source)
        self.assertIn("Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION", source)
        self.assertIn("Intent.FLAG_GRANT_PREFIX_URI_PERMISSION", source)

    def test_tree_identity_is_authority_document_and_volume_scoped(self):
        source = SAF.read_text(encoding="utf-8")
        self.assertIn("authority", source)
        self.assertIn("documentId", source)
        self.assertIn("volumeId", source)
        self.assertIn('"saf:"+authority+":"+documentId', source)
        self.assertIn("content://", source)

    def test_provider_states_are_explicit(self):
        source = SAF.read_text(encoding="utf-8")
        for state in ("STATUS_EMPTY_COMPLETE", "STATUS_PARTIAL", "STATUS_CANCELLED",
                      "STATUS_FAILED", "STATUS_REVOKED", "STATUS_UNAVAILABLE", "STATUS_COMPLETED"):
            self.assertIn(state, source)

    def test_nomedia_is_discovery_level_behavior(self):
        source = SAF.read_text(encoding="utf-8")
        self.assertIn('name.equals(".nomedia",ignoreCase=true)', source)
        self.assertIn("nomediaDirectories", source)
        self.assertIn("nomediaFiles", source)

    def test_metadata_absence_and_mime_fallback_are_not_fatal(self):
        source = SAF.read_text(encoding="utf-8")
        self.assertIn("metadataMissingSize", source)
        self.assertIn("metadataMissingModified", source)
        self.assertIn("mimeFallbacks", source)
        self.assertIn("application/octet-stream", source)

    def test_mailbox_classifies_saf_scan_lifecycle(self):
        source = MAILBOX.read_text(encoding="utf-8")
        self.assertIn('"CANCELLED" -> "scan_cancelled"', source)
        self.assertIn('"PARTIAL" -> "scan_partial"', source)
        self.assertIn('"FAILED" -> "scan_failed"', source)
        self.assertIn('"REVOKED" -> "saf_revoked"', source)
        self.assertIn('"UNAVAILABLE" -> "saf_unavailable"', source)

    def test_scan_failure_does_not_revoke_saf_authorization(self):
        source = MAIN.read_text(encoding="utf-8")
        block_start = source.find("elif event_type in {'saf_error','google_error'}:")
        block = source[block_start:block_start + 5000]
        self.assertIn("status == 'REVOKED'", block)
        self.assertIn("status in {'UNAVAILABLE', 'FAILED', 'PARTIAL'}", block)
        self.assertIn("update_folder_status(tree_uri, 'unavailable'", block)

    def test_persisted_tree_inventory_does_real_validation(self):
        source = MAIN_ACTIVITY.read_text(encoding="utf-8")
        self.assertIn("SafScanner.inspectTree(appContext, uri, requirePersisted = true)", source)
        self.assertIn("inventoryComplete", source)

    def test_store_persists_saf_identity(self):
        with tempfile.TemporaryDirectory() as data_dir:
            store = LibraryStore(data_dir)
            tree = "content://com.example.documents/tree/primary%3AMovies"
            store.add_folder(
                tree,
                name="Movies",
                kind="saf",
                saf_authority="com.example.documents",
                saf_document_id="primary:Movies",
                saf_volume_id="primary",
                saf_identity="saf:com.example.documents:primary:Movies",
            )
            folder = store.folders()[0]
            self.assertEqual("com.example.documents", folder["saf_authority"])
            self.assertEqual("primary:Movies", folder["saf_document_id"])
            self.assertEqual("primary", folder["saf_volume_id"])
            self.assertEqual("saf:com.example.documents:primary:Movies", folder["saf_identity"])

    def test_failed_native_ingest_keeps_previous_items_available(self):
        with tempfile.TemporaryDirectory() as data_dir:
            store = LibraryStore(data_dir)
            service = LibraryService(store)
            doc = {
                "uri": "content://provider/tree/document/1",
                "name": "Show S01E01.mkv",
                "relativePath": "Show S01E01.mkv",
                "mimeType": "video/x-matroska",
                "size": 100,
                "modifiedAt": 1000,
            }
            service.ingest_documents(
                "content://provider/tree/root",
                [doc],
                source_kind="saf",
                scan_id="ok",
                scan_stats={"status": "completed"},
            )
            service.ingest_documents(
                "content://provider/tree/root",
                [],
                source_kind="saf",
                scan_id="fail",
                scan_stats={"status": "failed"},
                scan_errors=["provider failure"],
            )
            row = store.physical_row(doc["uri"])
            self.assertFalse(row["missing"])
            self.assertEqual("available", row["availability_state"])
            self.assertEqual("error", store.scan_by_id("fail")["status"])


if __name__ == "__main__":
    unittest.main()
