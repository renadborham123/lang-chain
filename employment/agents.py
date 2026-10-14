"""Evidence-bound AI agents and deterministic fallbacks."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from model_provider import ModelProviderError, invoke_prompt, runtime_models

from .repository import EmploymentRepository, repository


def _json_object(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        raise ValueError("Model did not return a JSON object.")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("Model response must be an object.")
    return value


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#.]{3,}", value.casefold()))


@dataclass
class AgentResult:
    output: dict[str, Any]
    provider: str
    model: str
    confidence: float
    generated: bool


class SupervisorAgent:
    """Routes domain tasks while preserving evidence and human approval boundaries."""

    def __init__(self, repo: EmploymentRepository | None = None) -> None:
        self.repo = repo or repository

    def interview_plan(self, *, title: str, company: str, description: str, profile: dict[str, Any], mode: str, language: str) -> AgentResult:
        facts = json.dumps(profile, ensure_ascii=False, default=str)[:9000]
        evidence = f"Role: {title}\nCompany: {company}\nListing: {description[:9000]}\nCandidate: {facts}"
        fallback_questions = self._fallback_questions(title, company, mode, language)
        fallback = {"summary": f"Practice a {mode} interview for {title} at {company}.", "questions": fallback_questions, "candidate_questions": self._candidate_questions(language), "source_note": "Questions are based on the role context supplied to Wazzefni."}
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are Wazzefni's interview coach. Use only the supplied role and candidate evidence. Never invent candidate achievements or company facts. Return JSON with summary, questions (5 strings), candidate_questions (3 strings), and source_note. Write in Arabic when language is ar, otherwise English."),
            ("human", "{evidence}\nInterview mode: {mode}\nLanguage: {language}"),
        ])
        result = self._invoke("interview", "build_plan", prompt, {"evidence": evidence, "mode": mode, "language": language}, fallback, evidence={"title": title, "company": company, "mode": mode})
        questions = [str(item).strip() for item in result.output.get("questions", []) if str(item).strip()][:7]
        if len(questions) < 3:
            result.output["questions"] = fallback_questions
            result.confidence = min(result.confidence, .65)
        return result

    def evaluate_interview_answer(self, *, question: str, answer: str, duration_seconds: float, evidence: dict[str, Any], language: str) -> AgentResult:
        clean_answer = " ".join(answer.split())
        base = self._deterministic_evaluation(question, clean_answer, duration_seconds, language)
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Evaluate an interview answer using only the supplied question, answer, and confirmed evidence. Do not infer personality, emotion, protected traits, or hiring probability. Return JSON with a scores object containing relevance, structure, evidence, clarity, and conciseness from 0-100; strengths (max 3); improvements (max 3); improved_outline (max 5 steps); and source_note."),
            ("human", "Question: {question}\nAnswer: {answer}\nDuration seconds: {duration}\nConfirmed evidence: {evidence}\nLanguage: {language}"),
        ])
        result = self._invoke("interview", "evaluate_answer", prompt, {"question": question, "answer": clean_answer, "duration": duration_seconds, "evidence": json.dumps(evidence, ensure_ascii=False, default=str)[:7000], "language": language}, base, evidence={"question": question, "answer_length": len(clean_answer)})
        result.output["delivery"] = base["delivery"]
        result.output["safety_note"] = "Delivery feedback uses transcript timing and filler words only; it does not infer emotion or personality."
        return result

    def follow_up_draft(self, application: dict[str, Any], *, language: str = "en") -> AgentResult:
        company = application.get("company") or "the hiring team"
        title = application.get("title") or "the role"
        days = 0
        fallback = {
            "subject": f"Following up — {title}",
            "body": (f"Hello {company} team,\n\nI’m following up on my application for {title}. I remain interested in the role and would be happy to provide any additional information.\n\nBest regards") if language != "ar" else (f"مرحبًا فريق {company}،\n\nأتابع معكم بخصوص طلبي لوظيفة {title}. ما زلت مهتمًا بالفرصة ويسعدني إرسال أي معلومات إضافية.\n\nمع خالص التحية"),
            "send_after_days": 5,
            "source_note": "Draft uses only the application title and company.",
        }
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Write a concise professional application follow-up. Use only supplied facts. Do not claim interviews, deadlines, referrals, or achievements not provided. Return JSON: subject, body, send_after_days, source_note."),
            ("human", "Application: {application}\nLanguage: {language}"),
        ])
        return self._invoke("follow_up", "draft_message", prompt, {"application": json.dumps(application, ensure_ascii=False, default=str)[:7000], "language": language}, fallback, evidence={"application_id": application.get("id"), "company": company, "title": title})

    def negotiation_draft(self, offer: dict[str, Any], *, purpose: str = "negotiate", language: str = "en") -> AgentResult:
        company = offer.get("company") or "the company"
        title = offer.get("title") or "the role"
        salary = offer.get("base_salary")
        currency = offer.get("currency") or ""
        stated_salary = f"{salary:g} {currency}" if isinstance(salary, (int, float)) else "Not stated"
        if purpose == "accept":
            body = f"Thank you for the offer for {title}. I’m pleased to accept and look forward to joining {company}. Please share the next steps and final documents."
        elif purpose == "decline":
            body = f"Thank you for the offer for {title} and for the time invested in the process. After careful consideration, I need to decline. I appreciate the opportunity and hope we can stay in touch."
        else:
            body = f"Thank you for the offer for {title}. I’m excited about the opportunity. Before I confirm, could we discuss the compensation package and whether there is flexibility in the base salary?"
        fallback = {"subject": f"{title} offer — {purpose}", "body": body, "stated_compensation": stated_salary, "questions": ["Could you confirm the complete compensation and benefits package?", "Could you confirm the start date, probation period, and notice terms?"], "source_note": "No market benchmark or unstated compensation was added."}
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Draft an offer response using only the supplied structured offer. Never invent market salary, competing offers, leverage, or benefits. Return JSON: subject, body, stated_compensation, questions, source_note. The user must approve before sending."),
            ("human", "Purpose: {purpose}\nOffer: {offer}\nLanguage: {language}"),
        ])
        return self._invoke("offer", f"draft_{purpose}", prompt, {"purpose": purpose, "offer": json.dumps(offer, ensure_ascii=False, default=str)[:8000], "language": language}, fallback, evidence={"offer_id": offer.get("id"), "company": company, "title": title, "base_salary": salary, "currency": currency})

    def classify_recruiting_message(self, *, subject: str, body: str, known_company: str = "") -> AgentResult:
        text = f"{subject}\n{body}".casefold()
        patterns = {
            "offer": ("offer letter", "pleased to offer", "عرض عمل", "يسرنا أن نقدم"),
            "interview": ("interview", "schedule a call", "availability", "مقابلة", "موعد"),
            "assessment": ("assessment", "coding challenge", "take-home", "اختبار", "تقييم"),
            "rejected": ("not moving forward", "other candidates", "unfortunately", "لن نتمكن", "مرشحين آخرين"),
        }
        kind = "reply"
        confidence = .55
        for candidate, markers in patterns.items():
            if any(marker in text for marker in markers):
                kind, confidence = candidate, .9
                break
        output = {"kind": kind, "confidence": confidence, "company": known_company, "requires_review": confidence < .75, "evidence_quote": next((line.strip() for line in body.splitlines() if line.strip()), subject)[:300]}
        self.repo.record_agent_run(agent="communication", task="classify_message", provider="deterministic", model="rules-v1", confidence=confidence, evidence={"subject": subject, "known_company": known_company}, output=output)
        return AgentResult(output=output, provider="deterministic", model="rules-v1", confidence=confidence, generated=False)

    def _invoke(self, agent: str, task: str, prompt: ChatPromptTemplate, variables: dict[str, Any], fallback: dict[str, Any], *, evidence: dict[str, Any]) -> AgentResult:
        settings = runtime_models.public()
        if not str(settings.get("model") or "").strip():
            self.repo.record_agent_run(agent=agent, task=task, provider="deterministic", model="fallback-v1", confidence=.7, evidence=evidence, output=fallback)
            return AgentResult(fallback, "deterministic", "fallback-v1", .7, False)
        try:
            output = _json_object(invoke_prompt(prompt, variables, json_mode=True))
            provider = str(settings.get("provider") or "ollama_local")
            model = str(settings.get("model") or "")
            self.repo.record_agent_run(agent=agent, task=task, provider=provider, model=model, confidence=.85, evidence=evidence, output=output)
            return AgentResult(output, provider, model, .85, True)
        except (ModelProviderError, ValueError, KeyError, json.JSONDecodeError) as exc:
            self.repo.record_agent_run(agent=agent, task=task, provider="deterministic", model="fallback-v1", confidence=.65, evidence=evidence, output=fallback, error=str(exc))
            return AgentResult(fallback, "deterministic", "fallback-v1", .65, False)

    @staticmethod
    def _fallback_questions(title: str, company: str, mode: str, language: str) -> list[str]:
        if language == "ar":
            common = [f"لماذا تهتم بوظيفة {title} في {company}؟", "احكِ عن موقف استخدمت فيه مهارة مرتبطة بهذه الوظيفة.", "صف مشكلة واجهتك وكيف حددت الحل ونفذته.", "كيف ترتب أولوياتك عندما تتعارض المواعيد؟", "ما السؤال الذي تريد طرحه على فريق التوظيف؟"]
        else:
            common = [f"Why are you interested in the {title} role at {company}?", "Tell me about a time you used a skill relevant to this role.", "Describe a problem you faced and how you chose and implemented a solution.", "How do you prioritize when deadlines conflict?", "What would you like to ask the hiring team?"]
        if mode == "technical":
            common[1] = "Walk through a relevant project, your exact contribution, and the trade-offs you made." if language != "ar" else "اشرح مشروعًا مرتبطًا بالوظيفة، مساهمتك الدقيقة، والمفاضلات التي اتخذتها."
        return common

    @staticmethod
    def _candidate_questions(language: str) -> list[str]:
        return (["كيف تقيسون النجاح في أول 90 يومًا؟", "ما أهم تحدٍ سيعمل عليه الشخص في هذا الدور؟", "كيف يحصل أعضاء الفريق على الملاحظات والتوجيه؟"] if language == "ar" else ["How do you measure success in the first 90 days?", "What is the most important challenge this person will work on?", "How do team members receive feedback and mentoring?"])

    @staticmethod
    def _deterministic_evaluation(question: str, answer: str, duration: float, language: str) -> dict[str, Any]:
        words = answer.split()
        word_count = len(words)
        question_overlap = len(_tokens(question) & _tokens(answer))
        has_evidence = any(token in answer.casefold() for token in ("because", "result", "built", "improved", "used", "لأن", "النتيجة", "استخدمت", "طورت"))
        structure_markers = sum(marker in answer.casefold() for marker in ("situation", "task", "action", "result", "first", "then", "موقف", "مهمتي", "قمت", "النتيجة", "أولاً", "ثم"))
        filler_markers = sum(answer.casefold().count(marker) for marker in (" um ", " uh ", " like ", " يعني ", " اممم "))
        pace = round(word_count / (duration / 60), 1) if duration > 5 else None
        scores = {
            "relevance": min(100, 45 + question_overlap * 12),
            "structure": min(100, 45 + structure_markers * 10),
            "evidence": 78 if has_evidence else 42,
            "clarity": 80 if 35 <= word_count <= 220 else 60,
            "conciseness": 88 if 45 <= word_count <= 180 else 62,
        }
        strengths = ["The answer stays focused on the question."] if question_overlap else ["You completed a full response."]
        improvements = []
        if not has_evidence:
            improvements.append("Add one concrete action and a factual result from your experience.")
        if structure_markers < 2:
            improvements.append("Use a clear situation, action, and result structure.")
        if word_count < 35:
            improvements.append("Add enough context to make your contribution understandable.")
        elif word_count > 220:
            improvements.append("Shorten the setup and spend more time on your actions and result.")
        return {"scores": scores, "strengths": strengths, "improvements": improvements[:3], "improved_outline": ["Context", "Your responsibility", "Actions you took", "Factual result", "What you learned"], "delivery": {"word_count": word_count, "words_per_minute": pace, "filler_word_count": filler_markers}, "source_note": "Fallback evaluation uses answer structure, wording, and timing only."}


supervisor = SupervisorAgent()
