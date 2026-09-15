import asyncio
from pathlib import Path

import pytest
import main


class FakeKeyboard:
    async def press(self, key):
        assert key == "Escape"


class FakeCard:
    def __init__(self, title="Software Engineer", identity="123456", visible=True, box=True):
        self.title = title
        self.identity = identity
        self.visible = visible
        self.box = box
        self.calls = []

    async def get_attribute(self, name):
        assert name == "componentkey"
        return f"job-card-component-ref-{self.identity}"

    async def evaluate(self, script):
        return self.title

    async def is_visible(self):
        return self.visible

    async def scroll_into_view_if_needed(self):
        self.calls.append("scroll")

    async def bounding_box(self):
        self.calls.append("box")
        assert self.calls[-2] == "scroll"
        return {"x": 100, "y": 200, "width": 300, "height": 80} if self.box else None


class FakeScope:
    def __init__(self, cards):
        self.cards = cards

    async def query_selector_all(self, selector):
        assert selector == main.JOB_CARD_SELECTOR
        return self.cards


class FakePage:
    def __init__(self, cards=None):
        self.keyboard = FakeKeyboard()
        self.cards = [FakeCard()] if cards is None else cards
        self.url = "https://www.linkedin.com/jobs/search-results/?currentJobId=123456"

    async def query_selector_all(self, selector):
        assert selector == main.JOB_LIST_SCOPE
        return [FakeScope(self.cards)]


class FakeActions:
    def __init__(self):
        self.clicks = []

    async def human_click(self, x, y):
        assert (x, y) == (250.0, 240.0)
        self.clicks.append((x, y))

    async def random_delay(self, minimum, maximum):
        assert (minimum, maximum) == (1, 3)


class FakeBrowser:
    async def screenshot(self):
        return b"screenshot"

    async def get_page_text(self):
        return "job list"

    async def get_job_url(self):
        return "https://www.linkedin.com/jobs/view/123456/"

    async def get_job_detail_text(self, expected_job_id=None):
        return "A detailed job description " * 10


class FakeVision:
    async def analyze_page(self, screenshot, prompt):
        return {
            "page_type": "job_list",
            "jobs": [
                {
                    "title": "Software Engineer",
                    "company": "Example Co",
                    "salary": "$100k",
                    "location": "Remote",
                    "tags": ["Python"],
                    "click_x": 10,
                    "click_y": 20,
                }
            ],
            "has_next_page": False,
        }


class FakeMatcher:
    async def score_job(self, **kwargs):
        assert kwargs["title"] == "Software Engineer"
        return {
            "score": 8.5,
            "reason": "strong fit",
            "selected_resume": "backend_resume",
            "dimension_scores": {"technical_skills": 9},
            "analysis": "Python experience matches the role.",
        }


class FakeSearchPage:
    def __init__(self):
        self.gotos = []
        self.query_selector_calls = 0

    async def goto(self, url, **kwargs):
        self.gotos.append((url, kwargs))

    async def query_selector(self, selector):
        self.query_selector_calls += 1
        return None


class FakeRunBrowser:
    def __init__(self):
        self.page = FakePage()
        self.closed = False

    async def start(self):
        return self.page

    async def close(self):
        self.closed = True


class FakeInputLoop:
    def __init__(self, values):
        self.values = iter(values)

    async def run_in_executor(self, executor, function):
        return next(self.values)


def test_crawl_and_score_preserves_full_match_result():
    scraper = main.JobScraper.__new__(main.JobScraper)
    scraper.config = {"search": {"max_pages": 1}, "match": {"min_score": 6}}
    scraper.jobs = []
    scraper.actions = FakeActions()
    scraper.browser = FakeBrowser()
    scraper.vision = FakeVision()
    scraper.matcher = FakeMatcher()

    asyncio.run(scraper._crawl_and_score(FakePage()))

    assert scraper.jobs == [
        {
            "title": "Software Engineer",
            "company": "Example Co",
            "salary": "$100k",
            "location": "Remote",
            "tags": ["Python"],
            "description": "A detailed job description " * 10,
            "url": "https://www.linkedin.com/jobs/view/123456/",
            "score": 8.5,
            "reason": "strong fit",
            "selected_resume": "backend_resume",
            "dimension_scores": {"technical_skills": 9},
            "analysis": "Python experience matches the role.",
        }
    ]


def test_search_jobs_uses_manual_linkedin_search(monkeypatch):
    scraper = main.JobScraper.__new__(main.JobScraper)
    scraper.config = {
        "target": {"url": "https://www.linkedin.com/jobs"},
        "search": {"keywords": ["machine learning", "C++"]},
    }
    page = FakeSearchPage()
    waited = []
    prompts = []

    async def fake_wait_for_job_list(current_page):
        waited.append(current_page)

    async def fake_to_thread(function, prompt):
        prompts.append(prompt)

    scraper._wait_for_job_list = fake_wait_for_job_list
    monkeypatch.setattr(main.asyncio, "sleep", _noop_sleep)
    monkeypatch.setattr(main.asyncio, "to_thread", fake_to_thread)

    asyncio.run(scraper._search_jobs(page))

    assert len(page.gotos) == 1
    assert page.query_selector_calls == 0
    assert prompts == ["完成后请在终端按回车继续..."]
    assert len(waited) == 1


def test_wait_for_job_list_failure_only_warns(capsys):
    scraper = main.JobScraper.__new__(main.JobScraper)

    class PageWithoutJobList:
        async def wait_for_selector(self, selector, timeout):
            raise RuntimeError("selector unavailable")

    asyncio.run(scraper._wait_for_job_list(PageWithoutJobList()))

    assert "未检测到明确岗位列表" in capsys.readouterr().out


def test_crawl_waits_for_job_list_after_next_page_click():
    class PagingActions:
        def __init__(self):
            self.clicks = []

        async def human_click(self, x, y):
            self.clicks.append((x, y))

        async def random_delay(self, minimum, maximum):
            assert (minimum, maximum) == (4, 8)

    class PagingBrowser:
        async def screenshot(self):
            return b"screenshot"

        async def get_page_text(self):
            return "job list"

    class PagingVision:
        def __init__(self):
            self.calls = 0

        async def analyze_page(self, screenshot, prompt):
            self.calls += 1
            if self.calls == 1:
                return {
                    "page_type": "job_list",
                    "jobs": [],
                    "has_next_page": True,
                    "next_page_x": 30,
                    "next_page_y": 40,
                }
            return {"page_type": "job_list", "jobs": [], "has_next_page": False}

    scraper = main.JobScraper.__new__(main.JobScraper)
    scraper.config = {"search": {"max_pages": 2}, "match": {"min_score": 6}}
    scraper.jobs = []
    scraper.actions = PagingActions()
    scraper.browser = PagingBrowser()
    scraper.vision = PagingVision()
    wait_calls = []

    async def fake_wait_for_job_list(page):
        wait_calls.append(page)

    scraper._wait_for_job_list = fake_wait_for_job_list

    asyncio.run(scraper._crawl_and_score(FakePage()))

    assert scraper.actions.clicks == [(30.0, 40.0)]
    assert len(wait_calls) == 1


def test_run_yes_starts_next_search_and_q_closes_browser(monkeypatch):
    scraper = main.JobScraper.__new__(main.JobScraper)
    scraper.config = {"behavior": {}}
    scraper.jobs = []
    scraper.browser = FakeRunBrowser()
    search_count = []

    async def fake_search_jobs(page):
        search_count.append(page)

    async def fake_crawl_and_score(page):
        scraper.jobs.append({"title": "temporary"})

    async def fake_save():
        return Path("output/test.json")

    scraper._search_jobs = fake_search_jobs
    scraper._crawl_and_score = fake_crawl_and_score
    scraper._save = fake_save
    scraper._print_top10 = lambda: None
    input_loop = FakeInputLoop(["yes", "q"])
    monkeypatch.setattr(main.asyncio, "get_event_loop", lambda: input_loop)

    asyncio.run(scraper.run())

    assert len(search_count) == 2
    assert scraper.jobs == [{"title": "temporary"}]
    assert scraper.browser.closed is True


async def _noop_sleep(*args, **kwargs):
    return None


def make_scraper():
    scraper = main.JobScraper.__new__(main.JobScraper)
    scraper.config = {"search": {"max_pages": 1}, "match": {"min_score": 6}}
    scraper.jobs = []
    scraper.actions = FakeActions()
    scraper.browser = FakeBrowser()
    scraper.vision = FakeVision()
    scraper.matcher = FakeMatcher()
    return scraper


def test_unique_dom_match_ignores_vision_coordinates_and_wrong_company(monkeypatch):
    monkeypatch.setattr(main.asyncio, "sleep", _noop_sleep)
    scraper = make_scraper()
    card = FakeCard(title="  SOFTWARE\n  Engineer ")
    # FakeVision supplies Example Co; DOM matching does not require that company.
    asyncio.run(scraper._crawl_and_score(FakePage([card])))
    assert scraper.actions.clicks == [(250, 240)]
    assert card.calls == ["scroll", "box"]
    assert scraper.crawl_stats["CORRECT_JOB"] == 1
    assert scraper.crawl_stats["DETAIL_SUCCESS"] == 1


@pytest.mark.parametrize("cards,status", [
    ([], "DOM_RESOLVE_FAILED"),
    ([FakeCard(), FakeCard(identity="999")], "AMBIGUOUS_DOM_MATCH"),
    ([FakeCard(visible=False)], "DOM_RESOLVE_FAILED"),
    ([FakeCard(box=False)], "DOM_RESOLVE_FAILED"),
    ([FakeCard(title="Senior Software Engineer")], "DOM_RESOLVE_FAILED"),
])
def test_dom_failure_skips_without_click_or_scoring(cards, status, monkeypatch):
    monkeypatch.setattr(main.asyncio, "sleep", _noop_sleep)
    scraper = make_scraper()
    asyncio.run(scraper._crawl_and_score(FakePage(cards)))
    assert scraper.actions.clicks == []
    assert scraper.jobs == []
    assert scraper.crawl_stats[status] == 1
    assert scraper.crawl_stats["DETAIL_FAILED"] == 0


@pytest.mark.parametrize("identity", [
    {"job_id": "999"}, {"url": "https://www.linkedin.com/jobs/view/999/"},
    {"href": "https://www.linkedin.com/jobs/search/?currentJobId=999"},
])
def test_identity_disambiguates_duplicate_title(identity):
    scraper = make_scraper()
    first, second = FakeCard(), FakeCard(identity="999")
    result = asyncio.run(scraper._resolve_job_click_coordinates(
        FakePage([first, second]), {"title": "Software Engineer", "company": "wrong", **identity}))
    assert result["status"] == "DOM_RESOLVE_SUCCESS"
    assert result["strategy"] == "identity"
    assert result["target_job_id"] == "999"
    assert first.calls == []
    assert second.calls == ["scroll", "box"]


@pytest.mark.parametrize("identity", [True, [], "bogus", "999"])
def test_invalid_or_missing_identity_never_falls_back_to_title(identity):
    result = asyncio.run(make_scraper()._resolve_job_click_coordinates(
        FakePage(), {"title": "Software Engineer", "job_id": identity}))
    assert result["status"] == "DOM_RESOLVE_FAILED"


def test_wrong_resulting_id_skips_even_if_extractor_url_matches(monkeypatch):
    monkeypatch.setattr(main.asyncio, "sleep", _noop_sleep)
    scraper = make_scraper()
    page = FakePage()
    page.url = "https://www.linkedin.com/jobs/search-results/?currentJobId=999"
    asyncio.run(scraper._crawl_and_score(page))
    assert scraper.crawl_stats["WRONG_JOB_CLICK"] == 1
    assert scraper.crawl_stats["CORRECT_JOB"] == 0
    assert scraper.crawl_stats["DETAIL_SUCCESS"] == 0
    assert scraper.jobs == []


def test_click_without_exception_is_not_detail_success(monkeypatch):
    monkeypatch.setattr(main.asyncio, "sleep", _noop_sleep)
    scraper = make_scraper()

    async def empty_detail(expected_job_id=None):
        return ""

    scraper.browser.get_job_detail_text = empty_detail
    asyncio.run(scraper._crawl_and_score(FakePage()))
    assert scraper.crawl_stats["CORRECT_JOB"] == 1
    assert scraper.crawl_stats["DETAIL_FAILED"] == 1
    assert scraper.jobs == []


def test_title_only_target_records_result_without_claiming_correct_identity(monkeypatch):
    monkeypatch.setattr(main.asyncio, "sleep", _noop_sleep)
    scraper = make_scraper()
    result = asyncio.run(scraper._extract_job_after_dom_click(
        FakePage([FakeCard(identity="")]), {"title": "Software Engineer"}))
    assert result is not None
    assert scraper.crawl_stats["CORRECT_JOB"] == 0
    event = next(e for e in scraper.click_events if e["status"] == "DETAIL_SUCCESS")
    assert event["title"] == "Software Engineer"
    assert (event["x"], event["y"]) == (250, 240)
    assert event["resulting_url"].endswith("currentJobId=123456")
    assert event["detail_text_length"] >= 100


def test_security_challenge_stops_before_any_click(monkeypatch):
    scraper = make_scraper()

    async def blocked(page):
        raise main.AutomationBlocked("MFA")

    with pytest.raises(main.AutomationBlocked):
        asyncio.run(scraper._crawl_and_score(FakePage(), access_check=blocked))
    assert scraper.actions.clicks == []


def test_security_challenge_after_click_stops_without_escape_or_extraction():
    scraper = make_scraper()
    page = FakePage()
    checks = []

    async def check(current_page):
        checks.append(current_page)
        if len(checks) == 2:
            raise main.AutomationBlocked("CAPTCHA")

    async def forbidden(*args):
        pytest.fail("Must stop actions and extraction on security challenge")

    page.keyboard.press = forbidden
    scraper.browser.get_job_detail_text = forbidden
    with pytest.raises(main.AutomationBlocked):
        asyncio.run(scraper._extract_job_after_dom_click(
            page, {"title": "Software Engineer"}, check))
    assert len(scraper.actions.clicks) == 1


def test_missing_list_scope_does_not_match_detail_panel_title():
    class DetailOnlyPage:
        async def query_selector_all(self, selector):
            assert selector == main.JOB_LIST_SCOPE
            return []

    result = asyncio.run(make_scraper()._resolve_job_click_coordinates(
        DetailOnlyPage(), {"title": "Software Engineer"}))
    assert result["status"] == "DOM_RESOLVE_FAILED"


@pytest.mark.parametrize("correct", [True, False])
def test_detail_evidence_only_runs_after_correct_job(correct, monkeypatch):
    monkeypatch.setattr(main.asyncio, "sleep", _noop_sleep)
    scraper = make_scraper()
    page = FakePage()
    if not correct:
        page.url = "https://www.linkedin.com/jobs/search/?currentJobId=999"
    observations = []

    async def observer(current_page, phase, context, text):
        assert scraper.crawl_stats["CORRECT_JOB"] == 1
        assert context["target_job_id"] == "123456"
        assert context["before_click_url"] == page.url
        assert context["after_click_url"] == page.url
        observations.append((phase, text))

    asyncio.run(scraper._crawl_and_score(page, detail_observer=observer))
    if correct:
        assert [phase for phase, text in observations] == ["before_extract", "after_extract"]
        assert observations[0][1] is None
        assert len(observations[1][1]) >= 100
    else:
        assert observations == []
