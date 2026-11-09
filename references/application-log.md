# 继续上次投递与每周复盘

用户第一次要求跟踪投递时，优先使用其指定的本地目录。没有指定目录时，创建当前项目的 `local/` 目录，将记录保存为 `local/campus-applications.sqlite3`，并告诉用户实际位置。后续会话读取同一文件，以最后记录恢复岗位、阶段、简历版本、面试或测评截止和下一步。仅记录用户确认的状态和时间，缺少事实时先展示待填写项。收到邀请属于已发生事件，未来的面试时间填在 `due_at`。

## 操作

```bash
python3 scripts/application_log.py local/campus-applications.sqlite3 record 事件.json
python3 scripts/application_log.py local/campus-applications.sqlite3 review
python3 scripts/application_log.py local/campus-applications.sqlite3 review --job demo-role
```

数据库父目录须已存在。首次记录时创建数据库。无需额外软件依赖，使用 Python 3.9+ 标准库。程序只在本地处理记录。已有 Markdown 或 CSV 可以继续使用[手动表](../templates/local-tracking.md)，或在用户同意后按时间顺序导入已确认事件。用同一文件跨会话使用，即使岗位名称相近也保留招聘方、批次或城市可区分的稳定 ID。

先把事件写入一个 JSON 文件，例如 `事件.json`，再把文件路径作为 `record` 的参数。带空格的路径用引号包住。

每份事件 JSON 包含这些字段：

| 字段 | 写法 |
| --- | --- |
| `event_id`、`job_id` | 用字母、数字和少量分隔符组成的稳定短 ID。同一次记录重试复用事件 ID |
| `employer`、`title` | 招聘主体和准确岗位名 |
| `stage` | `tracking`、`submitted`、`assessment`、`interview`、`offer`、`accepted`、`rejected`、`withdrawn` |
| `at` | 已发生事件的 ISO 8601 时间，带时区 |
| `resume_version` | 本次使用的简历版本 ID，例如 `cv-ops-02`。未变化填 `null`，复盘会沿用最近已知版本 |
| `next_action`、`due_at` | 本人确认的下一步与截止时间，未知填 `null`。精确时刻须带时区。只有日期时填 YYYY-MM-DD，当天保持待办 |
| `feedback` | 用户确认收到的反馈。沉默填 `null` |

可以直接登记用户已经到达的阶段，也可以记录同一阶段的新测评或新一轮面试。更新时重写当前仍有效的下一步和截止。已结束的岗位重新开放时为新一轮创建新 ID。数据库存岗位与状态、版本号、本人选择留存的反馈，不存简历全文、账号、联系方式或凭证。应将数据库放在私人本地目录，不随 Skill、ZIP 或仓库分发。

## 复盘交付

默认看北京时间近七个日历日。可用 `--since YYYY-MM-DD` 指定起点。报告里先列最早到期的行动和当前状态，再按投递、测评、面试分别数进入该阶段的岗位。同一岗位的多轮面试只计一次。统计描述已记录事件，不把比例直接解释为通过率。针对有明确反馈的岗位写一条下周实验。没有明确反馈时写「暂无反馈」，优先检查是否漏记行动或未到回访时间。
