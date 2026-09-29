"""Turn a user-supplied GitHub URL into an (owner, repository) pair."""

from __future__ import annotations

import re

# GitHub usernames: letters, digits, single hyphens, max 39 chars.
_OWNER = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})"
# Repository names: letters, digits, '.', '_', '-'.
_REPO = r"[A-Za-z0-9._-]+"

_HTTPS_PATTERN = re.compile(
    rf"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>{_OWNER})/(?P<repo>{_REPO})(?:/.*)?$",
    re.IGNORECASE,
)
_SSH_PATTERN = re.compile(rf"^git@github\.com:(?P<owner>{_OWNER})/(?P<repo>{_REPO})$", re.IGNORECASE)

# First path segments on github.com that are site pages, not user accounts.
_RESERVED_OWNERS = {"orgs", "settings", "marketplace", "explore", "topics", "features", "login", "about"}


class InvalidGitHubURL(ValueError):
    """Raised when the text is not a recognisable GitHub repository URL."""


def parse_github_url(url: str) -> tuple[str, str]:
    """Return (owner, repo) for URLs such as:

    - https://github.com/owner/repo
    - https://github.com/owner/repo.git
    - https://github.com/owner/repo/tree/main/src
    - github.com/owner/repo
    - git@github.com:owner/repo.git
    """
    text = (url or "").strip()
    if not text:
        raise InvalidGitHubURL("Please enter a GitHub repository URL.")

    text = text.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    match = _HTTPS_PATTERN.match(text) or _SSH_PATTERN.match(text)
    if not match:
        raise InvalidGitHubURL(
            "That doesn't look like a GitHub repository URL. "
            "Use the format https://github.com/owner/repository."
        )

    owner = match.group("owner")
    repo = match.group("repo")
    if repo.lower().endswith(".git"):
        repo = repo[: -len(".git")]

    if owner.lower() in _RESERVED_OWNERS or not repo or repo in {".", ".."}:
        raise InvalidGitHubURL(
            "That GitHub link points to a page, not a repository. "
            "Use the format https://github.com/owner/repository."
        )
    return owner, repo
