# memory

Curate everything you remember about a person as a dated Markdown archive. Recordings are input only:
they are transcribed locally with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and summarized
through [ai-lab](https://github.com/DawnEver/ai-lab) (any provider, schema-enforced). **The archive never
stores audio**, only `.md`.

Code and data are separate. This repository is the tool; the data root (any synced folder), the people,
their recording sources and background all live in `config.toml` at the project root, which is git-ignored.

## Archive layout (progressive disclosure)

```
<root>/<Person>/
├── index.md              # level 1: one line per day, newest month first
├── profile.md            # facts you write; the tool only reads it
├── learned.md            # what the tool learned, as approved by you
├── learned.pending.md    # proposed update to learned.md, awaiting `memory review`
└── yyyy/mm/dd/
    ├── summary.md        # level 2: the day as a whole: summary, key disputes, next steps, key points, records
    ├── HHMM.md           # level 3: one recording's full conversation (source, duration, sha256 in frontmatter)
    └── HHMM-<title>.md   # level 3: a written note
```

One summary per day, written from all of that day's recordings and notes. Each level links only to
the next; nothing is repeated across levels. Headings are English by default, or Chinese with `lang = "zh"`.

**Learning, under review.** Days are processed oldest first. Each day is summarized with `profile.md`
and `learned.md` as background, then the model proposes what the day adds (new people, places,
ongoing threads, cues for telling speakers apart) as `learned.pending.md`; proposals from several days
accumulate. Nothing takes effect until you review it: `memory review` shows the diff, you may edit the
proposal, then `--accept` or `--reject`. Run `memory summarize` afterwards to rewrite the days with
the new knowledge. Seed `profile.md` with who the speakers are before the first `ingest`.

## Setup

```sh
uv sync
uv run memory init --root <data root> --person <Person> --source <recordings dir> [--lang zh]
uv run memory doctor
```

All settings are documented in [`config.example.toml`](config.example.toml). The data root resolves as
`--root` > `$MEMORY_ROOT` > `config.toml`. API keys stay in ai-lab's key store, never in config or data.

## Usage

```sh
memory ingest [paths...] [-p <Person>] [--force] [--delete]  # transcribe new recordings, re-summarize their days
memory add "first met at the station" --tag memories          # add a note, re-summarize its day
memory summarize [YYYY-MM-DD...] [--model deepseek:...]       # rewrite day summaries (default: every day)
memory review [--accept | --reject]                           # review proposed learned knowledge
memory index                                                  # rebuild index.md
memory search <text>
```

`--model none` transcribes only; the day summary then just lists the records.

- Recording start time: a timestamp in the file name (`...-202611011228.m4a`, `20261101_093015.mp3`),
  else the container's `creation_time`, else the file's mtime.
- Audio is deduplicated by sha256, so re-running `ingest` on the same sources only adds new recordings.
- The summary prompt is `src/memory/prompts/summarize.<lang>.md`; its structure is `SCHEMA` in
  `src/memory/summarize.py`.

## Development

```sh
uv run pytest
```
