import asyncio

import pytest

from agent.extractor import (
    JOB_CARD_SELECTOR,
    JOB_LIST_SCOPE,
    PAGE_BUTTON_SELECTOR,
    PAGINATION_SELECTOR,
    LINKEDIN_DETAIL_BODY,
    UniversalJobDescriptionExtractor,
)
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


class CardTextElement:
    def __init__(self, text):
        self.text = text

    async def inner_text(self):
        return self.text


class JobCardElement:
    def __init__(self, paragraphs, *, componentkey=None, text=None, box=None):
        self.paragraphs = [CardTextElement(value) for value in paragraphs]
        self.componentkey = componentkey
        self.text = text if text is not None else "\n".join(paragraphs)
        self.box = box

    async def query_selector_all(self, selector):
        assert selector == "p"
        return self.paragraphs

    async def get_attribute(self, name):
        return self.componentkey if name == "componentkey" else None

    async def inner_text(self):
        return self.text

    async def bounding_box(self):
        return self.box


class PageButton:
    def __init__(self, page_number, *, current=False, disabled=False, box=None):
        self.page_number = page_number
        self.current = current
        self.disabled = disabled
        self.box = box or {"x": 0, "y": 0, "width": 20, "height": 10}
        self.scrolled = False

    async def get_attribute(self, name):
        values = {
            "aria-label": f"Page {self.page_number}",
            "aria-current": "true" if self.current else "false",
            "disabled": "" if self.disabled else None,
            "aria-disabled": "true" if self.disabled else "false",
        }
        return values.get(name)

    async def scroll_into_view_if_needed(self):
        self.scrolled = True

    async def bounding_box(self):
        return self.box if self.scrolled else None


class PaginationElement:
    def __init__(self, buttons):
        self.buttons = buttons

    async def query_selector_all(self, selector):
        assert selector == PAGE_BUTTON_SELECTOR
        return self.buttons


class JobListScope:
    def __init__(self, cards=(), pagination=None):
        self.cards = list(cards)
        self.pagination = pagination

    async def query_selector_all(self, selector):
        assert selector == JOB_CARD_SELECTOR
        return self.cards

    async def query_selector(self, selector):
        assert selector == PAGINATION_SELECTOR
        return self.pagination


class JobListPage:
    def __init__(self, scopes):
        self.scopes = scopes

    async def query_selector_all(self, selector):
        assert selector == JOB_LIST_SCOPE
        return self.scopes


def extract_cards(page):
    return asyncio.run(UniversalJobDescriptionExtractor(page).extract_job_cards())


def next_page_target(page):
    return asyncio.run(UniversalJobDescriptionExtractor(page).extract_next_page_target())


def test_extract_job_cards_uses_confirmed_scope_identity_and_dom_order():
    cards = extract_cards(JobListPage([JobListScope([
        JobCardElement(
            [" Platform Engineer ", " Example Corp ", " Sydney, NSW "],
            componentkey="job-card-component-ref-4460945256",
            text="Platform Engineer\nExample Corp\nSydney, NSW\n6,000 CNY/month - 10K CNY/month",
            box={"x": 10, "y": 20, "width": 100, "height": 40},
        ),
        JobCardElement(
            ["Data Engineer", "Second Corp", "Melbourne, VIC"],
            componentkey="job-card-component-ref-4460945257",
            box={"x": 10, "y": 80, "width": 100, "height": 40},
        ),
    ])]))

    assert cards == [
        {
            "title": "Platform Engineer", "company": "Example Corp", "location": "Sydney, NSW",
            "salary": "6,000 CNY/month - 10K CNY/month", "job_id": "4460945256",
            "click_x": 60, "click_y": 40,
        },
        {
            "title": "Data Engineer", "company": "Second Corp", "location": "Melbourne, VIC",
            "salary": "", "job_id": "4460945257", "click_x": 60, "click_y": 100,
        },
    ]


def test_extract_job_cards_skips_missing_title_and_keeps_optional_fields_safe():
    cards = extract_cards(JobListPage([JobListScope([
        JobCardElement(["", "Not a title"], componentkey="job-card-component-ref-1", box={"x": 0, "y": 0, "width": 1, "height": 1}),
        JobCardElement(["Title only"], box={"x": 3, "y": 5, "width": 10, "height": 20}),
    ])]))

    assert cards == [{
        "title": "Title only", "company": "", "location": "", "salary": "", "job_id": None,
        "click_x": 8, "click_y": 15,
    }]


def test_extract_job_cards_skips_hidden_cards_without_a_bounding_box():
    page = JobListPage([JobListScope([
        JobCardElement(["Hidden"], componentkey="job-card-component-ref-1", box=None),
    ])])
    assert extract_cards(page) == []


def test_extract_job_cards_requires_one_confirmed_list_scope():
    card = JobCardElement(["Title"], box={"x": 0, "y": 0, "width": 1, "height": 1})
    assert extract_cards(JobListPage([])) == []
    assert extract_cards(JobListPage([JobListScope([card]), JobListScope([card])])) == []


def test_extract_next_page_target_uses_next_numeric_button_and_fresh_box_after_scroll():
    current = PageButton(1, current=True)
    target = PageButton(2, box={"x": 120, "y": 200, "width": 30, "height": 20})
    later = PageButton(3, box={"x": 160, "y": 200, "width": 30, "height": 20})
    page = JobListPage([JobListScope(pagination=PaginationElement([current, target, later]))])

    assert next_page_target(page) == (135, 210)
    assert target.scrolled is True
    assert later.scrolled is False


@pytest.mark.parametrize(
    "pagination",
    [
        None,
        PaginationElement([PageButton(1, current=True)]),
        PaginationElement([PageButton(1, current=True), PageButton(2, disabled=True)]),
        PaginationElement([PageButton(1), PageButton(2)]),
    ],
)
def test_extract_next_page_target_returns_none_without_an_enabled_following_page(pagination):
    assert next_page_target(JobListPage([JobListScope(pagination=pagination)])) is None
