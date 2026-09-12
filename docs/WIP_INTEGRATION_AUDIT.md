# WIP Integration Audit

记录 `origin/master`（稳定基线）与 `origin/backup-unintegrated-wip`
之间的事实差异，全部内容基于逐行 diff 核实，不是推测。整合完成后
本文件可以归档，不需要长期维护——下方原始分支状态和 diff 统计保留为
整合前的事实快照；功能地图和遗留问题已在 Phase 1-7 完成后更新为当前状态。

## 分支状态（核实于本次整合发起时）

```
origin/master                  = 7ce4190 "fixing the searching function"
origin/backup-unintegrated-wip = 59f7db6 "wip: snapshot of unintegrated features"
                                  （= master 之上仅多这一个 commit）
```

因为是单个 commit，无法用 `git cherry-pick` 按功能挑选，只能按
文件/代码块级别拆分整合。

## Diff 统计

```
 EXTRACTOR.md          | 412 行（新文档）
 FIX_URL_VALIDATION.md | 203 行（新文档，描述与实际代码不一致）
 INTERACTIVE_MODE.md   | 289 行（新文档）
 OPTIMIZATION.md       | 227 行（新文档）
 README.md             | 195 行（新文档）
 agent/browser.py      |  37 行改动
 agent/extractor.py    |  73 行（新文件）
 agent/matcher.py      | 245 行改动
 agent/vision.py       |   2 行改动
 data/resume.md        |   2 行改动（仅缺失末尾换行，无内容变化）
 main.py               | 242 行改动
 requirements.txt      |   1 行新增
```

## 功能地图

| 功能 | 涉及文件 | 状态 |
|---|---|---|
| 多简历加载 + 五维评分 | `requirements.txt`（新增 python-docx）、`main.py`（`_load_multiple_resumes`/`_read_docx_async`）、`agent/matcher.py`（`resume_texts` 参数） | 已整合（Phase 1/5/6a），`tests/test_main.py` 覆盖多字段保存；简历文本当前静默截断到 2000 字符 |
| 单次推理优化 | `agent/matcher.py`（`score_job`/`_parse_json`） | 已核实，`weighted_score` 真实存在并优先于 `score` |
| 交互式多次搜索 | `main.py`（`run()` 循环、`_show_help`） | 已整合（Phase 6b），支持继续/帮助/退出、LinkedIn URL fallback 和列表等待降级；无跨轮次去重逻辑，见下方"已知遗留问题" |
| extractor 集成 | 新增 `agent/extractor.py`，`agent/browser.py`（`get_job_detail_text`/`get_job_url`），`main.py`（`_crawl_and_score`） | 已核实 |
| URL 校验修复 | `agent/extractor.py`、`tests/test_extractor.py`、`FIX_URL_VALIDATION.md` | 已整合（Phase 3）；采用正向匹配，文档已同步，覆盖标准 URL、currentJobId、非岗位 URL 和多个兜底链接行为 |
| 视觉模型超时 | `agent/vision.py` | 120s → 300s，改动极小 |
| 浏览器 profile 可配置 | `agent/browser.py` | 新增 `CAREER_AGENT_PROFILE_DIR` 环境变量覆盖 |

## 已修复的问题

**main.py 丢弃 matcher 计算出的三个字段**：

# Phase 6a 修复前的代码片段：
```python
score = float(match.get("score", 5))
reason = str(match.get("reason", "解析失败"))
```

`self.jobs.append()`（第282-294行）保存的字典只有 `score`/`reason`，
`matcher.score_job()` 实际计算出的 `selected_resume`/
`dimension_scores`/`analysis` 三个字段从未进入最终保存的 JSON。
五维评分这个功能曾经"算了但没存"，现已在 Phase 6a 修复；当前保存
记录包含 `selected_resume`、`dimension_scores`、`analysis`，并由
`tests/test_main.py` 的 fake matcher 回归测试验证。对应提交为 `701c7af`。

## 已知遗留问题（整合完成后再排期，不要在当前整合过程中顺手修）

- **交互式多轮搜索没有跨轮次去重**：`run()` 每轮 `self.jobs.clear()`
  后重新搜索评分，同一岗位若在连续几轮里重复出现，会被重复截图/
  提取/调用一次 Ollama 评分，且 `_save()` 每轮生成独立时间戳文件，
  没有合并或去重机制。
- **失败兜底与真实低分在最终数据里无法区分**：所有异常路径统一
  返回 `{"score": 5, "reason": "..."}`，和模型认真评估后打5分的
  记录长得一样，无法靠 `score` 字段区分"失败样本"和"真实低分"。
- **`extract_description()` 末两个兜底选择器（`article`、
  `[role="main"]`）较宽泛**，可能连带抓到导航栏/侧边栏噪声，只要
  长度 >= 100 就会被当作有效描述返回，尚未验证实际触发频率。
- **简历截断到 2000 字符**，对详细简历可能过于激进，具体是否需要
  调整取决于实际简历长度和评分质量的观察结果。
