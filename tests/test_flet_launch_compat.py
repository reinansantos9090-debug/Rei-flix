import asyncio
import inspect
import unittest


class FletLaunchCompatibilityTests(unittest.TestCase):
    def test_page_launch_url_accepts_only_url_argument(self):
        async def page_launch_url(value):
            return value

        sig = inspect.signature(page_launch_url)
        self.assertEqual(["value"], list(sig.parameters.keys()))
        with self.assertRaises(TypeError):
            page_launch_url("https://example.com", mode="external")

    def test_android_bridge_launch_uses_flet_compatible_signature(self):
        class Page:
            def __init__(self):
                self.calls = []

            async def launch_url(self, value):
                self.calls.append(value)

        class Bridge:
            def __init__(self, page):
                self.page = page
                self.available = True

            async def launch(self, action, **params):
                import uuid
                from urllib.parse import urlencode
                request_id = uuid.uuid4().hex
                query = urlencode({"action": action, "request_id": request_id, **params})
                await self.page.launch_url(f"reiflix://native?{query}")

        page = Page()
        bridge = Bridge(page)
        asyncio.run(bridge.launch("select_tree", tree_uri="content://example"))
        self.assertTrue(page.calls)
        self.assertNotIn("mode=", page.calls[0])


if __name__ == "__main__":
    unittest.main()
