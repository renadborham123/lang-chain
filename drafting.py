"""The application-draft agent; it prepares text but never submits it."""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from nodes import _build_llm


_DRAFT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "Write a concise 90-120 word application note. Use only claims supported by the candidate profile. Do not invent achievements, employers, degrees, or years of experience. Return only the note."),
    ("human", "Candidate profile: {profile}\n\nRole: {title}\nCompany: {company}\nMatched skills: {keywords}"),
])


def draft_application(profile: dict, title: str, company: str, keywords: list[str]) -> str:
    response = (_DRAFT_PROMPT | _build_llm()).invoke({
        "profile": profile,
        "title": title,
        "company": company,
        "keywords": ", ".join(keywords),
    })
    return str(response.content).strip()
