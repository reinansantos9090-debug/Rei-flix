import unittest

from core.diagnostics import DiagnosticTimeline


class DiagnosticTimelineTests(unittest.TestCase):
    def test_record_accepts_legacy_home_refresh_fields_without_crashing(self):
        timeline = DiagnosticTimeline()
        event = timeline.record(
            "HOME_REFRESH_PHASE_CHANGED",
            refreshId="refresh-1",
            requestId="scan-1",
            previous="REQUESTED",
            state="RUNNING",
            reason="scan_started",
        )

        self.assertEqual("HOME_REFRESH_PHASE_CHANGED", event.name)
        self.assertEqual("refresh-1", event.extra["refreshId"])
        self.assertEqual("scan-1", event.extra["requestId"])
        self.assertEqual("REQUESTED", event.extra["previous"])
        self.assertEqual("RUNNING", event.extra["state"])
        self.assertEqual("scan_started", event.extra["reason"])

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


if __name__ == "__main__":
    unittest.main()
