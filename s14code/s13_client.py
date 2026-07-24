"""Read the Session 13 graph journal.

Two sources, one interface. In a live workshop S14Code reads a running
``S13Code`` over HTTP on 8113. Offline, or in tests and the widget replays, it
reads a recorded journal fixture captured from a real S13 run. The recorded
shape is byte-for-byte the S13 ``GET /v1/agent/runs/{id}`` response:
``{run_id, finished, nodes, edges, events}``.

S14Code holds no provider credential and never talks to the gateway. It only
reads the graph the agent already produced.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

_FIXTURES = Path(__file__).parent / "fixtures"


class S13Source:
    def get_run(self, run_id: str) -> dict:  # pragma: no cover - interface
        raise NotImplementedError


class LiveS13(S13Source):
    """Attach to a running S13Code over HTTP."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def get_run(self, run_id: str) -> dict:
        resp = httpx.get(f"{self.base_url}/v1/agent/runs/{run_id}", timeout=10)
        resp.raise_for_status()
        return resp.json()


class RecordedS13(S13Source):
    """Replay a recorded S13 journal fixture. Real shape, no live LLM needed."""

    def __init__(self, directory: Path = _FIXTURES):
        self.directory = directory

    def get_run(self, run_id: str) -> dict:
        path = self.directory / f"{run_id}.json"
        if not path.exists():
            raise KeyError(run_id)
        return json.loads(path.read_text())

    def available(self) -> list[str]:
        return sorted(p.stem for p in self.directory.glob("*.json") if p.stem != "injections")


def load_injections() -> dict:
    """The catalogue of malicious surfaces used by the injection wall widget."""
    return json.loads((_FIXTURES / "injections.json").read_text())
