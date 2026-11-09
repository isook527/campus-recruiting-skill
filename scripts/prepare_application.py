#!/usr/bin/env python3
"""Rank reviewed positions or render an evidence-linked application packet."""

import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from check_jobs import CHINA, OFFICIAL_SOURCES, audit, parse_boundary, parse_datetime


DECISIONS = {"ready": "优先准备投递", "verify": "条件成立才投", "skip": "跳过"}
REASONS = {
    "verified_open": "具体岗位的核验记录仍有效",
    "campaign_open": "项目开放，需再核具体岗位",
    "not_started": "报名尚未开始",
    "closed": "已关闭或截止",
    "unverified": "官网或投递状态待核",
    "stale": "核验记录已过时",
    "deadline_time_unconfirmed": "截止日当天的时刻待核",
    "source_not_confirmed": "目前只有线索或来源尚未确认",
    "official_conflict": "官方证据冲突，需复核后再提交",
    "duplicate_requires_resolution": "存在未解决的重复记录",
}
KINDS = {"required": "硬性资格", "preferred": "优先条件", "duty": "岗位任务"}
STATES = {"met": "有依据", "gap": "有缺口", "unknown": "待确认"}
PROVENANCE = {"user_confirmed": "用户确认", "material": "材料支持"}
RELATIONS = {"direct": "直接证据", "transferable": "可迁移经验"}
SECTIONS = {"education": "教育背景", "experience": "相关经历", "skills": "技能与证书"}
CHECKS = {"done": "已核对", "todo": "待处理", "unknown": "待确认"}
TIERS = {"target": "对口", "safety": "保底", "stretch": "冲刺"}
CHOICE_MODES = {"one_role", "ordered_preferences"}
HARD_STATES = {"met": "满足", "gap": "不满足", "unknown": "待核"}
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
        raise ValueError(
            'facts 需要以事实编号为键的 JSON 对象。示例 '
            '{"F1": {"text": "负责班费记录", "provenance": "user_confirmed"}}。'
            '完整字段见 references/application-packet.md 的「生成 Markdown 和排序」。'
        )
    for key, fact in facts.items():
        if not filled(key) or not isinstance(fact, dict) or not filled(fact.get("text")):
            raise ValueError("每条事实须有编号和已确认内容")
        origin = fact.get("provenance")
        if origin not in PROVENANCE or (origin == "material" and not filled(fact.get("source_detail"))):
            raise ValueError("每条事实须标记来源，材料支持的事实须标记材料位置")
    jobs = {row["id"]: row for row in data["jobs"]}
    reviews = {}
    confirmed_single_choices = set()
    for review in data["reviews"]:
        key = review["job_id"]
        if key in reviews or key not in jobs:
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
        if "tier" in review and review["tier"] not in TIERS:
            raise ValueError("tier 须为 target、safety 或 stretch")
        if "effort_minutes" in review and (
            type(review["effort_minutes"]) is not int or review["effort_minutes"] <= 0
        ):
            raise ValueError("effort_minutes 须为正整数")
        for flag in ("rolling", "choice_confirmed"):
            if flag in review and type(review[flag]) is not bool:
                raise ValueError(f"{flag} 须为布尔值")
        if "choice_mode" in review and review["choice_mode"] not in CHOICE_MODES:
            raise ValueError("choice_mode 须为 one_role 或 ordered_preferences")
        if "choice_group" in review and not filled(review["choice_group"]):
            raise ValueError("choice_group 须为同一限额单位和批次的稳定标识")
        if review.get("choice_mode") == "one_role" and review.get("choice_confirmed"):
            job = jobs[key]
            group = (review["choice_group"],) if "choice_group" in review else (
                job["employer"], job["batch"],
            )
            group = tuple(" ".join(part.casefold().split()) for part in group)
            if group in confirmed_single_choices:
                raise ValueError("同一限报组只能确认一个岗位")
            confirmed_single_choices.add(group)
        reviews[key] = review
    return reviews


def decision(status, review):
    required = [item for item in review.get("criteria", []) if item["kind"] == "required"]
    if status == "closed" or any(item["state"] == "gap" for item in required):
        return "skip"
    if (
        status != "verified_open" or not review.get("requirements_complete") or not required
        or any(item["state"] != "met" for item in required)
        or (review.get("choice_mode") and not review.get("choice_confirmed"))
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
            "tier": TIERS.get(review.get("tier"), "待分档"),
            "source_type": job.get("source_type"),
            "deadline_countdown": checked["deadline_countdown"][job["id"]],
            "rolling": review.get("rolling", False),
            "effort_minutes": review.get("effort_minutes"),
            "choice_mode": review.get("choice_mode"),
            "choice_pending": bool(review.get("choice_mode") and not review.get("choice_confirmed")),
            "reasons": [
                item["requirement"] for item in review.get("criteria", [])
                if item["kind"] == "required" and item["state"] != "met"
            ],
        })
    last = datetime.max.replace(tzinfo=CHINA)

    def order(row):
        deadline, _ = parse_boundary(row["deadline"])
        urgent = deadline is not None and deadline <= now + timedelta(days=3)
        timing = 0 if urgent else 1 if row["rolling"] else 2
        return (
            list(DECISIONS).index(row["decision"]), timing, (deadline or last) if urgent else last,
            -row["direct_duties"], -row["matched_duties"],
            row["source_type"] not in OFFICIAL_SOURCES,
            row["effort_minutes"] or float("inf"), deadline or last, row["id"],
        )

    return sorted(ranked, key=order)


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
    if row["decision"] == "skip":
        reason = "、".join(row["reasons"]) or REASONS[row["verification"]]
        raise ValueError(f"该岗位已排除，停止生成定制投递包。{reason}")
    job = next(item for item in data["jobs"] if item["id"] == job_id)
    facts = data["facts"]
    resume = review["resume"]
    questions = review["questions"]
    checklist = review["checklist"]
    form_fields = review.get("form_fields", [])
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

    for item in form_fields:
        if not filled(item["label"]) or not filled(item["constraint"]) or not filled(item["source"]):
            raise ValueError("表单字段须注明字段名、限制和出处")
        ids = evidence_ids(item["fact_ids"], facts)
        draft = item.get("text")
        if draft is not None and (not filled(draft) or not ids):
            raise ValueError("表单草稿须回指已确认事实，缺资料时填 null")
        limit = item.get("max_chars")
        if limit is not None and (type(limit) is not int or limit <= 0):
            raise ValueError("max_chars 须为正整数")

    lines = [
        f"# {cell(job['employer'])} · {cell(job['title'])}投递准备包", "",
        f"**准备判断** {DECISIONS[row['decision']]}。{REASONS[row['verification']]}。",
        f"**截止** {job['deadline'] or '未公布'}　**记录时间** {job['checked_at']}",
        f"**简历版本** `{version}`",
    ]
    if replay or row["decision"] != "ready" or any(item["state"] != "done" for item in checklist):
        lines.append("**材料状态**　准备草稿，待核事项见下方清单。")
    if row["decision"] == "verify":
        gates = ["具体岗位及入口仍有效", "全部硬门槛核实且满足"]
        gates.extend(row["reasons"])
        if row["choice_pending"]:
            gates.append("本人已确认志愿与占用规则")
        lines.append("**投递条件** 若" + "、".join(map(cell, gates))
                     + "均已确认，可投。任一不成立则不投，待核期间只备料。")
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
        "", "## 硬门槛", "",
        "| 要求及出处 | 判断 | 事实及来源 | 核对动作 |",
        "| --- | --- | --- | --- |",
    ])
    soft = []
    for item in review["criteria"]:
        facts_label = " / ".join(
            f"{key}（{fact_source(facts[key])}）" for key in item["fact_ids"]
        ) or "待补"
        requirement = f"{item['requirement']} · {item['source']}"
        if item["kind"] == "required":
            relation = RELATIONS.get(item["evidence_type"])
            evidence = f"{relation} · {facts_label}" if relation else facts_label
            cells = [requirement, HARD_STATES[item["state"]], evidence, item["next_step"]]
            lines.append("| " + " | ".join(map(cell, cells)) + " |")
        else:
            relation = RELATIONS.get(item["evidence_type"], "待确认")
            soft.append(
                f"- **{KINDS[item['kind']]} · {cell(requirement)}**　{STATES[item['state']]}。"
                f"{relation} · {cell(facts_label)}。{cell(item['next_step'])}"
            )
    lines.extend(["", "## 软匹配", "", *(soft or ["暂无可核对的优先项或岗位任务。"])])
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
    if form_fields:
        lines.extend(["", "## 网申表单字段稿", ""])
        for item in form_fields:
            draft = item.get("text")
            constraint = cell(item["constraint"])
            lines.append(f"- **{cell(item['label'])}**　{constraint}（{cell(item['source'])}）")
            if draft is None:
                lines.append("  - 待本人补充或在官方页面填写。")
                continue
            lines.append(f"  - {cell(draft)}（{len(draft)} 个 Unicode 字符）")
            if item.get("max_chars") and len(draft) > item["max_chars"]:
                lines.append("  - 超出记录的字符上限。请缩短并用网申计数器复核。")
    lines.extend(["", "## 投递前检查", ""])
    for item in checklist:
        mark = "x" if item["state"] == "done" else " "
        lines.append(f"- [{mark}] {cell(item['item'])}（{CHECKS[item['state']]}）")
    lines.extend(["", "## 简历追问", ""])
    for i, item in enumerate(questions, 1):
        lines.append(f"{i}. {cell(item['text'])}（{'、'.join(item['fact_ids'])}）")
        anchors = item.get("answer_anchor", "说明本人实际动作、产出物与可核对依据。")
        red_line = item.get("red_line", "补造未确认数字，或把团队成果当成本人贡献。")
        if not filled(anchors) or not filled(red_line):
            raise ValueError("追问的好答案要点和红线须为非空文本")
        lines.extend([f"   - 好答案要点　{cell(anchors)}", f"   - 红线　{cell(red_line)}"])
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
