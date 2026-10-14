"""Persistent local storage for user-managed CV text and PDF documents."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from sqlalchemy import select

from config import settings
from employment.database import SessionLocal, init_database
from employment.models import Document, UserProfile, utcnow


_ROOT = Path(__file__).resolve().parent / "memory" / "documents"
_ACTIVE_PATH = Path(__file__).resolve().parent / "memory" / "active_cv.json"
_LOCAL_USER_ID = "local-user"


def _safe_id(document_id: str) -> str:
    try:
        return str(uuid.UUID(document_id))
    except ValueError as exc:
        raise FileNotFoundError("Invalid document id.") from exc


def cleanup_expired_documents() -> None:
    if settings.DOCUMENT_TTL_HOURS <= 0 or not _ROOT.exists():
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
    user_id: str = _LOCAL_USER_ID,
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
    init_database()
    with SessionLocal.begin() as session:
        if session.get(UserProfile, user_id) is None:
            session.add(UserProfile(id=user_id, locale="en", country="EG", profile={}, preferences={}))
            session.flush()
        session.add(Document(
            id=document_id,
            user_id=user_id,
            kind=str(payload.get("kind") or "cv"),
            language=str(payload.get("language") or "en"),
            source_name=source_name,
            text_path=str(_ROOT / f"{document_id}.txt"),
            file_path=str(_ROOT / f"{document_id}.pdf"),
            metadata_json=payload,
            active=False,
        ))
    return document_id


def _owned_document(document_id: str, user_id: str | None = None) -> Document | None:
    init_database()
    with SessionLocal() as session:
        row = session.get(Document, _safe_id(document_id))
        if row is None or (user_id is not None and row.user_id != user_id):
            return None
        session.expunge(row)
        return row


def get_cv_text(document_id: str, user_id: str | None = None) -> str:
    safe_id = _safe_id(document_id)
    row = _owned_document(safe_id, user_id)
    if user_id is not None and row is None:
        raise FileNotFoundError("CV document was not found for this account.")
    _ensure_fresh(safe_id)
    path = Path(row.text_path) if row and row.text_path else _ROOT / f"{safe_id}.txt"
    if not path.is_file():
        raise FileNotFoundError("CV document was not found or has expired.")
    return path.read_text(encoding="utf-8")


def get_cv_pdf_path(document_id: str, user_id: str | None = None) -> Path:
    safe_id = _safe_id(document_id)
    row = _owned_document(safe_id, user_id)
    if user_id is not None and row is None:
        raise FileNotFoundError("CV PDF was not found for this account.")
    _ensure_fresh(safe_id)
    path = Path(row.file_path) if row and row.file_path else _ROOT / f"{safe_id}.pdf"
    if not path.is_file():
        raise FileNotFoundError("CV PDF was not found or has expired.")
    return path


def get_cv_metadata(document_id: str, user_id: str | None = None) -> dict:
    row = _owned_document(document_id, user_id)
    if user_id is not None and row is None:
        return {}
    if row is not None:
        return {**dict(row.metadata_json or {}), "source_name": row.source_name, "active": row.active, "created_at": row.created_at.timestamp() if row.created_at else 0}
    path = _ROOT / f"{_safe_id(document_id)}.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def update_cv_metadata(document_id: str, patch: dict, user_id: str = _LOCAL_USER_ID) -> dict:
    """Merge trusted workflow metadata without changing the source CV file."""
    safe_id = _safe_id(document_id)
    with SessionLocal.begin() as session:
        row = session.get(Document, safe_id)
        if row is None or row.user_id != user_id:
            raise FileNotFoundError("CV document was not found for this account.")
        row.metadata_json = {**dict(row.metadata_json or {}), **dict(patch or {})}
        payload = dict(row.metadata_json)
    metadata_path = _ROOT / f"{safe_id}.json"
    if metadata_path.is_file():
        try:
            stored = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            stored = {}
        metadata_path.write_text(json.dumps({**stored, **dict(patch or {})}, ensure_ascii=False), encoding="utf-8")
    return payload


def set_active_document(document_id: str, user_id: str = _LOCAL_USER_ID) -> dict:
    safe_id = _safe_id(document_id)
    get_cv_text(safe_id, user_id)
    get_cv_pdf_path(safe_id, user_id)
    metadata = get_cv_metadata(safe_id, user_id)
    payload = {
        "document_id": safe_id,
        "source_name": str(metadata.get("source_name") or "Saved CV"),
    }
    with SessionLocal.begin() as session:
        for row in session.scalars(select(Document).where(Document.user_id == user_id, Document.active.is_(True))).all():
            row.active = False
        row = session.get(Document, safe_id)
        if row is None or row.user_id != user_id:
            raise FileNotFoundError("CV document was not found for this account.")
        row.active = True
        row.metadata_json = {**dict(row.metadata_json or {}), "activated_at": utcnow().isoformat()}
    if user_id == _LOCAL_USER_ID:
        _ACTIVE_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def get_active_document(user_id: str = _LOCAL_USER_ID) -> dict | None:
    init_database()
    with SessionLocal() as session:
        row = session.scalar(select(Document).where(Document.user_id == user_id, Document.active.is_(True)).order_by(Document.created_at.desc()))
        if row is not None:
            try:
                get_cv_text(row.id, user_id)
                get_cv_pdf_path(row.id, user_id)
                return {"document_id": row.id, "source_name": row.source_name}
            except FileNotFoundError:
                pass
    if user_id != _LOCAL_USER_ID:
        return None
    if not _ACTIVE_PATH.is_file():
        return None
    try:
        payload = json.loads(_ACTIVE_PATH.read_text(encoding="utf-8"))
        return set_active_document(str(payload.get("document_id") or ""), user_id)
    except (OSError, ValueError, json.JSONDecodeError, FileNotFoundError):
        _ACTIVE_PATH.unlink(missing_ok=True)
        return None


def find_document_by_metadata(*, user_id: str = _LOCAL_USER_ID, **expected: object) -> str | None:
    cleanup_expired_documents()
    init_database()
    with SessionLocal() as session:
        rows = session.scalars(select(Document).where(Document.user_id == user_id).order_by(Document.created_at.desc())).all()
        for row in rows:
            metadata = dict(row.metadata_json or {})
            if all(metadata.get(key) == value for key, value in expected.items()):
                try:
                    get_cv_text(row.id, user_id)
                    get_cv_pdf_path(row.id, user_id)
                    return row.id
                except FileNotFoundError:
                    continue
    # Legacy files predate accounts and belong only to the local workspace. Never
    # allow an authenticated account to discover another workspace's document.
    if user_id != _LOCAL_USER_ID:
        return None
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
    if settings.DOCUMENT_TTL_HOURS > 0 and age > settings.DOCUMENT_TTL_HOURS * 3600:
        raise FileNotFoundError("CV document was not found or has expired.")
