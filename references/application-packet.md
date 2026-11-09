# 岗位判断与投递包

一个岗位链接或一份 JD 加一到两段经历即可开始。候选人给过简历时，复用本人确认的事实，不重复索取。未提供关键硬门槛信息时，先出岗位判断和可完成的草稿。

## 判断投递顺序

使用[投递优先级](application-prioritization.md)。先核实招聘状态和资格，确认关闭或硬门槛不满足时停止定制。其余按本人条件和公告规则给出可排期或条件成立才投的结论，再确定本周顺序。

## 交付一岗一份

- **岗位判断**写岗位名称、核验时间、官方公告、实际投递入口、截止时间及北京时间口径。给行动结论、投递档位和最重要的缺口。待核时写明「若哪些条件成立则投，否则不投」。
- **证据对照**用最多四列的硬门槛表列出要求及出处、判断、事实及来源和核对动作。优先项和岗位任务移到软匹配清单。区分本人动作、团队结果和练习作品。
- **可编辑简历**选择[对应方向模板](../templates/resume.md)。用用户确认的教育、经历、技能和证书生成可复制文本。联系方式留给本人填写。每条修改注明用了哪些事实，哪些要求决定了顺序或取舍。给新版本编号，例如 `cv-ops-02`。材料里没有的数字、任期和指标先留在改写依据区，简历正文只写已有事实。逐条尽量写成「动作 → 交付 → 可核对结果」，结果未确认时保留动作与实际产出物。
- **网申表单字段稿**。按官方字段顺序写项目经历、自我评价、证书等字段。列字段名、必填状态、原页面限制和出处，另列附件格式、大小、数量和命名。核对网申的字符或字节计数口径；无法打开表单时把限制和字段标为待核。表单与简历沿用同一事实和时间线。身份证、手机号、联系地址和证明文件由本人在可信官方流程填写。
- **投递前检查**结合[投递安全](application-safety.md)和当前公告列附件、语言、格式、志愿数和日期。逐项标记已核、待处理或待确认。硬门槛或网申状态仍待核时，称为准备草稿。
- **三道追问**对每条经历做「做了什么 / 怎么做 / 证据在哪」三层追问。回答不了时改为可确认的职责或移除。选三道不同的代表题写进投递包，每题附好答案要点和红线，不预设用户做过未确认的工作。继续练习时进入[评分与复练](interview-coaching.md)。

## 生成 Markdown 和排序

有 Python 时可以用脚本执行统一排序并输出 Markdown。把本次采集和归纳的数据写到用户选定的本地目录，再运行以下命令。只在用户指定的位置保存新文件，保留既有简历版本。

```bash
python3 scripts/prepare_application.py 评估.json
python3 scripts/prepare_application.py 评估.json --job example-job
```

JSON 的顶层字段：

| 字段 | 写法 |
| --- | --- |
| `jobs` | [岗位核验](job-verification.md#结构化核验记录)规定的数组 |
| `facts` | 事实编号到对象的字典。每项含 `text` 与 `provenance`（`user_confirmed` 为用户确认，`material` 为材料支持）。材料支持时再填 `source_detail`，用文件名或页码等简短定位 |
| `reviews` | 评估数组，每条含 `job_id`、`requirements_complete`、`criteria`。出包时同一条还需 `resume_version`、`resume`、`questions`、`checklist` |
| `criteria` | 每项含 `kind`（`required`、`preferred`、`duty`）、`requirement`、`source`（具体公告小节或原文定位）、`state`（`met`、`gap`、`unknown`）、`fact_ids`、`evidence_type`（`direct` 为直接证据，`transferable` 为可迁移经验，缺事实填 `null`）、`next_step` |
| `resume_version` | 可写进本地投递记录的简历版本，例如 `cv-ops-02`。新版本使用新编号 |
| `resume` | 每项含 `section`（`education`、`experience`、`skills`）、`text`、`fact_ids`、`rationale` |
| `questions` | 三项，每项含 `text`、`fact_ids`，引用本版简历用到的事实。可加 `answer_anchor` 与 `red_line` 写题目专属标准 |
| 投递约束 | 每条评估可含 `tier`（`target` / `safety` / `stretch`）、`effort_minutes`（正整数）、`rolling`（布尔）、`choice_mode`（`one_role` / `ordered_preferences`）和 `choice_confirmed`（该岗与顺位已由本人确认时才填 `true`），及可选 `choice_group`（同一限额组使用同一标识；省略时按招聘方与批次识别） |
| `form_fields` | 每条评估可附数组，每项含 `label`、`constraint`、`source`、`fact_ids`，以及 `text`（待补用 `null`）与可选 `max_chars`。脚本的字符数按 Unicode 码点计，最终以官方计数器为准 |
| `checklist` | 每项含 `item` 和 `state`（`done`、`todo`、`unknown`） |

只有公告及适用的资格条款都读完才填 `requirements_complete: true`。判断满足或不满足硬性条件都须引用直接事实。可迁移经验用于解释职责匹配，不能替代学历、语言或证书。缺关键事实时用 `unknown`。没有可靠网申证据时给岗位记录 `status: "unverified"`，并保留实际观察。脚本检查编号、日期、状态与引用关系，事实与文案是否匹配仍须逐句核对。没有 Python 时使用同一判断顺序和交付结构在对话中完成。
