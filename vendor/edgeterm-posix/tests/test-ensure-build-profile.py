import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "ensure_build_profile", ROOT / "scripts/ensure-build-profile.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class EnsureBuildProfileTests(unittest.TestCase):
    def test_appends_flags_to_generated_makefile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Makefile"
            path.write_text("LDFLAGS = -static\n", encoding="utf-8")
            self.assertTrue(MODULE.update_makefile(path, "-lprofile"))
            self.assertEqual(path.read_text(encoding="utf-8"), "LDFLAGS = -static -lprofile\n")

    def test_does_not_duplicate_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Makefile"
            path.write_text(
                "LDFLAGS = -static /profile/libedgeterm-posix.a\n", encoding="utf-8"
            )
            self.assertFalse(MODULE.update_makefile(path, "-lprofile"))

    def test_makes_archive_flags_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Makefile"
            path.write_text("ARFLAGS = -curvU\n", encoding="utf-8")
            self.assertTrue(MODULE.update_makefile(path, "-lprofile"))
            self.assertEqual(path.read_text(encoding="utf-8"), "ARFLAGS = -curvD\n")

    def test_preserves_existing_deterministic_archive_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Makefile"
            path.write_text("ARFLAGS = crD\n", encoding="utf-8")
            self.assertFalse(MODULE.update_makefile(path, "-lprofile"))
            self.assertEqual(path.read_text(encoding="utf-8"), "ARFLAGS = crD\n")


if __name__ == "__main__":
    unittest.main()
