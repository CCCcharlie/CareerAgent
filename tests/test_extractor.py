import asyncio

import pytest

from agent.extractor import UniversalJobDescriptionExtractor


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
