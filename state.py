"""
تعريف الـ State بتاع LangGraph + موديلات Pydantic للـ structured output
"""
from typing import TypedDict, List, Optional
from pydantic import BaseModel, Field


# ---------- Pydantic models (structured LLM outputs) ----------

class CVProfile(BaseModel):
    """البروفايل المستخرج من الـ CV بواسطة الـ LLM"""
    full_name: Optional[str] = Field(default=None, description="اسم صاحب الـ CV إن وجد")
    job_titles: List[str] = Field(description="المسميات الوظيفية المناسبة (مثال: Backend Engineer, Data Analyst)")
    seniority: str = Field(description="المستوى: Junior / Mid / Senior / Lead")
    primary_skills: List[str] = Field(description="أهم 10-15 مهارة تقنية/فنية من الـ CV")
    domains: List[str] = Field(description="المجالات (مثال: Fintech, E-commerce, Healthcare)")
    years_experience: float = Field(description="إجمالي سنوات الخبرة التقريبية")
    preferred_location: Optional[str] = Field(default=None, description="الموقع المفضل للعمل إن ذُكر")


class JobPosting(BaseModel):
    """وظيفة واحدة جاية من مصدر البحث"""
    id: str
    title: str
    company: str
    location: str
    description: str
    url: str
    source: str = "adzuna"


class MatchedJob(BaseModel):
    """وظيفة بعد عملية الـ matching"""
    job: JobPosting
    matched_keywords: List[str]
    match_score: float  # 0.0 -> 1.0


# ---------- LangGraph State ----------

class JobSearchState(TypedDict, total=False):
    user_id: str
    cv_text: str
    refresh_profile: bool          # لو True يعيد استخراج البروفايل من الـ CV
    location_override: Optional[str]
    live_browser: bool
    target_roles: List[str]
    excluded_title_terms: List[str]
    profile: dict                  # CVProfile.model_dump()
    search_queries: List[str]
    raw_jobs: List[dict]           # JobPosting.model_dump() list
    new_jobs: List[dict]           # بعد استبعاد اللي اتشافت قبل كده
    matched_jobs: List[dict]       # MatchedJob.model_dump() list
    final_report: str              # الناتج النهائي بصيغة Markdown
    error: Optional[str]
