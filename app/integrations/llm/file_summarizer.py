from dataclasses import dataclass
from typing import Protocol

from app.domain.github import GitHubRepositoryRef
from app.integrations.llm.openai_client import OpenAILLMClient, SummaryRequest
from app.integrations.llm.prompt_loader import PromptTemplate

MAX_PATCH_CHARS = 12000
MAX_FILE_CHARS = 8000


@dataclass(frozen=True)
class FileSummary:
    title: str
    bullets: list[str]
    breaking_changes: list[str]
    links: list[str]
    confidence: str
    prompt_id: str
    prompt_version: str
    model_name: str
    reasoning_effort: str
    text_verbosity: str
    input_tokens: int | None
    output_tokens: int | None


class GitHubCommitRefProto(Protocol):
    sha: str
    message: str
    author_name: str | None
    author_date: str | None
    html_url: str | None


class GitHubCommitFilePatchProto(Protocol):
    commit_sha: str
    file_path: str
    status: str | None
    additions: int | None
    deletions: int | None
    patch: str | None
    html_url: str | None


class GitHubCommitsClient(Protocol):
    async def list_commits_for_path(
        self,
        ref: GitHubRepositoryRef,
        *,
        path: str,
        branch: str,
        limit: int = 5,
    ) -> list[GitHubCommitRefProto]:
        raise NotImplementedError

    async def get_commit_file_patch(
        self, ref: GitHubRepositoryRef, *, commit_sha: str, path: str
    ) -> GitHubCommitFilePatchProto | None:
        raise NotImplementedError

    async def fetch_file_text(
        self, ref: GitHubRepositoryRef, *, path: str, branch: str
    ) -> str | None:
        raise NotImplementedError


class OpenAIFileSummarizer:
    def __init__(
        self,
        client: OpenAILLMClient,
        prompt: PromptTemplate,
        github_client: GitHubCommitsClient,
    ) -> None:
        self._client = client
        self._prompt = prompt
        self._github = github_client

    async def summarize_file_change(
        self,
        *,
        repository_full_name: str,
        branch: str,
        file_path: str,
        previous_sha: str | None,
        new_sha: str,
        file_html_url: str | None,
        language: str,
        style: str,
        preferences: str,
    ) -> FileSummary:
        owner, _, name = repository_full_name.partition("/")
        ref = GitHubRepositoryRef(owner=owner, name=name)

        commits: list[GitHubCommitRefProto] = []
        try:
            commits = await self._github.list_commits_for_path(
                ref, path=file_path, branch=branch, limit=3
            )
        except Exception:
            commits = []

        latest_patch: GitHubCommitFilePatchProto | None = None
        if commits:
            try:
                latest_patch = await self._github.get_commit_file_patch(
                    ref, commit_sha=commits[0].sha, path=file_path
                )
            except Exception:
                latest_patch = None

        file_excerpt: str | None = None
        if latest_patch is None or not (latest_patch.patch and latest_patch.patch.strip()):
            try:
                file_excerpt = await self._github.fetch_file_text(
                    ref, path=file_path, branch=branch
                )
            except Exception:
                file_excerpt = None

        payload = _build_payload(
            file_path=file_path,
            file_html_url=file_html_url,
            commits=commits,
            patch=latest_patch,
            file_excerpt=file_excerpt,
        )
        result = await self._client.summarize_update(
            SummaryRequest(
                prompt=self._prompt,
                repo_full_name=repository_full_name,
                update_type="file_change",
                source="github_file",
                language=language,
                style=style,
                summary_preferences=preferences or "—",
                update_payload=payload,
            )
        )
        summary = result.summary
        return FileSummary(
            title=summary.title,
            bullets=list(summary.bullets),
            breaking_changes=list(summary.breaking_changes),
            links=list(summary.links),
            confidence=summary.confidence,
            prompt_id=self._prompt.id,
            prompt_version=self._prompt.version,
            model_name=self._prompt.model,
            reasoning_effort=self._prompt.reasoning.effort,
            text_verbosity=self._prompt.text.verbosity,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )


def _build_payload(
    *,
    file_path: str,
    file_html_url: str | None,
    commits: list[GitHubCommitRefProto],
    patch: GitHubCommitFilePatchProto | None,
    file_excerpt: str | None,
) -> str:
    lines: list[str] = [f"File path: {file_path}"]
    if file_html_url:
        lines.append(f"URL: {file_html_url}")

    if commits:
        lines.append("")
        lines.append(
            "Recent commits affecting this file (newest first; "
            "focus on the most recent one):"
        )
        for index, commit in enumerate(commits, start=1):
            short_sha = commit.sha[:7]
            author = commit.author_name or "unknown"
            date = commit.author_date or "unknown date"
            message_first_line = (commit.message or "").splitlines()[0] if commit.message else ""
            lines.append(f"{index}. {short_sha} by {author} on {date}: {message_first_line}")

    if patch is not None:
        lines.append("")
        lines.append("Diff of the most recent commit for this file:")
        if patch.additions is not None or patch.deletions is not None:
            lines.append(
                f"(+{patch.additions or 0} -{patch.deletions or 0}, status={patch.status or '?'})"
            )
        patch_text = patch.patch or ""
        if patch_text.strip():
            truncated = patch_text[:MAX_PATCH_CHARS]
            lines.append(truncated)
            if len(patch_text) > MAX_PATCH_CHARS:
                lines.append("[…patch truncated]")
        else:
            lines.append("(patch is empty — possibly binary or rename without changes)")
    elif file_excerpt is not None:
        lines.append("")
        lines.append(
            "Patch unavailable; below is the current file content (truncated). "
            "Summarize the most recent change you can infer from the latest commit message:"
        )
        truncated = file_excerpt[:MAX_FILE_CHARS]
        lines.append(truncated)
        if len(file_excerpt) > MAX_FILE_CHARS:
            lines.append("[…content truncated]")
    else:
        lines.append("")
        lines.append(
            "No patch or file content available. "
            "Summarize from the commit messages above only."
        )

    return "\n".join(lines)
