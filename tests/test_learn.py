from datetime import timedelta

from test_ingest import DAY, INFO, FakeSummarizer, FakeTranscriber, make_audio

from memory import archive, ingest, learn


def setup_day(tmp_path, facts="# Alice\n- 我在英国读博\n", learned="- 旧的学习\n"):
    root = tmp_path / "root"
    if facts:
        archive.atomic_write(archive.profile_path(root), facts)
    if learned:
        archive.atomic_write(archive.learned_path(root), learned)
    ingest.ingest_audio(root, make_audio(tmp_path), FakeTranscriber(), info=INFO)
    return root


def test_learn_day_only_proposes(tmp_path):
    root = setup_day(tmp_path)
    s = FakeSummarizer()
    path = learn.learn_day(root, DAY, s)
    facts, base, material, day = s.seen[0]
    assert facts == "# Alice\n- 我在英国读博\n" and base == "- 旧的学习\n"
    assert "今天去公园" in material and day == "2026-11-01"
    assert path == root / "learned.pending.md"
    assert learn.pending(root) == ("- 旧的学习\n- 2026-11-01: 新事实\n", ["2026-11-01"])
    assert archive.learned_path(root).read_text("utf-8") == "- 旧的学习\n"
    assert archive.profile_path(root).read_text("utf-8") == "# Alice\n- 我在英国读博\n"


def test_proposals_accumulate_across_days(tmp_path):
    root = setup_day(tmp_path, learned="")
    ingest.ingest_audio(root, make_audio(tmp_path, "b.m4a", b"b"), FakeTranscriber(),
                        info=ingest.AudioInfo(INFO.recorded + timedelta(days=1), 10.0))
    s = FakeSummarizer()
    learn.learn_day(root, DAY, s)
    learn.learn_day(root, DAY + timedelta(days=1), s)
    assert s.seen[1][1] == "- 2026-11-01: 新事实\n"
    assert learn.pending(root) == ("- 2026-11-01: 新事实\n- 2026-11-02: 新事实\n", ["2026-11-01", "2026-11-02"])


def test_background_ignores_unreviewed_proposals(tmp_path):
    root = setup_day(tmp_path)
    learn.learn_day(root, DAY, FakeSummarizer())
    assert ingest.background(root) == "# Alice\n- 我在英国读博\n\n- 旧的学习"
    assert ingest.background(root, "今天特别").endswith("\n\n今天特别")


def test_diff_accept_reject(tmp_path):
    root = setup_day(tmp_path)
    assert learn.diff(root) == ""
    learn.learn_day(root, DAY, FakeSummarizer())
    d = learn.diff(root)
    assert "+- 2026-11-01: 新事实" in d and "learned.md" in d
    learn.reject(root)
    assert learn.pending(root) is None
    assert archive.learned_path(root).read_text("utf-8") == "- 旧的学习\n"

    learn.learn_day(root, DAY, FakeSummarizer())
    learn.accept(root)
    assert learn.pending(root) is None
    assert archive.learned_path(root).read_text("utf-8") == "- 旧的学习\n- 2026-11-01: 新事实\n"


def test_accept_keeps_user_edits_to_proposal(tmp_path):
    root = setup_day(tmp_path)
    learn.learn_day(root, DAY, FakeSummarizer())
    p = archive.pending_path(root)
    p.write_text(p.read_text("utf-8").replace("新事实", "我改过的事实"), "utf-8")
    learn.accept(root)
    assert "我改过的事实" in archive.learned_path(root).read_text("utf-8")
