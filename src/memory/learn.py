"""Continuous learning under user review.

Each processed day yields a *proposal* for the next learned.md (learned.pending.md); proposals from
several days accumulate. Nothing reaches learned.md, and so no summary uses it, until the user
accepts it (optionally after editing the proposal). profile.md is the user's and is only ever read.
"""
from __future__ import annotations

import difflib
from datetime import date
from pathlib import Path

from . import archive, i18n
from .ingest import day_material, read_text
from .summarize import Summarizer


def pending(root: Path) -> tuple[str, list[str]] | None:
    """(proposed learned.md, days it covers), or None when nothing awaits review."""
    p = archive.pending_path(root)
    if not p.is_file():
        return None
    meta, body = archive.read_entry(p)
    return body, list(meta.get("days", []))


def learn_day(root: Path, day: date, learner: Summarizer, lang: str = i18n.DEFAULT) -> Path:
    """Propose what this day adds, building on the pending proposal if there is one."""
    current = pending(root)
    base, days = current if current else (read_text(archive.learned_path(root)), [])
    facts = read_text(archive.profile_path(root))
    proposal = learner.learn(facts, base, day_material(root, day, lang), day.isoformat())
    path = archive.pending_path(root)
    archive.write_entry(path, {"days": sorted({*days, day.isoformat()})}, proposal)
    return path


def diff(root: Path) -> str:
    """Unified diff from the approved learned.md to the proposal; empty when nothing is pending."""
    current = pending(root)
    if current is None:
        return ""
    old = read_text(archive.learned_path(root))
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True), current[0].splitlines(keepends=True),
        "learned.md", f"learned.pending.md ({', '.join(current[1])})",
    ))


def accept(root: Path) -> Path:
    current = pending(root)
    if current is None:
        raise ValueError("nothing to review")
    path = archive.learned_path(root)
    archive.atomic_write(path, current[0])
    archive.pending_path(root).unlink()
    return path


def reject(root: Path) -> None:
    archive.pending_path(root).unlink(missing_ok=True)
