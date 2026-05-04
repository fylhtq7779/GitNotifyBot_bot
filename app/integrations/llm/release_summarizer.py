from dataclasses import dataclass

from app.integrations.llm.openai_client import OpenAILLMClient, SummaryRequest
from app.integrations.llm.prompt_loader import PromptTemplate

MAX_BODY_CHARS = 12000


@dataclass(frozen=True)
class ReleaseSummary:
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


class OpenAIReleaseSummarizer:
    def __init__(self, client: OpenAILLMClient, prompt: PromptTemplate) -> None:
        self._client = client
        self._prompt = prompt

    async def summarize_release(
        self,
        *,
        repository_full_name: str,
        tag_name: str | None,
        release_name: str | None,
        body: str | None,
        html_url: str | None,
        language: str,
        style: str,
        preferences: str,
    ) -> ReleaseSummary:
        payload = _build_payload(
            tag_name=tag_name,
            release_name=release_name,
            body=body,
            html_url=html_url,
        )
        result = await self._client.summarize_update(
            SummaryRequest(
                prompt=self._prompt,
                repo_full_name=repository_full_name,
                update_type="release",
                source="github_releases",
                language=language,
                style=style,
                summary_preferences=preferences or "(no preferences)",
                update_payload=payload,
            )
        )
        summary = result.summary
        return ReleaseSummary(
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
    tag_name: str | None,
    release_name: str | None,
    body: str | None,
    html_url: str | None,
) -> str:
    lines: list[str] = []
    if tag_name:
        lines.append(f"Tag: {tag_name}")
    if release_name:
        lines.append(f"Name: {release_name}")
    if html_url:
        lines.append(f"URL: {html_url}")
    if body:
        truncated = body[:MAX_BODY_CHARS]
        lines.append("Notes:")
        lines.append(truncated)
        if len(body) > MAX_BODY_CHARS:
            lines.append("[…release notes truncated]")
    else:
        lines.append("Notes: (release body is empty)")
    return "\n".join(lines)
