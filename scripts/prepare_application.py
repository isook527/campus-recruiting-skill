#!/usr/bin/env python3
"""Rank reviewed positions or render an evidence-linked application packet."""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from check_jobs import CHINA, audit, parse_boundary, parse_datetime


DECISIONS = {"ready": "优先准备投递", "verify": "补核后再决定", "skip": "跳过"}
REASONS = {
    "verified_open": "具体岗位的核验记录仍有效",
    "campaign_open": "项目开放，需再核具体岗位",
    "not_started": "报名尚未开始",
    "closed": "已关闭或截止",
    "unverified": "官网或投递状态待核",
    "stale": "核验记录已过时",
    "deadline_time_unconfirmed": "截止日当天的时刻待核",
    "duplicate_requires_resolution": "存在未解决的重复记录",
}
KINDS = {"required": "硬性资格", "preferred": "优先条件", "duty": "岗位任务"}
STATES = {"met": "有依据", "gap": "有缺口", "unknown": "待确认"}
PROVENANCE = {"user_confirmed": "用户确认", "material": "材料支持"}
RELATIONS = {"direct": "直接证据", "transferable": "可迁移经验"}
SECTIONS = {"education": "教育背景", "experience": "相关经历", "skills": "技能与证书"}
CHECKS = {"done": "已核对", "todo": "待处理", "unknown": "待确认"}
VERSION = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}\Z")


def filled(value):
    return isinstance(value, str) and bool(value.strip())


def evidence_ids(ids, facts):
    if not isinstance(ids, list) or not all(filled(item) and item in facts for item in ids):
        raise ValueError("证据编号须指向已确认的事实")
    if len(set(ids)) != len(ids):
        raise ValueError("同一条记录的证据编号不能重复")
    return ids


def index_reviews(data):
    facts = data["facts"]
    if not isinstance(facts, dict):
        raise ValueError("facts 须为事实编号到已确认事实的字典")
    for key, fact in facts.items():
        if not filled(key) or not isinstance(fact, dict) or not filled(fact.get("text")):
            raise ValueError("每条事实须有编号和已确认内容")
        origin = fact.get("provenance")
        if origin not in PROVENANCE or (origin == "material" and not filled(fact.get("source_detail"))):
            raise ValueError("每条事实须标记来源，材料支持的事实须标记材料位置")
    job_ids = {row["id"] for row in data["jobs"]}
    reviews = {}
    for review in data["reviews"]:
        key = review["job_id"]
        if key in reviews or key not in job_ids:
            raise ValueError("岗位评估编号重复或无法找到原岗位")
        if type(review["requirements_complete"]) is not bool:
            raise ValueError("requirements_complete 须为布尔值")
        for item in review["criteria"]:
            if item["kind"] not in KINDS or item["state"] not in STATES:
                raise ValueError("无法识别资格类型或判断结果")
            if not all(filled(item[field]) for field in ("requirement", "source", "next_step")):
                raise ValueError("每条要求须有公告出处和核对动作")
            ids = evidence_ids(item["fact_ids"], facts)
            if item["state"] == "met" and not ids:
                raise ValueError("标记有依据的要求须关联事实编号")
            if item["kind"] == "required" and item["state"] == "gap" and not ids:
                raise ValueError("确认硬性不符须有候选人事实，未提供资料应标为待确认")
            relation = item["evidence_type"]
            if (ids and relation not in RELATIONS) or (not ids and relation is not None):
                raise ValueError("有关联事实时须区分直接证据与可迁移经验")
            if item["kind"] == "required" and item["state"] != "unknown" and relation != "direct":
                raise ValueError("判断硬性资格只能用直接证据")
        reviews[key] = review
    return reviews


def decision(status, review):
    required = [item for item in review.get("criteria", []) if item["kind"] == "required"]
    if status == "closed" or any(item["state"] == "gap" for item in required):
        return "skip"
    if (
        status != "verified_open" or not review.get("requirements_complete") or not required
        or any(item["state"] != "met" for item in required)
    ):
        return "verify"
    return "ready"


def rank(data, now):
    checked = audit(data["jobs"], now)
    statuses = {row["id"]: row["status"] for row in checked["eligible_by_record"]}
    statuses.update({row["id"]: row["reason"] for row in checked["excluded"]})
    reviews = index_reviews(data)
    ranked = []
    for job in data["jobs"]:
        review = reviews.get(job["id"], {})
        status = statuses[job["id"]]
        matched = [
            item for item in review.get("criteria", [])
            if item["kind"] == "duty" and item["state"] == "met"
        ]
        direct_duties = sum(
            item["evidence_type"] == "direct" for item in matched
        )
        ranked.append({
            "id": job["id"], "employer": job["employer"], "title": job["title"],
            "decision": decision(status, review), "verification": status,
            "deadline": job["deadline"], "matched_duties": len(matched),
            "direct_duties": direct_duties,
            "reasons": [
                item["requirement"] for item in review.get("criteria", [])
                if item["kind"] == "required" and item["state"] != "met"
            ],
        })
    last = datetime.max.replace(tzinfo=CHINA)
    return sorted(ranked, key=lambda row: (
        list(DECISIONS).index(row["decision"]), parse_boundary(row["deadline"])[0] or last,
        -row["direct_duties"], -row["matched_duties"], row["id"],
    ))


def cell(value):
    return " ".join(value.splitlines()).replace("|", r"\|")


def fact_source(fact):
    label = PROVENANCE[fact["provenance"]]
    return f"{label} · {fact['source_detail']}" if fact["provenance"] == "material" else label


def render_packet(data, ranked, job_id, replay=False):
    row = next((item for item in ranked if item["id"] == job_id), None)
    review = next((item for item in data["reviews"] if item["job_id"] == job_id), None)
    if row is None or review is None:
        raise ValueError("生成投递包需要同一岗位的核验记录和评估")
    job = next(item for item in data["jobs"] if item["id"] == job_id)
    facts = data["facts"]
    resume = review["resume"]
    questions = review["questions"]
    checklist = review["checklist"]
    version = review["resume_version"]
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise ValueError("简历版本须为稳定的短编号")
    if not resume or not checklist or len(questions) != 3:
        raise ValueError("投递包需要简历条目、核对清单和三道追问")
    if not all(filled(item["text"]) for item in questions) or len({item["text"].strip() for item in questions}) != 3:
        raise ValueError("三道追问须各有不同的问题")
    for item in resume:
        if item["section"] not in SECTIONS or not all(filled(item[k]) for k in ("text", "rationale")):
            raise ValueError("简历条目须有可编辑正文、栏目和取舍理由")
        if not evidence_ids(item["fact_ids"], facts):
            raise ValueError("简历条目不得脱离已确认的事实")
    resume_facts = {key for item in resume for key in item["fact_ids"]}
    for item in questions:
        ids = evidence_ids(item["fact_ids"], facts)
        if not ids or not set(ids) <= resume_facts:
            raise ValueError("面试追问须回指本版简历里的事实")
    for item in checklist:
        if item["state"] not in CHECKS or not filled(item["item"]):
            raise ValueError("核对项须有说明及有效状态")

    lines = [
        f"# {cell(job['employer'])} · {cell(job['title'])}投递准备包", "",
        f"**准备判断** {DECISIONS[row['decision']]}。{REASONS[row['verification']]}。",
        f"**截止** {job['deadline'] or '未公布'}　**记录时间** {job['checked_at']}",
        f"**简历版本** `{version}`",
    ]
    if replay or row["decision"] != "ready" or any(item["state"] != "done" for item in checklist):
        lines.append("**材料状态**　准备草稿，待核事项见下方清单。")
    if replay:
        lines.append("**历史回放**　当前开放状态仍需重新核验。")
    links = [
        f"[{label}](<{job[key]}>)" for label, key in
        (("公告", "announcement_url"), ("投递入口", "application_url")) if job[key]
    ]
    if links:
        lines.append(" · ".join(links))
    if not review["requirements_complete"]:
        lines.append("公告中的硬性条件还未核对完整。")
    if not any(item["kind"] == "required" for item in review["criteria"]):
        lines.append("尚未得到可核对的硬性条件。")
    lines.extend([
        "", "## 岗位要求和本人证据", "",
        "| 类型 | 要求 | 公告出处 | 判断 | 证据关系 | 事实及来源 | 下一步 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ])
    for item in review["criteria"]:
        cells = [
            KINDS[item["kind"]], item["requirement"], item["source"], STATES[item["state"]],
            RELATIONS.get(item["evidence_type"], "待确认"),
            " / ".join(f"{key}（{fact_source(facts[key])}）" for key in item["fact_ids"]) or "待补",
            item["next_step"],
        ]
        lines.append("| " + " | ".join(map(cell, cells)) + " |")
    lines.extend(["", "## 可编辑简历", "", "姓名与联系方式由本人填写。", ""])
    for key, label in SECTIONS.items():
        section = [item for item in resume if item["section"] == key]
        if section:
            lines.extend([f"### {label}", ""])
            lines.extend(f"- {cell(item['text'])}" for item in section)
            lines.append("")
    lines.extend(["## 改写依据", ""])
    for number, item in enumerate(resume, 1):
        used = " / ".join(
            f"{key} {facts[key]['text']}（{fact_source(facts[key])}）" for key in item["fact_ids"]
        )
        lines.append(f"{number}. **{cell(item['text'])}**　{cell(item['rationale'])}。事实为 {cell(used)}")
    lines.extend(["", "## 投递前检查", ""])
    for item in checklist:
        mark = "x" if item["state"] == "done" else " "
        lines.append(f"- [{mark}] {cell(item['item'])}（{CHECKS[item['state']]}）")
    lines.extend(["", "## 简历追问", ""])
    lines.extend(f"{i}. {cell(item['text'])}（{'、'.join(item['fact_ids'])}）"
                 for i, item in enumerate(questions, 1))
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path)
    parser.add_argument("--job", help="Render the Markdown packet for this job ID")
    parser.add_argument("--as-of", help="Replay earlier records at an ISO timestamp")
    args = parser.parse_args()
    try:
        now = parse_datetime(args.as_of) if args.as_of else datetime.now(CHINA)
        data = json.loads(args.records.read_text(encoding="utf-8"))
        ranked = rank(data, now)
        output = (
            render_packet(data, ranked, args.job, replay=args.as_of is not None)
            if args.job else json.dumps({
                "as_of": now.isoformat(), "replay": args.as_of is not None, "positions": ranked,
            }, ensure_ascii=False, indent=2) + "\n"
        )
    except (KeyError, OSError, TypeError, ValueError) as error:
        parser.exit(2, f"无法生成投递材料：{error}\n")
    print(output, end="")


if __name__ == "__main__":
    main()
