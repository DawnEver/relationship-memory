from datetime import datetime, timedelta, timezone

from memory import archive, ingest
from memory.transcribe import Segment

TZ = timezone(timedelta(hours=8))
WHEN = datetime(2026, 11, 1, 9, 5, tzinfo=TZ)
INFO = ingest.AudioInfo(recorded=WHEN, duration=70.0)


class FakeTranscriber:
    def transcribe(self, path):
        return [Segment(0.0, 2.0, "今天去公园"), Segment(65.5, 70.0, "妈妈很开心")]


class FakeSummarizer:
    def summarize(self, transcript, context):
        assert "[01:05] 妈妈很开心" in transcript
        return {"title": "公园散步", "summary": "和妈妈去公园。", "points": ["天气好"],
                "disputes": [{"topic": "旅行目的地", "sides": ["妈妈想去云南", "我想去海边"], "outcome": "暂定云南"}],
                "plans": [{"item": "订云南机票", "owner": "我", "when": "12 月前"}],
                "tags": ["家庭"], "people": ["妈妈"]}


def make_audio(tmp_path, data=b"audio-bytes"):
    src = tmp_path / "rec.m4a"
    src.write_bytes(data)
    return src


def test_ingest_writes_summary_and_transcript_only(tmp_path):
    root, src = tmp_path / "root", make_audio(tmp_path)
    entry = ingest.ingest_audio(root, src, FakeTranscriber(), FakeSummarizer(), info=INFO, lang="zh")
    assert entry == root / "2026/11/01/0905-公园散步.md"
    meta, body = archive.read_entry(entry)
    assert meta["type"] == "audio" and meta["source"] == "rec.m4a"
    assert meta["duration"] == "00:01:10"
    assert meta["tags"] == ["家庭"] and meta["people"] == ["妈妈"]
    assert body.startswith("## 摘要\n和妈妈去公园。")
    assert "### 旅行目的地\n- 妈妈想去云南\n- 我想去海边\n- 结果：暂定云南" in body
    assert "- [ ] 订云南机票（我，12 月前）" in body
    assert "[完整对话](0905-公园散步.transcript.md)" in body
    assert "今天去公园" not in body

    transcript = archive.transcript_path(entry).read_text("utf-8")
    assert "[摘要](0905-公园散步.md)" in transcript
    assert "[00:00] 今天去公园\n[01:05] 妈妈很开心" in transcript
    assert sorted(p.name for p in entry.parent.iterdir()) == ["0905-公园散步.md", "0905-公园散步.transcript.md"]
    assert src.exists()


def test_ingest_dedupes_by_hash(tmp_path):
    root, src = tmp_path / "root", make_audio(tmp_path)
    first = ingest.ingest_audio(root, src, FakeTranscriber(), FakeSummarizer(), info=INFO, lang="zh")
    again = ingest.ingest_audio(root, src, FakeTranscriber(), FakeSummarizer(), info=INFO, lang="zh")
    assert again == first
    assert len(list(archive.iter_entries(root))) == 1


def test_ingest_without_summarizer(tmp_path):
    root = tmp_path / "root"
    entry = ingest.ingest_audio(root, make_audio(tmp_path), FakeTranscriber(), None, info=INFO, lang="zh")
    assert entry.name == "0905-rec.md"
    _, body = archive.read_entry(entry)
    assert "## 摘要" not in body and "[完整对话](0905-rec.transcript.md)" in body


def test_resummarize_reads_transcript_file(tmp_path):
    root = tmp_path / "root"
    entry = ingest.ingest_audio(root, make_audio(tmp_path), FakeTranscriber(), None, info=INFO, lang="zh")
    entry = ingest.resummarize(entry, FakeSummarizer(), lang="zh")
    meta, body = archive.read_entry(entry)
    assert meta["tags"] == ["家庭"] and meta["title"] == "公园散步"
    assert "## 摘要" in body and "[完整对话](0905-公园散步.transcript.md)" in body
    assert sorted(p.name for p in entry.parent.iterdir()) == ["0905-公园散步.md", "0905-公园散步.transcript.md"]


def test_add_note_and_index(tmp_path):
    root = tmp_path / "root"
    ingest.ingest_audio(root, make_audio(tmp_path), FakeTranscriber(), FakeSummarizer(), info=INFO, lang="zh")
    ingest.add_note(root, "第一次叫爸爸", WHEN.replace(hour=10), tags=["成长"])
    index = ingest.build_index(root, "Alice")
    text = index.read_text("utf-8")
    assert index == root / "index.md"
    assert text.startswith("# Alice\n")
    assert "## 2026-11-01" in text
    assert "- 09:05 [公园散步](2026/11/01/0905-公园散步.md) #家庭 — 和妈妈去公园。" in text
    assert "- 10:05 [第一次叫爸爸](2026/11/01/1005-第一次叫爸爸.md) #成长" in text


def test_time_from_filename():
    t = ingest.time_from_name("WeChat-Alice-202611011228.m4a")
    assert (t.year, t.month, t.day, t.hour, t.minute) == (2026, 11, 1, 12, 28)
    assert ingest.time_from_name("20261101_093015.mp3").second == 15
    assert ingest.time_from_name("rec.m4a") is None
    assert ingest.time_from_name("x-20261399-1200.m4a") is None


def test_english_is_default(tmp_path):
    root = tmp_path / "root"
    entry = ingest.ingest_audio(root, make_audio(tmp_path), FakeTranscriber(), FakeSummarizer(), info=INFO)
    _, body = archive.read_entry(entry)
    assert body.startswith("## Summary\n")
    assert "## Key disputes & discussions\n### 旅行目的地" in body and "- Outcome: 暂定云南" in body
    assert "- [ ] 订云南机票 (我, 12 月前)" in body
    assert "[Full conversation](0905-公园散步.transcript.md)" in body
    assert "[Summary](0905-公园散步.md)" in archive.transcript_path(entry).read_text("utf-8")
    assert "— 和妈妈去公园。" in ingest.build_index(root, "Alice").read_text("utf-8")


class OtherTranscriber:
    def transcribe(self, path):
        return [Segment(0.0, 1.0, "重新识别")]


def test_force_keeps_name_when_title_unchanged(tmp_path):
    root, src = tmp_path / "root", make_audio(tmp_path)
    first = ingest.ingest_audio(root, src, FakeTranscriber(), None, info=INFO, lang="zh")
    again = ingest.ingest_audio(root, src, OtherTranscriber(), None, info=INFO, lang="zh", force=True)
    assert again == first
    assert "[00:00] 重新识别" in archive.transcript_path(first).read_text("utf-8")
    assert len(list(archive.iter_entries(root))) == 1


def test_index_lists_person_notes(tmp_path):
    root = tmp_path / "root"
    ingest.add_note(root, "第一次叫爸爸", WHEN)
    archive.atomic_write(root / "Likes&Dislikes.md", "# 喜好\n")
    text = ingest.build_index(root, "Alice").read_text("utf-8")
    assert "- [Likes&Dislikes](Likes&Dislikes.md)" in text
    assert text.index("Likes&Dislikes") < text.index("## 2026-11-01")


def test_force_renames_to_new_title(tmp_path):
    root, src = tmp_path / "root", make_audio(tmp_path)
    old = ingest.ingest_audio(root, src, FakeTranscriber(), None, info=INFO, lang="zh")
    new = ingest.ingest_audio(root, src, FakeTranscriber(), FakeSummarizer(), info=INFO, lang="zh", force=True)
    assert new.name == "0905-公园散步.md"
    assert not old.exists() and not archive.transcript_path(old).exists()
    assert archive.transcript_path(new).is_file()
