from hsr_endgame_exporter.parsers import make_phase_row


def test_make_phase_row_uses_mode_config_and_stable_columns():
    config = {
        "collect_date_iso": "2026-06-25",
        "moc": {
            "ver": "4.2.1",
            "name": "Example Phase",
            "start_iso": "2026-06-01",
            "end_iso": "2026-06-15",
        },
    }
    row = make_phase_row(
        snapshot_id="4.3.2",
        config_entry=config,
        mode="moc",
        source_path="4.3.2/",
        has_chars=True,
        has_comps=False,
        has_histograph=True,
        collect_date=config["collect_date_iso"],
    )
    assert row["snapshot_id"] == "4.3.2"
    assert row["mode_cn"] == "混沌回忆"
    assert row["phase_ver"] == "4.2.1"
    assert row["phase_name"] == "Example Phase"
    assert row["has_chars"] == 1
    assert row["has_comps"] == 0
    assert row["has_histograph"] == 1

