# Blind resume quality rubric

Score each anonymous answer independently before comparing the pair. Use only the JD,
facts, forbidden inferences, and requested output contract for that case. Do not infer
which arm produced an answer.

## 1. JD relevance (0–4)

- **4**: The first two experiences and most bullets directly cover the JD's highest-value
  actions; ordering makes the match obvious without keyword stuffing.
- **3**: Mostly relevant, with one weaker or missed JD connection.
- **2**: Mixed relevance; several bullets are generic or important JD work is buried.
- **1**: Minimal targeting; the same resume could be sent to many unrelated roles.
- **0**: Contradicts the JD or omits the available evidence for its core work.

## 2. Evidence fidelity (0–4)

- **4**: Every action, number, role, boundary, and result is supported; team and personal
  work are separated; cautious wording preserves what can actually be checked.
- **3**: Faithful overall, with one small ambiguity that does not materially inflate scope.
- **2**: One material overstatement or several unsupported implications, but core facts remain.
- **1**: Multiple material inflations, invented causality, or blurred ownership.
- **0**: Fabricated experience/metric, false role, or a forbidden inference central to the resume.

Any score below 4 must cite the exact phrase and source fact or boundary it conflicts with.

## 3. First-screen scan (0–4)

- **4**: The header and the first line of each section reveal the target role, education,
  dates and strongest evidence. In a normal read, tools are easy to find; bullets are concise, parallel, and visually prioritized.
- **3**: Clear and skimmable with one density, hierarchy, or repetition issue.
- **2**: Understandable but important facts require rereading or layout is uneven.
- **1**: Dense, repetitive, poorly ordered, or dominated by explanation instead of resume copy.
- **0**: Not usable as a resume or fails the requested structure.

## 4. Selective phrasing (0–4)

- **4**: Uses precise verbs and concrete objects, keeps only discriminating evidence, and
  avoids generic self-praise, forced competency labels, caveat clutter, and empty adjectives.
- **3**: Generally selective, with one generic phrase or low-value detail.
- **2**: Several vague claims, repetitive bullets, excessive caveats, or weak verbs.
- **1**: Mostly boilerplate or inflated wording; factual material is hard to see.
- **0**: Phrasing materially misleads or is unusable.

## Pair decision

After scoring both answers, record:

- preferred answer: `A`, `B`, or `tie`;
- confidence: `low`, `medium`, or `high`;
- one sentence naming the largest quality difference;
- any compliance flag: fabricated fact, forbidden inference, missing requested section,
  non-resume commentary, or identity leakage.

Do not use answer length alone as a preference signal. Do not reward a polished phrase that
weakens evidence fidelity. Keep all four dimension scores even if a compliance flag appears.
