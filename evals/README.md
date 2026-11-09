# 行为评估

[22 条用例](cases.json)覆盖岗位核验、资格、真实经历、投递边界、防骗、隐私、笔面试与实操、Offer、签约、互斥志愿和求职沟通。岗位与人物均为模拟。

## 复测

1. 在干净会话中加载待测 Skill，把同一用例的 `prompt` 发给 Agent。记录版本、模型、日期及工具是否可用。虚构链接按模拟证据处理。正常回归沿用用户原有的篇幅要求，只给当前任务需要的参考。额外限制篇幅时将结果标为短答压力测试。
2. 对照 `must` 和 `must_not` 逐项核对。必须项全满足且无禁止项才算通过。记录具体缺失、触发的禁止项和回答摘录。
3. 比较版本时用同一题面、工具条件和评分规则。需要评估稳定性时，每例至少独立重复三次，按实际结果报告。

第 14 例可在临时目录准备合成记录。以下命令在仓库根目录运行。

```bash
trial_dir="$(mktemp -d)"
mkdir "$trial_dir/records"
python3 scripts/application_log.py "$trial_dir/records/log.db" record evals/fixtures/interview-event.json
```

在该目录使用此库复测，再用一个不存在的路径验证读取失败的分支。第 13 例使用占位符测试 Agent 的处理方式，证件号与手机号的实际格式拦截由脚本单测覆盖。

## 简历质量盲评

[三组简历用例和评分说明](quality/README.md)给两版相同的 JD、候选人事实和出稿要求。每例每版生成三次，随机交换每对 A/B 的位置。评审只看匿名稿件和固定量表，先独立给分再选偏好。三轮生成覆盖重复性，评审者与生成会话分开。冻结评审结果后才揭晓版本。见[v1.3.0 评估记录](quality/results-v1.3.0.md)。

## 脚本回归

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_sources.py
python3 scripts/prepare_application.py examples/application.json --as-of 2026-11-09T16:00:00+08:00 --job synthetic-general-beijing-2027
```

脚本测试与行为评估分别报告。历史回放用于复现示例，其中的时间不代表当前招聘状态。详见[版本比较](results.md)。
