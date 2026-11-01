"""Archive layout of one person, in progressive-disclosure levels:

    <person>/index.md                              overview: every entry, one line each
    <person>/yyyy/mm/dd/HHMM-slug.md               entry: frontmatter + summary, disputes, plans
    <person>/yyyy/mm/dd/HHMM-slug.transcript.md    full conversation

Only Markdown is stored; recordings never enter the archive.
"""
from __future__ import annotations

import os
import re
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import yaml

TRANSCRIPT_SUFFIX = ".transcript.md"


def day_dir(root: Path, when: date | datetime) -> Path:
    return root / f"{when:%Y}" / f"{when:%m}" / f"{when:%d}"


def index_path(root: Path) -> Path:
    return root / "index.md"


def transcript_path(entry: Path) -> Path:
    return entry.with_name(entry.stem + TRANSCRIPT_SUFFIX)


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^\w]+", "-", text.strip().lower()).strip("-_")
    return slug[:max_len].rstrip("-") or "note"


def entry_path(root: Path, when: datetime, title: str) -> Path:
    path = day_dir(root, when) / f"{when:%H%M}-{slugify(title)}.md"
    n, cand = 2, path
    while cand.exists() or transcript_path(cand).exists():
        cand = path.with_name(f"{path.stem}-{n}.md")
        n += 1
    return cand


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
    m = re.match(r"---\n(.*?)\n---\n\n?", text, re.S)
    if not m:
        return {}, text
    return yaml.safe_load(m.group(1)) or {}, text[m.end():]


def iter_entries(root: Path, day: date | None = None) -> Iterator[Path]:
    """Entry (summary) files, oldest first; transcripts excluded."""
    pattern = f"{day:%Y/%m/%d}/*.md" if day else "[0-9][0-9][0-9][0-9]/[0-9][0-9]/[0-9][0-9]/*.md"
    for p in sorted(root.glob(pattern)):
        if not p.name.endswith(TRANSCRIPT_SUFFIX):
            yield p
