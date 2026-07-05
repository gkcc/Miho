from hsr_endgame_exporter.normalize import normalize_character_id


def test_normalize_character_id_examples():
    assert normalize_character_id("Topaz & Numby") == "topaz-and-numby"
    assert normalize_character_id("Dan Heng • Imbibitor Lunae") == "dan-heng-imbibitor-lunae"
    assert normalize_character_id("March 7th") == "march-7th"

