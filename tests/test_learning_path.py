"""End-to-end tests of the deterministic pipeline on a mocked Flask todo repository."""

from models.repo_models import TreeEntry
from services.repo_analyzer import analyze_snapshot, build_import_graph, choose_files_to_download
from services.python_analyzer import analyze_python_source
from tests.conftest import MODELS, make_snapshot
from utils.helpers import TIME_BUCKETS, reachable_depths


def test_import_graph_resolves_project_files_only(flask_files):
    python = {p: analyze_python_source(p, t) for p, t in flask_files.items() if p.endswith(".py")}
    graph = build_import_graph(python)
    assert sorted(graph["app.py"]) == ["database.py", "routes/task_routes.py"]  # not flask
    assert sorted(graph["routes/task_routes.py"]) == ["database.py", "models.py"]


def test_relative_and_src_layout_imports():
    files = {
        "src/shop/__init__.py": "",
        "src/shop/cart.py": "from .pricing import total\n",
        "src/shop/pricing.py": "def total():\n    return 0\n",
        "src/shop/cli.py": "from shop.cart import x\n",
    }
    python = {p: analyze_python_source(p, t) for p, t in files.items()}
    graph = build_import_graph(python)
    assert graph["src/shop/cart.py"] == ["src/shop/pricing.py"]
    assert graph["src/shop/cli.py"] == ["src/shop/cart.py"]


def test_reachable_depths_skip_glue_files():
    graph = {"main.py": ["pkg/__init__.py"], "pkg/__init__.py": ["pkg/routes.py"]}
    assert reachable_depths("main.py", graph)["pkg/routes.py"] == 2
    assert reachable_depths("main.py", graph, free={"pkg/__init__.py"})["pkg/routes.py"] == 1


def test_learning_path_order(flask_snapshot):
    analysis = analyze_snapshot(flask_snapshot)
    paths = [step.path for step in analysis.learning_path]

    assert paths[0] == "README.md"
    assert paths[1] == "app.py"
    # Files imported directly by app.py come before files only they import.
    assert paths.index("routes/task_routes.py") < paths.index("models.py")
    assert paths.index("database.py") < paths.index("models.py")
    assert "templates/index.html" in paths
    # Never recommends skip-worthy or unconnected files.
    for skipped in ("Dockerfile", "requirements.txt", "utils.py", "migrations/001_init.py"):
        assert skipped not in paths
    assert len(paths) <= 6


def test_learning_steps_are_complete(flask_snapshot):
    analysis = analyze_snapshot(flask_snapshot)
    by_path = {s.path: s for s in analysis.learning_path}

    app_step = by_path["app.py"]
    assert "Likely entry point" in app_step.why
    assert "index() (lines 10-12)" in app_step.relevant_code
    assert app_step.prerequisites == [1]
    assert "app.py:6" in app_step.evidence

    routes_step = by_path["routes/task_routes.py"]
    assert 2 in routes_step.prerequisites  # imported by app.py
    assert "add()" in routes_step.why
    for step in analysis.learning_path:
        assert step.minutes in TIME_BUCKETS
        assert step.difficulty_label in {"Beginner", "Intermediate", "Advanced"}
        assert all(p < step.number for p in step.prerequisites)
    assert analysis.estimated_minutes == sum(s.minutes for s in analysis.learning_path)


def test_framework_entry_point_and_flow(flask_snapshot):
    analysis = analyze_snapshot(flask_snapshot)
    assert analysis.framework.name == "Flask"
    assert analysis.entry_points[0] == "app.py"

    flow_paths = [step.path for step in analysis.flow]
    assert analysis.flow[0].label.startswith("User sends an HTTP request")
    assert flow_paths[1] == "app.py"
    assert "database.py" in flow_paths
    assert "templates/index.html" in flow_paths
    # Every file in the flow really exists.
    assert all(p in analysis.tree_paths for p in flow_paths if p)


def test_confusion_map_and_skip_list(flask_snapshot):
    analysis = analyze_snapshot(flask_snapshot)
    assert "README.md" in analysis.confusion_map["Easy"]
    assert "Dockerfile" in analysis.confusion_map["Moderate"] + analysis.confusion_map["Advanced"]

    skipped = {item.path: item for item in analysis.skip_for_now}
    assert ".github/" in skipped and "automated" in skipped[".github/"].reason
    assert "Dockerfile" in skipped
    assert skipped["migrations/"].file_count == 2
    assert "tests/" in skipped
    learning = {s.path for s in analysis.learning_path}
    assert not learning & set(skipped)


def test_quest_is_grounded_in_real_files(flask_snapshot):
    quest = analyze_snapshot(flask_snapshot).quest
    assert quest is not None
    assert "empty" in quest.title.lower()  # the template loop has no {% else %}
    assert quest.likely_files[0] == "templates/index.html"
    assert quest.evidence == ["templates/index.html:3"]
    assert len(quest.success_criteria) >= 2


def test_quest_falls_back_to_input_validation_when_template_has_empty_state(flask_files):
    flask_files["templates/index.html"] = "{% for t in tasks %}{{ t }}{% else %}No tasks{% endfor %}"
    quest = analyze_snapshot(make_snapshot(flask_files)).quest
    assert quest.title == "Validate user input in `add()`"
    assert quest.likely_files == ["routes/task_routes.py"]


def test_missing_test_quest_for_plain_library():
    files = {
        "README.md": "# Lib\nInstall with pip install lib",
        "shop/pricing.py": "def discount(price, rate):\n    if rate > 1:\n        raise ValueError\n    return price * rate\n",
        "main.py": "from shop.pricing import discount\n\nif __name__ == '__main__':\n    print(discount(10, 0.5))\n",
    }
    quest = analyze_snapshot(make_snapshot(files)).quest
    assert "the first unit test for `discount()`" in quest.title
    assert quest.likely_files[0] == "shop/pricing.py"


def test_repository_without_python_code():
    files = {"README.md": "# JS lib", "index.js": "module.exports = 1"}
    analysis = analyze_snapshot(make_snapshot(files, language="JavaScript"))
    assert analysis.learning_path == []
    assert analysis.flow == []
    assert analysis.quest is None
    assert analysis.framework.name == "Not determined"
    assert any("could not identify enough Python application code" in n for n in analysis.notes)
    assert any("JavaScript" in n for n in analysis.notes)


def test_no_entry_point_falls_back_to_importance():
    files = {"models.py": MODELS, "database.py": "import sqlite3\n\ndef save():\n    pass\n"}
    analysis = analyze_snapshot(make_snapshot(files))
    assert analysis.entry_points == []
    assert analysis.learning_path  # still suggests something to read
    assert any("could not find a likely entry point" in n for n in analysis.notes)
    assert any("no README" in n for n in analysis.notes)


def test_download_selection_respects_limits():
    tree = [TreeEntry("README.md", 500), TreeEntry("requirements.txt", 50), TreeEntry("app.py", 800)]
    tree += [TreeEntry(f"pkg/mod{i}.py", 1000) for i in range(100)]
    tree += [TreeEntry("venv/lib/site.py", 10), TreeEntry("big/data.py", 5_000_000), TreeEntry("api_pb2.py", 10)]
    paths, notes = choose_files_to_download(tree)

    assert paths[:3] == ["README.md", "requirements.txt", "app.py"]
    assert sum(p.endswith(".py") for p in paths) == 60
    assert "venv/lib/site.py" not in paths
    assert "big/data.py" not in paths and "api_pb2.py" not in paths
    assert any("analysed the 60" in n for n in notes)
    assert any("larger than" in n for n in notes)
