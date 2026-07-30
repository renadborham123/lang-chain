from io import BytesIO

from pypdf import PdfReader

from cv_builder import cv_readiness, normalise_cv_text, render_cv_pdf


def test_readiness_rejects_sparse_answers():
    result = cv_readiness({"identity": "Ahmed"})
    assert result["ready"] is False
    assert result["progress"] < 100
    assert {item["field"] for item in result["missing"]} == {"identity", "goal", "skills", "evidence"}


def test_readiness_requires_defensible_complete_information():
    result = cv_readiness(
        {
            "identity": "Ahmed Ali, ahmed@example.com, Cairo",
            "goal": "Computer science student seeking an AI engineering internship",
            "skills": "Python, SQL, Git, FastAPI",
            "projects": "Built a job matching project using Python, FastAPI, and Playwright for public listings.",
            "education": "BSc Computer Science student, expected graduation in 2027.",
        }
    )
    assert result == {"ready": True, "progress": 100, "missing": []}


def test_pdf_is_parseable_and_keeps_ats_text():
    content = (
        "Ahmed Ali\nCONTACT\nahmed@example.com | Cairo\n"
        "SUMMARY\nComputer science student seeking an internship.\n"
        "SKILLS\n- Python\n- SQL\nEDUCATION\nBSc Computer Science - 2027"
    )
    pdf = render_cv_pdf(content)
    assert pdf.startswith(b"%PDF")
    extracted = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)
    assert "Ahmed Ali" in extracted
    assert "SKILLS" in extracted
    assert "Python" in extracted


def test_model_markdown_is_removed_before_pdf_generation():
    cleaned = normalise_cv_text(
        "**Ahmed Ali**\n\n- **Contact**: ahmed@example.com\n- **Skills**:\n  - Python\n  - SQL"
    )
    assert cleaned == "Ahmed Ali\n\nCONTACT\nahmed@example.com\nSKILLS\n- Python\n- SQL"
