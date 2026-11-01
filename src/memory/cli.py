"""memory: dated Markdown archive of one person's memories."""
from __future__ import annotations

import platform
import shutil
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer

from . import archive, config, i18n, ingest

app = typer.Typer(no_args_is_help=True, add_completion=False)
RootOpt = Annotated[Optional[Path], typer.Option("--root", help="Data root; overrides MEMORY_ROOT and config.")]
PersonOpt = Annotated[Optional[str], typer.Option("--person", "-p", help="Person folder under the root; default from config.")]


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


def _context(person_root: Path, given: str | None) -> str:
    """Explicit --context, else the person's configured background."""
    return given if given is not None else config.load().get("context", {}).get(person_root.name, "")


@app.command()
def init(root: Annotated[Path, typer.Option("--root", prompt="Data root path")],
         person: Annotated[Optional[str], typer.Option("--person", "-p", help="Default person")] = None,
         source: Annotated[Optional[list[Path]], typer.Option(help="Recording folder for --person (repeatable)")] = None,
         lang: Annotated[Optional[str], typer.Option(help="Archive language: en | zh")] = None):
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


@app.command()
def add(text: str, root: RootOpt = None, person: PersonOpt = None,
        when: Annotated[Optional[datetime], typer.Option("--date")] = None,
        title: str = "", tag: Annotated[Optional[list[str]], typer.Option("--tag")] = None):
    """Record a text note."""
    r = _root(root, person)
    when = (when or datetime.now()).astimezone()
    e = ingest.add_note(r, text, when, title, tag)
    ingest.build_index(r, r.name)
    typer.echo(e)


def _audio_files(paths: list[Path]) -> list[Path]:
    out = []
    for p in paths:
        items = sorted(p.rglob("*")) if p.is_dir() else [p]
        out += [f for f in items if f.is_file() and f.suffix.lower() in ingest.AUDIO_EXT]
    return out


@app.command(name="ingest")
def ingest_cmd(paths: Annotated[Optional[list[Path]], typer.Argument(help="Files/dirs; default: config sources of the person")] = None,
               root: RootOpt = None, person: PersonOpt = None,
               context: Annotated[Optional[str], typer.Option(help="Background; default config [context].<person>")] = None,
               model: Annotated[Optional[str], typer.Option(help="ai-lab spec or 'none'; overrides config")] = None,
               delete: Annotated[bool, typer.Option(help="Delete each audio file after it is archived")] = False,
               force: Annotated[bool, typer.Option(help="Redo already-ingested recordings in place")] = False):
    """Transcribe (local faster-whisper) and summarize (ai-lab) recordings into Markdown entries."""
    from . import summarize, transcribe

    r = _root(root, person)
    s = config.load()
    paths = paths or [Path(p) for p in s.get("sources", {}).get(r.name, [])]
    if not paths:
        raise typer.BadParameter(f"no paths and no sources configured for {r.name}")
    files = _audio_files(paths)
    if not files:
        typer.echo("no audio files")
        return
    lang = s["lang"]
    transcriber = transcribe.create(s["transcribe"])
    summarizer = summarize.create(model or s["summarize"]["model"], lang)
    for f in files:
        typer.echo(f"> {f.name}")
        e = ingest.ingest_audio(r, f, transcriber, summarizer, _context(r, context), lang=lang, force=force)
        ingest.build_index(r, r.name)
        typer.echo(f"  {e}")
        if delete:
            f.unlink()


@app.command()
def resummarize(entries: list[Path], context: Optional[str] = None, model: Optional[str] = None):
    """Regenerate summary/tags from an entry's stored transcript."""
    from . import summarize

    s = config.load()
    summarizer = summarize.create(model or s["summarize"]["model"], s["lang"])
    if summarizer is None:
        raise typer.BadParameter("summarizer is 'none'")
    for e in entries:
        if not archive.transcript_path(e).is_file():
            typer.echo(f"skip (no transcript): {e}")
            continue
        person_root = e.resolve().parents[3]  # <person>/yyyy/mm/dd/entry.md
        ingest.resummarize(e, summarizer, _context(person_root, context), s["lang"])
        ingest.build_index(person_root, person_root.name)
        typer.echo(e)


@app.command()
def index(root: RootOpt = None, person: PersonOpt = None):
    """Rebuild the person's index.md."""
    r = _root(root, person)
    typer.echo(ingest.build_index(r, r.name))


@app.command()
def search(query: str, root: RootOpt = None, person: PersonOpt = None):
    """Case-insensitive full-text search across a person's entries."""
    r, q = _root(root, person), query.lower()
    for p in archive.iter_entries(r):
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
