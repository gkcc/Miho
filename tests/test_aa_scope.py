from hsr_endgame_exporter.normalize import parse_aa_scope


def test_parse_aa_scope():
    assert parse_aa_scope("knights.json") == ("knights", "骑士关卡")
    assert parse_aa_scope("boss_stage.json") == ("king_piece", "王棋关卡")
    assert parse_aa_scope("top.json") == ("all_bosses", "全 Boss / 未拆分")

