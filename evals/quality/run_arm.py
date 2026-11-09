#!/usr/bin/env python3
"""Generate three fresh grouped rounds for one arm with the local Codex CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path


POLICY_PATHS = [
    "SKILL.md",
    "references/application-prioritization.md",
    "references/application-packet.md",
    "references/resume-and-evidence.md",
    "templates/resume.md",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--ref", required=True, help="Git ref, or WORKTREE for current files")
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--model", default="gpt-6.1-sol")
    parser.add_argument("--rounds", type=int, default=3)
    return parser.parse_args()


def policy_text(repo: Path, ref: str) -> str:
    sections = []
    for relative in POLICY_PATHS:
        if ref == "WORKTREE":
            text = (repo / relative).read_text(encoding="utf-8")
        else:
            result = subprocess.run(
                ["git", "-C", str(repo), "show", f"{ref}:{relative}"],
                check=True,
                capture_output=True,
                text=True,
            )
            text = result.stdout
        sections.append(f"\n===== {relative} =====\n{text}")
    return "".join(sections)


def build_prompt(policy: str, cases: dict) -> str:
    prompts = "\n\n".join(
        f"===== {case['id']} CANONICAL INPUT =====\n{case['prompt']}" for case in cases["cases"]
    )
    return f"""You are producing one blinded offline evaluation round for a Chinese campus-recruiting assistant.

Use ONLY the frozen policy bundle and the three canonical inputs below. Do not inspect local files, use tools, browse, ask questions, grade answers, mention policy/version/arm/run, or compare the cases. Treat every employer and person as synthetic. Answer each case independently as if it were the only request in a fresh conversation.

Return one JSON object with exactly three string fields: Q01, Q02, Q03. Each value must be only the requested resume answer, with no evaluation commentary outside the resume.

===== POLICY BUNDLE =====
{policy}

===== END POLICY BUNDLE =====

{prompts}
"""


def main() -> None:
    args = parse_args()
    if args.rounds != 3:
        raise SystemExit("this suite requires exactly 3 rounds per arm")
    if args.out.exists() and any(args.out.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty output directory: {args.out}")
    args.out.mkdir(parents=True, exist_ok=True)

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    policy = policy_text(args.repo.resolve(), args.ref)
    prompt = build_prompt(policy, cases)

    with tempfile.TemporaryDirectory(prefix="resume-quality-") as neutral_dir:
        for run in range(1, args.rounds + 1):
            raw_path = args.out / f"round-{run:02d}.json"
            command = [
                args.codex,
                "exec",
                "--ephemeral",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--model",
                args.model,
                "-c",
                'model_reasoning_effort="low"',
                "--cd",
                neutral_dir,
                "--output-schema",
                str(args.schema.resolve()),
                "-o",
                str(raw_path.resolve()),
                "-",
            ]
            subprocess.run(command, input=prompt, text=True, check=True)
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
            for case_num in range(1, 4):
                key = f"Q{case_num:02d}"
                output = payload[key].strip() + "\n"
                (args.out / f"q{case_num:02d}-r{run:02d}.md").write_text(
                    output, encoding="utf-8"
                )
            raw_path.unlink()

    notes = {
        "method": "local Codex CLI; three fresh ephemeral processes; each process generated all three cases",
        "policy_source": args.ref,
        "model": args.model,
        "reasoning_effort": "low",
        "ignore_rules": False,
        "cases_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
        "policy_bundle_sha256": hashlib.sha256(policy.encode("utf-8")).hexdigest(),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "rounds": args.rounds,
        "cases_per_round": 3,
    }
    (args.out / "RUN-NOTES.json").write_text(
        json.dumps(notes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"generated {args.rounds * 3} outputs in {args.out}")


if __name__ == "__main__":
    main()
