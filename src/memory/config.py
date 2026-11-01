"""Settings live in ONE file: config.toml at the project root (git-ignored; template: config.example.toml).

Root resolution order: explicit argument > $MEMORY_ROOT > config file.
All personal settings (root, people, sources, context) live in that file, never in code.
"""
from __future__ import annotations

import copy
import os
import tomllib
from pathlib import Path

import tomli_w

PROJECT_DIR = Path(__file__).resolve().parents[2]

DEFAULTS: dict = {
    "lang": "en",                # archive interface language: en | zh
    "transcribe": {
        "engine": "whisper",
        "model": "large-v3",
        "device": "auto",        # auto | cuda | cpu
        "compute_type": "auto",  # auto | float16 | int8_float16 | int8
        "language": "",          # spoken language; empty = autodetect
        "initial_prompt": "",
        # regexes; matching segments are known Whisper hallucinations and are dropped
        "drop_patterns": [
            r"点赞.{0,6}订阅", r"订阅.{0,6}转发", r"明镜与点点", r"字幕由.*提供", r"字幕志愿者",
            r"(?i)amara\.org", r"(?i)thanks? (you )?for watching", r"(?i)please subscribe",
        ],
    },
    # ai-lab spec "<provider>:<model>[@effort]"; "none" = transcript only
    "summarize": {"model": "anthropic:claude-sonnet-5-5"},
}


class RootNotFound(RuntimeError):
    pass


def config_file() -> Path:
    return PROJECT_DIR / "config.toml"


def _read() -> dict:
    f = config_file()
    return tomllib.loads(f.read_text("utf-8")) if f.is_file() else {}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load() -> dict:
    return _merge(DEFAULTS, _read())


def save(data: dict) -> Path:
    f = config_file()
    f.write_text(tomli_w.dumps(_merge(_read(), data)), "utf-8")
    return f


def resolve_root(explicit: Path | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    if env := os.environ.get("MEMORY_ROOT"):
        return Path(env).expanduser()
    if root := _read().get("root"):
        return Path(root).expanduser()
    raise RootNotFound("Memory root not found; run `memory init --root <path>` or set MEMORY_ROOT.")
