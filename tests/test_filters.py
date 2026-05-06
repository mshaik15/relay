from relay.filters import TemporalFilter

n = 3
conf = 0.5


# triggering

def test_normal_trigger():
    t = TemporalFilter(conf, n)
    for _ in range(n - 1):
        assert t.update("Label", 0.6) is False
    assert t.update("Label", 0.6) is True
    assert t.count == n

def test_triggers_exactly_at_n():
    t = TemporalFilter(conf, n)
    results = [t.update("Label", 0.6) for _ in range(n)]
    assert results[-1] is True

def test_continues_triggering_past_n():
    t = TemporalFilter(conf, n)
    for _ in range(n):
        t.update("Label", 0.6)
    assert t.update("Label", 0.6) is True

def test_n_equals_one_triggers_immediately():
    t = TemporalFilter(conf, 1)
    assert t.update("Label", 0.6) is False
    assert t.update("Label", 0.6) is True


# threshold
def test_below_threshold_never_triggers():
    t = TemporalFilter(conf, n)
    for _ in range(n):
        assert t.update("Label", 0.1) is False
    assert t.count == 0

def test_exactly_at_threshold_does_not_trigger():
    t = TemporalFilter(conf, n)
    for _ in range(n):
        t.update("Label", conf)
    assert t.count == n  

def test_just_above_threshold_counts():
    t = TemporalFilter(conf, n)
    t.update("Label", conf + 0.01)
    assert t.count == 1


# label switching
def test_label_change_resets_count():
    t = TemporalFilter(conf, n)
    t.update("A", 0.6)
    t.update("A", 0.6)
    assert t.update("B", 0.6) is False
    assert t.count == 1
    assert t.current_label == "B"

def test_alternating_labels_never_triggers():
    t = TemporalFilter(conf, n)
    for _ in range(6):
        t.update("A", 0.6)
        t.update("B", 0.6)
    assert t.count == 1

def test_return_to_original_label_restarts_count():
    t = TemporalFilter(conf, n)
    t.update("A", 0.6)
    t.update("A", 0.6)
    t.update("B", 0.6) # resets
    t.update("A", 0.6) # restarts A count from 1
    assert t.count == 1
    assert t.current_label == "A"


# confidence oscillation / dropout
def test_object_disappears_resets_count():
    t = TemporalFilter(conf, n)
    t.update("Label", 0.6)
    t.update("Label", 0.6)
    t.update("Label", 0.1) # drops below threshold
    t.update("Label", 0.6) # count restarts at 1
    assert t.count == 1

def test_confidence_oscillates_never_triggers():
    t = TemporalFilter(conf, n)
    sequence = [0.6, 0.1, 0.6, 0.1, 0.6, 0.1, 0.6]
    for c in sequence:
        assert t.update("Label", c) is False


# reset
def test_reset_clears_count():
    t = TemporalFilter(conf, n)
    t.update("Label", 0.6)
    t.update("Label", 0.6)
    t.reset()
    assert t.count == 0
    assert t.current_label is None

def test_reset_mid_stream_prevents_trigger():
    t = TemporalFilter(conf, n)
    for _ in range(n - 1):
        t.update("Label", 0.6)
    t.reset()
    for _ in range(n - 1):
        assert t.update("Label", 0.6) is False


"""
    To run use
    uv run pytest tests/test_filters.py -v
"""