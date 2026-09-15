import asyncio

import agent.browser as browser_module


def test_browser_forwards_target_identity_and_preserves_detail_diagnostic(monkeypatch):
    class Extractor:
        def __init__(self, page):
            self.detail_diagnostic = {"status": "DETAIL_SUCCESS"}

        async def extract_description(self, expected_job_id):
            assert expected_job_id == "123"
            return "Full body " * 100

    monkeypatch.setattr(browser_module, "UniversalJobDescriptionExtractor", Extractor)
    browser = browser_module.BrowserManager()
    browser.page = object()
    assert asyncio.run(browser.get_job_detail_text(expected_job_id="123")) == "Full body " * 100
    assert browser.last_detail_diagnostic["status"] == "DETAIL_SUCCESS"


def test_browser_detail_exception_returns_empty_and_records_failure(monkeypatch):
    class Extractor:
        def __init__(self, page):
            pass

        async def extract_description(self, expected_job_id):
            raise RuntimeError("page closed")

    monkeypatch.setattr(browser_module, "UniversalJobDescriptionExtractor", Extractor)
    browser = browser_module.BrowserManager()
    browser.page = object()
    assert asyncio.run(browser.get_job_detail_text(expected_job_id="123")) == ""
    assert browser.last_detail_diagnostic["status"] == "DETAIL_NOT_LOADED"


def test_browser_get_job_cards_forwards_the_current_page(monkeypatch):
    page = object()
    cards = [{"title": "Platform Engineer", "job_id": "4460945256"}]

    class Extractor:
        def __init__(self, received_page):
            assert received_page is page

        async def extract_job_cards(self):
            return cards

    monkeypatch.setattr(browser_module, "UniversalJobDescriptionExtractor", Extractor)
    browser = browser_module.BrowserManager()
    browser.page = page
    assert asyncio.run(browser.get_job_cards()) == cards


def test_browser_get_job_cards_returns_empty_on_missing_page_or_extractor_failure(monkeypatch):
    browser = browser_module.BrowserManager()
    assert asyncio.run(browser.get_job_cards()) == []

    class Extractor:
        def __init__(self, page):
            pass

        async def extract_job_cards(self):
            raise RuntimeError("page closed")

    monkeypatch.setattr(browser_module, "UniversalJobDescriptionExtractor", Extractor)
    browser.page = object()
    assert asyncio.run(browser.get_job_cards()) == []


def test_browser_get_next_page_target_forwards_and_returns_safe_fallbacks(monkeypatch):
    page = object()

    class Extractor:
        def __init__(self, received_page):
            assert received_page is page

        async def extract_next_page_target(self):
            return (120.5, 240.5)

    monkeypatch.setattr(browser_module, "UniversalJobDescriptionExtractor", Extractor)
    browser = browser_module.BrowserManager()
    assert asyncio.run(browser.get_next_page_target()) is None
    browser.page = page
    assert asyncio.run(browser.get_next_page_target()) == (120.5, 240.5)

    class FailingExtractor:
        def __init__(self, page):
            pass

        async def extract_next_page_target(self):
            raise RuntimeError("page closed")

    monkeypatch.setattr(browser_module, "UniversalJobDescriptionExtractor", FailingExtractor)
    assert asyncio.run(browser.get_next_page_target()) is None
