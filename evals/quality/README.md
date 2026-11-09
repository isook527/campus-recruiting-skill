# 简历质量盲评

本套用例与 `evals/cases.json` 中的合规用例分别运行。比较两版生成的中文校招简历时，使用相同的 JD、候选人事实、提示词和生成次数。

## 固定设计

- 使用三个合成案例。`Q01` 为综合职能，`Q02` 为内容运营，`Q03` 为人力与项目支持。
- 每个案例、每个版本独立生成三次。
- 直接使用 `cases.json` 里的 `prompt` 原文。
- 产物文件名为 `q01-r01.md` 至 `q03-r03.md`。
- 原始稿件保存在仓库外，例如 `work/v130-eval/baseline/` 和 `work/v130-eval/candidate/`。
- 每份文件只保存请求的回答。模型、版本、组别、提交号、轮次和评审身份不写进稿件。

## 生成两组稿件

每次新开会话，仅提供同一份提示词与该版本的 Skill 和参考资料。会话不继承上一轮稿件。原稿保持 UTF-8 文本和一个结尾换行，不做内容改写。

自动运行器不可用或会产生未获授权的费用时，可以分别人工撰写三次。在评分稿件之外的 `RUN-NOTES.md` 记录实际方法，并注明是人工稿件。

自带运行器在中立的临时目录启动三个只读 Codex 进程。每个进程各生成三例，使用相同的低推理强度。运行器保留主机规则，评估提示禁止调用工具。默认模型为 `gpt-6.1-sol`。指定 `--model` 时，两组使用相同的值。

```bash
python3 evals/quality/run_arm.py \
  --repo . --ref c6e1de9 \
  --cases evals/quality/cases.json \
  --schema evals/quality/round-output.schema.json \
  --out ../v130-eval/baseline

python3 evals/quality/run_arm.py \
  --repo . --ref WORKTREE \
  --cases evals/quality/cases.json \
  --schema evals/quality/round-output.schema.json \
  --out ../v130-eval/candidate
```

以上命令从仓库根目录运行。`c6e1de9` 是冻结的 v1.2.0 源码。候选规则确定后再运行第二条命令。`RUN-NOTES.json` 保存审计信息，评分时排除。

## 盲化与评分

两组各有九份稿件后，运行以下命令生成匿名配对。

```bash
python3 evals/quality/blind_pairs.py \
  --left ../v130-eval/baseline \
  --right ../v130-eval/candidate \
  --out ../v130-eval/blinded \
  --key ../v130-eval/private/answer-key.json \
  --seed-file ../v130-eval/private/seed.txt
```

按实际检出位置调整示例路径。评审只收到 `blinded/`、`rubric.md` 和案例题面。评分和文字理由冻结后，再用私下保存的随机种子及映射揭晓组别。

## 评分前审计

```bash
python3 evals/quality/audit_outputs.py \
  --cases evals/quality/cases.json \
  --arm ../v130-eval/baseline

python3 evals/quality/audit_outputs.py \
  --cases evals/quality/cases.json \
  --arm ../v130-eval/candidate
```

审计检查文件名、轮次数量、空文件和组别泄漏，并标记完全重复的稿件。质量和事实由评审对照 `rubric.md` 及 `cases.json` 的事实字段判定。

发布检查还应单独运行合规用例和单元测试。质量盲评的优势不能抵消合规退步。
