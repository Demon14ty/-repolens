"""Optional AI wording layer on top of the deterministic analysis.

Design rules (hallucination protection):
  * The LLM never sees the raw repository - only the structured facts RepoLens
    already extracted (paths, symbols with line ranges, framework evidence).
  * It only rewrites explanations; files, functions and quest targets are
    chosen deterministically before the call.
  * Every file/line citation in its answer is checked against the analysis.
    Text that cites anything unknown is discarded and the deterministic text
    is shown instead.
RepoLens works fully without an API key; this layer just adds friendlier prose.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

import anthropic

from models.repo_models import RepoAnalysis

DEFAULT_MODEL = "claude-opus-5"
MAX_OUTPUT_TOKENS = 16000
REQUEST_TIMEOUT_SECONDS = 180
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_CONTEXT_FILES = 25
MAX_SYMBOLS_PER_FILE = 12

INSUFFICIENT_EVIDENCE = "RepoLens could not find enough evidence in this repository to determine this reliably."

SYSTEM_PROMPT = f"""You are a patient senior developer onboarding a beginner into an unfamiliar Python repository.

You receive structured facts that RepoLens extracted from the repository with static analysis.
Rules:
- Use only the supplied repository evidence. Never invent files, functions, classes, frameworks, dependencies or behaviour.
- When you mention a file, use its exact path from the evidence. Cite code as `path` or `path:start-end`,
  using only line ranges that appear in the evidence. If you are unsure of lines, cite the path only.
- If the evidence is insufficient for a claim, say: "{INSUFFICIENT_EVIDENCE}"
- Describe heuristics as likely, not certain (e.g. "likely entry point").
- Write for a beginner: short sentences, plain words, no jargon without a quick explanation."""

USER_INSTRUCTIONS = """Using the repository evidence below, write:
1. "overview": 3-5 sentences explaining what this project appears to be and how its main parts connect.
2. "steps": for each learning-path step, one or two sentences on why a beginner should read that file at that point
   and what to look for. Keep the same paths.
3. "quest": friendlier wording for the provided contribution quest. Keep the same goal and the same files;
   do not add new files.

Repository evidence (JSON):
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "explanation": {"type": "string"}},
                "required": ["path", "explanation"],
                "additionalProperties": False,
            },
        },
        "quest": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "problem": {"type": "string"},
                "why_useful": {"type": "string"},
                "hint": {"type": "string"},
            },
            "required": ["title", "problem", "why_useful", "hint"],
            "additionalProperties": False,
        },
    },
    "required": ["overview", "steps", "quest"],
    "additionalProperties": False,
}

# Anything that looks like a file reference: "app.py", "routes/auth.py:12-37", "frontend/App.jsx".
CITATION_PATTERN = re.compile(r"(?<![\w/.-])([\w./-]+\.[A-Za-z0-9]{1,8})(?::(\d+)(?:-(\d+))?)?")
# Without a "/", a token only counts as a file if it has a common file extension.
# This keeps "request.form" or "st.title" from being mistaken for file names.
FILE_EXTENSIONS = {
    "py", "pyi", "md", "rst", "txt", "html", "htm", "jinja", "jinja2", "j2", "toml", "cfg", "ini", "yml", "yaml",
    "json", "lock", "js", "jsx", "ts", "tsx", "css", "scss", "sh", "sql", "env", "ipynb", "csv", "xml", "vue",
}


class LLMError(Exception):
    """Friendly message explaining why AI explanations are unavailable."""


@dataclass
class AIGuide:
    overview: str = ""
    step_explanations: dict[str, str] = field(default_factory=dict)
    quest_text: dict[str, str] = field(default_factory=dict)  # title/problem/why_useful/hint
    warnings: list[str] = field(default_factory=list)


def llm_api_key() -> str:
    """ANTHROPIC_API_KEY is the SDK's standard name; LLM_API_KEY is accepted too."""
    return (os.getenv("ANTHROPIC_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()


def llm_model() -> str:
    return os.getenv("REPOLENS_MODEL", "").strip() or DEFAULT_MODEL


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


def build_llm_context(analysis: RepoAnalysis) -> dict:
    """Structured, size-limited facts for the LLM (never raw file contents)."""
    step_paths = [s.path for s in analysis.learning_path]
    ranked = sorted(analysis.files.values(), key=lambda f: -f.importance)
    context_paths = list(dict.fromkeys(step_paths + [f.path for f in ranked]))[:MAX_CONTEXT_FILES]

    files = []
    for path in context_paths:
        insight = analysis.files.get(path)
        info = analysis.python_files.get(path)
        entry = {"path": path, "category": insight.category if insight else "unknown"}
        if info:
            symbols = info.classes + info.functions
            entry["lines"] = info.line_count
            entry["symbols"] = [f"{s.display_name} lines {s.line_range}" for s in symbols[:MAX_SYMBOLS_PER_FILE]]
            entry["routes"] = [f"{r.decorator} -> {r.function}() lines {r.lineno}-{r.end_lineno}" for r in info.routes]
            entry["imports_project_files"] = analysis.import_graph.get(path, [])
            entry["templates_rendered"] = info.template_refs
        files.append(entry)

    quest = analysis.quest
    return {
        "repository": analysis.metadata.full_name,
        "description": analysis.metadata.description,
        "framework": {
            "name": analysis.framework.name,
            "confidence": analysis.framework.confidence,
            "evidence": analysis.framework.evidence,
        },
        "likely_entry_points": analysis.entry_points[:3],
        "dependencies": analysis.dependencies[:30],
        "learning_path": [
            {"step": s.number, "path": s.path, "relevant_code": s.relevant_code, "heuristic_reason": s.why}
            for s in analysis.learning_path
        ],
        "code_flow": [f"{f.label}: {f.path}".rstrip(": ") for f in analysis.flow],
        "files": files,
        "quest": None if quest is None else {
            "title": quest.title, "problem": quest.problem, "likely_files": quest.likely_files,
            "concepts": quest.concepts, "success_criteria": quest.success_criteria,
        },
    }


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------


def request_guide(context_json: str) -> dict:
    """Call Claude once and return the parsed JSON answer. Raises LLMError."""
    api_key = llm_api_key()
    if not api_key:
        raise LLMError("No LLM API key configured, so RepoLens is showing its built-in explanations.")

    client = anthropic.Anthropic(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS)
    request = {
        "model": llm_model(),
        "max_tokens": MAX_OUTPUT_TOKENS,
        "system": SYSTEM_PROMPT,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "medium", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        "messages": [{"role": "user", "content": USER_INSTRUCTIONS + context_json}],
    }
    try:
        try:
            # Server-side fallbacks retry on another model if a request is declined.
            response = client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **request)
        except anthropic.BadRequestError:
            # Accounts/models without the fallback beta: retry as a plain request.
            response = client.messages.create(**request)
    except anthropic.AuthenticationError as exc:
        raise LLMError("The LLM API key was rejected. Check ANTHROPIC_API_KEY in your .env file.") from exc
    except anthropic.RateLimitError as exc:
        raise LLMError("The LLM API rate limit was reached. Try again in a minute.") from exc
    except anthropic.APIStatusError as exc:
        raise LLMError(f"The LLM API returned an error (HTTP {exc.status_code}).") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMError("Could not reach the LLM API. Check your internet connection.") from exc

    if response.stop_reason == "refusal":
        raise LLMError("The AI model declined this request, so built-in explanations are shown.")
    if response.stop_reason == "max_tokens":
        raise LLMError("The AI response was cut off, so built-in explanations are shown.")
    text = next((block.text for block in response.content if block.type == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError("The AI response could not be read, so built-in explanations are shown.") from exc


# ---------------------------------------------------------------------------
# Validation (hallucination protection)
# ---------------------------------------------------------------------------


def unknown_citations(text: str, analysis: RepoAnalysis) -> list[str]:
    """Citations in `text` that do not match a real file or a valid line range."""
    known = set(analysis.tree_paths) | set(analysis.files)
    problems = []
    for match in CITATION_PATTERN.finditer(text):
        path, start, end = match.group(1), match.group(2), match.group(3)
        extension = path.rsplit(".", 1)[-1].lower()
        is_url = path.startswith("//") or text[: match.start()].endswith(("://", "www."))
        if is_url or ("/" not in path and extension not in FILE_EXTENSIONS):
            continue
        if path not in known and any(k.endswith("/" + path) for k in known):
            continue  # a relative name such as "index.html" for templates/index.html
        if path not in known:
            problems.append(match.group(0))
            continue
        info = analysis.python_files.get(path)
        if start and info:
            last = int(end or start)
            if not (1 <= int(start) <= last <= info.line_count):
                problems.append(match.group(0))
    return problems


def validate_guide(data: dict, analysis: RepoAnalysis) -> AIGuide:
    """Keep only AI text whose citations are all real. Everything else is dropped."""
    guide = AIGuide()
    rejected: list[str] = []

    def accept(text: str) -> str:
        text = (text or "").strip()
        bad = unknown_citations(text, analysis)
        if bad:
            rejected.extend(bad)
            return ""
        return text

    guide.overview = accept(data.get("overview", ""))
    step_paths = {s.path for s in analysis.learning_path}
    for item in data.get("steps", []) or []:
        path = item.get("path", "")
        if path in step_paths:
            explanation = accept(item.get("explanation", ""))
            if explanation:
                guide.step_explanations[path] = explanation

    if analysis.quest:
        quest = data.get("quest") or {}
        texts = {key: accept(quest.get(key, "")) for key in ("title", "problem", "why_useful", "hint")}
        if all(texts[key] for key in ("title", "problem", "why_useful")):
            guide.quest_text = texts

    if rejected:
        guide.warnings.append(
            "Some AI-written text referenced files or lines RepoLens could not verify "
            f"({', '.join(sorted(set(rejected))[:5])}), so it was replaced with built-in explanations."
        )
    return guide
