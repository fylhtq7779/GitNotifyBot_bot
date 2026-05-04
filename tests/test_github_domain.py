import pytest

from app.domain.enums import GitHubSourceType
from app.domain.github import GitHubRepositoryRef, build_source_key, parse_github_repository


@pytest.mark.parametrize(
    ("raw", "owner", "repo"),
    [
        ("anthropics/claude-code", "anthropics", "claude-code"),
        ("https://github.com/anthropics/claude-code", "anthropics", "claude-code"),
        ("https://github.com/anthropics/claude-code.git", "anthropics", "claude-code"),
        ("https://github.com/anthropics/claude-code/releases", "anthropics", "claude-code"),
    ],
)
def test_parse_github_repository(raw: str, owner: str, repo: str) -> None:
    parsed = parse_github_repository(raw)

    assert parsed == GitHubRepositoryRef(owner=owner, name=repo)
    assert parsed.full_name == f"{owner}/{repo}"


def test_parse_github_repository_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="GitHub repository"):
        parse_github_repository("not a repo")


def test_build_release_source_key() -> None:
    assert (
        build_source_key(GitHubSourceType.RELEASES, "Anthropics", "Claude-Code")
        == "github:releases:anthropics/claude-code"
    )


def test_build_release_source_key_accepts_repository_ref() -> None:
    repo = GitHubRepositoryRef(owner="Anthropics", name="Claude-Code")

    assert build_source_key(GitHubSourceType.RELEASES, repo.owner, repo.name) == (
        "github:releases:anthropics/claude-code"
    )


def test_build_file_source_key() -> None:
    assert (
        build_source_key(
            GitHubSourceType.FILE,
            "Anthropics",
            "Claude-Code",
            branch="Main",
            file_path="/CHANGELOG.md",
        )
        == "github:file:anthropics/claude-code:Main:CHANGELOG.md"
    )
