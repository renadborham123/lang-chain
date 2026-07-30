import nodes


def test_live_mode_forces_playwright_even_when_adzuna_exists(monkeypatch):
    monkeypatch.setattr(nodes.settings, "ADZUNA_APP_ID", "configured")
    monkeypatch.setattr(nodes.settings, "ADZUNA_APP_KEY", "configured")
    monkeypatch.setattr(
        nodes,
        "_playwright_jobs",
        lambda queries, location, live: [
            {
                "id": "pw-1",
                "title": "AI Internship",
                "company": "Example",
                "location": location,
                "description": "Python",
                "url": "https://jobs.lever.co/example/1",
                "source": "playwright",
                "opportunity_type": "internship",
            }
        ],
    )
    monkeypatch.setattr(nodes, "_search_adzuna", lambda *args: (_ for _ in ()).throw(AssertionError("Adzuna should not run")))
    result = nodes.search_jobs_node(
        {
            "profile": {},
            "location_override": "Cairo",
            "search_queries": ["AI internship"],
            "live_browser": True,
            "excluded_title_terms": [],
        }
    )
    assert result["raw_jobs"][0]["source"] == "playwright"


def test_placeholder_adzuna_credentials_are_not_treated_as_configured(monkeypatch):
    monkeypatch.setattr(nodes.settings, "ADZUNA_APP_ID", "your_app_id")
    monkeypatch.setattr(nodes.settings, "ADZUNA_APP_KEY", "your_app_key")
    assert nodes.settings.has_adzuna is False


def test_repeat_search_does_not_hide_previously_seen_jobs(monkeypatch):
    job = {
        "id": "already-seen",
        "title": "AI Internship",
        "company": "Example",
        "location": "Cairo",
        "description": "Python",
        "url": "https://www.linkedin.com/jobs/view/123",
        "source": "linkedin_playwright",
        "opportunity_type": "internship",
    }
    monkeypatch.setattr(nodes.memory, "get_seen_job_ids", lambda user_id: {"already-seen"})
    result = nodes.filter_new_jobs_node({"user_id": "candidate", "raw_jobs": [job]})
    assert result["new_jobs"] == [job]
