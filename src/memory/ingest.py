"""Turn inputs into the archive: recordings -> full-conversation items, then one summary per day.
Audio is input only; it is never stored."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
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


# ---------- level 3: items ----------

def find_by_hash(root: Path, digest: str) -> Path | None:
    for p in archive.iter_items(root):
        if f"sha256: {digest}" in p.read_text("utf-8"):
            return p
    return None


def ingest_audio(root: Path, src: Path, transcriber: Transcriber, info: AudioInfo | None = None,
                 lang: str = i18n.DEFAULT, force: bool = False) -> Path | None:
    """Transcribe one recording into its day's full-conversation item.
    Returns the item, or None if it was already ingested (unless `force`, which redoes it in place)."""
    digest = sha256(src)
    existing = find_by_hash(root, digest)
    if existing and not force:
        return None
    info = info or probe(src)
    item = existing or archive.recording_path(root, info.recorded)
    meta = {
        "date": info.recorded.isoformat(),
        "type": "audio",
        "source": src.name,
        "duration": clock(info.duration) if info.duration else None,
        "sha256": digest,
    }
    transcript = render_transcript(transcriber.transcribe(src))
    up = f"[{i18n.labels(lang)['summary']}]({archive.SUMMARY})"
    archive.write_entry(item, meta, f"{up}\n\n{transcript}\n")
    return item


def read_transcript(item: Path) -> str:
    """A recording's conversation, without the link up to the day summary."""
    return archive.read_entry(item)[1].split("\n\n", 1)[1].strip()


def add_note(root: Path, text: str, when: datetime, title: str = "", tags: list[str] | None = None) -> Path:
    title = title or text.strip().splitlines()[0][:20]
    item = archive.note_path(root, when, title)
    meta = {"date": when.isoformat(), "type": "note", "title": title, "tags": tags or []}
    archive.write_entry(item, meta, text.strip() + "\n")
    return item


# ---------- level 2: day summary ----------

def _items(root: Path, day: date) -> list[tuple[Path, dict, datetime]]:
    out = []
    for p in archive.iter_items(root, day):
        meta, _ = archive.read_entry(p)
        out.append((p, meta, datetime.fromisoformat(str(meta["date"]))))
    return sorted(out, key=lambda x: x[2])


def _label(meta: dict, when: datetime, t: dict) -> str:
    if meta.get("type") == "audio":
        return f"{when:%H:%M} {t['recording']}" + (f" · {meta['duration']}" if meta.get("duration") else "")
    return f"{when:%H:%M} {t['note']} · {meta.get('title', '')}"


def day_material(root: Path, day: date, lang: str = i18n.DEFAULT) -> str:
    """Everything recorded that day, in time order, as the summarizer's input."""
    t = i18n.labels(lang)
    parts = []
    for p, meta, when in _items(root, day):
        text = read_transcript(p) if meta.get("type") == "audio" else archive.read_entry(p)[1].strip()
        parts.append(f"### {_label(meta, when, t)}\n{text}")
    return "\n\n".join(parts)


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


def summarize_day(root: Path, day: date, summarizer: Summarizer | None, context: str = "",
                  lang: str = i18n.DEFAULT) -> Path:
    """(Re)write the day's summary.md from all its items; without a summarizer it only lists them."""
    t = i18n.labels(lang)
    items = _items(root, day)
    s = summarizer.summarize(day_material(root, day, lang), context) if summarizer and items else {}
    meta = {"date": day.isoformat(), "title": s.get("title") or day.isoformat(),
            "tags": s.get("tags", []), "people": s.get("people", [])}
    records = "\n".join(f"- [{_label(m, w, t)}]({p.name})" for p, m, w in items)
    path = archive.summary_path(root, day)
    archive.write_entry(path, meta, render_summary(s, lang) + f"## {t['records']}\n{records}\n")
    return path


# ---------- learning: profile.md ----------

def read_text(path: Path) -> str:
    return path.read_text("utf-8") if path.is_file() else ""


def background(root: Path, extra: str = "") -> str:
    """Summarizer context: the user's facts, then the approved learned knowledge, then any one-off extra.
    Unreviewed proposals are never used."""
    parts = (read_text(archive.profile_path(root)), read_text(archive.learned_path(root)), extra)
    return "\n\n".join(x.strip() for x in parts if x.strip())


# ---------- level 1: index ----------

def gist(body: str) -> str:
    """First sentence of a day summary."""
    headings = "|".join(re.escape(t["summary"]) for t in i18n.LABELS.values())
    m = re.search(rf"## (?:{headings})\n(.+?)\n", body)
    return re.split(r"(?<=[。！？])|(?<=[.!?])\s", m.group(1), maxsplit=1)[0].strip() if m else ""


def build_index(root: Path, person: str) -> Path:
    """The person's own notes (Markdown at the person root), then one line per day, newest month first."""
    index = archive.index_path(root)
    skip = {index, archive.pending_path(root)}
    notes = [f"- [{p.stem}]({p.name})" for p in sorted(root.glob("*.md")) if p not in skip]
    months: dict[str, list[str]] = {}
    for day in reversed(archive.iter_days(root)):
        path = archive.summary_path(root, day)
        if not path.is_file():
            continue
        meta, body = archive.read_entry(path)
        tags = " ".join(f"#{t}" for t in meta.get("tags") or [])
        line = f"- {day:%m-%d} [{meta.get('title') or day}]({path.relative_to(root).as_posix()}) {tags}".rstrip()
        if g := gist(body):
            line += f" — {g}"
        months.setdefault(f"{day:%Y-%m}", []).append(line)
    head = [f"# {person}\n"] + (["\n".join(notes) + "\n"] if notes else [])
    archive.atomic_write(index, "\n".join(head + [f"## {m}\n" + "\n".join(v) + "\n" for m, v in months.items()]))
    return index
