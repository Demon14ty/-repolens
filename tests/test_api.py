"""HTTP API tests. GitHub is replaced by the hand-written snapshot fixture, so no network is used."""

import json

import pytest
from fastapi.testclient import TestClient

import api.index as api_index
from api.serializers import EVIDENCE_REF
from services.github_service import GitHubNetworkError, RateLimitError, RepoNotFoundError
from services.qa_engine import UNSUPPORTED

FAKE_SECRETS = {
    "GITHUB_TOKEN": "ghp_testsecretvalue_do_not_leak",
    "ANTHROPIC_API_KEY": "sk-ant-testsecret-do-not-leak",
    "LLM_API_KEY": "llm-testsecret-do-not-leak",
}


@pytest.fixture
def client(monkeypatch):
    for name in FAKE_SECRETS:
        monkeypatch.setenv(name, "")
    api_index.cache.clear()
    yield TestClient(api_index.app, raise_server_exceptions=False)
    api_index.cache.clear()


@pytest.fixture
def fake_github(monkeypatch, flask_snapshot):
    """Make fetch_snapshot return the Flask fixture and count how often GitHub would be called."""
    calls = []

    def fake_fetch(owner, repo, client, choose_files):
        calls.append((owner, repo))
        return flask_snapshot

    monkeypatch.setattr(api_index, "fetch_snapshot", fake_fetch)
    return calls


def _raise(error):
    def fake_fetch(*args, **kwargs):
        raise error
    return fake_fetch


def _analyze(client, url="https://github.com/student/flask-todo"):
    return client.post("/api/analyze", json={"repo_url": url})


# --- Health ---------------------------------------------------------------------


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": api_index.VERSION, "ai_explanations_available": False}


# --- Analyze: errors --------------------------------------------------------------


@pytest.mark.parametrize("url", ["not a url", "https://github.com/onlyowner", "https://github.com/settings/profile", ""])
def test_analyze_invalid_url(client, url):
    response = _analyze(client, url)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REPOSITORY_URL"
    assert response.json()["error"]["title"] == "Invalid GitHub URL"


def test_analyze_non_github_url(client):
    response = _analyze(client, "https://gitlab.com/owner/repository")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "NOT_GITHUB_URL"


def test_analyze_missing_field_is_structured(client):
    response = client.post("/api/analyze", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


@pytest.mark.parametrize("error, status, code", [
    (RateLimitError("limit"), 429, "GITHUB_RATE_LIMITED"),
    (RepoNotFoundError("missing"), 404, "REPOSITORY_NOT_FOUND"),
    (GitHubNetworkError("down"), 503, "GITHUB_UNAVAILABLE"),
])
def test_analyze_github_errors(client, monkeypatch, error, status, code):
    monkeypatch.setattr(api_index, "fetch_snapshot", _raise(error))
    response = _analyze(client)
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert body["error"]["title"] and body["error"]["message"]


def test_unexpected_error_hides_internals(client, monkeypatch):
    monkeypatch.setattr(api_index, "fetch_snapshot", _raise(RuntimeError("database password is hunter2")))
    response = _analyze(client)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "hunter2" not in response.text and "Traceback" not in response.text


# --- Analyze: success -------------------------------------------------------------


def test_analyze_success(client, fake_github):
    response = _analyze(client)
    assert response.status_code == 200
    data = response.json()
    assert data["analysis_id"] == "student/flask-todo"
    assert data["repository"]["full_name"] == "student/flask-todo"
    assert data["framework"]["name"] == "Flask"
    assert data["entry_point"]["path"] == "app.py"
    assert data["entry_point"]["citations"]
    assert [s["path"] for s in data["learning_path"]][:2] == ["README.md", "app.py"]
    assert data["first_30_minutes"]["steps"]
    assert data["readme_quality"]["score"] > 0
    assert data["contribution_quest"]["title"]
    assert data["code_flow"][1]["path"] == "app.py"
    assert "flask" in data["dependencies"]["packages"]
    assert 0 <= data["beginner_score"]["score"] <= 100
    assert sum(f["points"] for f in data["beginner_score"]["factors"]) == data["beginner_score"]["score"]
    assert any(item["path"] == ".github/" for item in data["skip_for_now"])
    assert data["files_summary"]["analysed_python_files"] == 5


def test_analyze_uses_cache_unless_refresh(client, fake_github):
    _analyze(client)
    _analyze(client)
    assert len(fake_github) == 1
    client.post("/api/analyze", json={"repo_url": "https://github.com/student/flask-todo", "refresh": True})
    assert len(fake_github) == 2


def test_complete_when_every_python_file_is_analysed(client, monkeypatch, flask_files):
    from tests.conftest import make_snapshot
    monkeypatch.setattr(api_index, "fetch_snapshot", lambda *a, **k: make_snapshot(flask_files))
    assert _analyze(client).json()["status"] == "complete"


def test_partial_analysis_is_flagged(client, monkeypatch, flask_files, flask_snapshot):
    from tests.conftest import make_snapshot
    # flask_snapshot lists migrations/*.py in the tree that were never downloaded.
    monkeypatch.setattr(api_index, "fetch_snapshot", lambda *a, **k: flask_snapshot)
    assert _analyze(client).json()["status"] == "partial"
    truncated = make_snapshot(flask_files)
    truncated.tree_truncated = True
    monkeypatch.setattr(api_index, "fetch_snapshot", lambda *a, **k: truncated)
    response = client.post("/api/analyze", json={"repo_url": "https://github.com/student/flask-todo", "refresh": True})
    assert response.json()["status"] == "partial"


def test_repository_without_python_is_unsupported(client, monkeypatch):
    from tests.conftest import make_snapshot
    snapshot = make_snapshot({"README.md": "# A JS app\n\nSome text here for the readme.\n", "index.js": "x()\n"},
                             language="JavaScript")
    monkeypatch.setattr(api_index, "fetch_snapshot", lambda *a, **k: snapshot)
    data = _analyze(client).json()
    assert data["status"] == "unsupported"
    assert data["beginner_score"] is None
    assert data["readme_quality"]["path"] == "README.md"


def test_empty_repository(client, monkeypatch):
    from tests.conftest import make_snapshot
    monkeypatch.setattr(api_index, "fetch_snapshot", lambda *a, **k: make_snapshot({}))
    response = _analyze(client)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EMPTY_REPOSITORY"


# --- Citations ---------------------------------------------------------------------


def _all_citations(data):
    found = list(data["entry_point"]["citations"]) + list(data["contribution_quest"]["citations"])
    for step in data["learning_path"] + data["first_30_minutes"]["steps"]:
        found.extend(step["citations"])
    return found


def test_citations_point_to_real_lines(client, fake_github, flask_files):
    citations = _all_citations(_analyze(client).json())
    assert citations
    for citation in citations:
        assert citation["path"] in flask_files
        line_count = len(flask_files[citation["path"]].splitlines())
        assert 1 <= citation["start_line"] <= citation["end_line"] <= line_count
        preview = citation["preview"]
        assert preview["start_line"] == citation["start_line"]
        expected = flask_files[citation["path"]].splitlines()[citation["start_line"] - 1:citation["end_line"]]
        assert preview["lines"] == expected[:len(preview["lines"])]


def test_invalid_evidence_is_dropped(flask_snapshot):
    from api.serializers import CitationBuilder
    from services.repo_analyzer import analyze_snapshot

    builder = CitationBuilder(analyze_snapshot(flask_snapshot))
    assert builder.from_evidence(["app.py:500", "invented/file.py:3", "nothing"]) == []
    assert [c.start_line for c in builder.from_evidence(["Creates `Flask(...)` at app.py:6"])] == [6]
    assert EVIDENCE_REF.search("routes/task_routes.py:8-12").groups() == ("routes/task_routes.py", "8", "12")


# --- Questions ---------------------------------------------------------------------


def test_question_with_deterministic_answer(client, fake_github, flask_files):
    _analyze(client)
    response = client.post("/api/question", json={"analysis_id": "student/flask-todo",
                                                  "question": "Where does the application start?"})
    assert response.status_code == 200
    data = response.json()
    assert data["answer"].startswith("The likely application entry point is `app.py`")
    assert data["confidence"] == "High"
    assert data["unsupported"] is False
    assert data["citations"][0]["path"] == "app.py"
    for citation in data["citations"]:
        lines = len(flask_files[citation["path"]].splitlines())
        assert 1 <= citation["start_line"] <= citation["end_line"] <= lines
    assert len(fake_github) == 1  # served from the warm cache


def test_question_reanalyses_on_cache_miss(client, fake_github):
    response = client.post("/api/question", json={"analysis_id": "student/flask-todo",
                                                  "question": "Which framework does this project use?"})
    assert response.status_code == 200
    assert "Flask" in response.json()["answer"]
    assert len(fake_github) == 1


def test_unsupported_question(client, fake_github):
    response = client.post("/api/question", json={"analysis_id": "student/flask-todo",
                                                  "question": "What is the meaning of life?"})
    data = response.json()
    assert data["unsupported"] is True
    assert data["confidence"] == "No reliable answer"
    assert data["citations"] == []
    assert data["answer"] == UNSUPPORTED


def test_question_errors(client, fake_github):
    empty = client.post("/api/question", json={"analysis_id": "student/flask-todo", "question": "  "})
    assert empty.status_code == 400 and empty.json()["error"]["code"] == "EMPTY_QUESTION"
    bad_id = client.post("/api/question", json={"analysis_id": "../etc", "question": "Where are the tests?"})
    assert bad_id.status_code == 400 and bad_id.json()["error"]["code"] == "INVALID_ANALYSIS_ID"


def test_explain_is_disabled_without_key(client, fake_github):
    data = client.post("/api/explain", json={"analysis_id": "student/flask-todo"}).json()
    assert data["available"] is False
    assert fake_github == []  # no GitHub call when AI is off


# --- Secrets -----------------------------------------------------------------------


def test_responses_never_include_secrets(client, fake_github, monkeypatch):
    for name, value in FAKE_SECRETS.items():
        monkeypatch.setenv(name, value)
    bodies = [
        client.get("/api/health").text,
        _analyze(client).text,
        client.post("/api/question", json={"analysis_id": "student/flask-todo", "question": "How do I run it?"}).text,
        _analyze(client, "not a url").text,
    ]
    monkeypatch.setattr(api_index, "fetch_snapshot", _raise(RateLimitError("GITHUB_TOKEN=" + FAKE_SECRETS["GITHUB_TOKEN"])))
    bodies.append(client.post("/api/analyze", json={"repo_url": "https://github.com/a/b", "refresh": True}).text)
    combined = "\n".join(bodies)
    for value in FAKE_SECRETS.values():
        assert value not in combined
    assert json.loads(bodies[0])["ai_explanations_available"] is True


def test_cors_allows_only_configured_origins(monkeypatch):
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    assert api_index.allowed_origins() == ["http://localhost:3000", "http://127.0.0.1:3000"]
    monkeypatch.setenv("VERCEL", "1")
    assert api_index.allowed_origins() == []
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://repolens.example, https://preview.example/")
    assert api_index.allowed_origins() == ["https://repolens.example", "https://preview.example"]
