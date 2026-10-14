import scrape_jobs
from scrape_jobs import (
    _clean_listing_url,
    _listing_matches_location_hint,
    _linkedin_search_url,
    contains_captcha,
    result_looks_inactive,
)
from nodes import classify_opportunity


def test_stale_and_closed_search_results_are_rejected():
    assert result_looks_inactive("LLM Internship", "Posted 8 months ago")
    assert result_looks_inactive("LLM Internship", "منذ ٨ من الشهور")
    assert result_looks_inactive("LLM Internship", "لم نعد نقبل استمارات")


def test_recent_search_results_remain_eligible():
    assert not result_looks_inactive("LLM Internship", "Posted 3 days ago")
    assert not result_looks_inactive("LLM Internship", "منذ أسبوع")


def test_captcha_detection_supports_english_and_arabic():
    assert contains_captcha("Verify you are human")
    assert contains_captcha("تحقق من أنك إنسان")


def test_linkedin_search_is_recent_and_listing_links_are_stable():
    url = _linkedin_search_url("AI Engineer Intern", "Cairo, Egypt")
    assert "linkedin.com/jobs/search/" in url
    assert "f_TPR=r2592000" in url
    assert _clean_listing_url(
        "https://eg.linkedin.com/jobs/view/example-123?position=1&trackingId=abc"
    ) == "https://eg.linkedin.com/jobs/view/example-123"


def test_search_query_does_not_relabel_a_regular_job_as_an_internship():
    assert classify_opportunity("AI Engineer", "2 days ago") == "job"
    assert classify_opportunity("AI Engineer Internship", "2 days ago") == "internship"


def test_foreign_linkedin_country_subdomain_is_rejected_for_cairo_search():
    assert _listing_matches_location_hint("https://eg.linkedin.com/jobs/view/123", "Cairo") is True
    assert _listing_matches_location_hint("https://www.linkedin.com/jobs/view/123", "Cairo") is True
    assert _listing_matches_location_hint("https://ca.linkedin.com/jobs/view/123", "Cairo") is False


def test_linkedin_navigation_failure_falls_back_instead_of_aborting(monkeypatch):
    class Body:
        @staticmethod
        def inner_text():
            return "Search results"

    class Page:
        def goto(self, url, **_kwargs):
            if "linkedin.com/jobs/search" in url:
                raise scrape_jobs.PlaywrightError("net::ERR_HTTP_RESPONSE_CODE_FAILURE")

        @staticmethod
        def locator(_selector):
            return Body()

    class Context:
        @staticmethod
        def new_page():
            return Page()

        @staticmethod
        def close():
            return None

    class Browser:
        @staticmethod
        def new_context(**_kwargs):
            return Context()

        @staticmethod
        def close():
            return None

    class Playwright:
        chromium = None

        def __init__(self):
            self.chromium = self

        def __enter__(self):
            return self

        @staticmethod
        def __exit__(*_args):
            return None

        @staticmethod
        def launch(**_kwargs):
            return Browser()

    monkeypatch.setattr(scrape_jobs, "sync_playwright", Playwright)
    monkeypatch.setattr(
        scrape_jobs,
        "_extract_results",
        lambda *_args: [
            {
                "title": "Backend Developer",
                "url": "https://eg.linkedin.com/jobs/view/123",
                "snippet": "Posted today",
                "location": "Cairo",
                "query": "Backend Developer",
                "source": "duckduckgo_playwright",
                "company": "Example",
            }
        ],
    )
    results = scrape_jobs.scrape_jobs_for_queries(["Backend Developer"], "Cairo", 5, False)
    assert [item["title"] for item in results] == ["Backend Developer"]
