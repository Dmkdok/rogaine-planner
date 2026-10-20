# rogaine-planner

A local, offline tool that turns a rogaine (score-orienteering) map raster into a scored route
plan. It classifies terrain from ISOM colours, finds the purple/red control circles, builds a
per-pixel travel-time field for a given runner speed, computes exact travel times between all
controls, and solves the Orienteering Problem (maximise points inside a time limit, start = finish,
points lost per minute late). Ships as a Python CLI (`rogaine`) plus a local web viewer.

Full requirements and design: [docs/SPEC.md](docs/SPEC.md), [docs/PLAN.md](docs/PLAN.md),
[docs/DECISIONS.md](docs/DECISIONS.md).

## Install

Docker is the only supported runtime (ADR-004) — the image pins Python 3.12 and bundles
`tesseract-ocr` and the OpenCV/scipy native libs. A host install works but is best-effort.

```bash
docker compose build
```

This builds two images from the one `Dockerfile`: `rogaine-planner:base` (the product, `app`
service) and `rogaine-planner:test` (adds pytest/ruff/Playwright, `tests` service).

### Host install (best-effort)

```bash
pip install -e ".[dev]"
```

Requires Python >=3.12 and a system `tesseract-ocr` binary on `PATH` for control-number OCR
(`pytesseract` only calls out to it, it does not bundle it). On Windows, `pytest` itself hangs —
always run the suite through `docker compose run --rm tests` regardless of host OS.

## Quick start

```bash
docker compose run --rm app rogaine plan \
  --map data/maps/example/map.png --scale 10000 --dpi 300 \
  --limit 4h --speed 2.0 --out-dir out
```

Writes `out/route.json` and `out/route.png`, and prints a leg-by-leg summary plus top-K
alternatives to the terminal. `docker compose run --rm app` overrides the `app` service's default
command (`rogaine serve`, see [Web viewer](#web-viewer)), so any `rogaine …` invocation works the
same way. The whole repo is bind-mounted (`./:/app`), so paths under `data/`, `config/` and any
`--out-dir` you choose are the same on the host and in the container.

## CLI commands

Every command accepts `--config <path>` (or `$ROGAINE_CONFIG`) to override
[`config/default.toml`](config/default.toml) — see [Config reference](#config-reference).

### `rogaine segment`

Classify a map raster into the ISOM terrain classes; writes `terrain.npz` (labels + contour
density) and `terrain_preview.png`.

| Flag | Default | Meaning |
|---|---|---|
| `--map` | *(required)* | Map raster or PDF. |
| `--dpi` | probed from file / config | Scan resolution. |
| `--scale` | — | Map scale denominator `N` in `1:N`; combined with `--dpi` (SPEC F2). |
| `--calibrate` | — | `x1,y1,x2,y2,meters` two-point calibration instead of `--scale` (SPEC F3). |
| `--page` | `0` | PDF page, 0-based; ignored for other formats. |
| `--out-dir` | `.` | Where `terrain.npz`/`terrain_preview.png` land. |

Exactly one of `--scale`/`--calibrate` is required.

### `rogaine detect`

Detect the hub and control circles, OCR their numbers, write an editable controls CSV.

| Flag | Default | Meaning |
|---|---|---|
| `--map` | *(required)* | Map raster or PDF. |
| `--dpi` | probed from file / config | Scan resolution. |
| `--out` | `controls.csv` | Output CSV path (format below). |

Exits 1 if no hub (start/finish) circle is found. Unreadable control numbers are written with
blank `points` and printed as flagged warnings, never guessed (SPEC F8, ADR-009).

### `rogaine plan`

Full pipeline: resolve controls (detect, or `--controls` to skip straight to a hand-edited CSV),
build the cost field and travel matrix, solve, print the route and alternatives, write
`route.json` + `route.png`.

| Flag | Default | Meaning |
|---|---|---|
| `--map` | *(required)* | Map raster or PDF. |
| `--dpi` | probed from file / config | Scan resolution. |
| `--scale` / `--calibrate` | — | Same as `segment`; exactly one required. |
| `--controls` | — | Hand-edited `controls.csv`; skips detection entirely (SPEC F9). |
| `--speed` | `2.0` | Runner base (road) speed, m/s. |
| `--limit` | `4h` | Time budget: `4h`, `2h30m`, `90s`, or a bare number of seconds. |
| `--penalty-per-min` | `1.0` | Score penalty per minute over the limit. |
| `--strategy` | `auto` | `auto` \| `exact` \| `heuristic`. `auto` picks exact under `exact_max_controls`. |
| `--heuristic-time-budget` | `30.0` | Heuristic solver time budget, seconds. |
| `--alternatives` | `3` | Top-K structurally distinct alternative routes (max 20). |
| `--seed` | `0` | Seeds the heuristic solver and alternatives search (deterministic, SPEC F19). |
| `--out-dir` | `.` | Where `route.json`/`route.png` land. |

Exits 1, writing nothing, if no hub is found or no candidate control is reachable within the time
limit — only a successfully solved route reaches disk.

### `rogaine bench`

Solver honesty check: runs exact and heuristic on the same small synthetic instance, prints the
heuristic-vs-exact score gap (SPEC F13 bar: ≤5%). Always exits 0 — it reports, it never gates.

| Flag | Default | Meaning |
|---|---|---|
| `--n-candidates` | `10` | Candidate controls in the synthetic instance (hub excluded). Capped at `config.solver.exact_max_controls`. |
| `--seed` | `0` | Seeds instance generation and the heuristic RNG. |
| `--time-budget` | `2.0` | Heuristic solver time budget, seconds. |

### `rogaine serve`

Launches the FastAPI web viewer backend (uvicorn).

| Flag | Default | Meaning |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address. Never `0.0.0.0` on the host directly — the `app` service binds `0.0.0.0` only because that's the only address reachable from inside the container, and `docker-compose.yml` publishes it back out on `127.0.0.1:8001` only. |
| `--port` | `8000` | Bind port. |

### `rogaine corpus list` / `rogaine corpus check <id>`

Inspect `data/maps/` — see [data/README.md](data/README.md) for the corpus layout (`meta.toml`,
`controls.csv`, `reference.json`). `list` never fails on an incomplete map, it reports what's
missing; `check <id>` exits 1 if that one map isn't plannable. Both take `--root` (default
`data/maps`).

### Global

`--version` prints the version and exits. `rogaine` with no subcommand prints help.

## Web viewer

```bash
docker compose up app
```

Open http://localhost:8001. Drop a map file, set scale (1:N + DPI, or drag a calibration line and
type its length in metres), review/edit the detected controls, set time limit/speed/penalty, press
Run, inspect the route over the map with a leg table, export JSON/PNG/CSV.

Each browser session gets a `run_id` (a server-generated UUID); every stage's output persists under
`runs/<run_id>/` on disk so later stages (detect, plan) can re-enter without redoing earlier work,
and so `GET /api/runs/{id}/export/{route.json,route.png,controls.csv}` can serve them back. Jobs
(`segment`/`detect`/`plan`) run as background tasks polled via `GET /api/jobs/{job_id}`; nothing
here is a substitute for the CLI's own `--out-dir` artefacts, it is the same pipeline exposed over
HTTP for the interactive flow (SPEC F17). Uploads are sniffed by magic bytes and capped at 200 MB,
never trusted by client filename or `Content-Type`.

## Config reference

Every tunable lives in one TOML file, [`config/default.toml`](config/default.toml) (SPEC F18) —
extensively commented in place, each section citing where its numbers come from (IOF ISOM 2017-2 /
Appendix 1, or a measurement against a named real scan). Override with `--config my.toml` (a user
file only needs the keys it changes — it's deep-merged over the shipped default) or `$ROGAINE_CONFIG`;
individual CLI flags (`--speed`, `--limit`, `--alternatives`, …) override per run on top of that.
Loading validates that the file covers exactly the terrain contract in `models.py` — a config
missing a terrain class, or carrying an unknown key (every table is `extra="forbid"`), fails fast.

| Section | Governs |
|---|---|
| `[map]` | Fallback DPI when a raster carries none and the user gives none. |
| `[palette]` / `[palette.ink]` / `[[palette.shade]]` | CIELAB classification threshold, unknown-fill radius, the six ISOM process inks (CMYK) and every printed shade (ink + tint %) derived from them. |
| `[[terrain]]` (17 entries) | One row per `TerrainClass`: ISOM symbol code, printed shade, `speed_factor` (fraction of road speed), `passable`. |
| `[grid]` | Shape thresholds that keep grid/magnetic-north/border lines from misclassifying as water (ADR-012, SPEC F20). |
| `[linear]` | Nominal printed widths (road/track/footpath) and shape filters (elongation, aspect ratio, minimum length) that split the shared black-ink `road` placeholder into the three linear classes. |
| `[slope]` | Contour-density blur sigma and the speed penalty it drives (a slope *proxy*, not elevation — ADR-006). |
| `[detector]` | Control-circle geometry and tolerance, ink hue bands (`ink_hue_ranges` for purple, `red_hue_ranges` with its own tighter saturation/value/channel-gap floor for red, ADR-011/ADR-018), Hough parameters, the scale multipliers swept for oversized hand-drawn circles (ADR-015), control-number OCR search window and points rule (`first_digit` / `constant` / `csv`). |
| `[graph]` | Grid downsampling factor and the impassable-terrain cost multiplier. |
| `[solver]` | Solver strategy/dispatch cap, heuristic time budget and GRASP parameters, seed, alternatives count. |
| `[rules]` | Default points penalty per minute late. |

## Route JSON schema

`route.json` (written by `plan`/the viewer's `plan` job, schema in
[`src/rogaine/io/route_json.py`](src/rogaine/io/route_json.py)):

```json
{
  "schema_version": 1,
  "order": [0, 3, 0],
  "legs": [
    {
      "from_id": 0, "to_id": 3,
      "seconds": 612.4, "meters": 1180.0,
      "polyline": [[1600, 1200], [1580, 1150]],
      "cumulative_seconds": 612.4
    },
    {
      "from_id": 3, "to_id": 0,
      "seconds": 598.1, "meters": 1150.0,
      "polyline": [[1580, 1150], [1600, 1200]],
      "cumulative_seconds": 1210.5
    }
  ],
  "total_seconds": 13920.0,
  "total_meters": 26400.0,
  "points": 38,
  "penalty": 0.0,
  "score": 38.0,
  "solver": "exact",
  "optimal": true,
  "seed": 0,
  "run_config": {
    "base_speed_mps": 2.0, "time_limit_s": 14400.0, "penalty_per_min": 1.0,
    "strategy": "auto", "heuristic_time_budget_s": 30.0, "alternatives": 3, "seed": 0
  }
}
```

- `order` — control ids in visit order; always starts and ends at the hub.
- `legs` — one entry per consecutive pair in `order`; `polyline` is pixel `(x, y)` points along the
  actual walked path; `cumulative_seconds` is elapsed time from the hub through the end of that leg.
- `solver` — `"exact"` (Held-Karp, proven optimal up to `exact_max_controls`) or `"heuristic"`
  (GRASP + local search); `optimal` is only ever `true` for the former (ADR-003).
- `run_config` — the exact `RunConfig` that produced this route (speed, limit, penalty, strategy,
  seed), embedded so a `route.json` is self-describing.
- `schema_version` — bump point for future incompatible changes to this shape; currently `1`.

`route.png` is the same route drawn over the source map, numbered controls matching the JSON.

Controls import/export as a CSV (`id,x,y,number,points,confidence,source,is_hub`) — round-trips
losslessly; format and hand-editing rules in [data/README.md](data/README.md).

## Known limitations

- **OCR is never load-bearing.** Tesseract reads control numbers best-effort; an unreadable number
  gets `points: null` and a flagged warning rather than a guess. The points rule (`first_digit` by
  default) or a hand-edited controls CSV are the reliable paths (ADR-009).
- **Contour density is a slope proxy, not real elevation.** It cannot tell uphill from downhill, so
  route direction never changes cost (ADR-006).
- **Grid/border-line and control-ink handling is tuned against a small set of real scans**, not a
  general solution: the shape/hue heuristics (`[grid]`, `[detector].ink_hue_ranges`, ADR-011,
  ADR-012) carry the measurements they were fitted to in `config/default.toml`'s own comments, and
  may need retuning on a very different printer/scanner combination.
- **Heuristic optimality is unverifiable above `exact_max_controls` (15).** `bench` reports the
  measured gap wherever the exact solver is computable; the product never claims optimality at
  30-80 controls, only the objective and, where available, the gap.
- **Palette classification assumes a render or scan, not a phone photo.** White-balance and
  illumination normalisation help but are not a substitute for controlled lighting; the optional
  SegFormer milestone (M7, not built by default — see `docs/TASKS.md`) exists precisely for this
  case, trained on palette-generated masks, but is not part of the shipped CLI/viewer path.
- **No GPS georeferencing, GPX/GeoTIFF export, or automatic scale-bar detection.** Scale is always
  user-supplied (`--scale`+`--dpi` or `--calibrate`).
- **No VLM-based control detection** (the reference article's Yandex Cloud Qwen path) — detection is
  classical CV (Hough circles + colour/shape filters) end to end.
- **No fatigue or time-varying speed modelling** — one `base_speed_mps` scales every terrain class
  for the whole route.
- **`.ocd` (OCAD) binary vector geometry is not parsed.** Only rasters rendered from OCAD (or any
  other source) are supported as map input.
- **Single-user, single-process, no persistence beyond local run directories.** The viewer's job
  registry is in-memory (lost on restart); `runs/<uuid>/` on disk is what survives.

## Development

```bash
docker compose run --rm tests            # full suite (pytest hangs on Windows host — always use this)
docker compose run --rm tests ruff check .
docker compose run --rm tests pytest -m "not perf and not corpus"   # skip slow/owner-corpus-only tests
```

Test markers (`pyproject.toml`): `perf` (slow performance-budget guards), `e2e` (CLI/Playwright
end-to-end flows), `corpus` (needs the owner's real map corpus under `data/maps`, ADR-010).

Project docs: [docs/SPEC.md](docs/SPEC.md) (requirements), [docs/PLAN.md](docs/PLAN.md)
(architecture/file map), [docs/TASKS.md](docs/TASKS.md) (open work), [docs/DECISIONS.md](docs/DECISIONS.md)
(ADRs), [docs/STATUS.md](docs/STATUS.md) (session handoff).
