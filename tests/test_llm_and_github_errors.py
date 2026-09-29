"""Hallucination guards and friendly GitHub errors - no network or API key needed."""

import json

import pytest
import requests

from services.github_service import RateLimitError, RepoNotFoundError, _error_for_response
from services.llm_service import build_llm_context, unknown_citations, validate_guide
from services.repo_analyzer import analyze_snapshot


@pytest.fixture
def analysis(flask_snapshot):
    return analyze_snapshot(flask_snapshot)


# --- Citation checking -------------------------------------------------------------


def test_real_citations_are_accepted(analysis):
    text = "Start in app.py:6-12, then read routes/task_routes.py and templates/index.html."
    assert unknown_citations(text, analysis) == []


def test_relative_template_name_is_accepted(analysis):
    assert unknown_citations('It calls render_template("index.html").', analysis) == []


def test_invented_file_is_rejected(analysis):
    assert unknown_citations("Login is handled in auth/login.py.", analysis) == ["auth/login.py"]


def test_impossible_line_range_is_rejected(analysis):
    assert unknown_citations("See app.py:500-520.", analysis) == ["app.py:500-520"]


def test_validate_guide_drops_hallucinated_text(analysis):
    answer = {
        "overview": "A Flask todo app. The entry point is likely app.py.",
        "steps": [
            {"path": "app.py", "explanation": "Creates the Flask app at app.py:6."},
            {"path": "routes/task_routes.py", "explanation": "Calls services/task_service.py to save tasks."},
            {"path": "not_in_path.py", "explanation": "Ignored because it is not a learning step."},
        ],
        "quest": {"title": "Add an empty state", "problem": "Edit templates/index.html.",
                  "why_useful": "Better UX.", "hint": "Use {% else %}."},
    }
    guide = validate_guide(answer, analysis)
    assert guide.overview.startswith("A Flask todo app")
    assert guide.step_explanations == {"app.py": "Creates the Flask app at app.py:6."}
    assert guide.quest_text["title"] == "Add an empty state"
    assert guide.warnings and "services/task_service.py" in guide.warnings[0]


def test_quest_text_rejected_if_it_invents_files(analysis):
    answer = {"overview": "", "steps": [],
              "quest": {"title": "Fix", "problem": "Edit frontend/App.jsx", "why_useful": "x", "hint": ""}}
    assert validate_guide(answer, analysis).quest_text == {}


def test_llm_context_is_structured_and_small(analysis):
    context = build_llm_context(analysis)
    assert context["framework"]["name"] == "Flask"
    assert context["likely_entry_points"][0] == "app.py"
    assert [s["path"] for s in context["learning_path"]][:2] == ["README.md", "app.py"]
    serialized = json.dumps(context)
    assert "SELECT id, title FROM tasks" not in serialized  # no raw source code is sent


# --- GitHub error messages ----------------------------------------------------------


def _response(status: int, headers: dict | None = None) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response.headers.update(headers or {})
    return response


def test_404_means_not_found_or_private():
    error = _error_for_response(_response(404))
    assert isinstance(error, RepoNotFoundError)
    assert "Private" in str(error)


def test_rate_limit_message_suggests_token():
    error = _error_for_response(_response(403, {"X-RateLimit-Remaining": "0"}))
    assert isinstance(error, RateLimitError)
    assert "GITHUB_TOKEN" in str(error)


def test_other_errors_are_friendly():
    assert "empty" in str(_error_for_response(_response(409)))
    assert "HTTP 502" in str(_error_for_response(_response(502)))


def test_code_names_and_urls_are_not_mistaken_for_files(analysis):
    text = "It reads request.form.get and calls st.title; see https://flask.palletsprojects.com/en/3.0.x/ docs. Flask 3.0.0."
    assert unknown_citations(text, analysis) == []


def test_invented_file_with_uncommon_extension_is_rejected(analysis):
    assert unknown_citations("Edit frontend/App.jsx", analysis) == ["frontend/App.jsx"]


# --- LLM request plumbing (fake client, no network) -------------------------------

class _FakeMessages:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def _fake_response(text: str, stop_reason: str = "end_turn"):
    from types import SimpleNamespace
    blocks = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)]
    return SimpleNamespace(stop_reason=stop_reason, content=blocks)


def _install_fake_client(monkeypatch, beta_messages, messages=None):
    from types import SimpleNamespace
    import services.llm_service as llm

    client = SimpleNamespace(beta=SimpleNamespace(messages=beta_messages), messages=messages or _FakeMessages())
    monkeypatch.setattr(llm.anthropic, "Anthropic", lambda **kwargs: client)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    return client


def test_request_guide_parses_json_after_thinking_block(monkeypatch):
    from services.llm_service import request_guide

    beta = _FakeMessages(response=_fake_response('{"overview": "ok", "steps": [], "quest": {}}'))
    _install_fake_client(monkeypatch, beta)
    assert request_guide("{}")["overview"] == "ok"
    sent = beta.calls[0]
    assert sent["fallbacks"] == "default" and sent["output_config"]["format"]["type"] == "json_schema"


def test_request_guide_retries_without_fallback_beta(monkeypatch):
    import anthropic
    import httpx2 as httpx  # the HTTP library used by the anthropic 1.x SDK
    from services.llm_service import request_guide

    bad_request = anthropic.BadRequestError(
        message="unsupported", response=httpx.Response(400, request=httpx.Request("POST", "https://x")), body=None
    )
    plain = _FakeMessages(response=_fake_response('{"overview": "plain", "steps": [], "quest": {}}'))
    _install_fake_client(monkeypatch, _FakeMessages(error=bad_request), plain)
    assert request_guide("{}")["overview"] == "plain"
    assert "fallbacks" not in plain.calls[0]


def test_refusal_and_missing_key_raise_friendly_errors(monkeypatch):
    from services.llm_service import LLMError, request_guide

    _install_fake_client(monkeypatch, _FakeMessages(response=_fake_response("", stop_reason="refusal")))
    with pytest.raises(LLMError, match="declined"):
        request_guide("{}")

    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(LLMError, match="No LLM API key"):
        request_guide("{}")
