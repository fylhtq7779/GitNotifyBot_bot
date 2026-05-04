from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ReasoningConfig(BaseModel):
    effort: str
    summary: str


class TextConfig(BaseModel):
    verbosity: str


class OutputConfig(BaseModel):
    format: str
    schema_name: str = Field(alias="schema")


class PromptVariables(BaseModel):
    repo_full_name: str
    update_type: str
    source: str
    language: str
    style: str
    summary_preferences: str
    update_payload: str


class PromptTemplate(BaseModel):
    id: str
    version: str
    model: str
    reasoning: ReasoningConfig
    text: TextConfig
    output: OutputConfig
    system: str
    developer: str
    user_template: str

    def render_user(self, variables: PromptVariables) -> str:
        rendered = self.user_template
        for key, value in variables.model_dump().items():
            rendered = rendered.replace("{{ " + key + " }}", value)
        return rendered


def load_prompt_template(path: Path) -> PromptTemplate:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return PromptTemplate.model_validate(data)
