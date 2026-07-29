"""
Long-term memory layer.

بيستخدم langgraph.store.memory.InMemoryStore كـ interface موحّد، لكن بيعمل
persist فعلي على disk (JSON) عشان الذاكرة تفضل موجودة بين الجلسات المختلفة
(زي ما يفتكر الـ LLM بروفايلك وتاريخ الوظائف اللي بعتهالك قبل كده).

في production: استبدل الـ JSON file بـ Postgres/Redis store
(langgraph.store.postgres.PostgresStore) بنفس الـ interface بالظبط.
"""
import json
import os
from threading import RLock
from typing import Optional
from langgraph.store.memory import InMemoryStore

_DATA_DIR = os.path.join(os.path.dirname(__file__), "memory")
_PROFILES_FILE = os.path.join(_DATA_DIR, "profiles.json")
_SEEN_JOBS_FILE = os.path.join(_DATA_DIR, "seen_jobs.json")
_memory_lock = RLock()

os.makedirs(_DATA_DIR, exist_ok=True)


def _load_json(path: str) -> dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class JobMatcherMemory:
    """
    Facade بسيطة فوق LangGraph Store لإدارة:
    1) بروفايل المستخدم (مستخرج مرة واحدة من الـ CV، ويتحدث لو طلب المستخدم)
    2) IDs الوظائف اللي اتبعتت له قبل كده (عشان منكررش نفس الوظيفة)
    """

    def __init__(self):
        # الـ InMemoryStore هنا بيمثل الـ "hot cache" جوه الـ process
        # والـ JSON files هي الـ persistence الفعلي بين التشغيلات
        self.store = InMemoryStore()
        self._profiles = _load_json(_PROFILES_FILE)
        self._seen_jobs = _load_json(_SEEN_JOBS_FILE)

    # ---------- Profile ----------
    def get_profile(self, user_id: str) -> Optional[dict]:
        with _memory_lock:
            return self._profiles.get(user_id)

    def save_profile(self, user_id: str, profile: dict) -> None:
        with _memory_lock:
            self._profiles[user_id] = profile
            _save_json(_PROFILES_FILE, self._profiles)
            self.store.put(("profiles",), user_id, profile)

    # ---------- Seen jobs (لمنع التكرار) ----------
    def get_seen_job_ids(self, user_id: str) -> set:
        with _memory_lock:
            return set(self._seen_jobs.get(user_id, []))

    def mark_jobs_seen(self, user_id: str, job_ids: list[str]) -> None:
        with _memory_lock:
            existing = set(self._seen_jobs.get(user_id, []))
            existing.update(job_ids)
        # نحتفظ بآخر 500 id بس عشان الملف مايكبرش أوي
            self._seen_jobs[user_id] = list(existing)[-500:]
            _save_json(_SEEN_JOBS_FILE, self._seen_jobs)


memory = JobMatcherMemory()
