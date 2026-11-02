"""Archive layout of one person, in progressive-disclosure levels:

    <person>/index.md                     level 1: one line per day, grouped by month
    <person>/profile.md                   facts written by the user (never written by the tool)
    <person>/learned.md                   what the tool learned, as approved by the user
    <person>/learned.pending.md           proposed update to learned.md, awaiting review
    <person>/yyyy/mm/dd/summary.md        level 2: the day's summary, disputes, next steps; links to its items
    <person>/yyyy/mm/dd/HHMM.md           level 3: one recording's full conversation (+ its metadata)
    <person>/yyyy/mm/dd/HHMM-<slug>.md    level 3: a written note

Only Markdown is stored; recordings never enter the archive.
"""
from __future__ import annotations

import os
import re
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import yaml

SUMMARY = "summary.md"
DAY_GLOB = "[0-9][0-9][0-9][0-9]/[0-9][0-9]/[0-9][0-9]"


def day_dir(root: Path, when: date | datetime) -> Path:
    return root / f"{when:%Y}" / f"{when:%m}" / f"{when:%d}"


def summary_path(root: Path, day: date) -> Path:
    return day_dir(root, day) / SUMMARY


def index_path(root: Path) -> Path:
    return root / "index.md"


def profile_path(root: Path) -> Path:
    """Facts written by the user. Authoritative; the tool never writes it."""
    return root / "profile.md"


def learned_path(root: Path) -> Path:
    """What the tool learned from the records, day by day. Machine-maintained; yields to profile.md."""
    return root / "learned.md"


def pending_path(root: Path) -> Path:
    """Proposed next learned.md, waiting for the user's review."""
    return root / "learned.pending.md"


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^\w]+", "-", text.strip().lower()).strip("-_")
    return slug[:max_len].rstrip("-") or "note"


def _free(path: Path) -> Path:
    n, cand = 2, path
    while cand.exists():
        cand = path.with_name(f"{path.stem}-{n}.md")
        n += 1
    return cand


def recording_path(root: Path, when: datetime) -> Path:
    return _free(day_dir(root, when) / f"{when:%H%M}.md")


def note_path(root: Path, when: datetime, title: str) -> Path:
    return _free(day_dir(root, when) / f"{when:%H%M}-{slugify(title)}.md")


def atomic_write(path: Path, text: str) -> None:
    """Write via temp file + rename so a sync client never sees a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, "utf-8", newline="\n")
    os.replace(tmp, path)


def write_entry(path: Path, meta: dict, body: str) -> None:
    head = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    atomic_write(path, f"---\n{head}\n---\n\n{body}")


def read_entry(path: Path) -> tuple[dict, str]:
    text = path.read_text("utf-8")
    m = re.match(r"---\n(.*?)\n---\n\n?", text, re.DOTALL)
    if not m:
        return {}, text
    return yaml.safe_load(m.group(1)) or {}, text[m.end():]


def iter_items(root: Path, day: date | None = None) -> Iterator[Path]:
    """Recordings and notes (not day summaries), oldest first."""
    pattern = f"{day:%Y/%m/%d}/*.md" if day else f"{DAY_GLOB}/*.md"
    for p in sorted(root.glob(pattern)):
        if p.name != SUMMARY:
            yield p


def iter_days(root: Path) -> list[date]:
    """Days that have at least one item."""
    return sorted({date(int(p.parts[-4]), int(p.parts[-3]), int(p.parts[-2])) for p in iter_items(root)})
