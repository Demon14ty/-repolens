"""Shared test fixtures: small, hand-written repositories (no network access)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.repo_models import RepoMetadata, RepoSnapshot, TreeEntry  # noqa: E402

FLASK_APP = '''\
from flask import Flask, render_template, request, redirect

from routes.task_routes import tasks_bp
from database import get_tasks

app = Flask(__name__)
app.register_blueprint(tasks_bp)


@app.route("/")
def index():
    return render_template("index.html", tasks=get_tasks())


if __name__ == "__main__":
    app.run(debug=True)
'''

TASK_ROUTES = '''\
from flask import Blueprint, request, redirect

from database import add_task, delete_task
from models import Task

tasks_bp = Blueprint("tasks", __name__)


@tasks_bp.route("/add", methods=["POST"])
def add():
    title = request.form.get("title")
    add_task(Task(title=title))
    return redirect("/")


@tasks_bp.route("/delete/<int:task_id>", methods=["POST"])
def delete(task_id):
    delete_task(task_id)
    return redirect("/")
'''

DATABASE = '''\
import sqlite3

from models import Task

DB_PATH = "tasks.db"


def get_tasks():
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT id, title FROM tasks").fetchall()
    return [Task(id=row[0], title=row[1]) for row in rows]


def add_task(task):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO tasks (title) VALUES (?)", (task.title,))


def delete_task(task_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
'''

MODELS = '''\
from dataclasses import dataclass


@dataclass
class Task:
    title: str
    id: int = 0
'''

UTILS = '''\
def shorten(text, limit=20):
    if len(text) <= limit:
        return text
    return text[:limit] + "..."
'''

INDEX_HTML = '''\
<h1>Tasks</h1>
<ul>
{% for task in tasks %}
  <li>{{ task.title }}</li>
{% endfor %}
</ul>
'''

README = "# Flask Todo\n\nA tiny todo app.\n\n## How to run\n\npip install -r requirements.txt\npython app.py\n"


def make_snapshot(files: dict[str, str], extra_tree: list[str] | None = None, language: str = "Python") -> RepoSnapshot:
    """Build a RepoSnapshot from {path: content}; `extra_tree` adds files that were not downloaded."""
    tree = [TreeEntry(path=p, size=len(text)) for p, text in files.items()]
    tree += [TreeEntry(path=p, size=100) for p in extra_tree or []]
    metadata = RepoMetadata(
        owner="student", name="flask-todo", full_name="student/flask-todo", description="A todo app",
        stars=3, language=language, default_branch="main", html_url="https://github.com/student/flask-todo",
    )
    return RepoSnapshot(metadata=metadata, tree=tree, files=files)


@pytest.fixture
def flask_files() -> dict[str, str]:
    return {
        "README.md": README,
        "requirements.txt": "Flask==3.0.0\npytest\n",
        "app.py": FLASK_APP,
        "routes/task_routes.py": TASK_ROUTES,
        "database.py": DATABASE,
        "models.py": MODELS,
        "utils.py": UTILS,
        "templates/index.html": INDEX_HTML,
    }


@pytest.fixture
def flask_snapshot(flask_files) -> RepoSnapshot:
    extra = [
        "Dockerfile",
        ".github/workflows/ci.yml",
        "migrations/001_init.py",
        "migrations/002_add_done.py",
        "tests/integration/test_flow.py",
        "static/style.css",
    ]
    return make_snapshot(flask_files, extra_tree=extra)
