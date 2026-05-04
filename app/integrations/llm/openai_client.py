import json
from typing import Protocol

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.integrations.llm.prompt_loader import PromptTemplate, PromptVariables
from app.integrations.llm.schemas import GitHubUpdateSummary


class SummaryRequest(BaseModel):
    prompt: PromptTemplate
    repo_full_name: str
    update_type: str
    source: str
    language: str
    style: str
    summary_preferences: str
    update_payload: str


class SummaryResult(BaseModel):
    summary: GitHubUpdateSummary
    input_tokens: int | None = None
    output_tokens: int | None = None


class ResponsesClient(Protocol):
    async def create(self, **kwargs): ...


class OpenAIClientProtocol(Protocol):
    responses: ResponsesClient


class OpenAILLMClient:
    def __init__(self, openai_client: OpenAIClientProtocol | None = None) -> None:
        self._client = openai_client or AsyncOpenAI()

    async def summarize_update(self, request: SummaryRequest) -> SummaryResult:
        prompt = request.prompt
        rendered_user = prompt.render_user(
            PromptVariables(
                repo_full_name=request.repo_full_name,
                update_type=request.update_type,
                source=request.source,
                language=request.language,
                style=request.style,
                summary_preferences=request.summary_preferences,
                update_payload=request.update_payload,
            )
        )

        response = await self._client.responses.create(
            model=prompt.model,
            reasoning={
                "effort": prompt.reasoning.effort,
                "summary": prompt.reasoning.summary,
            },
            text={
                "verbosity": prompt.text.verbosity,
                "format": {
                    "type": "json_schema",
                    "name": "github_update_summary",
                    "schema": GitHubUpdateSummary.model_json_schema(),
                    "strict": True,
                },
            },
            input=[
                {"role": "system", "content": prompt.system},
                {"role": "developer", "content": prompt.developer},
                {"role": "user", "content": rendered_user},
            ],
        )

        summary = GitHubUpdateSummary.model_validate(json.loads(response.output_text))
        usage = getattr(response, "usage", None)
        return SummaryResult(
            summary=summary,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )
