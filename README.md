# Wazzefni — وظّفني

**بنجهّزك للشغل، خطوة بخطوة.** A local-first AI qualification and employment
agent that follows the person—not only the application—from diagnosis to proof
and from CV to offer:
readiness, a personal development plan, skill assessment, CV promotion,
discovery, decision support, preparation, reviewed application
automation, reply tracking, follow-up, interview practice, offer comparison, and
outcome learning. It uses Ollama, LangGraph, Playwright, FastAPI, React, and an
event-sourced SQLite store that can move to Postgres without changing services.

The qualification loop is:

`Diagnose → Plan → Learn → Practice → Prove → Update CV → Apply → Measure → Improve`

Readiness is always presented as verified requirement coverage, never as an
acceptance probability. Finishing a course records exposure only; a skill claim
needs evidence, assessment, and explicit approval before it becomes CV-safe.

## Employment OS

The responsive PWA now has dedicated routes for **Your Readiness**,
**Qualification Plan**, **Skill Proof**, **Today**, **Opportunities**,
**Applications**, **Interviews**, **Offers**, **Profile**, and **Settings**.

- **Readiness** separates role coverage, evidence strength, and CV representation.
- **Qualification Plan** turns market gaps into an ordered, persistent to-do list
  and a career ladder from foundations to a realistic junior role.
- **Skill Proof** uses concept, scenario, and project-defence turns. Pass creates
  a reviewable CV proposal; Partial or Not yet creates remediation.
- **Today** ranks the next qualification or application action. Every
  recommendation includes evidence and confidence.
- **Applications** provides Kanban/list tracking and an append-only timeline
  across discovered, preparing, applied, interview, offer, accepted, rejected,
  blocked, and related states. Active browser sessions are checkpointed in the
  repository and reopen as review-first recoverable sessions after a restart.
- **Communications** can synchronize recruiting mail from Gmail or Outlook,
  classify replies, generate contextual follow-ups, and create calendar events.
  Sending and calendar writes require approval for the exact reviewed payload.
- **Interview Copilot** creates job-grounded text/voice practice, transcribes
  locally with faster-whisper, and scores relevance, structure, evidence,
  clarity, and conciseness. It does not infer emotion or personality.
- **Offers** stores stated compensation and terms, refuses unsafe currency
  comparisons, and drafts clarification, negotiation, acceptance, or rejection
  messages behind explicit approval.
- **Telegram** supports signed, short-lived controls for approve, reject,
  snooze, and done. Local mode uses persistent long polling.
- **Provenance** records model/provider, prompt version, evidence, confidence,
  errors, and local/cloud routing for every agent run.

The product optimizes application quality and conversion, not blind application
volume. It never guarantees a job and never submits, sends, schedules, or
responds to an offer without the user's approval.

## Production flows

- Upload a PDF/TXT CV or answer the guided questions to generate a reusable,
  single-column ATS PDF.
- CV generation stays blocked until identity/contact, target, skills, and
  education/project/experience evidence are sufficient.
- Detect student status and prioritise relevant internships, trainee roles,
  and graduate programs while penalising unrealistic seniority.
- Discover public vacancies with Adzuna in background mode or one reusable,
  visible Playwright browser in live mode. A transient LinkedIn navigation
  failure falls through to the browser-based search fallback instead of
  cancelling the whole search.
- Leave target roles blank to derive them from the CV; direct listings are
  deduplicated and category pages or clear seniority mismatches are removed.
- Select any result to get an evidence-bound brief from the live listing,
  including pay, work setup, hours, duration, deadline, and verified job and
  company links when the source provides them. Missing details stay visibly
  marked as not stated instead of being guessed. Any role or company value is
  shown only with an exact supporting quote from that listing.
- Build an acceptance plan from the current CV and current result set. It shows
  live search progress, calculates skill gaps against the roles actually found,
  asks one high-impact question at a time, and quantifies location or salary
  trade-offs only when the current listings contain the supporting data.
- Keep confirmed career answers in `memory/career_answers.json`. Reuse them in
  later applications and create a new factual CV PDF only for explicitly
  confirmed, CV-safe facts; existing CV claims are never rewritten.
- Research selective, source-linked events, fairs, competitions, and meetups
  when external proof would materially help the candidate. Dates, eligibility,
  and availability stay marked for verification rather than being assumed.
- Discover only published contact details or public LinkedIn profile results,
  then produce an editable, review-first outreach draft. Email opens in the
  user's mail client and LinkedIn opens the profile; neither channel is sent
  silently or used to bypass platform restrictions.
- Choose Ollama Local or Ollama Cloud from the UI, refresh available models,
  then select the model used by every AI step.
- Auto-fill text fields, selects, radio groups, and checkboxes, upload the
  stored CV PDF, and verify the employer's submission confirmation.
- Use the selected Ollama model to phrase genuinely missing application
  questions. Answers are kept locally in `memory/application_answers.json`
  and reused on later forms, while the persistent Playwright profile in
  `memory/browser_profiles/job-accounts` keeps job-site login sessions.

No automation bypasses CAPTCHA or invents candidate information. Application
tests use the local fixture in `fixtures/application_form.html`; they never
submit to a real employer.

## Start locally

1. Copy `.env.example` to `.env`.
2. Install dependencies:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m playwright install chromium
   cd frontend
   npm install
   ```

3. Start Ollama and make at least one model available:

   ```powershell
   ollama serve
   ollama pull qwen2.5:7b
   ```

4. Start the API from the repository root:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
   ```

5. Start the UI:

   ```powershell
   cd frontend
   npm run dev -- --host 127.0.0.1
   ```

6. Open `http://127.0.0.1:5173`, choose **Model settings**, refresh the local
   or cloud model list, and save a model.

The first API startup initializes `memory/employment.sqlite`, imports legacy
JSON memory idempotently, and keeps the source files untouched as recovery
copies. CV artifacts remain available until explicit deletion. Persistent
background jobs refresh next actions and poll Telegram.

The same database stores Wazzefni accounts, scrypt password hashes, server-side
session records, password-reset requests, and account-linked profile data.
Browser sessions use an HttpOnly cookie. Set `JOBFLOW_SECURE_COOKIES=true` only
when the public deployment is served over HTTPS. Profile photos are limited to
PNG, JPG, or WebP files up to 5 MB and are stored under `memory/avatars`.

Run schema upgrades explicitly when deploying an existing database:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
```

For Gmail/Google Calendar or Outlook/Outlook Calendar, configure the matching
OAuth client values in `.env` and register the callback URL shown by the UI.
OAuth tokens and the Telegram bot token are stored in the operating-system
keyring, not the SQLite database. `faster-whisper` is only loaded when voice
transcription is used, so the rest of the product remains functional without a
local speech model.

For a single-process production-style run, build `frontend/dist` with
`npm run build`, then start only FastAPI and open `http://127.0.0.1:8000`.
FastAPI serves the built SPA after all `/api` routes.

Ollama Local uses `http://127.0.0.1:11434` and needs no key. Direct Ollama
Cloud uses `https://ollama.com` and an API key. The key is kept only in backend
memory; it is not written to `memory/model_settings.json`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm run build
```

The test suite covers signup/login/logout, protected profiles, account updates,
profile-photo persistence, CV readiness/PDF extraction, student-stage ranking,
provider validation, resilient live-source dispatch, evidence-bound job brief
extraction, acceptance-plan gap and salary calculations, persistent career
memory, factual CV enrichment, source-bound outreach and growth research, and
end-to-end Playwright application flows including generated questions,
persisted answers, multi-step forms, CAPTCHA recovery, uploads, and confirmed
submit. It also covers event-sourced lifecycle transitions, idempotent
approvals, exact-payload calendar approval, interview safety/provenance,
offer-comparison safeguards, and next-best-action evidence.
