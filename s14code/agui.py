"""Map S13 graph journal events onto AG-UI events.

The Session 13 graph already records a durable, ordered journal. AG-UI is
CopilotKit's event-based agent-UI protocol. We do not invent a stream; we
translate the one that exists into AG-UI's vocabulary so a browser can render
it. The S13 event shape is ``{sequence, kind, node_id, payload}``.

AG-UI event names use SCREAMING_SNAKE_CASE. We use the handful the surface
needs and leave the rest of the ~30-event protocol available:

  run_started    -> RUN_STARTED
  graph_patched  -> STATE_DELTA          (the graph structure changed)
  task_started   -> STEP_STARTED
  task_succeeded -> STEP_FINISHED (+ STATE_DELTA with the node result)
  task_failed    -> STEP_FINISHED (error) + RUN_ERROR
  task_cancelled -> CUSTOM (step_cancelled)
  run_resumed    -> CUSTOM (run_resumed)

RUN_FINISHED is not a journal event in S13 (finished is a run flag), so it is
derived from the snapshot after the last event rather than invented. That is
the honest mapping: we emit exactly what the graph recorded plus one derived
terminal event.
"""

from __future__ import annotations

from typing import Iterable, Iterator

_KIND_TO_AGUI = {
    "run_started": "RUN_STARTED",
    "run_resumed": "CUSTOM",
    "graph_patched": "STATE_DELTA",
    "task_started": "STEP_STARTED",
    "task_succeeded": "STEP_FINISHED",
    "task_failed": "STEP_FINISHED",
    "task_cancelled": "CUSTOM",
}


def to_agui_event(s13_event: dict) -> dict:
    """Translate one S13 journal event into one AG-UI event."""
    kind = s13_event["kind"]
    node = s13_event.get("node_id")
    payload = s13_event.get("payload") or {}
    seq = s13_event["sequence"]
    name = _KIND_TO_AGUI.get(kind, "CUSTOM")

    base = {"type": name, "seq": seq, "source_kind": kind}

    if kind == "run_started":
        return {**base}
    if kind == "graph_patched":
        return {**base, "delta": {"op": "graph_patched", "reason": payload.get("reason", ""),
                                  "trigger": payload.get("trigger_event")}}
    if kind == "task_started":
        return {**base, "stepName": node}
    if kind == "task_succeeded":
        # Two AG-UI meanings: the step finished, and the data model gained the
        # node's result. We fold the STATE_DELTA into the same event so the
        # client patches its data model at /results/<node>.
        return {**base, "stepName": node, "delta": {"op": "add", "path": f"/results/{node}", "value": payload}}
    if kind == "task_failed":
        return {**base, "stepName": node, "error": payload.get("error", "task failed")}
    if kind == "task_cancelled":
        return {**base, "custom": "step_cancelled", "stepName": node}
    if kind == "run_resumed":
        return {**base, "custom": "run_resumed"}
    return base


def stream_agui(events: Iterable[dict], *, finished: bool) -> Iterator[dict]:
    """Yield AG-UI events for a whole journal, then a derived RUN_FINISHED."""
    last_seq = 0
    for ev in events:
        last_seq = ev["sequence"]
        yield to_agui_event(ev)
    if finished:
        yield {"type": "RUN_FINISHED", "seq": last_seq + 1, "source_kind": "derived"}
