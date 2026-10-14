from qualification import is_direct_listing, qualify_match


def test_direct_listing_detection_uses_the_real_hostname():
    assert is_direct_listing("https://www.linkedin.com/jobs/view/123") is True
    assert is_direct_listing("https://jobs.lever.co/example/backend-123") is True
    assert is_direct_listing("https://example.com/linkedin.com/jobs/view/123") is False
    assert is_direct_listing("https://www.founditgulf.com/job/backend-developer-example-123") is True
    assert is_direct_listing("https://career.luxoft.com/jobs/python-engineer-27325") is True
    assert is_direct_listing("https://example.com/jobs") is False


def test_sparse_but_strong_title_match_is_kept_for_review():
    result = qualify_match(
        {
            "job": {
                "title": "Backend Developer",
                "url": "https://jobs.lever.co/example/backend-123",
            },
            "match_score": 0.31,
            "score_breakdown": {"role_title": 1.0},
            "matched_keywords": [],
            "match_reasons": ["The title matches the candidate's role."],
        },
        {"seniority": "Junior"},
    )
    assert result["status"] == "review"


def test_category_page_and_experience_mismatch_are_excluded():
    category = qualify_match(
        {
            "job": {"title": "Django Jobs", "url": "https://example.com/django-jobs/"},
            "match_score": 0.8,
            "matched_keywords": ["Django"],
        },
        {"years_experience": 3},
    )
    assert category["status"] == "excluded"

    too_senior = qualify_match(
        {
            "job": {
                "title": "Senior Backend Developer",
                "description": "Requires 7 - 9 years of experience.",
                "url": "https://www.founditgulf.com/job/senior-backend-developer-123",
            },
            "match_score": 0.7,
            "matched_keywords": ["Python", "Django"],
            "score_breakdown": {"career_stage_adjustment": -0.18},
        },
        {"years_experience": 3, "seniority": "mid"},
    )
    assert too_senior["status"] == "excluded"

    sparse_senior = qualify_match(
        {
            "job": {
                "title": "Senior Python Backend Engineer",
                "description": "Posted today",
                "url": "https://www.linkedin.com/jobs/view/123",
            },
            "match_score": 0.5,
            "matched_keywords": ["Python"],
            "score_breakdown": {"career_stage_adjustment": -0.18},
        },
        {"years_experience": 3, "seniority": "mid"},
    )
    assert sparse_senior["status"] == "excluded"
