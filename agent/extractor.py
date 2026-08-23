import re
from typing import Optional
from urllib.parse import urljoin

from playwright.async_api import Page


class UniversalJobDescriptionExtractor:
    """ä»Žå½“å‰è¯¦æƒ…é¢æ¿æå–å²—ä½æ­£æ–‡å’Œå¯ç”¨çš„å²—ä½ URLã€‚"""

    def __init__(self, page: Page) -> None:
        self.page = page

    async def extract_description(self) -> Optional[str]:
        """æå–å²—ä½æ­£æ–‡ï¼›æ­£æ–‡æå–ä¸ä¾èµ–å½“å‰é¡µé¢ URLã€‚"""
        if not self.page:
            return None

        selectors = (
            ".jobs-description-content__text",
            "#job-details",
            '[data-test-id="job-details"]',
            ".job-description__content",
            "div.jobs-box__html-content",
            "article",
            '[role="main"]',
        )
        for selector in selectors:
            try:
                element = await self.page.query_selector(selector)
                if not element:
                    continue
                text = self._clean_text(await element.inner_text())
                if len(text) >= 100:
                    return text
            except Exception:
                continue
        return None

    async def extract_url(self) -> Optional[str]:
        """ä»Žå½“å‰é¡µã€è§„èŒƒé“¾æŽ¥æˆ–èŒä½é“¾æŽ¥ä¸­æå– LinkedIn èŒä½ URLã€‚"""
        if not self.page:
            return None

        candidates = [self.page.url]
        for selector in ('meta[property="og:url"]', 'link[rel="canonical"]', 'a[href*="/jobs/view/"]'):
            try:
                element = await self.page.query_selector(selector)
                if element:
                    value = await element.get_attribute("content") or await element.get_attribute("href")
                    if value:
                        candidates.append(urljoin(self.page.url, value))
            except Exception:
                continue

        for candidate in candidates:
            job_id = self._extract_job_id(candidate)
            if job_id:
                return f"https://www.linkedin.com/jobs/view/{job_id}/"
        return None

    @staticmethod
    def _extract_job_id(url: str) -> Optional[str]:
        if not url:
            return None
        match = re.search(r"/jobs/view/(\d+)|currentJobId=(\d+)", url, re.IGNORECASE)
        if not match:
            return None
        return match.group(1) or match.group(2)

    @staticmethod
    def _clean_text(text: str) -> str:
        return "\n".join(line.strip() for line in text.splitlines() if line.strip())
