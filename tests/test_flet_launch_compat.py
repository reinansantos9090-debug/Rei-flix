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
        self.assertNotIn("mode=", page.urls[0])


if __name__ == "__main__":
    unittest.main()
