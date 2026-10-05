from rerank.policy import TimeoutWindow


def test_three_of_five_timeouts_triggers_downgrade():
    window = TimeoutWindow()
    for value in (True, False, True, True, False):
        window.record("s1", value)
    assert window.should_downgrade("s1")


def test_below_threshold_does_not_downgrade():
    window = TimeoutWindow()
    window.record("s1", True)
    window.record("s1", True)
    window.record("s1", False)
    assert not window.should_downgrade("s1")


def test_only_latest_span_is_counted():
    window = TimeoutWindow(span=3, threshold=2)
    window.record("s", True)
    window.record("s", True)
    window.record("s", False)
    window.record("s", False)
    assert not window.should_downgrade("s")


def test_ttl_resets_window(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("rerank.policy.time.time", lambda: now[0])
    window = TimeoutWindow(ttl_s=600)
    for _ in range(3):
        window.record("s1", True)
    assert window.should_downgrade("s1")
    now[0] += 601
    assert not window.should_downgrade("s1")
    window.record("s1", True)
    assert not window.should_downgrade("s1")
