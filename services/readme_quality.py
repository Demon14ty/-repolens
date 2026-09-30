"""README Quality Checker: a transparent, rule-based README Onboarding Score.

The score (0-100) answers one question: does this README help a beginner
understand, install, run, test and contribute to the project? Each rubric line
earns points only when concrete evidence is found - a heading whose section has
real content, or a recognisable command/link in the text. A heading followed by
nothing (or by "TODO") earns nothing. This is a heuristic estimate, not an AI
opinion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from models.repo_models import ReadmeCheck, ReadmeQuality
from utils.helpers import basename, depth

README_NAMES = ("readme.md", "readme.rst", "readme.txt", "readme")
MIN_BODY_WORDS = 3  # a section needs at least this much real text to count
MIN_INTRO_WORDS = 8  # an untitled opening paragraph needs this much to count as a description
MAX_EVIDENCE = 3
MAX_SNIPPET_CHARS = 80

# (key, label shown when found, points, suggestion when missing)
RUBRIC = (
    ("exists", "README exists", 15,
     "Create a README.md at the repository root that explains what the project is."),
    ("description", "Project purpose is described", 10,
     "Add a short \"About\" or \"Overview\" paragraph explaining what the project does and who it is for."),
    ("installation", "Installation or setup instructions found", 15,
     "Add an \"Installation\" section with the exact commands to install the project (e.g. cloning and "
     "installing dependencies)."),
    ("environment", "Dependency or environment setup guidance found", 10,
     "Explain how to prepare the environment: the dependency file to install from, a virtual environment, "
     "and any environment variables (ideally with a `.env.example`)."),
    ("usage", "Example usage or run command found", 10,
     "Add a \"Usage\" section with the exact command that starts the project and a short example."),
    ("testing", "Testing instructions found", 10,
     "Add a \"Testing\" section with the exact command needed to run the tests."),
    ("contribution", "Contribution guidance found", 10,
     "Add a \"Contributing\" section explaining how to report issues or submit pull requests."),
    ("license", "License is referenced", 5,
     "Mention the project's license (and add a LICENSE file) so people know how they may use it."),
    ("visuals", "Screenshot, demo or visual reference found", 5,
     "Add a screenshot, GIF or demo link so beginners can see what the project looks like."),
    ("troubleshooting", "Troubleshooting, FAQ or configuration guidance found", 10,
     "Add a \"Troubleshooting\" or \"FAQ\" section covering common setup errors and how to fix them."),
)

# Heading keywords per check (matched on whole-word prefixes of the heading text).
HEADING_PATTERNS = {
    "description": r"\b(about|overview|introduction|intro|features?|what is|description|summary|motivation)\b",
    "installation": r"\b(install\w*|set ?up|getting started|get started|quick ?start|requirements|prerequisites)\b",
    "environment": r"(\benvironment\b|\.env\b|\benvironment variables?\b|\bconfiguration\b|\bconfig\b|\bapi keys?\b"
                   r"|\bsecrets?\b|\bvirtual ?env)",
    "usage": r"\b(usage|run\w*|how to use|examples?|demo usage|launch\w*|start\w* the)\b",
    "testing": r"\b(tests?|testing|pytest|unittest|coverage)\b",
    "contribution": r"\b(contribut\w*|pull requests?|development)\b",
    "license": r"\b(licen[cs]e|licensing)\b",
    "visuals": r"\b(screenshots?|demo|gif|video|preview)\b",
    "troubleshooting": r"\b(troubleshoot\w*|faq|frequently asked|common (issues|problems|errors)|known issues"
                       r"|errors?|problems?|configuration)\b",
}

# Evidence found anywhere in the text (outside of headings), e.g. commands.
TEXT_PATTERNS = {
    "installation": r"(\bpip3? install\b|\bpoetry install\b|\bpipenv install\b|\buv (sync|pip install)\b"
                    r"|\bconda (env create|create|install)\b|\bgit clone\b|\bpython3? setup\.py install\b)",
    "environment": r"(\brequirements[\w-]*\.txt\b|\bpyproject\.toml\b|\bpython3? -m venv\b|\bvirtualenv\b"
                   r"|\.env(\.example)?\b|\benvironment variables?\b|\bapi[_ ]key\b|\bexport [A-Z_]{3,}=)",
    "usage": r"(\bstreamlit run \S+|\bpython3? (-m (?!venv|pip|pytest|unittest)[\w.]+|[\w./-]+\.py)\b|\bflask (--app \S+ )?run\b"
             r"|\buvicorn \S+|\bgunicorn \S+|\bmanage\.py runserver\b|\bfastapi (dev|run)\b|\bdocker(-| )compose up\b)",
    "testing": r"(\bpytest\b|\bpython3? -m unittest\b|\btox\b|\bnox\b|\bcoverage run\b|\bmake test\b)",
    "contribution": r"(\bpull requests?\b|\bcontributing\.md\b|\bcontribut(e|ions?|ing)\b)",
    "license": r"(\b(?i:licen[cs]e[sd]?)\b|\bMIT\b|\bApache\b|\bGPL\b|\bBSD\b)",
}

IMAGE_MARKDOWN = re.compile(r"!\[[^\]]*\]\(([^)\s]+)[^)]*\)")
IMAGE_HTML = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
MEDIA_LINK = re.compile(r"\((https?://[^)\s]*(youtube\.com|youtu\.be|vimeo\.com|loom\.com)[^)\s]*|[^)\s]+\.(gif|mp4|webm))\)",
                        re.IGNORECASE)
BADGE_HINTS = ("shields.io", "badge", "travis-ci", "circleci", "codecov", "coveralls", "badgen", "/workflows/",
               "pepy.tech", "readthedocs.org/projects")

HEADING_ATX = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
UNDERLINE = re.compile(r"^\s*([=\-~^*+#])\1{2,}\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
PLACEHOLDER = re.compile(
    r"^(todo|tbd|tba|wip|coming soon|to be (added|written|done|completed)|work in progress|n/?a|none|\.\.\.|lorem ipsum.*)"
    r"[.!:]*$",
    re.IGNORECASE,
)
MARKUP_ONLY = re.compile(r"^([-*_=]{3,}|<!--.*-->|</?\w+[^>]*>|\[!\[.*)$")


@dataclass
class _Section:
    heading: str
    level: int
    line: int  # 1-based line of the heading
    body: list[tuple[int, str]]  # (line number, text) including nested subsections


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_readme(files: dict[str, str], tree_paths: list[str] | None = None) -> tuple[str | None, bool]:
    """Return (root README path, whether its text was downloaded).

    A README that exists in the tree but was not downloaded (e.g. too large)
    is returned with False so the caller can say it could not be analysed.
    """
    for path in files:
        if depth(path) == 0 and basename(path).lower() in README_NAMES:
            return path, True
    for path in tree_paths or []:
        if depth(path) == 0 and basename(path).lower() in README_NAMES:
            return path, False
    return None, False


def evaluate_readme(path: str | None, text: str | None) -> ReadmeQuality:
    """Score a README with the transparent onboarding rubric.

    `path` is None when the repository has no root README. `text` is None when
    the README exists but its contents are unavailable.
    """
    checks = {key: ReadmeCheck(key=key, label=label, max_points=points, suggestion=suggestion)
              for key, label, points, suggestion in RUBRIC}

    if path is None:
        return _result(None, checks, [])
    if text is None:
        checks["exists"].points = checks["exists"].max_points
        checks["exists"].evidence.append(f"`{path}` found at the repository root")
        return _result(path, checks, [f"`{path}` exists but could not be downloaded (it may be too large), so only "
                                      "its presence was scored."])
    if not text.strip():
        return _result(path, checks, [f"`{path}` exists but is empty, so it earns no points."])

    checks["exists"].points = checks["exists"].max_points
    checks["exists"].evidence.append(f"`{path}` found at the repository root")

    lines = text.splitlines()
    sections, prose = _parse(lines)

    for key, pattern in HEADING_PATTERNS.items():
        regex = re.compile(pattern, re.IGNORECASE)
        for section in sections:
            if key == "usage" and re.search(HEADING_PATTERNS["testing"], section.heading, re.IGNORECASE):
                continue  # "Running tests" is testing guidance, not usage
            if regex.search(section.heading) and _has_meaningful_body(section.body):
                _award(checks[key], f"Heading: \"{section.heading}\" (line {section.line})")

    for key, pattern in TEXT_PATTERNS.items():
        # Commands inside code blocks count; licence/contribution words must not come from the heading alone.
        regex = re.compile(pattern, 0 if key == "license" else re.IGNORECASE)
        for number, line in prose:
            match = regex.search(line)
            if match:
                _award(checks[key], f"Line {number}: {_snippet(line)}")
                break

    _check_description(checks["description"], sections, prose)
    _check_visuals(checks["visuals"], lines)
    return _result(path, checks, [])


def score_label(score: int) -> str:
    if score >= 80:
        return "Excellent onboarding"
    if score >= 60:
        return "Good onboarding"
    if score >= 40:
        return "Basic onboarding"
    return "Needs major improvement"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse(lines: list[str]) -> tuple[list[_Section], list[tuple[int, str]]]:
    """Split a README into sections (Markdown `#` or underlined headings), ignoring code fences.

    Returns (sections, prose) where prose is every non-heading line with its line number.
    """
    headings: list[tuple[int, int, str]] = []  # (index, level, text)
    in_fence = False
    heading_lines: set[int] = set()
    for index, line in enumerate(lines):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        atx = HEADING_ATX.match(line)
        if atx and atx.group(2).strip():
            headings.append((index, len(atx.group(1)), _clean_heading(atx.group(2))))
            heading_lines.add(index)
        elif (UNDERLINE.match(line) and index > 0 and lines[index - 1].strip() and index - 1 not in heading_lines
              and not FENCE.match(lines[index - 1])):
            level = 1 if line.strip().startswith("=") else 2
            headings.append((index - 1, level, _clean_heading(lines[index - 1])))
            heading_lines.update({index - 1, index})

    sections = []
    for position, (index, level, heading) in enumerate(headings):
        end = len(lines)
        for next_index, next_level, _ in headings[position + 1:]:
            if next_level <= level:
                end = next_index
                break
        body = [(i + 1, lines[i]) for i in range(index + 1, end) if i not in heading_lines]
        sections.append(_Section(heading=heading, level=level, line=index + 1, body=body))

    prose = [(i + 1, line) for i, line in enumerate(lines) if i not in heading_lines]
    return sections, prose


def _clean_heading(text: str) -> str:
    text = re.sub(r"[*_`]", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # [text](link) -> text
    return text.strip()


def _has_meaningful_body(body: list[tuple[int, str]]) -> bool:
    """True when the section contains real content, not just blank lines or placeholders."""
    words = 0
    in_fence = False
    for _, line in body:
        stripped = line.strip()
        if FENCE.match(stripped):
            in_fence = not in_fence
            continue
        if not stripped:
            continue
        if in_fence:
            return True  # a non-empty code block is concrete content (e.g. a command)
        content = stripped.lstrip(">*-+ ").strip()
        if not content or PLACEHOLDER.match(content) or MARKUP_ONLY.match(content):
            continue
        if IMAGE_MARKDOWN.search(content) or re.search(r"\]\([^)]+\)", content):
            return True  # a link or image is concrete content
        words += len(re.findall(r"[A-Za-z0-9][\w.'/-]*", content))
        if words >= MIN_BODY_WORDS:
            return True
    return False


def _check_description(check: ReadmeCheck, sections: list[_Section], prose: list[tuple[int, str]]) -> None:
    """Accept an untitled opening paragraph as a description if it has enough real words."""
    if check.passed:
        return
    first_section_line = min((s.line for s in sections if s.level >= 2), default=None)
    words = 0
    first_line = None
    in_fence = False
    for number, line in prose:
        if first_section_line is not None and number >= first_section_line:
            break
        stripped = line.strip()
        if FENCE.match(stripped):
            in_fence = not in_fence
            continue
        if in_fence or not stripped or MARKUP_ONLY.match(stripped) or IMAGE_MARKDOWN.fullmatch(stripped):
            continue
        text = IMAGE_MARKDOWN.sub("", stripped)
        text = re.sub(r"<[^>]+>", "", text)
        count = len(re.findall(r"[A-Za-z][\w'-]*", text))
        if count and first_line is None:
            first_line = (number, stripped)
        words += count
    if words >= MIN_INTRO_WORDS and first_line:
        _award(check, f"Opening paragraph, line {first_line[0]}: {_snippet(first_line[1])}")


def _check_visuals(check: ReadmeCheck, lines: list[str]) -> None:
    """Images and demo links count; status badges do not."""
    for number, line in enumerate(lines, start=1):
        for target in IMAGE_MARKDOWN.findall(line) + IMAGE_HTML.findall(line):
            if not any(hint in target.lower() for hint in BADGE_HINTS):
                _award(check, f"Line {number}: image `{_snippet(target, 60)}`")
                break
        else:
            if MEDIA_LINK.search(line):
                _award(check, f"Line {number}: {_snippet(line)}")
        if len(check.evidence) >= MAX_EVIDENCE:
            break


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _award(check: ReadmeCheck, evidence: str) -> None:
    check.points = check.max_points
    if len(check.evidence) < MAX_EVIDENCE and evidence not in check.evidence:
        check.evidence.append(evidence)


def _snippet(text: str, limit: int = MAX_SNIPPET_CHARS) -> str:
    text = " ".join(text.strip().split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _result(path: str | None, checks: dict[str, ReadmeCheck], notes: list[str]) -> ReadmeQuality:
    ordered = [checks[key] for key, *_ in RUBRIC]
    score = sum(check.points for check in ordered)
    label = score_label(score)
    if path is None:
        interpretation = ("No README was found at the repository root, so a beginner has no written starting point. "
                          "The score is 0.")
    elif score >= 80:
        interpretation = "This README covers most of what a beginner needs to get started and contribute."
    elif score >= 60:
        interpretation = "This README gives a beginner a solid start, but a few onboarding topics are missing."
    elif score >= 40:
        interpretation = "This README covers the basics, but a beginner will likely need to guess some steps."
    else:
        interpretation = "This README gives a beginner little help with setup, running or contributing."
    return ReadmeQuality(path=path, score=score, label=label, interpretation=interpretation, checks=ordered,
                         notes=notes)
