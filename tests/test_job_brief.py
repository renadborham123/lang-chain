import json

import requests
from fastapi.testclient import TestClient

import job_brief
from backend.main import app


class _FakeResponse:
    def __init__(self, text: str, url: str = "https://jobs.example.com/backend-intern") -> None:
        self.text = text
        self.url = url
        self.headers = {"content-type": "text/html; charset=utf-8"}

    def raise_for_status(self) -> None:
        return None


def test_job_brief_uses_listing_schema_and_never_invents_missing_facts(monkeypatch):
    schema = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Backend Engineering Intern",
        "description": (
            "This is a paid six month internship. Work 20 hours per week. "
            "You will build REST APIs and write tests with the product team."
        ),
        "employmentType": "INTERN",
        "jobLocationType": "TELECOMMUTE",
        "datePosted": "2026-09-10",
        "validThrough": "2026-10-15",
        "baseSalary": {
            "currency": "EGP",
            "value": {"minValue": 6000, "maxValue": 8000, "unitText": "MONTH"},
        },
        "jobLocation": {
            "@type": "Place",
            "address": {"addressLocality": "Cairo", "addressCountry": "Egypt"},
        },
        "responsibilities": "Build REST APIs. Write automated tests.",
        "qualifications": "Comfortable with Python and Git.",
        "hiringOrganization": {
            "@type": "Organization",
            "name": "Example Labs",
            "sameAs": "https://example.com",
            "industry": "Financial technology",
        },
    }
    html = f'<html><head><script type="application/ld+json">{json.dumps(schema)}</script></head><body></body></html>'
    monkeypatch.setattr(job_brief.requests, "get", lambda *args, **kwargs: _FakeResponse(html))
    monkeypatch.setattr(
        job_brief,
        "invoke_prompt",
        lambda *args, **kwargs: json.dumps(
            {
                "summary": "A paid backend internship focused on REST APIs and automated tests.",
                "responsibilities": ["Build REST APIs", "Write automated tests"],
                "requirements": ["Comfortable with Python and Git", "Five years of Kubernetes experience"],
                "company_snapshot": "Example Labs is listed as a financial technology employer.",
                "signals": [
                    {"trait": "Collaborative delivery", "evidence_quote": "with the product team"},
                    {"trait": "Invented culture", "evidence_quote": "We are one big family"},
                ],
            }
        ),
    )

    result = job_brief.build_job_brief(
        {
            "title": "Backend Engineering Intern",
            "company": "Example Labs",
            "location": "Cairo",
            "description": "",
            "url": "https://jobs.example.com/backend-intern?tracking=1",
            "opportunity_type": "internship",
        }
    )

    assert result["facts"]["salary"] == "EGP 6,000–8,000 / month"
    assert result["facts"]["schedule"] == "20 hours per week"
    assert result["facts"]["duration"] == "six month"
    assert result["facts"]["work_mode"] == "Remote"
    assert result["facts"]["employment_type"] == "Internship"
    assert result["company"]["url"] == "https://example.com"
    assert result["company"]["industry"] == "Financial technology"
    assert result["listing_url"] == "https://jobs.example.com/backend-intern"
    assert result["generated"] is True
    assert "experience" not in result["summary"].casefold()
    assert result["requirements"] == ["Comfortable with Python and Git"]
    assert result["listing_signals"] == [
        {"trait": "Collaborative delivery", "evidence_quote": "with the product team"}
    ]


def test_job_brief_falls_back_to_supplied_evidence_when_page_and_model_fail(monkeypatch):
    def fail_request(*args, **kwargs):
        raise requests.RequestException("offline")

    monkeypatch.setattr(job_brief.requests, "get", fail_request)
    monkeypatch.setattr(job_brief, "_fetch_listing_browser", lambda url: {})
    monkeypatch.setattr(job_brief, "invoke_prompt", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))

    result = job_brief.build_job_brief(
        {
            "title": "Support Engineer",
            "company": "Example",
            "location": "Alexandria",
            "description": "Part-time hybrid role. Work 24 hours per week supporting customer integrations.",
            "url": "https://example.com/jobs/support",
            "opportunity_type": "job",
        }
    )

    assert result["generated"] is False
    assert result["facts"]["employment_type"] == "Part-time"
    assert result["facts"]["work_mode"] == "Hybrid"
    assert result["facts"]["schedule"] == "24 hours per week"
    assert result["facts"]["salary"] == ""
    assert "no facts were added or guessed" in result["source_note"]


def test_job_brief_endpoint(monkeypatch):
    monkeypatch.setattr(
        "backend.main.build_job_brief",
        lambda payload: {"summary": f"Brief for {payload['title']}", "facts": {}, "company": {}},
    )
    response = TestClient(app).post(
        "/api/job-brief",
        json={"title": "Backend Engineer", "url": "https://example.com/jobs/1"},
    )
    assert response.status_code == 200
    assert response.json()["summary"] == "Brief for Backend Engineer"
