# CareerAgent — Product Runnable Plan

> 目标：在当前 `feature/integrate-wip` 上，用最小修复恢复一个可以演示的 MVP。
>
> 当前基线：
>
> * DOM migration 已完成并收尾到 `a20c58e`
> * `master` branch 已有可工作的 MVP 流程，作为行为基线
> * 不重新设计已经正常工作的交互、保存、分页和浏览器流程
> * 本阶段只修“整合后新增的回归”

---

## 1. MVP Definition of Done

本轮完成后必须能够真实运行：

```text
python main.py
→ Chrome 启动
→ 用户正常完成 LinkedIn 搜索
→ 回终端按 Enter
→ 自动枚举岗位
→ 正确点击岗位
→ 提取详情
→ Matcher 至少成功评分一个真实岗位
→ threshold 正常工作
→ 结果保存到 output/
→ 程序正常完成或继续交互
```

满足以上流程即定义：

`PRODUCT_RUNNABLE_MVP = PASS`

本轮不要求性能最优、日志最漂亮或架构最终完成。

---

## 2. Golden Baseline

`master` 是已知可工作的 MVP 参考。

当前整合版本应该保留 master 已有产品行为，同时叠加：

* DOM job-list extraction
* DOM identity
* fresh bounding box click
* A.4 detail extraction
* Vision semantic fallback
* 多简历能力（如果不会阻断 MVP）

不要为了恢复 MVP：

* 整段复制旧 `main.py`
* 回滚 DOM migration
* 删除新的详情提取逻辑
* 删除 Vision fallback
* 重写 HumanActions
* 大规模重构 matcher

只移植或修复被真实证明发生回归的部分。

---

## 3. R0 — 快速基线确认

只检查 MVP hot path：

* `main.py` 正式交互是否仍符合 master 的可用行为
* 搜索后 Enter 是否能正常进入 crawl
* output save / TOP10 是否仍存在
* 当前 Ollama `text_model` 是否真实存在
* 当前 matcher 最小请求是否成功

如果交互、保存、分页没有真实故障，不修改。

当前已知：

DOM click / detail 已真实工作。

因此本轮禁止重新诊断 DOM。

---

## 4. R1 — Matcher Unblock

这是当前最高优先级。

当前整合 matcher 相比 master 增加：

* 多简历输入
* 更长 resume / JD context
* 五维分析
* 更大的结构化输出
* 更高 `num_predict`

当前真实运行出现：

`POST /api/generate → HTTP 500`

### 第一阶段：确认原因

使用当前 configured text model 分别做：

1. 极小 Ollama generate request
2. 当前 matcher request
3. master 风格的轻量 matcher request

判断属于：

```text
MODEL_SERVICE_FAILURE
CURRENT_ADVANCED_PAYLOAD_FAILURE
PROMPT/CONTEXT_RESOURCE_FAILURE
OTHER
```

不要凭猜测修改参数。

### 第二阶段：最快恢复策略

如果当前高级 matcher 正常：
→ 不改 matcher，只继续 E2E。

如果高级 matcher 失败，但轻量请求成功：
→ 在当前 `ResumeMatcher` 内增加一个有边界的 lightweight fallback。

优先结构：

```text
advanced matcher
↓ failure
lightweight matcher fallback
↓
score + reason (+ 能可靠提供的最小附加字段)
```

fallback 只用于保证 MVP，不建立平行 matcher 文件，不覆盖正常高级路径。

### Failure semantics

无论高级还是 fallback：

模型请求失败不得继续被当成真实的 `score=5.0` 岗位。

必须区分：

```text
MATCH_SUCCESS
MATCH_FAILED
```

main 只有在 `MATCH_SUCCESS` 时才执行：

`score >= min_score`

如果最终 provider 仍失败：

* 记录失败
* 不伪装成低分
* 不因为单个岗位失败终止整个 run

具体字段可以在实现时按当前契约做最小扩展，不要求大规模 schema 重构。

---

## 5. R2 — Integrated MVP End-to-End

R1 通过后立即运行：

```text
python main.py
```

不使用 `real_smoke.py` 代替最终验收。

真实验收：

```text
LinkedIn 搜索
→ Enter
→ job enumeration
→ correct click
→ detail
→ matcher
→ threshold
→ output JSON
```

为快速完成 MVP：

* 使用 `max_pages=1`
* 不要求处理所有岗位
* 不要求性能优化
* 不要求 console cleanup
* 至少验证 1~3 个真实岗位
* 至少一个岗位取得真实 matcher score

如果 DOM mode 工作正常，优先用 DOM 完成验收。

如果发现 DOM 本身的新 regression，才允许针对真实 failure 做最小修复。

---

## 6. R3 — MVP Checkpoint

最终必须执行：

```text
pytest tests/
python -X utf8 scripts/verify.py
git diff --check
python main.py
```

必须报告：

* jobs discovered
* jobs processed
* correct / wrong click
* detail success / failed
* matcher success / failed
* accepted jobs
* output JSON path

成功后：

1. 更新 `PRODUCT_RUNNABLE_RUNSHEET.md`
2. commit 当前修复
3. push `feature/integrate-wip`
4. 标记 `PRODUCT_RUNNABLE_MVP = PASS`

---

## 7. 明确延期

以下全部不阻塞本次 MVP：

* DOM performance optimization
* 180s smoke budget 优化
* Vision fallback consolidation
* Vision coordinate 修复
* console JSON telemetry 美化
* UI
* 日志系统重构
* 新招聘网站
* 大规模并发
* 默认 `vision → dom` 切换
* matcher 完整架构重新设计

这些在 MVP checkpoint 后单独继续。

---

## 8. MVP 后续路线

MVP PASS 后再进入：

```text
P1 DOM performance
P2 console / telemetry UX
P3 runtime resilience
P4 Vision fallback consolidation
P5 default DOM decision
```

这些不属于当前一小时修复范围。
