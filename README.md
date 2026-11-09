# 秋招求职助手

给非技术岗应届求职者用的免费开源 Skill。它在 Agent 对话里完成岗位核验、筛选、简历改写、面试练习和投递跟踪。所有材料随源码开放，无需付费、激活或登录专用工作台。

## 安装

下载仓库 ZIP 或克隆仓库，把整个 `campus-recruiting-skill` 目录放到 Agent 的本地 Skill 目录。Codex 使用 `~/.codex/skills/`，Claude Code 使用 `~/.claude/skills/`。若解压目录带分支后缀，改名为 `campus-recruiting-skill`，确认该目录下直接包含 `SKILL.md`，然后重新打开 Agent。

在对话中使用 `$campus-recruiting-skill` 或明确让 Agent 按 [SKILL.md](SKILL.md) 处理。实时岗位核验使用 Agent 已有的网页工具。结构化批量校验用 Python 3.9+ 标准库。简历、案例、面试和行动模板可离线阅读。

## 可以这样说

| 目标 | 给 Agent 的话 |
| --- | --- |
| 查现在还能投的 | 我 2027 年 6 月毕业，上海或杭州，想找内容运营和市场校招。只列你刚刚核验过官网与投递页的岗位。 |
| 清理旧表 | 帮我把这份秋招表分成当前可投、未开始、明确结束和待核。只在结果表排除失效记录，保留我的原文件。 |
| 用普通经历写简历 | 我只有市场调研课程和社团排版经历。用案例带我做证据卡，再改成针对这份 JD 的保守版本。 |
| 模拟面试 | 我想投银行综合岗。每次问我一题，继续问本人动作和证据。 |
| 跟踪投递 | 把我刚确认的岗位、简历版本、面试时间和下一步整理成一张可本地维护的表。 |

## 内容

- [查岗、核验与去重](references/job-verification.md) · [官方来源导航](references/official-sources.md)
- [七天求职行动](references/action-guide.md) · [投递前检查与防骗](references/application-safety.md) · [本地行动表](templates/local-tracking.md)
- [12 个模拟经历案例](references/cases/index.md) · [简历证据卡、三份示范与一分钟自我介绍](references/resume-and-evidence.md) · [三类可编辑简历](templates/resume.md)
- [20 道面试题与 12 条追问](references/interview.md)

实时机会每次重新查验。来源导航只用于起步，历史线索、已经关闭的公告和待核岗位不混入实时结果。招聘方原文与站点遵循各自权利，仓库整理的是自有案例、模板、核验方法和必要链接。

维护校验器时运行 `python3 -m unittest discover -s tests -v`。测试覆盖截止日、核验时效、证据字段、项目与岗位的区分及重复记录。

本仓库的自有内容和代码按 [MIT License](LICENSE) 提供。
