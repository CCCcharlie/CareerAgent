# DOM 列表提取迁移 —— Runsheet

> **当前进度（2026-09-14）**：Step A.3 开发和自动 Search smoke 已完成，
> 按决策门 B 收尾：Vision 7，DOM resolved 3 / skipped 4，正确点击 3、
> 错误点击 0；detail 成功 0 / 失败 3。下一步 Step A.4 = detail load /
> extractor timing。点击 resolver 保持本轮实现，不继续堆匹配 heuristic。
> 本轮不进入 Step 0~6 / A.4。施工基线是 feature/integrate-wip 的
> d5100fe，fetch 后落后 0 / 领先 2，无未知生产代码修改。
> 本标准路径文档基于现有 DOM_EXTRACTION_RUNSHEET (2).md 整理，原文件保留。

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

## Step 0：选择器侦察

对应 `DOM_EXTRACTION_PLAN.md` 第3节。人工需要做的事：正常启动
程序，等终端提示"请手动完成搜索"时手动搜一次、回车继续——不需要
额外的登录操作，`data/chrome_profile`已保留登录态。

给Codex的指令：

```
请阅读 docs/DOM_EXTRACTION_PLAN.md 第3节"阶段0：选择器侦察"，
按其中描述的方法执行（写临时调试脚本，不提交，侦察完整卡片HTML
结构和分页区域结构）。

补充要求（Plan写的时候还不知道的新情况）：这次侦察时顺手确认
Step A.3诊断中提到的两件事：卡片是否带job id类属性、列表区和
详情区在DOM语义（role/标签）上如何区分。结果一律写入文件（比如
docs/debug/dom_snapshot.html），不要打印到终端。
```

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

验证：`pytest tests/test_extractor.py` + `verify.py`。单独commit。

---

## Step 2：browser.py 加薄封装

对应 `DOM_EXTRACTION_PLAN.md` 第4节后半（`browser.py`的薄封装
职责划分）。

```
请阅读 docs/DOM_EXTRACTION_PLAN.md 第4节关于browser.py部分，新增
两个薄封装方法，调用Step 1新增的extractor方法，异常处理参照现有
get_job_detail_text()/get_job_url()的做法。
```

验证：`py_compile` + import检查 + `verify.py`。单独commit。

---

## Step 3：config.yaml 加开关

对应 `DOM_EXTRACTION_PLAN.md` 第5节。

```
请阅读 docs/DOM_EXTRACTION_PLAN.md 第5节，按其中的yaml结构新增
extraction.job_list_mode开关，默认值先保持"vision"不改变现有行为。
```

验证：`verify.py`的config解析检查。可以和Step 4合并commit。

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

验证：`pytest tests/`全量 + `verify.py`。单独commit。

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
- Step A.3是当前最高优先级，Step 0~6在A.3验证通过、成功率有实质
  改善之后再继续，不要在坐标/点击问题没解决之前开始完整列表迁移
