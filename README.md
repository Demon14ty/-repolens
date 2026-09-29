# 🔍 RepoLens: Explain This Repo Like a Senior

> Understand unfamiliar GitHub repositories through source-cited explanations, progressive learning paths,
> confusion maps, and first-contribution quests generated from the repository itself.

Paste a public GitHub URL. RepoLens tells you **where to start**, **what to read next**, **what to ignore for now**,
**how the important files connect**, and gives you **one small coding challenge** based on the actual code, the
way a senior developer would onboard a junior.

Version 1 supports **Python repositories only**.

## Problem

Beginners who open an unfamiliar repository see hundreds of files and don't know which ones matter. Generic AI
chatbots help a little, but they often invent files and functions that don't exist.

## Solution

RepoLens analyses the repository deterministically first: GitHub metadata, the file tree, and Python `ast`
parsing. It then builds a short learning path from that evidence. Every claim points back to a real file, and
where possible to real line numbers. An optional LLM rewrites the explanations in friendlier language, and any
AI text that cites a file or line RepoLens can't verify is thrown away.

## Features

- **Repository overview**: name, owner, description, stars, language, default branch, estimated learning time
- **Framework detection**: Flask, FastAPI, Django, Streamlit, Tkinter, PySide/PyQt, or CLI, with a confidence
  level and the evidence behind it
- **Entry-point detection**: the likely entry point with reasons (file name, `if __name__ == "__main__"`,
  `Flask(...)`, `create_app()`, Streamlit top-level code)
- **Beginner learning path**: up to 6 steps. Each step has the file, the relevant functions/classes with line
  ranges, why to read it, difficulty, reading time, prerequisites, and sources
- **Progress tracking**: "Mark as completed" checkboxes (kept in Streamlit session state)
- **Main code flow**: request → entry point → routes → supporting code → template → response, using only
  relationships found in the code
- **Confusion map**: 🟢 Easy / 🟡 Moderate / 🔴 Advanced, with the reasons for each file's score
- **Skip for now**: CI workflows, Docker, migrations, tests, lock files and so on, each with a reason
- **First Contribution Quest**: one small task grounded in evidence (an empty state for a template loop,
  input validation in a route, a missing unit test, a README section, or a docstring)
- **Source-cited explanations**: citations such as `app.py:6` or `routes/tasks.py:10-14`

## Architecture

```text
app.py                      Streamlit UI only (caching, session state, rendering)
│
├── services/
│   ├── github_service.py   The only module that talks to GitHub (REST API + raw file downloads)
│   ├── repo_analyzer.py    Orchestrates the pipeline: choose files → analyse → score → build outputs
│   ├── python_analyzer.py  ast facts per file: imports, functions, classes, calls, routes, branches...
│   ├── framework_detector.py  Dependency parsing + framework detection with evidence
│   ├── file_classifier.py  documentation / entry_point / routes / models / database / test / ...
│   ├── learning_path.py    Reading order, confusion map, skip-for-now list
│   ├── code_flow.py        Main execution flow from resolved imports/decorators/render calls
│   ├── challenge_generator.py  One evidence-based First Contribution Quest
│   └── llm_service.py      Optional: one Claude call + citation validation
├── models/repo_models.py   Dataclasses shared by everything (picklable for Streamlit caching)
├── utils/
│   ├── github_parser.py    URL → (owner, repo)
│   ├── scoring.py          Difficulty, importance and entry-point scores, each with reasons
│   └── helpers.py          Small path/format/graph helpers
├── tests/                  Unit tests (no network)
└── evaluation/             Five-repository evaluation set + script
```

Main design decisions:

1. **Download and analysis are separated.** `fetch_snapshot` downloads a `RepoSnapshot`, and
   `analyze_snapshot` is a pure function of it. The tests build snapshots by hand, so they need no network.
2. **Evidence first, AI second.** The LLM only gets structured facts (paths, symbols with line ranges,
   framework evidence) and never raw source code. It can reword explanations but can't choose files. Its
   output is checked with `unknown_citations()`.
3. **Importance and difficulty are separate scores.** A README is important and easy, a `models.py` can be
   important and hard, and a Dockerfile is unimportant at first but not easy. The path uses importance to
   choose files and difficulty to label them.
4. **Transparent heuristics.** Every score comes with a list of reasons. The thresholds are named constants
   in `utils/scoring.py`.
5. **Ready for Phase 2.** `PythonFileInfo` already stores symbols with line ranges and call sites, and
   `RepoAnalysis.import_graph` / `importers_of()` give the imports and importers of any file. Those are the
   building blocks for source-cited Q&A (keyword search over symbols → chunks → LLM → `validate_guide`-style
   citation check) and for the Change Impact Simulator (file → imports → callers → related tests).

## Setup

Requires **Python 3.11+** (RepoLens uses the built-in `tomllib`).

```bash
git clone <your-fork-url> repolens
cd repolens
python -m venv .venv
```

Activate the virtual environment:

```bash
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

Install and run:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Streamlit opens http://localhost:8501. Try `https://github.com/miguelgrinberg/microblog`.

## Environment Variables

Copy `.env.example` to `.env`. Both variables are optional.

| Variable | Purpose |
|---|---|
| `GITHUB_TOKEN` | Raises GitHub's API limit from 60 to 5,000 requests/hour. No scopes are needed for public repos. File contents are downloaded from `raw.githubusercontent.com`, which doesn't count against the limit, so each analysis uses only about 2 API requests. |
| `ANTHROPIC_API_KEY` | Enables AI-written explanations (Claude). `LLM_API_KEY` also works. Without it, RepoLens uses its built-in explanations. |
| `REPOLENS_MODEL` | Optional model override (default `claude-opus-5`). |

The LLM call uses Anthropic's server-side refusal fallback (`fallbacks="default"`). If a request is declined,
the API retries it on another model. If your account doesn't support that beta, RepoLens retries once as a
plain request.

`.env` is in `.gitignore`. Never commit secrets.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests cover URL parsing, AST analysis, dependency parsing, framework detection, file classification,
difficulty/importance/entry-point scoring, import resolution, learning-path ordering, the skip list, the code
flow, quest generation, GitHub error messages, and the AI citation checks. They use small mocked repositories
and make no network calls.

Evaluation against real repositories (needs network): `python -m evaluation.run_eval`. See
[evaluation/README.md](evaluation/README.md).

## Limitations

- Version 1 analyses **Python** code only. Other languages show metadata and a notice.
- All scores are **heuristic estimates** ("RepoLens beginner difficulty estimate"), not validated
  measurements. Entry points are labelled "likely".
- **Large repositories are only partly analysed.** At most 60 non-test Python files are analysed (shallow and
  entry-point-like files first), files over 100 KB are skipped, and total downloads are capped at 1.5 MB. The
  UI says when this happens.
- Import resolution is static. Dynamic imports, Django's string-based `INSTALLED_APPS`/`urls` wiring, and
  plugin systems aren't followed.
- AI explanations depend on the evidence RepoLens extracted. Text that cites files or lines RepoLens can't
  verify is dropped, but the checker validates citations, not every sentence.
- Progress is kept only for the current browser session.

## Future Roadmap

- **Source-cited Q&A**: "Where is login handled?" → keyword/symbol search → relevant chunks → cited answer
- **Change Impact Simulator**: pick a function → see its imports, callers, related tests, and likely impact
- **Tree-sitter** for multi-language support
- **Persistent learning progress** across sessions
- **Better contribution quests**: several candidates to choose from, difficulty levels, and checking the
  learner's diff against the success criteria
