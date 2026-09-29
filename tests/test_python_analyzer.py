from services.python_analyzer import analyze_python_source
from tests.conftest import DATABASE, FLASK_APP, TASK_ROUTES


def test_imports_are_collected():
    info = analyze_python_source("app.py", FLASK_APP)
    assert {"flask", "routes.task_routes", "database"} <= info.imported_modules
    assert "flask" in info.top_level_packages
    flask_import = next(i for i in info.imports if i.module == "flask")
    assert "Flask" in flask_import.names
    assert flask_import.lineno == 1


def test_relative_import_level():
    info = analyze_python_source("pkg/a.py", "from . import b\nfrom ..core import c\n")
    assert [(i.module, i.level) for i in info.imports] == [("", 1), ("core", 2)]


def test_functions_classes_and_methods_with_line_ranges():
    source = '''\
class Greeter:
    """Says hello."""

    def greet(self, name):
        return f"Hello {name}"


async def fetch():
    pass
'''
    info = analyze_python_source("greeter.py", source)
    assert [c.name for c in info.classes] == ["Greeter"]
    assert info.classes[0].has_docstring
    method = next(f for f in info.functions if f.name == "greet")
    assert method.kind == "method" and method.parent == "Greeter"
    assert method.display_name == "Greeter.greet()"
    assert (method.lineno, method.end_lineno) == (4, 5)
    fetch = next(f for f in info.functions if f.name == "fetch")
    assert fetch.is_async and not fetch.has_docstring


def test_routes_calls_and_template_refs():
    info = analyze_python_source("app.py", FLASK_APP)
    assert [r.function for r in info.routes] == ["index"]
    assert info.routes[0].decorator == "app.route('/')"
    assert info.calls_named("Flask")[0].lineno == 6
    assert info.template_refs == ["index.html"]


def test_blueprint_routes_are_detected():
    info = analyze_python_source("routes/task_routes.py", TASK_ROUTES)
    assert [r.function for r in info.routes] == ["add", "delete"]
    assert any(c.name == "request.form.get" for c in info.calls)


def test_main_guard_and_top_level_statements():
    info = analyze_python_source("app.py", FLASK_APP)
    assert info.has_main_guard
    assert info.main_guard_line == 15
    assert info.top_level_statements >= 2  # app = Flask(...), register_blueprint, if __main__


def test_branches_and_nesting():
    source = '''\
def f(items):
    for item in items:
        if item:
            while True:
                if item > 2 and item < 5:
                    break
'''
    info = analyze_python_source("f.py", source)
    assert info.branch_count == 5  # for, if, while, if, and
    assert info.max_nesting == 4
    assert info.functions[0].branch_count == 5


def test_line_count():
    info = analyze_python_source("database.py", DATABASE)
    assert info.line_count == len(DATABASE.splitlines())


def test_syntax_error_does_not_raise():
    info = analyze_python_source("broken.py", "def broken(:\n    pass\n")
    assert info.syntax_error
    assert info.functions == []
    assert info.line_count == 2
