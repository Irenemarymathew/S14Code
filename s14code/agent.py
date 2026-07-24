"""The surface agent: Gemini composes the UI; code decides what is legal.

This is the generative core of Session 14. Given a task and the data produced
by an S13 run, the agent asks the model (through the glc_v3 gateway, the same
path S13 uses) to emit an A2UI component tree using ONLY the trusted catalog.
The model decides what is useful. The validator decides what is possible.

The design mirrors S13's two planners:
  - constrained model planner   the model emits the surface (agent.generate)
  - deterministic fallback      showcase.build_corpus_dashboard, used when the
                                model's surface fails validation or the gateway
                                is unavailable

Because the model's output is untrusted, it passes through the SAME validator
that rejects injections. If Gemini hallucinates a RawHtml node or an
unregistered action, the wall drops it — the agent cannot escape its own
catalog.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import httpx

from .catalog import catalog_manifest
from .validator import validate_surface

_SYSTEM = """You compose user interfaces as declarative JSON only.
You may use ONLY these component types and their listed properties. You may NOT
invent component types, add event-handler properties (onclick, onerror, ...),
put HTML/markup in any text value, or reference any action outside the
registered list. Every displayed value must be a binding of the form
{"$bind": "/pointer"} into the provided data model. Output a single JSON object
with keys root, components (a flat array, each with a unique id), and reuse the
data model keys given to you. No prose, no code fences.

CATALOG:
%s

DATA MODEL KEYS AVAILABLE:
%s
"""


@dataclass(frozen=True)
class GenerationResult:
    surface: dict
    source: str  # "model" | "fallback"
    provider: str | None
    model: str | None
    rejections: list  # validator rejections on the model's raw output
    raw: str = ""


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


class SurfaceAgent:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or os.getenv("GLC_BASE_URL", "http://127.0.0.1:8111")).rstrip("/")

    def _call_gateway(self, prompt: str, system: str) -> dict:
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "system": system,
            "max_tokens": 1500,
            "temperature": 0,
            "reasoning": "off",
            "agent": "s14_surface",
        }
        if provider := os.getenv("S14_GATEWAY_PROVIDER", os.getenv("S13_GATEWAY_PROVIDER", "gemini")):
            payload["provider"] = provider
        resp = httpx.post(f"{self.base_url}/v1/chat", json=payload, timeout=120)
        if resp.status_code >= 400:
            raise RuntimeError(f"GLC /v1/chat returned {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    def generate(self, task: str, data_model: dict, *, fallback) -> GenerationResult:
        """Ask the model for a surface; validate it; fall back if illegal.

        ``fallback`` is a zero-arg callable returning a deterministic surface
        (e.g. lambda: build_corpus_dashboard(run)).
        """
        system = _SYSTEM % (json.dumps(catalog_manifest(), indent=2), sorted(data_model.keys()))
        prompt = f"Task: {task}\nData model: {json.dumps(data_model)}\nCompose the surface."
        try:
            body = self._call_gateway(prompt, system)
        except Exception:
            fb = fallback()
            return GenerationResult(fb, "fallback", None, None, [], raw="")

        raw = body.get("text", "")
        candidate = _extract_json(raw)
        if candidate and "components" in candidate:
            candidate.setdefault("dataModel", data_model)
            result = validate_surface(candidate)
            if result.ok:
                return GenerationResult(
                    {"root": candidate.get("root"), "components": result.accepted, "dataModel": data_model},
                    "model", body.get("provider"), body.get("model"), [], raw=raw,
                )
            # The model produced an illegal surface: keep the safe part, but the
            # honest move is to fall back so the run is coherent, and report what
            # the wall caught on the model's own output.
            fb = fallback()
            return GenerationResult(
                fb, "fallback", body.get("provider"), body.get("model"),
                [r.as_dict() for r in result.rejections], raw=raw,
            )

        fb = fallback()
        return GenerationResult(fb, "fallback", body.get("provider"), body.get("model"), [], raw=raw)
