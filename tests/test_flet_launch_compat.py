import asyncio
import inspect
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

import flet as ft

from core.android_bridge import AndroidBridge


class FletLaunchCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    def test_real_flet_page_launch_url_has_no_unsupported_mode_parameter(self):
        self.assertEqual("0.86.5", getattr(ft, "__version__", None))
        launch_url = inspect.signature(ft.Page.launch_url)
        self.assertNotIn("mode", launch_url.parameters)

    async def test_android_bridge_uses_flet_0865_non_browser_url_launcher_and_confirms_receipt(self):
        class StrictLauncher:
            def __init__(self, page):
                self.page = page
                self.calls = []

            async def launch_url(self, value, *, mode):
                self.calls.append((value, mode))
                params = parse_qs(urlsplit(value).query)
                request_id = params["request_id"][0]
                self.page.bridge.observe_native_event(
                    {
                        "type": "diagnostic",
                        "requestId": request_id,
                        "payload": {
                            "event": "COMMAND_RECEIVED",
                            "requestId": request_id,
                            "action": params["action"][0],
                            "timestamp": 123456789,
                        },
                    }
                )

        class StrictPage:
            platform = "android"

            def __init__(self):
                self.launcher = StrictLauncher(self)
                self.bridge = None

            @property
            def url_launcher(self):
                return self.launcher

            async def launch_url(self, value):
                raise AssertionError("AndroidBridge must not use Page.launch_url for native commands")

        with tempfile.TemporaryDirectory() as data_dir:
            page = StrictPage()
            bridge = AndroidBridge(data_dir, page)
            page.bridge = bridge
            request_id = await bridge.select_tree()

        self.assertEqual(1, len(page.launcher.calls))
        value, mode = page.launcher.calls[0]
        self.assertEqual(ft.LaunchMode.EXTERNAL_NON_BROWSER_APPLICATION, mode)
        self.assertIn("reiflix://native?action=select_tree&request_id=", value)
        self.assertIn("protocol_version=2", value)
        self.assertIn("created_at=", value)
        self.assertEqual(request_id, parse_qs(urlsplit(value).query)["request_id"][0])

    async def test_android_bridge_does_not_treat_launcher_return_as_delivery(self):
        class SilentLauncher:
            async def launch_url(self, value, *, mode):
                return None

        class SilentPage:
            platform = "android"
            url_launcher = SilentLauncher()

        with tempfile.TemporaryDirectory() as data_dir:
            bridge = AndroidBridge(data_dir, SilentPage())
            bridge._command_delivery_timeout_s = 0.01
            with self.assertRaisesRegex(RuntimeError, "não chegou à MainActivity"):
                await bridge.select_tree()

    async def test_android_bridge_generates_distinct_request_ids_for_retries(self):
        class StrictLauncher:
            async def launch_url(self, value, *, mode):
                params = parse_qs(urlsplit(value).query)
                request_id = params["request_id"][0]
                self.page.bridge.observe_native_event(
                    {
                        "type": "diagnostic",
                        "requestId": request_id,
                        "payload": {
                            "event": "COMMAND_RECEIVED",
                            "requestId": request_id,
                            "action": params["action"][0],
                            "timestamp": 123456789,
                        },
                    }
                )

            def __init__(self):
                self.page = None

        class StrictPage:
            platform = "android"

            def __init__(self):
                self.launcher = StrictLauncher()
                self.launcher.page = self
                self.bridge = None

            @property
            def url_launcher(self):
                return self.launcher

        with tempfile.TemporaryDirectory() as data_dir:
            page = StrictPage()
            bridge = AndroidBridge(data_dir, page)
            page.bridge = bridge
            await bridge.select_tree()
            await bridge.select_tree()

        # The launcher itself saw two independent request identities.
        self.assertEqual(2, len(page.launcher.page.bridge._command_delivery_waiters))
        # Both waiters are cleaned up after confirmation.
        self.assertEqual({}, page.launcher.page.bridge._command_delivery_waiters)

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
