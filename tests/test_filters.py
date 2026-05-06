from relay.filters import TemporalFilter

n = 3
conf = 0.5

def test_normal_trigger():
    t1 = TemporalFilter(conf, n)
    for _ in range(n-1):
        assert t1.update("Test_1", 0.6) is False

    assert t1.update("Test_1", 0.6) is True
    assert t1.count == n

def test_below_threshold():
    t2 = TemporalFilter(conf, n)
    for _ in range(n):
        assert t2.update("Test_2", 0.1) is False

    assert t2.count == 0

def test_object_disappears():
    t3 = TemporalFilter(conf, n)
    assert t3.update("Test_3", 0.6) is False
    assert t3.update("Test_3", 0.6) is False
    assert t3.update("Test_3", 0.1) is False
    assert t3.update("Test_3", 0.6) is False

    assert t3.count == 1

def test_confidence_oscillates():
    t4 = TemporalFilter(conf, n)

    assert t4.update("Test_4", 0.6) is False
    assert t4.update("Test_4", 0.1) is False
    assert t4.update("Test_4", 0.1) is False
    assert t4.update("Test_4", 0.6) is False
    assert t4.update("Test_4", 0.1) is False
    assert t4.update("Test_4", 0.6) is False
    assert t4.update("Test_4", 0.6) is False


"""
    To run use
    uv run pytest tests/test_filters.py -v
"""