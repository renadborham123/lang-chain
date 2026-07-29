# Jobflow

Local job discovery and CV matching with Gemini, LangGraph, Playwright, FastAPI, and React.

## What it does

- Upload one CV or a batch of up to 10 CVs.
- Runs isolated LangGraph job-search agents in parallel.
- Searches public job pages through Playwright.
- Ranks roles by matched CV keywords and shows up to 10 roles per CV.
- Separates direct vacancies from search/category leads. A direct vacancy can open in a visible local Playwright browser for review.
- Provides a locally generated application draft for review.

The app never fills personal data or submits applications automatically. A person must review the role, choose the data to share, and submit the final form on the job site.

## Start locally

1. Copy `.env.example` to `.env` and set `GOOGLE_API_KEY`.
2. Install Python dependencies: `python -m pip install -r requirements.txt`
3. Start the API: `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`
4. In a second terminal, start the UI:

   ```bash
   cd frontend
   npm install
   npm run dev -- --host 127.0.0.1
   ```

Open `http://localhost:5173`.

## Key modules

- `backend/main.py` — FastAPI upload, discovery, batch, and application-draft endpoints.
- `frontend/` — React user interface.
- `graph.py`, `nodes.py` — LangGraph workflow and Gemini nodes.
- `batch.py` — bounded parallel execution for 10 CVs.
- `scrape_jobs.py` — public job discovery with Playwright.
