import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from application_memory import ApplicationAnswerStore, canonical_answer_key
from apply_agent import ApplicationManager
from cv_builder import render_cv_pdf
from document_store import store_cv


def test_application_answer_keys_normalise_common_ai_synonyms():
    assert canonical_answer_key("work_mode") == "preferred_work_mode"
    assert canonical_answer_key("salary expectations") == "expected_salary"
    assert canonical_answer_key("authorized_to_work") == "work_authorization"


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


def test_missing_answers_are_asked_once_saved_and_reused(tmp_path):
    fixture_dir = Path(__file__).resolve().parents[1] / "fixtures"
    handler = partial(SimpleHTTPRequestHandler, directory=str(fixture_dir))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    document_id = store_cv(
        "Ahmed Ali\nCONTACT\nahmed@example.com\nSKILLS\nPython",
        render_cv_pdf("Ahmed Ali\nCONTACT\nahmed@example.com\nSKILLS\nPython"),
        source_name="test.pdf",
    )
    generated_calls = []

    def questions(fields, **_kwargs):
        generated_calls.append([item["name"] for item in fields])
        keys = {
            "work_authorization": "work_authorization",
            "work_mode": "preferred_work_mode",
            "notice_period": "notice_period",
            "terms_consent": "application_accuracy_consent",
        }
        return [
            {
                "field_id": item["field_id"],
                "memory_key": keys[item["name"]],
                "question": f"Please answer: {item['label']}",
            }
            for item in fields
        ]

    store = ApplicationAnswerStore(tmp_path / "application_answers.json")
    manager = ApplicationManager(answer_store=store, question_generator=questions)
    application_url = f"http://127.0.0.1:{server.server_port}/application_with_questions.html"
    profile = {"full_name": "Ahmed Ali", "email": "ahmed@example.com"}

    def wait_for(session_id, statuses, timeout=25):
        deadline = time.time() + timeout
        snapshot = manager.get(session_id)
        while time.time() < deadline and snapshot["status"] not in statuses:
            time.sleep(0.15)
            snapshot = manager.get(session_id)
        return snapshot

    try:
        first = manager.start(application_url, document_id, profile, auto_submit=True, visible=False)
        first_snapshot = wait_for(first["id"], {"needs_input", "failed"})
        assert first_snapshot["status"] == "needs_input", first_snapshot
        questions_by_key = {
            item["memory_key"]: item for item in first_snapshot["details"]["missing_required"]
        }
        assert set(questions_by_key) == {
            "work_authorization",
            "preferred_work_mode",
            "notice_period",
            "application_accuracy_consent",
        }
        assert questions_by_key["work_authorization"]["options"] == ["Yes", "No"]
        assert questions_by_key["preferred_work_mode"]["options"] == ["Remote", "Hybrid", "On-site"]

        manager.command(
            first["id"],
            "retry",
            {
                "work_authorization": "Yes",
                "preferred_work_mode": "Hybrid",
                "notice_period": "2 weeks",
                "application_accuracy_consent": "Yes",
            },
        )
        submitted = wait_for(first["id"], {"submitted", "failed"})
        assert submitted["status"] == "submitted", submitted
        assert store.count() == 4
        assert len(generated_calls) == 1

        second = manager.start(application_url, document_id, profile, auto_submit=True, visible=False)
        reused = wait_for(second["id"], {"submitted", "needs_input", "failed"})
        assert reused["status"] == "submitted", reused
        assert set(reused["details"]["reused_answers"]) == {
            "work_authorization",
            "preferred_work_mode",
            "notice_period",
            "application_accuracy_consent",
        }
        assert len(generated_calls) == 1
    finally:
        server.shutdown()
