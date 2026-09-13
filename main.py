import asyncio
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import yaml

from agent.actions import HumanActions
from agent.browser import BrowserManager
from agent.matcher import ResumeMatcher
from agent.vision import LocalVisionAPI


class JobScraper:
    """岗位爬取主控类：编排浏览、识别、评分与结果保存。"""

    def __init__(self, config: Dict[str, Any], resume_texts: Dict[str, str], base_dir: Path) -> None:
        """加载配置并初始化各功能模块。

        Args:
            config: 配置字典
            resume_texts: 多份简历文本，键为简历标识，值为简历内容
            base_dir: 项目根目录
        """
        self.config = config
        self.resume_texts = resume_texts
        self.base_dir = base_dir
        self.jobs: List[Dict[str, Any]] = []

        behavior = self.config.get("behavior", {})
        ollama = self.config.get("ollama", {})

        self.browser = BrowserManager(headless=bool(behavior.get("headless", False)))
        self.vision = LocalVisionAPI(
            base_url=str(ollama.get("base_url", "http://localhost:11434")),
            model=str(ollama.get("vision_model", "minicpm-v:8b-2.6-q4_K_M")),
        )
        self.matcher = ResumeMatcher(
            resume_texts=self.resume_texts,
            base_url=str(ollama.get("base_url", "http://localhost:11434")),
            model=str(ollama.get("text_model", "qwen3.5:9b")),
        )
        self.actions: Optional[HumanActions] = None

    async def run(self) -> None:
        """执行完整爬取流程（支持交互式多次搜索）。"""
        try:
            print("✅ 阶段1：启动浏览器")
            page = await self.browser.start()
            behavior = self.config.get("behavior", {})
            self.actions = HumanActions(
                page=page,
                min_delay=float(behavior.get("delay_min", 2)),
                max_delay=float(behavior.get("delay_max", 6)),
            )

            # 交互式循环：支持多次搜索
            search_count = 0
            while True:
                search_count += 1
                print(f"\n{'='*60}")
                print(f"🔍 第 {search_count} 次搜索")
                print(f"{'='*60}")

                print("\n🔍 阶段2：搜索岗位")
                await self._search_jobs(page)

                print("\n📊 阶段3：爬取并评分")
                await self._crawl_and_score(page)

                output_file = await self._save()
                self._print_top10()
                print(f"\n📁 结果已保存：{output_file}")

                # 询问用户是否继续
                print(f"\n{'='*60}")
                print("ℹ️  浏览器保持开启状态")
                print("="*60)
                print("\n请选择下一步操作：")
                print("  1. 继续搜索（输入回车或 'y'）")
                print("  2. 退出程序（输入 'q' 或 'quit'）")
                print("  3. 查看帮助（输入 'h' 或 'help'）")

                try:
                    # 使用 asyncio 的非阻塞输入
                    user_input = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: input("\n👉 请输入选择: ").strip().lower()
                    )

                    if user_input in ['q', 'quit', 'exit']:
                        print("\n👋 感谢使用，再见！")
                        break
                    elif user_input in ['h', 'help']:
                        self._show_help()
                        continue
                    else:
                        # 默认继续搜索
                        print("\n🔄 开始新的搜索...")
                        # 清空当前搜索结果，准备下一轮
                        self.jobs.clear()
                        continue

                except EOFError:
                    # 处理管道输入或 Ctrl+D
                    print("\n⚠️ 输入结束，退出程序")
                    break
                except KeyboardInterrupt:
                    print("\n⚠️ 用户中断")
                    break

        except Exception:
            print(f"\n❌ 程序发生未处理异常：")
            traceback.print_exc()
        finally:
            await self.browser.close()

    def _show_help(self) -> None:
        """显示帮助信息。"""
        help_text = """
╔═══════════════════════════════════════════════════════════╗
║                   📖 使用帮助                             ║
╠═══════════════════════════════════════════════════════════╣
║                                                           ║
║  🎯 功能说明：                                             ║
║  • 自动搜索 LinkedIn 岗位                                 ║
║  • AI 智能匹配简历                                        ║
║  • 多维度评分（技术/经验/项目/薪资/潜力）                  ║
║  • 保存结果到 JSON 文件                                   ║
║                                                           ║
║  ⌨️  快捷操作：                                            ║
║  • 直接回车  → 继续下一次搜索                             ║
║  • y / yes   → 继续搜索                                   ║
║  • q / quit  → 退出程序                                   ║
║  • h / help  → 显示此帮助                                 ║
║  • Ctrl+C    → 中断当前操作                               ║
║                                                           ║
║  📁 输出文件：                                             ║
║  • 位置：output/ 目录                                     ║
║  • 格式：jobs_YYYYMMDD_HHMMSS.json                        ║
║  • 内容：岗位详情 + 匹配分数 + 维度分析                    ║
║                                                           ║
║  🔧 配置修改：                                             ║
║  • 编辑 config.yaml 调整搜索关键词                         ║
║  • 修改 data/ 目录下的简历文件                            ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
        """
        print(help_text)

    async def _search_jobs(self, page) -> None:
        """打开目标站点并执行关键词搜索。"""
        target_url = self.config.get("target", {}).get(
            "url", "https://www.zhipin.com/web/geek/job"
        )
        keywords = self.config.get("search", {}).get("keywords", [])
        query = " ".join([str(k).strip() for k in keywords if str(k).strip()])

        print(f"🔍 打开目标网站：{target_url}")
        await page.goto(target_url, wait_until="domcontentloaded", timeout=90000)
        await asyncio.sleep(2)

        if "linkedin.com" in target_url:
            print("⚠️ LinkedIn 请手动在浏览器中完成搜索。")
            await asyncio.to_thread(input, "完成后请在终端按回车继续...")
            await self._wait_for_job_list(page)
            return

        selectors = [
            'input[placeholder*="搜索"]',
            'input[name*="query"]',
            'input[name*="keyword"]',
            'input[aria-label*="Search by title"]',
            'input[aria-label*="Search jobs"]',
            'input[placeholder*="Search by title"]',
            'input[id*="jobs-search-box-keyword"]',
        ]
        search_input = None
        for sel in selectors:
            try:
                candidate = await page.query_selector(sel)
                if candidate:
                    search_input = candidate
                    break
            except Exception:
                continue

        if search_input and query:
            await search_input.click()
            await search_input.fill(query)
            await page.keyboard.press("Enter")
            print(f"✅ 已自动搜索：{query}")
            await asyncio.sleep(4)
            await self._wait_for_job_list(page)
            return

        print("⚠️ 自动搜索失败，请手动在浏览器中完成搜索。")
        await asyncio.to_thread(input, "完成后请在终端按回车继续...")
        await self._wait_for_job_list(page)

    async def _wait_for_job_list(self, page) -> None:
        """等待岗位列表区域出现，降低过早截图导致的识别失败。"""
        list_selectors = [
            "li.jobs-search-results__list-item",
            "li[data-occludable-job-id]",
            ".jobs-search-results-list__list-item",
            ".job-card-container",
        ]
        for selector in list_selectors:
            try:
                await page.wait_for_selector(selector, timeout=8000)
                return
            except Exception:
                continue
        print("⚠️ 未检测到明确岗位列表，后续将继续尝试视觉识别。")

    async def _resolve_job_click_coordinates(
        self, page, title: str, fallback_x: float, fallback_y: float
    ) -> tuple[float, float]:
        """优先用岗位卡片的视口坐标点击，失败时回退视觉坐标。"""
        if not title:
            return fallback_x, fallback_y

        list_selectors = [
            "li.jobs-search-results__list-item",
            "li[data-occludable-job-id]",
            ".jobs-search-results-list__list-item",
            ".job-card-container",
        ]
        for selector in list_selectors:
            try:
                cards = await page.query_selector_all(selector)
            except Exception:
                continue

            for card in cards:
                try:
                    card_text = (await card.inner_text()).strip()
                    if title not in card_text:
                        continue
                    await card.scroll_into_view_if_needed()
                    box = await card.bounding_box()
                    if box:
                        return (
                            float(box["x"] + box["width"] / 2),
                            float(box["y"] + box["height"] / 2),
                        )
                except Exception:
                    continue

        return fallback_x, fallback_y

    async def _crawl_and_score(self, page) -> None:
        """按页循环抓取岗位并进行匹配评分。"""
        max_pages = int(self.config.get("search", {}).get("max_pages", 5))
        min_score = float(self.config.get("match", {}).get("min_score", 6))
        assert self.actions is not None

        for page_index in range(1, max_pages + 1):
            print(f"📊 正在处理第 {page_index}/{max_pages} 页")
            screenshot_bytes = await self.browser.screenshot()
            _ = await self.browser.get_page_text()
            vision_result = await self.vision.analyze_page(
                screenshot_bytes, f"请分析第{page_index}页招聘结果并提取岗位列表"
            )
            page_type = vision_result.get("page_type")
            if page_type != "job_list":
                print(f"⚠️ 当前页面类型为 {page_type}，停止翻页。")
                break

            jobs = vision_result.get("jobs", []) or []
            if not jobs:
                print("⚠️ 本页未识别到岗位。")

            for idx, job in enumerate(jobs, start=1):
                title = str(job.get("title", "")).strip()
                company = str(job.get("company", "")).strip()
                salary = str(job.get("salary", "")).strip()
                location = str(job.get("location", "")).strip()
                tags = job.get("tags", [])
                click_x = job.get("click_x")
                click_y = job.get("click_y")
                if click_x is None or click_y is None:
                    print(f"⚠️ 跳过岗位（无坐标）：{title} @ {company}")
                    continue

                print(f"🔍 [{idx}/{len(jobs)}] {title} @ {company}")
                try:
                    resolved_x, resolved_y = await self._resolve_job_click_coordinates(
                        page, title, float(click_x), float(click_y)
                    )
                    await self.actions.human_click(resolved_x, resolved_y)
                    await self.actions.random_delay(1, 3)
                    job_url = await self.browser.get_job_url()
                    detail_text = await self.browser.get_job_detail_text()
                    if not detail_text or len(detail_text.strip()) < 100:
                        print(f"⚠️ 跳过岗位（无法提取有效描述）：{title} @ {company}")
                        try:
                            await page.keyboard.press("Escape")
                            await asyncio.sleep(1)
                        except Exception:
                            pass
                        continue

                    match = await self.matcher.score_job(
                        title=title,
                        description=detail_text,
                        company=company,
                        salary=salary,
                    )
                    score = float(match.get("score", 5))
                    reason = str(match.get("reason", "解析失败"))
                    selected_resume = str(match.get("selected_resume", "unknown"))
                    dimension_scores = match.get("dimension_scores", {})
                    analysis = str(match.get("analysis", ""))
                    print(f"✅ 评分：{score} | 理由：{reason}")

                    if score >= min_score:
                        self.jobs.append(
                            {
                                "title": title,
                                "company": company,
                                "salary": salary,
                                "location": location,
                                "tags": tags if isinstance(tags, list) else [],
                                "description": detail_text,  # 保存完整描述，不再截断
                                "url": job_url or "",  # URL 提取失败时置空，不影响评分
                                "score": score,
                                "reason": reason,
                                "selected_resume": selected_resume,
                                "dimension_scores": dimension_scores,
                                "analysis": analysis,
                            }
                        )
                    else:
                        print(f"⚠️ 分数低于阈值({min_score})，不纳入结果。")
                except Exception as exc:
                    print(f"❌ 处理岗位失败：{exc}")
                finally:
                    try:
                        await page.keyboard.press("Escape")
                        await asyncio.sleep(1)
                    except Exception:
                        try:
                            await page.go_back(wait_until="domcontentloaded", timeout=20000)
                        except Exception:
                            pass

            has_next = bool(vision_result.get("has_next_page", False))
            next_x = vision_result.get("next_page_x")
            next_y = vision_result.get("next_page_y")
            if has_next and page_index < max_pages and next_x is not None and next_y is not None:
                print("🔍 准备进入下一页")
                try:
                    await self.actions.human_click(float(next_x), float(next_y))
                    await self.actions.random_delay(4, 8)
                    await self._wait_for_job_list(page)
                except Exception as exc:
                    print(f"⚠️ 翻页失败，流程结束：{exc}")
                    break
            else:
                print("✅ 无下一页或达到最大页数，结束抓取。")
                break

    async def _save(self) -> Path:
        """将结果按分数降序保存为 JSON 文件。"""
        self.jobs.sort(key=lambda x: float(x.get("score", 0)), reverse=True)
        output_dir = self.base_dir / "output"
        await asyncio.to_thread(output_dir.mkdir, parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"jobs_{ts}.json"
        content = json.dumps(self.jobs, ensure_ascii=False, indent=2)
        await asyncio.to_thread(output_file.write_text, content, "utf-8")
        return output_file

    def _print_top10(self) -> None:
        """打印 TOP10 匹配岗位。"""
        print("\n📊 TOP 10 匹配岗位")
        if not self.jobs:
            print("⚠️ 无符合阈值的岗位。")
            return
        for i, job in enumerate(self.jobs[:10], start=1):
            print(
                f"{i}. {job.get('title', '')} @ {job.get('company', '')} "
                f"→ {job.get('salary', '')} | 匹配分数 {job.get('score', 0)} "
                f"→ {job.get('reason', '')}"
            )


async def _read_yaml_async(path: Path) -> Dict[str, Any]:
    """异步读取 YAML 配置。"""
    text = await asyncio.to_thread(path.read_text, "utf-8")
    data = yaml.safe_load(text) or {}
    return data if isinstance(data, dict) else {}


async def _read_text_async(path: Path) -> str:
    """异步读取文本文件。"""
    return await asyncio.to_thread(path.read_text, "utf-8")


async def _check_ollama(base_url: str) -> bool:
    """检查 Ollama 服务连通性。"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/api/tags")
            resp.raise_for_status()
            tags = resp.json().get("models", [])
            print(f"✅ Ollama 可连接，当前模型数量：{len(tags)}")
            return True
    except httpx.HTTPError as exc:
        print(f"❌ Ollama 连接失败：{exc}")
        return False
    except Exception as exc:
        print(f"❌ Ollama 检查异常：{exc}")
        return False


async def async_main() -> None:
    """主入口：执行环境检查并启动爬虫。"""
    base_dir = Path(__file__).resolve().parent
    config_path = base_dir / "config.yaml"
    resume_dir = base_dir / "data"

    if not config_path.exists():
        print("❌ 未找到 config.yaml，请先创建配置文件。")
        return

    # 加载多份简历（支持 .md 和 .docx 格式）
    resume_texts = await _load_multiple_resumes(resume_dir)
    if not resume_texts:
        print("❌ 未在 data/ 目录下找到任何简历文件（支持 .md 或 .docx）。")
        return

    config = await _read_yaml_async(config_path)
    ollama_base = str(config.get("ollama", {}).get("base_url", "http://localhost:11434"))
    ok = await _check_ollama(ollama_base)
    if not ok:
        return

    scraper = JobScraper(config=config, resume_texts=resume_texts, base_dir=base_dir)
    await scraper.run()


async def _load_multiple_resumes(resume_dir: Path) -> Dict[str, str]:
    """从 data 目录加载所有简历文件。

    Returns:
        字典，键为简历标识（如 "dev", "ba_pm"），值为简历文本
    """
    resume_texts = {}

    # 支持的简历文件格式
    supported_extensions = {'.md', '.txt', '.docx'}

    # 需要忽略的系统文件和隐藏文件
    ignore_files = {'desktop.ini', 'thumbs.db', '.ds_store'}

    # 检查 python-docx 是否可用
    docx_available = False
    try:
        import docx
        docx_available = True
    except ImportError:
        print("⚠️ 未安装 python-docx，将跳过 .docx 文件")
        print("💡 提示：如需解析 Word 简历，请运行：pip install python-docx")

    for file_path in resume_dir.iterdir():
        # 跳过系统文件和隐藏文件
        if file_path.name.lower() in ignore_files:
            continue

        if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
            try:
                # 根据文件名生成标识（去掉扩展名）
                key = file_path.stem.lower().replace(' ', '_').replace('-', '_')

                if file_path.suffix.lower() == '.docx':
                    if not docx_available:
                        print(f"⚠️ 跳过 {file_path.name}（需要 python-docx）")
                        continue
                    # 解析 Word 文档
                    text = await _read_docx_async(file_path)
                else:
                    # 读取文本文件
                    text = await _read_text_async(file_path)

                if text.strip():
                    resume_texts[key] = text.strip()
                    print(f"✅ 加载简历：[{key}] - {file_path.name}")

            except Exception as exc:
                print(f"⚠️ 加载简历失败 {file_path.name}：{exc}")

    return resume_texts


async def _read_docx_async(file_path: Path) -> str:
    """异步读取 .docx 文件内容。"""
    try:
        from docx import Document
        doc = Document(str(file_path))
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        return '\n'.join(paragraphs)
    except ImportError:
        # 这个异常应该在上层已经处理了，这里作为保险
        raise RuntimeError("python-docx 未安装")
    except Exception as exc:
        print(f"❌ 读取 Word 文档失败：{exc}")
        raise


def main() -> None:
    """同步入口包装：处理 Ctrl+C 和未捕获异常。"""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断，已安全退出。")
        print("💡 提示：如果浏览器仍开启，请手动关闭窗口")
    except Exception:
        print("❌ 程序发生未处理异常：")
        traceback.print_exc()
        print("\n💡 提示：如果浏览器仍开启，请手动关闭窗口")


if __name__ == "__main__":
    main()
