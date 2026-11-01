"""Local transcription with faster-whisper (CTranslate2).

Decodes any audio/video format via PyAV; VAD segmentation handles long recordings.
"""
from __future__ import annotations

from pathlib import Path

from . import Segment, drop_hallucinations


def _cuda_available() -> bool:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


class WhisperLocal:
    def __init__(self, model: str, device: str = "auto", compute_type: str = "auto",
                 language: str = "", initial_prompt: str = "", drop_patterns: list[str] = ()):
        from faster_whisper import WhisperModel

        if device == "auto":
            device = "cuda" if _cuda_available() else "cpu"
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"
        self.model = WhisperModel(model, device=device, compute_type=compute_type)
        self.language = language or None
        self.initial_prompt = initial_prompt or None
        self.drop_patterns = list(drop_patterns)

    def transcribe(self, path: Path) -> list[Segment]:
        # condition_on_previous_text=False stops one hallucinated line from repeating for minutes
        segments, _ = self.model.transcribe(
            str(path), language=self.language, initial_prompt=self.initial_prompt,
            vad_filter=True, beam_size=5, condition_on_previous_text=False,
        )
        kept = [Segment(s.start, s.end, s.text.strip()) for s in segments if s.text.strip()]
        return drop_hallucinations(kept, self.drop_patterns)
