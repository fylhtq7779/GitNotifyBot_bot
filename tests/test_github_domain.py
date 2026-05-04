import pytest

from app.domain.enums import GitHubSourceType
from app.domain.github import GitHubRepositoryRef, build_source_key, parse_github_repository


@pytest.mark.parametrize(
    ("raw", "owner", "repo"),
    [
        ("octocat/hello-world", "octocat", "hello-world"),
        ("https://github.com/octocat/hello-world", "octocat", "hello-world"),
        ("https://github.com/octocat/hello-world.git", "octocat", "hello-world"),
        ("https://github.com/octocat/hello-world/releases", "octocat", "hello-world"),
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
        build_source_key(GitHubSourceType.RELEASES, "Octocat", "Hello-World")
        == "github:releases:octocat/hello-world"
    )


def test_build_release_source_key_accepts_repository_ref() -> None:
    repo = GitHubRepositoryRef(owner="Octocat", name="Hello-World")

    assert build_source_key(GitHubSourceType.RELEASES, repo.owner, repo.name) == (
        "github:releases:octocat/hello-world"
    )


def test_build_file_source_key() -> None:
    assert (
        build_source_key(
            GitHubSourceType.FILE,
            "Octocat",
            "Hello-World",
            branch="Main",
            file_path="/CHANGELOG.md",
        )
        == "github:file:octocat/hello-world:Main:CHANGELOG.md"
    )
