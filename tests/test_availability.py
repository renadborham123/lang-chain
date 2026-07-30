import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from availability import probe_application_urls
from backend import main


def test_http_preflight_distinguishes_open_and_closed_pages():
    fixture_dir = Path(__file__).resolve().parents[1] / "fixtures"
    handler = partial(SimpleHTTPRequestHandler, directory=str(fixture_dir))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        closed = f"{base}/closed_job.html"
        opened = f"{base}/application_form.html"
        result = probe_application_urls([closed, opened])
        assert result[closed] is False
        assert result[opened] is True
    finally:
        server.shutdown()


def test_closed_preflight_result_is_removed_from_job_board(monkeypatch):
    url = "https://www.linkedin.com/jobs/view/123/"
    monkeypatch.setattr(main, "probe_application_urls", lambda urls: {url: False})
    result = main._result_view(
        {
            "profile": {"is_student": True, "seniority": "student"},
            "document_id": "cv-1",
            "raw_jobs": [{"id": "job-1"}],
            "matched_jobs": [
                {
                    "job": {
                        "id": "job-1",
                        "title": "AI Internship",
                        "company": "Example",
                        "location": "Cairo",
                        "description": "Python internship",
                        "url": url,
                        "source": "fixture",
                        "opportunity_type": "internship",
                    },
                    "match_score": 0.8,
                    "matched_keywords": ["Python"],
                    "score_breakdown": {},
                    "match_reasons": ["Student fit"],
                }
            ],
        }
    )
    assert result["jobs"] == []
    assert result["excluded"] == 1
