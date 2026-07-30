import json

import nodes


def _job(identifier: str, title: str, opportunity_type: str) -> dict:
    return {
        "id": identifier,
        "title": title,
        "company": "Example",
        "location": "Cairo",
        "description": "Build Python APIs and use Git in an AI team.",
        "url": f"https://jobs.lever.co/example/{identifier}",
        "source": "fixture",
        "opportunity_type": opportunity_type,
    }


def test_profile_detection_does_not_lose_student_status():
    profile = nodes._normalise_profile_data(
        {
            "job_titles": ["AI Engineer"],
            "primary_skills": ["Python"],
            "domains": ["AI"],
            "years_experience": 1,
            "seniority": "Junior",
        },
        "Computer Science student at Cairo University, expected graduation 2027",
    )
    assert profile["is_student"] is True
    assert profile["seniority"] == "Student"
    assert profile["opportunity_types"][:2] == ["internship", "graduate"]


def test_profile_normalises_object_links_and_structured_list_items():
    profile = nodes._normalise_profile_data(
        {
            "full_name": "Abdelrahman Abozena",
            "links": [
                {"name": "LinkedIn", "url": "https://linkedin.com/in/abdelrahman"},
                {"name": "GitHub", "url": "https://github.com/abdelrahman"},
            ],
            "job_titles": [{"title": "AI Engineer"}],
            "primary_skills": [{"skill": "Python"}, "FastAPI"],
            "domains": [{"name": "Artificial Intelligence"}],
            "opportunity_types": [{"type": "internship"}],
        },
        "Computer Science student",
    )
    assert profile["links"] == [
        "https://linkedin.com/in/abdelrahman",
        "https://github.com/abdelrahman",
    ]
    assert profile["job_titles"] == ["AI Engineer"]
    assert profile["primary_skills"] == ["Python", "FastAPI"]


def test_student_internship_ranks_above_equivalent_full_time(monkeypatch):
    jobs = [_job("intern", "AI Engineering Internship", "internship"), _job("job", "Junior AI Engineer", "job")]
    model_result = [
        {"id": "intern", "score": 0.65, "matched_keywords": ["Python", "Git"], "reasons": ["Relevant AI work."]},
        {"id": "job", "score": 0.65, "matched_keywords": ["Python", "Git"], "reasons": ["Relevant AI work."]},
    ]
    monkeypatch.setattr(nodes, "invoke_prompt", lambda *args, **kwargs: json.dumps(model_result))
    result = nodes.match_keywords_node(
        {
            "new_jobs": jobs,
            "profile": {
                "is_student": True,
                "seniority": "Student",
                "primary_skills": ["Python", "Git", "SQL"],
            },
            "target_roles": ["AI Engineer"],
        }
    )
    scores = {item["job"]["id"]: item["match_score"] for item in result["matched_jobs"]}
    assert scores["intern"] > scores["job"]
    assert result["matched_jobs"][0]["score_breakdown"]["career_stage_adjustment"] == 0.22
