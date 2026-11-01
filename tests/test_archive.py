from datetime import datetime, timedelta, timezone

from memory import archive

TZ = timezone(timedelta(hours=8))
WHEN = datetime(2026, 11, 1, 15, 30, tzinfo=TZ)


def test_day_dir(tmp_path):
    assert archive.day_dir(tmp_path, WHEN) == tmp_path / "2026" / "11" / "01"


def test_slugify_keeps_cjk():
    assert archive.slugify("Walk in 公园!") == "walk-in-公园"
    assert archive.slugify("   ") == "note"


def test_unique_entry_path(tmp_path):
    p1 = archive.entry_path(tmp_path, WHEN, "walk")
    assert p1 == tmp_path / "2026/11/01/1530-walk.md"
    p1.parent.mkdir(parents=True)
    p1.write_text("x")
    assert archive.entry_path(tmp_path, WHEN, "walk").name == "1530-walk-2.md"


def test_roundtrip(tmp_path):
    p = tmp_path / "a.md"
    archive.write_entry(p, {"date": WHEN.isoformat(), "tags": ["家"]}, "## 正文\n内容\n")
    meta, body = archive.read_entry(p)
    assert meta["tags"] == ["家"]
    assert body == "## 正文\n内容\n"
    assert not list(tmp_path.glob("*.tmp"))


def test_iter_entries_skips_transcripts_and_index(tmp_path):
    e = archive.entry_path(tmp_path, WHEN, "a")
    archive.write_entry(e, {"date": WHEN.isoformat()}, "x")
    archive.atomic_write(archive.transcript_path(e), "x")
    archive.atomic_write(archive.index_path(tmp_path), "x")
    assert archive.transcript_path(e).name == "1530-a.transcript.md"
    assert [p.name for p in archive.iter_entries(tmp_path)] == ["1530-a.md"]


def test_entry_path_avoids_transcript_collision(tmp_path):
    e = archive.entry_path(tmp_path, WHEN, "a")
    archive.atomic_write(archive.transcript_path(e), "x")
    assert archive.entry_path(tmp_path, WHEN, "a").name == "1530-a-2.md"
