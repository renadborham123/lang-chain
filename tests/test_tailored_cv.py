from pypdf import PdfReader

from cv_builder import render_cv_pdf
from document_store import store_cv
from tailored_cv import build_tailored_cv, tailor_cv_text


SOURCE_CV = """Ahmed Ali

CONTACT
ahmed@example.com | Cairo

SUMMARY
Computer science student building practical software projects.

SKILLS
React, SQL, Python, Git

PROJECTS
- Built a React dashboard for student analytics.
- Built a Python API with SQL persistence.

EDUCATION
BSc Computer Science, expected 2027
"""


def test_tailoring_preserves_facts_and_prioritizes_relevant_evidence():
    tailored = tailor_cv_text(
        SOURCE_CV,
        {
            "title": "Python Backend Intern",
            "company": "Example",
            "description": "Build Python APIs and SQL services.",
            "keywords": ["Python", "SQL"],
        },
    )
    assert "Targeting: Python Backend Intern at Example" in tailored
    assert "BSc Computer Science, expected 2027" in tailored
    assert "Built a Python API with SQL persistence." in tailored
    skills_line = next(line for line in tailored.splitlines() if "Python" in line and "React" in line)
    assert skills_line.index("Python") < skills_line.index("React")
    assert tailored.index("Built a React dashboard") < tailored.index("Built a Python API")
    assert "invented" not in tailored.casefold()


def test_each_job_gets_a_cached_ats_pdf():
    source_id = store_cv(
        SOURCE_CV,
        render_cv_pdf(SOURCE_CV),
        source_name="source-cv.pdf",
    )
    job = {
        "title": "Python Backend Intern",
        "company": "Example",
        "description": "Build Python APIs and SQL services.",
        "url": "",
        "keywords": ["Python", "SQL"],
    }
    first = build_tailored_cv(source_id, job)
    second = build_tailored_cv(source_id, job)
    assert first["document_id"] == second["document_id"]
    assert second["cached"] is True
    reader = PdfReader(f"memory/documents/{first['document_id']}.pdf")
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Python Backend Intern" in extracted
    assert 1 <= len(reader.pages) <= 2
