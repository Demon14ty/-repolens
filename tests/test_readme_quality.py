"""README Quality Checker: transparent, evidence-based scoring (no network, no AI)."""

from services.readme_quality import evaluate_readme, find_readme, score_label

STRONG_README = """\
# TaskBoard

![Build](https://img.shields.io/badge/build-passing-green.svg)

TaskBoard is a small Flask web application that helps teams track their daily tasks in the browser.

## Features

- Create, edit and delete tasks
- Filter tasks by status

![Screenshot of the task board](docs/screenshot.png)

## Installation

```bash
git clone https://github.com/example/taskboard.git
cd taskboard
python -m venv .venv
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and set `SECRET_KEY` and `DATABASE_URL` environment variables.

## Usage

```bash
flask --app app run
```

Then open http://localhost:5000 in your browser.

## Running tests

```bash
pytest
```

## Troubleshooting

If you see `ModuleNotFoundError`, make sure your virtual environment is activated.

## Contributing

Pull requests are welcome. Please open an issue first to discuss what you would like to change.

## License

This project is licensed under the MIT License.
"""


def checks(result):
    return {check.key: check for check in result.checks}


def test_missing_readme_scores_zero_with_explanation():
    result = evaluate_readme(None, None)
    assert result.score == 0
    assert result.path is None
    assert result.label == "Needs major improvement"
    assert "No README" in result.interpretation
    assert not result.strengths
    assert len(result.missing) == 10
    assert all(check.suggestion for check in result.missing)


def test_strong_readme_scores_excellent():
    result = evaluate_readme("README.md", STRONG_README)
    assert result.score == 100
    assert result.label == "Excellent onboarding"
    found = checks(result)
    assert any("Installation" in e for e in found["installation"].evidence)
    assert any("docs/screenshot.png" in e for e in found["visuals"].evidence)
    assert all(check.evidence for check in result.checks)  # every point is backed by evidence


def test_setup_without_tests_is_not_rewarded_for_testing():
    readme = (
        "# Weather CLI\n\nA command-line tool that prints the weather forecast for any city you type in.\n\n"
        "## Installation\n\n```\npip install -r requirements.txt\n```\n\n"
        "## Usage\n\n```\npython weather.py London\n```\n"
    )
    result = evaluate_readme("README.md", readme)
    found = checks(result)
    for key in ("exists", "description", "installation", "environment", "usage"):
        assert found[key].passed, key
    for key in ("testing", "contribution", "license", "visuals", "troubleshooting"):
        assert not found[key].passed, key
    assert result.score == 60
    assert result.label == "Good onboarding"
    missing_keys = {check.key for check in result.missing}
    assert "testing" in missing_keys
    assert any("Testing" in check.suggestion for check in result.missing)


def test_headings_without_meaningful_content_earn_nothing():
    readme = (
        "# My Project\n\n## Installation\n\nTODO\n\n## Usage\n\n\n## Testing\n\nComing soon.\n\n"
        "## Contributing\n\nTBD\n\n## Troubleshooting\n\n...\n"
    )
    result = evaluate_readme("README.md", readme)
    assert result.score == 15  # only "README exists"
    assert [check.key for check in result.strengths] == ["exists"]
    assert result.label == "Needs major improvement"


def test_code_block_comments_are_not_headings():
    readme = "# Tool\n\n```bash\n# Installation\n# testing\n```\n"
    found = checks(evaluate_readme("README.md", readme))
    assert not found["testing"].passed
    assert not any("Heading" in e for e in found["installation"].evidence)


def test_screenshots_count_but_badges_do_not():
    with_image = "# App\n\n![Demo](assets/demo.gif)\n"
    only_badge = "# App\n\n[![CI](https://github.com/a/b/actions/workflows/ci.yml/badge.svg)](link)\n"
    html_image = '# App\n\n<img src="images/ui.png" width="400">\n'
    assert checks(evaluate_readme("README.md", with_image))["visuals"].passed
    assert checks(evaluate_readme("README.md", html_image))["visuals"].passed
    assert not checks(evaluate_readme("README.md", only_badge))["visuals"].passed


def test_empty_or_undownloaded_readme():
    empty = evaluate_readme("README.md", "   \n")
    assert empty.score == 0 and empty.notes
    too_big = evaluate_readme("README.md", None)
    assert too_big.score == 15 and "could not be downloaded" in too_big.notes[0]


def test_find_readme_and_labels():
    assert find_readme({"README.md": "x", "docs/README.md": "y"}) == ("README.md", True)
    assert find_readme({}, ["readme.rst"]) == ("readme.rst", False)
    assert find_readme({"docs/README.md": "y"}, ["docs/README.md"]) == (None, False)
    assert [score_label(s) for s in (0, 39, 40, 59, 60, 79, 80, 100)] == [
        "Needs major improvement", "Needs major improvement", "Basic onboarding", "Basic onboarding",
        "Good onboarding", "Good onboarding", "Excellent onboarding", "Excellent onboarding",
    ]


def test_rst_underlined_headings_are_recognised():
    readme = "Tool\n====\n\nTesting\n-------\n\nRun the whole suite with pytest from the project root.\n"
    assert checks(evaluate_readme("README.rst", readme))["testing"].passed


def test_analysis_includes_readme_quality(flask_snapshot):
    from services.repo_analyzer import analyze_snapshot

    quality = analyze_snapshot(flask_snapshot).readme_quality
    assert quality is not None and quality.path == "README.md"
    assert checks(quality)["installation"].passed
    assert not checks(quality)["testing"].passed
