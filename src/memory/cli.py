"""memory: dated Markdown archive of one person's memories."""
from __future__ import annotations

import platform
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import typer

from . import archive, config, i18n, ingest, learn

app = typer.Typer(no_args_is_help=True, add_completion=False)
RootOpt = Annotated[Path | None, typer.Option("--root", help="Data root; overrides MEMORY_ROOT and config.")]
PersonOpt = Annotated[str | None, typer.Option("--person", "-p", help="Person folder under the root; default from config.")]


def _data_root(root: Path | None) -> Path:
    try:
        return config.resolve_root(root)
    except config.RootNotFound as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)


def _root(root: Path | None, person: str | None) -> Path:
    """The person's archive: <data root>/<person>."""
    person = person or config.load().get("person")
    if not person:
        raise typer.BadParameter("no person: pass --person or set `person` in config (memory init --person)")
    return _data_root(root) / person


@app.command()
def init(root: Annotated[Path, typer.Option("--root", prompt="Data root path")],
         person: Annotated[str | None, typer.Option("--person", "-p", help="Default person")] = None,
         source: Annotated[list[Path] | None, typer.Option(help="Recording folder for --person (repeatable)")] = None,
         lang: Annotated[str | None, typer.Option(help="Archive language: en | zh")] = None):
    """Write data root, default person, its recording sources and language into config.toml."""
    root = root.expanduser().resolve()
    data: dict = {"root": str(root)}
    if lang:
        i18n.labels(lang)
        data["lang"] = lang
    if person:
        (root / person).mkdir(parents=True, exist_ok=True)
        data["person"] = person
        if source:
            data["sources"] = {person: [str(s.expanduser().resolve()) for s in source]}
    typer.echo(f"config: {config.save(data)}")


def _summarize_days(r: Path, days: set[date], model: str | None, context: str | None) -> None:
    """Oldest day first: summarize it with the current profile, then learn from it; finally the index."""
    from . import summarize

    s = config.load()
    summarizer = summarize.create(model or s["summarize"]["model"], s["lang"])
    for d in sorted(days):
        typer.echo(f"= {d}")
        typer.echo(f"  {ingest.summarize_day(r, d, summarizer, ingest.background(r, context or ''), s['lang'])}")
        if summarizer:
            from ai_lab import ProviderError
            try:
                typer.echo(f"  {learn.learn_day(r, d, summarizer, s['lang'])}")
            except ProviderError as e:  # one bad answer must not stop the run
                typer.echo(f"  nothing learned from {d}: {e}", err=True)
    ingest.build_index(r, r.name)
    if learn.pending(r):
        typer.echo("learned knowledge has a proposed update: run `memory review`")


ModelOpt = Annotated[str | None, typer.Option(help="ai-lab spec or 'none'; overrides config")]
ContextOpt = Annotated[str | None, typer.Option(help="One-off extra background, added to <person>/profile.md")]


@app.command()
def add(text: str, root: RootOpt = None, person: PersonOpt = None,
        when: Annotated[datetime | None, typer.Option("--date")] = None,
        title: str = "", tag: Annotated[list[str] | None, typer.Option("--tag")] = None,
        model: ModelOpt = None, context: ContextOpt = None):
    """Record a text note and refresh that day's summary."""
    r = _root(root, person)
    when = (when or datetime.now()).astimezone()
    typer.echo(ingest.add_note(r, text, when, title, tag))
    _summarize_days(r, {when.date()}, model, context)


def _audio_files(paths: list[Path]) -> list[Path]:
    out = []
    for p in paths:
        items = sorted(p.rglob("*")) if p.is_dir() else [p]
        out += [f for f in items if f.is_file() and f.suffix.lower() in ingest.AUDIO_EXT]
    return out


@app.command(name="ingest")
def ingest_cmd(paths: Annotated[list[Path] | None, typer.Argument(help="Files/dirs; default: config sources of the person")] = None,
               root: RootOpt = None, person: PersonOpt = None, context: ContextOpt = None, model: ModelOpt = None,
               delete: Annotated[bool, typer.Option(help="Delete each audio file after it is archived")] = False,
               force: Annotated[bool, typer.Option(help="Re-transcribe already-ingested recordings in place")] = False):
    """Transcribe recordings locally (faster-whisper), then summarize each affected day (ai-lab)."""
    from . import transcribe

    r = _root(root, person)
    s = config.load()
    paths = paths or [Path(p) for p in s.get("sources", {}).get(r.name, [])]
    if not paths:
        raise typer.BadParameter(f"no paths and no sources configured for {r.name}")
    files = _audio_files(paths)
    if not files:
        typer.echo("no audio files")
        return
    transcriber = transcribe.create(s["transcribe"])
    days: set[date] = set()
    for f in files:
        item = ingest.ingest_audio(r, f, transcriber, lang=s["lang"], force=force)
        typer.echo(f"> {f.name}: {item or 'already archived'}")
        if item:
            days.add(date.fromisoformat(item.parts[-4] + "-" + item.parts[-3] + "-" + item.parts[-2]))
        if delete:
            f.unlink()
    if days:
        _summarize_days(r, days, model, context)


@app.command(name="summarize")
def summarize_cmd(days: Annotated[list[str] | None, typer.Argument(help="YYYY-MM-DD; default: every day")] = None,
                  root: RootOpt = None, person: PersonOpt = None, model: ModelOpt = None, context: ContextOpt = None):
    """Rewrite day summaries from the stored transcripts and notes."""
    r = _root(root, person)
    _summarize_days(r, {date.fromisoformat(d) for d in days} if days else set(archive.iter_days(r)), model, context)


@app.command()
def review(root: RootOpt = None, person: PersonOpt = None,
           accept: Annotated[bool, typer.Option("--accept", help="Apply the proposal (edit it first if needed)")] = False,
           reject: Annotated[bool, typer.Option("--reject", help="Discard the proposal")] = False):
    """Review the proposed update to learned.md: show the diff, then --accept or --reject."""
    r = _root(root, person)
    if accept and reject:
        raise typer.BadParameter("choose one of --accept / --reject")
    if not learn.pending(r):
        typer.echo("nothing to review")
        return
    if accept:
        typer.echo(f"accepted: {learn.accept(r)}")
    elif reject:
        learn.reject(r)
        typer.echo("rejected")
    else:
        typer.echo(learn.diff(r) or "proposal is identical to learned.md")
        typer.echo(f"\nedit {archive.pending_path(r)} if needed, then `memory review --accept` or `--reject`")


@app.command()
def index(root: RootOpt = None, person: PersonOpt = None):
    """Rebuild the person's index.md."""
    r = _root(root, person)
    typer.echo(ingest.build_index(r, r.name))


@app.command()
def search(query: str, root: RootOpt = None, person: PersonOpt = None):
    """Case-insensitive full-text search across a person's archive."""
    r, q = _root(root, person), query.lower()
    for p in sorted(r.rglob("*.md")):
        for line in p.read_text("utf-8").splitlines():
            if q in line.lower():
                typer.echo(f"{p.relative_to(r).as_posix()}: {line.strip()}")




@app.command()
def doctor(root: RootOpt = None):
    """Check data root, ffprobe, CUDA, summarizer and sync-conflict copies."""
    r = _data_root(root)
    typer.echo(f"people: {', '.join(sorted(p.name for p in r.iterdir() if p.is_dir())) if r.is_dir() else '-'}")
    typer.echo(f"root: {r} ({'ok' if r.is_dir() else 'MISSING'})")
    typer.echo(f"config: {config.config_file()}")
    typer.echo(f"ffprobe: {shutil.which('ffprobe') or 'missing (recording time falls back to file mtime)'}")
    from .transcribe.whisper_local import _cuda_available
    typer.echo(f"cuda: {_cuda_available()}")
    s = config.load()
    typer.echo(f"transcribe: {s['transcribe']['model']}  summarize: {s['summarize']['model']}")
    host = platform.node().split(".")[0].lower()
    for p in r.rglob("*.md"):
        if p.stem.lower().endswith(f"-{host}"):
            typer.echo(f"conflict copy: {p}")


if __name__ == "__main__":
    app()
