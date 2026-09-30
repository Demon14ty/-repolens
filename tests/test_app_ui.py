"""Offline UI smoke test: render every tab from a pre-built analysis (no GitHub or LLM calls)."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from services.repo_analyzer import analyze_snapshot

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def app(flask_snapshot, monkeypatch):
    # Empty keys keep the optional AI layer off, even if a local .env defines them.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["analysis_result"] = analyze_snapshot(flask_snapshot)
    return at.run()


def test_all_tabs_render(app):
    assert not app.exception
    assert [tab.label for tab in app.tabs] == [
        "📋 Overview", "🧭 Learning Path", "🗺️ Code Map", "🛠️ First Quest", "💬 Ask RepoLens",
    ]
    headers = [h.value for h in app.header]
    for expected in ("📘 README Quality Checker", "🎯 First 30 Minutes", "Start Here", "💬 Ask RepoLens"):
        assert expected in headers
    assert any(m.label == "README Onboarding Score" for m in app.metric)


def test_preset_question_shows_cited_answer(app):
    app.button(key="qa_preset::0").click().run()
    assert not app.exception
    markdown = " ".join(m.value for m in app.markdown)
    assert "The likely application entry point is `app.py`" in markdown
    assert "Confidence: High" in markdown
    assert "`app.py` (lines 6–16)" in markdown


def test_first_30_checkbox_uses_its_own_state(app):
    app.checkbox(key="f30::student/flask-todo::1").check().run()
    assert app.session_state["first30_completed"]["student/flask-todo"] == [1]
    assert app.session_state["completed_steps"].get("student/flask-todo", []) == []
