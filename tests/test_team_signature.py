from hsr_endgame_exporter.normalize import (
    make_ordered_signature,
    make_unordered_signature,
    natural_version_key,
)


def test_team_signatures():
    ordered = make_ordered_signature(
        "4.3.2",
        "2026-06-25",
        "moc",
        "all",
        "top",
        "4.3.1",
        "Gale of Forgetting",
        ["a", "b", "c", "d"],
    )
    assert ordered == "4.3.2|2026-06-25|moc|all|top|4.3.1|Gale of Forgetting|a>b>c>d"

    unordered = make_unordered_signature(
        "4.3.2",
        "2026-06-25",
        "moc",
        "all",
        "top",
        "4.3.1",
        "Gale of Forgetting",
        ["d", "b", "a", "c"],
    )
    assert unordered == "4.3.2|2026-06-25|moc|all|top|4.3.1|Gale of Forgetting|a>b>c>d"


def test_natural_version_key_compares_numeric_runs():
    assert natural_version_key("4.3.10") > natural_version_key("4.3.9")
    assert natural_version_key("4.10") > natural_version_key("4.9")
    assert natural_version_key("fixture-10") > natural_version_key("fixture-9")
