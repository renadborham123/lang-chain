"""Persistent, local memory for factual application-form answers."""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Iterable


_DEFAULT_PATH = Path(__file__).resolve().parent / "memory" / "application_answers.json"
_KEY_ALIASES = {
    "work_mode": "preferred_work_mode",
    "work_arrangement": "preferred_work_mode",
    "preferred_work_arrangement": "preferred_work_mode",
    "salary_expectation": "expected_salary",
    "salary_expectations": "expected_salary",
    "expected_compensation": "expected_salary",
    "visa_sponsorship": "sponsorship_required",
    "requires_sponsorship": "sponsorship_required",
    "need_sponsorship": "sponsorship_required",
    "authorized_to_work": "work_authorization",
    "authorised_to_work": "work_authorization",
    "legal_work_authorization": "work_authorization",
    "right_to_work": "work_authorization",
    "notice_period_days": "notice_period",
    "notice_period_weeks": "notice_period",
}


def canonical_answer_key(value: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")
    return _KEY_ALIASES.get(key, key)[:80]


def _normalise_alias(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()


def _aliases_match(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    if min(len(left), len(right)) >= 8 and (left in right or right in left):
        return True
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return False
    return len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens)) >= 0.75


class ApplicationAnswerStore:
    """Small single-user store used by the local Playwright application agent."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else _DEFAULT_PATH
        self._lock = threading.RLock()

    def _read(self) -> dict:
        if not self.path.is_file():
            return {"answers": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return {"answers": {}}
        answers = payload.get("answers")
        return {"answers": answers if isinstance(answers, dict) else {}}

    def _write(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def _database_answers(self, user_id: str) -> dict[str, dict]:
        from sqlalchemy import select
        from employment.database import SessionLocal
        from employment.models import CareerFact
        with SessionLocal() as session:
            rows = session.scalars(select(CareerFact).where(CareerFact.user_id == user_id, CareerFact.category == "application_answer", CareerFact.confirmed.is_(True))).all()
            return {
                row.fact_key: {
                    "value": row.value,
                    "question": str((row.evidence or {}).get("question") or ""),
                    "aliases": list((row.evidence or {}).get("aliases") or []),
                    "updated_at": row.updated_at.timestamp() if row.updated_at else 0,
                }
                for row in rows
                if str(row.value or "").strip()
            }

    def count(self, user_id: str | None = None) -> int:
        if user_id:
            return len(self._database_answers(user_id))
        with self._lock:
            return len(self._read()["answers"])

    def keys(self, user_id: str | None = None) -> list[str]:
        if user_id:
            return sorted(self._database_answers(user_id))
        with self._lock:
            return sorted(self._read()["answers"])

    def values(self, user_id: str | None = None) -> dict[str, str]:
        if user_id:
            return {key: str(item["value"]) for key, item in self._database_answers(user_id).items()}
        with self._lock:
            return {
                key: str(item.get("value") or "")
                for key, item in self._read()["answers"].items()
                if isinstance(item, dict) and str(item.get("value") or "").strip()
            }

    def lookup(self, memory_key: str = "", aliases: Iterable[str] = (), user_id: str | None = None) -> tuple[str, str] | None:
        key = canonical_answer_key(memory_key)
        normalized_aliases = [_normalise_alias(alias) for alias in aliases if _normalise_alias(alias)]
        if user_id:
            answers = self._database_answers(user_id)
            direct = answers.get(key)
            if isinstance(direct, dict) and str(direct.get("value") or "").strip():
                return key, str(direct["value"])
            for stored_key, item in answers.items():
                stored_aliases = [_normalise_alias(alias) for alias in [stored_key, item.get("question", ""), *(item.get("aliases") or [])] if _normalise_alias(alias)]
                if any(_aliases_match(candidate, stored) for candidate in normalized_aliases for stored in stored_aliases):
                    return stored_key, str(item["value"])
            return None
        with self._lock:
            answers = self._read()["answers"]
            direct = answers.get(key)
            if isinstance(direct, dict) and str(direct.get("value") or "").strip():
                return key, str(direct["value"])
            for stored_key, item in answers.items():
                if not isinstance(item, dict) or not str(item.get("value") or "").strip():
                    continue
                stored_aliases = [
                    _normalise_alias(alias)
                    for alias in [stored_key, item.get("question", ""), *(item.get("aliases") or [])]
                    if _normalise_alias(alias)
                ]
                if any(
                    _aliases_match(candidate, stored)
                    for candidate in normalized_aliases
                    for stored in stored_aliases
                ):
                    return stored_key, str(item["value"])
        return None

    def remember(
        self,
        memory_key: str,
        value: str,
        *,
        question: str = "",
        aliases: Iterable[str] = (),
        user_id: str | None = None,
    ) -> str:
        clean_value = str(value).strip()
        alias_values = [str(alias).strip() for alias in aliases if str(alias).strip()]
        key = canonical_answer_key(
            memory_key or question or (alias_values[0] if alias_values else "application_answer")
        )
        if not key or not clean_value:
            raise ValueError("A stable answer key and non-empty value are required.")
        clean_aliases = list(dict.fromkeys(alias_values))[:20]
        if user_id:
            from employment.repository import repository
            repository.upsert_fact(
                key,
                clean_value,
                category="application_answer",
                source="user_confirmed",
                evidence={"question": str(question).strip(), "aliases": clean_aliases},
                confirmed=True,
                cv_safe=False,
                user_id=user_id,
            )
            return key
        with self._lock:
            payload = self._read()
            existing = payload["answers"].get(key) or {}
            payload["answers"][key] = {
                "value": clean_value,
                "question": str(question or existing.get("question") or "").strip(),
                "aliases": list(dict.fromkeys([*(existing.get("aliases") or []), *clean_aliases]))[:20],
                "updated_at": time.time(),
            }
            self._write(payload)
        return key

    def remember_bulk(self, values: dict[str, str], user_id: str | None = None) -> None:
        for key, value in values.items():
            if str(key).strip() and str(value).strip():
                self.remember(str(key), str(value), question=str(key), aliases=[str(key)], user_id=user_id)


application_answers = ApplicationAnswerStore()
