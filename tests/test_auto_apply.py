import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from apply_agent import ApplicationManager
from cv_builder import render_cv_pdf
from document_store import store_cv


def test_auto_apply_fills_uploads_and_submits_fixture():
    fixture_dir = Path(__file__).resolve().parents[1] / "fixtures"
    handler = partial(SimpleHTTPRequestHandler, directory=str(fixture_dir))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    document_id = store_cv(
        "Ahmed Ali\nCONTACT\nahmed@example.com\nSKILLS\nPython",
        render_cv_pdf("Ahmed Ali\nCONTACT\nahmed@example.com\nSKILLS\nPython"),
        source_name="test.pdf",
    )
    manager = ApplicationManager()
    try:
        session = manager.start(
            f"http://127.0.0.1:{server.server_port}/application_form.html",
            document_id,
            {
                "full_name": "Ahmed Ali",
                "email": "ahmed@example.com",
                "phone": "+201001234567",
                "links": ["https://linkedin.com/in/ahmed"],
            },
            auto_submit=True,
            visible=False,
        )
        deadline = time.time() + 30
        snapshot = session
        while time.time() < deadline and snapshot["status"] not in {"submitted", "failed"}:
            time.sleep(0.2)
            snapshot = manager.get(session["id"])
        assert snapshot["status"] == "submitted", snapshot
        assert snapshot["details"]["cv_uploaded"] is True
        assert len(snapshot["details"]["filled_fields"]) >= 4
    finally:
        server.shutdown()


def test_closed_job_is_not_submitted():
    fixture_dir = Path(__file__).resolve().parents[1] / "fixtures"
    handler = partial(SimpleHTTPRequestHandler, directory=str(fixture_dir))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    document_id = store_cv(
        "Ahmed Ali\nCONTACT\nahmed@example.com",
        render_cv_pdf("Ahmed Ali\nCONTACT\nahmed@example.com"),
        source_name="test.pdf",
    )
    manager = ApplicationManager()
    try:
        session = manager.start(
            f"http://127.0.0.1:{server.server_port}/closed_job.html",
            document_id,
            {"full_name": "Ahmed Ali", "email": "ahmed@example.com"},
            auto_submit=True,
            visible=False,
        )
        deadline = time.time() + 20
        snapshot = session
        while time.time() < deadline and snapshot["status"] not in {"unavailable", "failed"}:
            time.sleep(0.2)
            snapshot = manager.get(session["id"])
        assert snapshot["status"] == "unavailable", snapshot
    finally:
        server.shutdown()


def test_auto_apply_advances_through_multiple_steps():
    fixture_dir = Path(__file__).resolve().parents[1] / "fixtures"
    handler = partial(SimpleHTTPRequestHandler, directory=str(fixture_dir))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    document_id = store_cv(
        "Ahmed Ali\nCONTACT\nahmed@example.com",
        render_cv_pdf("Ahmed Ali\nCONTACT\nahmed@example.com"),
        source_name="test.pdf",
    )
    manager = ApplicationManager()
    try:
        session = manager.start(
            f"http://127.0.0.1:{server.server_port}/multi_step_application.html",
            document_id,
            {"full_name": "Ahmed Ali", "email": "ahmed@example.com"},
            auto_submit=True,
            visible=False,
        )
        deadline = time.time() + 20
        snapshot = session
        while time.time() < deadline and snapshot["status"] not in {"submitted", "failed"}:
            time.sleep(0.2)
            snapshot = manager.get(session["id"])
        assert snapshot["status"] == "submitted", snapshot
        assert snapshot["details"]["cv_uploaded"] is True
    finally:
        server.shutdown()


def test_auto_apply_resumes_after_human_verification_disappears():
    fixture_dir = Path(__file__).resolve().parents[1] / "fixtures"
    handler = partial(SimpleHTTPRequestHandler, directory=str(fixture_dir))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    document_id = store_cv(
        "Ahmed Ali\nCONTACT\nahmed@example.com",
        render_cv_pdf("Ahmed Ali\nCONTACT\nahmed@example.com"),
        source_name="test.pdf",
    )
    manager = ApplicationManager()
    try:
        session = manager.start(
            f"http://127.0.0.1:{server.server_port}/captcha_then_application.html",
            document_id,
            {"full_name": "Ahmed Ali", "email": "ahmed@example.com"},
            auto_submit=True,
            visible=False,
        )
        deadline = time.time() + 20
        snapshot = session
        while time.time() < deadline and snapshot["status"] not in {"submitted", "failed"}:
            time.sleep(0.2)
            snapshot = manager.get(session["id"])
        assert snapshot["status"] == "submitted", snapshot
    finally:
        server.shutdown()
