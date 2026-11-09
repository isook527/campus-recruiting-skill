#!/usr/bin/env python3
"""Create blinded A/B pairs and a separate private answer key."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import secrets
import shutil
from pathlib import Path


EXPECTED = [f"q{case:02d}-r{run:02d}.md" for case in range(1, 4) for run in range(1, 4)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--seed-file", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    args = parse_args()
    for arm in (args.left, args.right):
        missing = [name for name in EXPECTED if not (arm / name).is_file()]
        if missing:
            raise SystemExit(f"{arm}: missing {', '.join(missing)}")

    if args.out.exists() and any(args.out.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty directory: {args.out}")
    if args.key.exists() or args.seed_file.exists():
        raise SystemExit("refusing to overwrite an existing key or seed file")

    seed = secrets.token_hex(32)
    rng = random.Random(seed)
    shuffled = EXPECTED[:]
    rng.shuffle(shuffled)

    args.out.mkdir(parents=True, exist_ok=True)
    args.key.parent.mkdir(parents=True, exist_ok=True)
    args.seed_file.parent.mkdir(parents=True, exist_ok=True)

    public_pairs = []
    private_pairs = []
    for index, filename in enumerate(shuffled, start=1):
        pair_id = f"pair-{index:03d}"
        pair_dir = args.out / pair_id
        pair_dir.mkdir()
        left_is_a = bool(rng.getrandbits(1))
        source_a = args.left / filename if left_is_a else args.right / filename
        source_b = args.right / filename if left_is_a else args.left / filename
        shutil.copyfile(source_a, pair_dir / "A.md")
        shutil.copyfile(source_b, pair_dir / "B.md")
        case_id = filename[1:3]
        public_pairs.append({"pair_id": pair_id, "case_id": f"Q{case_id}"})
        private_pairs.append(
            {
                "pair_id": pair_id,
                "source_filename": filename,
                "A": "left" if left_is_a else "right",
                "B": "right" if left_is_a else "left",
                "A_sha256": sha256(source_a),
                "B_sha256": sha256(source_b),
            }
        )

    (args.out / "manifest.json").write_text(
        json.dumps({"pairs": public_pairs}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.key.write_text(
        json.dumps(
            {
                "left_dir": str(args.left.resolve()),
                "right_dir": str(args.right.resolve()),
                "pairs": private_pairs,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    args.seed_file.write_text(seed + "\n", encoding="utf-8")
    args.key.chmod(0o600)
    args.seed_file.chmod(0o600)
    print(f"created {len(public_pairs)} blind pairs in {args.out}")


if __name__ == "__main__":
    main()

