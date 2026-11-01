"""Speech-to-text engines. Each engine exposes transcribe(path) -> list[Segment]."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


class Transcriber(Protocol):
    def transcribe(self, path: Path) -> list[Segment]: ...


def drop_hallucinations(segments: list[Segment], patterns: list[str]) -> list[Segment]:
    """Remove segments matching known Whisper hallucinations (subtitle credits, 'like and subscribe', ...)."""
    regexes = [re.compile(p) for p in patterns]
    return [s for s in segments if not any(r.search(s.text) for r in regexes)]


def create(settings: dict) -> Transcriber:
    engine = settings["engine"]
    if engine == "whisper":
        from .whisper_local import WhisperLocal
        return WhisperLocal(**{k: v for k, v in settings.items() if k != "engine"})
    raise ValueError(f"Unknown transcribe engine: {engine}")
