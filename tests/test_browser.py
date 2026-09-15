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
