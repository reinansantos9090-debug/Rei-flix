import unittest
from pathlib import Path

from core.navigation import NavigationController, SafSelectionState


class NavigationControllerTests(unittest.TestCase):
    def setUp(self):
        self.now = [100.0]
        self.navigation = NavigationController(clock=lambda: self.now[0])

    def test_home_is_root_and_first_back_requests_exit_confirmation(self):
        self.assertEqual(self.navigation.current, "home")
        self.assertEqual(self.navigation.back(), "prompt_exit")
        self.assertEqual(self.navigation.current, "home")

    def test_second_home_back_inside_window_exits(self):
        self.navigation.back()
        self.now[0] += 1.9
        self.assertEqual(self.navigation.back(), "exit")

    def test_home_back_after_window_requests_exit_confirmation(self):
        self.navigation.back()
        self.now[0] += 2.1
        self.assertEqual(self.navigation.back(), "prompt_exit")

    def test_details_back_returns_to_real_origin(self):
        self.navigation.push("details")
        self.assertEqual(self.navigation.back(), "previous")
        self.assertEqual(self.navigation.current, "home")

    def test_organize_details_back_returns_to_organize(self):
        self.navigation.push("organize")
        self.navigation.push("details")
        self.assertEqual(self.navigation.back(), "previous")
        self.assertEqual(self.navigation.current, "organize")

    def test_settings_back_returns_to_origin(self):
        self.navigation.push("organize")
        self.navigation.push("settings")
        self.assertEqual(self.navigation.back(), "previous")
        self.assertEqual(self.navigation.current, "organize")

    def test_native_player_is_not_a_second_navigation_route(self):
        self.navigation.push("details")
        self.assertEqual(self.navigation.current, "details")
        self.assertEqual(self.navigation.back(), "previous")
        self.assertEqual(self.navigation.current, "home")

    def test_main_has_single_logical_back_router_with_duplicate_suppression(self):
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        self.assertIn('def navigate_back(source="unknown")', source)
        self.assertIn("BACK_DEBOUNCE_SECONDS = 0.30", source)
        self.assertIn("duplicate BACK suppressed", source)
        self.assertIn('"[NAV] DIALOG_BACK', source)
        self.assertIn('"[NAV] NAVIGATE_BACK', source)

    def test_visual_back_callbacks_identify_their_origin_screen(self):
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        self.assertIn('lambda: navigate_back("visual:organize")', source)
        self.assertIn('lambda: navigate_back("visual:details")', source)
        self.assertIn('lambda: navigate_back("visual:settings")', source)


    def test_main_uses_one_persistent_view_host(self):
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        self.assertIn("view_host = ft.Container", source)
        self.assertIn("screen_cache = {}", source)
        self.assertNotIn("page.clean()", source)

    def test_multiple_back_events_never_underflow_history(self):
        self.navigation.push("organize")
        self.assertEqual(self.navigation.back(), "previous")
        self.assertEqual(self.navigation.back(), "prompt_exit")
        self.assertEqual(self.navigation.stack, ("home",))


class SafSelectionStateTests(unittest.TestCase):
    def test_button_is_pending_only_while_android_selection_is_unresolved(self):
        state = SafSelectionState()
        self.assertTrue(state.begin())
        self.assertTrue(state.pending)
        self.assertFalse(state.begin())
        state.finish()  # cancellation
        self.assertFalse(state.pending)

    def test_success_error_and_invalid_result_all_release_selection(self):
        state = SafSelectionState()
        for _result in ("success", "error", None):
            self.assertTrue(state.begin())
            state.finish()
            self.assertFalse(state.pending)
