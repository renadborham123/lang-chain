import json

import outreach
from career_research import discover_growth_opportunities


def test_contact_discovery_returns_only_published_or_source_linked_contacts(monkeypatch):
    monkeypatch.setattr(
        outreach,
        "_fetch_listing",
        lambda url: {
            "final_url": url,
            "anchors": [
                ("mailto:talent@example.com", "Talent team"),
                ("mailto:support@example.com", "Customer support"),
                ("https://www.linkedin.com/in/nora-recruiter", "Nora Hassan"),
            ],
        },
    )
    monkeypatch.setattr(outreach, "public_search", lambda *args, **kwargs: [])

    result = outreach.discover_contacts(
        {"job": {"title": "Backend Intern", "company": "Example", "url": "https://example.com/jobs/1"}}
    )

    assert [contact["channel"] for contact in result["contacts"]] == ["email", "linkedin"]
    assert result["contacts"][0]["destination"] == "talent@example.com"
    assert all(contact["destination"] != "support@example.com" for contact in result["contacts"])
    assert all(contact["verified"] for contact in result["contacts"])


def test_outreach_draft_is_review_first_and_falls_back_without_model(monkeypatch):
    monkeypatch.setattr(outreach, "invoke_prompt", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
    result = outreach.draft_outreach(
        {
            "channel": "email",
            "lead": {"name": "Talent team", "destination": "talent@example.com"},
            "job": {"title": "Backend Intern", "company": "Example"},
            "profile": {"primary_skills": ["Python"]},
            "matched_skills": ["Python"],
        }
    )

    assert result["review_required"] is True
    assert result["generated"] is False
    assert result["mailto_url"].startswith("mailto:talent@example.com")
    assert "Python" in result["message"]


def test_outreach_rejects_an_ai_draft_with_an_unsupplied_candidate_claim(monkeypatch):
    monkeypatch.setattr(
        outreach,
        "invoke_prompt",
        lambda *args, **kwargs: json.dumps(
            {
                "subject": "Backend Intern",
                "message": "Hello. I graduated from Cairo University with an engineering degree. Could you refer me?",
            }
        ),
    )
    result = outreach.draft_outreach(
        {
            "channel": "linkedin",
            "lead": {"name": "Nora", "destination": "https://linkedin.com/in/nora"},
            "job": {"title": "Backend Intern", "company": "Example"},
            "matched_skills": ["Python"],
        }
    )

    assert result["generated"] is False
    assert "Cairo University" not in result["message"]


def test_growth_research_keeps_only_source_linked_relevant_results(monkeypatch):
    monkeypatch.setattr(
        "career_research.public_search",
        lambda *args, **kwargs: [
            {"title": "Cairo Data Hackathon 2026", "url": "https://events.example/hackathon", "snippet": "Student challenge"},
            {"title": "Generic course", "url": "https://example.com/course", "snippet": "Learn online"},
        ],
    )
    result = discover_growth_opportunities(
        {"profile": {"job_titles": ["Data Analyst"]}, "location": "Cairo"}
    )
    assert len(result["items"]) == 1
    assert result["items"][0]["url"] == "https://events.example/hackathon"
    assert "Check the organiser page" in result["items"][0]["verification"]
