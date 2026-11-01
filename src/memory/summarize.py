"""Summarize a transcript into structured fields through ai-lab (any provider, schema-enforced).
The schema is language-neutral; the output language comes from prompts/summarize.<lang>.md."""
from __future__ import annotations

from importlib.resources import files
from typing import Protocol

from . import i18n

_STR_LIST = {"type": "array", "items": {"type": "string"}}

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "short title naming the core of the conversation"},
        "summary": {"type": "string", "description": "faithful summary, 5-8 sentences"},
        "points": {**_STR_LIST, "description": "key events, details and quotes worth keeping"},
        "disputes": {
            "type": "array",
            "description": "key disputes, disagreements and important discussions, most important first",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "sides": {**_STR_LIST, "description": "each party's position, naming who holds it"},
                    "outcome": {"type": "string", "description": "agreement reached, or unresolved"},
                },
                "required": ["topic", "sides", "outcome"],
                "additionalProperties": False,
            },
        },
        "plans": {
            "type": "array",
            "description": "follow-up plans, agreements, promises and to-dos",
            "items": {
                "type": "object",
                "properties": {
                    "item": {"type": "string"},
                    "owner": {"type": "string", "description": "who; empty if not mentioned"},
                    "when": {"type": "string", "description": "deadline/time; empty if not mentioned"},
                },
                "required": ["item", "owner", "when"],
                "additionalProperties": False,
            },
        },
        "tags": {**_STR_LIST, "description": "3-6 topic tags"},
        "people": {**_STR_LIST, "description": "people mentioned"},
    },
    "required": ["title", "summary", "points", "disputes", "plans", "tags", "people"],
    "additionalProperties": False,
}


class Summarizer(Protocol):
    def summarize(self, transcript: str, context: str) -> dict: ...


def instructions(context: str, lang: str) -> str:
    template = files("memory").joinpath(f"prompts/summarize.{lang}.md").read_text("utf-8")
    return template.replace("{{context}}", context or i18n.labels(lang)["no_context"])


class AiLabSummarizer:
    def __init__(self, spec: str, lang: str):
        from ai_lab import connect
        self.client = connect(spec)
        self.lang = lang

    def summarize(self, transcript: str, context: str) -> dict:
        from ai_lab import ResponseRequest, Text
        request = ResponseRequest(instructions(context, self.lang), (Text(transcript),), SCHEMA, name="memory_summary")
        return self.client.respond(request).value


def create(spec: str, lang: str = i18n.DEFAULT) -> Summarizer | None:
    """`spec` is an ai-lab model spec "<provider>:<model>[@effort]", or "none"."""
    return None if spec == "none" else AiLabSummarizer(spec, lang)
