from services.python_analyzer import analyze_python_source
from tests.conftest import FLASK_APP, UTILS
from utils.helpers import confusion_level, difficulty_label, round_to_time_bucket
from utils.scoring import (
    ROOT_README_IMPORTANCE,
    difficulty_score,
    entry_point_score,
    importance_score,
    is_glue_file,
    is_likely_entry_point,
)


def _big_complex_source(functions: int = 20, lines_per_function: int = 30) -> str:
    body = "\n".join(
        f"def f{i}(x):\n" + "".join(
            f"    if x > {j}:\n        for y in range(x):\n            while y:\n                if y and x:\n                    y -= 1\n"
            for j in range(lines_per_function // 5)
        )
        for i in range(functions)
    )
    imports = "\n".join(f"import mod{i}" for i in range(20))
    return imports + "\n\nclass A: pass\nclass B: pass\nclass C: pass\n\n" + body


# --- Difficulty -------------------------------------------------------------------


def test_small_simple_file_is_easy_with_reasons():
    info = analyze_python_source("utils.py", UTILS)
    score, reasons = difficulty_score("utility", info)
    assert score <= 30
    assert any("Small file" in r for r in reasons)
    assert "No classes" in reasons
    assert "Simple control flow" in reasons


def test_large_complex_file_is_advanced():
    info = analyze_python_source("engine.py", _big_complex_source())
    score, reasons = difficulty_score("core_logic", info)
    assert score > 60
    assert confusion_level(score) == "Advanced"
    assert any("Many imports" in r for r in reasons)
    assert any("branching" in r for r in reasons)
    assert any("nested" in r.lower() for r in reasons)


def test_score_is_clamped_to_100():
    info = analyze_python_source("huge.py", _big_complex_source(functions=60, lines_per_function=60))
    score, _ = difficulty_score("deployment", info)
    assert 0 <= score <= 100


def test_non_python_files_use_category_defaults():
    assert difficulty_score("documentation")[0] <= 30
    assert difficulty_score("deployment")[0] > 30


def test_parse_error_gets_a_middle_score():
    info = analyze_python_source("broken.py", "def (:")
    score, reasons = difficulty_score("core_logic", info)
    assert score == 50 and "could not parse" in reasons[0]


# --- Importance is separate from difficulty -------------------------------------------


def test_root_readme_is_important_but_easy():
    importance, _ = importance_score("README.md", "documentation")
    difficulty, _ = difficulty_score("documentation")
    assert importance == ROOT_README_IMPORTANCE
    assert difficulty <= 30


def test_dockerfile_is_unimportant_but_not_easy():
    importance, _ = importance_score("Dockerfile", "deployment")
    difficulty, _ = difficulty_score("deployment")
    assert importance < 30
    assert difficulty > 30


def test_importers_raise_importance():
    alone, _ = importance_score("database.py", "database")
    shared, reasons = importance_score("database.py", "database", importers=["app.py", "routes.py"])
    assert shared > alone
    assert any("Imported by 2" in r for r in reasons)


def test_glue_file_importance_is_capped():
    info = analyze_python_source("pkg/__init__.py", "from pkg import a, b\n")
    assert is_glue_file(info)
    importance, reasons = importance_score("pkg/__init__.py", "routes", info, importers=["x.py"] * 5)
    assert importance <= 30
    assert any("wiring" in r for r in reasons)


# --- Entry points ------------------------------------------------------------------


def test_flask_app_is_likely_entry_point_with_reasons():
    info = analyze_python_source("app.py", FLASK_APP)
    score, reasons = entry_point_score("app.py", info)
    assert is_likely_entry_point(score)
    assert any("app.py" in r and "common entry-point name" in r for r in reasons)
    assert any("__main__" in r for r in reasons)
    assert any("Flask(...)" in r and "app.py:6" in r for r in reasons)


def test_app_factory_call_counts_as_entry_point():
    info = analyze_python_source("microblog.py", "from app import create_app\n\napp = create_app()\n")
    score, _ = entry_point_score("microblog.py", info)
    assert is_likely_entry_point(score)


def test_streamlit_script_is_entry_point():
    info = analyze_python_source("dashboard.py", "import streamlit as st\n\nst.title('Sales')\n")
    assert is_likely_entry_point(entry_point_score("dashboard.py", info)[0])


def test_plain_module_is_not_entry_point():
    info = analyze_python_source("pkg/helpers.py", UTILS)
    score, reasons = entry_point_score("pkg/helpers.py", info)
    assert score == 0 and reasons == []


# --- Labels and time buckets ---------------------------------------------------------


def test_labels():
    assert difficulty_label(10) == "Beginner"
    assert difficulty_label(45) == "Intermediate"
    assert difficulty_label(90) == "Advanced"
    assert confusion_level(30) == "Easy" and confusion_level(31) == "Moderate" and confusion_level(61) == "Advanced"


def test_time_buckets_avoid_fake_precision():
    assert round_to_time_bucket(1) == 5
    assert round_to_time_bucket(8.53) == 10
    assert round_to_time_bucket(16) == 20
    assert round_to_time_bucket(500) == 30
