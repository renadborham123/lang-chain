"""Gemini-backed, fact-only CV builder for people without an existing CV."""

from __future__ import annotations

import json

from langchain_core.prompts import ChatPromptTemplate

from nodes import _build_llm


_CV_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "Create an ATS-friendly plain-text CV from the candidate's answers. "
        "Use only information explicitly supplied. Never invent employers, dates, degrees, metrics, certifications, or skills. "
        "If something is missing, omit it rather than guessing. Use clear sections: name/contact, professional summary, skills, experience/projects, education/certifications, links. "
        "Keep the language consistent with the candidate's answers. Return only the finished CV text.",
    ),
    ("human", "Candidate answers:\n{answers}"),
])


def build_cv(answers: dict[str, str]) -> str:
    clean_answers = {key: value.strip() for key, value in answers.items() if value and value.strip()}
    if not clean_answers:
        raise ValueError("Answer at least one CV question before generating a CV.")
    response = (_CV_PROMPT | _build_llm()).invoke({"answers": json.dumps(clean_answers, ensure_ascii=False)})
    return str(response.content).strip()
