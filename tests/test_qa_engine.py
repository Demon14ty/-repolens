"""Ask RepoLens: deterministic intent matching, evidence-based answers and citation validation."""

import pytest

from models.repo_models import Citation, QAAnswer, QuestionIntent
from services.qa_engine import (
    NO_ANSWER,
    NO_EVIDENCE,
    PRESET_QUESTIONS,
    UNSUPPORTED,
    analysed_line_counts,
    answer_question,
    match_intent,
    validate_answer,
)
from services.repo_analyzer import analyze_snapshot
from tests.conftest import MODELS, make_snapshot

SQLALCHEMY_MODELS = '''\
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import String

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(String(80))
'''

STREAMLIT_APP = '''\
import streamlit as st

from logic import greet

st.title("Greeter")
name = st.text_input("Your name")
st.write(greet(name))
'''

LOGIC = "def greet(name):\n    return f'Hello {name}'\n"


@pytest.fixture
def flask_analysis(flask_snapshot):
    return analyze_snapshot(flask_snapshot)


def ask(analysis, question):
    return answer_question(question, analysis)


def assert_citations_valid(answer, analysis):
    counts = analysed_line_counts(analysis)
    for citation in answer.citations:
        assert citation.path in counts, citation
        assert 1 <= citation.start_line <= citation.end_line <= counts[citation.path], citation


# ---------------------------------------------------------------------------
# Intent matching
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("question, intent", [
    ("Where does the application start?", QuestionIntent.ENTRY_POINT),
    ("where is the application started", QuestionIntent.ENTRY_POINT),
    ("What's the entry point??", QuestionIntent.ENTRY_POINT),
    ("main file", QuestionIntent.ENTRY_POINT),
    ("How does the app launch?", QuestionIntent.ENTRY_POINT),
    ("Which framework does this project use?", QuestionIntent.FRAMEWORK),
    ("is this django", QuestionIntent.FRAMEWORK),
    ("Is this FastAPI?", QuestionIntent.FRAMEWORK),
    ("Where are dependencies defined?", QuestionIntent.DEPENDENCIES),
    ("libraries used", QuestionIntent.DEPENDENCIES),
    ("requirements", QuestionIntent.DEPENDENCIES),
    ("Where are the tests?", QuestionIntent.TESTS),
    ("pytest", QuestionIntent.TESTS),
    ("Does this project use a database?", QuestionIntent.DATABASE),
    ("Is there an ORM or SQLAlchemy?", QuestionIntent.DATABASE),
    ("Which file should I read first?", QuestionIntent.READ_FIRST),
    ("where should I begin", QuestionIntent.READ_FIRST),
    ("How do I run this project?", QuestionIntent.RUN),
    ("installation command", QuestionIntent.RUN),
    ("launch the app", QuestionIntent.RUN),
    ("Where are API routes defined?", QuestionIntent.ROUTES),
    ("endpoints", QuestionIntent.ROUTES),
    ("Which file likely creates the user interface?", QuestionIntent.UI),
    ("frontend templates", QuestionIntent.UI),
    ("What is the main code flow?", QuestionIntent.CODE_FLOW),
    ("How does it work?", QuestionIntent.CODE_FLOW),
    ("What's the weather like?", QuestionIntent.UNKNOWN),
    ("   ", QuestionIntent.UNKNOWN),
])
def test_match_intent(question, intent):
    assert match_intent(question) is intent


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------


def test_entry_point_with_direct_evidence(flask_analysis):
    answer = ask(flask_analysis, "Where does the application start?")
    assert answer.confidence == "High"
    assert "`app.py`" in answer.answer
    assert Citation("app.py", 6, 16) in answer.citations  # Flask(...) call through the __main__ block
    assert Citation("requirements.txt", 1, 1) in answer.citations
    assert_citations_valid(answer, flask_analysis)


def test_missing_entry_point():
    analysis = analyze_snapshot(make_snapshot({"models.py": MODELS, "helpers.py": "def f():\n    return 1\n"}))
    answer = ask(analysis, "Where does the application start?")
    assert answer.confidence == NO_ANSWER
    assert answer.answer == NO_EVIDENCE
    assert answer.citations == []


def test_framework_question(flask_analysis):
    answer = ask(flask_analysis, "Which framework does this project use?")
    assert answer.confidence == "High"
    assert "Flask" in answer.answer
    assert Citation("app.py", 6, 6) in answer.citations  # Flask(...) call
    assert Citation("requirements.txt", 1, 1) in answer.citations
    assert ask(flask_analysis, "Is this Django?").answer.startswith("RepoLens found no evidence of Django")
    assert ask(flask_analysis, "Is this Flask?").answer.startswith("Yes.")


def test_dependencies_question(flask_analysis):
    answer = ask(flask_analysis, "Where are dependencies defined?")
    assert answer.confidence == "High"
    assert "`requirements.txt`" in answer.answer and "`flask`" in answer.answer
    assert answer.citations == [Citation("requirements.txt", 1, 2)]


def test_tests_question(flask_files):
    flask_files["tests/test_database.py"] = "from database import get_tasks\n\n\ndef test_empty():\n    assert True\n"
    analysis = analyze_snapshot(make_snapshot(flask_files, extra_tree=["tests/test_more.py"]))
    answer = ask(analysis, "Where are the tests?")
    assert answer.confidence == "High"
    assert "2 test file(s)" in answer.answer and "`tests/`" in answer.answer
    assert answer.citations == [Citation("tests/test_database.py", 4, 5)]  # not-downloaded file is not cited


def test_tests_question_without_tests(flask_analysis):
    analysis = analyze_snapshot(make_snapshot({"app.py": "print('hi')\n"}))
    answer = ask(analysis, "Where are the tests?")
    assert answer.confidence == NO_ANSWER and answer.answer == NO_EVIDENCE


def test_database_with_sqlalchemy_evidence():
    files = {"models.py": SQLALCHEMY_MODELS, "requirements.txt": "flask\nflask-sqlalchemy\n",
             "app.py": "from flask import Flask\nfrom models import db\n\napp = Flask(__name__)\n"}
    analysis = analyze_snapshot(make_snapshot(files))
    answer = ask(analysis, "Does this project use a database?")
    assert answer.confidence == "High"
    assert "SQLAlchemy" in answer.answer and "`models.py`" in answer.answer and "ORM" in answer.answer
    assert Citation("models.py", 1, 2) in answer.citations
    assert Citation("requirements.txt", 2, 2) in answer.citations
    assert_citations_valid(answer, analysis)


def test_database_with_no_evidence():
    files = {"app.py": "import argparse\n\nif __name__ == '__main__':\n    print(argparse)\n",
             "requirements.txt": "requests\n"}
    answer = ask(analyze_snapshot(make_snapshot(files)), "Does this project use a database?")
    assert answer.confidence == NO_ANSWER
    assert answer.answer == NO_EVIDENCE
    assert answer.citations == []


def test_routes_with_decorators(flask_analysis):
    answer = ask(flask_analysis, "Where are API routes defined?")
    assert answer.confidence == "High"
    assert "`routes/task_routes.py`" in answer.answer
    assert Citation("routes/task_routes.py", 9, 19) in answer.citations
    assert Citation("app.py", 10, 12) in answer.citations


def test_ui_with_templates(flask_analysis):
    answer = ask(flask_analysis, "Which file likely creates the user interface?")
    assert answer.confidence == "High"
    assert "`templates/index.html`" in answer.answer
    assert Citation("templates/index.html", 1, 6) in answer.citations
    assert Citation("app.py", 12, 12) in answer.citations  # the render_template call


def test_ui_with_streamlit():
    files = {"streamlit_app.py": STREAMLIT_APP, "logic.py": LOGIC, "requirements.txt": "streamlit\n"}
    analysis = analyze_snapshot(make_snapshot(files))
    answer = ask(analysis, "Which file likely creates the user interface?")
    assert answer.confidence == "High"
    assert "`streamlit_app.py`" in answer.answer and "Streamlit" in answer.answer
    assert answer.citations == [Citation("streamlit_app.py", 1, 7)]


def test_ui_with_django_template_name():
    files = {
        "manage.py": "from django.core.management import execute_from_command_line\n\n"
                     "if __name__ == '__main__':\n    execute_from_command_line()\n",
        "pages/views.py": "from django.views.generic import TemplateView\n\n\nclass HomePageView(TemplateView):\n"
                          "    template_name = \"pages/home.html\"\n",
        "templates/pages/home.html": "<h1>Home</h1>\n<p>Welcome</p>\n",
    }
    answer = ask(analyze_snapshot(make_snapshot(files)), "Which file likely creates the user interface?")
    assert answer.confidence == "High"
    assert Citation("templates/pages/home.html", 1, 2) in answer.citations
    assert Citation("pages/views.py", 5, 5) in answer.citations


def test_tests_question_with_empty_test_files():
    files = {"app.py": "print('hi')\n", "tests.py": "from django.test import TestCase\n\n# Create your tests here.\n"}
    answer = ask(analyze_snapshot(make_snapshot(files)), "Where are the tests?")
    assert answer.confidence == "Low"
    assert answer.citations == [Citation("tests.py", 1, 3)]
    assert "no `test...` functions" in answer.limitations


def test_run_with_explicit_readme_command():
    readme = "# Greeter\n\n## Run\n\n```bash\npip install -r requirements.txt\nstreamlit run streamlit_app.py\n```\n"
    files = {"README.md": readme, "streamlit_app.py": STREAMLIT_APP, "logic.py": LOGIC}
    answer = ask(analyze_snapshot(make_snapshot(files)), "How do I run this project?")
    assert answer.confidence == "High"
    assert "`streamlit run streamlit_app.py`" in answer.answer
    assert "`pip install -r requirements.txt`" in answer.answer
    assert answer.citations == [Citation("README.md", 6, 6), Citation("README.md", 7, 7)]


def test_run_without_explicit_command_never_invents_one():
    files = {"README.md": "# Greeter\n\nA friendly greeting app for new users.\n",
             "streamlit_app.py": STREAMLIT_APP, "logic.py": LOGIC, "requirements.txt": "streamlit\n"}
    answer = ask(analyze_snapshot(make_snapshot(files)), "How do I run this project?")
    assert answer.confidence == NO_ANSWER
    assert answer.answer == NO_EVIDENCE
    for invented in ("streamlit run", "python app.py", "flask run", "uvicorn"):
        assert invented not in answer.answer


def test_run_ignores_test_commands():
    readme = "# Lib\n\n```\npytest\npoetry run pytest\n```\n"
    answer = ask(analyze_snapshot(make_snapshot({"README.md": readme, "lib.py": LOGIC})), "how to run")
    assert answer.confidence == NO_ANSWER


def test_read_first_and_code_flow(flask_analysis):
    first = ask(flask_analysis, "Which file should I read first?")
    assert first.answer.startswith("Start with `README.md`")
    assert first.confidence == "High"
    flow = ask(flask_analysis, "What is the main code flow?")
    assert flow.confidence == "High"
    assert "`app.py`" in flow.answer and "→" in flow.answer
    assert_citations_valid(flow, flask_analysis)


def test_unknown_question(flask_analysis):
    answer = ask(flask_analysis, "What is the capital of France?")
    assert answer.intent is QuestionIntent.UNKNOWN
    assert answer.answer == UNSUPPORTED
    assert answer.confidence == NO_ANSWER
    assert answer.citations == []


def test_every_preset_question_has_only_valid_citations(flask_analysis):
    for question in PRESET_QUESTIONS:
        answer = ask(flask_analysis, question)
        assert answer.intent is not QuestionIntent.UNKNOWN, question
        assert answer.confidence in {"High", "Medium", "Low", NO_ANSWER}
        assert_citations_valid(answer, flask_analysis)


def test_non_python_repository_limited_analysis():
    analysis = analyze_snapshot(make_snapshot({"README.md": "# JS lib\n", "index.js": "x"}, language="JavaScript"))
    for question in PRESET_QUESTIONS:
        answer = ask(analysis, question)
        assert answer.confidence != "High", question  # never overconfident without parsed Python evidence
        assert_citations_valid(answer, analysis)
    assert ask(analysis, "Where does the application start?").answer == NO_EVIDENCE
    assert ask(analysis, "Which framework does this project use?").answer == NO_EVIDENCE


# ---------------------------------------------------------------------------
# Citation validation
# ---------------------------------------------------------------------------


def make_answer(*citations, confidence="High"):
    return QAAnswer(question="q", intent=QuestionIntent.ROUTES, answer="Some answer.", confidence=confidence,
                    citations=list(citations))


def test_citation_validation_failure_withholds_answer(flask_analysis):
    answer = validate_answer(make_answer(Citation("ghost.py", 1, 3), Citation("app.py", 0, 2)), flask_analysis)
    assert answer.confidence == NO_ANSWER
    assert answer.answer == NO_EVIDENCE
    assert answer.citations == []
    assert "could not verify" in answer.limitations


def test_citation_outside_analysed_files_is_removed(flask_analysis):
    # Dockerfile is in the repository tree but was never downloaded/analysed.
    answer = validate_answer(make_answer(Citation("app.py", 1, 5), Citation("Dockerfile", 1, 2)), flask_analysis)
    assert answer.citations == [Citation("app.py", 1, 5)]
    assert answer.confidence == "Medium"  # downgraded because evidence was removed
    assert "could not be verified" in answer.limitations


def test_invalid_line_range_is_removed(flask_analysis):
    line_count = analysed_line_counts(flask_analysis)["app.py"]
    answer = validate_answer(
        make_answer(Citation("app.py", 1, line_count), Citation("app.py", 5, line_count + 1),
                    Citation("app.py", 9, 3), Citation("models.py", -1, 2)),
        flask_analysis,
    )
    assert answer.citations == [Citation("app.py", 1, line_count)]


def test_high_confidence_requires_a_citation(flask_analysis):
    answer = validate_answer(make_answer(confidence="High"), flask_analysis)
    assert answer.confidence == "Medium"


def test_citation_display_format():
    assert Citation("app.py", 1, 35).display == "`app.py` (lines 1–35)"
    assert Citation("app.py", 4, 4).display == "`app.py` (line 4)"
