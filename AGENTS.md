# CareerAgent — AI Coding Agent Development Rules

本文件是 CareerAgent 项目的持久化开发规则，供 Codex、Cursor 等 AI
coding agent 在每次会话开始时自动读取。这里记录的是长期有效的工程
规则、架构边界和质量要求。

本文件不是某一次具体任务的施工计划。任务级别的开发计划放在
`docs/INTEGRATION_PLAN.md`，WIP 与稳定版本的事实差异记录放在
`docs/WIP_INTEGRATION_AUDIT.md`，两者完成任务后可以归档，不要把
一次性施工步骤永久写进本文件。

当前进度请看 `docs/INTEGRATION_PLAN.md` 顶部的进度行，本文件不
重复记录"现在做到哪一步"这类会过期的状态信息。

---

## 1. 项目概述

CareerAgent 是一个本地运行的求职岗位检索、提取与简历匹配工具。

核心流程：Playwright 控制 Chrome 浏览招聘网站（默认 LinkedIn）→
截图交给本地 Ollama 视觉模型识别岗位列表 → 对每个岗位提取详情文本
→ 交给本地 Ollama 文本模型做多简历匹配打分 → 结果保存为 JSON 到
`output/` 目录 → 支持交互式多轮搜索。

入口文件：`main.py`（同步入口 `main()` → 异步主流程 `async_main()`）

---

## 2. AI Agent 工作规则

**开始任务前**：先看本文件 + `docs/` 下与当前任务相关的文档，不要
只依赖聊天窗口里的局部描述。

**先理解，再修改**：检查现有代码和调用关系，必要时看 `git diff` /
`git log`，再做最小范围修改。禁止在没检查现有实现的情况下直接重写
核心模块。

**最小修改原则**：优先扩展现有函数，而不是创建平行实现——不要新建
`browser_manager_v2.py` 这类文件、不要无必要更换框架或增加第三方
依赖、不要无必要改变已有 API。

---

## 3. Scope Control

每个任务必须有明确范围。例如当前任务只涉及 `agent/extractor.py`
时，默认不得顺便修改 matcher / browser / main / config / 无关文档，
除非这些修改是完成当前任务所必需的。

如果在执行过程中发现任务范围之外的问题：不要顺手修复，记录下来，
在最终报告中说明；如果确实需要扩大范围，先说明原因、等待确认。

---

## 4. 模块职责边界

| 模块 | 职责 |
|---|---|
| `agent/browser.py` | Playwright 生命周期、浏览器 context、页面导航、截图、`get_job_detail_text()`/`get_job_url()` |
| `agent/vision.py` | 调用本地视觉模型解析截图，识别岗位列表 |
| `agent/actions.py` | 拟人化鼠标点击/延迟等交互原语 |
| `agent/extractor.py` | 岗位详情文本提取 + URL 提取与规范化，供 `browser.py` 调用 |
| `agent/matcher.py` | 简历与岗位的匹配打分，输出结构化结果 |
| `main.py` | 编排以上模块：搜索 → 抓取 → 评分 → 保存 → 交互式循环 |

新增能力前先确认属于哪个已有模块、能否直接扩展现有函数。

---

## 5. 已知的架构决策（避免 agent 重新"发现"并试图推翻）

- **URL 校验采用正向匹配而非黑名单**：`agent/extractor.py` 的
  `extract_url()` 只在候选 URL 中能提取出岗位 ID
  （`/jobs/view/(\d+)` 或 `currentJobId=(\d+)`）时才返回结果，
  提取不到即返回 `None`。非岗位页面（`/feed/`、`/in/`、
  `/messaging/` 等）天然不含这个特征，因此不需要额外的黑名单。
  除非发现正向匹配漏判了某类真实场景，否则不要重写成黑名单式实现。

- **候选 URL 的优先级已经是安全的，只缺一个确认测试**：候选顺序是
  `page.url` → `og:url` → `canonical` → `a[href*="/jobs/view/"]`，
  最后这个宽泛的兜底选择器已经是优先级最低的一项，只有前三者都没
  提取到岗位 ID 时才会用到它，"可能抓到侧边栏相似岗位推荐链接"的
  风险在设计上已经降到最低，不需要调整现有顺序，只需要一条测试
  确认极端情况下不会返回错误的岗位 URL。

- **ResumeMatcher 的评分结果契约**：`score_job()` 正常返回
  `{"score": float, "reason": str, "selected_resume": str,
  "dimension_scores": dict, "analysis": str}`；解析失败时至少返回
  `{"score": float, "reason": str}`（`score` 固定在 1.0~10.0 且不
  允许是 `None` 或字符串）。`_parse_json()` 内部 `weighted_score`
  字段存在时优先于 `score` 使用。main.py 保存岗位记录时必须完整
  保留这五个字段，历史上出现过只保存 `score`/`reason` 两个字段、
  其余三个被静默丢弃的 bug（原 `main.py` 第277-278行、
  `self.jobs.append()` 的字典结构），改动 `_crawl_and_score()`
  时留意这一点。

- **简历文本会被静默截断到 2000 字符**：`ResumeMatcher.__init__`
  里 `self.resume_texts = {k: (v or "")[:2000] for k, v in
  resume_texts.items()}`，超出部分没有任何日志或警告直接丢弃。这
  是当前已知行为，不代表是最终推荐设计。修改这个限制前，先检查
  评分逻辑、token/context 成本、多简历行为，补充必要测试并明确
  记录行为变化，不要在没有明确需求的情况下擅自改。

- **多简历支持**：`ResumeMatcher.__init__` 接收
  `resume_texts: Dict[str, str]`（不是单份 `resume_text: str`），
  键为简历标识（如文件名去扩展名），值为简历全文。main.py 从
  `data/` 目录动态加载所有符合格式（`.md`/`.txt`/`.docx`）的简历
  文件，`.docx` 需要 `python-docx`，未安装时跳过该文件而不是崩溃。

- **模型输出一律视为不可信输入**：Ollama Vision Model 和 Text
  Model 的返回不保证格式正确，涉及 job title/company/location/
  URL/job ID 的视觉输出、以及涉及 score/reason/selected_resume/
  dimension_scores/analysis 的评分输出，都必须做类型、范围和字段
  校验（具体契约见上面 matcher 那条）。JSON 解析要考虑 markdown
  代码块包裹、字段缺失、类型错误、越界值等情况，解析失败时安全
  降级或明确报告错误，不得为了让程序继续运行而猜测或制造缺失数据。

---

## 6. Browser Automation 边界

Playwright 用于用户授权范围内的浏览器自动化。遇到以下情况必须
停止当前自动化流程并报告需要人工处理，不得自行尝试绕过：

- CAPTCHA
- MFA / 2FA / 登录安全验证
- 网站明确的安全挑战或其他反机器人机制

不得为了提高自动化成功率而加入 CAPTCHA bypass、MFA bypass、
fingerprint spoofing 或任何未经验证的 stealth 方案。这个项目的目标
是自动化正常用户操作流程，不是绕过网站安全机制——这一条尤其重要，
因为触发反机器人机制有可能导致真实 LinkedIn 账号被限制或封禁。

浏览器 profile 目录默认硬编码在 `agent/browser.py` 的
`PROFILE_DIR`，可通过环境变量 `CAREER_AGENT_PROFILE_DIR` 覆盖，
不要删除这个环境变量覆盖逻辑。

---

## 7. 环境依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

运行前必须满足：本地 Ollama 服务已启动（默认
`http://localhost:11434`，可在 `config.yaml` 的 `ollama.base_url`
覆盖）；`config.yaml` 中指定的 `vision_model` 和 `text_model` 已经
`ollama pull` 到本地；`data/` 目录下至少放一份支持格式的简历文件。

---

## 8. Git 工作流规则

提交前必须 `git status --short` / `git diff` / `git diff --check`
确认暂存内容。禁止 `git add .` 或 `git add -A`，除非明确确认工作区
没有其他无关的未完成改动。一个 commit 对应一个逻辑功能，不要把
多个不相关的改动压成一个大 commit。

**核心文件保护**：不要整体重写 `main.py` 或 `agent/matcher.py`——
这两个文件承载的编排逻辑和评分逻辑复杂，要求按代码块/函数级别局部
整合并逐步验证。

**禁止危险操作**：未经用户明确要求，不得执行 `git reset --hard`、
`git checkout --`、`git restore`、`git clean`，不得删除或覆盖用户
未提交的工作。

**Remote 操作**：默认不得 push、创建 PR、merge、删除分支，除非
用户明确要求。

---

## 9. 验证与 Quality Gate

`scripts/verify.py` 是最低质量门禁，每次代码修改完成后执行：

```bash
python scripts/verify.py
```

当前检查：Python 语法、模块 import（动态检测 `agent/` 下实际存在
的文件）、`config.yaml` 解析、依赖一致性；如果 `tests/` 下已有
测试文件，会自动追加 pytest 检查。

Verify Integrity：不得为了让 `verify.py` PASS 而降低验证标准或
删除已有检查项。只有以下情况允许修改 `verify.py`：新功能需要增加
自动化验证、发现 `verify.py` 本身有 bug、项目长期验证标准变化。
修改时必须在报告里说明为什么改、改了什么、是否影响已有检查。没有
必要时不要碰这个文件。

改动涉及浏览器/视觉/评分逻辑时，如果本地 Ollama 可用，额外用
`echo q | python main.py` 做一次真实冒烟测试（用 `echo q |` 提供
输入，否则交互式循环会挂起等待终端输入，不代表程序卡死）。

单元测试放在 `tests/` 下，浏览器相关测试用轻量 fake Page 对象，
不在单元测试里启动真实浏览器、依赖真实网络或依赖 Ollama 服务。

---

## 10. 任务完成标准与失败分类

一个任务只有同时满足以下条件才算完成：修改范围符合 Scope、没有
无关修改、相关测试通过、`python scripts/verify.py` 通过、
`git diff --check` 通过、没有破坏第5节列出的架构契约。

如果验证因 Ollama 未启动、LinkedIn 未登录、网络不可用、外部网站
限制而失败，必须明确报告为环境/外部服务问题，不得为了让程序"看起来
能跑"而修改本身正确的代码。

任务完成后简洁报告：改了什么 / 跑了哪些测试 / verify.py 是否通过 /
当前 branch 和 commit hash / 是否修改了 AGENTS.md 或 verify.py（及
原因）/ 还有什么遗留问题 / 下一步建议。除非用户明确要求，完成当前
任务后停止，不自动进入下一个任务。
