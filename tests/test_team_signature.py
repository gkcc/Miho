from hsr_endgame_exporter.normalize import make_ordered_signature, make_unordered_signature


def test_team_signatures():
    ordered = make_ordered_signature("moc", "all", "4.3.1", ["a", "b", "c", "d"])
    assert ordered == "moc|all|4.3.1|a>b>c>d"

    unordered = make_unordered_signature("moc", "all", "4.3.1", ["d", "b", "a", "c"])
    assert unordered == "moc|all|4.3.1|a>b>c>d"

