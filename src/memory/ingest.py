"""Turn inputs (audio, text) into archived Markdown entries. Audio is input only; it is never stored."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import archive, i18n
from .summarize import Summarizer
from .transcribe import Segment, Transcriber

AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".opus", ".amr", ".wma", ".webm", ".mp4", ".mov"}


@dataclass(frozen=True)
class AudioInfo:
    recorded: datetime
    duration: float | None


NAME_TIME = re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})[-_ T]?(\d{2})(\d{2})(\d{2})?(?!\d)")


def time_from_name(name: str) -> datetime | None:
    """Start time embedded by recorders/WeChat, e.g. ...-202611011228.m4a or 20261101_093015.mp3."""
    m = NAME_TIME.search(name)
    if not m:
        return None
    try:
        return datetime(*(int(g) for g in m.groups() if g is not None))
    except ValueError:
        return None


def probe(path: Path) -> AudioInfo:
    """Recording start: time in the file name, else container creation_time (ffprobe), else mtime; local tz."""
    created, duration = None, None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
            capture_output=True, text=True, check=True, encoding="utf-8",
        ).stdout
        fmt = json.loads(out).get("format", {})
        duration = float(fmt["duration"]) if fmt.get("duration") else None
        tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
        if raw := tags.get("creation_time") or tags.get("date"):
            created = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError):
        pass
    created = time_from_name(path.name) or created
    if created is None:
        created = datetime.fromtimestamp(path.stat().st_mtime)
    return AudioInfo(created.astimezone().replace(microsecond=0), duration)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def stamp(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def render_transcript(segments: list[Segment]) -> str:
    return "\n".join(f"[{stamp(s.start)}] {s.text}" for s in segments)


def render_summary(s: dict, lang: str) -> str:
    t = i18n.labels(lang)
    parts = []
    if s.get("summary"):
        parts.append(f"## {t['summary']}\n{s['summary']}\n")
    if s.get("disputes"):
        blocks = [
            f"### {d['topic']}\n" + "".join(f"- {side}\n" for side in d.get("sides", []))
            + (f"- {t['outcome']}{d['outcome']}\n" if d.get("outcome") else "")
            for d in s["disputes"]
        ]
        parts.append(f"## {t['disputes']}\n" + "\n".join(blocks))
    if s.get("plans"):
        def plan(p: dict) -> str:
            extra = t["sep"].join(x for x in (p.get("owner"), p.get("when")) if x)
            return f"- [ ] {p['item']}" + (f"{t['open']}{extra}{t['close']}" if extra else "")
        parts.append(f"## {t['plans']}\n" + "\n".join(plan(p) for p in s["plans"]) + "\n")
    if s.get("points"):
        parts.append(f"## {t['points']}\n" + "\n".join(f"- {p}" for p in s["points"]) + "\n")
    return "\n".join(parts) + ("\n" if parts else "")


def find_by_hash(root: Path, digest: str) -> Path | None:
    for p in archive.iter_entries(root):
        if f"sha256: {digest}" in p.read_text("utf-8"):
            return p
    return None


def write_audio_entry(entry: Path, meta: dict, summary: dict, lang: str) -> None:
    """Entry = summary level; links down to the full conversation."""
    t = i18n.labels(lang)
    link = f"## {t['transcript']}\n[{t['transcript']}]({archive.transcript_path(entry).name})\n"
    archive.write_entry(entry, meta, render_summary(summary, lang) + link)


def write_transcript(entry: Path, title: str, transcript: str, lang: str) -> None:
    t = i18n.labels(lang)
    text = f"# {title} · {t['transcript']}\n\n[{t['summary']}]({entry.name})\n\n{transcript}\n"
    archive.atomic_write(archive.transcript_path(entry), text)


def read_transcript(entry: Path) -> str:
    return archive.transcript_path(entry).read_text("utf-8").split("\n\n", 2)[2].strip()


def ingest_audio(root: Path, src: Path, transcriber: Transcriber, summarizer: Summarizer | None,
                 context: str = "", info: AudioInfo | None = None, lang: str = i18n.DEFAULT,
                 force: bool = False) -> Path:
    """Transcribe + summarize one recording into an entry and its transcript; the audio itself is not stored.
    An already-ingested recording returns its entry, or with `force` is redone (renamed if its title changed)."""
    digest = sha256(src)
    existing = find_by_hash(root, digest)
    if existing and not force:
        return existing
    info = info or probe(src)
    transcript = render_transcript(transcriber.transcribe(src))
    summary = summarizer.summarize(transcript, context) if summarizer and transcript else {}
    title = summary.get("title") or src.stem

    entry = archive.retitled_path(existing, title) if existing else archive.entry_path(root, info.recorded, title)
    meta = {
        "date": info.recorded.isoformat(),
        "type": "audio",
        "title": title,
        "source": src.name,
        "duration": clock(info.duration) if info.duration else None,
        "sha256": digest,
        "tags": summary.get("tags", []),
        "people": summary.get("people", []),
    }
    write_transcript(entry, title, transcript, lang)
    write_audio_entry(entry, meta, summary, lang)
    if existing and existing != entry:
        archive.remove_entry(existing)
    return entry


def resummarize(entry: Path, summarizer: Summarizer, context: str = "", lang: str = i18n.DEFAULT) -> Path:
    """Regenerate the summary level (and transcript header) from the stored transcript.
    Returns the entry path, which follows the new title."""
    meta, _ = archive.read_entry(entry)
    transcript = read_transcript(entry)
    s = summarizer.summarize(transcript, context)
    meta.update(title=s.get("title") or meta.get("title"), tags=s.get("tags", []), people=s.get("people", []))
    target = archive.retitled_path(entry, meta["title"])
    write_transcript(target, meta["title"], transcript, lang)
    write_audio_entry(target, meta, s, lang)
    if target != entry:
        archive.remove_entry(entry)
    return target


def add_note(root: Path, text: str, when: datetime, title: str = "", tags: list[str] | None = None) -> Path:
    title = title or text.strip().splitlines()[0][:20]
    entry = archive.entry_path(root, when, title)
    meta = {"date": when.isoformat(), "type": "note", "title": title, "tags": tags or [], "people": []}
    archive.write_entry(entry, meta, text.strip() + "\n")
    return entry


def gist(body: str, title: str) -> str:
    """First sentence of the summary (or of a note), unless it just repeats the title."""
    headings = "|".join(re.escape(t["summary"]) for t in i18n.LABELS.values())
    m = re.search(rf"## (?:{headings})\n(.+?)\n", body)
    if m:
        text = m.group(1)
    else:
        lines = body.strip().splitlines()
        text = lines[0] if lines and not lines[0].startswith("#") else ""
    first = re.split(r"(?<=[。！？])|(?<=[.!?])\s", text, maxsplit=1)[0].strip()
    return "" if first == title else first


def build_index(root: Path, person: str) -> Path:
    """Top level: the person's own notes (Markdown at the person root), then entries, newest day first."""
    index = archive.index_path(root)
    notes = [f"- [{p.stem}]({p.name})" for p in sorted(root.glob("*.md")) if p != index]
    by_day: dict[str, list[str]] = {}
    for p in archive.iter_entries(root):
        meta, body = archive.read_entry(p)
        when = datetime.fromisoformat(str(meta["date"]))
        title = meta.get("title") or p.stem
        tags = " ".join(f"#{t}" for t in meta.get("tags") or [])
        line = f"- {when:%H:%M} [{title}]({p.relative_to(root).as_posix()}) {tags}".rstrip()
        if g := gist(body, title):
            line += f" — {g}"
        by_day.setdefault(f"{when:%Y-%m-%d}", []).append(line)
    days = [f"## {d}\n" + "\n".join(by_day[d]) + "\n" for d in sorted(by_day, reverse=True)]
    head = [f"# {person}\n"] + (["\n".join(notes) + "\n"] if notes else [])
    archive.atomic_write(index, "\n".join(head + days))
    return index
