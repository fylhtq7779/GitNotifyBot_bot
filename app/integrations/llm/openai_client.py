import json
from typing import Any, Protocol

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
    def __init__(
        self,
        openai_client: OpenAIClientProtocol | None = None,
        *,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        if openai_client is not None:
            self._client = openai_client
        else:
            kwargs: dict[str, object] = {}
            if api_key is not None:
                kwargs["api_key"] = api_key
            if timeout_seconds is not None:
                kwargs["timeout"] = timeout_seconds
            self._client = AsyncOpenAI(**kwargs)

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
                    "schema": _to_strict_schema(GitHubUpdateSummary.model_json_schema()),
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


def _to_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Adapt a Pydantic-generated JSON schema for OpenAI strict mode.

    Strict requires additionalProperties=false on every object and every
    property listed in required[]. Recurse through nested objects/arrays.
    """
    if not isinstance(schema, dict):
        return schema
    schema_copy: dict[str, Any] = dict(schema)
    if schema_copy.get("type") == "object":
        properties = schema_copy.get("properties")
        if isinstance(properties, dict):
            schema_copy["properties"] = {
                key: _to_strict_schema(value) for key, value in properties.items()
            }
            schema_copy["required"] = list(properties.keys())
        schema_copy["additionalProperties"] = False
    items = schema_copy.get("items")
    if isinstance(items, dict):
        schema_copy["items"] = _to_strict_schema(items)
    defs = schema_copy.get("$defs")
    if isinstance(defs, dict):
        schema_copy["$defs"] = {
            key: _to_strict_schema(value) for key, value in defs.items()
        }
    return schema_copy
