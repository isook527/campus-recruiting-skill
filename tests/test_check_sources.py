import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_check_jobs import ROOT


NAVIGATION = "| [导航](https://example.org/) | 检索 | 仅导航，不追踪日期 |\n"


class SourceCheckTest(unittest.TestCase):
    def run_check(self, root, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/check_sources.py"), "references/official-sources.md",
             "--as-of", "2026-11-09", *args],
            cwd=root, capture_output=True, text=True,
        )

    def test_nested_links_and_ninety_day_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            refs = root / "references"
            (refs / "industry").mkdir(parents=True)
            (refs / "official-sources.md").write_text(NAVIGATION, encoding="utf-8")
            (refs / "industry/example.md").write_text(
                "# 示例\n"
                "- [过期](https://example.org/a) 核验时间 2026-08-10。\n"
                "- [边界](https://example.org/b) 核验时间：2026-08-11。\n"
                "- [早期格式](https://example.org/c) 核验于 2026-08-10。\n"
                "无链接的日期。核验时间 2026-01-01。\n",
                encoding="utf-8",
            )
            standard = self.run_check(root)
            self.assertEqual(standard.returncode, 0, standard.stderr)
            self.assertIn("references/industry/example.md:2\t需重新核对", standard.stdout)
            self.assertIn("references/industry/example.md:4\t需重新核对", standard.stdout)
            self.assertNotIn("example.md:3", standard.stdout)
            self.assertNotIn("example.md:5", standard.stdout)
            self.assertNotIn("official-sources.md:", standard.stdout)

            strict = self.run_check(root, "--strict", "--max-age-days", "89")
            self.assertEqual(strict.returncode, 1, strict.stderr)
            self.assertIn("references/industry/example.md:3\t需重新核对", strict.stdout)

            relaxed = self.run_check(root, "--strict", "--max-age-days", "91")
            self.assertEqual(relaxed.returncode, 0, relaxed.stderr)
            self.assertEqual(relaxed.stdout, "")

    def test_invalid_reference_date_has_location_and_error_exit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            refs = root / "references"
            refs.mkdir()
            (refs / "official-sources.md").write_text(NAVIGATION, encoding="utf-8")
            (refs / "example.md").write_text(
                "[链接](https://example.org/) 核验时间：2026-02-30。\n", encoding="utf-8"
            )
            result = self.run_check(root, "--strict")
            self.assertEqual(result.returncode, 2)
            self.assertIn("example.md:1:", result.stderr)


if __name__ == "__main__":
    unittest.main()
