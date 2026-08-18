# Decisions

## Index
| ADR | Title | Status |
|-----|-------|--------|
| 001 | ISOM palette classifier is the primary segmenter; SegFormer is optional | accepted |
| 002 | Multi-source Dijkstra for the travel matrix, not pairwise A* | accepted |
| 003 | Two solvers: exact Held-Karp as oracle, heuristic for real sizes | accepted |
| 004 | Docker + Python 3.12 is the supported runtime; host 3.14 is best-effort | accepted |
| 005 | Vanilla JS + Canvas viewer, no node toolchain | accepted |
| 006 | Contour density as a slope proxy, no elevation reconstruction | accepted |
| 007 | No georeferencing or GPX in v1 | accepted |
| 008 | `models.py` is a frozen contract after M0 | accepted |
| 009 | Tesseract OCR, explicitly non-load-bearing | accepted |
| 010 | Real map corpus validates; synthetic fixture tests; neither is committed | accepted |

---

## ADR-001 — ISOM palette classifier is the primary segmenter; SegFormer is optional
- Date: 2026-08-18
- Status: accepted
- Context: The article trains SegFormer MiT-B4 on ~200 OCAD maps. This project has a handful of
  rasters and a few `.ocd` files — nowhere near that dataset. ISOM is a printing specification, so
  the colours on a rendered or scanned map are standardised, not learned.
- Decision: Classify terrain by nearest ISOM colour in CIELAB with an `unknown` fallback. Keep
  SegFormer as milestone M7, trained on masks this classifier generates, and only after the owner
  accepts the route quality.
- Consequences: No dataset, no GPU and no training time before the first useful route; near-exact
  masks on renders and scans. Weak on phone photos, which is exactly what M7 addresses. Adds a
  dependency on the ISOM colour table being correct — sourced from IOF Appendix 1 and cited in
  `config/default.toml`.

## ADR-002 — Multi-source Dijkstra for the travel matrix, not pairwise A*
- Date: 2026-08-18
- Status: accepted
- Context: The route needs travel time between every pair of controls. The article runs A* per pair.
  At 60 controls that is 1830 searches over a multi-million-node grid.
- Decision: Run one Dijkstra sweep per control (61 sweeps) over the CSR grid graph via
  `scipy.sparse.csgraph`, reading every pair off the resulting distance rows. Keep A* only for the
  viewer's interactive single-pair queries.
- Consequences: Roughly 30x fewer searches and C-speed execution. Each sweep explores the whole map
  rather than stopping early, and predecessor arrays cost memory, so `graph_downsample` (default 4)
  is a first-class config knob with a performance guard on it.

## ADR-003 — Two solvers: exact Held-Karp as oracle, heuristic for real sizes
- Date: 2026-08-18
- Status: accepted
- Context: Held-Karp is exact but 2^N in state; the owner's maps carry 30-80 controls. Reporting a
  heuristic route with no quality evidence would fail the acceptance bar ("не хуже качеством").
- Decision: Ship both. Held-Karp solves and proves optimality up to a configured cap (N<=15) and
  serves as the test oracle; a seeded GRASP + local search handles real instances. `bench` prints
  the measured gap.
- Consequences: More code and a second correctness surface, bought back as verifiable quality. The
  product never claims optimality at 60 controls — it reports the objective and the measured gap
  where the exact answer is computable.

## ADR-004 — Docker + Python 3.12 is the supported runtime; host 3.14 is best-effort
- Date: 2026-08-18
- Status: accepted
- Context: The host runs Python 3.14.3, ahead of most CV wheel matrices. `CLAUDE.md` already requires
  `docker compose run --rm tests` because pytest hangs on this Windows host.
- Decision: One image, `python:3.12-slim` plus tesseract and the opencv runtime libraries, shared by
  the `app` and `tests` services. Host installation is documented but unsupported.
- Consequences: Reproducible runs and a working test path; the viewer needs a published port, and
  file paths cross the container boundary, which the CLI must handle.

## ADR-005 — Vanilla JS + Canvas viewer, no node toolchain
- Date: 2026-08-18
- Status: accepted
- Context: The viewer is one page: a zoomable map canvas, draggable markers, a parameter panel, a
  results table.
- Decision: FastAPI serves static HTML/CSS/JS drawing on Canvas 2D. No React, no bundler, no
  `node_modules`.
- Consequences: The whole product stays a single Python install and one process, and Playwright can
  drive it directly. Complex UI state is hand-rolled; if the viewer grows well past this scope, this
  ADR gets superseded rather than stretched.

## ADR-006 — Contour density as a slope proxy, no elevation reconstruction
- Date: 2026-08-18
- Status: accepted
- Context: The article penalises contour crossings. Reconstructing a DEM from contour lines needs
  line tracing, height assignment and interpolation — a project of its own, and fragile on a raster
  where contours are broken by symbols and text.
- Decision: Extract the brown contour mask, blur it into a local density field, and derive a
  multiplicative slope penalty from it.
- Consequences: Cheap, robust, and close to the reference behaviour. It cannot distinguish uphill
  from downhill, so a leg costs the same in both directions — stated in the output and in the README
  rather than hidden.

## ADR-007 — No georeferencing or GPX in v1
- Date: 2026-08-18
- Status: accepted
- Context: The owner explicitly declined GPX export; the route is consumed as a picture and a table.
- Decision: Everything stays in map pixel coordinates. No world files, no GeoTIFF, no GPX.
- Consequences: Removes an entire coordinate-transform surface from v1. Adding it later means a
  two-point affine calibration and a GPX writer, additive rather than structural.

## ADR-008 — `models.py` is a frozen contract after M0
- Date: 2026-08-18
- Status: accepted
- Context: Three workstreams (vision, routing, delivery) run in parallel after M0 and must not block
  on each other or edit the same files.
- Decision: All shared types live in `src/rogaine/models.py`, defined in M0 and frozen. Changing them
  afterwards requires a new ADR and a coordinated update.
- Consequences: Routing develops against synthetic terrain and hand-built matrices while vision is
  still in progress; delivery develops against recorded fixture JSON. The cost is that a modelling
  mistake in M0 is expensive to correct later.

## ADR-009 — Tesseract OCR, explicitly non-load-bearing
- Date: 2026-08-18
- Status: accepted
- Context: Control numbers give the points under the common rogaine convention (first digit = value).
  Reading two digits from a map is the most fragile step in the pipeline. EasyOCR pulls in torch; a
  VLM costs money and determinism.
- Decision: Tesseract from the Docker image, with a confidence per control. Unread numbers produce
  `points: null` plus a flag; the points rule can fall back to a constant, and CSV or viewer editing
  is a designed flow, not a repair hatch.
- Consequences: A system dependency in the image, and OCR quality never gates a route. If Tesseract
  proves too weak on map typography, a small digit-template matcher replaces it without touching any
  other module.

## ADR-010 — Real map corpus validates; synthetic fixture tests; neither is committed
- Date: 2026-08-19
- Status: accepted
- Context: The owner can supply 200+ scanned maps and a couple of `.ocd` files. Tests need exact
  ground truth and must run anywhere; real scans have no labels but carry the real distribution of
  map styles, printers and scanner colour shifts.
- Decision: Split the two roles. The synthetic generator (T004) stays the test fixture — exact
  labels, deterministic, in-repo, small. The real corpus (T005) is a validation set living in a
  gitignored `data/maps/`, driving T017's palette report and, later, M7's training data. A `.ocd`
  render spike (T006) may add a third, best-of-both artefact: a real map with symbol-exact masks.
  Sizing: 10-20 scans retire the palette risk; the full 200+ are for M7 only.
- Consequences: CI stays fast and self-contained, while the claim "this works on real maps" rests on
  real maps. The corpus is never committed, so results referencing it must be reproducible from the
  report artefacts rather than from the repo. If T006 succeeds, some synthetic-fixture assertions get
  a stronger real counterpart; T004 is not removed either way.
