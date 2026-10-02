# RepoLens

> Paste a GitHub repository. Get a reliable onboarding brief.

RepoLens is an evidence-based onboarding coach for unfamiliar Python repositories. Paste a public GitHub URL
and it tells you **what the project does**, **which framework it uses**, **where it starts**, **what to read
first**, **what to skip for now**, **how the main code flows**, **how helpful the README is**, and gives you
**one small first contribution**. You can also ask questions and get answers that cite real files and line
ranges.

Every claim comes from deterministic static analysis (GitHub metadata, the file tree, and Python `ast`
parsing). No LLM is needed. An optional AI layer can reword explanations, and any AI text that cites a file or
line RepoLens can't verify is thrown away.

Version 1 supports **Python repositories only**.

## Features

- **Overview**: one-paragraph summary, framework detection with evidence and confidence, the likely entry
  point with the reasons and source lines behind it, the main code-flow diagram, and caveats
- **Beginner-friendliness score**: a transparent 0–100 heuristic. It is the sum of six factors (README,
  entry point, dependencies, reading difficulty, codebase size, tests), each with its reason
- **First 30 Minutes**: 3–5 files in a fixed order (README → dependencies → entry point → core logic →
  user-facing code), each with a time box, why it matters and what to look for
- **Learning Path**: the full reading order (up to 6 files) with difficulty, reading time, relevant
  functions/classes with line ranges, prerequisites and sources
- **Confusion Map**: files grouped into *Start here*, *Read after basics* and *Skip initially*, plus
  folders and tooling you can ignore at first (CI, Docker, migrations, lock files…)
- **README Review**: a rubric-based README Onboarding Score with strengths, gaps, suggested improvements and
  the headings or lines that earned each point
- **Contribution Quest**: one small task grounded in the code (an empty state for a template loop, input
  validation in a route, a missing unit test, a README section, or a docstring)
- **Ask RepoLens**: deterministic answers about entry points, frameworks, dependencies, tests, databases,
  routes, UI files, setup commands, reading order and code flow. Every citation is checked against the
  analysed files, and you can expand a citation to preview the cited source lines
- **Progress tracking**: reading checkboxes are stored in the browser's `sessionStorage` per repository and
  never call the server

## Architecture

```text
frontend/                   Next.js 16 (App Router, TypeScript, Tailwind CSS v4)
├── app/                    / (landing page) and /analyze?repo=... (analysis workspace)
├── components/             One component per section, plus citations, badges, loading and error states
└── lib/                    api.ts (typed API client), types.ts (mirrors api/schemas.py), utils.ts

api/                        FastAPI app (thin HTTP layer, no business logic)
├── index.py                ASGI entry point `app`: /api/health, /api/analyze, /api/question, /api/explain
├── schemas.py              Pydantic request/response models
├── serializers.py          Analysis dataclasses → JSON, with every citation re-validated
├── errors.py               Structured, user-safe errors
└── cache.py                Short-lived in-memory cache (not storage, see "Serverless state")

services/                   Repository analysis (unchanged pipeline, reused by both UIs)
├── github_service.py       The only module that talks to GitHub (REST API + raw file downloads)
├── repo_analyzer.py        Choose files → analyse → score → build outputs
├── python_analyzer.py      ast facts per file: imports, functions, classes, calls, routes, branches
├── framework_detector.py   Dependency parsing + framework detection with evidence
├── file_classifier.py      documentation / entry_point / routes / models / database / test / …
├── learning_path.py        Reading order, confusion map, skip-for-now list
├── first_30_minutes.py     The short First 30 Minutes plan
├── code_flow.py            Main execution flow from resolved imports/decorators/render calls
├── readme_quality.py       README Onboarding Score
├── challenge_generator.py  One evidence-based Contribution Quest
├── beginner_score.py       Beginner-friendliness score (new)
├── qa_engine.py            Deterministic Q&A with citation validation
└── llm_service.py          Optional: one Claude call + citation validation
models/repo_models.py       Dataclasses shared by everything
utils/                      URL parsing, scoring rules, path helpers
app.py                      The original Streamlit UI (kept for local use)
tests/                      Unit and API tests (no network)
evaluation/                 Real-repository evaluation script
vercel.json                 Vercel Services config: Next.js at /, FastAPI at /api/*
```

Design decisions:

1. **Download and analysis are separated.** `fetch_snapshot` downloads a `RepoSnapshot`, and
   `analyze_snapshot` is a pure function of it. Tests build snapshots by hand, so they need no network.
2. **Evidence first, AI second.** The optional LLM only gets structured facts (never raw source), can't
   choose files, and its output is checked with `unknown_citations()`.
3. **One citation rule everywhere.** Every file/line reference the API returns, whether in Q&A, entry-point
   evidence, learning steps or the quest, is validated against the files RepoLens actually analysed. Anything
   that doesn't verify is dropped, never shown.
4. **The API adds no analysis logic.** `api/` only parses requests, calls `services/`, and serialises the
   results, so the Streamlit app and the web app give identical results.

## Local development

Requires **Python 3.11+** (RepoLens uses the built-in `tomllib`) and **Node.js 20.9+**.

### 1. Backend (FastAPI on http://localhost:8000)

```powershell
cd C:\RepoLens
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env        # optional: add GITHUB_TOKEN
uvicorn api.index:app --reload --port 8000
```

macOS/Linux: `source .venv/bin/activate` and `cp .env.example .env`.

Check it: open http://localhost:8000/api/health. Interactive API docs are at http://localhost:8000/api/docs.

### 2. Frontend (Next.js on http://localhost:3000)

In a second terminal:

```powershell
cd C:\RepoLens\frontend
npm install
copy .env.local.example .env.local   # optional; the default already points at localhost:8000
npm run dev
```

Open http://localhost:3000 and try `https://github.com/miguelgrinberg/microblog`.

During `npm run dev`, the browser calls the API at `http://localhost:8000` directly. The API allows that
origin through CORS by default (only `http://localhost:3000` and `http://127.0.0.1:3000`). To allow other
origins, set `FRONTEND_ORIGIN` (comma-separated).

### Legacy Streamlit UI

The original Streamlit app still works and uses the same services:

```powershell
pip install -r requirements-dev.txt   # includes streamlit
streamlit run app.py
```

Streamlit is intentionally **not** in `requirements.txt`, which keeps it out of the Vercel Python function.

## Environment variables

Backend (`.env` locally, Vercel Project Settings in production). None of these are ever returned by the API.

| Variable | Required | Purpose |
|---|---|---|
| `GITHUB_TOKEN` | Recommended in production | Raises GitHub's API limit from 60 to 5,000 requests/hour. No scopes are needed for public repos. Each analysis uses about 2 API requests; file contents come from `raw.githubusercontent.com`. Without a token, all visitors share the server's 60 requests/hour. |
| `ANTHROPIC_API_KEY` | No | Enables the optional "Explain in plain language" AI layer. `LLM_API_KEY` also works. |
| `LLM_API_KEY` | No | Alias for `ANTHROPIC_API_KEY`. |
| `REPOLENS_MODEL` | No | Model override for the AI layer (default `claude-opus-5`). |
| `FRONTEND_ORIGIN` | No | Comma-separated CORS origins. Not needed on Vercel (same domain). |

Frontend (`frontend/.env.local`):

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Where the browser sends API requests. Leave **empty** in production on Vercel (relative `/api/...` paths). During `npm run dev`, an empty value falls back to `http://localhost:8000`. This value is bundled into browser JavaScript, so never put a secret in any `NEXT_PUBLIC_*` variable. |

## API

All errors use one shape and never include stack traces or upstream response bodies:

```json
{ "error": { "code": "INVALID_REPOSITORY_URL", "title": "Invalid GitHub URL",
             "message": "Enter a public GitHub repository URL such as https://github.com/owner/repository.",
             "details": null } }
```

| Endpoint | Body | Returns |
|---|---|---|
| `GET /api/health` | – | `{ status, version, ai_explanations_available }` |
| `POST /api/analyze` | `{ "repo_url": "...", "refresh": false }` | The full analysis: repository metadata, `status` (`complete` / `partial` / `unsupported`), summary, framework + evidence, beginner score, entry point + citations, First 30 Minutes, learning path, confusion map, skip list, README review, dependencies, code flow, contribution quest, file counts, warnings and limitations. `analysis_id` is `owner/repo`. |
| `POST /api/question` | `{ "analysis_id": "owner/repo", "question": "..." }` | `{ answer, confidence, citations[], limitations, unsupported, intent }`. Each citation has `path`, `start_line`, `end_line` and an optional source `preview`. |
| `POST /api/explain` | `{ "analysis_id": "owner/repo" }` | Optional AI wording. Returns `available: false` (not an error) when no LLM key is set. |

Error codes: `INVALID_REPOSITORY_URL`, `NOT_GITHUB_URL`, `REPOSITORY_NOT_FOUND` (missing *or* private: GitHub
returns 404 for both), `REPOSITORY_INACCESSIBLE`, `EMPTY_REPOSITORY`, `GITHUB_RATE_LIMITED`,
`GITHUB_UNAVAILABLE`, `GITHUB_AUTH_FAILED`, `GITHUB_ERROR`, `INVALID_REQUEST`, `EMPTY_QUESTION`,
`INVALID_ANALYSIS_ID`, `INTERNAL_ERROR`. Repositories without Python code are not an error: they return
`status: "unsupported"` so the README review and Q&A still work.

### Serverless state

There is **no database and no durable server-side session**.

- The browser keeps the analysis result and reading progress in `sessionStorage` for the current tab. A
  refresh in the same tab re-uses it, while a new tab or **Re-analyze** fetches it again.
- The API keeps a short-lived in-memory cache (15 minutes, 8 repositories) per function instance. On Vercel,
  instances are recycled at any time and two requests may hit different instances, so the cache is only an
  optimisation.
- `analysis_id` is just `owner/repo`. When `/api/question` or `/api/explain` lands on an instance without the
  analysis cached, the API re-runs the deterministic analysis from GitHub and answers from it. Answers stay
  correct across cold starts, at the cost of a slower first question.

## Tests

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

The tests cover URL parsing, AST analysis, dependency parsing, framework detection, file classification,
scoring, import resolution, learning paths, the First 30 Minutes plan, README scoring, Q&A and citation
validation, the AI citation checks, GitHub error messages, the Streamlit UI smoke test, the beginner score,
and the HTTP API (`tests/test_api.py`): health, invalid/non-GitHub URLs, mocked success, mocked rate limits
and other GitHub errors, partial/unsupported status, Q&A with valid citations, unsupported questions,
cache-miss re-analysis, CORS configuration, and a check that responses never contain secret values. No test
needs network access.

Frontend checks:

```powershell
cd frontend
npm run lint
npm run build      # also type-checks
```

Evaluation against real repositories (needs network): `python -m evaluation.run_eval`. See
[evaluation/README.md](evaluation/README.md).

## Deploying to Vercel

The repository deploys as **one Vercel project** using
[Vercel Services](https://vercel.com/docs/services). `vercel.json` defines two services on one domain:

- `web`: the Next.js app in `frontend/`, serving every path except `/api/*`
- `api`: the FastAPI app (`api.index:app`) from the repository root, serving `/api/*` as one Python
  function. It installs the root `requirements.txt`, which does not include Streamlit.

Because both share a domain, the browser calls relative `/api/...` paths and no CORS setup is needed.

> Vercel Services is currently marked **Beta** by Vercel. This configuration follows Vercel's documentation
> but has not been deployed from this repository yet. If the import fails, see the fallback below.

Steps:

1. **Push the project to GitHub.**
2. **Import the repository into Vercel**: Vercel dashboard → *Add New…* → *Project* → choose the repository.
   Keep the **Root Directory** at the repository root (`./`), because `vercel.json` lives there and points
   each service at its own folder.
3. **Add environment variables** in *Project Settings → Environment Variables*:
   - `GITHUB_TOKEN`: strongly recommended, since without it every visitor shares 60 GitHub requests/hour
   - `ANTHROPIC_API_KEY` (or `LLM_API_KEY`) and `REPOLENS_MODEL`: only if you want the optional AI layer
   - Do **not** set `NEXT_PUBLIC_API_BASE_URL` (relative paths are correct here), and you do not need
     `FRONTEND_ORIGIN`.
4. **Confirm the build settings.** With `services` in `vercel.json`, the framework for each service comes from
   the file (`nextjs` and `fastapi`). Leave the dashboard's build/output overrides empty.
5. **Deploy.**
6. **Test the API**: open `https://<your-deployment>.vercel.app/api/health` and expect
   `{"status":"ok", ...}`.
7. **Test a real repository**: open the site, paste `https://github.com/miguelgrinberg/microblog`, and
   check the overview, First 30 Minutes and an *Ask RepoLens* question.
8. **Know the serverless limits:**
   - There is no durable server-side session storage. Analyses live in the browser tab, and the server cache
     is per-instance and short-lived.
   - Cached data may not survive cold starts, so the first question after one triggers a re-analysis.
   - GitHub API limits still apply, per token, and are shared by all visitors.
   - Large repositories are partially analysed (at most 60 non-test Python files, 100 KB per file and about
     1.5 MB in total) and are labelled *Partially analysed*.
   - The API function's `maxDuration` is set to 60 seconds in `vercel.json`. Optional AI explanations add
     noticeable latency, so raise `maxDuration` (within your plan's limit) if you enable them.

**Fallback (two projects)**: if Services is unavailable on your account, create two Vercel projects from the
same repository. Use one with Root Directory `frontend` (Next.js) and one with Root Directory `./` for the API
(add `[tool.vercel] entrypoint = "api.index:app"` to a root `pyproject.toml` so Vercel doesn't pick up the
Streamlit `app.py`). Remove the `services`/`rewrites` from `vercel.json`, set `NEXT_PUBLIC_API_BASE_URL` on the
frontend project to the API project's URL, and set `FRONTEND_ORIGIN` on the API project to the frontend's URL.

## Limitations

- Version 1 analyses **Python** code only. Other repositories show metadata, the README review and Q&A, with a
  notice.
- All scores are **heuristic estimates**, not validated measurements. Entry points are labelled "likely".
- **Large repositories are only partly analysed** (limits above). The UI says when this happens.
- Import resolution is static. Dynamic imports, Django's string-based `INSTALLED_APPS`/`urls` wiring and
  plugin systems aren't followed.
- Ask RepoLens supports ten question types and says so, rather than guessing, when a question is outside
  them.
- Analysis and progress are kept only for the current browser tab.

## Future roadmap

- Shareable, durable analysis links (would need storage, deliberately left out of this version)
- Streaming progress from the API, so the loading stages reflect real work
- Change Impact Simulator: pick a function and see its imports, callers, related tests and likely impact
- Tree-sitter for multi-language support
- Several contribution-quest candidates with difficulty levels
