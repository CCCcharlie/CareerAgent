import asyncio
import io
import os
from typing import Optional

from PIL import Image
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright


from agent.extractor import UniversalJobDescriptionExtractor


class BrowserManager:
    """浏览器管理器：负责启动浏览器、反检测注入、截图和安全关闭。"""
    PROFILE_DIR = os.getenv(
        "CAREER_AGENT_PROFILE_DIR",
        r"C:\Users\04268\Downloads\AgentWork\job-agent\data\chrome_profile",
    )

    def __init__(self, headless: bool = False) -> None:
        """初始化浏览器管理器。"""
        self.headless = headless
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def start(self) -> Page:
        """启动浏览器并返回页面对象。"""
        self.playwright = await async_playwright().start()
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=AutomationControlled",
            "--disable-infobars",
        ]
        try:
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=self.PROFILE_DIR,
                channel="chrome",
                headless=self.headless,
                args=launch_args,
                viewport={"width": 1440, "height": 900},
                locale="zh-CN",
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
            )
            print("✅ 已启动独立 Profile 的 Chrome 持久化上下文")
        except Exception as exc:
            print(f"⚠️ 启动 Chrome 持久化上下文失败，改用 Chromium：{exc}")
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=self.PROFILE_DIR,
                headless=self.headless,
                args=launch_args,
                viewport={"width": 1440, "height": 900},
                locale="zh-CN",
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
            )

        await self.context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {
              get: () => undefined
            });
            """
        )
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = await self.context.new_page()
        return self.page

    async def screenshot(self) -> bytes:
        """截取当前页面并返回 JPEG bytes（质量75）。"""
        if not self.page:
            raise RuntimeError("页面未初始化，无法截图。")
        png_bytes = await self.page.screenshot(type="png", full_page=True)
        return await asyncio.to_thread(self._png_to_jpeg, png_bytes, 75)

    @staticmethod
    def _png_to_jpeg(png_bytes: bytes, quality: int) -> bytes:
        """将 PNG bytes 转换为 JPEG bytes。"""
        image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()

    async def get_page_text(self) -> str:
        """获取页面 body 可见文本。"""
        if not self.page:
            raise RuntimeError("页面未初始化，无法提取文本。")
        return await self.page.evaluate(
            """
            () => {
              const body = document.body;
              return body ? body.innerText || "" : "";
            }
            """
        )

    async def get_job_detail_text(self, expected_job_id=None) -> str:
        """提取当前岗位详情正文，不依赖 URL 提取成功。"""
        if not self.page:
            raise RuntimeError("页面未初始化，无法提取文本。")

        self.last_detail_diagnostic = {}
        try:
            extractor = UniversalJobDescriptionExtractor(self.page)
            description = await extractor.extract_description(expected_job_id=expected_job_id)
            self.last_detail_diagnostic = extractor.detail_diagnostic
            if description:
                return description
            return ""
        except Exception as exc:
            self.last_detail_diagnostic = {"status": "DETAIL_NOT_LOADED", "reason": str(exc)}
            print(f"⚠️ 提取岗位详情失败：{exc}")
            return ""

    async def get_job_url(self) -> Optional[str]:
        """提取并规范化当前岗位 URL。"""
        if not self.page:
            return None

        try:
            extractor = UniversalJobDescriptionExtractor(self.page)

            return await extractor.extract_url()
        except Exception as exc:
            print(f"⚠️ URL提取失败：{exc}")
            return None

    async def close(self) -> None:
        """安全关闭页面、上下文和浏览器。"""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            print("✅ 浏览器已安全关闭")
        except Exception as exc:
            print(f"⚠️ 关闭浏览器时出现异常：{exc}")
