# S14Code

`S14Code` is the Session 14 layer: it gives the agent a **face**. It turns an
agent outcome into a declarative A2UI-style surface, streams the S13 graph
journal to a browser as AG-UI events, and carries user actions back as
validated events. It renders none of the model's text as code.

The load-bearing claim of the session, enforced by [`s14code/validator.py`](s14code/validator.py):

> A surface is **declarative data**, checked against a catalog the client
> already trusts. Three invariants hold:
> - **catalog** — every component `type` is in the trusted catalog;
> - **data-not-code** — no property is ever evaluated as script, markup, or a URL;
> - **event** — the surface changes the world only by emitting a registered action.

`S14Code` holds **no provider credentials**. It reads the graph the agent
already produced and calls no model directly (the generative path routes
through the `glc_v3` gateway, exactly as S13 does).

## What runs where

| Service | Default address | Responsibility |
|---|---|---|
| `glc_v3` | `http://127.0.0.1:8111` | Models, keys, routing (owns every credential) |
| `S13Code` | `http://127.0.0.1:8113` | Live graph, memory, the `compose_surface` skill |
| `S14Code` | `http://127.0.0.1:8115` | Catalog, validator, surface builder, AG-UI stream, render client |

## Requirements

- Python 3.11+, [`uv`](https://docs.astral.sh/uv/)
- A running `glc_v3` (for the generative loop) and `S13Code` (for a live harness run)
- Unzip `glc_v3`, `S13Code`, and `S14Code` beside one another; `S14Code`'s
  harness drivers reference `../../S13/S13Code` the way `S13Proof` references `../S13Code`.

## Install and run

```bash
uv sync
export S13_BASE_URL=http://127.0.0.1:8113   # attach to a running S13Code (optional)
uv run s14code serve                         # http://127.0.0.1:8115
```

Health and the trusted catalog:

```bash
curl http://127.0.0.1:8115/healthz
curl http://127.0.0.1:8115/v1/catalog
```

Open a rendered surface (served by the render client, which executes nothing):

```bash
open http://127.0.0.1:8115/s/harness        # the real harness-composed surface
```

## The generative loop (UI composed by the harness)

The surface is composed by a **skill node inside a real S13 live-graph run**,
not by a standalone prompt. The `compose_surface` skill is an additive,
tagged change to `S13Code/s13code/runtime.py` (grep `# --- S14 additive` and
`# --- S14 outcome-aware`). A real run researches, distills, and then composes
the A2UI surface via Gemini; the validator checks the model's own output.

```bash
# gateway on 8111 (provider=gemini); Ollama with nomic-embed-text for episode embedding
cd ../../S13/S13Code
S13_GATEWAY_PROVIDER=gemini GLC_BASE_URL=http://127.0.0.1:8111 \
  uv run python ../../S14/S14Code/proofs/harness_run.py          # -> proofs/harness_run.json

# the outcome-aware planner: weak evidence earns a corrective node before compose
S14_SELFCORRECT_CITY=Berlin GLC_BASE_URL=http://127.0.0.1:8111 \
  uv run python ../../S14/S14Code/proofs/harness_selfcorrect.py  # -> proofs/harness_selfcorrect.json
```

## Proofs

Everything the Session 14 widgets replay is real captured output under `proofs/`:

| File | Produced by | Shows |
|---|---|---|
| `proof.json` | `run_surface_proof.py` | injection wall (4 rejections), HITL, catalog/validator |
| `harness_run.json` | `harness_run.py` | a real live-graph run → Gemini composes a 19-component surface |
| `harness_selfcorrect.json` | `harness_selfcorrect.py` | the planner catches weak Berlin evidence and re-researches |
| `generated_surface.json` | `generate_live.py` | a local model's output caught by the validator (`Flatters`) |
| `gemini_surface.json` | `generate_gemini.py` | Gemini's raw output via the gateway |

```bash
uv run python proofs/run_surface_proof.py    # writes proof.json, prints the table
uv run pytest -q                             # the three invariants, 8 tests
```

## Layout

```
s14code/         catalog, validator, surface builder, agui mapper, hitl, agent, render fixtures
client/          the render client (maps catalog types to DOM; executes nothing)
proofs/          drivers + captured proof JSON the widgets replay
tests/           invariant tests
```

## Sharing / security

- `S14Code` contains no secrets. It never reads `.env` and holds no credentials.
- `.venv/`, `__pycache__/`, and any `.env` are git-ignored.
- The `compose_surface` and outcome-aware changes to `S13Code` are additive and
  reversible; they belong as a pull request against `S13Code`, not in this repo.
