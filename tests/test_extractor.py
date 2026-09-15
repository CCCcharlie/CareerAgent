import asyncio

import pytest

from agent.extractor import LINKEDIN_DETAIL_BODY, UniversalJobDescriptionExtractor
from playwright.async_api import TimeoutError as PlaywrightTimeoutError


class FakeElement:
    def __init__(self, *, content=None, href=None):
        self.content = content
        self.href = href

    async def get_attribute(self, name):
        if name == "content":
            return self.content
        if name == "href":
            return self.href
        return None


class FakePage:
    def __init__(self, url, elements=None):
        self.url = url
        self.elements = elements or {}

    async def query_selector(self, selector):
        element = self.elements.get(selector)
        return element[0] if isinstance(element, list) else element


def extract_url(page):
    return asyncio.run(UniversalJobDescriptionExtractor(page).extract_url())


def test_extract_url_normalizes_standard_job_url():
    assert extract_url(FakePage("https://www.linkedin.com/jobs/view/123456/?trackingId=x")) == (
        "https://www.linkedin.com/jobs/view/123456/"
    )


def test_extract_url_normalizes_current_job_id():
    assert extract_url(FakePage("https://www.linkedin.com/jobs/search/?currentJobId=654321")) == (
        "https://www.linkedin.com/jobs/view/654321/"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://www.linkedin.com/jobs/preferences/",
        "https://www.linkedin.com/in/someone/",
        "https://www.linkedin.com/feed/",
    ],
)
def test_extract_url_rejects_urls_without_a_job_id(url):
    assert extract_url(FakePage(url)) is None


def test_extract_url_prefers_canonical_job_id_before_link_fallback():
    page = FakePage(
        "https://www.linkedin.com/jobs/search/",
        {
            'link[rel="canonical"]': FakeElement(
                href="/jobs/view/222222/"
            ),
            'a[href*="/jobs/view/"]': FakeElement(
                href="/jobs/view/111111/"
            ),
        },
    )

    assert extract_url(page) == "https://www.linkedin.com/jobs/view/222222/"


def test_extract_url_uses_first_link_only_as_last_fallback():
    page = FakePage(
        "https://www.linkedin.com/jobs/search/",
        {
            'a[href*="/jobs/view/"]': [
                FakeElement(href="/jobs/view/111111/"),
                FakeElement(href="/jobs/view/222222/"),
            ],
        },
    )

    assert extract_url(page) == "https://www.linkedin.com/jobs/view/111111/"


class DescriptionElement:
    def __init__(self, text, visible=True):
        self.text = text
        self.visible = visible

    async def inner_text(self):
        return self.text

    async def is_visible(self):
        return self.visible


class DescriptionPage:
    def __init__(self, elements):
        self.elements = elements
        self.calls = []

    async def query_selector_all(self, selector):
        self.calls.append(selector)
        return self.elements.get(selector, [])


def test_description_prefers_observed_about_job_body_and_returns_full_text():
    text = "First paragraph\n" + ("Full job body. " * 300).rstrip() + "\nFinal requirement"
    page = DescriptionPage({
        LINKEDIN_DETAIL_BODY: [DescriptionElement(text)],
        "article": [DescriptionElement("unrelated article " * 100)],
    })
    extractor = UniversalJobDescriptionExtractor(page)
    assert asyncio.run(extractor.extract_description()) == text
    assert page.calls == [LINKEDIN_DETAIL_BODY]


def test_description_fallback_order_skips_hidden_short_and_empty_elements():
    text = "Correct full description. " * 10
    page = DescriptionPage({
        LINKEDIN_DETAIL_BODY: [DescriptionElement("stale " * 100, visible=False)],
        ".jobs-description-content__text": [DescriptionElement("")],
        "#job-details": [DescriptionElement("short"), DescriptionElement(text)],
        "article": [DescriptionElement("unrelated " * 100)],
    })
    assert asyncio.run(UniversalJobDescriptionExtractor(page).extract_description()) == text.strip()
    assert page.calls == [LINKEDIN_DETAIL_BODY, ".jobs-description-content__text", "#job-details"]


@pytest.mark.parametrize("elements,status", [
    ({}, "DETAIL_SELECTOR_MISS"),
    ({LINKEDIN_DETAIL_BODY: [DescriptionElement(" ")]}, "DETAIL_EMPTY"),
    ({LINKEDIN_DETAIL_BODY: [DescriptionElement("short")]}, "DETAIL_EMPTY"),
    ({LINKEDIN_DETAIL_BODY: [DescriptionElement("hidden " * 100, False)]}, "DETAIL_EMPTY"),
])
def test_description_failure_classification(elements, status):
    extractor = UniversalJobDescriptionExtractor(DescriptionPage(elements))
    assert asyncio.run(extractor.extract_description()) is None
    assert extractor.detail_diagnostic["status"] == status


class DetailHandle:
    def __init__(self, state):
        self.state = state
        self.disposed = False

    async def json_value(self):
        return dict(self.state)

    async def dispose(self):
        self.disposed = True


class WaitingDetailPage:
    def __init__(self, state, timeout=False):
        self.state = state
        self.timeout = timeout
        self.handle = DetailHandle(state)
        self.wait_args = None

    async def wait_for_function(self, expression, *, arg, timeout, polling):
        self.wait_args = (arg, timeout, polling)
        assert "DETAIL_SUCCESS" in expression
        if self.timeout:
            raise PlaywrightTimeoutError("target body not ready")
        return self.handle

    async def evaluate(self, expression, arg):
        assert self.timeout
        assert arg["jobId"] == "123"
        return dict(self.state)


def test_detail_wait_requires_target_identity_and_returns_complete_ready_body():
    text = "A full requirement. " * 200
    page = WaitingDetailPage({"status": "DETAIL_SUCCESS", "text": text})
    extractor = UniversalJobDescriptionExtractor(page)
    assert asyncio.run(extractor.extract_description(expected_job_id="123")) == text
    assert page.wait_args == ({"jobId": "123", "selector": LINKEDIN_DETAIL_BODY}, 10000, 200)
    assert page.handle.disposed
    assert extractor.detail_diagnostic["wait"]["timed_out"] is False


@pytest.mark.parametrize("state", ["DETAIL_NOT_LOADED", "DETAIL_SELECTOR_MISS", "DETAIL_EMPTY"])
def test_detail_wait_timeout_preserves_failure_and_does_not_fallback_to_other_job(state):
    page = WaitingDetailPage({"status": state, "text": ""}, timeout=True)
    extractor = UniversalJobDescriptionExtractor(page)
    assert asyncio.run(extractor.extract_description(expected_job_id="123", timeout_ms=25)) is None
    assert extractor.detail_diagnostic["status"] == state
    assert extractor.detail_diagnostic["wait"]["timed_out"] is True
    assert page.wait_args[1] == 25


def test_detail_wait_rejects_unvalidated_identity_before_dom_queries():
    extractor = UniversalJobDescriptionExtractor(object())
    assert asyncio.run(extractor.extract_description(expected_job_id='123"]')) is None
    assert extractor.detail_diagnostic["status"] == "DETAIL_NOT_LOADED"


def test_extraction_stays_pending_until_target_body_is_ready():
    async def scenario():
        ready = asyncio.Event()
        entered = asyncio.Event()
        text = "Target description " * 20

        class DelayedPage(WaitingDetailPage):
            async def wait_for_function(self, expression, **kwargs):
                entered.set()
                await ready.wait()
                return await super().wait_for_function(expression, **kwargs)

        page = DelayedPage({"status": "DETAIL_SUCCESS", "text": text})
        task = asyncio.create_task(UniversalJobDescriptionExtractor(page).extract_description("123"))
        await entered.wait()
        assert not task.done()
        ready.set()
        assert await task == text

    asyncio.run(scenario())
