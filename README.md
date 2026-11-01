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
├── index.md                          # level 1: every entry, newest day first, one line each
└── yyyy/mm/dd/
    ├── HHMM-<title>.md               # level 2: metadata + summary, key disputes, next steps, key points
    └── HHMM-<title>.transcript.md    # level 3: full conversation with timestamps
```

Each level links only to the next; nothing is repeated across levels. Headings are English by default,
or Chinese with `lang = "zh"`.

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
memory ingest [paths...] [-p <Person>] [--context "..."] [--delete]  # default: the person's sources
memory add "first met at the station" --tag memories
memory resummarize <entry.md> [--model deepseek:...]   # rebuild level 2 from the stored transcript
memory index                                            # rebuild index.md
memory search <text>
```

- Recording start time: a timestamp in the file name (`...-202611011228.m4a`, `20261101_093015.mp3`),
  else the container's `creation_time`, else the file's mtime.
- Audio is deduplicated by sha256, so re-running `ingest` on the same sources only adds new recordings.
- The summary prompt is `src/memory/prompts/summarize.<lang>.md`; its structure is `SCHEMA` in
  `src/memory/summarize.py`.

## Development

```sh
uv run pytest
```
