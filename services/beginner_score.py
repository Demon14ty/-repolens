"""Beginner-friendliness score: one transparent 0-100 heuristic for the whole repository.

It only combines facts the analysis already produced, and every point comes with
a reason, in the same spirit as utils/scoring.py:
  README onboarding score     up to 30
  Clear entry point           up to 15
  Declared dependencies       up to 10
  Learning-path difficulty    up to 25 (easier files score higher)
  Codebase size               up to 10 (fewer analysed Python files score higher)
  Tests present               up to 10
This is a RepoLens estimate, not a validated measurement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from models.repo_models import RepoAnalysis
from services.file_classifier import is_test_path

README_POINTS = 30
ENTRY_POINTS_DIRECT = 15
ENTRY_POINTS_NAME_ONLY = 8
DEPENDENCY_POINTS = 10
DIFFICULTY_POINTS = 25
TEST_POINTS = 10
# (max analysed Python files, points, reason)
SIZE_RULES = (
    (15, 10, "Small codebase ({n} analysed Python files)"),
    (40, 6, "Medium-sized codebase ({n} analysed Python files)"),
    (float("inf"), 3, "Large codebase ({n} analysed Python files)"),
)
CODE_STEP_CATEGORIES = {"entry_point", "routes", "models", "database", "core_logic", "ui", "utility"}


@dataclass
class ScoreFactor:
    label: str
    points: int
    max_points: int
    reason: str


@dataclass
class BeginnerScore:
    score: int
    label: str
    factors: list[ScoreFactor] = field(default_factory=list)


def score_label(score: int) -> str:
    if score >= 75:
        return "Very approachable"
    if score >= 55:
        return "Approachable"
    if score >= 35:
        return "Some ramp-up needed"
    return "Steep learning curve"


def beginner_friendliness(analysis: RepoAnalysis) -> BeginnerScore | None:
    """Return the score, or None when there is no Python application code to judge."""
    if not analysis.python_files:
        return None
    factors = [
        _readme_factor(analysis),
        _entry_factor(analysis),
        _dependency_factor(analysis),
        _difficulty_factor(analysis),
        _size_factor(analysis),
        _test_factor(analysis),
    ]
    total = max(0, min(100, sum(f.points for f in factors)))
    return BeginnerScore(score=total, label=score_label(total), factors=factors)


def _readme_factor(analysis: RepoAnalysis) -> ScoreFactor:
    quality = analysis.readme_quality
    score = quality.score if quality else 0
    points = round(score * README_POINTS / 100)
    reason = f"README onboarding score is {score}/100" if quality and quality.path else "No README at the root"
    return ScoreFactor("README onboarding", points, README_POINTS, reason)


def _entry_factor(analysis: RepoAnalysis) -> ScoreFactor:
    if not analysis.entry_points:
        return ScoreFactor("Clear entry point", 0, ENTRY_POINTS_DIRECT, "No likely entry point was found")
    entry = analysis.entry_points[0]
    info = analysis.python_files.get(entry)
    insight = analysis.files.get(entry)
    direct = bool(info and (info.has_main_guard or any(":" in r for r in (insight.entry_reasons if insight else []))))
    if direct:
        return ScoreFactor("Clear entry point", ENTRY_POINTS_DIRECT, ENTRY_POINTS_DIRECT,
                           f"`{entry}` contains start-up code RepoLens could see")
    return ScoreFactor("Clear entry point", ENTRY_POINTS_NAME_ONLY, ENTRY_POINTS_DIRECT,
                       f"`{entry}` is likely the entry point, based on its name and location")


def _dependency_factor(analysis: RepoAnalysis) -> ScoreFactor:
    if analysis.dependencies:
        return ScoreFactor("Declared dependencies", DEPENDENCY_POINTS, DEPENDENCY_POINTS,
                           f"{len(analysis.dependencies)} package(s) declared in dependency files")
    return ScoreFactor("Declared dependencies", 0, DEPENDENCY_POINTS, "No parsable dependency file was found")


def _difficulty_factor(analysis: RepoAnalysis) -> ScoreFactor:
    scores = [analysis.files[s.path].difficulty for s in analysis.learning_path
              if s.path in analysis.files and analysis.files[s.path].category in CODE_STEP_CATEGORIES]
    if not scores:
        return ScoreFactor("Reading difficulty", 0, DIFFICULTY_POINTS, "No code files in the learning path to measure")
    average = sum(scores) / len(scores)
    points = round(DIFFICULTY_POINTS * (1 - average / 100))
    return ScoreFactor("Reading difficulty", points, DIFFICULTY_POINTS,
                       f"Learning-path code files average {round(average)}/100 difficulty")


def _size_factor(analysis: RepoAnalysis) -> ScoreFactor:
    count = len(analysis.python_files)
    for limit, points, reason in SIZE_RULES:
        if count <= limit:
            return ScoreFactor("Codebase size", points, SIZE_RULES[0][1], reason.format(n=count))
    return ScoreFactor("Codebase size", 0, SIZE_RULES[0][1], "")  # unreachable: last rule has no limit


def _test_factor(analysis: RepoAnalysis) -> ScoreFactor:
    tests = [p for p in analysis.tree_paths if p.endswith(".py") and is_test_path(p)]
    if tests:
        return ScoreFactor("Tests present", TEST_POINTS, TEST_POINTS, f"{len(tests)} test file(s) found")
    return ScoreFactor("Tests present", 0, TEST_POINTS, "No test files found")
