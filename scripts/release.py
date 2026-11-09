#!/usr/bin/env python3
"""Build the public Skill ZIP and its SHA-256 checksum."""

import argparse
import hashlib
import os
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
PROJECT = "campus-recruiting-skill"
PUBLIC_FILES = {".gitignore", "CHANGELOG.md", "CONTRIBUTING.md", "LICENSE",
                "README.md", "SECURITY.md", "SKILL.md"}
PUBLIC_DIRS = {".github", "docs", "evals", "examples", "references", "scripts", "templates", "tests"}
PRIVATE_DIRS = {".git", "dist", "__pycache__", "local"}
PRIVATE_SUFFIXES = (".local.json", ".db", ".sqlite", ".sqlite3", ".pyc")
SEMVER = re.compile(r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){2}"
                    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
                    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?")


def release_version(root):
    text = (root / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = re.match(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", text, re.DOTALL)
    metadata = re.search(r"^metadata:[ \t]*\n((?:^ +[^\n]*\n?)*)",
                         frontmatter[1], re.MULTILINE) if frontmatter else None
    lines = [line for line in metadata[1].splitlines()
             if line.strip() and not line.lstrip().startswith("#")] if metadata else []
    indentation = min((len(line) - len(line.lstrip()) for line in lines), default=0)
    versions = [match[1].strip() for line in lines
                if (match := re.fullmatch(r" " * indentation + r"version:\s*(.+)", line))]
    version = versions[0] if len(versions) == 1 else ""
    if len(version) >= 2 and version[0] in "'\"" and version[-1] == version[0]:
        version = version[1:-1]
    if not SEMVER.fullmatch(version):
        raise ValueError("SKILL.md 的 metadata.version 须为有效版本号")

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = re.search(r"^##[ \t]+(.+)$", changelog, re.MULTILINE)
    if not heading or heading[1].strip() != version:
        raise ValueError(f"CHANGELOG.md 的首个二级标题须与 metadata.version 一致（{version}）")
    return version


def release_files(root):
    for name in sorted(PUBLIC_FILES):
        path = root / name
        if path.is_file() and not path.is_symlink():
            yield path
    for directory in sorted(PUBLIC_DIRS):
        start = root / directory
        if start.is_symlink():
            continue
        for folder, directories, filenames in os.walk(start):
            base = Path(folder)
            directories[:] = sorted(
                name for name in directories
                if name not in PRIVATE_DIRS and not name.startswith(".")
                and not (base / name).is_symlink()
            )
            for name in sorted(filenames):
                path = base / name
                if (
                    not name.startswith(".")
                    and not name.endswith(PRIVATE_SUFFIXES)
                    and not re.search(r"\.(?:db|sqlite3?)-(?:wal|shm|journal)$", name)
                    and not path.is_symlink() and path.is_file()
                ):
                    yield path


def build_release(root, tag=None):
    version = release_version(root)
    if tag is not None and tag != f"v{version}":
        raise ValueError(f"标签 {tag!r} 与版本 v{version} 不一致")
    dist = root / "dist"
    if dist.is_symlink():
        raise ValueError("dist/ 须为仓库内目录")
    dist.mkdir(exist_ok=True)
    filename = f"{PROJECT}-v{version}.zip"
    with TemporaryDirectory(dir=dist) as temporary:
        zip_path = Path(temporary) / filename
        with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
            for path in release_files(root):
                archive.write(path, f"{PROJECT}/{path.relative_to(root).as_posix()}")
        digest = hashlib.sha256()
        with zip_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        checksum = Path(temporary) / "SHA256SUMS"
        checksum.write_text(f"{digest.hexdigest()}  {filename}\n", encoding="ascii")
        zip_path.replace(dist / filename)
        checksum.replace(dist / checksum.name)
    return dist / filename, dist / "SHA256SUMS"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Require an exact version tag before building")
    args = parser.parse_args()
    try:
        for path in build_release(ROOT, tag=args.tag):
            print(path.relative_to(ROOT))
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
