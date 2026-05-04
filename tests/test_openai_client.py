from pathlib import Path

import pytest

from app.integrations.llm.openai_client import OpenAILLMClient, SummaryRequest
from app.integrations.llm.prompt_loader import load_prompt_template


class FakeResponse:
    output_text = (
        '{"title":"Claude Code updated","bullets":["Added CLI flag"],'
        '"breaking_changes":[],"links":["https://github.com/example/repo"],"confidence":"high"}'
    )
    usage = type("Usage", (), {"input_tokens": 10, "output_tokens": 12})()


class FakeResponses:
    def __init__(self) -> None:
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return FakeResponse()


class FakeOpenAI:
    def __init__(self) -> None:
        self.responses = FakeResponses()


@pytest.fixture
def prompt_template():
    return load_prompt_template(Path("app/prompts/github_update_summary.v1.yaml"))


async def test_openai_client_builds_responses_request(prompt_template):
    fake_openai = FakeOpenAI()
    client = OpenAILLMClient(openai_client=fake_openai)

    result = await client.summarize_update(
        SummaryRequest(
            prompt=prompt_template,
            repo_full_name="anthropics/claude-code",
            update_type="release",
            source="release",
            language="ru",
            style="short_technical",
            summary_preferences="breaking changes",
            update_payload="Release notes",
        )
    )

    assert result.summary.title == "Claude Code updated"
    assert result.input_tokens == 10
    assert result.output_tokens == 12
    assert fake_openai.responses.kwargs["model"] == "gpt-5.4-mini"
    assert fake_openai.responses.kwargs["reasoning"] == {"effort": "low", "summary": "concise"}
