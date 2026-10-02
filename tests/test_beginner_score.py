"""Beginner-friendliness score: transparent factors that add up to the total."""

from services.beginner_score import beginner_friendliness, score_label
from services.repo_analyzer import analyze_snapshot
from tests.conftest import make_snapshot


def test_score_is_sum_of_factors_with_reasons(flask_snapshot):
    result = beginner_friendliness(analyze_snapshot(flask_snapshot))
    assert result is not None
    assert result.score == sum(f.points for f in result.factors)
    assert all(0 <= f.points <= f.max_points and f.reason for f in result.factors)
    assert sum(f.max_points for f in result.factors) == 100
    by_label = {f.label: f for f in result.factors}
    assert by_label["Clear entry point"].points == by_label["Clear entry point"].max_points  # app.py has a main guard
    assert by_label["Tests present"].points == by_label["Tests present"].max_points


def test_no_python_code_means_no_score():
    snapshot = make_snapshot({"README.md": "# Docs only\n"}, language="Markdown")
    assert beginner_friendliness(analyze_snapshot(snapshot)) is None


def test_missing_readme_and_tests_lower_the_score(flask_files):
    full = beginner_friendliness(analyze_snapshot(make_snapshot(flask_files)))
    stripped = {p: t for p, t in flask_files.items() if p != "README.md"}
    weaker = beginner_friendliness(analyze_snapshot(make_snapshot(stripped)))
    assert weaker.score < full.score


def test_labels():
    assert score_label(80) == "Very approachable"
    assert score_label(60) == "Approachable"
    assert score_label(40) == "Some ramp-up needed"
    assert score_label(10) == "Steep learning curve"
