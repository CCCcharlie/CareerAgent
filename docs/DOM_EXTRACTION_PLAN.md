# 岗位列表提取改用 DOM 选择器 —— 已完成架构说明

> **迁移状态（2026-09-15）**：Step 0~6 已完成。LinkedIn 岗位列表以
> DOM 为长期主路径；Vision 保留为语义和未适配页面 fallback，原始 Vision
> 坐标不自动用于点击。`extraction.job_list_mode` 当前默认仍为 `"vision"`，
> 等待 DOM 单页处理预算优化的观察结果。执行记录和真实 smoke 结果见
> `docs/DOM_EXTRACTION_RUNSHEET.md`。

## 0. 这个方案要解决什么，不解决什么

**已解决**：`_crawl_and_score()` 已支持从页面 DOM 精确读取本页岗位、
点击目标和数字分页，而非只能依赖截图识别。

**保留既有能力**：
- 岗位详情文本提取——A.4 已完成目标详情等待和 AboutTheJob 正文提取；
  本迁移直接复用该链路
- 点击的"拟人化程度"——`agent/actions.py` 的 `human_click(x, y)`
  完全不动，见下方"关键设计原则"
- LinkedIn 搜索本身——问题一的修复（手动搜索）已经落地，不受影响

**和 `docs/DOM_EXTRACTION_RUNSHEET.md` 的分工**：本文件是设计参考，
回答"这个功能应该长什么样"；Runsheet 回答"现在做到第几步、下一步
发什么"。Runsheet 的每个 Step 会指向本文件对应章节，不会重复这里
的内容，本文件也不需要写成可以直接转发给 Codex 的指令。

---

## 1. 关键设计原则：坐标来源换了，点击方式不换

`HumanActions.human_click(self, x: float, y: float)` 的实现（已核实
`agent/actions.py`）只接收两个浮点数坐标，内部做贝塞尔曲线鼠标移动
+随机抖动+点击，**完全不关心这两个坐标是怎么算出来的**。

改造后的坐标来源是 Playwright 元素的 `bounding_box()`：

```python
box = await element.bounding_box()
if box:
    click_x = box["x"] + box["width"] / 2
    click_y = box["y"] + box["height"] / 2
```

**一个必须注意的细节**：`bounding_box()` 只有元素在当前视口内才能
拿到有效坐标，调用前必须先 `await element.scroll_into_view_if_needed()`。

**补充说明（来自 Step A 紧急止血过程中的真实诊断）**：这条设计
原则不只是"更精确"的优化，是有实测依据的必要改动——Vision模型
给出的 `click_x/click_y` 被证实不可信（曾出现坐标数值超出压缩后
截图实际尺寸的情况），不是简单的坐标系换算问题就能修正的，详见
`docs/DOM_EXTRACTION_RUNSHEET.md` Step A 部分的完整诊断记录。

---

## 2. 最终确认的 LinkedIn DOM 语义

**这句话已被 Step A 诊断证伪，删除并更正**：实测确认
`li.jobs-search-results__list-item`、`li[data-occludable-job-id]`、
`.jobs-search-results-list__list-item`、`.job-card-container`
这四个选择器对 `query_selector_all()` **全部返回空列表**，包括在
确认页面确实是LinkedIn搜索结果页、还没做任何点击操作的情况下。

这个错误判断是怎么产生的，值得记录下来避免重蹈覆辙：
`_wait_for_job_list()` 被设计成选择器超时后静默降级（只打印警告、
不抛异常、不阻断流程），这个"优雅降级"的设计让"没有报错"被错误
理解成"选择器工作正常"，而实际上它可能从这四个选择器第一次被
写进代码开始就从未真正匹配成功过。**"没有异常"不等于"逻辑被
正确执行"**，后续任何选择器相关的验证都不能只看有没有报错，要
主动打印/确认匹配到的元素数量。

**最终结论**：Step 0 已完成侦察，不再需要重新猜测 selector。当前
LinkedIn 搜索页使用以下语义：

- list scope：`[componentkey="SearchResultsMainContent"]`
- card：scope 内 `[role="button"][componentkey^="job-card-component-ref-"]`
- identity：card `componentkey` 中 `job-card-component-ref-<id>` 的数字 ID
- pagination：`ul[data-testid="pagination-controls-list"]` 内
  `button[data-testid^="pagination-indicator-"]`；当前页为 `aria-current="true"`

右侧详情面板不在列表 scope 内。动态 class 和本节开头列出的四个旧 selector
都不能重新使用。

---

## 3. Step 0 侦察结果

侦察已由 BrowserManager 自动打开 search URL 完成，不依赖人工搜索或终端
按回车。现场确认 25 张左侧 card、稳定 component key identity、右侧详情
面板 scope 隔离，以及数字分页的 Page 2 target。完整证据与后续真实 smoke
结果保留在 Runsheet；本计划不再把侦察列为待执行前置条件。

---

## 4. 已落地的实现

### 已落地的 `extractor.py` 与 `browser.py` 职责

`UniversalJobDescriptionExtractor.extract_job_cards()` 返回 DOM 顺序的
`title`、`company`、`location`、`salary`、`job_id` 和初始 box center；没有
title 或有效 box 的 card 安全跳过。`extract_next_page_target()` 从已确认的
数字分页中选择当前页之后的最小可用页码，并在 scroll 后重取 target box。

这两个方法的内部实现放在 `extractor.py` 更合适（`extractor.py` 已经
是"DOM结构解析"这个职责的归属模块），`browser.py` 只做薄封装调用
（参考现有 `get_job_detail_text()`/`get_job_url()` 的分工方式）。

`BrowserManager.get_job_cards()` 和 `get_next_page_target()` 只作 Page 传递
和异常处理。`main.py` 在 `"dom"` mode 使用这些薄封装；每次正式岗位点击
前，按稳定 job ID 重新通过 A.3 resolver scroll 并取得当前 box，避免列表
滚动后使用 stale coordinate。翻页后的 `_wait_for_job_list()` 已改为等待确认的
scope/card 语义，不再使用旧四个 selector。

---

## 5. 当前运行模式开关

不建议直接删掉视觉识别列表这条路径，改成 `config.yaml` 里加一个
开关，方便对比调试和快速回滚：

```yaml
extraction:
  job_list_mode: "vision"   # 可选 "vision" | "dom"
```

`_crawl_and_score()` 校验该配置，非法值安全回退 `"vision"`。`"dom"` 先走
完整 DOM list path；没有可用 DOM cards 时，fallback 只允许 Vision 提供岗位
语义，再经 DOM resolver 取得真实 target。它绝不自动使用 Vision raw coordinates。
默认值仍为 `"vision"`，因为 DOM 已验证正确但单页仍达到 180 秒 smoke 预算。

---

## 6. 已完成的测试覆盖

用轻量 fake Page/fake ElementHandle 对象模拟 `query_selector_all()`
返回固定结构的假卡片，不依赖真实浏览器，覆盖：

- card 顺序、缺失字段、hidden/`bounding_box=None`、component key job ID 和
  数字分页 target
- browser 薄封装异常处理，以及 `vision`/`dom` 配置校验
- DOM 不调用 Vision 枚举、DOM 分页、无 cards/无下一页安全结束、hybrid fallback
  不使用 raw Vision coordinates、点击前重取 scroll 后 box
- A.3/A.4 的 DOM click、详情等待、selector fallback 与空正文回归

---

## 7. 已完成验证与后续观察

Step 5 在同一 search URL、profile 与单页条件下比较了两种模式：Vision 识别
3 jobs、1 correct、1 detail success、0 wrong；DOM 在 180 秒预算内处理 13 个岗位，
12 correct、12 detail success、0 wrong，并正确命中 Page 2。DOM 首轮出现的 stale
box 已修复。后续工作应独立处理 DOM performance/processing-budget optimization；
在此之前不改变默认 mode。

---

## 8. Vision 模块的后续定位

**不是被淘汰，是职责收窄**——这和 `extractor.py` 当初"URL校验用
正向匹配、宽泛选择器降级兜底"是同一种设计模式：精确方案优先，
视觉方案退到兜底位置。具体分工调整为：

- **不再负责**：岗位列表页的卡片枚举、点击坐标、翻页按钮定位
  （这些交给DOM选择器；除了"数量/顺序受截图压缩影响"这个最初
  已知的局限，Step A诊断还发现了更严重的问题——Vision给出的点击
  坐标本身可能不可信，这进一步强化了"点击坐标必须来自DOM而不是
  Vision"这个结论）

- **继续负责**：`"vision"` mode 的岗位语义能力，以及 DOM 列表不可用或
  页面尚未适配时的 semantic fallback。该 fallback 仍须经 DOM resolver 取得
  真实 card；无法定位就 skip。
- **legacy 结论**：`agent/vision.py` 可以输出 `page_type="job_detail"`，但
  `main.py` 没有独立的 `page_type == "job_detail"` branch，仅保留
  `page_type != "job_list"` 的通用停止 guard；记录但不在 migration 中删除。

上述职责已写入 `AGENTS.md`。将来可单独进行 Vision fallback consolidation：比较
main branch 的稳定 Vision 实现与当前实现，只移植必要能力，不整段回退 DOM 架构。
