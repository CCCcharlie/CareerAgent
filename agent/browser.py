import asyncio
import io
import os
import shutil
from typing import Optional

from PIL import Image
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright


class BrowserManager:
    """浏览器管理器：负责启动浏览器、反检测注入、截图和安全关闭。"""
    SOURCE_PROFILE_DIR = r"C:\Users\04268\AppData\Local\Google\Chrome\User Data\Profile 6"
    PROFILE_DIR = r"C:\Users\04268\Downloads\AgentWork\job-agent\data\chrome_profile"

    def __init__(self, headless: bool = False) -> None:
        """初始化浏览器管理器。"""
        self.headless = headless
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def start(self) -> Page:
        """启动浏览器并返回页面对象。"""
        await self._sync_profile_data()
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

    async def _sync_profile_data(self) -> None:
        """仅在本地副本不存在时，从源 Profile 同步一次。"""
        # 如果本地副本已经存在，跳过同步
        if os.path.exists(self.PROFILE_DIR) and os.listdir(self.PROFILE_DIR):
            print("✅ 使用已有浏览器 Profile 副本（跳过同步）")
            return
        
        # 首次运行才从源 Profile 复制
        try:
            print(f"🔍 首次同步 Profile：{self.SOURCE_PROFILE_DIR} -> {self.PROFILE_DIR}")
            copied, failed = await asyncio.to_thread(self._copy_profile_tree)
            print(f"✅ 已同步浏览器 Profile：复制 {copied} 个文件")
            if failed:
                print(f"⚠️ 有 {failed} 个文件被占用未复制")
        except Exception as exc:
            print(f"⚠️ 同步 Profile 失败：{exc}")

    def _copy_profile_tree(self) -> tuple[int, int]:
        """复制 Profile 目录树，跳过被占用文件。"""
        if not os.path.exists(self.SOURCE_PROFILE_DIR):
            raise FileNotFoundError(f"源 Profile 不存在：{self.SOURCE_PROFILE_DIR}")
        copied = 0
        failed = 0
        os.makedirs(self.PROFILE_DIR, exist_ok=True)
        for root, _, files in os.walk(self.SOURCE_PROFILE_DIR):
            rel_root = os.path.relpath(root, self.SOURCE_PROFILE_DIR)
            dst_root = os.path.join(self.PROFILE_DIR, rel_root)
            os.makedirs(dst_root, exist_ok=True)
            for filename in files:
                src_file = os.path.join(root, filename)
                dst_file = os.path.join(dst_root, filename)
                try:
                    shutil.copy2(src_file, dst_file)
                    copied += 1
                except OSError:
                    failed += 1
        return copied, failed

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
