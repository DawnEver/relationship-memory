from memory.transcribe import Segment, drop_hallucinations


def test_drops_known_hallucinations():
    segs = [Segment(0, 1, "请不吝点赞 订阅 转发 打赏支持明镜与点点栏目"),
            Segment(1, 2, "听得见吗?"),
            Segment(2, 3, "Thanks for watching!")]
    kept = drop_hallucinations(segs, [r"明镜与点点", r"(?i)thanks for watching"])
    assert [s.text for s in kept] == ["听得见吗?"]


def test_no_patterns_keeps_all():
    segs = [Segment(0, 1, "a")]
    assert drop_hallucinations(segs, []) == segs
