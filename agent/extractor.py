import re
from typing import Optional
from urllib.parse import urljoin

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError


LINKEDIN_DETAIL_BODY = (
    '[data-sdui-component="com.linkedin.sdui.generated.jobseeker.dsl.impl.aboutTheJob"] '
    '[data-testid="expandable-text-box"]'
)

# Read identity and text together, so an old detail panel cannot satisfy readiness.
DETAIL_STATE_SCRIPT = r"""({jobId, selector}) => {
    const visible = e => !!(e && e.getClientRects().length &&
        getComputedStyle(e).visibility !== 'hidden' && getComputedStyle(e).display !== 'none');
    const actualId = new URL(location.href).searchParams.get('currentJobId') ||
        (location.pathname.match(/\/jobs\/view\/(\d+)/) || [])[1];
    const root = document.getElementById('JobDetails_AboutTheJob_' + jobId);
    const result = {status:'DETAIL_NOT_LOADED', actual_job_id:actualId || null,
        root_id:root ? root.id : null, root_visible:visible(root), selector,
        match_count:0, elements:[], text:''};
    if (actualId !== jobId || !visible(root)) return result;
    const elements = [...root.querySelectorAll(selector)];
    result.match_count = elements.length;
    result.status = elements.length ? 'DETAIL_EMPTY' : 'DETAIL_SELECTOR_MISS';
    for (const e of elements) {
        const text = (e.innerText || '').split(/\r?\n/).map(s=>s.trim()).filter(Boolean).join('\n');
        const shown = visible(e);
        result.elements.push({visible:shown, inner_text_length:text.length});
        if (shown && text.length >= 100 && !result.text) {
            result.status = 'DETAIL_SUCCESS'; result.text = text;
        }
    }
    return result;
}"""


class UniversalJobDescriptionExtractor:
    """ä»Žå½“å‰è¯¦æƒ…é¢æ¿æå–å²—ä½æ­£æ–‡å’Œå¯ç”¨çš„å²—ä½ URLã€‚"""

    DESCRIPTION_SELECTORS = (
        LINKEDIN_DETAIL_BODY,
        ".jobs-description-content__text", "#job-details",
        '[data-test-id="job-details"]', ".job-description__content",
        "div.jobs-box__html-content", "article", '[role="main"]',
    )

    def __init__(self, page: Page) -> None:
        self.page = page
        self.detail_diagnostic = {}

    async def _wait_for_job_detail(self, job_id: str, timeout_ms: int) -> Optional[str]:
        """Wait for the target AboutTheJob body, not just URL navigation or sleep."""
        args = {"jobId": job_id, "selector": LINKEDIN_DETAIL_BODY}
        wait = {"condition": "target URL ID + visible target AboutTheJob ID + visible body >= 100 chars",
                "timeout_ms": timeout_ms, "timed_out": False}
        try:
            handle = await self.page.wait_for_function(
                f"args => {{ const state = ({DETAIL_STATE_SCRIPT})(args); "
                "return state.status === 'DETAIL_SUCCESS' ? state : false; }",
                arg=args, timeout=timeout_ms, polling=200,
            )
            try:
                state = await handle.json_value()
            finally:
                await handle.dispose()
        except PlaywrightTimeoutError:
            wait["timed_out"] = True
            state = await self.page.evaluate(DETAIL_STATE_SCRIPT, args)
            # The final snapshot is evidence only; timeout never becomes success.
            if state["status"] == "DETAIL_SUCCESS":
                state["status"] = "DETAIL_NOT_LOADED"
        text = state.pop("text", "")
        self.detail_diagnostic = {**state, "wait": wait, "detail_text_length": len(text)}
        return text if state["status"] == "DETAIL_SUCCESS" and len(text) >= 100 else None

    async def extract_description(self, expected_job_id=None, timeout_ms=10000) -> Optional[str]:
        """æå–å²—ä½æ­£æ–‡ï¼›æ­£æ–‡æå–ä¸ä¾èµ–å½“å‰é¡µé¢ URLã€‚"""
        if not self.page:
            return None

        if expected_job_id is not None:
            if not isinstance(expected_job_id, str) or not re.fullmatch(r"[0-9]+", expected_job_id):
                self.detail_diagnostic = {"status": "DETAIL_NOT_LOADED", "reason": "invalid target identity"}
                return None
            return await self._wait_for_job_detail(expected_job_id, timeout_ms)

        found = False
        for selector in self.DESCRIPTION_SELECTORS:
            try:
                elements = await self.page.query_selector_all(selector)
                found = found or bool(elements)
                for element in elements:
                    if not await element.is_visible():
                        continue
                    text = self._clean_text(await element.inner_text())
                    if len(text) >= 100:
                        self.detail_diagnostic = {"status": "DETAIL_SUCCESS", "selector": selector,
                                                  "detail_text_length": len(text)}
                        return text
            except Exception:
                continue
        self.detail_diagnostic = {"status": "DETAIL_EMPTY" if found else "DETAIL_SELECTOR_MISS"}
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
