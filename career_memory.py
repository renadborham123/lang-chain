"""Persistent, document-scoped memory for factual career-coaching answers."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path
from typing import Any


_DEFAULT_PATH = Path(__file__).resolve().parent / "memory" / "career_answers.json"
_CV_SECTIONS = {"SKILLS", "LANGUAGES", "LINKS", "CERTIFICATIONS"}


def _clean_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")[:100]


class CareerMemoryStore:
    """Keep coaching answers with their provenance without silently editing a CV."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else _DEFAULT_PATH
        self._lock = threading.RLock()

    def _read(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"documents": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return {"documents": {}}
        documents = payload.get("documents")
        return {"documents": documents if isinstance(documents, dict) else {}}

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def entries(self, document_id: str, user_id: str | None = None) -> dict[str, dict[str, Any]]:
        if user_id:
            from sqlalchemy import select
            from employment.database import SessionLocal
            from employment.models import CareerFact
            with SessionLocal() as session:
                rows = session.scalars(select(CareerFact).where(CareerFact.user_id == user_id, CareerFact.confirmed.is_(True))).all()
                return {
                    row.fact_key: {
                        "value": row.value,
                        "question": str((row.evidence or {}).get("question") or ""),
                        "kind": row.category,
                        "subject": str((row.evidence or {}).get("subject") or ""),
                        "cv_safe": row.cv_safe,
                        "cv_section": str((row.evidence or {}).get("cv_section") or ""),
                        "updated_at": row.updated_at.timestamp() if row.updated_at else 0,
                    }
                    for row in rows
                    if str(row.value or "").strip()
                }
        with self._lock:
            payload = self._read()
            document = payload["documents"].get(str(document_id), {})
            answers = document.get("answers") if isinstance(document, dict) else {}
            if not isinstance(answers, dict):
                return {}
            return {
                str(key): dict(value)
                for key, value in answers.items()
                if isinstance(value, dict) and str(value.get("value") or "").strip()
            }

    def values(self, document_id: str, user_id: str | None = None) -> dict[str, str]:
        return {
            key: str(item.get("value") or "").strip()
            for key, item in self.entries(document_id, user_id).items()
            if str(item.get("value") or "").strip()
        }

    def remember(
        self,
        document_id: str,
        memory_key: str,
        value: str,
        *,
        question: str = "",
        kind: str = "profile",
        subject: str = "",
        cv_safe: bool = False,
        cv_section: str = "",
        user_id: str | None = None,
    ) -> dict[str, Any]:
        clean_document_id = str(document_id).strip()
        key = _clean_key(memory_key)
        clean_value = re.sub(r"\s+", " ", str(value)).strip()
        clean_section = str(cv_section).strip().upper()
        if not clean_document_id or not key or not clean_value:
            raise ValueError("A document, stable answer key, and non-empty value are required.")
        if clean_section and clean_section not in _CV_SECTIONS:
            raise ValueError("Unsupported CV section for a remembered answer.")
        entry = {
            "value": clean_value[:1000],
            "question": re.sub(r"\s+", " ", str(question)).strip()[:500],
            "kind": _clean_key(kind) or "profile",
            "subject": re.sub(r"\s+", " ", str(subject)).strip()[:120],
            "cv_safe": bool(cv_safe and clean_section),
            "cv_section": clean_section if cv_safe else "",
            "updated_at": time.time(),
        }
        if user_id:
            from employment.repository import repository
            saved = repository.upsert_fact(
                key,
                clean_value,
                category=entry["kind"],
                source="user_confirmed",
                evidence={
                    "question": entry["question"],
                    "subject": entry["subject"],
                    "cv_section": entry["cv_section"],
                    "document_id": clean_document_id,
                },
                confirmed=True,
                cv_safe=entry["cv_safe"],
                user_id=user_id,
            )
            return {"memory_key": key, **entry, "id": saved["id"]}
        with self._lock:
            payload = self._read()
            document = payload["documents"].setdefault(clean_document_id, {"answers": {}})
            answers = document.setdefault("answers", {})
            answers[key] = entry
            self._write(payload)
        return {"memory_key": key, **entry}

    def known_skills(self, document_id: str, user_id: str | None = None) -> list[str]:
        skills: list[str] = []
        for item in self.entries(document_id, user_id).values():
            if item.get("kind") != "skill_evidence":
                continue
            answer = str(item.get("value") or "").casefold()
            subject = str(item.get("subject") or "").strip()
            if subject and (answer.startswith("yes") or answer.startswith("used")):
                skills.append(subject)
        return list(dict.fromkeys(skills))

    def cv_facts(self, document_id: str, user_id: str | None = None) -> dict[str, list[str]]:
        facts: dict[str, list[str]] = {section: [] for section in _CV_SECTIONS}
        for key, item in self.entries(document_id, user_id).items():
            if not item.get("cv_safe"):
                continue
            section = str(item.get("cv_section") or "").upper()
            value = str(item.get("value") or "").strip()
            subject = str(item.get("subject") or "").strip()
            if section not in facts or not value:
                continue
            if item.get("kind") == "skill_evidence":
                if not (value.casefold().startswith("yes") or value.casefold().startswith("used")):
                    continue
                line = subject
            elif key == "english_proficiency":
                if value.casefold() in {"not sure", "prefer not to say"}:
                    continue
                line = f"English — {value}"
            else:
                line = value
            if line and line not in facts[section]:
                facts[section].append(line)
        return {section: lines for section, lines in facts.items() if lines}

    def revision(self, document_id: str, user_id: str | None = None) -> str:
        encoded = json.dumps(self.entries(document_id, user_id), sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]

    def copy(self, source_document_id: str, target_document_id: str, user_id: str | None = None) -> None:
        if user_id:
            return
        with self._lock:
            payload = self._read()
            source = payload["documents"].get(str(source_document_id))
            if isinstance(source, dict):
                payload["documents"][str(target_document_id)] = json.loads(json.dumps(source))
                self._write(payload)


career_memory = CareerMemoryStore()
