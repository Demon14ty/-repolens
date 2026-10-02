"""Talk to GitHub. This is the only module that makes network requests to GitHub.

Metadata and the file tree come from the REST API. File contents are downloaded
from raw.githubusercontent.com, which does not count against the (small)
unauthenticated API rate limit of 60 requests per hour.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote

import requests

from models.repo_models import RepoMetadata, RepoSnapshot, TreeEntry

API_ROOT = "https://api.github.com"
RAW_ROOT = "https://raw.githubusercontent.com"
REQUEST_TIMEOUT_SECONDS = 15
DOWNLOAD_WORKERS = 8  # parallel file downloads


class GitHubError(Exception):
    """Base class. `str(error)` is a friendly message safe to show in the UI."""


class RepoNotFoundError(GitHubError):
    pass


class RateLimitError(GitHubError):
    pass


class EmptyRepositoryError(GitHubError):
    pass


class GitHubNetworkError(GitHubError):
    """GitHub could not be reached at all (DNS, timeout, connection reset)."""


class GitHubAuthError(GitHubError):
    """The configured GITHUB_TOKEN was rejected."""


class AccessDeniedError(GitHubError):
    """GitHub refused access for a reason other than rate limiting."""


def github_token() -> str:
    """Optional token from the environment. Public repos work without one."""
    return os.getenv("GITHUB_TOKEN", "").strip()


class GitHubClient:
    def __init__(self, token: str = "") -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "User-Agent": "RepoLens",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    # -- low level -----------------------------------------------------------

    def _get(self, url: str) -> requests.Response:
        try:
            response = self.session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise GitHubNetworkError(
                "Could not reach GitHub. Check your internet connection and try again."
            ) from exc
        return response

    def _get_api_json(self, path: str) -> dict:
        response = self._get(f"{API_ROOT}{path}")
        if response.status_code == 200:
            return response.json()
        raise _error_for_response(response)

    # -- public API ------------------------------------------------------------

    def get_metadata(self, owner: str, repo: str) -> RepoMetadata:
        data = self._get_api_json(f"/repos/{owner}/{repo}")
        return RepoMetadata(
            owner=data["owner"]["login"],
            name=data["name"],
            full_name=data["full_name"],
            description=data.get("description") or "",
            stars=int(data.get("stargazers_count") or 0),
            language=data.get("language") or "Unknown",
            default_branch=data.get("default_branch") or "main",
            html_url=data.get("html_url") or f"https://github.com/{owner}/{repo}",
            license=_license_name(data.get("license")),
        )

    def get_tree(self, owner: str, repo: str, branch: str) -> tuple[list[TreeEntry], bool]:
        """Return (files, truncated). GitHub truncates trees above ~100k entries."""
        data = self._get_api_json(f"/repos/{owner}/{repo}/git/trees/{quote(branch, safe='')}?recursive=1")
        entries = [
            TreeEntry(path=item["path"], size=int(item.get("size") or 0))
            for item in data.get("tree", [])
            if item.get("type") == "blob"
        ]
        return entries, bool(data.get("truncated"))

    def get_file_text(self, owner: str, repo: str, branch: str, path: str) -> str | None:
        """Download one file as text. Returns None if it fails or is not UTF-8."""
        url = f"{RAW_ROOT}/{owner}/{repo}/{quote(branch, safe='')}/{quote(path)}"
        try:
            response = self.session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException:
            return None
        if response.status_code != 200:
            return None
        try:
            return response.content.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def download_files(self, owner: str, repo: str, branch: str, paths: list[str]) -> dict[str, str]:
        with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
            texts = pool.map(lambda p: self.get_file_text(owner, repo, branch, p), paths)
            return {path: text for path, text in zip(paths, texts) if text is not None}


def _license_name(data: object) -> str:
    """GitHub's license object -> "MIT"; "" when there is none or GitHub could not identify it."""
    if not isinstance(data, dict):
        return ""
    spdx = data.get("spdx_id") or ""
    if spdx and spdx != "NOASSERTION":
        return spdx
    return data.get("name") or ""


def _error_for_response(response: requests.Response) -> GitHubError:
    """Translate an HTTP error into a friendly, specific exception."""
    status = response.status_code
    remaining = response.headers.get("X-RateLimit-Remaining")

    if status in (403, 429) and (remaining == "0" or status == 429):
        reset = response.headers.get("X-RateLimit-Reset")
        when = ""
        if reset and reset.isdigit():
            reset_time = datetime.fromtimestamp(int(reset), tz=timezone.utc)
            minutes = max(1, int((reset_time - datetime.now(timezone.utc)).total_seconds() // 60))
            when = f" Try again in about {minutes} minute(s)."
        return RateLimitError(
            "GitHub's API rate limit was reached." + when +
            " Adding a GITHUB_TOKEN to your .env file raises the limit from 60 to 5,000 requests per hour."
        )
    if status == 404:
        return RepoNotFoundError(
            "Repository not found. Check the URL for typos. "
            "Private repositories are not supported unless your GITHUB_TOKEN can access them."
        )
    if status == 401:
        return GitHubAuthError("GitHub rejected the GITHUB_TOKEN in your .env file. Check that it is valid.")
    if status == 409:
        return EmptyRepositoryError("This repository is empty, so there is nothing to analyse yet.")
    if status == 403:
        return AccessDeniedError("GitHub refused access to this repository (HTTP 403).")
    return GitHubError(f"GitHub returned an unexpected error (HTTP {status}). Please try again later.")


def fetch_snapshot(owner: str, repo: str, client: GitHubClient, choose_files) -> RepoSnapshot:
    """Fetch metadata + tree, then download only the files `choose_files` selects.

    `choose_files(tree) -> (paths, notes)` lives in the analyzer, so the rules
    for *what* to download stay next to the rules for *how* to analyse it.
    """
    metadata = client.get_metadata(owner, repo)
    tree, truncated = client.get_tree(metadata.owner, metadata.name, metadata.default_branch)
    paths, notes = choose_files(tree)
    files = client.download_files(metadata.owner, metadata.name, metadata.default_branch, paths)

    failed = len(paths) - len(files)
    if failed:
        notes.append(f"{failed} file(s) could not be downloaded or were not UTF-8 text and were skipped.")
    if truncated:
        notes.append("GitHub returned a partial file tree because this repository is very large.")
    return RepoSnapshot(metadata=metadata, tree=tree, files=files, tree_truncated=truncated, notes=notes)
