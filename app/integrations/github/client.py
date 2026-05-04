import urllib.parse
from dataclasses import dataclass
from typing import Any, cast

import httpx

from app.domain.github import GitHubRepositoryRef

GITHUB_API_URL = "https://api.github.com"


class GitHubApiError(RuntimeError):
    pass


class GitHubNotFoundError(GitHubApiError):
    pass


@dataclass(frozen=True)
class GitHubRepository:
    owner: str
    name: str
    full_name: str
    html_url: str
    default_branch: str
    is_archived: bool


@dataclass(frozen=True)
class GitHubRelease:
    release_id: str | None
    tag_name: str | None
    name: str | None
    html_url: str | None
    body: str | None


@dataclass(frozen=True)
class GitHubFileContents:
    path: str
    sha: str
    size: int | None
    html_url: str | None
    download_url: str | None


class GitHubClient:
    def __init__(self, token: str, *, timeout_seconds: float = 20) -> None:
        self._token = token
        self._timeout_seconds = timeout_seconds

    async def get_repository(self, ref: GitHubRepositoryRef) -> GitHubRepository:
        data = await self._request_json("GET", f"/repos/{ref.owner}/{ref.name}")
        owner_data = data.get("owner") if isinstance(data.get("owner"), dict) else {}
        owner = str(owner_data.get("login") or data["full_name"].split("/", maxsplit=1)[0])
        name = str(data["name"])
        return GitHubRepository(
            owner=owner,
            name=name,
            full_name=str(data["full_name"]),
            html_url=str(data["html_url"]),
            default_branch=str(data["default_branch"]),
            is_archived=bool(data.get("archived", False)),
        )

    async def get_latest_release(self, ref: GitHubRepositoryRef) -> GitHubRelease | None:
        try:
            data = await self._request_json("GET", f"/repos/{ref.owner}/{ref.name}/releases/latest")
        except GitHubNotFoundError:
            return None

        return GitHubRelease(
            release_id=str(data["id"]) if data.get("id") is not None else None,
            tag_name=str(data["tag_name"]) if data.get("tag_name") is not None else None,
            name=str(data["name"]) if data.get("name") is not None else None,
            html_url=str(data["html_url"]) if data.get("html_url") is not None else None,
            body=str(data["body"]) if isinstance(data.get("body"), str) else None,
        )

    async def get_file_contents(
        self, ref: GitHubRepositoryRef, *, path: str, branch: str
    ) -> GitHubFileContents:
        normalized_path = path.strip("/")
        if not normalized_path:
            raise ValueError("File path must not be empty")
        encoded_path = urllib.parse.quote(normalized_path, safe="/")
        encoded_branch = urllib.parse.quote(branch, safe="")
        payload = await self._request_any(
            "GET",
            f"/repos/{ref.owner}/{ref.name}/contents/{encoded_path}?ref={encoded_branch}",
        )
        if isinstance(payload, list):
            raise GitHubApiError(
                "GitHub returned a directory listing; provide a path to a single file"
            )
        if not isinstance(payload, dict):
            raise GitHubApiError("GitHub API returned an unexpected file payload")
        if payload.get("type") != "file":
            raise GitHubApiError(
                f"Path is not a regular file (type={payload.get('type')})"
            )
        sha = payload.get("sha")
        if not isinstance(sha, str):
            raise GitHubApiError("GitHub API returned a file without a sha")
        size_raw = payload.get("size")
        size = int(size_raw) if isinstance(size_raw, int) else None
        return GitHubFileContents(
            path=str(payload.get("path") or normalized_path),
            sha=sha,
            size=size,
            html_url=str(payload["html_url"])
            if isinstance(payload.get("html_url"), str)
            else None,
            download_url=str(payload["download_url"])
            if isinstance(payload.get("download_url"), str)
            else None,
        )

    async def _request_json(self, method: str, path: str) -> dict[str, Any]:
        payload = await self._request_any(method, path)
        if not isinstance(payload, dict):
            raise GitHubApiError("GitHub API returned an unexpected response")
        return payload

    async def _request_any(self, method: str, path: str) -> Any:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "GitNotifyBot",
        }
        async with httpx.AsyncClient(
            base_url=GITHUB_API_URL,
            headers=headers,
            timeout=self._timeout_seconds,
            follow_redirects=True,
        ) as client:
            response = await client.request(method, path)

        if response.status_code == 404:
            raise GitHubNotFoundError("GitHub repository or resource was not found")
        if response.status_code >= 400:
            raise GitHubApiError(
                f"GitHub API request failed with HTTP {response.status_code}"
            )
        return cast(Any, response.json())
