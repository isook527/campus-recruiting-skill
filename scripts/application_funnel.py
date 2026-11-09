"""Diagnose a submission cohort using observed transitions in its event history."""

from collections import defaultdict
from datetime import date, timedelta


GATES = ("submitted", "assessment", "interview")
PROGRESSION = (*GATES, "offer", "accepted")
MIN_RESOLVED = 3
ACTIONS = {
    "submitted": "抽查三份已确认在简历关止步的投递，只改 JD 前三项任务与简历首屏的对应关系。",
    "assessment": "用已确认的测评题型做一套限时题，按耗时和错因复盘，优先修复失分最多的一类。",
    "interview": "选一次有真实反馈的面试，针对该环节用同一评分表复练一个真实故事。",
}


def diagnose(history, now, start):
    by_job = defaultdict(list)
    for event in history:
        by_job[event["job_id"]].append(event)

    cohort = []
    missing = 0
    for events in by_job.values():
        first = next((event for event in events if event["stage"] == "submitted"), None)
        if first is None:
            missing += any(event["stage"] != "tracking" for event in events)
        elif date.fromisoformat(first["at"][:10]) >= start:
            cohort.append(events)

    counts = {
        stage: dict(passed=0, rejected=0, pending=0, withdrawn=0, pending_seven_days=0)
        for stage in GATES
    }
    for events in cohort:
        current = events[-1]["stage"]
        reached = {event["stage"] for event in events}
        furthest = max((PROGRESSION.index(stage) for stage in reached if stage in PROGRESSION))
        for index, stage in enumerate(GATES):
            if stage not in reached:
                continue
            bucket = counts[stage]
            if furthest > index:
                bucket["passed"] += 1
            elif current in {"rejected", "withdrawn"}:
                bucket[current] += 1
            else:
                bucket["pending"] += 1
                entry = next(event for event in events if event["stage"] == stage)
                if date.fromisoformat(entry["at"][:10]) <= now.date() - timedelta(days=7):
                    bucket["pending_seven_days"] += 1

    comparable = []
    for stage, bucket in counts.items():
        resolved = bucket["passed"] + bucket["rejected"]
        rate = bucket["passed"] / resolved if resolved else None
        bucket.update(
            entered=resolved + bucket["pending"] + bucket["withdrawn"],
            resolved=resolved,
            conversion=rate,
        )
        if resolved >= MIN_RESOLVED and bucket["rejected"]:
            comparable.append(stage)

    weakest = min(comparable, key=lambda stage: counts[stage]["conversion"], default=None)
    if weakest is not None:
        action = ACTIONS[weakest]
    elif counts["submitted"]["pending_seven_days"]:
        action = "抽查最多三份满七天未有进展的投递，先从官方系统核对是否确实提交和当前进度。"
    elif not cohort:
        action = "核对下一批投递的提交回执，并记录真实提交时间和后续阶段。"
    else:
        action = "把本周已经收到的阶段反馈补到记录里，下周再看最弱的一关。"

    return {
        "as_of": now.isoformat(),
        "since": start.isoformat(),
        "cohort_size": len(cohort),
        "jobs_missing_submission_event": missing,
        "gates": counts,
        "min_resolved_for_diagnosis": MIN_RESOLVED,
        "weakest_observed_gate": weakest,
        "next_week_action": action,
    }
