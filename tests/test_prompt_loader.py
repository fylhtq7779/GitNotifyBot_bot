from pathlib import Path

from app.integrations.llm.prompt_loader import PromptVariables, load_prompt_template


def test_load_prompt_template() -> None:
    prompt = load_prompt_template(Path("app/prompts/github_update_summary.v1.yaml"))

    assert prompt.id == "github_update_summary"
    assert prompt.version == "v1"
    assert prompt.model == "gpt-5.4-mini"
    assert prompt.reasoning.effort == "low"
    assert prompt.reasoning.summary == "concise"
    assert prompt.text.verbosity == "low"


def test_render_prompt_template() -> None:
    prompt = load_prompt_template(Path("app/prompts/github_update_summary.v1.yaml"))
    rendered = prompt.render_user(
        PromptVariables(
            repo_full_name="anthropics/claude-code",
            update_type="file_change",
            source="CHANGELOG.md",
            language="ru",
            style="short_technical",
            summary_preferences="CLI flags and breaking changes",
            update_payload="Changed CLI behavior",
        )
    )

    assert "anthropics/claude-code" in rendered
    assert "Changed CLI behavior" in rendered
    assert "{{" not in rendered
