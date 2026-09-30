"""First 30 Minutes mode: a short reading plan built from the existing analysis."""

from services.first_30_minutes import MAX_STEPS, MAX_TOTAL_MINUTES, build_first_30_minutes
from services.repo_analyzer import analyze_snapshot
from tests.conftest import MODELS, make_snapshot

STREAMLIT_APP = "import streamlit as st\n\nst.title('Hello')\nname = st.text_input('Name')\nst.write(name)\n"


def test_plan_order_and_contents(flask_snapshot):
    plan = analyze_snapshot(flask_snapshot).first_30_minutes
    paths = [step.path for step in plan.steps]

    assert paths[:3] == ["README.md", "requirements.txt", "app.py"]
    assert 3 <= len(paths) <= MAX_STEPS
    assert len(paths) == len(set(paths))  # no file repeated
    assert [s.number for s in plan.steps] == list(range(1, len(paths) + 1))
    assert plan.steps[2].category == "entry_point"
    assert {"database.py", "routes/task_routes.py"} & set(paths[3:])
    assert not plan.is_limited


def test_plan_steps_are_complete_and_time_boxed(flask_snapshot):
    plan = analyze_snapshot(flask_snapshot).first_30_minutes
    for step in plan.steps:
        assert step.why and step.look_for and step.outcome
        assert step.difficulty_label in {"Beginner", "Intermediate", "Advanced"}
        assert step.minutes > 0
        assert step.evidence
    assert plan.total_minutes == sum(s.minutes for s in plan.steps)
    assert 20 <= plan.total_minutes <= MAX_TOTAL_MINUTES
    assert "What the project does" in plan.outcomes
    assert "Where the application starts" in plan.outcomes
    assert "Which Python framework it uses (Flask)" in plan.outcomes


def test_plan_never_recommends_skipped_ignored_or_test_files(flask_files):
    flask_files["tests/test_app.py"] = "def test_x():\n    assert True\n"
    flask_files["setup.cfg"] = "[metadata]\nname = todo\n"
    snapshot = make_snapshot(flask_files, extra_tree=["Dockerfile", "migrations/001.py", "venv/lib/x.py", "logo.png"])
    analysis = analyze_snapshot(snapshot)
    paths = {step.path for step in analysis.first_30_minutes.steps}
    skipped = {item.path for item in analysis.skip_for_now}

    for bad in ("tests/test_app.py", "setup.cfg", "Dockerfile", "migrations/001.py", "venv/lib/x.py", "logo.png"):
        assert bad not in paths
    assert not paths & skipped
    assert all(p in analysis.file_contents for p in paths)


def test_small_repository_gets_a_shorter_plan_with_notice():
    analysis = analyze_snapshot(make_snapshot({"models.py": MODELS}))
    plan = analysis.first_30_minutes
    assert len(plan.steps) < 3
    assert plan.is_limited


def test_non_python_repository_is_limited():
    analysis = analyze_snapshot(make_snapshot({"README.md": "# JS lib\n", "index.js": "x"}, language="JavaScript"))
    plan = analysis.first_30_minutes
    assert [s.path for s in plan.steps] == ["README.md"]
    assert plan.is_limited


def test_streamlit_single_file_app():
    files = {"README.md": "# Hello app\n", "requirements.txt": "streamlit\n", "streamlit_app.py": STREAMLIT_APP}
    analysis = analyze_snapshot(make_snapshot(files))
    plan = build_first_30_minutes(analysis)
    assert [s.path for s in plan.steps] == ["README.md", "requirements.txt", "streamlit_app.py"]
    assert "Streamlit" in plan.steps[2].look_for
    assert "Which Python framework it uses (Streamlit)" in plan.outcomes


def test_existing_learning_path_is_unchanged(flask_snapshot):
    """The 30-minute plan is additive: the full learning path keeps its own order and rules."""
    analysis = analyze_snapshot(flask_snapshot)
    assert [s.path for s in analysis.learning_path][:2] == ["README.md", "app.py"]
    assert "requirements.txt" not in [s.path for s in analysis.learning_path]
