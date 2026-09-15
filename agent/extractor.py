import re
from typing import Optional
from urllib.parse import urljoin

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError


LINKEDIN_DETAIL_BODY = (
    '[data-sdui-component="com.linkedin.sdui.generated.jobseeker.dsl.impl.aboutTheJob"] '
    '[data-testid="expandable-text-box"]'
)

# Step 0 reconnaissance confirmed these component semantics on the real search
# page. They deliberately avoid LinkedIn's generated CSS class names.
JOB_LIST_SCOPE = '[componentkey="SearchResultsMainContent"]'
JOB_CARD_SELECTOR = '[role="button"][componentkey^="job-card-component-ref-"]'
JOB_CARD_ID_PATTERN = re.compile(r"^job-card-component-ref-(\d+)$")
PAGINATION_SELECTOR = 'ul[data-testid="pagination-controls-list"]'
PAGE_BUTTON_SELECTOR = 'button[data-testid^="pagination-indicator-"]'
SALARY_LINE_PATTERN = re.compile(
    r"[$€£¥]|\b(?:AUD|USD|CNY|EUR|GBP)\b|/(?:year|yr|month|day|hour)\b",
    re.IGNORECASE,
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

    async def extract_job_cards(self) -> list[dict]:
        """Extract visible job cards from the confirmed search-results scope."""
        scope = await self._get_job_list_scope()
        if scope is None:
            return []

        try:
            elements = await scope.query_selector_all(JOB_CARD_SELECTOR)
        except Exception:
            return []

        cards = []
        for element in elements:
            try:
                box = await element.bounding_box()
                if not box or box["width"] <= 0 or box["height"] <= 0:
                    continue

                fields = [
                    self._normalize_inline_text(await field.inner_text())
                    for field in await element.query_selector_all("p")
                ]
                # The observed card structure has title first. Without it, this
                # is not a usable job record for later orchestration.
                if not fields or not fields[0]:
                    continue

                componentkey = await element.get_attribute("componentkey")
                job_id_match = JOB_CARD_ID_PATTERN.fullmatch(componentkey or "")
                card_text = await element.inner_text()
                cards.append({
                    "title": fields[0],
                    "company": fields[1] if len(fields) > 1 else "",
                    "location": fields[2] if len(fields) > 2 else "",
                    "salary": self._extract_salary_line(card_text),
                    "job_id": job_id_match.group(1) if job_id_match else None,
                    "click_x": box["x"] + box["width"] / 2,
                    "click_y": box["y"] + box["height"] / 2,
                })
            except Exception:
                continue
        return cards

    async def extract_next_page_target(self) -> Optional[tuple[float, float]]:
        """Return the center of the numeric page after the current page, if any."""
        scope = await self._get_job_list_scope()
        if scope is None:
            return None

        try:
            pagination = await scope.query_selector(PAGINATION_SELECTOR)
            if pagination is None:
                return None
            buttons = await pagination.query_selector_all(PAGE_BUTTON_SELECTOR)
        except Exception:
            return None

        current_page = None
        candidates = []
        for button in buttons:
            try:
                page_number = self._page_number(await button.get_attribute("aria-label"))
                if page_number is None:
                    continue
                if (await button.get_attribute("aria-current")) == "true":
                    current_page = page_number
                    continue
                if await self._is_disabled(button):
                    continue
                candidates.append((page_number, button))
            except Exception:
                continue

        if current_page is None:
            return None
        following = [(number, button) for number, button in candidates if number > current_page]
        if not following:
            return None

        _, target = min(following, key=lambda candidate: candidate[0])
        try:
            await target.scroll_into_view_if_needed()
            # Scroll can move the target, so obtain its box only afterwards.
            box = await target.bounding_box()
            if not box or box["width"] <= 0 or box["height"] <= 0:
                return None
            return (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        except Exception:
            return None

    async def _get_job_list_scope(self):
        if not self.page:
            return None
        try:
            scopes = await self.page.query_selector_all(JOB_LIST_SCOPE)
        except Exception:
            return None
        # A unique component scope prevents accidentally parsing a detail panel.
        return scopes[0] if len(scopes) == 1 else None

    @staticmethod
    async def _is_disabled(button) -> bool:
        return (
            await button.get_attribute("disabled") is not None
            or (await button.get_attribute("aria-disabled")) == "true"
        )

    @staticmethod
    def _page_number(label: Optional[str]) -> Optional[int]:
        match = re.fullmatch(r"\s*Page\s+(\d+)\s*", label or "", re.IGNORECASE)
        return int(match.group(1)) if match else None

    @staticmethod
    def _normalize_inline_text(text: str) -> str:
        return " ".join(text.split())

    @staticmethod
    def _extract_salary_line(text: str) -> str:
        for line in text.splitlines():
            normalized = UniversalJobDescriptionExtractor._normalize_inline_text(line)
            if normalized and SALARY_LINE_PATTERN.search(normalized):
                return normalized
        return ""

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
