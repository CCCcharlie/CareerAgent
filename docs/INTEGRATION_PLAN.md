# INTEGRATION_PLAN

> **当前进度**：Phase 1-6a 已完成，下一步 Phase 6b（请在每次 Phase 完成并 commit 后手动更新这一行，例如"Phase 1-4 已完成，下一步 Phase 5"，不需要为此单独建文件）

---

你现在是 CareerAgent 仓库的"增量整合与稳定性修复 Agent"。

本指令基于对 origin/master 与 origin/backup-unintegrated-wip 两个分支的
逐行 diff 核实结果编写，文中标注【已核实】的部分已经过人工确认，
不需要你重新判断真伪；标注【待你验证】的部分需要你在执行时用命令确认。

============================================================
一、仓库位置与基线【已核实】
============================================================

实际 Git 仓库：C:\Users\04268\Downloads\AgentWork\job-agent
远程仓库：https://github.com/CCCcharlie/CareerAgent.git

分支状态：

origin/master = 7ce4190（稳定基线，可正常运行）
origin/backup-unintegrated-wip = 59f7db6（= master 之上仅多一个
  "wip: snapshot of unintegrated features" commit，包含全部未整合改动）

两分支差异统计：

 EXTRACTOR.md          | 412 行（新文档）
 FIX_URL_VALIDATION.md | 203 行（新文档，描述与实际代码不一致，见十一节）
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

由于 backup-unintegrated-wip 只是单个 commit，无法用 git cherry-pick
按功能挑选，必须按文件/代码块级别整合，这是本指令按 Phase 拆分的原因。

============================================================
二、绝对禁止事项
============================================================

任何情况下都禁止：

git reset / git reset --hard / git checkout -- / git clean /
git restore . / git restore --source / 任何形式的强制覆盖工作区 /
任何形式的批量删除工作区文件

禁止：

- 整体重写 main.py 或 agent/matcher.py
- 用 origin/master 直接覆盖当前文件
- 删除当前未提交功能后重新实现
- 为了通过测试而删除已有功能
- 修改 config.yaml 中用户配置
- 删除 output/ 或浏览器 profile
- push、创建 PR、修改远程仓库

如果发现当前工作区与本任务描述不一致：STOP，先报告，不要自行猜测。

============================================================
三、最重要的开发原则
============================================================

STABLE BASELINE + USER WIP → SAFE INTEGRATION

Existing code > new code / Existing capability > new module /
Minimal patch > rewrite / Tested behavior > documentation claim /
Source code + tests > feature documentation

如果已有模块已经拥有某项能力：禁止创建第二套实现（例如不要新建
browser_manager_v2.py 之类的平行实现）。

============================================================
四、准备阶段：建立隔离分支【已核实的操作步骤】
============================================================

不要在 backup-unintegrated-wip 或 master 分支上直接工作。执行：

git checkout master
git pull origin master
git checkout -b feature/integrate-wip
git cherry-pick -n origin/backup-unintegrated-wip

最后一步会把 backup-unintegrated-wip 的全部改动以"未提交修改"的形式
应用到当前工作区（-n 表示 no-commit），效果等价于本地未提交的 WIP，
但工作在一个干净的新分支上，master 不受影响。

执行后运行：

git status --short

确认显示的文件列表与本文档第一节的 diff --stat 一致（六个已修改文件 +
六个新文件，且 data/resume.md 只有末尾换行差异）。如有出入，STOP 并报告。

============================================================
五、整合顺序
============================================================

Phase 1  requirements.txt
Phase 2  agent/vision.py
Phase 3  agent/extractor.py + FIX_URL_VALIDATION.md 文档修正
Phase 4  agent/browser.py
Phase 5  agent/matcher.py
Phase 6a main.py — 多简历加载 + extractor 接入 + 补全丢失字段（重点）
Phase 6b main.py — 交互式搜索循环
Phase 7  data/resume.md whitespace cleanup

Phase 6a 与 6b 必须分别验证、分别提交，不得合并为同一个 commit。

每个 Phase 完成并且 commit 之后，停下来等待人工确认，不要自动继续
下一个 Phase。

============================================================
六、Phase 1  DOCX Resume Dependency
============================================================

目标：保留 python-docx==1.1.0，不要加入 trafilatura（extractor 的
真实实现不依赖它，见 Phase 3）。

验证：

python -m pip install -r requirements.txt
python -m pip check
python -c "import docx; print(docx.__version__)"

提交：只暂存 requirements.txt
feat: add docx resume dependency

============================================================
七、Phase 2  Vision Timeout【已核实：改动极小】
============================================================

真实改动只有一行：AsyncClient timeout 从 120 改为 300，其余请求结构、
JSON 解析、异常处理完全未变。

验证：
python -m py_compile agent/vision.py

提交：只暂存 agent/vision.py
fix: extend local vision request timeout

============================================================
八、Phase 3  Extractor【已核实：实现思路与文档不同，但功能基本达标】
============================================================

【已核实】agent/extractor.py 的真实实现是"正向匹配"而非文档
FIX_URL_VALIDATION.md 描述的"黑名单拦截"：

- extract_url() 从候选列表（page.url / meta og:url / canonical link /
  页面中 a[href*="/jobs/view/"] 链接）里用正则
  r"/jobs/view/(\d+)|currentJobId=(\d+)" 提取岗位 ID，提取不到就返回 None
- 因为非岗位页面（/feed/、/in/、/messaging/ 等）的 URL 本身不含这个
  ID 特征，天然会被拒绝，不需要额外写黑名单
- extract_description() 用固定 selector 列表逐个尝试，成功后要求
  长度 >= 100 才返回，不使用 body.inner_text() 作为默认成功路径

【待你验证的真实风险点】extract_url() 的候选列表最后一项是宽泛的
`a[href*="/jobs/view/"]`——如果当前页面 URL 本身不含岗位 ID
（走到这层兜底），而页面上存在"相似岗位推荐"一类同样含
`/jobs/view/` 的侧边栏链接，有可能提取到错误的（非当前岗位的）URL。
必须为这个边界情况补充一条测试用例。

任务：

1. 不要重写 extractor.py 的核心逻辑（它已经工作），只做以下两件事：
   a. 补充单元测试，覆盖：
      - 标准 /jobs/view/123456/ → 返回规范化 URL
      - ?currentJobId=123456 → 返回规范化 URL
      - /jobs/preferences/、/in/someone/、/feed/ → 返回 None
      - 【新增边界测试】page.url 不含 ID，但页面存在多个
        a[href*="/jobs/view/"] 元素时，明确记录当前行为（返回第一个
        匹配还是全部尝试），如果测试暴露了"可能提取到错误岗位"的
        实际风险，将 a[href*="/jobs/view/"] 这个兜底选择器的优先级
        调整为最低，或要求其只在 page.url、og:url、canonical 均未
        命中时才使用（当前实现已经是这个顺序，只需用测试确认，
        不需要改代码顺序，除非测试证明顺序有问题）
   b. 修正 EXTRACTOR.md 和 FIX_URL_VALIDATION.md 的描述，使其准确
      反映"正向匹配 + 无黑名单"这个真实实现，删除文档中关于
      Trafilatura、四级 fallback、_validate_page_url() 的不实描述

2. 测试文件放在 tests/ 下，使用轻量 fake page 对象（不启动真实浏览器）。

验证：

python -c "import agent.extractor; print('extractor import ok')"
运行新增的 extractor 单元测试

提交：暂存 agent/extractor.py（如有小改动）、EXTRACTOR.md、
FIX_URL_VALIDATION.md、测试文件
docs: align extractor documentation with actual URL-matching behavior (EXTRACTOR.md, FIX_URL_VALIDATION.md)

============================================================
九、Phase 4  Browser Integration【已核实：改动干净，风险低】
============================================================

【已核实】agent/browser.py 的真实改动只有三处，且已经写对：

1. PROFILE_DIR 改为 os.getenv("CAREER_AGENT_PROFILE_DIR", 原硬编码路径)
   ——环境变量覆盖 + 默认值兜底，两处 launch_persistent_context 调用
   本身未被触碰
2. 新增 get_job_detail_text()：无 page 时抛 RuntimeError，extractor
   异常已经用 try/except 包裹并安全降级返回空字符串
3. 新增 get_job_url()：无 page 时返回 None，extractor 异常同样已经
   被捕获并返回 None

这个文件基本不需要"整合"，只需要确认它能正常 import、且没有破坏
两处 launch_persistent_context 的参数（user_data_dir / channel /
headless / args / viewport / locale / user_agent）。

验证：

python -m py_compile agent/browser.py
python -c "import agent.browser, agent.extractor; print('browser import ok')"

提交：只暂存 agent/browser.py
feat: integrate job extractor with browser

============================================================
十、Phase 5  Matcher【已核实：weighted_score 字段真实存在】
============================================================

这是高风险功能，不要整体重写 agent/matcher.py。

【已核实，不需要再验证真伪】

- ResumeMatcher.__init__ 真实签名：
  def __init__(self, resume_texts: Dict[str, str], base_url: str, model: str) -> None
- score_job() 用 XML 包装全部简历（<resume id="...">...</resume>），
  单次 Ollama 调用完成"选择简历 + 五维评分"
- _parse_json() 的兜底优先级已经在真实代码中确认为：
  weighted_score = parsed.get("weighted_score")
  score_source = weighted_score if weighted_score is not None else parsed.get("score", 5)
  即 weighted_score 优先于 score，这是真实存在的逻辑，直接保留，
  不需要怀疑或重新判断
- 正常返回结构：
  {"score": float, "reason": str, "selected_resume": str,
   "dimension_scores": dict, "analysis": str}
- 异常/解析失败时的最小兼容返回：{"score": 5, "reason": "..."}
- _extract_first_json_object() 的嵌套 JSON 处理能力已保留，不要删除

任务：基于当前 diff 逐段核对以上逻辑是否完整迁移，不需要重新设计。

验证：

python -m py_compile agent/matcher.py
python -c "import agent.matcher; print('matcher import ok')"
运行 matcher parser 测试（覆盖标准JSON / fenced JSON / 前后带文本 /
非标准文本 / 非法输出 / dimension_scores非dict）

必须额外执行构造函数冒烟测试（用已核实的真实签名）：

python -c "from agent.matcher import ResumeMatcher; ResumeMatcher(resume_texts={'test':'dummy'}, base_url='http://x', model='x'); print('matcher construct ok')"

提交：暂存 agent/matcher.py、OPTIMIZATION.md、相关测试
refactor: use single-pass resume matching (OPTIMIZATION.md)

============================================================
十一、Phase 6a  main.py — 编排整合 + 修复已确认的丢字段 bug
============================================================

这是本次整合中优先级最高的修复项。

【已核实的具体 bug，位置精确】main.py 当前（WIP版本）在提取 matcher
结果时：

    score = float(match.get("score", 5))
    reason = str(match.get("reason", "解析失败"))

只取走了 score 和 reason 两个字段，随后 self.jobs.append(...) 里
保存的字典也只包含这两个字段，matcher.score_job() 实际计算出的
selected_resume / dimension_scores / analysis 三个字段在这里被直接
丢弃，从未进入最终保存的 JSON。这是一个必须修复的真实 bug，不是
可选优化。

Phase 6a 具体任务：

1. 简历加载：保留 _load_multiple_resumes() / _read_docx_async()，
   从 data/*.md、*.txt、*.docx 加载多份简历为 Dict[str, str]；
   python-docx 未安装时提示并跳过 .docx，不崩溃；data/ 下无有效
   简历时清晰返回并退出
2. JobScraper.__init__ 中 ResumeMatcher 构造调用使用 resume_texts=
   参数名（与 Phase 5 确认的签名一致）
3. _crawl_and_score() 改造：
   a. 点击岗位后调用 get_job_url() 和 get_job_detail_text()
   b. detail_text 为空或长度 <100 时跳过该岗位，跳过时保留原有的
      Escape/go_back 恢复列表页逻辑
   c. 调用 matcher.score_job()
   d. 在 match.get("score", 5) / match.get("reason", ...) 这两行
      基础上，补充提取：
        selected_resume = str(match.get("selected_resume", "unknown"))
        dimension_scores = match.get("dimension_scores", {})
        analysis = str(match.get("analysis", ""))
   e. 按 min_score 筛选
   f. self.jobs.append(...) 的字典中，在原有 description / url /
      score / reason 基础上，新增保存 selected_resume、
      dimension_scores、analysis 三个字段——这是本次修复的核心目标，
      验收标准是最终输出 JSON 的每条岗位记录必须包含这五个匹配相关
      字段，缺一不可
   g. 单岗位出错不终止整页，保留原有异常处理

4. 本阶段不改动 run() 的整体执行结构，不引入交互循环，run() 仍是
   "搜索一次 → 抓取评分 → 保存 → 结束"的原有流程，交互循环留给 6b

必须保留：config.yaml 存在性检查 / Ollama 连通性检查 / 顶层
KeyboardInterrupt 处理 / 浏览器关闭 finally 逻辑

验证：

python -m py_compile main.py agent/*.py
python -c "import agent.browser, agent.vision, agent.matcher, agent.actions, agent.extractor; print('all imports ok')"
python -c "import yaml; yaml.safe_load(open('config.yaml', encoding='utf-8')); print('config ok')"
python -c "from pathlib import Path; import asyncio; from main import _load_multiple_resumes; print(asyncio.run(_load_multiple_resumes(Path('data'))).keys())"

额外验收（针对本 Phase 修复的具体 bug）：编写一个不依赖真实浏览器/
Ollama 的单元测试，用一个 fake matcher.score_job 返回值（包含全部
五个字段），断言 _crawl_and_score 最终保存到 self.jobs 的记录里
selected_resume / dimension_scores / analysis 三个字段确实存在且
值正确传递，不是被丢弃。

如果 main.py 中"多简历加载/extractor接入/字段修复"与"交互循环"的
代码在同一个函数里物理交织、无法干净拆分：STOP 并报告"当前文件包含
无法安全拆分的混合 WIP"。

提交：
fix: preserve full match result fields (selected_resume, dimension_scores, analysis) in saved job records (README.md, OPTIMIZATION.md, EXTRACTOR.md)

============================================================
十二、Phase 6b  main.py — 交互式搜索循环
============================================================

必须在 Phase 6a 独立验证并提交完成之后才能开始。

行为：

Enter / y / yes → clear self.jobs → 下一轮搜索
q / quit / exit → 安全退出
h / help → 打印帮助，继续等待，不自动开始下一次搜索
EOFError / KeyboardInterrupt → 安全退出
浏览器进程运行期间保持开启，最终 finally 安全关闭

LinkedIn 搜索：搜索框存在用 selector；不存在且 target_url 含
linkedin.com 时用 urllib.parse.urlencode() 构建
/jobs/search/?keywords=...；非 LinkedIn 保留手动搜索 fallback。

_wait_for_job_list() 失败只能提示，不能导致程序崩溃。

【重要：自动化验证注意事项】run() 中的交互输入使用
asyncio.get_event_loop().run_in_executor(None, lambda: input(...))
实现，这意味着如果在自动化终端里直接跑 python main.py 而不提供输入，
进程会挂起等待，不代表代码有问题。做自动化冒烟测试时，应通过管道
提前提供 "q\n" 作为标准输入以便进程能正常退出，例如：

echo q | python main.py

不要因为进程"看起来卡住"就误判为代码故障。

验证：

python -m py_compile main.py
python -c "import main; print('main import ok')"

仅在 Ollama 服务可用时，运行：
echo q | python main.py

观察是否输出"✅ 阶段1：启动浏览器"后能正常响应 q 退出，不因导入、
配置、简历加载或构造参数不匹配而提前异常。如浏览器/登录/网站条件
不满足，记录实际阻塞点，不要将外部登录问题误判为代码失败。

提交：
feat: add interactive multi-search loop (INTERACTIVE_MODE.md)

============================================================
十三、Phase 7  data/resume.md
============================================================

【已核实】真实改动只是文件末尾缺少换行符，内容完全没有变化。
只需恢复末尾换行，不作为功能提交，可在最终清理提交中一并处理，
不要单独创建 commit。

============================================================
十四、每个 Phase 的验证与提交纪律
============================================================

每完成一个 Phase：
1. git diff --check
2. 该 Phase 的 targeted test
3. 相关 import / compile
4. git diff 确认没有 unrelated changes
只有全部通过才允许 commit，失败则 STOP，不进入下一 Phase。

commit 前必须 git diff / git status --short 确认 staged files；
禁止 git add . 或 git add -A，优先 git add <specific files>。

失败分类：CODE_FAILURE / ENVIRONMENT_FAILURE（如 Ollama 未启动）/
EXTERNAL_SERVICE_FAILURE（如 LinkedIn 未登录）/
USER_CONFIGURATION_FAILURE。不要为了让 main.py 跑起来而修改正确代码。

如果一个文件同时包含已验证完成的改动和其他未完成 WIP：只提交已验证
完成的相关 hunk，无法安全拆分时 STOP 报告，不强行提交。

============================================================
十五、最终验收
============================================================

git diff --check
python -m py_compile main.py agent/*.py
python -c "import agent.browser, agent.vision, agent.matcher, agent.actions, agent.extractor; print('all imports ok')"
python -c "import yaml; yaml.safe_load(open('config.yaml', encoding='utf-8')); print('config ok')"
python -m pip check
git status --short
git log --oneline origin/master..HEAD

不要 push，不要创建 PR。所有 Phase 完成后，人工在 GitHub 上开
feature/integrate-wip → master 的 PR，用 PR diff 视图做一次宏观
review（重点检查 Phase 6a 修复的字段是否在 Phase 5 的返回结构和
Phase 6a 的保存逻辑之间真正对上了），再手动合并。合并动作不交给
Codex 执行。

============================================================
十六、最终报告
============================================================

## Integration Summary

### Baseline
origin/master: <commit>

### Commits
每一个 Phase 的 <hash> / <commit message> / <files>
（Phase 6a 与 6b 必须是两个不同的 commit）

### Validation
每一个 feature：command / result
（Phase 6a 需单独列出"字段丢失 bug"修复前后的对比测试结果）

### Contract
最终 MatchResult 真实字段：
{score: float, reason: str, selected_resume: str,
 dimension_scores: dict, analysis: str}

### Extractor
说明实际支持的能力（正向匹配 job id，而非黑名单拦截）与文档修正情况，
以及边界测试（宽泛兜底选择器）的结果。

### Runtime
python main.py（用 echo q | 提供输入）：PASS / NOT RUN / BLOCKED，
BLOCKED 时准确说明原因。

### Git
最终 git status --short，确认是否还有未提交文件。

### Remaining Risks
列出 environment dependencies / external website dependencies /
unresolved architecture issues / user decisions required。
