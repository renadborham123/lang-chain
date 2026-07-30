# Jobflow

Local-first job discovery, student-aware semantic ranking, ATS CV generation,
and reviewed application automation using Ollama, LangGraph, Playwright,
FastAPI, and React.

## Production flows

- Upload a PDF/TXT CV or answer the guided questions to generate a reusable,
  single-column ATS PDF.
- CV generation stays blocked until identity/contact, target, skills, and
  education/project/experience evidence are sufficient.
- Detect student status and prioritise relevant internships, trainee roles,
  and graduate programs while penalising unrealistic seniority.
- Discover public vacancies with Adzuna in background mode or one reusable,
  visible Playwright browser in live mode.
- Choose Ollama Local or Ollama Cloud from the UI, refresh available models,
  then select the model used by every AI step.
- Auto-fill supported application forms, upload the stored CV PDF, report
  missing factual answers/login/CAPTCHA, and submit only after explicit
  confirmation.

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

The test suite covers CV readiness/PDF extraction, student-stage ranking,
provider validation, live-source dispatch, and an end-to-end Playwright
auto-apply against a local form.
