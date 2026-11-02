from datetime import date, datetime, timedelta, timezone

from memory import archive

TZ = timezone(timedelta(hours=8))
WHEN = datetime(2026, 11, 1, 15, 30, tzinfo=TZ)


def test_day_paths(tmp_path):
    assert archive.day_dir(tmp_path, WHEN) == tmp_path / "2026" / "11" / "01"
    assert archive.summary_path(tmp_path, WHEN.date()) == tmp_path / "2026/11/01/summary.md"


def test_slugify_keeps_cjk():
    assert archive.slugify("Walk in 公园!") == "walk-in-公园"
    assert archive.slugify("   ") == "note"


def test_unique_item_paths(tmp_path):
    p1 = archive.recording_path(tmp_path, WHEN)
    assert p1 == tmp_path / "2026/11/01/1530.md"
    archive.atomic_write(p1, "x")
    assert archive.recording_path(tmp_path, WHEN).name == "1530-2.md"
    assert archive.note_path(tmp_path, WHEN, "walk").name == "1530-walk.md"


def test_roundtrip(tmp_path):
    p = tmp_path / "a.md"
    archive.write_entry(p, {"date": WHEN.isoformat(), "tags": ["家"]}, "## 正文\n内容\n")
    meta, body = archive.read_entry(p)
    assert meta["tags"] == ["家"]
    assert body == "## 正文\n内容\n"
    assert not list(tmp_path.glob("*.tmp"))


def test_items_and_days_skip_summaries(tmp_path):
    archive.atomic_write(archive.recording_path(tmp_path, WHEN), "x")
    archive.atomic_write(archive.summary_path(tmp_path, WHEN.date()), "x")
    archive.atomic_write(archive.index_path(tmp_path), "x")
    assert [p.name for p in archive.iter_items(tmp_path)] == ["1530.md"]
    assert archive.iter_days(tmp_path) == [date(2026, 11, 1)]
