"""Short-lived local storage for CV text and PDF documents."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from config import settings


_ROOT = Path(__file__).resolve().parent / "memory" / "documents"
_ACTIVE_PATH = Path(__file__).resolve().parent / "memory" / "active_cv.json"


def _safe_id(document_id: str) -> str:
    try:
        return str(uuid.UUID(document_id))
    except ValueError as exc:
        raise FileNotFoundError("Invalid document id.") from exc


def cleanup_expired_documents() -> None:
    if not _ROOT.exists():
        return
    cutoff = time.time() - settings.DOCUMENT_TTL_HOURS * 3600
    for metadata_path in _ROOT.glob("*.json"):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if float(metadata.get("created_at", 0)) >= cutoff:
                continue
            document_id = metadata_path.stem
            for suffix in (".json", ".txt", ".pdf"):
                (_ROOT / f"{document_id}{suffix}").unlink(missing_ok=True)
        except (OSError, ValueError, json.JSONDecodeError):
            continue


def store_cv(
    text: str,
    pdf_bytes: bytes,
    *,
    source_name: str = "cv.pdf",
    answers: dict | None = None,
    metadata: dict | None = None,
) -> str:
    cleanup_expired_documents()
    _ROOT.mkdir(parents=True, exist_ok=True)
    document_id = str(uuid.uuid4())
    (_ROOT / f"{document_id}.txt").write_text(text, encoding="utf-8")
    (_ROOT / f"{document_id}.pdf").write_bytes(pdf_bytes)
    payload = {
        "created_at": time.time(),
        "source_name": source_name,
        "answers": answers or {},
    }
    payload.update(
        {
            str(key): value
            for key, value in (metadata or {}).items()
            if str(key) not in {"created_at", "source_name", "answers"}
        }
    )
    (_ROOT / f"{document_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    return document_id


def get_cv_text(document_id: str) -> str:
    safe_id = _safe_id(document_id)
    _ensure_fresh(safe_id)
    path = _ROOT / f"{safe_id}.txt"
    if not path.is_file():
        raise FileNotFoundError("CV document was not found or has expired.")
    return path.read_text(encoding="utf-8")


def get_cv_pdf_path(document_id: str) -> Path:
    safe_id = _safe_id(document_id)
    _ensure_fresh(safe_id)
    path = _ROOT / f"{safe_id}.pdf"
    if not path.is_file():
        raise FileNotFoundError("CV PDF was not found or has expired.")
    return path


def get_cv_metadata(document_id: str) -> dict:
    path = _ROOT / f"{_safe_id(document_id)}.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def set_active_document(document_id: str) -> dict:
    safe_id = _safe_id(document_id)
    get_cv_text(safe_id)
    get_cv_pdf_path(safe_id)
    metadata = get_cv_metadata(safe_id)
    payload = {
        "document_id": safe_id,
        "source_name": str(metadata.get("source_name") or "Saved CV"),
    }
    _ACTIVE_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def get_active_document() -> dict | None:
    if not _ACTIVE_PATH.is_file():
        return None
    try:
        payload = json.loads(_ACTIVE_PATH.read_text(encoding="utf-8"))
        return set_active_document(str(payload.get("document_id") or ""))
    except (OSError, ValueError, json.JSONDecodeError, FileNotFoundError):
        _ACTIVE_PATH.unlink(missing_ok=True)
        return None


def find_document_by_metadata(**expected: object) -> str | None:
    cleanup_expired_documents()
    if not _ROOT.is_dir():
        return None
    for path in sorted(_ROOT.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
            if all(metadata.get(key) == value for key, value in expected.items()):
                get_cv_text(path.stem)
                get_cv_pdf_path(path.stem)
                return path.stem
        except (OSError, ValueError, json.JSONDecodeError, FileNotFoundError):
            continue
    return None


def _ensure_fresh(document_id: str) -> None:
    metadata_path = _ROOT / f"{document_id}.json"
    if not metadata_path.is_file():
        raise FileNotFoundError("CV document was not found or has expired.")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        age = time.time() - float(metadata.get("created_at", 0))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise FileNotFoundError("CV document metadata is invalid.") from exc
    if age > settings.DOCUMENT_TTL_HOURS * 3600:
        raise FileNotFoundError("CV document was not found or has expired.")
