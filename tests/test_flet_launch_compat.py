import asyncio
import inspect
import tempfile
import unittest

import flet as ft

from core.android_bridge import AndroidBridge


class FletLaunchCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    def test_real_flet_page_launch_url_has_no_unsupported_mode_parameter(self):
        self.assertEqual("0.86.5", getattr(ft, "__version__", None))
        launch_url = inspect.signature(ft.Page.launch_url)
        self.assertNotIn("mode", launch_url.parameters)

    async def test_android_bridge_uses_real_compatible_page_launch_contract(self):
        class StrictPage:
            platform = "android"

            def __init__(self):
                self.urls = []

            async def launch_url(self, value):
                self.urls.append(value)

        with tempfile.TemporaryDirectory() as data_dir:
            page = StrictPage()
            bridge = AndroidBridge(data_dir, page)
            await bridge.select_tree()

        self.assertEqual(1, len(page.urls))
        self.assertIn("reiflix://native?action=select_tree&request_id=", page.urls[0])
        self.assertIn("protocol_version=2", page.urls[0])
        self.assertIn("created_at=", page.urls[0])
        self.assertNotIn("mode=", page.urls[0])

    async def test_android_bridge_generates_distinct_request_ids_for_retries(self):
        class StrictPage:
            platform = "android"

            def __init__(self):
                self.urls = []

            async def launch_url(self, value):
                self.urls.append(value)

        with tempfile.TemporaryDirectory() as data_dir:
            page = StrictPage()
            bridge = AndroidBridge(data_dir, page)
            await bridge.select_tree()
            await bridge.select_tree()

        self.assertEqual(2, len(page.urls))
        first = page.urls[0].split("request_id=", 1)[1].split("&", 1)[0]
        second = page.urls[1].split("request_id=", 1)[1].split("&", 1)[0]
        self.assertTrue(first)
        self.assertTrue(second)
        self.assertNotEqual(first, second)

    def test_android_bridge_normalizes_legacy_events_with_stable_ids(self):
        event = AndroidBridge._normalize_event(
            {"type": "native_error", "message": "failed"},
            "event-abc.consumed",
            0,
        )
        self.assertIsNotNone(event)
        self.assertTrue(event["eventId"].startswith("legacy:event-abc.consumed:0:"))
        self.assertEqual(24, len(event["eventId"].rsplit(":", 1)[-1]))
        self.assertIn("createdAt", event)


if __name__ == "__main__":
    unittest.main()
