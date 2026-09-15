# DOM 列表提取迁移 —— Runsheet

> **当前进度（2026-09-15）**：A.3 已完成（`4a2b9d0`）：7 Vision /
> 3 correct / 0 wrong / 0 detail success / 3 detail failed。
> **A.4 已完成真实验证**：5 Vision / 3 correct / 0 wrong /
> 3 detail success / 0 detail failed，NOT_LOADED / SELECTOR_MISS / EMPTY 均为 0。
> 根因确认是已加载详情的正文 selector 未命中；按目标 ID 提取 AboutTheJob
> 正文并检查就绪状态后，正确点击后的详情成功率由 0/3 提升到 3/3。
> A.3 resolver 和 HumanActions 未改动。**Step 0 已完成侦察**：确认左侧
> SearchResultsMainContent 列表 scope、card job identity 和数字分页语义。
> **Step 1~4 已完成**：默认 Vision 路径未变，DOM 路径与安全 hybrid fallback
> 已接入。下一步为 Step 5 的人工真实对比，不自动进入。
> `docs/DOM_EXTRACTION_RUNSHEET.md` 是唯一 active Runsheet；后续开发只引用
> 此标准文件名。

---

## 本文件和 `DOM_EXTRACTION_PLAN.md` 的分工（先说明白，避免再次混淆）

- **`DOM_EXTRACTION_PLAN.md`** = 设计参考，回答"这个功能应该长
  什么样"（模块职责、函数签名、测试方式、Vision的后续定位）。这
  份文件**不是**可以直接转发给Codex的指令，是背景资料。
- **本文件** = 操作指针，回答"现在做到第几步、下一步发什么、谁来
  确认"。**本文件的每个Step原则上不重复Plan里已经写过的设计内容**，
  只写：这一步要求Codex读Plan的哪一节、这一步特有的补充要求（比如
  这次诊断中发现的、Plan写的时候还不知道的新情况）、验证方式、
  commit规范。

如果发现某个Step又开始整段重复Plan的内容，就是这个分工被打破了，
应该立刻改成"发送Plan第X节"这种指针写法，而不是重新写一遍。

---

## 关于"要不要每次都粘贴执行规则"

不需要。AGENTS.md 第2/3/9/10节已经覆盖了"先读文档当执行边界、
范围控制、不降低verify标准、只有长期判断才改AGENTS.md、完成后
停下不自动继续"这些规则，Codex 每次会话会自动读取，不需要在每个
Step的消息里重复粘贴这一整套。

发送每个Step指令时，只需要一句话起到"指路"作用：

```
现在执行 Step X（对应 docs/DOM_EXTRACTION_RUNSHEET.md），按
AGENTS.md 规矩来。
```

后面跟上该Step特有的内容（比如"读Plan第X节实现XX"）就够了。

**本文件独有、AGENTS.md不管的两件事**：
1. 完成每个Step后，记得更新本文件顶部的"当前进度"这一行——这是
   最容易被忘记的一步，之前就因为没更新导致这份文件和实际诊断
   进度脱节了好几轮，这次务必每次做完都记得改（这是"维护这份
   具体文档"的动作，不是通用规则，所以不写进AGENTS.md）
2. Step之间的执行顺序和依赖关系（比如Step A.3必须在Step 0之前，
   Step 6依赖Step 5的人工验证结果）——这个排序本身就是这份Runsheet
   存在的意义，AGENTS.md不记录任何具体任务的顺序信息

（诊断类任务不强制commit、长内容写文件不打印到终端，这两条已经
在这次更新时补进了AGENTS.md第9节，不再在这里重复。）

---

## Step A：紧急坐标修复（A.3 已按决策门 B 收尾）

这个Step不在`DOM_EXTRACTION_PLAN.md`的范围内（Plan是为完整列表
迁移写的），是真实使用中发现0%成功率之后单独加的紧急止血任务，
所以内容在本文件里独立展开，不是"重复"，是这里本来就是唯一出处。

**A.1（已完成，结论被推翻）**：最初假设"full_page截图坐标系vs
视口点击坐标系不一致"，修复为DOM反查+bounding_box，提交
`d5100fe`。真实验证0%成功，结论：假设不完整。

**A.2（已完成）**：诊断确认根因是(1)旧四个选择器全部返回0个元素
(2)Vision坐标本身不可信（superset问题：曾出现y坐标超出压缩图片
实际高度）。产出：这两条已经写进本文件顶部"当前进度"。

**A.3 (2026-09-14): DOM-confirmed job clicks + automatic Search smoke**

**执行规则（以本轮最新 A.3 指令为准）**：

施工前先同步本节，再核对本地基线：

```bash
git branch --show-current
git status --short
git log -5 --oneline
git fetch origin
git rev-list --left-right --count origin/feature/integrate-wip...HEAD
```

确认当前为 `feature/integrate-wip`，并检查 `main.py` 中的
`_resolve_job_click_coordinates()`。local HEAD 单纯领先 origin（如包含
已知的 `d5100fe`），且没有未知生产代码修改，可以继续；不要因 local ahead
停止。只有 diverged、local behind、来源不明的生产代码未提交修改，或 HEAD
与 Runsheet 明显矛盾且无法判断来源时，停止并报告。不执行 reset / restore /
checkout / merge / push。

优先复用以下已有证据及当前 `main.py`：

- `debug_dom_inspection_20260914_010241.json`
- `debug_vision_raw_20260914_010241.txt`
- `debug_vision_jobs_20260914_010241.json`

不再新增独立诊断 Step，也不把完整 DOM 快照诊断作为开发前置步骤。只快速确认
稳定 identity、列表 scope 和排除右侧重复 title 的依据；证据足够则直接实现。
仅当实现缺少必要字段时，允许自动打开 LinkedIn search URL 补一次最小 probe，
结果写文件，随后立即进入开发，不要求用户手动搜索或按回车。

- Production path: Vision jobs -> unique DOM target -> scroll -> fresh box ->
  HumanActions.human_click(). Job clicks never consume Vision click_x/click_y.
- Reuse A.2 evidence. Only missing DOM attributes were supplemented by one
  automatic probe opening the recorded search URL; no manual search or Enter.
- Real evidence: left scope `[componentkey="SearchResultsMainContent"]`;
  cards `[role="button"][componentkey^="job-card-component-ref-"]`.
  The probe found 25 unique job identities. The right detail panel is outside
  this scope. These semantic component keys replace dynamic-class assumptions.
- Identity takes precedence when supplied and valid. Otherwise normalized exact
  title in the list identifies the card, and its DOM job ID verifies navigation.
  Company is not a hard condition. Multiple matching titles ->
  AMBIGUOUS_DOM_MATCH -> skip; no occurrence, fuzzy, or geometry heuristic.
- Hidden/absent/ambiguous targets and unusable post-scroll boxes skip safely.
  After clicking, compare the target ID with the actual resulting page URL ID.
  Missing/different actual ID -> WRONG_JOB_CLICK -> skip detail/scoring.
  Do not use the extractor's broad list-link URL fallback to prove correctness.
- Required event counters: VISION_JOBS, DOM_RESOLVE_SUCCESS,
  DOM_RESOLVE_FAILED, AMBIGUOUS_DOM_MATCH, CLICKS, CORRECT_JOB,
  WRONG_JOB_CLICK, DETAIL_SUCCESS, DETAIL_FAILED.

**Automatic development validation** (project .venv Python):

```bash
python -m pytest tests/test_main.py
python scripts/verify.py
git diff --check
python scripts/real_smoke.py --search-url "<LinkedIn search URL>"
```

The harness directly opens the search URL with BrowserManager/current Chrome
profile, sets max_pages=1, and reuses production Vision, DOM resolver,
HumanActions and detail extraction. Resume scoring is disabled for this click
smoke. It never calls input(), enters production manual search, or enters the
interactive repeat loop; it closes the browser in finally. Logs, event JSON,
and before/after screenshots are saved under output/real_smoke_<timestamp>/.
Login, CAPTCHA, MFA or an explicit security challenge stops automation and is
reported as BLOCKED requiring human handling. Zero Vision jobs is ERROR, not a
successful click smoke. Production manual fallback remains available.

不得通过 comment/uncomment `main.py` 人工交互逻辑完成开发验证，也不得删除
正式用户流程的人工 fallback。独立的 `scripts/real_smoke.py` 仅作为开发验证
入口，直接 `goto(search_url)`，不调用 `input()`，最多处理一页并自动退出。

**Decision gate**:

- Correct DOM clicks and valid details: A.3 succeeds; commit and stop.
- Correct DOM clicks but many/all details fail: preserve the click resolver;
  next Step A.4 = detail load / extractor timing. Commit A.3 and stop.
- No reliable identity/list scope: stop adding bridge heuristics and recommend
  bringing full DOM Job List Extraction forward.

**本次真实验证结果**：

最终运行 `output/real_smoke_20260914_180828/`：状态 `COMPLETED`，进程
退出码 0，浏览器自动关闭，没有人工搜索或终端输入，没有登录/安全挑战。
`result.json` 保存每次解析、点击、实际 URL 和详情长度；`run.log` 保存
完整过程，`before.png` / `after.png` 均成功生成，无截图告警。

| 指标 | 最终一页 Search smoke |
|---|---:|
| VISION_JOBS | 7 |
| DOM_RESOLVE_SUCCESS | 3 |
| DOM_RESOLVE_FAILED | 1 |
| AMBIGUOUS_DOM_MATCH | 3 |
| DOM skipped（上两项合计） | 4 |
| CLICKS | 3 |
| CORRECT_JOB | 3 |
| WRONG_JOB_CLICK | 0 |
| DETAIL_SUCCESS | 0 |
| DETAIL_FAILED | 3 |

三次实际 URL 的 `currentJobId` 都与 DOM target ID 相同：

| title | DOM / actual job ID | DOM click center | detail length |
|---|---|---|---:|
| Software Developer | 4462913805 | (454.15, 423.06) | 0 |
| Haskell Developer (AU & NZ) | 4407747256 | (454.15, 550.18) | 0 |
| Full stack Developer | 4465493673 | (454.15, 790.40) | 0 |

`Software Engineer` 两次、`Appian Developer` 一次因 DOM 重名跳过；
`Research Developer` 无精确 title 匹配，跳过。company 没有作为硬条件。
与历史 `15/15 failed`、`22/22 failed` 相比，本轮已把点击正确性与详情
提取失败分开验证：**点击 3/3 正确，详情仍是 3/3 failed**，不宣称端到端
提取已修复。真实页面内容和 Vision 输出会变化，本次不是固定岗位样本对照。

本轮验证过程中的环境/辅助问题也保留记录：

- `180143`：Ollama 未运行，Vision 连接失败，0 次点击；随后修正 harness，
  无 Vision 岗位必须报 ERROR，不能标记为已完成点击 smoke。
- 启动本机已安装的 Ollama 后，`180328` 遇到 HTTP 500，0 次点击；随后本地
  图片请求恢复 HTTP 200，未更换模型、未修改 vision.py。
- `180513`：Vision 6，resolved 2，skip 4，正确点击 2，错误 0，detail 0/2；
  抓取完成后的截图超时使旧 harness 报 ERROR。截图现在为可选留档，超时记录
  artifact_warnings，核心 Vision/抓取异常仍报 ERROR；最终 `180828` 无此问题。
- 最小 DOM probe：`debug_a3_probe.json`，25 个唯一 card identity，明确左侧
  SearchResultsMainContent scope。原 A.2 三份证据没有改写。

验证：`pytest tests/test_main.py` **24 passed**；`scripts/verify.py` **PASS**
（含全部 **48** 项测试）；`git diff --check` **PASS**。保留 matcher 结果保存、
生产搜索人工 fallback、分页等待和 interactive loop 原有回归测试。

**决策 B：下一步 Step A.4 = detail load / extractor timing。** 本轮不新增
detail-smoke、不修改 extractor、不继续修改 click resolver。单独提交 A.3 后停止。

No Step 0 or A.4 implementation is included. AGENTS.md and verify.py are not
modified by this step. The existing user-modified AGENTS.md is preserved.

本次执行方式同步只修改本 Runsheet，不改写 `AGENTS.md` 或
`DOM_EXTRACTION_PLAN.md`。同步内容属于 A.3，与正式实现一起检查、验证并提交，
不创建独立 docs commit。

---

## Step A.4：详情加载与正文提取（已完成）

读取 BrowserManager -> extractor 调用链及点击后等待逻辑，不预设 selector
或时机是根因。自动 Search smoke 仅在 CORRECT_JOB 后记录 target title/ID、
点击前后 URL、页面 title、等待条件、每个正文 selector 的匹配数量、可见性、
innerText 长度及最终提取长度；长 JSON/HTML 写入本次 smoke 输出目录。

失败分别归类为 DETAIL_NOT_LOADED、DETAIL_SELECTOR_MISS
（DETAIL_LOADED_SELECTOR_MISS）或 DETAIL_EMPTY（DETAIL_ELEMENT_FOUND_BUT_EMPTY）。
根据真实证据修复显式 DOM 等待和/或正文 selector，不用固定 sleep 加时掩盖问题。
WRONG_JOB_CLICK 只记录，不修改 A.3。若详情已加载且 selector 正确但仍无法提取，
保存证据并停止猜测，不进入完整 DOM migration。

完成 targeted tests、verify、diff check 和自动 Search smoke 后，与 A.3 的
3 correct / 0 wrong / 0 detail success / 3 detail failed 比较，记录结果并单独
提交 A.4。保留 AGENTS.md 现有修改，不修改 matcher、Vision、actions 或 verify.py。

**已确认根因与修复**：

根因是 `DETAIL_LOADED_SELECTOR_MISS`，对应统计名 `DETAIL_SELECTOR_MISS`。
在 `output/real_smoke_20260914_182815/` 保存的真实证据中，目标
`D365 Application Developer - FinOps` 的 job ID 为 `4463596080`，
页面 title 与目标一致，`JobDetails_AboutTheJob_4463596080` 可见且容器文本
长度为 2037；旧七个正文 selector 全部匹配 0。不是依据猜测增加等待时间。

正文采用已观察到的语义 selector：

```css
[data-sdui-component="com.linkedin.sdui.generated.jobseeker.dsl.impl.aboutTheJob"] [data-testid="expandable-text-box"]
```

有 target job ID 时，限定在 `JobDetails_AboutTheJob_<id>` 内，最多等待 10 秒，
条件是实际 URL ID 正确、目标容器可见、内部正文可见且清理后不少于 100 字符。
同一次 DOM 读取返回正文，避免 URL 已切换但仍读取旧面板；超时安全失败并记录
NOT_LOADED / SELECTOR_MISS / EMPTY 分类。未确认等待不足是本次 0% 的根因，
此等待用于保证目标正文已就绪，没有新增固定 sleep。

无目标 ID 时，新正文 selector 优先，保留旧 selector 的相对 fallback 顺序；
隐藏、空和过短元素不视为成功，正文只清理行首尾空白/空行，不截断内容。
BrowserManager 传递目标 ID 并保留提取状态；main 仅扩展详情调用及分类统计。
A.3 resolver 经 AST 对比与 `4a2b9d0` 一致。

Search smoke 的详情观察钩子仅在 CORRECT_JOB 后运行，逐次保存 before/after
证据，文件名带序号避免重复岗位覆盖。该能力保留在开发 harness 中；一次性
日志/HTML/JSON 留在本地输出目录，不纳入提交，也不删除已有证据。

**已恢复的上轮结果**：`output/real_smoke_20260914_183455/result.json` 实际为
`COMPLETED`，并非抓取未完成。Vision 6，DOM resolved 1 / failed 2 / ambiguous 3，
correct 1 / wrong 0，detail success 1 / failed 0，三个详情失败分类均为 0。
`Full stack Developer`（`4465493673`）正文 4640 字符，等待未超时。
结束截图有超时告警，核心抓取和证据文件已完成，浏览器正常关闭。

**恢复后验证**：targeted tests 57 passed；verify PASS（全量 64 项测试）；
diff check PASS。恢复后未修改正式实现，继续用同一 Search smoke 验证。

**恢复后最终真实结果（2026-09-15）**：

`output/real_smoke_20260915_121142/result.json` 为 `COMPLETED`，进程退出码 0，
浏览器自动关闭。本轮使用相同 search URL、现有 Chrome profile、正式 Vision /
DOM resolver / HumanActions / extractor，max_pages=1，无人工搜索或按回车。
Ollama 原先未运行，启动已有本地服务后，本轮没有发生 HTTP 500、登录或安全挑战。

| 指标 | A.3 基线 | A.4 最终 smoke |
|---|---:|---:|
| VISION_JOBS | 7 | 5 |
| DOM_RESOLVE_SUCCESS | 3 | 3 |
| DOM_RESOLVE_FAILED | 1 | 0 |
| AMBIGUOUS_DOM_MATCH | 3 | 2 |
| CLICKS | 3 | 3 |
| CORRECT_JOB | 3 | 3 |
| WRONG_JOB_CLICK | 0 | 0 |
| DETAIL_NOT_LOADED | 未分类 | 0 |
| DETAIL_SELECTOR_MISS | 未分类 | 0 |
| DETAIL_EMPTY | 未分类 | 0 |
| DETAIL_SUCCESS | 0 | 3 |
| DETAIL_FAILED | 3 | 0 |

| 成功详情 | target / actual job ID | 完整正文字符数 | 等待超时 |
|---|---|---:|---|
| Software Developer | 4462913805 | 5719 | 否 |
| Haskell Developer (AU & NZ) | 4407747256 | 4118 | 否 |
| Associate Software Engineer | 4462553046 | 5018 | 否 |

每次正确点击都有两份带序号的 `detail_*_before_extract.json` /
`detail_*_after_extract.json`，共六份，记录 URL、目标 ID、页面 title、等待条件、
selector match count / visible / innerText length 和最终提取长度。正文读取没有
截断。结束时 `after.png` 超时 5 秒，记录为 artifact warning；该可选截图未生成，
核心结果、详情证据、run.log 和 before.png 已保存，不修改正文代码来处理截图问题。

结论：正确点击后的详情成功率由 **0/3（0%）改善到 3/3（100%）**，A.4 修复方向
已由真实 smoke 验证。两个轮次的实时岗位集合不同，样本仅一页，不推断长期全站
成功率。停止本 Step，不继续实现完整 DOM job-list migration。

最终提交范围（9 个文件）：`agent/extractor.py`、`agent/browser.py`、`main.py`、
`scripts/real_smoke.py`、`tests/test_extractor.py`、`tests/test_browser.py`、
`tests/test_main.py`、`tests/test_real_smoke.py`、本 Runsheet。原有 `AGENTS.md`
修改、用户草稿和历史/本次诊断证据均不暂存；没有待提交的一次性临时脚本。

## Step 0：选择器侦察（已完成，2026-09-15）

读取 `DOM_EXTRACTION_PLAN.md` 第3节后，以现有 BrowserManager 自动打开
已验证的 LinkedIn search URL；没有修改 `main.py` 的生产人工 fallback，
也没有要求用户手动搜索或终端按回车。临时 scout 脚本只用于本次侦察，
不提交；完整 JSON 和 HTML 写入 `docs/debug/`：

- `step0_dom_scout_20260915_124032.json`（272,904 bytes）
- `step0_dom_snapshot_20260915_124032.html`（191,194 bytes）

自动页面结果：`Software Engineer | Liberty | LinkedIn`，3 个
`data-testid="lazy-column"`，25 张左侧岗位卡片，列表分页可见。没有登录、
CAPTCHA、MFA 或安全挑战。

| 侦察项 | 现场确认结果 | 后续可用性 |
|---|---|---|
| 左侧列表 scope | `[componentkey="SearchResultsMainContent"]`，同时有 `data-testid="lazy-column"`、`data-component-type="LazyColumn"` | 可作为列表唯一 scope；不要用动态 class |
| 岗位卡片 | scope 内 `[role="button"][componentkey^="job-card-component-ref-"]` | 25 个匹配；可作为 card selector |
| 稳定 identity | card `componentkey="job-card-component-ref-<digits>"`，例如 `job-card-component-ref-4460945256` | 从固定前缀后的数字取得 job ID；未见 `data-job-id` 或 `data-occludable-job-id` |
| 列表与右侧详情区分 | 右侧也有 LazyColumn，但没有 `componentkey="SearchResultsMainContent"`，且该 scope 外没有匹配的 card selector | 用列表 scope 隔离，不依赖像素位置；本页没有可靠 list/listitem role 语义 |
| card 字段 | 可见 `p` 顺序是 title、company、location，之后是可选社交/状态/发布时间；薪资仅在部分卡片文本出现 | class 都是动态；没有确认稳定的独立 title/company/location/salary selector，Step 1 应在已确认 card scope 内解析文本/结构，不能猜 class |
| 分页容器 | `ul[data-testid="pagination-controls-list"]`，位于列表 scope 内 | 可作为分页范围 |
| 分页目标 | 数字按钮为 `button[data-testid^="pagination-indicator-"]`，当前页有 `aria-current="true"`、例如 `aria-label="Page 1"`；其余为 `aria-current="false"`、`Page 2` / `Page 3` | 本页没有独立 Next 按钮。下一页需从该范围选择当前页后的数字按钮，不要假设 `button[aria-label*="Next"]` |

旧四个已证伪 selector 没有被采用。该结果只是 Step 1 的现场输入，不实现
`extract_job_cards` 或分页逻辑；完成本 Step 后停止。

---

## Step 1：extractor.py 新增列表解析能力

对应 `DOM_EXTRACTION_PLAN.md` 第4节前半（`extract_job_cards`/
`extract_next_page_target`的设计）。

```
请阅读 docs/DOM_EXTRACTION_PLAN.md 第4节，在 agent/extractor.py
中按其中的函数签名实现，selector以Step 0侦察结果为准，不要用
Plan文档里的示例selector。配套单测参照Plan第6节的覆盖要求写在
tests/test_extractor.py。
```

完成（2026-09-15）：

- `extract_job_cards()` 只在唯一的
  `[componentkey="SearchResultsMainContent"]` scope 内读取
  `[role="button"][componentkey^="job-card-component-ref-"]`。它按已确认的
  `p` 文本顺序取得 title/company/location，从 `componentkey` 提取 job ID，并只对
  有有效 bounding box 的 card 返回中心坐标；没有 title 的 card 跳过，缺少可选字段
  返回空字符串。
- `extract_next_page_target()` 只在 scope 内的
  `ul[data-testid="pagination-controls-list"]` 查找
  `button[data-testid^="pagination-indicator-"]`，从 `aria-current="true"` 的
  页码选择下一个可用数字按钮。不存在独立 Next 按钮的假设，也没有采用动态 class。
  滚动目标后重新取得 bounding box。
- 单测覆盖多 card 顺序、identity 缺失、title/salary 缺失、隐藏 card、唯一 scope、
  下一个数字页、无分页/无当前页/禁用目标等安全返回。

验证：`pytest tests/test_extractor.py` **28 passed**；`python scripts/verify.py`
**PASS**；`git diff --check` **PASS**。单独 commit 后停止，不进入 Step 2。

---

## Step 2：browser.py 加薄封装

对应 `DOM_EXTRACTION_PLAN.md` 第4节后半（`browser.py`的薄封装
职责划分）。

```
请阅读 docs/DOM_EXTRACTION_PLAN.md 第4节关于browser.py部分，新增
两个薄封装方法，调用Step 1新增的extractor方法，异常处理参照现有
get_job_detail_text()/get_job_url()的做法。
```

完成（2026-09-15）：

- `BrowserManager.get_job_cards()` 只向当前 `Page` 创建
  `UniversalJobDescriptionExtractor` 并转调 `extract_job_cards()`；没有 page 或
  extractor 异常时返回空列表。
- `BrowserManager.get_next_page_target()` 对应转调
  `extract_next_page_target()`；没有 page 或异常时返回 `None`。
- browser 层没有新增 selector、DOM 解析或 main/Vision/HumanActions 改动。

验证：`pytest tests/test_browser.py` **5 passed**；`python -X utf8 scripts/verify.py`
**PASS**；`git diff --check` **PASS**。单独 commit 后停止，不进入 Step 3。

---

## Step 3：config.yaml 加开关

对应 `DOM_EXTRACTION_PLAN.md` 第5节。

```
请阅读 docs/DOM_EXTRACTION_PLAN.md 第5节，按其中的yaml结构新增
extraction.job_list_mode开关，默认值先保持"vision"不改变现有行为。
```

完成（2026-09-15）：

- `config.yaml` 新增 `extraction.job_list_mode: "vision"`，默认行为不变。
- 配置测试将该字段限制为 `"vision"` 或 `"dom"`，并确认默认值是
  `"vision"`。当前没有修改 `main.py`，因此没有接入 DOM 路径。

验证：`pytest tests/test_config.py` **2 passed**；`python -X utf8 scripts/verify.py`
**PASS**；`git diff --check` **PASS**。可与 Step 4 合并 commit，完成本 Step 后停止。

---

## Step 4：main.py 接入开关

对应 `DOM_EXTRACTION_PLAN.md` 第4节"main.py的_crawl_and_score()
改造"部分。

```
请阅读 docs/DOM_EXTRACTION_PLAN.md 第4节main.py部分，按
extraction.job_list_mode接入两条路径。同时补上点击详情后的显式
等待（_wait_for_job_detail()，具体selector以Step 0侦察结果为准，
Plan文档里没有这部分，是这次排障新发现的缺口，需要新写）。
```

完成（2026-09-15）：

- `main.py` 读取 `extraction.job_list_mode`。缺失或非法值安全地按
  `"vision"` 处理，因此默认生产路径保持原行为。
- `"dom"` 模式直接将 `BrowserManager.get_job_cards()` 返回的 card job ID 与
  bounding-box 中心坐标送进既有 HumanActions、详情提取和评分流程；不重新实现
  A.4 的详情等待。
- DOM 无可用 card 时，才调用 Vision 取得岗位语义，并复用 A.3 resolver 在真实
  card 上取得 DOM 坐标。该 fallback 不会使用 Vision 的 `click_x` / `click_y`。
- DOM 模式翻页只调用 `get_next_page_target()`；点击后继续用已确认的
  `SearchResultsMainContent` / card selector 等待列表，不采用旧四个 selector。

验证：`pytest tests/` **PASS**；`python -X utf8 scripts/verify.py` **PASS**；
`git diff --check` **PASS**。Step 3 与 Step 4 合并 commit 后停止，不进入 Step 5。

---

## Step 5：本地对比测试

对应 `DOM_EXTRACTION_PLAN.md` 第7节第5步。这一步是人工真实体验
验证，不涉及自动化测试，不需要给Codex发指令模板，直接把
`job_list_mode`改成`"dom"`本地跑几轮，参照Plan第7节列的对比项。

---

## Step 6：收尾

对应 `DOM_EXTRACTION_PLAN.md` 第7节第6步 + 第8节（Vision定位更新）。

```
确认DOM模式稳定后，请阅读 docs/DOM_EXTRACTION_PLAN.md 第8节，
按其中描述更新AGENTS.md第4节里agent/vision.py的职责说明；同时
判断page_type=="job_detail"分支是否已成死代码，记录但不清理。
```

---

## 每一步的共同纪律

- 先读现有代码/AGENTS.md，只读审查在前，改动在后
- 每步验证：`pytest` → `verify.py` → `git diff --check` → 单独
  commit
- A.3 已完成；A.4 单独验证并提交后停止，不自动进入 Step 0~6 的完整列表迁移。
