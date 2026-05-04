from dataclasses import dataclass
from urllib.parse import urlparse

from app.domain.enums import GitHubSourceType


@dataclass(frozen=True)
class GitHubRepositoryRef:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


def parse_github_repository(raw: str) -> GitHubRepositoryRef:
    value = raw.strip()
    if value.startswith(("https://", "http://")):
        parsed = urlparse(value)
        if parsed.netloc.lower() != "github.com":
            raise ValueError("Expected a GitHub repository URL or owner/repo value")
        parts = [part for part in parsed.path.strip("/").split("/") if part]
    else:
        parts = [part for part in value.strip("/").split("/") if part]

    if len(parts) < 2:
        raise ValueError("Expected a GitHub repository URL or owner/repo value")

    owner = parts[0].strip()
    name = parts[1].removesuffix(".git").strip()
    if not owner or not name:
        raise ValueError("Expected a GitHub repository URL or owner/repo value")

    return GitHubRepositoryRef(owner=owner, name=name)


def build_source_key(
    source_type: GitHubSourceType,
    owner: str,
    repo: str,
    *,
    branch: str | None = None,
    file_path: str | None = None,
) -> str:
    normalized_repo = f"{owner.lower()}/{repo.lower()}"
    if source_type == GitHubSourceType.RELEASES:
        return f"github:releases:{normalized_repo}"

    if source_type == GitHubSourceType.FILE:
        if not branch or not file_path:
            raise ValueError("File source key requires branch and file_path")
        normalized_path = file_path.strip("/")
        return f"github:file:{normalized_repo}:{branch}:{normalized_path}"

    raise ValueError(f"Unsupported GitHub source type: {source_type}")
