"""Convert RepoLens's analysis dataclasses into API response models.

No analysis happens here. The one rule this module adds is about citations:
every file/line reference sent to the browser is re-checked against the files
RepoLens actually analysed (reusing the Q&A engine's validator), and anything
that does not verify is dropped instead of being shown.
"""

from __future__ import annotations

import re

from api import schemas
from models.repo_models import Citation, QAAnswer, QuestionIntent, RepoAnalysis
from services.beginner_score import beginner_friendliness
from services.file_classifier import is_test_path
from services.first_30_minutes import LIMITED_NOTICE
from services.framework_detector import is_dependency_file, parse_dependencies
from services.llm_service import AIGuide
from services.qa_engine import NO_ANSWER, analysed_line_counts, is_valid_citation
from services.repo_analyzer import is_ignored

MAX_PREVIEW_LINES = 40
MAX_CONFUSION_ITEMS = 12
MAX_CONFUSION_REASONS = 3

# "app.py:6", "routes/tasks.py:10-14" or "routes/tasks.py:10–14" inside evidence text.
EVIDENCE_REF = re.compile(r"(?<![\w/.-])([\w./-]+\.[A-Za-z0-9]{1,8}):(\d+)(?:[-–](\d+))?")

LIMITATIONS = [
    "Version 1 analyses Python code only.",
    "Scores, difficulty labels and reading times are heuristic estimates, not validated measurements.",
    "Analysis is static: RepoLens reads the code but never runs it, so dynamic imports and plugin wiring "
    "are not followed.",
    "Large repositories are analysed partially: at most 60 non-test Python files, files up to 100 KB, "
    "and about 1.5 MB of source in total.",
]


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------


class CitationBuilder:
    """Validated citations with short source previews for one analysis."""

    def __init__(self, analysis: RepoAnalysis) -> None:
        self.analysis = analysis
        self.line_counts = analysed_line_counts(analysis)

    def build(self, citation: Citation) -> schemas.Citation | None:
        if not is_valid_citation(citation, self.line_counts):
            return None
        return schemas.Citation(path=citation.path, start_line=citation.start_line, end_line=citation.end_line,
                                preview=self._preview(citation))

    def _preview(self, citation: Citation) -> schemas.SourcePreview | None:
        text = self.analysis.file_contents.get(citation.path)
        if text is None:
            return None
        lines = text.splitlines()[citation.start_line - 1:citation.end_line]
        return schemas.SourcePreview(start_line=citation.start_line, lines=lines[:MAX_PREVIEW_LINES],
                                     truncated=len(lines) > MAX_PREVIEW_LINES)

    def from_evidence(self, items: list[str]) -> list[schemas.Citation]:
        """Parse 'path', 'path:line' or 'path:start-end' strings; unverifiable ones are dropped."""
        found: list[schemas.Citation] = []
        seen: set[tuple[str, int, int]] = set()
        for item in items:
            refs = list(EVIDENCE_REF.finditer(item))
            candidates: list[Citation] = []
            if refs:
                for ref in refs:
                    start = int(ref.group(2))
                    candidates.append(Citation(ref.group(1), start, int(ref.group(3) or start)))
            elif item.strip() in self.line_counts:
                candidates.append(Citation(item.strip(), 1, self.line_counts[item.strip()]))
            for candidate in candidates:
                key = (candidate.path, candidate.start_line, candidate.end_line)
                built = self.build(candidate) if key not in seen else None
                if built:
                    seen.add(key)
                    found.append(built)
        return found


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def analysis_status(analysis: RepoAnalysis, tree_truncated: bool) -> schemas.AnalysisStatus:
    if not analysis.python_files:
        return "unsupported"
    if tree_truncated or _python_files_in_tree(analysis) > len(analysis.python_files):
        return "partial"
    return "complete"


def _python_files_in_tree(analysis: RepoAnalysis) -> int:
    return sum(1 for p in analysis.tree_paths if p.endswith(".py") and not is_test_path(p) and not is_ignored(p))


def serialize_analysis(analysis_id: str, analysis: RepoAnalysis, tree_truncated: bool,
                       ai_available: bool) -> schemas.AnalysisResponse:
    cites = CitationBuilder(analysis)
    meta = analysis.metadata
    return schemas.AnalysisResponse(
        analysis_id=analysis_id,
        status=analysis_status(analysis, tree_truncated),
        summary=build_summary(analysis),
        repository=schemas.Repository(
            owner=meta.owner, name=meta.name, full_name=meta.full_name, description=meta.description,
            stars=meta.stars, language=meta.language, default_branch=meta.default_branch, html_url=meta.html_url,
            license=meta.license,
        ),
        framework=schemas.Framework(name=analysis.framework.name, confidence=analysis.framework.confidence,
                                    evidence=list(analysis.framework.evidence), others=list(analysis.framework.others)),
        beginner_score=_beginner_score(analysis),
        entry_point=_entry_point(analysis, cites),
        estimated_minutes=analysis.estimated_minutes,
        first_30_minutes=_first_30(analysis, cites),
        learning_path=[
            schemas.LearningStep(
                number=s.number, path=s.path,
                category=analysis.files[s.path].category if s.path in analysis.files else "unknown",
                why=s.why, difficulty_label=s.difficulty_label, difficulty_score=s.difficulty_score,
                minutes=s.minutes, relevant_code=list(s.relevant_code), prerequisites=list(s.prerequisites),
                citations=cites.from_evidence(s.evidence),
            )
            for s in analysis.learning_path
        ],
        confusion_map=_confusion_map(analysis),
        skip_for_now=[schemas.SkipItem(path=i.path, reason=i.reason, file_count=i.file_count)
                      for i in analysis.skip_for_now],
        readme_quality=_readme(analysis),
        dependencies=_dependencies(analysis),
        code_flow=[schemas.FlowStep(label=f.label, path=f.path, detail=f.detail) for f in analysis.flow],
        contribution_quest=_quest(analysis, cites),
        files_summary=_files_summary(analysis),
        warnings=list(analysis.notes),
        limitations=list(LIMITATIONS),
        ai_explanations_available=ai_available,
    )


def build_summary(analysis: RepoAnalysis) -> str:
    """One deterministic sentence or two, assembled only from detected facts."""
    meta = analysis.metadata
    count = len(analysis.python_files)
    if not count:
        return (f"{meta.full_name} has no Python application code RepoLens could analyse "
                f"(GitHub reports its main language as {meta.language}).")
    framework = analysis.framework.name
    if framework in ("Not determined",) or framework.startswith("Plain Python"):
        kind = "a Python project with no known framework detected"
    elif framework.startswith("Python CLI"):
        kind = "a Python command-line tool or script"
    else:
        kind = f"a {framework} project"
    text = f"{meta.full_name} looks like {kind}, with {count} Python file{'s' if count != 1 else ''} analysed."
    if analysis.entry_points:
        text += f" It most likely starts in `{analysis.entry_points[0]}`."
    if analysis.learning_path:
        text += (f" The suggested reading path covers {len(analysis.learning_path)} files "
                 f"in about {analysis.estimated_minutes} minutes.")
    return text


def _beginner_score(analysis: RepoAnalysis) -> schemas.BeginnerScore | None:
    result = beginner_friendliness(analysis)
    if result is None:
        return None
    return schemas.BeginnerScore(
        score=result.score, label=result.label,
        factors=[schemas.ScoreFactor(label=f.label, points=f.points, max_points=f.max_points, reason=f.reason)
                 for f in result.factors],
    )


def _entry_point(analysis: RepoAnalysis, cites: CitationBuilder) -> schemas.EntryPoint | None:
    if not analysis.entry_points:
        return None
    path = analysis.entry_points[0]
    insight = analysis.files.get(path)
    reasons = list(insight.entry_reasons) if insight else []
    citations = cites.from_evidence(reasons)
    if not citations:
        citations = cites.from_evidence([path])
    return schemas.EntryPoint(path=path, reasons=reasons, citations=citations, others=analysis.entry_points[1:4])


def _first_30(analysis: RepoAnalysis, cites: CitationBuilder) -> schemas.FirstThirtyPlan | None:
    plan = analysis.first_30_minutes
    if plan is None or not plan.steps:
        return None
    return schemas.FirstThirtyPlan(
        steps=[
            schemas.FirstThirtyStep(
                number=s.number, path=s.path, category=s.category, minutes=s.minutes,
                difficulty_label=s.difficulty_label, why=s.why, look_for=s.look_for, outcome=s.outcome,
                citations=cites.from_evidence(s.evidence),
            )
            for s in plan.steps
        ],
        total_minutes=plan.total_minutes,
        outcomes=list(plan.outcomes),
        is_limited=plan.is_limited,
        limited_notice=LIMITED_NOTICE if plan.is_limited else None,
    )


def _confusion_map(analysis: RepoAnalysis) -> schemas.ConfusionMap:
    def bucket(level: str) -> schemas.ConfusionBucket:
        paths = analysis.confusion_map.get(level, [])
        items = []
        for path in paths[:MAX_CONFUSION_ITEMS]:
            insight = analysis.files[path]
            items.append(schemas.ConfusionItem(
                path=path, category=insight.category, difficulty=insight.difficulty,
                importance=insight.importance, reasons=insight.difficulty_reasons[:MAX_CONFUSION_REASONS],
            ))
        return schemas.ConfusionBucket(items=items, total=len(paths))

    return schemas.ConfusionMap(start_here=bucket("Easy"), read_after_basics=bucket("Moderate"),
                                leave_for_later=bucket("Advanced"))


def _readme(analysis: RepoAnalysis) -> schemas.ReadmeQuality | None:
    quality = analysis.readme_quality
    if quality is None:
        return None
    return schemas.ReadmeQuality(
        path=quality.path, score=quality.score, label=quality.label, interpretation=quality.interpretation,
        notes=list(quality.notes),
        checks=[schemas.ReadmeCheck(key=c.key, label=c.label, points=c.points, max_points=c.max_points,
                                    passed=c.passed, evidence=list(c.evidence), suggestion=c.suggestion)
                for c in quality.checks],
    )


def _dependencies(analysis: RepoAnalysis) -> schemas.Dependencies:
    files = [schemas.DependencyFile(path=path, packages=parse_dependencies(path, text))
             for path, text in sorted(analysis.file_contents.items(), key=lambda item: (item[0].count("/"), item[0]))
             if is_dependency_file(path)]
    return schemas.Dependencies(packages=list(analysis.dependencies), files=files)


def _quest(analysis: RepoAnalysis, cites: CitationBuilder) -> schemas.ContributionQuest | None:
    quest = analysis.quest
    if quest is None:
        return None
    return schemas.ContributionQuest(
        title=quest.title, difficulty=quest.difficulty, minutes=quest.minutes, problem=quest.problem,
        why_useful=quest.why_useful, likely_files=list(quest.likely_files), concepts=list(quest.concepts),
        success_criteria=list(quest.success_criteria), hint=quest.hint, citations=cites.from_evidence(quest.evidence),
    )


def _files_summary(analysis: RepoAnalysis) -> schemas.FilesSummary:
    by_category: dict[str, int] = {}
    for insight in analysis.files.values():
        by_category[insight.category] = by_category.get(insight.category, 0) + 1
    return schemas.FilesSummary(
        tree_files=len(analysis.tree_paths),
        downloaded_files=len(analysis.file_contents),
        analysed_python_files=len(analysis.python_files),
        python_files_in_tree=_python_files_in_tree(analysis),
        scored_files=len(analysis.files),
        by_category=dict(sorted(by_category.items())),
    )


# ---------------------------------------------------------------------------
# Q&A and AI explanations
# ---------------------------------------------------------------------------


def serialize_answer(answer: QAAnswer, analysis: RepoAnalysis) -> schemas.QuestionResponse:
    cites = CitationBuilder(analysis)
    citations = [built for c in answer.citations if (built := cites.build(c))]
    return schemas.QuestionResponse(
        question=answer.question,
        intent=answer.intent.value,
        answer=answer.answer,
        confidence=answer.confidence if answer.confidence in ("High", "Medium", "Low") else NO_ANSWER,
        citations=citations,
        limitations=answer.limitations,
        unsupported=answer.intent is QuestionIntent.UNKNOWN,
    )


def serialize_guide(guide: AIGuide | None, message: str) -> schemas.ExplainResponse:
    if guide is None:
        return schemas.ExplainResponse(available=False, message=message, overview="", step_explanations={},
                                       quest_text={}, warnings=[])
    return schemas.ExplainResponse(
        available=True, message=message, overview=guide.overview, step_explanations=dict(guide.step_explanations),
        quest_text=dict(guide.quest_text), warnings=list(guide.warnings),
    )

