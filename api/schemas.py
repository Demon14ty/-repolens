"""Pydantic request/response models for the RepoLens HTTP API.

These mirror frontend/lib/types.ts. They contain only analysis output - never
environment variables, tokens or internal error details.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AnalysisStatus = Literal["complete", "partial", "unsupported"]
Confidence = Literal["High", "Medium", "Low", "No reliable answer"]


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    repo_url: str = Field(..., max_length=500)
    refresh: bool = False  # bypass this instance's short-lived cache (Re-analyze)


class QuestionRequest(BaseModel):
    analysis_id: str = Field(..., max_length=200)
    question: str = Field(..., max_length=500)


class ExplainRequest(BaseModel):
    analysis_id: str = Field(..., max_length=200)


# ---------------------------------------------------------------------------
# Shared pieces
# ---------------------------------------------------------------------------


class SourcePreview(BaseModel):
    start_line: int
    lines: list[str]
    truncated: bool  # the cited range is longer than the preview


class Citation(BaseModel):
    path: str
    start_line: int
    end_line: int
    preview: SourcePreview | None = None


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


class Repository(BaseModel):
    owner: str
    name: str
    full_name: str
    description: str
    stars: int
    language: str
    default_branch: str
    html_url: str
    license: str


class Framework(BaseModel):
    name: str
    confidence: str
    evidence: list[str]
    others: list[str]


class ScoreFactor(BaseModel):
    label: str
    points: int
    max_points: int
    reason: str


class BeginnerScore(BaseModel):
    score: int
    label: str
    factors: list[ScoreFactor]


class EntryPoint(BaseModel):
    path: str
    reasons: list[str]
    citations: list[Citation]
    others: list[str]


class LearningStep(BaseModel):
    number: int
    path: str
    category: str
    why: str
    difficulty_label: str
    difficulty_score: int
    minutes: int
    relevant_code: list[str]
    prerequisites: list[int]
    citations: list[Citation]


class FirstThirtyStep(BaseModel):
    number: int
    path: str
    category: str
    minutes: int
    difficulty_label: str
    why: str
    look_for: str
    outcome: str
    citations: list[Citation]


class FirstThirtyPlan(BaseModel):
    steps: list[FirstThirtyStep]
    total_minutes: int
    outcomes: list[str]
    is_limited: bool
    limited_notice: str | None


class ConfusionItem(BaseModel):
    path: str
    category: str
    difficulty: int
    importance: int
    reasons: list[str]


class ConfusionBucket(BaseModel):
    items: list[ConfusionItem]
    total: int


class ConfusionMap(BaseModel):
    start_here: ConfusionBucket
    read_after_basics: ConfusionBucket
    leave_for_later: ConfusionBucket


class SkipItem(BaseModel):
    path: str
    reason: str
    file_count: int


class ReadmeCheck(BaseModel):
    key: str
    label: str
    points: int
    max_points: int
    passed: bool
    evidence: list[str]
    suggestion: str


class ReadmeQuality(BaseModel):
    path: str | None
    score: int
    label: str
    interpretation: str
    notes: list[str]
    checks: list[ReadmeCheck]


class DependencyFile(BaseModel):
    path: str
    packages: list[str]


class Dependencies(BaseModel):
    packages: list[str]
    files: list[DependencyFile]


class FlowStep(BaseModel):
    label: str
    path: str
    detail: str


class ContributionQuest(BaseModel):
    title: str
    difficulty: str
    minutes: int
    problem: str
    why_useful: str
    likely_files: list[str]
    concepts: list[str]
    success_criteria: list[str]
    hint: str
    citations: list[Citation]


class FilesSummary(BaseModel):
    tree_files: int
    downloaded_files: int
    analysed_python_files: int
    python_files_in_tree: int
    scored_files: int
    by_category: dict[str, int]


class AnalysisResponse(BaseModel):
    analysis_id: str
    status: AnalysisStatus
    summary: str
    repository: Repository
    framework: Framework
    beginner_score: BeginnerScore | None
    entry_point: EntryPoint | None
    estimated_minutes: int
    first_30_minutes: FirstThirtyPlan | None
    learning_path: list[LearningStep]
    confusion_map: ConfusionMap
    skip_for_now: list[SkipItem]
    readme_quality: ReadmeQuality | None
    dependencies: Dependencies
    code_flow: list[FlowStep]
    contribution_quest: ContributionQuest | None
    files_summary: FilesSummary
    warnings: list[str]
    limitations: list[str]
    ai_explanations_available: bool


# ---------------------------------------------------------------------------
# Q&A and optional AI explanations
# ---------------------------------------------------------------------------


class QuestionResponse(BaseModel):
    question: str
    intent: str
    answer: str
    confidence: Confidence
    citations: list[Citation]
    limitations: str
    unsupported: bool


class ExplainResponse(BaseModel):
    available: bool
    message: str
    overview: str
    step_explanations: dict[str, str]
    quest_text: dict[str, str]
    warnings: list[str]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    ai_explanations_available: bool


class ErrorBody(BaseModel):
    code: str
    title: str
    message: str
    details: dict[str, str | int] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
