from new import metric


def test_parse_single_line():
    log = "other\nval_loss: 0.1234\nbye\n"
    v = metric.parse(log, r"^val_loss:")
    assert abs(v - 0.1234) < 1e-9


def test_parse_last_match_wins():
    log = "val_loss: 0.5\nval_loss: 0.3\n"
    v = metric.parse(log, r"^val_loss:")
    assert abs(v - 0.3) < 1e-9


def test_parse_no_match_returns_none():
    assert metric.parse("nope\n", r"^val_loss:") is None


def test_parse_bad_number_returns_none():
    assert metric.parse("val_loss: not_a_number\n", r"^val_loss:") is None


def test_stats():
    mean, sd = metric.stats([1.0, 2.0, 3.0])
    assert mean == 2.0
    assert 0.81 < sd < 1.01
