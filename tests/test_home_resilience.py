import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HomeResilienceContractTests(unittest.TestCase):
    def test_flet_image_uses_box_fit_compatibility_api(self):
        ui_source = (ROOT / 'core' / 'ui.py').read_text(encoding='utf-8')
        home_source = (ROOT / 'views' / 'home_view.py').read_text(encoding='utf-8')
        self.assertNotIn('ImageFit', ui_source + home_source)
        self.assertIn('ft.BoxFit.COVER', ui_source + home_source)

    def test_catalog_load_is_authoritative_and_secondary_projections_are_isolated(self):
        source = (ROOT / 'views' / 'home_view.py').read_text(encoding='utf-8')
        self.assertIn('loaded_catalog = await asyncio.to_thread(library.catalog)', source)
        self.assertNotIn('def load_data():', source)
        self.assertIn('library.media_center_home, limit=12, catalog=list(catalog)', source)
        self.assertIn('library.search_options, list(catalog)', source)
        self.assertIn('filtered = list(catalog)', source)
        self.assertNotIn('catalog.clear(); continuing.clear(); home_data.clear()', source)

    def test_home_hydration_never_blocks_first_catalog_render(self):
        source = (ROOT / 'views' / 'home_view.py').read_text(encoding='utf-8')
        self.assertIn('await render_library()', source)
        self.assertIn('page.run_task(hydrate_metadata_and_artwork)', source)
        self.assertIn('asyncio.to_thread(library.hydrate_catalog_metadata, catalog)', source)
        self.assertIn('target["meta"] = dict(metadata)', source)

    def test_home_diagnostic_log_keeps_failure_context_without_exposing_traceback(self):
        source = (ROOT / 'views' / 'home_view.py').read_text(encoding='utf-8')
        self.assertIn("logger.exception(\n                    \"Home local catalog load failed\"", source)
        self.assertIn("\"screen\":\"home\"", source)
        self.assertNotIn('traceback' , source.lower())


if __name__ == '__main__':
    unittest.main()