import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_ACTIVITY = (
    ROOT
    / "android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt"
)
HOST = (
    ROOT
    / "android/app/src/main/kotlin/com/reiflix/reiflix_local/ReiAnixComposeLibraryHost.kt"
)
NAVIGATION = ROOT / "core/navigation.py"
HOME = ROOT / "views/home_view.py"
MAIN = ROOT / "main.py"


class Prompt91ComposeHostTests(unittest.TestCase):
    def test_main_activity_attaches_reversible_compose_library_host(self):
        source = MAIN_ACTIVITY.read_text(encoding="utf-8")
        host = HOST.read_text(encoding="utf-8")
        self.assertIn("ReiAnixComposeLibraryHost", source)
        self.assertIn("composeLibraryHost.show()", source)
        self.assertIn("composeLibraryHost.hide()", source)
        self.assertIn("ComposeView", host)
        self.assertIn("ReiAnixComposeRoot", host)
        self.assertIn("ReiAnixLibraryRoute", host)

    def test_library_is_a_single_existing_navigation_route(self):
        navigation = NAVIGATION.read_text(encoding="utf-8")
        main = MAIN.read_text(encoding="utf-8")
        self.assertIn('"library"', navigation)
        self.assertIn('navigation.push("library")', main)
        self.assertIn('route == "library"', main)
        self.assertNotIn("class ComposeNavigationController", main)
        self.assertNotIn("class LibraryNavigation", main)

    def test_home_exposes_the_real_library_entry_point(self):
        home = HOME.read_text(encoding="utf-8")
        main = MAIN.read_text(encoding="utf-8")
        self.assertIn("on_open_library", home)
        self.assertIn('tooltip="Biblioteca"', home)
        self.assertIn("on_open_library=navigate_library", main)

    def test_python_keeps_details_and_back_in_the_existing_navigation_authority(self):
        navigation = NAVIGATION.read_text(encoding="utf-8")
        main = MAIN.read_text(encoding="utf-8")
        self.assertIn("library", navigation)
        self.assertIn('if navigation.current == "library":', main)
        self.assertIn('navigation.back()', main)
        self.assertIn('navigate_details(anime', main)

    def test_library_route_uses_canonical_compose_path_without_list_positions(self):
        host = HOST.read_text(encoding="utf-8")
        library = (
            ROOT
            / "android/app/src/main/kotlin/com/reiflix/reiflix_local/ui/library/ReiAnixLibrary.kt"
        ).read_text(encoding="utf-8")
        self.assertIn("ReiAnixLibraryRoute(", host)
        self.assertIn("anime.stableKey", library)
        self.assertIn('"anime:" + id', library)

    def test_main_activity_does_not_replace_flutter_host(self):
        source = MAIN_ACTIVITY.read_text(encoding="utf-8")
        self.assertIn("class MainActivity : FlutterFragmentActivity()", source)
        self.assertNotIn("class MainActivity : ComponentActivity()", source)


if __name__ == "__main__":
    unittest.main()
