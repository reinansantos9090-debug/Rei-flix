import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestRepositoryHygiene(unittest.TestCase):
    def test_no_file_or_directory_name_contains_legacy_word(self):
        offenders = []
        for path in ROOT.rglob("*"):
            if ".git" in path.parts:
                continue
            if "prompt" in path.name.casefold():
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual([], offenders)

    def test_renamed_validation_files_exist(self):
        expected = [
            ROOT / "tests/test_discovery_engine.py",
            ROOT / "tests/test_ui_states.py",
            ROOT / "tests/test_e2e_diagnostics.py",
            ROOT / "tests/test_scalability.py",
            ROOT / "android/app/src/androidTest/kotlin/com/reiflix/reiflix_local/DeviceFlowInstrumentedTest.kt",
        ]
        self.assertTrue(all(path.is_file() for path in expected))


if __name__ == "__main__":
    unittest.main()
