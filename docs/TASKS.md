# Tasks

Requirement IDs (F1-F19) refer to [SPEC.md](SPEC.md). Workstreams (WS-A vision, WS-B routing,
WS-C delivery) and owned paths come from [PLAN.md](PLAN.md) — no two open tasks share a path.

## M0 — Scaffold, contract, synthetic fixture

- [x] T001 — Repo scaffold and toolchain — paths: `pyproject.toml`, `Dockerfile`,
  `docker-compose.yml`, `.gitignore`, `.dockerignore` — deps: none —
  DoD: `docker compose run --rm tests` runs pytest and exits 0 on an empty suite; image contains
  tesseract and opencv runtime libs; `app` and `tests` services share one image.
  Landed: ruff configured in `pyproject.toml` rather than a separate `ruff.toml`, so the
  toolchain lives in one file. Verified: `ruff check` clean, 87 tests pass, `tesseract 5.5.0`
  and `cv2 5.0.0` present, `docker compose run --rm app` prints the CLI help.
- [x] T002 — Frozen data contract — paths: `src/rogaine/models.py` — deps: T001 —
  DoD: pydantic v2 models for `TerrainClass`, `MapContext`, `Control`, `TerrainMap`, `CostField`,
  `TravelMatrix`, `Leg`, `Route`, `RunConfig`; every field typed and documented; a round-trip test
  serialises and reloads each model. **Changes after M0 require an ADR** — three workstreams build
  on it.
- [x] T003 — Config system and ISOM terrain table — paths: `config/default.toml`,
  `src/rogaine/config.py` — deps: T002 — DoD: TOML loads into pydantic; terrain table carries
  `isom_code`, `color_rgb`, `speed_factor`, `passable` for all 17 classes; CMYK values sourced from
  the IOF ISOM 2017-2 Appendix 1 (colour definitions) and cited in the file; `--config` override and
  per-flag override both tested (F18).
- [x] T004 — Synthetic ISOM map fixture generator — paths: `tests/fixtures/synth_map.py` — deps:
  T003 — DoD: renders a map at a requested size with known terrain polygons, path/road polylines,
  contour lines and purple control circles; returns per-pixel ground-truth labels, control
  coordinates, numbers and the true scale; deterministic under a seed; a "full size" 4000x3000 preset
  exists for the performance guards.
- [x] T005 — Real map corpus intake — paths: `data/README.md`, `.gitignore` — deps: T001 —
  DoD: `data/maps/` layout documented (raster, its scale and DPI, optional controls CSV, optional
  reference route); the directory is gitignored so no map is ever committed; a loader lists the
  corpus and reports what metadata each entry is missing.
  Landed: loader in `src/rogaine/io/corpus.py`, surfaced as `rogaine corpus list` /
  `rogaine corpus check` in `src/rogaine/cli.py` — a minimal app that T050 (WS-C) extends
  rather than replaces. Owner supplies 10-20 scans covering the
  map styles they actually meet (ADR-010).
  **2026-08-25: 13 scans + 1 `.ocd` landed** under `data/maps/<slug>/map.*` (14 directories, ids
  transliterated from the owner's filenames). `rogaine corpus list` confirms all 14 are read;
  none is plannable yet — every one is missing `meta.toml` (scale + DPI). Owner has not supplied
  scale/DPI, a controls list, or a reference route for any of them; still blocking T017's
  per-map validation and any real (non-fixture) `plan` run.
- [ ] T006 — Spike: `.ocd` to raster plus ground-truth mask — paths: `tools/ocd_render.md`,
  `tools/ocd_render.py` — deps: T003 — DoD: a documented route from the owner's `.ocd` files to
  (a) a rendered raster at a known DPI and (b) per-symbol-class masks, using OCAD itself or
  OpenOrienteering Mapper's command-line export. Timeboxed: if neither exports usably, record the
  finding in the spike doc and fall back to T004 alone — this task never blocks M1.
  **Reopened 2026-08-25:** `data/maps/rfar2016-for-stroganov/map.ocd` has arrived. Not executed
  yet — OpenOrienteering Mapper is a host-installed GUI/CLI tool (`docs/STATUS.md` "Blocked on the
  owner"), not available inside this environment. Run `tools/ocd_render.py` on a host with Mapper
  installed and record the outcome in `tools/ocd_render.md`'s Findings section. Still never blocks
  M1 — T004's synthetic fixture carries it.

## M1 — Terrain segmentation (WS-A)

- [x] T010 — Raster loading — paths: `src/rogaine/io/raster.py` — deps: T002 —
  DoD: PNG/JPG/BMP/TIFF and PDF (via pypdfium2, `--page`) load to identical RGB arrays within 1 LSB;
  corrupt and oversized files fail with a clear error, not a traceback (F1).
  Landed 2026-08-25: PNG/BMP/TIFF round-trip exactly; JPEG/PDF within a documented relaxed
  tolerance (lossy by nature). `MAX_DECODED_PIXELS = 150_000_000` (>5x the largest real corpus
  file). `resolve_dpi`/`probe_dpi` implement the F1/F2 DPI fallback: user → embedded metadata →
  `config/default.toml [map].default_dpi`. 19 tests.
- [x] T011 — Scale and calibration — paths: `src/rogaine/io/scale.py` — deps: T002 —
  DoD: `mpp = (25.4/dpi) * N / 1000` exact to 1e-6; two-point calibration agrees within 1% on the
  fixture's known scale; invalid inputs (zero DPI, coincident points) rejected (F2, F3).
  Landed 2026-08-25 as `mpp_from_dpi` + `Calibration`. `io/corpus.py`'s `Calibration` now imports
  from here instead of duplicating the formula — single implementation. 10 tests.
- [x] T012 — Normalisation — paths: `src/rogaine/vision/normalize.py` — deps: T010 —
  DoD: grey-world white balance plus illumination flattening; a synthetically tinted and vignetted
  fixture classifies at least as well as the clean one.
  Landed 2026-08-25. Found and fixed a real bug along the way: the grey-world/illumination
  `.mean()` reductions ran in float32 over ~2M-pixel arrays, losing precision on the same order as
  the correction itself; switched to float64. 5 tests.

**2026-08-25 verification:** `docker compose run --rm tests` — 121 passed, exit 0 (87 baseline +
34 new). `ruff check .` clean. Independently re-run and confirmed by the parent session, not just
the implementer's self-report.
- [x] T013 — ISOM palette classifier — paths: `src/rogaine/vision/palette.py` — deps: T003, T012 —
  DoD: CIELAB nearest-colour with a distance threshold and an `unknown` class; per-class IoU at least
  0.95 for area classes on the fixture; `unknown` filled by neighbourhood majority; runs a 4000x3000
  map in under 30 s on CPU (F4). The nominal shade table is derived from published CMYK, so it sits
  a measurable distance from what any given map actually prints — largest for green. If a fixed
  palette proves brittle across the corpus, **fit it per map** (cluster the map's own dominant
  colours in Lab, assign each cluster to its nearest nominal shade) rather than widening the
  threshold until `unknown` stops meaning anything.
  Landed 2026-08-27. The implementation and its test file existed uncommitted from a prior session
  but had never been run; first real run found three defects, all fixed:
  1. `fill_unknown` filled in one fixed-radius pass, so an `unknown` region wider than
     `2 * unknown_fill_radius` left an unreachable core permanently `unknown` (two tests caught
     this: a 10x10 hole and a border-touching patch). Now iterates the same majority-vote pass to a
     fixed point — see the function's own docstring for why that still terminates.
  2. `tests/fixtures/synth_map.py` drew roads/tracks/footpaths, the start triangle, control circles
     and control numbers with `cv2.LINE_AA` (`putText` antialiases regardless of the flag) straight
     onto the ground-truth image, so edge pixels blended to colours matching no real shade — one,
     by coincidence, landed on the nominal `black_30` (bare_rock) point closely enough to
     contaminate its precision. Switched to hard edges (numbers now render into a scratch layer,
     thresholded, same pattern the contour lines already used) so `image` and `labels` agree
     exactly, the fixture's own stated purpose.
  3. The fixture's independent green_60/green_100 render colours (chosen without checking against
     the CMYK-derived nominal palette, unlike every other shade in the table) sat closer to the
     *next* nominal green tier than to their own — `veg_walk` and `veg_fight` both scored 0.0 IoU,
     each captured whole by the tier below. Verified the CMYK values themselves against the IOF
     Appendix 1 PDF (correct, unchanged); re-picked the two render colours as the same small,
     plausible perturbation from nominal the other eleven shades already use.
  Also: `out_of_bounds` truth pixels (hatched, not filled — module docstring) are now excluded from
  every *other* class's sampleable mask, not just the class's own IoU, and the degraded-render
  regression test asserts the mean IoU across classes rather than the min — a rare small class
  (`water_shallow`, ~700px) swings 0.1+ on JPEG blockiness alone under a full seed, which a min-based
  bound was really just measuring. 152 tests pass (121 baseline + 31 new), `ruff check .` clean;
  full-size (4000x3000) classification takes 4.9 s against the 30 s budget.
- [x] T014 — Linear feature extraction — paths: `src/rogaine/vision/linear.py` — deps: T013 —
  DoD: roads, tracks and footpaths recovered as connected corridors via elongation and skeleton
  filters; a fixture path end-to-end is one component covering at least 90% of its length; map text
  and point symbols are rejected, measured as false-positive corridor area on the fixture (F5).
  Landed 2026-08-28. `extract_linear_features` takes `classify_palette`'s `road`-collapsed labels
  and splits them by shape: a component must clear an absolute pixel-area floor, a
  skeleton-length/sqrt(area) elongation ratio, a `minAreaRect` bounding-box aspect ratio, *and* an
  absolute skeleton-length floor (mm, converted via DPI) to be accepted as a corridor; accepted
  corridors are assigned `road`/`vehicle_track`/`footpath` by nearest nominal printed width
  (distance-transform along the skeleton); rejected components become `unknown`, not left as `road`.
  New `config/default.toml [linear]` section holds the eight tunables. DoD numbers measured on the
  fixture: an isolated wandering path recovers as one component covering 100% of its length (bar:
  90%); false-positive corridor area from black map-text/point-symbol ink is 0.0% (bar: under 5%).
  Per-sub-class IoU on the full chaotic fixture scene (six wandering paths, several crossing) is
  reported, not gated — road/vehicle_track/footpath are correctly separated on lines that never
  cross (`TestWidthBasedClassAssignment`, exact match); a component several true classes merge into
  at a crossing can only be assigned one of them, which mechanically caps the fixture-wide per-class
  number regardless of estimator quality.
  `tests/fixtures/synth_map.py` extended with black map-text labels and point symbols (`noise_mask`)
  — the fixture drew none before (T013's landing note), so F5's false-positive bar had nothing real
  to measure against. Three real defects found and fixed along the way:
  1. `cv2.line`/`cv2.polylines` does not draw an axis-aligned stroke `thickness` pixels wide: the
     actual rendered width jumps in steps of 2 (1, 3, 5, 7, ...) and two adjacent `thickness` values
     (one even, the odd one above it) land on the same actual width. The fixture's own
     `round(mm * ppm)` thickness for `vehicle_track` (4) and `footpath` (3) both drew a 5 px stroke
     at 300 dpi — indistinguishable by width, which defeated the one thing this task measures.
     Fixed with `stroke_thickness_px`, which searches for the `thickness` whose actual rendered
     width is nearest the target.
  2. Width estimation itself had a systematic +1 px bias: `2 * distanceTransform` at a stroke's
     skeleton measures pixel-*centre*-to-pixel-*centre* distance, which is `ceil(width/2)`, so
     doubling it overestimates by exactly 1 whenever the true width is odd — which, after fixing
     defect 1 above, is every width the fixture ever draws. `road`/`vehicle_track`/`footpath` all
     came back classified `road` until this was found. Fixed with a `- 1` correction in
     `extract_linear_features`, exact for odd widths, off by one pixel otherwise (still smaller than
     the gap between any two class widths).
  3. Several letters of a word, close enough for `close_radius_px`'s gap-bridging to merge into one
     connected component, can pass both the elongation ratio and the absolute length floor: a
     branchy multi-stroke skeleton racks up enough total pixel count even though the component is
     not shaped like a corridor. Neither test constrains overall shape, so both were fooled. Added a
     third, independent test — `minAreaRect` bounding-box aspect ratio — calibrated against real
     fixture measurements (touching-glyph clusters topped out near 1.6, the shortest real corridor
     fragments started near 2.8; `aspect_ratio_min = 2.0` sits between them with margin both ways).
  Also: the new noise-drawing code originally ran mid-generation, shifting every later `rng` draw
  (out-of-bounds blob, contour waviness, control placement) for every existing seeded fixture and
  quietly dropping a pre-existing T013 test (`rough_open` area IoU) from its passing value to 0.94
  against the 0.95 bar — not a T014 defect, but a reminder that `make_synthetic_map` threads one
  `rng` stream sequentially through the whole function. Moved the noise-drawing to the very end
  (after controls, before the optional degrade step) so extending the fixture there never reshuffles
  geometry any other seeded test already depends on. `test_palette.py`'s area-class IoU sampleable
  masks now also exclude `noise_mask`, the same treatment already given to `contour_mask` and for
  the same reason: black overprint classifies as `road`, not the area class underneath.
  166 tests pass (152 baseline + 14 new), `ruff check .` clean.
- [ ] T015 — Contour density and slope factor — paths: `src/rogaine/vision/contours.py` — deps: T013 —
  DoD: brown contour mask, density by Gaussian blur, `k_slope` from config; a contour-dense fixture
  region yields a strictly higher cost than a flat region of the same class; coefficient documented
  as direction-blind (F6).
- [ ] T016 — Segmentation orchestration and preview — paths: `src/rogaine/vision/segment.py`,
  `src/rogaine/render/preview.py` — deps: T013, T014, T015 —
  DoD: produces a `TerrainMap` plus a legible preview PNG; `terrain.npz` round-trips; IoU report
  printed per class.
- [ ] T017 — Palette validation across the real corpus — paths: `tools/palette_report.py`,
  `docs/palette-findings.md` — deps: T005, T016 —
  DoD: runs the classifier over every corpus map and reports per-map `unknown` fraction and the
  colour clusters that failed to match; identifies which map styles (ISOM 2000, ISOM 2017,
  topo-based rogaine maps, scanner colour shift) need their own palette profile; the outcome is
  either "one palette suffices" or a per-profile table added to `config/default.toml`. This task,
  not the fixture, is what retires SPEC risk 1.

## M2 — Control detection (WS-A)

- [ ] T020 — Control circle detection — paths: `src/rogaine/vision/controls.py` — deps: T011, T012 —
  DoD: HSV purple mask plus HoughCircles with the radius range derived from `mpp` (ISOM 5-6 mm);
  start triangle and finish double-circle recognised; on the fixture recall at least 0.95, precision
  at least 0.90, centre error at most a quarter radius (F7).
- [ ] T021 — Number OCR and points rule — paths: `src/rogaine/vision/ocr.py` — deps: T020 —
  DoD: digits read from a crop beside each circle with a confidence; points rule `first_digit` /
  `constant` / CSV; unreadable numbers emit `points: null` and a flag, never a guess; OCR failure
  degrades the run, never aborts it (F8).
- [ ] T022 — Controls CSV round-trip — paths: `src/rogaine/io/controls_csv.py` — deps: T002 —
  DoD: `id,x,y,number,points,confidence` reads and writes losslessly; a hand-edited CSV fully
  replaces detection; malformed rows are reported with line numbers (F9).

## M3 — Cost field and travel matrix (WS-B)

- [ ] T030 — Cost field — paths: `src/rogaine/cost/field.py` — deps: T002, T003 —
  DoD: `t = mpp / (v_base * k_terrain * k_slope)` as float32 seconds per pixel plus a passability
  mask; impassable classes excluded; a hand-checked 5x5 case matches the formula exactly (F10).
- [ ] T031 — Grid graph — paths: `src/rogaine/cost/graph.py` — deps: T030 —
  DoD: 8-connected CSR graph with sqrt(2) diagonals and configurable `graph_downsample`; node/pixel
  mapping is exact both ways; a 4000x3000 map at downsample 4 builds in under 15 s and stays under
  1 GB.
- [ ] T032 — Travel matrix and path reconstruction — paths: `src/rogaine/cost/travel.py` — deps: T031 —
  DoD: `scipy.sparse.csgraph.dijkstra` from each control; matrix symmetric within tolerance;
  per-pair polylines reconstructed from predecessors and simplified for rendering; unreachable pairs
  marked infinite, not zero; 60 controls on a full-size map in under 60 s (F11).

## M4 — Solvers and bench (WS-B)

- [ ] T040 — Objective and feasibility — paths: `src/rogaine/solve/objective.py` — deps: T002 —
  DoD: `score = sum(points) - penalty_per_min * max(0, T - limit)`; hub start and end enforced;
  unit-tested on hand-computed cases including exactly-on-limit (F14).
- [ ] T041 — Exact Held-Karp — paths: `src/rogaine/solve/exact.py` — deps: T040 —
  DoD: optimal for N up to 15 within memory; agrees with brute force for N up to 9 on random
  matrices; refuses N above the configured cap with a clear message instead of exhausting RAM (F12).
- [ ] T042 — Heuristic solver — paths: `src/rogaine/solve/heuristic.py` — deps: T040 —
  DoD: GRASP construction plus 2-opt / or-opt / insert / remove / swap local search under a time
  budget; seeded and deterministic; gap versus T041 at most 5% across a suite of random instances
  with N up to 15; handles 80 controls inside the budget (F13, F19).
- [ ] T043 — Alternative routes and interestingness — paths: `src/rogaine/solve/alternatives.py` —
  deps: T042 — DoD: top-K routes differing by at least one control, each with its score; K
  configurable; the score spread is reported as the map's interestingness measure (F16).
- [ ] T044 — `bench` command — paths: `src/rogaine/cli.py` (bench subcommand only) — deps: T041,
  T042 — DoD: runs both solvers on a reduced instance and prints points, time, and the gap; a test
  asserts the fixture gap stays within F13.

## M5 — CLI end-to-end and renders (WS-C)

- [ ] T050 — CLI commands — paths: `src/rogaine/cli.py` — deps: T016, T022, T032, T042 —
  DoD: `segment`, `detect`, `plan`, `bench`, `serve` with typer; `--seed` everywhere randomness
  exists; rich summary table of legs, time, points, penalty; non-zero exit on failure.
- [ ] T051 — Route JSON schema and writer — paths: `src/rogaine/io/route_json.py` — deps: T002 —
  DoD: documented schema with order, per-leg time/distance/polyline, cumulative time, points,
  penalty, score, and the config that produced it; validated on write; golden test on the fixture
  (F15).
- [ ] T052 — Route overlay render — paths: `src/rogaine/render/overlay.py` — deps: T051 —
  DoD: route drawn over the map with numbered visit order and leg times, legible over dark and light
  terrain; rendered legs match the JSON polylines pixel for pixel (F15).
- [ ] T053 — Determinism and performance guards — paths: `tests/e2e/test_cli.py`,
  `tests/perf/test_budgets.py` — deps: T050, T051, T052 —
  DoD: same inputs and seed give byte-identical JSON; the four NFR budgets are asserted on the
  full-size synthetic map (F19).

## M6 — Web viewer (WS-C)

- [ ] T060 — FastAPI backend — paths: `src/rogaine/web/app.py` — deps: T050 —
  DoD: upload, segment, detect, plan and export endpoints; long runs execute in a background task
  with a poll endpoint; binds 127.0.0.1; uploads validated by magic bytes and size, stored under
  `runs/<uuid>/` with a server-generated name (F17, security).
- [ ] T061 — Canvas viewer UI — paths: `src/rogaine/web/static/**` — deps: T060 —
  DoD: pan/zoom map canvas, calibration line tool, control markers that can be dragged, added,
  deleted and edited, parameter panel, run button, leg table, JSON/PNG/CSV export; keyboard
  operable with visible focus; Russian UI strings; legible in light and dark.
- [ ] T062 — Playwright end-to-end — paths: `tests/e2e/test_viewer.py` — deps: T061 —
  DoD: upload fixture, calibrate, move one control, run, assert the leg table and the exported JSON;
  runs headless inside the tests service (F17).

## M7 — Optional, only after the owner accepts the route

- [ ] T070 — Tiling and mask export — paths: `ml/dataset.py` — deps: T016, T017 —
  DoD: 512x512 tiles as `image.jpg` + `channels.npy` from palette-generated masks over the owner's
  200+ scan corpus, with rotation, blur and JPEG augmentation, matching the article's data recipe;
  tiles whose `unknown` fraction exceeds a threshold are dropped rather than taught as noise;
  train/val split is by source map, never by tile, so the same map cannot appear on both sides.
- [ ] T071 — SegFormer training — paths: `ml/train.py` — deps: T070 —
  DoD: MiT-B4 fine-tune with CE + Dice + Lovasz and rare-class weights, mixed precision, batch sized
  for 8 GB VRAM; per-class IoU reported on a held-out split.
- [ ] T072 — Inference path — paths: `ml/infer.py`, `src/rogaine/vision/segment.py` (backend switch)
  — deps: T071 — DoD: `--segmenter palette|segformer`; palette stays the default; the CPU-only path
  keeps working without torch installed.
