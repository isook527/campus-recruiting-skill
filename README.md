# 秋招求职助手

给非技术岗应届求职者用的免费开源 Skill。它在 Agent 对话里完成岗位核验、筛选、简历改写、面试练习和投递跟踪。所有材料随源码开放，无需付费、激活或登录专用工作台。

发一个岗位链接和一到两段真实经历，即可开始准备一份针对该岗位的投递包。

## 安装

下载仓库 ZIP 或克隆仓库，把整个 `campus-recruiting-skill` 目录放到 Agent 的本地 Skill 目录。Codex 使用 `~/.codex/skills/`，Claude Code 使用 `~/.claude/skills/`。若解压目录带分支后缀，改名为 `campus-recruiting-skill`，确认该目录下直接包含 `SKILL.md`，然后重新打开 Agent。

在对话中使用 `$campus-recruiting-skill` 或明确让 Agent 按 [SKILL.md](SKILL.md) 处理。实时岗位核验使用 Agent 已有的网页工具。结构化批量校验用 Python 3.9+ 标准库。简历、案例、面试和行动模板可离线阅读。

## 可以这样说

| 目标 | 给 Agent 的话 |
| --- | --- |
| 查现在还能投的 | 我 2027 年 6 月毕业，上海或杭州，想找内容运营和市场校招。只列你刚刚核验过官网与投递页的岗位。 |
| 清理旧表 | 帮我把这份秋招表分成当前可投、未开始、明确结束和待核。只在结果表排除失效记录，保留我的原文件。 |
| 判断值不值得投 | 这两个岗位帮我排一下。分开写硬性条件、优先项和本人经历。缺什么信息就告诉我先核哪一条。 |
| 做一份投递包 | 这是一份 JD 和我的两段经历。给我一版能编辑的简历、每条改写依据、附件检查和三道追问。 |
| 模拟面试 | 我想投银行综合岗。一次问一题，根据我的回答追问。用同一套标准给我两轮练习反馈。 |
| 做岗位实操 | 给我一道人力行政排期题，等我交卷再逐项评分。 |
| 继续上次投递 | 读取我选的本地投递记录，找出本周最早到期的行动，按实际反馈帮我复盘。 |

## 内容

- [查岗、核验与去重](references/job-verification.md) · [官方来源导航](references/official-sources.md)
- [岗位判断、排序与投递包](references/application-packet.md)
- [七天求职行动](references/action-guide.md) · [投递前检查与防骗](references/application-safety.md) · [本地行动表](templates/local-tracking.md)
- [12 个模拟经历案例](references/cases/index.md) · [简历证据卡、三份示范与一分钟自我介绍](references/resume-and-evidence.md) · [三类可编辑简历](templates/resume.md)
- [20 道面试题与 12 条追问](references/interview.md) · [模拟面试评分](references/interview-coaching.md) · [三个方向的实操题](references/practice.md)
- [本地投递记录和每周复盘](references/application-log.md)

实时机会每次重新查验。来源导航只用于起步，历史线索、已经关闭的公告和待核岗位不混入实时结果。招聘方原文与站点遵循各自权利，仓库整理的是自有案例、模板、核验方法和必要链接。

维护时运行 `python3 -m unittest discover -s tests -v`。测试覆盖岗位核验、投递包的事实引用、跨进程恢复和重复写入。个人记录保存在用户选定的本地文件中。

本仓库的自有内容和代码按 [MIT License](LICENSE) 提供。
