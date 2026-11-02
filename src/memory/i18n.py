"""Archive interface languages: every heading/label written into Markdown comes from here.
The matching summarizer prompt is prompts/summarize.<lang>.md."""
from __future__ import annotations

LANGS = ("en", "zh")
DEFAULT = "en"

LABELS = {
    "en": {
        "summary": "Summary",
        "disputes": "Key disputes & discussions",
        "outcome": "Outcome: ",
        "plans": "Next steps",
        "points": "Key points",
        "records": "Records",
        "recording": "Recording",
        "note": "Note",
        "no_context": "(none)",
        "open": " (", "sep": ", ", "close": ")",
    },
    "zh": {
        "summary": "摘要",
        "disputes": "关键争吵与讨论",
        "outcome": "结果：",
        "plans": "后续计划",
        "points": "要点",
        "records": "当天记录",
        "recording": "录音",
        "note": "笔记",
        "no_context": "（无）",
        "open": "（", "sep": "，", "close": "）",
    },
}


def labels(lang: str) -> dict:
    if lang not in LABELS:
        raise ValueError(f"Unsupported language {lang!r}; choose one of {LANGS}")
    return LABELS[lang]
