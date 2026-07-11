import json

from compat_compare import compare_artifact_trees


def test_compare_artifact_trees_normalizes_json_and_csv(tmp_path):
    expected, actual = tmp_path / "expected", tmp_path / "actual"
    expected.mkdir(); actual.mkdir()
    (expected / "table.csv").write_bytes(b"a,b\n1,2\n")
    (actual / "table.csv").write_bytes(b"a,b\r\n1,2\r\n")
    (expected / "data.json").write_text(json.dumps({"generated_at": "old", "v": 1}), encoding="utf-8")
    (actual / "data.json").write_text(json.dumps({"v": 1, "generated_at": "new"}), encoding="utf-8")
    assert compare_artifact_trees(expected, actual, {"generated_at"}) == []


def test_compare_artifact_trees_reports_file_and_content_differences(tmp_path):
    expected, actual = tmp_path / "expected", tmp_path / "actual"
    expected.mkdir(); actual.mkdir()
    (expected / "only.txt").write_text("expected", encoding="utf-8")
    (actual / "extra.txt").write_text("extra", encoding="utf-8")
    assert compare_artifact_trees(expected, actual) == ["missing: only.txt", "unexpected: extra.txt"]
