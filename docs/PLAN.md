# Technical Plan — Rogaine Route Planner

## Recap
Raster map in, scored route out. Five stages: normalise and calibrate, classify terrain from the
ISOM palette, detect controls, turn terrain into a per-pixel travel-time field and an all-pairs
travel matrix, then solve the Orienteering Problem. Shipped as a Typer CLI plus a FastAPI local
viewer. See [SPEC.md](SPEC.md) for requirement IDs (F1-F19) referenced by the tasks.

## Stack
- **Chosen:** Python 3.12 (in Docker) · numpy · opencv-python-headless · scipy (`sparse.csgraph`) ·
  scikit-image · Pillow · pypdfium2 · pydantic v2 · typer + rich · FastAPI + uvicorn ·
  vanilla JS + Canvas 2D for the viewer · pytest + pytest-cov · Playwright · uv for dependency
  management · Tesseract (system package, only for control numbers).
  Optional M7 only: PyTorch 2.12 + transformers (SegFormer MiT-B4), CUDA on the local RTX 3060 Ti.
- **Alternatives considered:**
  - *Neural segmentation first (the article's path).* Rejected as the primary route: ISOM colours are
    a printing standard, so a palette classifier is near-exact on renders and scans, needs no dataset,
    and runs on CPU in seconds. The network's real value is robustness to photos — it becomes M7,
    trained on masks this classifier generates for free.
  - *A\* per control pair (the article's path).* Rejected for the matrix: N+1 Dijkstra sweeps give
    every pair at once, versus N²/2 A\* runs. A\* is kept for the viewer's single-pair queries.
  - *Held-Karp alone.* Kept, but as the exact oracle and the small-instance solver only; 2^N state
    makes it unusable at the 30-80 controls this user actually runs.
  - *React + Vite viewer.* Rejected: a node toolchain for one canvas page. Vanilla JS keeps the whole
    product a single `pip install` and one process.
  - *EasyOCR / a VLM for numbers.* Rejected: torch or a paid API for two digits, when OCR is
    explicitly non-load-bearing and hand-editable.
  - *Python 3.14 on the host.* Rejected as the run target: it is two minor versions ahead of most CV
    wheels. Docker pins 3.12; host use stays best-effort.

## Architecture

```mermaid
flowchart LR
  raster[Map raster<br/>PNG/JPG/PDF] --> norm[normalize<br/>white balance]
  norm --> seg[palette classifier<br/>Lab nearest colour]
  norm --> det[control detector<br/>HSV + Hough + OCR]
  seg --> lin[linear features<br/>roads / paths]
  seg --> cont[contour density<br/>slope proxy]
  lin --> cost[cost field<br/>seconds per pixel]
  cont --> cost
  scale[scale / DPI<br/>or calibration] --> cost
  speed[runner speed] --> cost
  cost --> graph[8-connected grid graph]
  det --> travel
  graph --> travel[multi-source Dijkstra<br/>travel matrix + polylines]
  travel --> solve{solver}
  solve -->|N<=15| exact[Held-Karp]
  solve -->|30-80| heur[GRASP + local search]
  exact --> out[route.json + route.png]
  heur --> out
  out --> cli[CLI]
  out --> web[FastAPI viewer]
```

## Data / content model
Defined once in `src/rogaine/models.py` (pydantic v2) during M0 and frozen — it is the contract the
three parallel workstreams code against:
`TerrainClass`, `MapContext`, `Control`, `TerrainMap`, `CostField`, `TravelMatrix`, `Route`, `Leg`,
`RunConfig`. Terrain coefficients and every other tunable live in `config/default.toml`, loaded into
pydantic models, overridable by `--config` and by individual CLI flags (F18).

## Security
- No network access at runtime; the optional training milestone is the only thing that downloads
  weights, and it is a separate entry point.
- The viewer binds `127.0.0.1` only, never `0.0.0.0`.
- Uploads are written under `runs/<uuid>/` with a server-generated name; the original filename is
  never used as a path. Content type and magic bytes are checked, size is capped.
- No `shell=True`, no user string ever reaches a subprocess.
- Route JSON and CSV are parsed with strict schemas, not `eval`.

## Repository map
```text
/
  pyproject.toml            uv-managed deps, ruff + pytest config
  Dockerfile                python:3.12-slim + tesseract + opencv runtime libs
  docker-compose.yml        services: app (viewer, port 8000), tests, train (GPU, optional)
  config/default.toml       terrain coefficients, detector params, solver budgets
  src/rogaine/
    models.py               pydantic contract (frozen after M0)
    config.py               TOML loading, overrides, ISOM terrain table
    io/raster.py            PNG/JPG/BMP/TIFF/PDF -> MapContext           (F1)
    io/controls_csv.py      CSV round-trip                               (F9)
    io/scale.py             1:N + DPI, two-point calibration             (F2, F3)
    vision/normalize.py     white balance, illumination flattening
    vision/palette.py       ISOM colour table, Lab nearest-colour classify (F4)
    vision/linear.py        roads/tracks/paths as connected corridors     (F5)
    vision/contours.py      contour mask -> density -> slope factor       (F6)
    vision/segment.py       orchestrates the above -> TerrainMap
    vision/controls.py      purple mask, Hough circles, start marker      (F7)
    vision/ocr.py           digit reading, confidence, fallbacks          (F8)
    cost/field.py           TerrainMap + speed -> CostField               (F10)
    cost/graph.py           CostField -> scipy CSR grid graph
    cost/travel.py          multi-source Dijkstra -> TravelMatrix + paths (F11)
    solve/objective.py      score, penalty, feasibility                   (F14)
    solve/exact.py          Held-Karp over subsets                        (F12)
    solve/heuristic.py      GRASP construction + 2-opt/or-opt/swap        (F13)
    solve/alternatives.py   top-K distinct routes                         (F16)
    render/preview.py       terrain preview PNG
    render/overlay.py       route over map PNG                            (F15)
    cli.py                  typer: segment, detect, plan, bench, serve
    web/app.py              FastAPI endpoints                             (F17)
    web/static/             index.html, app.js, style.css (Canvas 2D)
  tests/
    fixtures/synth_map.py   synthetic ISOM map generator + ground truth
    fixtures/*.py           small hand-built travel matrices
    unit/                   per-module tests
    e2e/test_cli.py         fixture map -> route.json golden
    e2e/test_viewer.py      Playwright full flow
  ml/                       optional M7: dataset.py, train.py, infer.py
  runs/                     gitignored working directories
  docs/
```

## Milestones

| M | Name | Requirements | Depends on |
|---|------|--------------|------------|
| M0 | Scaffold, contract, synthetic fixture | F18, F19 | — |
| M1 | Terrain segmentation | F1-F6 | M0 |
| M2 | Control detection | F7-F9 | M0 |
| M3 | Cost field and travel matrix | F10, F11 | M0 (fixture), M1 for real input |
| M4 | Solvers and bench | F12-F14, F16 | M0 (matrix contract) |
| M5 | CLI end-to-end and renders | F15, F19 | M1-M4 |
| M6 | Web viewer | F17 | M5 |
| M7 | *(optional, post-acceptance)* SegFormer for photos | — | M1 |

**Parallel workstreams after M0** (no shared files):
- **WS-A vision** — owns `src/rogaine/vision/**`, `src/rogaine/io/**` → M1, M2
- **WS-B routing** — owns `src/rogaine/cost/**`, `src/rogaine/solve/**` → M3, M4, developed against
  the fixture generator's synthetic terrain and hand-built matrices, never blocked on WS-A
- **WS-C delivery** — owns `src/rogaine/render/**`, `src/rogaine/web/**`, `src/rogaine/cli.py` → M5,
  M6, developed against recorded fixture `Route` JSON

## Test strategy
- **Synthetic fixture first.** `tests/fixtures/synth_map.py` renders an ISOM-coloured map with known
  polygons, paths, contours and purple circles, and returns exact ground truth. Every vision
  requirement is measured against it (IoU, recall, precision, centre error), not eyeballed.
- **Oracles for the solvers.** Brute force agrees with Held-Karp for N<=9; Held-Karp bounds the
  heuristic's gap for N<=15. The gap is a printed number in `bench`, and a test asserts it stays
  within F13.
- **Golden end-to-end.** Fixture map through the whole CLI produces a `route.json` compared against a
  stored golden with numeric tolerance; also the F19 determinism check (same seed, byte-identical).
- **Playwright** drives the viewer's full flow (upload, calibrate, edit a control, run, export).
- **Performance guards** measure the NFR budgets on a full-size synthetic map and fail loudly on
  regression rather than silently getting slower.
- Everything runs as `docker compose run --rm tests`. Never pipe the run through `tail` in Bash — the
  pipe's exit code masks a red suite.

## Local run / env
```bash
docker compose run --rm tests                    # suite
docker compose run --rm app plan --map ... ...   # CLI
docker compose up app                            # viewer on http://127.0.0.1:8000
docker compose run --rm train ...                # M7 only, needs GPU runtime
```
Host Python 3.14 is best-effort; Docker (3.12) is the supported path. Inference is CPU-only
throughout; the GPU is used only by M7.

## Deploy notes
None. Local tool, no hosting, no accounts, no telemetry.

## Risks
1. Palette classification on photos — mitigated by normalisation now, M7 later. (SPEC risk 1)
2. Text and symbols polluting classes — size/elongation filters plus `unknown` infill. (SPEC risk 2)
3. Contour density is direction-blind — accepted, stated in output. (SPEC risk 3)
4. All-pairs Dijkstra cost at full resolution — mitigated by a configurable `graph_downsample`
   (default 4, giving ~750k nodes on a 4000x3000 map) and by measuring it in the performance guard.
5. Heuristic quality at 60+ controls is unprovable — mitigated by reporting the gap where exact is
   computable and never claiming optimality.
6. No real map fixture yet — synthetic fixture covers CI; the owner's map is the acceptance gate.

## Definition of Done
- Every F-ID in SPEC.md maps to at least one passing test, listed in the handoff.
- `docker compose run --rm tests` green, including Playwright and the performance guards.
- `bench` prints a heuristic-versus-exact gap within F13 on the fixture.
- CLI and viewer both run the owner's own map end to end, and the owner accepts the route.
- README documents install, every CLI command, the config reference, the route JSON schema, and the
  known limitations (no georeferencing, direction-blind slope, OCR is advisory).
- No network calls at runtime; viewer bound to loopback.
