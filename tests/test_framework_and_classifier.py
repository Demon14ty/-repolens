import pytest

from services.file_classifier import classify_file
from services.framework_detector import (
    CLI_FRAMEWORK,
    UNKNOWN_FRAMEWORK,
    detect_framework,
    parse_dependencies,
)
from services.python_analyzer import analyze_python_source
from tests.conftest import FLASK_APP

# --- Dependency parsing -------------------------------------------------------


def test_requirements_txt_parsing():
    text = "Flask==3.0.0\n# comment\nrequests>=2 ; python_version>'3'\n-r dev.txt\nuvicorn[standard]\n\n"
    assert parse_dependencies("requirements.txt", text) == ["flask", "requests", "uvicorn"]


def test_pyproject_parsing():
    text = '[project]\ndependencies = ["fastapi>=0.100", "SQLModel"]\n[tool.poetry.dependencies]\npython = "^3.11"\nrich = "*"\n'
    assert parse_dependencies("backend/pyproject.toml", text) == ["fastapi", "sqlmodel", "rich"]


def test_pipfile_parsing():
    text = '[packages]\nstreamlit = "*"\n[dev-packages]\npytest = "*"\n'
    assert parse_dependencies("Pipfile", text) == ["streamlit", "pytest"]


def test_invalid_toml_is_ignored():
    assert parse_dependencies("pyproject.toml", "this is [not toml") == []


# --- Framework detection ------------------------------------------------------


def test_flask_detected_with_high_confidence():
    python_files = {"app.py": analyze_python_source("app.py", FLASK_APP)}
    result = detect_framework({"requirements.txt": ["flask"]}, python_files)
    assert result.name == "Flask"
    assert result.confidence == "High"
    assert any("requirements.txt" in e for e in result.evidence)
    assert any("app.py:6" in e and "Flask(...)" in e for e in result.evidence)


def test_framework_from_dependency_only_is_medium_confidence():
    result = detect_framework({"requirements.txt": ["fastapi"]}, {})
    assert (result.name, result.confidence) == ("FastAPI", "Medium")


def test_streamlit_from_imports():
    info = analyze_python_source("streamlit_app.py", "import streamlit as st\nst.title('Hi')\n")
    result = detect_framework({}, {"streamlit_app.py": info})
    assert result.name == "Streamlit"


def test_strongest_framework_wins_and_others_are_listed():
    flask = analyze_python_source("app.py", FLASK_APP)
    result = detect_framework({"requirements.txt": ["flask", "streamlit"]}, {"app.py": flask})
    assert result.name == "Flask"
    assert "Streamlit" in result.others


def test_cli_script_detected():
    info = analyze_python_source("tool.py", "import argparse\n\nif __name__ == '__main__':\n    pass\n")
    result = detect_framework({}, {"tool.py": info})
    assert result.name == CLI_FRAMEWORK
    assert result.confidence == "Medium"


def test_no_framework_is_not_invented():
    info = analyze_python_source("lib.py", "def add(a, b):\n    return a + b\n")
    result = detect_framework({}, {"lib.py": info})
    assert result.name == UNKNOWN_FRAMEWORK
    assert result.confidence == "Low"


# --- File classification --------------------------------------------------------


@pytest.mark.parametrize(
    "path, expected",
    [
        ("README.md", "documentation"),
        ("docs/guide.rst", "documentation"),
        ("requirements.txt", "dependency"),
        ("pyproject.toml", "dependency"),
        ("setup.py", "dependency"),
        ("Dockerfile", "deployment"),
        ("docker-compose.yml", "deployment"),
        (".github/workflows/ci.yml", "deployment"),
        ("tests/test_app.py", "test"),
        ("test_utils.py", "test"),
        ("tests.py", "test"),
        ("templates/index.html", "template"),
        ("static/style.css", "ui"),
        ("config.py", "configuration"),
        ("settings.yaml", "configuration"),
        ("routes/task_routes.py", "routes"),
        ("app/views.py", "routes"),
        ("models.py", "models"),
        ("database.py", "database"),
        ("app/db.py", "database"),
        ("utils/helpers.py", "utility"),
        ("app/forms.py", "ui"),
        ("logo.png", "unknown"),
    ],
)
def test_classify_by_path(path, expected):
    assert classify_file(path) == expected


def test_entry_point_flag_wins_for_python_files():
    info = analyze_python_source("app.py", FLASK_APP)
    assert classify_file("app.py", info, is_entry_point=True) == "entry_point"


def test_file_with_route_decorators_is_routes_even_with_generic_name():
    info = analyze_python_source("server_things.py", FLASK_APP)
    assert classify_file("server_things.py", info) == "routes"


def test_content_based_rules():
    sql = analyze_python_source("store.py", "import sqlite3\n\ndef save():\n    pass\n")
    assert classify_file("store.py", sql) == "database"
    model = analyze_python_source("things.py", "from app import db\n\nclass Thing(db.Model):\n    pass\n")
    assert classify_file("things.py", model) == "models"
    logic = analyze_python_source("pricing.py", "def total(items):\n    return sum(items)\n")
    assert classify_file("pricing.py", logic) == "core_logic"
