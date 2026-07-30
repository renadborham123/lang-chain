from scrape_jobs import (
    _clean_listing_url,
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
