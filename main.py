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

    def __init__(self, config: Dict[str, Any], resume_text: str, base_dir: Path) -> None:
        """加载配置并初始化各功能模块。"""
        self.config = config
        self.resume_text = resume_text
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
            resume_text=self.resume_text,
            base_url=str(ollama.get("base_url", "http://localhost:11434")),
            model=str(ollama.get("text_model", "qwen3.5:9b")),
        )
        self.actions: Optional[HumanActions] = None

    async def run(self) -> None:
        """执行完整爬取流程。"""
        page = None
        try:
            print("✅ 阶段1：启动浏览器")
            page = await self.browser.start()
            behavior = self.config.get("behavior", {})
            self.actions = HumanActions(
                page=page,
                min_delay=float(behavior.get("delay_min", 2)),
                max_delay=float(behavior.get("delay_max", 6)),
            )

            print("🔍 阶段2：搜索岗位")
            await self._search_jobs(page)

            print("📊 阶段3：爬取并评分")
            await self._crawl_and_score(page)

            output_file = await self._save()
            self._print_top10()
            print(f"📁 结果已保存：{output_file}")
        finally:
            await self.browser.close()

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

        selectors = [
            'input[placeholder*="搜索"]',
            'input[name*="query"]',
            'input[name*="keyword"]',
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
            return

        print("⚠️ 自动搜索失败，请手动在浏览器中完成搜索。")
        await asyncio.to_thread(input, "完成后请在终端按回车继续...")

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
                    await self.actions.human_click(float(click_x), float(click_y))
                    await self.actions.random_delay(1, 3)
                    detail_text = await self.browser.get_page_text()
                    match = await self.matcher.score_job(
                        title=title,
                        description=detail_text,
                        company=company,
                        salary=salary,
                    )
                    score = float(match.get("score", 5))
                    reason = str(match.get("reason", "解析失败"))
                    print(f"✅ 评分：{score} | 理由：{reason}")

                    if score >= min_score:
                        self.jobs.append(
                            {
                                "title": title,
                                "company": company,
                                "salary": salary,
                                "location": location,
                                "tags": tags if isinstance(tags, list) else [],
                                "description": detail_text[:500],
                                "score": score,
                                "reason": reason,
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
    resume_path = base_dir / "data" / "resume.md"

    if not config_path.exists():
        print("❌ 未找到 config.yaml，请先创建配置文件。")
        return
    if not resume_path.exists():
        print("❌ 未找到 data/resume.md，请先准备简历文件。")
        return

    config = await _read_yaml_async(config_path)
    ollama_base = str(config.get("ollama", {}).get("base_url", "http://localhost:11434"))
    ok = await _check_ollama(ollama_base)
    if not ok:
        return

    resume_text = await _read_text_async(resume_path)
    scraper = JobScraper(config=config, resume_text=resume_text, base_dir=base_dir)
    await scraper.run()


def main() -> None:
    """同步入口包装：处理 Ctrl+C 和未捕获异常。"""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断，已安全退出。")
    except Exception:
        print("❌ 程序发生未处理异常：")
        traceback.print_exc()


if __name__ == "__main__":
    main()
