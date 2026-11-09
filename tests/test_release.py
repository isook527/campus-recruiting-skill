import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from test_check_jobs import ROOT

from release import build_release


class ReleaseTest(unittest.TestCase):
    def fixture(self, root, changelog_version="1.3.0"):
        (root / "SKILL.md").write_text(
            '---\nname: example\nmetadata:\n  version: "1.3.0"\n---\n',
            encoding="utf-8",
        )
        (root / "CHANGELOG.md").write_text(f"# History\n\n## {changelog_version}\n",
                                          encoding="utf-8")

    def test_zip_excludes_private_files_and_matches_checksum(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            paths = [
                ".github/workflows/test.yml", "docs/example.md", "examples/data.local.json",
                "examples/.env", "examples/records.db", "examples/records.sqlite3",
                "examples/records.sqlite3-wal", "examples/local/note.txt",
                "scripts/__pycache__/release.pyc", ".git/config", "dist/old.zip",
            ]
            for name in paths:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture", encoding="utf-8")

            archive, sums = build_release(root, tag="v1.3.0")
            self.assertEqual(archive.name, "campus-recruiting-skill-v1.3.0.zip")
            with ZipFile(archive) as package:
                prefix = "campus-recruiting-skill/"
                self.assertEqual(set(package.namelist()), {
                    prefix + name for name in
                    ("CHANGELOG.md", "SKILL.md", ".github/workflows/test.yml", "docs/example.md")
                })
                self.assertIsNone(package.testzip())
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(sums.read_text(encoding="ascii"), f"{digest}  {archive.name}\n")

    def test_cli_rejects_changelog_mismatch_and_wrong_tag_before_building(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "scripts").mkdir()
            script = root / "scripts/release.py"
            shutil.copyfile(ROOT / "scripts/release.py", script)
            self.fixture(root, changelog_version="1.2.0")
            wrong_changelog = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
            self.assertEqual(wrong_changelog.returncode, 1)
            self.assertIn("CHANGELOG.md", wrong_changelog.stderr)
            self.assertFalse((root / "dist").exists())

            self.fixture(root)
            wrong_tag = subprocess.run([sys.executable, str(script), "--tag", "v1.2.0"],
                                       capture_output=True, text=True)
            self.assertEqual(wrong_tag.returncode, 1)
            self.assertIn("v1.3.0", wrong_tag.stderr)
            self.assertFalse((root / "dist").exists())


if __name__ == "__main__":
    unittest.main()
