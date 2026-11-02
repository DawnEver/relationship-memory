from datetime import date, datetime, timedelta, timezone

from memory import archive, ingest
from memory.transcribe import Segment

TZ = timezone(timedelta(hours=8))
WHEN = datetime(2026, 11, 1, 9, 5, tzinfo=TZ)
DAY = WHEN.date()
INFO = ingest.AudioInfo(recorded=WHEN, duration=70.0)
SUMMARY = {"title": "公园散步", "summary": "和妈妈去公园。散步很开心。", "points": ["天气好"],
           "disputes": [{"topic": "旅行目的地", "sides": ["妈妈想去云南", "我想去海边"], "outcome": "暂定云南"}],
           "plans": [{"item": "订云南机票", "owner": "我", "when": "12 月前"}],
           "tags": ["家庭"], "people": ["妈妈"]}


class FakeTranscriber:
    def __init__(self, text="今天去公园"):
        self.text = text

    def transcribe(self, path):
        return [Segment(0.0, 2.0, self.text), Segment(65.5, 70.0, "妈妈很开心")]


class FakeSummarizer:
    def __init__(self):
        self.seen = []

    def summarize(self, material, context):
        self.seen.append(material)
        return SUMMARY

    def learn(self, facts, learned, material, day):
        self.seen.append((facts, learned, material, day))
        return learned + f"- {day}: 新事实\n"


def make_audio(tmp_path, name="rec.m4a", data=b"audio-bytes"):
    src = tmp_path / name
    src.write_bytes(data)
    return src


def test_ingest_writes_transcript_only(tmp_path):
    root, src = tmp_path / "root", make_audio(tmp_path)
    item = ingest.ingest_audio(root, src, FakeTranscriber(), info=INFO, lang="zh")
    assert item == root / "2026/11/01/0905.md"
    meta, body = archive.read_entry(item)
    assert meta["type"] == "audio" and meta["source"] == "rec.m4a"
    assert meta["duration"] == "00:01:10" and len(meta["sha256"]) == 64
    assert body == "[摘要](summary.md)\n\n[00:00] 今天去公园\n[01:05] 妈妈很开心\n"
    assert ingest.read_transcript(item) == "[00:00] 今天去公园\n[01:05] 妈妈很开心"
    assert [p.name for p in item.parent.iterdir()] == ["0905.md"]
    assert src.exists()


def test_ingest_dedupes_and_force_redoes_in_place(tmp_path):
    root, src = tmp_path / "root", make_audio(tmp_path)
    first = ingest.ingest_audio(root, src, FakeTranscriber(), info=INFO)
    assert ingest.ingest_audio(root, src, FakeTranscriber("x"), info=INFO) is None
    again = ingest.ingest_audio(root, src, FakeTranscriber("重新识别"), info=INFO, force=True)
    assert again == first
    assert "重新识别" in ingest.read_transcript(first)
    assert len(list(archive.iter_items(root))) == 1


def test_summarize_day_combines_items(tmp_path):
    root = tmp_path / "root"
    ingest.ingest_audio(root, make_audio(tmp_path), FakeTranscriber(), info=INFO, lang="zh")
    later = ingest.AudioInfo(WHEN.replace(hour=21), 3700.0)
    ingest.ingest_audio(root, make_audio(tmp_path, "b.m4a", b"b"), FakeTranscriber("晚上"), info=later, lang="zh")
    ingest.add_note(root, "第一次叫爸爸", WHEN.replace(hour=12), tags=["成长"])
    s = FakeSummarizer()
    path = ingest.summarize_day(root, DAY, s, "背景", lang="zh")

    material = s.seen[0]
    assert material.index("### 09:05") < material.index("### 12:05") < material.index("### 21:05")
    assert "今天去公园" in material and "第一次叫爸爸" in material and "晚上" in material
    assert "[摘要]" not in material

    assert path == root / "2026/11/01/summary.md"
    meta, body = archive.read_entry(path)
    assert meta["date"] == "2026-11-01" and meta["title"] == "公园散步" and meta["tags"] == ["家庭"]
    assert body.startswith("## 摘要\n和妈妈去公园。")
    assert "### 旅行目的地\n- 妈妈想去云南\n- 我想去海边\n- 结果：暂定云南" in body
    assert "- [ ] 订云南机票（我，12 月前）" in body
    assert "## 当天记录\n- [09:05 录音 · 00:01:10](0905.md)\n- [12:05 笔记 · 第一次叫爸爸](1205-第一次叫爸爸.md)\n" in body
    assert "- [21:05 录音 · 01:01:40](2105.md)" in body


def test_summarize_day_without_summarizer_lists_items(tmp_path):
    root = tmp_path / "root"
    ingest.ingest_audio(root, make_audio(tmp_path), FakeTranscriber(), info=INFO)
    meta, body = archive.read_entry(ingest.summarize_day(root, DAY, None))
    assert meta["title"] == "2026-11-01"
    assert body == "## Records\n- [09:05 Recording · 00:01:10](0905.md)\n"


def test_english_is_default(tmp_path):
    root = tmp_path / "root"
    item = ingest.ingest_audio(root, make_audio(tmp_path), FakeTranscriber(), info=INFO)
    assert archive.read_entry(item)[1].startswith("[Summary](summary.md)")
    _, body = archive.read_entry(ingest.summarize_day(root, DAY, FakeSummarizer()))
    assert body.startswith("## Summary\n")
    assert "- Outcome: 暂定云南" in body and "- [ ] 订云南机票 (我, 12 月前)" in body


def test_index(tmp_path):
    root = tmp_path / "root"
    ingest.ingest_audio(root, make_audio(tmp_path), FakeTranscriber(), info=INFO)
    ingest.summarize_day(root, DAY, FakeSummarizer())
    ingest.add_note(root, "x", datetime(2026, 10, 3, 8, 0, tzinfo=TZ))
    ingest.summarize_day(root, date(2026, 10, 3), None)
    archive.atomic_write(root / "Likes&Dislikes.md", "# 喜好\n")
    text = ingest.build_index(root, "Alice").read_text("utf-8")
    assert text.startswith("# Alice\n\n- [Likes&Dislikes](Likes&Dislikes.md)\n")
    assert "## 2026-11\n- 11-01 [公园散步](2026/11/01/summary.md) #家庭 — 和妈妈去公园。\n" in text
    assert "## 2026-10\n- 10-03 [2026-10-03](2026/10/03/summary.md)" in text
    assert text.index("## 2026-11") < text.index("## 2026-10")


def test_time_from_filename():
    t = ingest.time_from_name("WeChat-Alice-202611011228.m4a")
    assert (t.year, t.month, t.day, t.hour, t.minute) == (2026, 11, 1, 12, 28)
    assert ingest.time_from_name("20261101_093015.mp3").second == 15
    assert ingest.time_from_name("rec.m4a") is None
    assert ingest.time_from_name("x-20261399-1200.m4a") is None
