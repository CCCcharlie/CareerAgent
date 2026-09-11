import asyncio

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