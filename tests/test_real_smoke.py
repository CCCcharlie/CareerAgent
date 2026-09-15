import asyncio
import builtins
import json

import pytest

from scripts import real_smoke


@pytest.mark.parametrize("url", [
    "http://www.linkedin.com/jobs/search/?keywords=python",
    "https://example.com/jobs/search/", "https://www.linkedin.com/feed/",
])
def test_rejects_non_linkedin_search_url(url):
    with pytest.raises(real_smoke.argparse.ArgumentTypeError):
        real_smoke.search_url(url)


@pytest.mark.parametrize("blocked,vision_jobs,mode,dom_cards", [
    (False, 3, "vision", 1), (True, 0, "vision", 1),
    (False, 0, "vision", 1), (False, 0, "dom", 1),
])
def test_search_smoke_is_noninteractive_one_page_and_always_closes(
        tmp_path, monkeypatch, blocked, vision_jobs, mode, dom_cards):
    calls = []

    class Page:
        url = "https://www.linkedin.com/jobs/search/?keywords=python"

        async def goto(self, url, **kwargs):
            calls.append(("goto", url))

        async def wait_for_selector(self, selector, **kwargs):
            calls.append(("wait", selector))

        async def screenshot(self, **kwargs):
            pass

    class Browser:
        async def start(self):
            return Page()

        async def close(self):
            calls.append("close")

        async def get_job_cards(self):
            return [{"job_id": str(index)} for index in range(dom_cards)]

        async def get_next_page_target(self):
            return None

    class Scraper:
        def __init__(self, config, **kwargs):
            assert config["search"]["max_pages"] == 1
            assert config["extraction"]["job_list_mode"] == mode
            self.browser = Browser()

        async def _crawl_and_score(self, page, *, score_jobs, access_check, detail_observer):
            assert score_jobs is False
            assert access_check is check
            assert callable(detail_observer)
            calls.append("crawl")
            self.crawl_stats = dict.fromkeys(real_smoke.SMOKE_COUNTERS, 0)
            self.crawl_stats["VISION_JOBS"] = vision_jobs
            self.click_events = []

    async def config(path):
        return {"search": {"max_pages": 5}}

    async def check(page):
        if blocked:
            raise real_smoke.AutomationBlocked("MFA")

    def no_input(*args):
        pytest.fail("Smoke must not request terminal input")

    monkeypatch.setattr(builtins, "input", no_input)
    monkeypatch.setattr(real_smoke, "JobScraper", Scraper)
    monkeypatch.setattr(real_smoke, "_read_yaml_async", config)
    monkeypatch.setattr(real_smoke, "check_access", check)
    result = asyncio.run(real_smoke.run_search(Page.url, tmp_path, mode))
    assert calls[0] == ("goto", Page.url)
    assert calls[-1] == "close"
    assert ("crawl" in calls) is not blocked
    expected = "BLOCKED" if blocked else "COMPLETED" if vision_jobs or mode == "dom" else "ERROR"
    assert result["status"] == expected
    assert result.get("job_list_mode") == mode
    assert json.loads((tmp_path / "result.json").read_text(encoding="utf-8")) == result


@pytest.mark.parametrize("url,text", [
    ("https://www.linkedin.com/login", ""),
    ("https://www.linkedin.com/checkpoint/challenge", ""),
    ("https://www.linkedin.com/jobs/search/", "Let's do a quick security check"),
])
def test_access_check_detects_explicit_challenge(url, text):
    class Page:
        async def query_selector_all(self, selector):
            return []

        async def inner_text(self, selector):
            return text

    page = Page()
    page.url = url
    with pytest.raises(real_smoke.AutomationBlocked):
        asyncio.run(real_smoke.check_access(page))


def test_optional_screenshot_timeout_records_warning(tmp_path):
    class Page:
        async def screenshot(self, path, timeout):
            assert timeout == 5000
            raise TimeoutError("rendering timeout")

    report = {"status": "COMPLETED"}
    asyncio.run(real_smoke.capture_screenshot(Page(), tmp_path / "after.png", report))
    assert report["status"] == "COMPLETED"
    assert report["artifact_warnings"] == ["after.png: rendering timeout"]
