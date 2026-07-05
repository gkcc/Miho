from __future__ import annotations

import json
import shutil
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .constants import DEFAULT_REPO_ID, DEFAULT_REVISION


class HuggingFaceClient:
    def __init__(
        self,
        repo_id: str = DEFAULT_REPO_ID,
        revision: str = DEFAULT_REVISION,
        timeout: int = 60,
    ) -> None:
        self.repo_id = repo_id
        self.revision = revision
        self.timeout = timeout

    def _request(self, url: str) -> urllib.request.Request:
        return urllib.request.Request(
            url,
            headers={
                "User-Agent": "hsr-endgame-exporter/0.1 (+https://huggingface.co)",
                "Accept": "application/json,text/plain,*/*",
            },
        )

    def _api_base(self) -> str:
        return f"https://huggingface.co/api/datasets/{self.repo_id}/tree/{self.revision}"

    def _resolve_base(self) -> str:
        return f"https://huggingface.co/datasets/{self.repo_id}/resolve/{self.revision}"

    def list_tree(self, path: str = "", recursive: bool = False) -> list[dict[str, Any]]:
        quoted_path = urllib.parse.quote(path.strip("/"))
        url = self._api_base()
        if quoted_path:
            url = f"{url}/{quoted_path}"
        url = f"{url}?recursive={'true' if recursive else 'false'}&expand=false"
        with urllib.request.urlopen(self._request(url), timeout=self.timeout) as response:
            return json.load(response)

    def raw_url(self, path: str) -> str:
        return f"{self._resolve_base()}/{urllib.parse.quote(path)}"

    def download_text(self, path: str) -> str:
        with urllib.request.urlopen(self._request(self.raw_url(path)), timeout=self.timeout) as response:
            return response.read().decode("utf-8")

    def download_json(self, path: str) -> Any:
        return json.loads(self.download_text(path))

    def download_to(self, path: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(self._request(self.raw_url(path)), timeout=self.timeout) as response:
            with destination.open("wb") as output:
                shutil.copyfileobj(response, output)

