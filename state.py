"""LangGraph state and validated domain models."""

from typing import List, Optional, TypedDict

from pydantic import BaseModel, Field


class CVProfile(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    links: List[str] = Field(default_factory=list)
    job_titles: List[str] = Field(default_factory=list)
    seniority: str = "Not specified"
    primary_skills: List[str] = Field(default_factory=list)
    domains: List[str] = Field(default_factory=list)
    years_experience: float = 0
    preferred_location: Optional[str] = None
    is_student: bool = False
    education_level: Optional[str] = None
    graduation_year: Optional[int] = None
    opportunity_types: List[str] = Field(default_factory=list)


class JobPosting(BaseModel):
    id: str
    title: str
    company: str
    location: str
    description: str
    url: str
    source: str = "adzuna"
    opportunity_type: str = "job"


class MatchedJob(BaseModel):
    job: JobPosting
    matched_keywords: List[str]
    match_score: float
    score_breakdown: dict = Field(default_factory=dict)
    match_reasons: List[str] = Field(default_factory=list)


class JobSearchState(TypedDict, total=False):
    user_id: str
    cv_text: str
    document_id: Optional[str]
    refresh_profile: bool
    location_override: Optional[str]
    live_browser: bool
    target_roles: List[str]
    excluded_title_terms: List[str]
    profile: dict
    search_queries: List[str]
    raw_jobs: List[dict]
    new_jobs: List[dict]
    matched_jobs: List[dict]
    final_report: str
    error: Optional[str]
