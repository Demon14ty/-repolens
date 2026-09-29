"""Lightweight static analysis of one Python file using the built-in `ast` module.

This is intentionally simple: it collects facts (imports, functions, calls,
branches...) and leaves interpretation to the scoring and learning-path code.
Nothing here executes the analysed code.
"""

from __future__ import annotations

import ast

from models.repo_models import CallSite, CodeSymbol, ImportInfo, PythonFileInfo, RouteInfo

# AST nodes that add a decision point (roughly: cyclomatic complexity).
BRANCH_NODES = (
    ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler,
    ast.IfExp, ast.BoolOp, ast.comprehension, ast.match_case,
)
# Statements that open a nested block, used to measure nesting depth.
NESTING_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match)
if hasattr(ast, "TryStar"):  # Python 3.11+
    NESTING_NODES = NESTING_NODES + (ast.TryStar,)

# Decorator method names that register web routes: @app.route, @router.get, ...
ROUTE_DECORATOR_ATTRS = {"route", "get", "post", "put", "delete", "patch", "websocket", "api_route"}
# Functions whose string arguments name a template file.
TEMPLATE_FUNCTIONS = {"render_template", "TemplateResponse", "render", "render_to_response", "get_template"}

MAX_DECORATOR_TEXT = 80


def analyze_python_source(path: str, source: str) -> PythonFileInfo:
    """Analyse Python source text. Never raises on bad code: syntax errors are recorded."""
    info = PythonFileInfo(path=path, line_count=_count_lines(source))
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as exc:
        info.syntax_error = f"Could not parse this file: {exc.__class__.__name__}"
        return info

    info.imports = _collect_imports(tree)
    info.functions, info.classes = _collect_symbols(tree)
    info.calls = _collect_calls(tree)
    info.decorators = sorted({d for sym in info.functions + info.classes for d in sym.decorators})
    info.routes = _collect_routes(tree)
    info.template_refs = _collect_template_refs(tree)
    info.branch_count = _count_branches(tree)
    info.max_nesting = _max_nesting(tree)
    info.main_guard_line = _main_guard_line(tree)
    info.has_main_guard = info.main_guard_line > 0
    info.top_level_statements = _count_top_level_statements(tree)
    return info


# ---------------------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------------------


def _count_lines(source: str) -> int:
    return len(source.splitlines())


def _collect_imports(tree: ast.AST) -> list[ImportInfo]:
    imports: list[ImportInfo] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportInfo(module=alias.name, names=[], level=0, lineno=node.lineno))
        elif isinstance(node, ast.ImportFrom):
            imports.append(
                ImportInfo(
                    module=node.module or "",
                    names=[alias.name for alias in node.names],
                    level=node.level,
                    lineno=node.lineno,
                )
            )
    return imports


def _collect_symbols(tree: ast.Module) -> tuple[list[CodeSymbol], list[CodeSymbol]]:
    """Top-level functions, classes, and the methods directly inside classes."""
    functions: list[CodeSymbol] = []
    classes: list[CodeSymbol] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(_function_symbol(node, kind="function"))
        elif isinstance(node, ast.ClassDef):
            classes.append(
                CodeSymbol(
                    name=node.name,
                    kind="class",
                    lineno=_start_line(node),
                    end_lineno=node.end_lineno or node.lineno,
                    decorators=[_short_unparse(d) for d in node.decorator_list],
                    branch_count=_count_branches(node),
                    bases=[_dotted_name(base) or _short_unparse(base) for base in node.bases],
                    has_docstring=ast.get_docstring(node) is not None,
                )
            )
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append(_function_symbol(child, kind="method", parent=node.name))
    return functions, classes


def _start_line(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> int:
    """First line of a definition, including any decorators above it."""
    return min([node.lineno] + [d.lineno for d in node.decorator_list])


def _function_symbol(node: ast.FunctionDef | ast.AsyncFunctionDef, kind: str, parent: str = "") -> CodeSymbol:
    return CodeSymbol(
        name=node.name,
        kind=kind,
        lineno=_start_line(node),
        end_lineno=node.end_lineno or node.lineno,
        decorators=[_short_unparse(d) for d in node.decorator_list],
        is_async=isinstance(node, ast.AsyncFunctionDef),
        branch_count=_count_branches(node),
        parent=parent,
        has_docstring=ast.get_docstring(node) is not None,
    )


def _collect_calls(tree: ast.AST) -> list[CallSite]:
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _dotted_name(node.func)
            if name:
                calls.append(CallSite(name=name, lineno=node.lineno))
    return sorted(calls, key=lambda c: c.lineno)


def _collect_routes(tree: ast.Module) -> list[RouteInfo]:
    routes = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if isinstance(target, ast.Attribute) and target.attr in ROUTE_DECORATOR_ATTRS:
                routes.append(
                    RouteInfo(
                        function=node.name,
                        decorator=_short_unparse(decorator),
                        lineno=_start_line(node),
                        end_lineno=node.end_lineno or node.lineno,
                    )
                )
                break
    return routes


def _collect_template_refs(tree: ast.AST) -> list[str]:
    refs: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = (_dotted_name(node.func) or "").split(".")[-1]
        if name not in TEMPLATE_FUNCTIONS:
            continue
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.endswith(
                (".html", ".jinja", ".jinja2", ".j2", ".txt")
            ):
                refs.append(arg.value)
    return sorted(set(refs))


def _count_branches(node: ast.AST) -> int:
    return sum(isinstance(child, BRANCH_NODES) for child in ast.walk(node))


def _max_nesting(node: ast.AST, current: int = 0) -> int:
    deepest = current
    for child in ast.iter_child_nodes(node):
        child_depth = current + 1 if isinstance(child, NESTING_NODES) else current
        deepest = max(deepest, _max_nesting(child, child_depth))
    return deepest


def _main_guard_line(tree: ast.Module) -> int:
    """Line of `if __name__ == "__main__":` at module level, or 0."""
    for node in tree.body:
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        left, comparators = node.test.left, node.test.comparators
        values = [left] + list(comparators)
        has_name = any(isinstance(v, ast.Name) and v.id == "__name__" for v in values)
        has_main = any(isinstance(v, ast.Constant) and v.value == "__main__" for v in values)
        if has_name and has_main:
            return node.lineno
    return 0


def _count_top_level_statements(tree: ast.Module) -> int:
    """Executable module-level statements (not imports, defs, or the docstring)."""
    count = 0
    for index, node in enumerate(tree.body):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        is_docstring = index == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
        if not is_docstring:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Small AST helpers
# ---------------------------------------------------------------------------


def _dotted_name(node: ast.AST) -> str:
    """'a.b.c' for Name/Attribute chains; '' for anything more complex."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _short_unparse(node: ast.AST) -> str:
    text = ast.unparse(node)
    return text if len(text) <= MAX_DECORATOR_TEXT else text[: MAX_DECORATOR_TEXT - 3] + "..."
