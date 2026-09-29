import pytest

from utils.github_parser import InvalidGitHubURL, parse_github_url


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/pallets/flask",
        "https://github.com/pallets/flask/",
        "http://github.com/pallets/flask",
        "https://www.github.com/pallets/flask",
        "github.com/pallets/flask",
        "https://github.com/pallets/flask.git",
        "https://github.com/pallets/flask/tree/main/src/flask",
        "https://github.com/pallets/flask/blob/main/README.md",
        "https://github.com/pallets/flask?tab=readme-ov-file",
        "https://github.com/pallets/flask#readme",
        "git@github.com:pallets/flask.git",
        "  https://github.com/pallets/flask  ",
    ],
)
def test_valid_urls(url):
    assert parse_github_url(url) == ("pallets", "flask")


def test_repo_names_with_dots_and_dashes():
    assert parse_github_url("https://github.com/owner-1/my.repo_name-2") == ("owner-1", "my.repo_name-2")


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "not a url",
        "https://gitlab.com/owner/repo",
        "https://github.com/owner",
        "https://github.com/",
        "https://example.com/github.com/owner/repo",
        "https://github.com/orgs/python",
        "https://github.com/settings/profile",
    ],
)
def test_invalid_urls(url):
    with pytest.raises(InvalidGitHubURL):
        parse_github_url(url)


def test_error_message_is_friendly():
    with pytest.raises(InvalidGitHubURL, match="https://github.com/owner/repository"):
        parse_github_url("hello")
