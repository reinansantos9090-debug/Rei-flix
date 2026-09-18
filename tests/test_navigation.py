import unittest

from core.navigation import NavigationController, SafSelectionState


class NavigationControllerTests(unittest.TestCase):
    def setUp(self):
        self.now = [100.0]
        self.navigation = NavigationController(clock=lambda: self.now[0])

    def test_home_is_root_and_first_back_only_prompts(self):
        self.assertEqual(self.navigation.current, "home")
        self.assertEqual(self.navigation.back(), "prompt_exit")
        self.assertEqual(self.navigation.current, "home")

    def test_second_home_back_inside_window_exits(self):
        self.navigation.back()
        self.now[0] += 1.9
        self.assertEqual(self.navigation.back(), "exit")

    def test_home_back_after_window_prompts_again(self):
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

    def test_player_is_a_regular_history_entry(self):
        self.navigation.push("details")
        self.navigation.push("player")
        self.assertEqual(self.navigation.back(), "previous")
        self.assertEqual(self.navigation.current, "details")

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
