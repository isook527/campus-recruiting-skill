# Resume quality A/B evaluation

This suite complements, and does not replace, the compliance cases in `evals/cases.json`.
It compares the quality of targeted Chinese campus-recruiting resumes while holding the
JD, candidate facts, prompt, and run count constant across both arms.

## Fixed design

- Three synthetic cases: `Q01` comprehensive functions, `Q02` content operations,
  and `Q03` HR/project support.
- Three independent attempts per case and per arm.
- Canonical input is the exact `prompt` string in `cases.json`. Do not paraphrase it.
- Output filenames are `q01-r01.md` through `q03-r03.md`.
- Raw arm directories are outside the repository, for example:
  - `work/v130-eval/baseline/`
  - `work/v130-eval/candidate/`
- An output must contain only the answer to the prompt. Do not add model, version,
  arm, commit, run, or evaluator labels inside the file.

## Generate each arm

For every case, start three fresh attempts with no prior attempt in context. Give each
attempt the same canonical prompt and only the Skill/reference files belonging to that
arm. Do not ask one attempt to imitate or revise another. Preserve raw output exactly;
normalization is limited to ensuring UTF-8 text and one trailing newline.

If an automated runner is unavailable or would incur unapproved cost, three separately
authored attempts are acceptable. Record the real method in an arm-local `RUN-NOTES.md`
outside the nine scored files. Never describe manually authored attempts as independent
model calls.

The bundled runner uses three fresh ephemeral Codex processes in a neutral temporary
directory, one grouped three-case round per process, and applies the same low reasoning
effort to both arms. Existing host rules remain loaded; the evaluation prompt still
prohibits tools and the sandbox is read-only. The runner pins `gpt-6.1-sol` unless an
explicit identical `--model` is supplied to both arms:

```bash
python3 evals/quality/run_arm.py \
  --repo . --ref c6e1de9 \
  --cases evals/quality/cases.json \
  --schema evals/quality/round-output.schema.json \
  --out ../v130-eval/baseline

python3 evals/quality/run_arm.py \
  --repo . --ref WORKTREE \
  --cases evals/quality/cases.json \
  --schema evals/quality/round-output.schema.json \
  --out ../v130-eval/candidate
```

Run each command from the repository root. The baseline ref is the frozen v1.2.0 source;
run the candidate command only after its rules are ready. `RUN-NOTES.json` is audit metadata
and is excluded from scoring.

## Blind and score

After both arms contain nine files, create a blind package with:

```bash
python3 evals/quality/blind_pairs.py \
  --left ../v130-eval/baseline \
  --right ../v130-eval/candidate \
  --out ../v130-eval/blinded \
  --key ../v130-eval/private/answer-key.json \
  --seed-file ../v130-eval/private/seed.txt
```

Paths above are examples; use explicit paths appropriate to the checkout. Give graders
only `blinded/`, `rubric.md`, and the case prompts. Keep the seed and answer key private
until all grades and written rationales are frozen.

## Audit before grading

```bash
python3 evals/quality/audit_outputs.py \
  --cases evals/quality/cases.json \
  --arm ../v130-eval/baseline

python3 evals/quality/audit_outputs.py \
  --cases evals/quality/cases.json \
  --arm ../v130-eval/candidate
```

The audit checks filenames, run counts, empty files, accidental arm labels, and exact
duplicate attempts. It does not score quality or verify facts; graders must use
`rubric.md` and the structured facts in `cases.json`.

For a complete release check, retain and run the existing compliance cases and test
suite separately. A quality win never overrides a compliance regression.

