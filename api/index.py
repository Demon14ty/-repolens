"""RepoLens HTTP API (FastAPI).

Local:   uvicorn api.index:app --reload --port 8000
Vercel:  the `app` object below is the ASGI entrypoint (see vercel.json).

The API is a thin layer over the existing services: it downloads a repository
with services.github_service, analyses it with services.repo_analyzer, answers
questions with services.qa_engine, and serialises the results. No database,
no accounts, no secrets in responses.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:  # make services/, models/, utils/ importable however the app is started
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402

from api import errors, schemas  # noqa: E402
from api.cache import AnalysisCache, CachedAnalysis  # noqa: E402
from api.serializers import serialize_analysis, serialize_answer, serialize_guide  # noqa: E402
from services.github_service import GitHubClient, GitHubError, fetch_snapshot, github_token  # noqa: E402
from services.llm_service import LLMError, build_llm_context, llm_api_key, request_guide, validate_guide  # noqa: E402
from services.qa_engine import answer_question  # noqa: E402
from services.repo_analyzer import analyze_snapshot, choose_files_to_download  # noqa: E402
from utils.github_parser import InvalidGitHubURL, parse_github_url  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

VERSION = "2.0.0"
LOCAL_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]

logger = logging.getLogger("repolens.api")
cache = AnalysisCache()

app = FastAPI(
    title="RepoLens API",
    version=VERSION,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)


def allowed_origins() -> list[str]:
    """FRONTEND_ORIGIN (comma-separated) wins. Without it, only local dev origins - and none on Vercel,
    where the frontend and API share one domain and need no CORS at all."""
    configured = [o.strip().rstrip("/") for o in os.getenv("FRONTEND_ORIGIN", "").split(",") if o.strip()]
    if configured:
        return configured
    return [] if os.getenv("VERCEL") else LOCAL_ORIGINS


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# ---------------------------------------------------------------------------
# Error handling: always {"error": {...}}, never a stack trace
# ---------------------------------------------------------------------------


def _error_response(error: errors.ApiError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content=error.body())


@app.exception_handler(errors.ApiError)
async def _api_error(_: Request, exc: errors.ApiError) -> JSONResponse:
    return _error_response(exc)


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    fields = sorted({str(e.get("loc", ["", "body"])[-1]) for e in exc.errors()})
    return _error_response(errors.ApiError(
        422, "INVALID_REQUEST", "Invalid request", "The request is missing a field or has a field of the wrong type.",
        {"fields": ", ".join(fields)} if fields else None,
    ))


@app.exception_handler(StarletteHTTPException)
async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 405:
        return _error_response(errors.ApiError(405, "METHOD_NOT_ALLOWED", "Method not allowed",
                                               "This endpoint does not support that HTTP method."))
    if exc.status_code == 404:
        return _error_response(errors.ApiError(404, "NOT_FOUND", "Not found", "There is no API endpoint at this path."))
    return _error_response(errors.unexpected())


@app.exception_handler(Exception)
async def _unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error", exc_info=exc)
    return _error_response(errors.unexpected())


# ---------------------------------------------------------------------------
# Analysis loading (cache first, GitHub on a miss)
# ---------------------------------------------------------------------------


def _cache_key(owner: str, repo: str) -> str:
    return f"{owner}/{repo}".lower()


def load_analysis(owner: str, repo: str, refresh: bool = False) -> CachedAnalysis:
    """Return the analysis for owner/repo. Raises ApiError with a friendly message on failure."""
    key = _cache_key(owner, repo)
    if not refresh and (hit := cache.get(key)):
        return hit
    try:
        snapshot = fetch_snapshot(owner, repo, GitHubClient(token=github_token()), choose_files_to_download)
    except GitHubError as exc:
        raise errors.from_github_error(exc) from exc
    if not snapshot.tree:
        raise errors.empty_repository()
    try:
        analysis = analyze_snapshot(snapshot)
    except Exception as exc:  # a bug in a heuristic must not leak a traceback to the browser
        logger.exception("Analysis failed for %s/%s", owner, repo)
        raise errors.unexpected() from exc
    item = cache.put(key, analysis, snapshot.tree_truncated)
    canonical = analysis.metadata.full_name.lower()
    if canonical != key:  # e.g. the user typed a different letter case or GitHub redirected a rename
        cache.put(canonical, analysis, snapshot.tree_truncated)
    return item


def _parse_analysis_id(analysis_id: str) -> tuple[str, str]:
    try:
        return parse_github_url(f"https://github.com/{analysis_id.strip().strip('/')}")
    except InvalidGitHubURL as exc:
        raise errors.invalid_analysis_id() from exc


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/health", response_model=schemas.HealthResponse)
def health() -> schemas.HealthResponse:
    return schemas.HealthResponse(status="ok", version=VERSION, ai_explanations_available=bool(llm_api_key()))


@app.post("/api/analyze", response_model=schemas.AnalysisResponse,
          responses={code: {"model": schemas.ErrorResponse} for code in (400, 403, 404, 422, 429, 500, 502, 503)})
def analyze(request: schemas.AnalyzeRequest) -> schemas.AnalysisResponse:
    try:
        owner, repo = parse_github_url(request.repo_url)
    except InvalidGitHubURL as exc:
        raise errors.invalid_url(request.repo_url) from exc
    item = load_analysis(owner, repo, refresh=request.refresh)
    analysis_id = item.analysis.metadata.full_name.lower()
    return serialize_analysis(analysis_id, item.analysis, item.tree_truncated, bool(llm_api_key()))


@app.post("/api/question", response_model=schemas.QuestionResponse,
          responses={code: {"model": schemas.ErrorResponse} for code in (400, 404, 422, 429, 500, 502, 503)})
def question(request: schemas.QuestionRequest) -> schemas.QuestionResponse:
    text = request.question.strip()
    if not text:
        raise errors.empty_question()
    owner, repo = _parse_analysis_id(request.analysis_id)
    analysis = load_analysis(owner, repo).analysis
    # answer_question validates every citation against the analysed files before returning.
    return serialize_answer(answer_question(text, analysis), analysis)


@app.post("/api/explain", response_model=schemas.ExplainResponse,
          responses={code: {"model": schemas.ErrorResponse} for code in (400, 404, 429, 500, 502, 503)})
def explain(request: schemas.ExplainRequest) -> schemas.ExplainResponse:
    """Optional AI wording layer. Disabled (not an error) when no LLM key is configured."""
    if not llm_api_key():
        return serialize_guide(None, "AI explanations are not enabled on this server. Everything shown comes from "
                                     "RepoLens's built-in analysis.")
    owner, repo = _parse_analysis_id(request.analysis_id)
    analysis = load_analysis(owner, repo).analysis
    if not analysis.learning_path:
        return serialize_guide(None, "There is not enough analysed code to explain.")
    try:
        data = request_guide(json.dumps(build_llm_context(analysis), sort_keys=True))
    except LLMError as exc:
        return serialize_guide(None, str(exc))
    guide = validate_guide(data, analysis)  # drops any AI text that cites files or lines RepoLens cannot verify
    return serialize_guide(guide, "AI-written from RepoLens evidence. Citations were checked against the analysed files.")
