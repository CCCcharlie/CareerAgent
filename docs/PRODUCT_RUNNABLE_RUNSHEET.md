# CareerAgent — Product Runnable Runsheet

> **当前目标**：尽快恢复 `feature/integrate-wip` 的可展示 MVP。
> DOM extraction migration 已完成，不再属于本 Runsheet 范围。
> 当前下一步：**R2 — Integrated MVP End-to-End**。

---

## 本文件和 `PRODUCT_RUNNABLE_PLAN.md` 的分工

* `PRODUCT_RUNNABLE_PLAN.md`
  = 设计参考，说明为什么修、怎么修、技术边界和 MVP 验收标准。

* 本文件
  = 执行指南，只记录：

  * 当前做到哪一步
  * 下一步给 Agent 什么指令
  * 验证方式
  * 实际结果 / commit

不要在 Runsheet 重新展开 Plan 已经写过的技术设计。

通用工程规则统一遵守 `AGENTS.md`。

---

# R0 — MVP Baseline Check

状态：COMPLETED（2026-09-15）

给 Agent：

```text
现在执行 Product Runnable R0。

读取：
- AGENTS.md
- docs/PRODUCT_RUNNABLE_PLAN.md 的 Golden Baseline / R0 部分
- 当前 feature/integrate-wip
- master 中对应稳定 MVP 实现

目标只是确认当前真正阻断 MVP 的 regression。

重点检查：
- 正式交互流程
- matcher
- save / TOP10 / output
- 当前 Ollama text model

DOM migration 已完成，不重新诊断。

完成后把结论更新到本 Runsheet。
如果确认 matcher 是当前主要 blocker，直接继续 R1。
```

验收：

* 明确当前 MVP blocker
* 不产生无关代码修改

实际结果：

* `master` 与当前分支均保留正式的 LinkedIn 搜索后 Enter → crawl 路径；当前
  `main.py` 还保留多轮交互循环。R0 未发现交互流程回归。
* `_save()` 仍按 score 降序写入 `output/jobs_<timestamp>.json`，`_print_top10()`
  仍在每轮保存后调用。R0 未发现 save / TOP10 / output 回归。
* `config.yaml` 当前 text model 为 `qwen3.5:9b`；本机 Ollama `/api/tags` 确认
  模型已安装。
* 真实最小 matcher 请求成功：单简历 Python backend 样本在 **29.52s** 返回
  score `8.05`、selected resume、五项 dimension scores 和非空 analysis。当前
  高级 matcher 相比 master 虽增加多简历、较长上下文和 `num_predict=800`，但
  本轮没有复现 HTTP 500 或 provider failure。
* **结论：matcher 不是当前 MVP blocker，R1 不触发。** DOM click/detail 已由
  既有 smoke 确认；当前剩余 gate 是 R2 的正式 LinkedIn 端到端验收，确认真实
  matcher、threshold 与 output artifact 在同一次产品流程内联通。
* 本 R0 未修改生产代码；仅更新本 Runsheet。

---

# R1 — Matcher MVP Restore

状态：NOT_REQUIRED（R0 未确认 matcher regression）

给 Agent：

```text
现在执行 Product Runnable R1。

读取：
- docs/PRODUCT_RUNNABLE_PLAN.md 的 R1 Matcher Unblock
- R0 已确认结果
- master 与当前 feature 的 matcher 实现

按 Plan 进行最小真实验证并修复 matcher regression。

目标：
- 至少一次真实 matcher scoring 成功
- provider failure 不再伪装成正常低分
- 不修改 DOM / Vision / HumanActions / 正式交互流程

补必要测试。

验证：
pytest tests/
python -X utf8 scripts/verify.py
git diff --check

完成后更新本 Runsheet并停止，等待 R2。
```

实际结果：

* R0 的当前 matcher 最小请求已成功，未发现需要 lightweight fallback 的
  `CURRENT_ADVANCED_PAYLOAD_FAILURE` 或 provider failure。
* commit：不适用

---

# R2 — Integrated MVP E2E

状态：NEXT（R0 已完成，R1 不需要）

**开发验收方式：自动 E2E smoke。** 正式 `main.py` 仍保持用户在 LinkedIn
完成搜索后回终端按 Enter 的产品交互；开发阶段不再要求用户运行 `main.py`。
Agent 使用 `scripts/real_smoke.py --e2e` 自动完成指定搜索 URL 的 MVP 流程。

给 Agent：

```text
现在执行 Product Runnable R2。

读取 PRODUCT_RUNNABLE_PLAN.md 的 R2。

执行 `scripts/real_smoke.py --e2e --job-list-mode dom`，传入指定的 LinkedIn
search URL。该路径复用生产 BrowserManager、DOM extraction、HumanActions、
detail extraction、ResumeMatcher、threshold 和 save 逻辑，并自动退出。

根据 smoke 日志和 result.json 核验 correct click、detail、matcher、threshold
和 output JSON；如果存在 blocker，只修该 blocker 并补 regression test。
```

自动 E2E 步骤：

1. Agent 传入指定的 LinkedIn jobs search URL。
2. smoke 自动启动 Chrome 并使用 DOM mode 处理岗位。
3. smoke 自动完成 click、detail、matcher、threshold 和 save。
4. smoke 自动关闭浏览器并输出 result.json、run.log 和 output JSON 路径。

验收：

```text
CORRECT_JOB >= 1
DETAIL_SUCCESS >= 1
MATCH_SUCCESS >= 1
output JSON exists
```

实际结果：

* 已扩展 `scripts/real_smoke.py --e2e`，默认 CLI mode 为 `dom`；待执行真实
  LinkedIn E2E。

---

# R3 — MVP Checkpoint

状态：WAITING_FOR_R2

给 Agent：

```text
现在执行 Product Runnable R3。

读取 PRODUCT_RUNNABLE_PLAN.md 的 MVP Checkpoint 要求。

执行：
pytest tests/
python -X utf8 scripts/verify.py
git diff --check
git status --short

确认提交只包含本轮 MVP 必需修复、测试和 Product Runnable 文档。

不要提交历史 debug artifacts。

提交后报告：
- commit hash
- tests
- E2E 结果
- output artifact

完成后停止。
```

R3 完成后：

```text
PRODUCT_RUNNABLE_MVP = PASS
```

---

# Deferred

以下内容不属于当前 MVP Runsheet：

* DOM performance
* Vision fallback consolidation
* console telemetry cleanup
* default DOM switch
* UI / 新网站支持

这些在 MVP 完成后另开后续 Plan。
