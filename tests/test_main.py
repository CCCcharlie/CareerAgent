import asyncio
from pathlib import Path

import main


class FakeKeyboard:
    async def press(self, key):
        assert key == "Escape"


class FakePage:
    def __init__(self):
        self.keyboard = FakeKeyboard()


class FakeActions:
    async def human_click(self, x, y):
        assert (x, y) == (10.0, 20.0)

    async def random_delay(self, minimum, maximum):
        assert (minimum, maximum) == (1, 3)


class FakeBrowser:
    async def screenshot(self):
        return b"screenshot"

    async def get_page_text(self):
        return "job list"

    async def get_job_url(self):
        return "https://www.linkedin.com/jobs/view/123456/"

    async def get_job_detail_text(self):
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