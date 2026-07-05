from hsr_endgame_exporter.normalize import parse_percent


def test_parse_percent():
    assert parse_percent("12.34%") == 12.34
    assert parse_percent(12.34) == 12.34
    assert parse_percent("-") is None
    assert parse_percent("") is None
    assert parse_percent(None) is None
    assert parse_percent("0.00") == 0.0

