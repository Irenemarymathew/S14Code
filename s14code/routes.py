"""HTTP + SSE surface for S14Code.

  GET  /healthz                     liveness
  GET  /v1/catalog                  the trusted component catalog
  GET  /v1/runs                     recorded runs available for replay
  GET  /v1/runs/{id}/surface        build + validate a declarative surface
  GET  /v1/runs/{id}/events         AG-UI event stream over SSE
  POST /v1/action                   a validated user action (approve/reject/rerun)
  POST /v1/validate                 validate an arbitrary surface (injection wall)
  GET  /s/{id}                      the render client, pointed at a run
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from .agui import stream_agui
from .catalog import catalog_manifest
from .hitl import PendingAction, decide_resume
from .showcase import build_corpus_dashboard
from .surface import build_run_surface
from .validator import validate_surface

router = APIRouter()
_CLIENT = Path(__file__).parent.parent / "client" / "index.html"


def _source(request: Request):
    state = request.app.state
    if state.prefer_live and state.live is not None:
        return state.live
    return state.recorded


@router.get("/healthz")
async def healthz():
    return {"ok": True, "service": "s14code", "holds_credentials": False}


@router.get("/v1/catalog")
async def catalog():
    return catalog_manifest()


@router.get("/v1/runs")
async def runs(request: Request):
    return {"recorded": request.app.state.recorded.available()}


@router.get("/v1/runs/{run_id}/surface")
async def surface(run_id: str, request: Request):
    try:
        run = _source(request).get_run(run_id)
    except KeyError:
        raise HTTPException(404, "run not found") from None
    built = build_run_surface(run)
    result = validate_surface(built)
    # The builder's own surface is always clean; validating it here proves the
    # service treats even its own output as untrusted before serving.
    return {
        "run_id": run_id,
        "surface": {"root": built["root"], "components": result.accepted, "dataModel": built["dataModel"]},
        "rejections": [r.as_dict() for r in result.rejections],
    }


@router.get("/v1/harness/surface")
async def harness_surface():
    """Serve the real surface composed by the S13 harness run (proofs/harness_run.json).

    Re-validates on serve, so what renders is provably the model's own output
    passed through the same wall that guards injection.
    """
    import json as _json
    from pathlib import Path as _Path

    path = _Path(__file__).parent.parent / "proofs" / "harness_run.json"
    if not path.exists():
        raise HTTPException(404, "harness_run.json not found — run proofs/harness_run.py first")
    data = _json.loads(path.read_text())
    node = data["compose_surface_node"]
    acc = node["surface_accepted"]
    surface = {"root": acc["root"], "components": acc["components"], "dataModel": node["data_model"]}
    result = validate_surface(surface)
    return {
        "run_id": data.get("run_id"),
        "surface": surface,
        "component_count": len(result.accepted),
        "validator": {"proposed": len(surface["components"]), "accepted": len(result.accepted),
                      "rejected": len(result.rejections)},
        "clean": result.ok,
        "provider": node.get("provider"),
        "model": node.get("model"),
    }


@router.get("/v1/runs/{run_id}/dashboard")
async def dashboard(run_id: str, request: Request):
    """Build the rich showcase dashboard from a corpus run, validated."""
    try:
        run = _source(request).get_run(run_id)
    except KeyError:
        raise HTTPException(404, "run not found") from None
    built = build_corpus_dashboard(run)
    result = validate_surface(built)
    return {
        "run_id": run_id,
        "surface": {"root": built["root"], "components": result.accepted, "dataModel": built["dataModel"]},
        "component_count": len(result.accepted),
        "executable_nodes": len(result.rejections),
        "clean": result.ok,
    }


@router.get("/v1/harness/surface")
async def harness_surface():
    """Serve the surface a REAL S13 harness run composed (proofs/harness_run.json)."""
    path = Path(__file__).parent.parent / "proofs" / "harness_run.json"
    if not path.exists():
        raise HTTPException(404, "no harness run captured yet")
    data = json.loads(path.read_text())
    node = data["compose_surface_node"]
    acc = node["surface_accepted"]
    surface = acc if "components" in acc else {"root": acc.get("root"), "components": acc.get("components", [])}
    surface["dataModel"] = node.get("data_model", {})
    v = node.get("validator", {})
    return {"run_id": data.get("run_id"), "provider": node.get("provider"), "model": node.get("model"),
            "surface": surface, "validator": v, "component_count": len(surface.get("components", []))}


@router.get("/v1/runs/{run_id}/events")
async def events(run_id: str, request: Request):
    try:
        run = _source(request).get_run(run_id)
    except KeyError:
        raise HTTPException(404, "run not found") from None

    async def gen():
        for ev in stream_agui(run["events"], finished=run["finished"]):
            yield f"data: {json.dumps(ev)}\n\n"
            await asyncio.sleep(0.25)  # pace the tape so a browser can render it

    return StreamingResponse(gen(), media_type="text/event-stream")


class ValidateBody(BaseModel):
    surface: dict


@router.post("/v1/validate")
async def validate(body: ValidateBody):
    result = validate_surface(body.surface)
    return {
        "ok": result.ok,
        "accepted": [c.get("id") for c in result.accepted],
        "rejections": [r.as_dict() for r in result.rejections],
    }


class ActionBody(BaseModel):
    run_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    args: dict = Field(default_factory=dict)
    # In a live system the pending params come from the parked node in S13. For
    # the recorded demo the caller supplies them so the binding check is real.
    pending_params: dict = Field(default_factory=dict)
    pending_summary: str = ""


@router.post("/v1/action")
async def action(body: ActionBody):
    pending = PendingAction(body.run_id, body.node_id, body.pending_summary, body.pending_params)
    decision = decide_resume(pending, body.action, body.args)
    if not decision.allowed:
        # A tamper attempt is refused; the node stays waiting.
        raise HTTPException(409, decision.reason)
    return {"resumed": True, "node_id": body.node_id, "reason": decision.reason}


@router.get("/s/{run_id}", response_class=HTMLResponse)
async def client(run_id: str):
    if not _CLIENT.exists():
        raise HTTPException(500, "render client missing")
    return _CLIENT.read_text().replace("__RUN_ID__", run_id)
