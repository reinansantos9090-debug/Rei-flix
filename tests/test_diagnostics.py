import unittest

from core.diagnostics import DiagnosticTimeline


class DiagnosticTimelineTests(unittest.TestCase):
    def test_home_refresh_phase_uses_supported_record_fields(self):
        timeline = DiagnosticTimeline()
        event = timeline.record(
            "HOME_REFRESH_PHASE_CHANGED",
            request_id="scan-1",
            source="scan_started",
            result="RUNNING",
            refresh_id="refresh-1",
            previous_phase="REQUESTED",
            phase="RUNNING",
            transition_reason="scan_started",
        )

        self.assertEqual("HOME_REFRESH_PHASE_CHANGED", event.name)
        self.assertEqual("scan-1", event.request_id)
        self.assertEqual("scan_started", event.source)
        self.assertEqual("RUNNING", event.result)
        self.assertEqual("refresh-1", event.extra["refresh_id"])
        self.assertEqual("REQUESTED", event.extra["previous_phase"])
        self.assertEqual("RUNNING", event.extra["phase"])
        self.assertEqual("scan_started", event.extra["transition_reason"])

    def test_record_preserves_existing_fields_and_numeric_extra_data(self):
        timeline = DiagnosticTimeline()
        event = timeline.record(
            "HOME_REFRESH_SCAN_COMPLETED",
            request_id="scan-1",
            source="button",
            result="COMPLETED",
            refreshId="refresh-1",
            durationMs=123,
        )

        self.assertEqual("scan-1", event.request_id)
        self.assertEqual("button", event.source)
        self.assertEqual("COMPLETED", event.result)
        self.assertEqual({"refreshId": "refresh-1", "durationMs": 123}, event.extra)

    def test_extra_values_are_json_safe(self):
        timeline = DiagnosticTimeline()
        event = timeline.record(
            "EXTRA_DATA",
            nested={"items": [1, object()]},
        )

        self.assertEqual(1, event.extra["nested"]["items"][0])
        self.assertIsInstance(event.extra["nested"]["items"][1], str)


    def test_home_refresh_phase_callsite_does_not_use_legacy_keyword_aliases(self):
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        start = source.index("    def _set_home_refresh_phase(")
        end = source.index("    def _handle_page_disconnect", start)
        block = source[start:end]

        self.assertNotIn("refreshId=", block)
        self.assertNotIn("requestId=", block)
        self.assertNotIn("previous=", block)
        self.assertNotIn("state=", block)
        self.assertNotIn("reason=", block)
        self.assertIn("request_id=", block)
        self.assertIn("result=normalized", block)
        self.assertIn('"previous_phase"', block)
        self.assertIn('"phase"', block)


if __name__ == "__main__":
    unittest.main()
