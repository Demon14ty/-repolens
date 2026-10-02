"""Structured, user-safe API errors.

Every failure becomes {"error": {"code", "title", "message", "details"}}. Messages
are written for the person using the website: they never include stack traces,
upstream response bodies or configuration values.
"""

from __future__ import annotations

from urllib.parse import urlparse

from services.github_service import (
    AccessDeniedError,
    EmptyRepositoryError,
    GitHubAuthError,
    GitHubError,
    GitHubNetworkError,
    RateLimitError,
    RepoNotFoundError,
)


class ApiError(Exception):
    def __init__(self, status: int, code: str, title: str, message: str,
                 details: dict[str, str | int] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.title = title
        self.message = message
        self.details = details

    def body(self) -> dict:
        return {"error": {"code": self.code, "title": self.title, "message": self.message, "details": self.details}}


def invalid_url(raw: str) -> ApiError:
    """Distinguish 'not a URL to GitHub at all' from 'a GitHub URL that is not a repository'."""
    text = (raw or "").strip()
    host = urlparse(text if "://" in text else f"https://{text}").hostname or ""
    if text and "." in host and host.lower() not in {"github.com", "www.github.com"}:
        return ApiError(400, "NOT_GITHUB_URL", "Only GitHub repositories are supported",
                        "RepoLens reads repositories hosted on github.com. Paste a URL such as "
                        "https://github.com/owner/repository.")
    return ApiError(400, "INVALID_REPOSITORY_URL", "Invalid GitHub URL",
                    "Enter a public GitHub repository URL such as https://github.com/owner/repository.")


def invalid_analysis_id() -> ApiError:
    return ApiError(400, "INVALID_ANALYSIS_ID", "Unknown analysis",
                    "This question does not belong to a repository RepoLens can identify. Analyse the repository again.")


def empty_question() -> ApiError:
    return ApiError(400, "EMPTY_QUESTION", "Question is empty", "Type a question about the repository first.")


def empty_repository() -> ApiError:
    return ApiError(422, "EMPTY_REPOSITORY", "This repository is empty",
                    "There are no files on the default branch yet, so there is nothing to analyse.")


def from_github_error(error: GitHubError) -> ApiError:
    if isinstance(error, RateLimitError):
        return ApiError(429, "GITHUB_RATE_LIMITED", "GitHub rate limit reached",
                        "GitHub is limiting requests from this server right now. Wait a few minutes and try again.")
    if isinstance(error, RepoNotFoundError):
        return ApiError(404, "REPOSITORY_NOT_FOUND", "Repository not found",
                        "GitHub could not find this repository. Check the URL for typos. Private repositories "
                        "are not supported.")
    if isinstance(error, EmptyRepositoryError):
        return empty_repository()
    if isinstance(error, AccessDeniedError):
        return ApiError(403, "REPOSITORY_INACCESSIBLE", "Repository is not accessible",
                        "GitHub refused access to this repository. It may be private, blocked or restricted.")
    if isinstance(error, GitHubAuthError):
        return ApiError(502, "GITHUB_AUTH_FAILED", "GitHub rejected the server's credentials",
                        "The GitHub token configured on this server is not valid. The site owner needs to update it.")
    if isinstance(error, GitHubNetworkError):
        return ApiError(503, "GITHUB_UNAVAILABLE", "Could not reach GitHub",
                        "RepoLens could not connect to GitHub. Check that GitHub is reachable and try again.")
    return ApiError(502, "GITHUB_ERROR", "GitHub returned an error",
                    "GitHub returned an unexpected response. Please try again in a moment.")


def unexpected() -> ApiError:
    return ApiError(500, "INTERNAL_ERROR", "Something went wrong",
                    "RepoLens hit an unexpected problem while handling this request. Please try again.")
