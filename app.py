"""RepoLens - Explain This Repo Like a Senior.

Streamlit entry point. Run with:  streamlit run app.py

This file only handles the UI. All analysis lives in services/, so the logic
can be tested without Streamlit.
"""

from __future__ import annotations

import html
import json

import streamlit as st
from dotenv import load_dotenv

from models.repo_models import LearningStep, Quest, RepoAnalysis
from services.github_service import GitHubClient, GitHubError, fetch_snapshot, github_token
from services.llm_service import AIGuide, LLMError, build_llm_context, llm_api_key, request_guide, validate_guide
from services.repo_analyzer import analyze_snapshot, choose_files_to_download
from utils.github_parser import InvalidGitHubURL, parse_github_url

load_dotenv()

CACHE_SECONDS = 60 * 60
MAX_FILES_PER_BUCKET = 8
LEVEL_ICONS = {"Easy": "🟢", "Moderate": "🟡", "Advanced": "🔴"}
LEVEL_HINTS = {"Easy": "Easy to start", "Moderate": "Read after the basics", "Advanced": "Leave for later"}
EXAMPLE_REPOS = (
    "https://github.com/miguelgrinberg/microblog",
    "https://github.com/streamlit/streamlit-example",
)

st.set_page_config(page_title="RepoLens", page_icon="🔍", layout="centered")
st.markdown(
    """
    <style>
      /* Background: soft violet/cyan glows over a faint grid */
      [data-testid="stAppViewContainer"] {
        background:
          radial-gradient(900px 500px at 10% -10%, rgba(139,92,246,.22), transparent 60%),
          radial-gradient(800px 500px at 110% 10%, rgba(34,211,238,.14), transparent 60%),
          linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px) 0 0 / 32px 32px,
          linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px) 0 0 / 32px 32px,
          #0B0B14;
      }
      [data-testid="stHeader"] {background: transparent;}

      /* Hero */
      .hero {text-align:center; padding:2.5rem 0 1.25rem;}
      .hero h1 {font-size:3.4rem !important; font-weight:700; margin:.6rem 0 .2rem; padding:0 !important;
        background:linear-gradient(90deg,#A78BFA 0%,#22D3EE 50%,#A78BFA 100%); background-size:200% auto;
        -webkit-background-clip:text; background-clip:text; color:transparent;
        animation:shine 6s linear infinite;}
      .hero-tag {font-size:1.25rem; font-weight:500; color:#E6E6F0; margin-bottom:.5rem;}
      .hero-sub {color:#9A9AB5; max-width:560px; margin:0 auto; line-height:1.55;}
      @keyframes shine {to {background-position:200% center;}}

      /* Section headings get a gradient accent bar */
      [data-testid="stHeading"] h2 {position:relative; padding-left:.9rem; margin-top:1.5rem;}
      [data-testid="stHeading"] h2::before {content:""; position:absolute; left:0; top:.35em; bottom:.35em;
        width:4px; border-radius:4px; background:linear-gradient(#8B5CF6,#22D3EE);}

      /* Input card */
      [data-testid="stForm"] {background:rgba(21,21,37,.75); backdrop-filter:blur(8px);
        border:1px solid rgba(139,92,246,.35); box-shadow:0 0 40px rgba(139,92,246,.12);}
      [data-testid="stFormSubmitButton"] button {width:100%; border:none; font-weight:600;
        background:linear-gradient(90deg,#8B5CF6,#06B6D4); transition:transform .15s, box-shadow .15s;}
      [data-testid="stFormSubmitButton"] button:hover {transform:translateY(-1px);
        box-shadow:0 8px 24px rgba(139,92,246,.35);}

      /* Metrics as glowing tiles */
      [data-testid="stMetric"] {background:rgba(21,21,37,.8); border:1px solid #2A2A45; border-radius:.75rem;
        padding:.8rem 1rem; transition:border-color .2s, transform .2s;}
      [data-testid="stMetric"]:hover {border-color:rgba(34,211,238,.6); transform:translateY(-2px);}
      [data-testid="stMetricValue"] {font-size:1.35rem;}

      [data-testid="stExpander"] details {background:rgba(21,21,37,.6);}
      [data-testid="stProgress"] [role="progressbar"] > div > div > div {
        background:linear-gradient(90deg,#8B5CF6,#22D3EE) !important;}

      /* Code flow */
      .flow-box {border:1px solid rgba(139,92,246,.4); border-radius:12px; padding:.65rem 1rem; margin:0 auto;
        background:linear-gradient(135deg,rgba(139,92,246,.12),rgba(34,211,238,.06));
        box-shadow:0 0 18px rgba(139,92,246,.08);}
      .flow-arrow {text-align:center; font-size:1.2rem; margin:.15rem 0; color:#22D3EE; opacity:.8;}
      .flow-detail {opacity:.7; font-size:.85rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Cached data loading (so Streamlit reruns don't re-download the repository)
# ---------------------------------------------------------------------------


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def load_analysis(owner: str, repo: str, has_token: bool) -> RepoAnalysis:
    """Download and analyse a repository. `has_token` is part of the cache key only."""
    client = GitHubClient(token=github_token())
    snapshot = fetch_snapshot(owner, repo, client, choose_files_to_download)
    return analyze_snapshot(snapshot)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def load_ai_answer(context_json: str) -> tuple[dict | None, str]:
    """Return (answer, error message). Errors are returned, not raised, so they are cached too."""
    try:
        return request_guide(context_json), ""
    except LLMError as exc:
        return None, str(exc)


def get_ai_guide(analysis: RepoAnalysis) -> tuple[AIGuide | None, str]:
    if not llm_api_key() or not analysis.learning_path:
        return None, ""
    context_json = json.dumps(build_llm_context(analysis), sort_keys=True)
    answer, error = load_ai_answer(context_json)
    if answer is None:
        return None, error
    return validate_guide(answer, analysis), ""


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


def init_state() -> None:
    st.session_state.setdefault("repository_url", "")
    st.session_state.setdefault("analysis_result", None)
    st.session_state.setdefault("completed_steps", {})  # repo full name -> list of step numbers


def completed_for(repo: str) -> set[int]:
    return set(st.session_state.completed_steps.get(repo, []))


def toggle_step(repo: str, number: int) -> None:
    done = completed_for(repo)
    done.symmetric_difference_update({number})
    st.session_state.completed_steps[repo] = sorted(done)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_header() -> None:
    st.markdown(
        """
        <div class="hero">
          <h1>RepoLens</h1>
          <div class="hero-tag">Explain This Repo Like a Senior</div>
          <p class="hero-sub">Paste a public GitHub repository. RepoLens tells you where to start,
          what to read next, what to skip, and gives you one small first contribution.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_input() -> str | None:
    with st.form("repo_form"):
        url = st.text_input(
            "Public GitHub Repository URL",
            value=st.session_state.repository_url,
            placeholder="https://github.com/owner/repository",
        )
        submitted = st.form_submit_button("Analyse Repository", type="primary")
    st.caption("Try: " + " · ".join(f"`{u}`" for u in EXAMPLE_REPOS))
    return url if submitted else None


def render_overview(analysis: RepoAnalysis, ai: AIGuide | None) -> None:
    meta = analysis.metadata
    st.header("Repository Overview")
    st.markdown(f"### [{meta.full_name}]({meta.html_url})")
    if meta.description:
        st.write(meta.description)

    cols = st.columns(4)
    cols[0].metric("Language", meta.language)
    cols[1].metric("Framework", analysis.framework.name.split(" (")[0])
    cols[2].metric("Stars", f"{meta.stars:,}")
    cols[3].metric("Learning time", f"~{analysis.estimated_minutes} min" if analysis.estimated_minutes else "—")
    st.caption(f"Owner: {meta.owner} · Default branch: `{meta.default_branch}`")

    with st.expander(f"Framework: {analysis.framework.name} — confidence {analysis.framework.confidence}"):
        st.markdown("**Evidence**")
        for item in analysis.framework.evidence:
            st.markdown(f"- {item}")
        if analysis.framework.others:
            st.markdown("Also found: " + ", ".join(analysis.framework.others))

    if analysis.entry_points:
        entry = analysis.entry_points[0]
        st.markdown(f"**Likely entry point:** `{entry}`")
        with st.expander("Why RepoLens thinks this is the entry point"):
            for reason in analysis.files[entry].entry_reasons:
                st.markdown(f"- {reason}")
            others = analysis.entry_points[1:4]
            if others:
                st.markdown("Other possible entry points: " + ", ".join(f"`{p}`" for p in others))

    if ai and ai.overview:
        with st.container(border=True):
            st.markdown("**🧑‍🏫 Senior's summary** (AI-written from RepoLens evidence)")
            st.write(ai.overview)


def render_learning_path(analysis: RepoAnalysis, ai: AIGuide | None) -> None:
    st.header("Start Here")
    steps = analysis.learning_path
    if not steps:
        st.info("RepoLens could not find enough evidence in this repository to build a reliable learning path.")
        return

    repo = analysis.metadata.full_name
    done = completed_for(repo)
    st.progress(len(done & {s.number for s in steps}) / len(steps),
                text=f"{len(done)} of {len(steps)} steps completed")
    for step in steps:
        render_step(repo, step, ai, step.number in done)


def render_step(repo: str, step: LearningStep, ai: AIGuide | None, is_done: bool) -> None:
    with st.container(border=True):
        top = st.columns([6, 2])
        top[0].markdown(f"**{step.number}. `{step.path}`**")
        top[1].markdown(f"⏱️ {step.minutes} min · {step.difficulty_label}")

        explanation = ai.step_explanations.get(step.path) if ai else ""
        st.write(explanation or step.why)

        with st.expander("Details"):
            if explanation:
                st.markdown(f"**RepoLens heuristic reason:** {step.why}")
            if step.relevant_code:
                st.markdown("**Relevant code**")
                for symbol in step.relevant_code:
                    st.markdown(f"- `{symbol}`")
            st.markdown(f"**Difficulty estimate:** {step.difficulty_score}/100 ({step.difficulty_label})")
            if step.prerequisites:
                st.markdown("**Read first:** " + ", ".join(f"step {n}" for n in step.prerequisites))
            st.markdown("**Sources:** " + ", ".join(f"`{e}`" for e in step.evidence))

        st.checkbox("Mark as completed", value=is_done, key=f"done::{repo}::{step.number}",
                    on_change=toggle_step, args=(repo, step.number))


def render_flow(analysis: RepoAnalysis) -> None:
    st.header("Main Code Flow")
    if not analysis.flow:
        st.info("RepoLens could not find enough evidence in this repository to determine the main flow reliably.")
        return
    st.caption("Built only from relationships found in the source code (imports, route decorators, render calls).")
    parts = []
    for index, step in enumerate(analysis.flow):
        if index:
            parts.append('<div class="flow-arrow">↓</div>')
        # Paths and details come from the analysed repository, so escape them.
        path = f" — <code>{html.escape(step.path)}</code>" if step.path else ""
        detail = f'<div class="flow-detail">{html.escape(step.detail)}</div>' if step.detail else ""
        parts.append(f'<div class="flow-box"><b>{html.escape(step.label)}</b>{path}{detail}</div>')
    st.markdown("".join(parts), unsafe_allow_html=True)


def render_confusion_map(analysis: RepoAnalysis) -> None:
    st.header("Confusion Map")
    st.caption("RepoLens beginner difficulty estimate — a transparent heuristic, not a validated measurement.")
    cols = st.columns(3)
    for col, (level, paths) in zip(cols, analysis.confusion_map.items()):
        with col:
            st.markdown(f"**{LEVEL_ICONS[level]} {LEVEL_HINTS[level]}** ({len(paths)})")
            for path in paths[:MAX_FILES_PER_BUCKET]:
                insight = analysis.files[path]
                with st.expander(f"{path}"):
                    st.markdown(f"Difficulty: **{insight.difficulty}/100** · Importance: **{insight.importance}/100**")
                    st.markdown(f"Category: {insight.category.replace('_', ' ')}")
                    st.markdown("Why:\n" + "\n".join(f"- {r}" for r in insight.difficulty_reasons))
            if len(paths) > MAX_FILES_PER_BUCKET:
                st.caption(f"+ {len(paths) - MAX_FILES_PER_BUCKET} more (less important) files")


def render_skip(analysis: RepoAnalysis) -> None:
    st.header("Skip For Now")
    if not analysis.skip_for_now:
        st.write("Nothing obvious to skip — this repository is already small and focused.")
        return
    for item in analysis.skip_for_now:
        count = f" ({item.file_count} files)" if item.path.endswith("/") and item.file_count > 1 else ""
        st.markdown(f"- `{item.path}`{count} — {item.reason}")


def render_quest(quest: Quest | None, ai: AIGuide | None) -> None:
    st.header("🎯 First Contribution Quest")
    if quest is None:
        st.info("RepoLens could not find enough evidence in this repository to suggest a grounded first task.")
        return
    text = ai.quest_text if ai and ai.quest_text else {}
    with st.container(border=True):
        st.subheader(text.get("title") or quest.title)
        st.markdown(f"**Difficulty:** {quest.difficulty} · **Estimated time:** {quest.minutes} minutes")
        st.markdown(f"**Problem:** {text.get('problem') or quest.problem}")
        st.markdown(f"**Why this is useful:** {text.get('why_useful') or quest.why_useful}")
        st.markdown("**Likely files:** " + ", ".join(f"`{f}`" for f in quest.likely_files))
        st.markdown("**Concepts practiced:** " + ", ".join(quest.concepts))
        st.markdown("**Success criteria:**\n" + "\n".join(f"- {c}" for c in quest.success_criteria))
        hint = text.get("hint") or quest.hint
        if hint:
            with st.expander("💡 Hint"):
                st.write(hint)
        if quest.evidence:
            st.caption("Evidence: " + ", ".join(quest.evidence))
    st.caption("RepoLens never modifies the repository or opens pull requests — this quest is for you to try.")


def render_notes(analysis: RepoAnalysis, ai_error: str, ai: AIGuide | None) -> None:
    for note in analysis.notes:
        st.info(note)
    if ai_error:
        st.caption(f"ℹ️ {ai_error}")
    if ai:
        for warning in ai.warnings:
            st.warning(warning)
    if not llm_api_key():
        st.caption("ℹ️ AI explanations are off (no ANTHROPIC_API_KEY). Everything shown comes from RepoLens's "
                   "built-in analysis.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_analysis(url: str) -> None:
    st.session_state.repository_url = url
    st.session_state.analysis_result = None
    try:
        owner, repo = parse_github_url(url)
    except InvalidGitHubURL as exc:
        st.error(str(exc))
        return
    with st.spinner(f"Reading {owner}/{repo} like a senior developer would..."):
        try:
            st.session_state.analysis_result = load_analysis(owner, repo, bool(github_token()))
        except GitHubError as exc:
            st.error(str(exc))
        except Exception:  # never show a stack trace to a beginner for a normal mistake
            st.error("Something unexpected went wrong while analysing this repository. Please try another one.")


def main() -> None:
    init_state()
    render_header()
    submitted_url = render_input()
    if submitted_url is not None:
        run_analysis(submitted_url)

    analysis: RepoAnalysis | None = st.session_state.analysis_result
    if analysis is None:
        return

    ai, ai_error = None, ""
    if analysis.learning_path and llm_api_key():
        with st.spinner("Asking the AI mentor to explain the evidence..."):
            ai, ai_error = get_ai_guide(analysis)

    render_notes(analysis, ai_error, ai)
    render_overview(analysis, ai)
    if not analysis.python_files:
        return  # the notes above already explain why there is nothing more to show
    render_learning_path(analysis, ai)
    render_flow(analysis)
    render_confusion_map(analysis)
    render_skip(analysis)
    render_quest(analysis.quest, ai)


main()
