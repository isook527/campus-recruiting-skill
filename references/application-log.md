# 继续上次投递与每周复盘

用户第一次要求跟踪投递时，优先使用其指定的本地目录。没有指定目录时，创建当前项目的 `local/` 目录，将记录保存为 `local/campus-applications.sqlite3`，并告诉用户实际位置。后续会话读取同一文件，以最后记录恢复岗位、阶段、简历版本、面试或测评截止和下一步。仅记录用户确认的状态和时间，缺少事实时先展示待填写项。收到邀请属于已发生事件，未来的面试时间填在 `due_at`。

## 操作

```bash
python3 scripts/application_log.py local/campus-applications.sqlite3 record 事件.json
python3 scripts/application_log.py local/campus-applications.sqlite3 review
python3 scripts/application_log.py local/campus-applications.sqlite3 review --job demo-role
python3 scripts/application_log.py local/campus-applications.sqlite3 export 本地安全导出.json
python3 scripts/application_log.py local/campus-applications.sqlite3 backup 本地精确备份.sqlite3
python3 scripts/application_log.py local/campus-applications.sqlite3 migrate 升级前精确备份.sqlite3
```

数据库、备份和导出的父目录须已存在。新建数据库、备份和导出默认权限为 `0600`。`backup`、`export` 和 `migrate` 都拒绝覆盖已有目标。不能把源数据库本身作为目标。缺少源数据库时，迁移会失败，不创建空数据库占位。

先把事件写入一个 JSON 文件，例如 `事件.json`，再把文件路径作为 `record` 的参数。带空格的路径用引号包住。无需额外软件依赖，使用 Python 3.9+ 标准库。程序只在本地处理记录。

## 隐私边界

记录程序在打开数据库写入前检查所有事件文本。疑似中国大陆手机号（含 `+86`、空格、连字符和常见全角写法）及 15 位或 18 位居民身份证号样式会被拒绝。身份证数字之间夹单个空格或连字符也会识别。即使日期或校验位可能输错，也按敏感内容处理。报错不会回显匹配到的号码。数据库不用于保存简历全文、联系方式、身份证号、账号、凭证或未脱敏证明。

`review` 和 `export` 会对 v1 历史记录再次做输出脱敏，因此旧库里已有的手机号或身份证号不会出现在复盘 JSON 或导出文件。这个保护是读取边界，不表示旧文件已经物理清除敏感内容。

`backup` 通过 SQLite 在线备份创建数据库的精确副本。它可能保留旧库中原有的敏感内容。`migrate` 要求同时指定一个升级前精确备份，也会保留这些旧内容。精确备份只放在本人私有本地目录，不加入仓库、Skill、ZIP 或共享文件夹。`0600` 是本机访问权限，不是加密声明。

## 数据库版本与并发

- 新数据库直接使用 schema v2。新写入行的 `privacy_checked` 为 `1`。
- schema v1 可以继续安全复盘和导出，但不能追加记录。升级须显式运行 `migrate`。
- v1→v2 是事务内的 schema 升级：取得写锁后重新检查版本，在同一写锁窗口创建精确 SQLite 备份，再增加 `privacy_checked` 字段并提交。历史行标记为 `0`，原始 payload 保持不变，由读取和导出层持续脱敏。
- 并发执行两个迁移时，后取得锁的进程会重新检查版本并安全返回“无需迁移”，不会做第二次结构修改。升级失败则事务回滚。若精确备份已经成功创建，备份保留供恢复。
- `export` 在一个只读事务中取得一致快照。并发但尚未提交的写入不会混进半份导出。`backup` 使用 SQLite 备份接口取得一致副本。两项操作都以目标不存在为前提，避免并发调用互相覆盖。

## 事件字段

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

可以直接登记用户已经到达的阶段，也可以记录同一阶段的新测评或新一轮面试。更新时重写当前仍有效的下一步和截止。已结束的岗位重新开放时为新一轮创建新 ID。已有 Markdown 或 CSV 可以继续使用[手动表](../templates/local-tracking.md)，或在用户同意后按时间顺序导入已确认事件。用同一文件跨会话使用，即使岗位名称相近也保留招聘方、批次或城市可区分的稳定 ID。

## 复盘交付

默认看北京时间近七个日历日。可用 `--since YYYY-MM-DD` 指定起点。报告里先列最早到期的行动和当前状态，再按投递、测评、面试分别数进入该阶段的岗位。同一岗位的多轮面试只计一次。统计描述已记录事件，不把比例直接解释为通过率。针对有明确反馈的岗位写一条下周实验。没有明确反馈时写「暂无反馈」，优先检查是否漏记行动或未到回访时间。
