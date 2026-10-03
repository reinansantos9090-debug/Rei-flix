from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from core.compose_library_bridge import ComposeLibraryBridge
from core.storage_access import StorageCapabilities


class FakeLibrary:
    def catalog(self):
        return []

    def continue_watching(self, limit=12):
        return []


class FakeStore:
    def folders(self):
        return [
            {
                "path": "content://com.example/tree/primary%3AAnime",
                "name": "Anime",
                "kind": "saf",
                "authorization": "granted",
                "status": "granted",
                "saf_identity": "saf:com.example:primary:Anime",
                "saf_volume_id": "primary",
                "saf_document_id": "primary:Anime",
            },
            {
                "path": "broad-storage",
                "name": "Armazenamento amplo",
                "kind": "broad-storage",
                "authorization": "granted",
                "status": "available",
            },
        ]


class Prompt17ComposeStorageBridgeTest(unittest.TestCase):
    def test_storage_projection_uses_canonical_capabilities_and_configured_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            bridge = ComposeLibraryBridge(
                directory,
                FakeLibrary(),
                FakeStore(),
                storage_state_provider=lambda: {
                    "capabilities": StorageCapabilities(
                        media_read_state="full",
                        broad_storage_state="available",
                        saf_roots=("content://com.example/tree/primary%3AAnime",),
                        scanner_capabilities=frozenset({"saf", "mediastore"}),
                        reconciliation_capabilities=frozenset({"saf", "mediastore"}),
                        lifecycle_state="revalidated",
                        api=36,
                    ),
                    "safSelectionPending": True,
                },
            )
            bridge.request_publish("prompt17")
            asyncio.run(bridge.wait_for_idle())

            payload = json.loads(
                (Path(directory) / "reianix-compose" / "library.json").read_text(encoding="utf-8")
            )

            storage = payload["storage"]
            self.assertEqual("full", storage["capabilities"]["mediaReadState"])
            self.assertEqual("available", storage["capabilities"]["broadStorageState"])
            self.assertTrue(storage["safSelectionPending"])
            self.assertEqual(
                ["saf:com.example:primary:Anime"],
                storage["capabilities"]["safRootIdentities"],
            )
            self.assertEqual(2, len(storage["configuredSources"]))
            self.assertEqual("Anime", storage["configuredSources"][0]["name"])
            self.assertEqual("broad-storage", storage["configuredSources"][1]["kind"])


if __name__ == "__main__":
    unittest.main()
