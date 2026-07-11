import json
from pathlib import Path

from hsr_endgame_exporter.hf_client import HuggingFaceClient


def test_hf_client_fixture_freezes_python_url_contract():
    fixture = json.loads((Path(__file__).parent / "fixtures" / "hf_client_cases.json").read_text(encoding="utf-8"))
    for case in fixture["urls"]:
        client = HuggingFaceClient(repo_id=case["repo_id"], revision=case["revision"])
        quoted_path = client._request(client._api_base()).full_url  # request construction is network-free
        assert quoted_path == client._api_base()

        import urllib.parse

        path = urllib.parse.quote(case["path"].strip("/"))
        tree_url = client._api_base() + (f"/{path}" if path else "")
        tree_url += f"?recursive={'true' if case['recursive'] else 'false'}&expand=false"
        assert tree_url == case["tree_url"]
        assert client.raw_url(case["path"]) == case["raw_url"]


def test_hf_tree_response_and_cache_relative_path_contract():
    fixture = json.loads((Path(__file__).parent / "fixtures" / "hf_client_cases.json").read_text(encoding="utf-8"))
    encoded = json.dumps(fixture["tree_response"], ensure_ascii=False)
    assert json.loads(encoded) == fixture["tree_response"]
    assert [row["type"] for row in fixture["tree_response"]] == ["file", "directory"]

    cache = fixture["cache"]
    destination = Path(cache["raw_dir"]).joinpath(*cache["source_path"].split("/"))
    assert destination.parts[-4:] == tuple(cache["relative_parts"])
