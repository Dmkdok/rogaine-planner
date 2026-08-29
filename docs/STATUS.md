# Status

phase: implement
approved: true
approved_at: 2026-08-19
current: M1 T010-T016 landed (T017 blocked on owner data); M2 complete (T020-T022 landed); M3
  complete (T030-T032 landed); T040 (objective and feasibility, M4) landed; T041 (exact Held-Karp,
  M4) landed; T042 (heuristic solver, M4, deps T040) next

## Checklist
- [x] Phase 0 intake
- [x] Phase 1 elicit (DoR met)
- [x] Phase 2 SPEC.md
- [x] Phase 3 PLAN.md + TASKS.md
- [x] GATE user approved (2026-08-19, «утверждаю»)
- [ ] Phase 4 implementation — M0 done, M1-M7 open
- [ ] Phase 5 tests green
- [ ] Phase 6 review clean (or accepted waivers)
- [ ] Phase 7 handoff

## Test report

`docker compose run --rm tests` — **270 passed**, exit 0 (2026-08-29). `ruff check .` clean.
Full-size (4000x3000) palette classification: 4.9s against the 30s budget (T013). Full-size grid
graph build (downsample=4): 0.34-0.53s / ~406 MiB peak against the 15s/1GB budget (T031). Full-size
travel matrix, 61 controls: 11.2s against the 60s budget (T032).

Earlier baseline: 87 passed, exit 0 (2026-08-19).
Image verified to carry `tesseract 5.5.0` and `cv2 5.0.0`; `docker compose run --rm app` prints the
CLI help. Never run pytest on the Windows host — it hangs.

Three real defects were found by this first run and fixed:

1. `Route._legs_match_order` zipped `order` with `order[1:]` under `strict=True`. Those are always
   one apart, so **every valid route was rejected** with `zip() argument 2 is shorter than
   argument 1`. The inner zip is ragged on purpose; only the outer one may be strict.
2. `_place_controls` in the fixture returned a hub and nothing else when the map was too small for
   the 5-radii minimum gap (a 400x300 map at 300 dpi placed **0 of 6** controls). Silent
   under-placement would have made every downstream control assertion pass by vacuum; it now
   raises with the numbers in the message.
3. The fixture drew a fixed 26 contour lines regardless of map height, so a small map came out
   almost solid brown. The count now scales with height; the standard 1200 px fixture keeps its 26.

## What M0 landed

- `pyproject.toml`, `Dockerfile` (base + test stages), `docker-compose.yml`, `.dockerignore`,
  `.gitignore`. Ruff is configured in `pyproject.toml`, not a separate `ruff.toml`.
- `src/rogaine/models.py` — the contract, **frozen** (ADR-008). pydantic for what serialises,
  frozen dataclasses for what carries numpy.
- `config/default.toml` + `src/rogaine/config.py` — ISOM inks and shades from IOF Appendix 1,
  the 17-class terrain table, and `cmyk_to_srgb` built on process-ink primaries.
- `tests/fixtures/synth_map.py` — the synthetic ISOM map with exact ground truth, plus the
  `FULL_SIZE` 4000x3000 preset the performance budgets are stated against.
- `src/rogaine/io/corpus.py` + `src/rogaine/cli.py` — corpus intake and `rogaine corpus
  list` / `check`. The CLI is a stub that T050 (WS-C) extends, not replaces.
- `data/README.md` — the on-disk contract for the owner's maps.
- `tools/ocd_render.md` + `tools/ocd_render.py` — the T006 spike, closed as
  documented-not-executed (no `.ocd` file has arrived).

## Two decisions worth keeping in view

- **`cmyk_to_srgb` does not use the textbook formula.** The naive conversion renders ISOM purple
  (35/85/0/0) with a blue channel of 255, which would put the control circles nearer to blue than
  to purple and break T020 before it started. The conversion interpolates towards measured process
  ink primaries instead. `test_isom_purple_is_purple_not_blue` is the guard.
- **`palette.lab_distance_threshold = 35.0` is provisional, left unchanged by T013.** The shade
  table is derived from published CMYK, so it sits a real distance from what any given map prints —
  largest for green (verified against the IOF Appendix 1 PDF directly: the CMYK values are correct,
  the CMYK->sRGB conversion is what's approximate). T013 found the threshold itself wasn't the
  problem — on the synthetic fixture the nearest-*wrong*-shade distance was smaller than the
  nearest-*right*-shade distance for two green tiers, which no threshold value can fix, only a
  closer palette or fixture can. T017 confirms the real threshold value against the real corpus. If
  a fixed palette proves brittle there, fit it per map (cluster the map's own colours in Lab) rather
  than widening the threshold until `unknown` stops meaning anything.

## Blocked on the owner

None of these block M1 — the synthetic fixture carries it. **2026-08-25: the map corpus arrived** —
13 scans + 1 `.ocd` file, relocated from a root-level `maps/` drop into `data/maps/<slug>/map.*`
per the documented contract (ids transliterated from the owner's filenames; see T005 in TASKS.md
for the full list). `rogaine corpus list` reads all 14. Still open:

- whether OCAD itself is available, or OpenOrienteering Mapper should be installed on the host for
  T006 — `data/maps/rfar2016-for-stroganov/map.ocd` is ready and waiting the moment it is;
- **one map with a reference route** (`reference.json`) — this is the acceptance oracle and the
  single most valuable item on the list;
- a controls list with points for at least one map;
- the scan DPI and map scale for each of the 14 — none has `meta.toml` yet, so none is plannable
  (only listable) and T017 (per-map palette validation) has nothing to run against.

Also sitting at repo root, unexplained: `crop_dense.png` (a small cropped fragment of a real map —
olive rough-open terrain, blue-hatched marsh, a purple control numbered 37). Not moved or deleted;
ask the owner what it's for before touching it.

## Notes
- Source of the idea: https://habr.com/ru/articles/1065342/ (rogaine route optimisation:
  SegFormer segmentation, VLM control detection, A* + Held-Karp).
- Owner decisions taken during elicitation (2026-08-18):
  - Success = route quality equal to or better than the article's; method is free.
  - Inputs on disk: map rasters (PNG/JPG/PDF/scan) plus a few `.ocd` files. On 2026-08-19 the owner
    offered 200+ scans and further help; roles and sizing settled in ADR-010, tasks T005/T006/T017.
  - Control detection: CV plus manual correction. No VLM.
  - Delivery: CLI plus a local web viewer.
  - Scale: 30-80 controls, heuristic solver acceptable, exact solver kept as the oracle.
  - Map scale: manual entry plus calibration line.
  - Movement model: base speed x terrain coefficient + contour-based slope penalty.
  - Rules: start = finish, points penalty per minute late.
  - Georeferencing/GPX: out of scope.
  - Acceptance: solver self-check (heuristic vs exact gap) plus the owner's own judgement.
- Environment probed: Windows 11, Python 3.14.3 host, Docker 29.3.1 / Compose v5.1.1,
  NVIDIA RTX 3060 Ti 8 GB, git 2.55.0. Docker Desktop needs starting manually after a reboot.
- Serena project `map-planer` created and activated at `E:\Dev\_AI_\map-planer`.
- Next action: M1 (WS-A vision, T010-T017) — raster loading, scale, normalisation, then the
  palette classifier that everything downstream depends on.
- 2026-08-25: real corpus arrived and relocated to `data/maps/`, contract unchanged (see "Blocked
  on the owner" above and T005/T006 in TASKS.md).
- 2026-08-25: T010 (raster loading), T011 (scale/calibration), T012 (normalisation) landed — see
  TASKS.md for detail. 121 tests pass, `ruff check .` clean, independently re-verified.
- 2026-08-27: T013 (ISOM palette classifier) landed — see TASKS.md for the three defects found on
  first real run (the code and its tests had existed uncommitted, never executed) and fixed: a
  single-pass `unknown` fill that couldn't reach the middle of a wide gap, antialiased fixture edges
  blending into a colour that coincidentally matched a real shade, and two green tiers whose
  independently-chosen fixture colour sat closer to the wrong nominal tier than their own. 152 tests
  pass, `ruff check .` clean.
- 2026-08-28: T014 (linear feature extraction) landed — `extract_linear_features` splits the
  palette's `road` placeholder into `road`/`vehicle_track`/`footpath` by shape (area, elongation,
  bounding-box aspect ratio, absolute length floor) then by measured stroke width. Found and fixed
  three real defects, all in the OpenCV-rendering-quirk category T013's landing note already named:
  `cv2.line` doesn't draw an axis-aligned stroke as many pixels wide as its `thickness` argument
  claims (making the fixture's `vehicle_track` and `footpath` render at the same width until
  corrected); the distance-transform width estimator had a systematic +1 px bias; touching text
  glyphs merged by gap-bridging could pass both shape tests that existed until a third
  (`minAreaRect` aspect ratio) was added. See TASKS.md T014 for the full detail. Fixture extended
  with black map-text/point-symbol noise so F5's false-positive bar has something real to measure
  (0.0% false-positive corridor area; 100% single-component coverage on an isolated path, both
  against their DoD bars). 166 tests pass, `ruff check .` clean.
- 2026-08-28: T015 (contour density and slope factor) landed — `contour_density` Gaussian-blurs the
  palette's `contour` label (sigma in mm, converted via DPI, matching every other physical tunable in
  `config/default.toml`) into `TerrainMap.contour_density`; `k_slope(density) = 1/(1 + penalty *
  density)` is the reciprocal T030 will multiply into `k_terrain`. Independent review before landing
  found four real issues, all fixed: a config comment claiming density reaches 1.0 on a real map
  (it tops out near 0.40 on the fixture — contour-line gaps dominate real area); `k_slope` accepting
  out-of-contract input (wrong dtype, outside `[0, 1]`) and silently producing `inf`/negative factors
  instead of raising; the blur sigma being a raw pixel constant instead of mm+DPI like every sibling
  setting; a docstring pointing at a README and route output that don't exist yet. See TASKS.md T015
  for full detail. 184 tests pass, `ruff check .` clean.
- 2026-08-28: T016 (segmentation orchestration and preview) landed — `vision/segment.py`'s
  `segment()` chains normalize -> classify_palette -> extract_linear_features -> contour_density
  into one `TerrainMap`, plus a `terrain.npz` round-trip and a shared `iou_report` helper T017 will
  reuse; new `render/preview.py` colours labels by their nominal printed colour via a vectorised
  lookup table and writes the PNG. Two real findings: `unknown` and `forest_runnable` both render
  white (both classes' shades resolve there independently — a legitimate config fact, documented and
  regression-tested, not a bug); the first IoU-floor test measured against the clean fixture and
  failed hard because `segment()`'s unconditional `normalize()` step measurably hurts an
  already-clean render (`test_normalize.py` already documented this), fixed by measuring on the
  degraded fixture instead, matching `test_palette.py`'s own precedent. See TASKS.md T016 for full
  detail. 198 tests pass, `ruff check .` clean. T017 (palette validation across the real corpus) is
  next in M1 order but blocked on the owner for scale/DPI/controls/reference route on the real maps
  (see "Blocked on the owner" below) — moved to M2 instead, which is fully unblocked (deps T011/T012,
  both landed) and works the same way M1 did before real corpus data existed: against the synthetic
  fixture.
- 2026-08-28: T020 (control circle detection, M2) landed — `vision/controls.py`'s `detect_controls`
  runs `cv2.HoughCircles` (ISOM 703 control circles) and a `cv2.approxPolyDP`-based triangle finder
  (ISOM 701 start marker, the hub) over one shared HSV purple mask; `dpi`, not `mpp`, drives the
  radius conversion (TASKS.md's T020 wording said `mpp`, corrected to match the established
  printed-size-on-paper convention). One real finding: the shipped Hough parameters fit spurious
  circles inside the purple out-of-bounds hatching pattern, dragging precision to 0.857 against the
  0.90 floor; fixed with a ring-coverage shape check (samples each candidate's fitted circumference,
  requires at least 75% purple coverage — real rings measured 0.822-1.000, spurious hatch-fits
  0.500-0.682) rather than blind Hough retuning. Final fixture numbers: recall 1.000, precision 1.000,
  max centre error 3.85px against an 8.86px floor. The DoD's "finish double-circle" has nothing to
  test: this project's start = finish convention means the fixture (and the project) has only one hub
  marker, stated plainly rather than fabricated. See TASKS.md T020 for full detail. 207 tests pass,
  `ruff check .` clean.
- 2026-08-28: T021 (number OCR and points rule, M2) landed — `vision/ocr.py`'s
  `read_control_number`/`read_control_numbers` crop each non-hub control's number from a purple-only
  mask (T020's `purple_mask` reused), erase the circle's own ring, run `pytesseract` (psm 7, digit
  whitelist), and take `min(detection confidence, OCR confidence)` as the combined trust. Two
  crop-geometry findings, both measured end to end against `clean_synthetic_map` rather than tuned
  blind: the circle ring is the same purple ink as the number and reads as garbage text left in the
  crop (fixed by masking a ring-sized disk); a crop sized to exactly `number_search_radius` clips the
  second digit (1/12 read correctly), fixed by added margin headroom (11/12). The twelfth control's
  purple out-of-bounds hatching sits close enough to the course boundary to land inside even the
  widened crop — documented as a real limitation (flagged, `number=None`, never a guess) rather than
  chased with a wider margin, which measures worse. ADR-009 carves the `constant` points rule out of
  the DoD's blanket "unreadable emits null" wording — a constant-points control's score never
  depended on the reading, so `constant` still assigns `points_constant` even when the number itself
  stays unreadable and flagged; `first_digit` and `csv` are unaffected. This module's implementation
  and its 16 tests (`tests/unit/vision/test_ocr.py`) both existed uncommitted from a prior session
  when this one picked the work back up — verified against the tree rather than trusted, per this
  file's own standing instruction, and a stray `ruff` finding (`zip()` without `strict=`) fixed along
  the way. Also cleaned up: a `.tmp_dev/` directory of ad hoc debug scripts from that prior session's
  OCR-tuning exploration, superseded by the two findings above now written into `ocr.py`'s docstring
  and no longer needed. See TASKS.md T021 for full detail. 223 tests pass, `ruff check .` clean.
- 2026-08-28: T022 (controls CSV round-trip, M2 — milestone now complete) landed —
  `io/controls_csv.py`'s `read_controls`/`write_controls` are the single canonical home for the CSV
  contract, moved from `io/corpus.py` (which now re-exports the name rather than owning a second
  copy). Real discrepancy found and resolved: the DoD's literal `id,x,y,number,points,confidence`
  header cannot round-trip losslessly alone — `is_hub` is structurally required (SPEC F14) and
  `source` (`detected`/`manual`) is a full `Control` field per SPEC's own data-model section, so both
  are appended after the DoD's six columns rather than silently dropped; `confidence` itself was
  previously hardcoded to `1.0` on every CSV read (`source` to `"manual"`) since nothing produced a
  real value at T005 time — now that T020/T021 do, this module reads and writes the real number
  instead of overwriting it. Optional columns still default on a blank cell or an absent column
  (`confidence` -> `1.0`, `source` -> `"manual"`), so `data/README.md`'s documented bare
  `id,x,y,number,points,is_hub` example keeps reading exactly as before; `id`/`x`/`y` are never
  defaulted. `data/README.md`'s own example header is now stale (pre-T022, no `confidence` column) —
  flagged, not fixed here (outside T022's assigned paths). See TASKS.md T022 for full detail. 229
  tests pass (223 baseline - 4 moved out of `test_corpus.py` + 10 new in
  `tests/unit/io/test_controls_csv.py`), `ruff check .` clean.
- 2026-08-28: T030 (cost field, M3) landed — new `src/rogaine/cost/` package; `compute_cost_field`
  gathers `k_terrain`/`passable` from `AppConfig.speed_factors()`/`passability()`, reuses T015's
  `k_slope` unchanged, and divides with `out=`/`where=passable` so the division never executes at
  an impassable cell. Two real judgement calls, both documented in the module docstring: impassable
  pixels store `+inf`, never `nan` (proved unreachable — `mpp` is always positive finite, `k_slope`
  is always strictly positive for a finite non-negative `penalty`, so only `k_terrain` can ever be
  the zero factor); and a real defect caught before it ever crashed — `contour` is `passable = true`
  with `speed_factor = 0.0` by design (`TerrainSpec`'s own validator exception, config's own "not an
  area class" note), so the raw formula would divide by zero at a *passable* cell and raise inside
  `CostField.__post_init__` on any map with contour ink; fixed by neutralising `k_terrain` to `1.0`
  wherever a pixel is passable yet its gathered `k_terrain` is `0.0` (by that same validator this
  can only be the contour case), leaving only `k_slope`'s density-driven penalty there. Hand-checked
  5x5 fixture (`tests/unit/cost/test_field.py`) covers five homogeneous rows — `forest_runnable`,
  `road`, `water_uncrossable` (impassable), `contour` (the neutralised case), `road` again at a
  different density — with per-pixel expected cost computed independently from
  `config.terrain_of(cls).speed_factor` and the plain `1/(1+penalty*density)` formula, never by
  calling `compute_cost_field` itself; also covers dtype, the exact passable/finite bijection, and
  `base_speed_mps <= 0` rejection. See TASKS.md T030 for full detail. 236 tests pass (229 baseline +
  7 new), `ruff check .` clean.
  Next: T031 (grid graph, M3, deps T030).
- 2026-08-29: T031 (grid graph, M3) landed — new `build_grid_graph` in `src/rogaine/cost/graph.py`
  turns a `CostField` into an 8-connected `scipy.sparse` CSR grid graph, one node per
  `downsample x downsample` block, built vectorised (numpy reshape/sum aggregation, four slice-pair
  calls for the 8-connected edge set, no Python loop over nodes or edges). Four documented judgement
  calls: edge weight = `spacing * avg(rate_u, rate_v)` (`downsample` orthogonal, `downsample *
  sqrt(2)` diagonal) — the standard trapezoidal cost-distance discretisation, dimensionally
  consistent with T030's per-pixel formula and exact at `downsample == 1`; a block is passable iff
  it has at least one passable original pixel, rated by the mean over only those pixels (rejected a
  naive full-block mean, which would let one impassable pixel poison an otherwise-open block, and
  stride-sampling, which could step clean over a one-pixel barrier); `strict_impassable=true`
  creates no edge touching an impassable block (node index unchanged, just degree zero) while
  `false` substitutes `impassable_cost_multiplier * (mean rate of every passable block)` as a
  single global reference rate, chosen over a literal per-edge local one because that is ill-defined
  for an edge between two impassable blocks; node/pixel mapping uses this codebase's `(x, y)`
  pixel convention (`Control.x`/`Control.y`, `Leg.polyline`), floors sub-pixel input, and returns
  each block's top-left pixel as the canonical representative, with `node -> pixel -> node`
  round-tripping exactly always and `pixel -> node -> pixel` exactly only at `downsample == 1`. No
  further defects found — the vectorised implementation matched hand-computed values on first run.
  Measured on the real 4000x3000/downsample=4 preset (750,000 nodes, ~5.99M CSR nonzeros): 0.34-0.53s
  wall time, ~406 MiB tracemalloc peak, against the 15s/1GB budget. See TASKS.md T031 for full detail.
  256 tests pass (236 baseline + 20 new in `tests/unit/cost/test_graph.py`), `ruff check .` clean.
  Next: T032 (travel matrix and path reconstruction, M3, deps T031).
- 2026-08-29: T032 (travel matrix and path reconstruction, M3 — milestone now complete) landed —
  new `build_travel_matrix` in `src/rogaine/cost/travel.py` runs one `scipy.sparse.csgraph.dijkstra`
  call with `indices` set to every control's node (ADR-002), reading `seconds` off the returned
  distance matrix in one vectorised fancy-index op and reconstructing each pairwise polyline from
  the matching predecessors matrix. Five documented design calls: `meters_per_pixel` is this
  function's own explicit parameter (`GridGraph` carries no ground scale, and `cost/graph.py` /
  `models.py` were both off-limits); `meters[i,j]` is the physical length of the *actual*
  reconstructed time-optimal path, not an independently shortest distance; self-pairs are `0.0`
  with no `paths` entry; symmetry is asserted within tolerance (`rtol=1e-7`/`atol=1e-6`) rather
  than forced, since `seconds` comes from two independent sweeps and forcing it would hide a real
  directed-edge bug; each unordered pair is reconstructed once and mirrored for its reverse
  direction, cheaper and exact by construction rather than post-hoc symmetrisation. Polyline
  simplification reuses `vision/controls.py`'s `cv2.approxPolyDP` idiom at a plain pixel constant
  (no new config section — checked first, confirmed nothing existing to extend, and this is
  cosmetic-only, unlike every existing config-driven geometric tunable). No other defects found.
  Measured on the real 4000x3000/downsample=4 preset with 61 controls: 11.2s wall time against the
  60s budget. See TASKS.md T032 for full detail. 270 tests pass (256 baseline + 14 new), `ruff
  check .` clean. Next: T040 (objective and feasibility, M4, deps T002, unblocked).
- 2026-08-29: T040 (objective and feasibility, M4) landed — new `src/rogaine/solve/` package;
  `score_order` in `objective.py` scores one candidate visit order against a `TravelMatrix` and
  `RunConfig`, returning a `ScoredOrder` (totals, points, penalty, score, feasible), deliberately
  no `Route`/`Leg` construction (left to T041/T042). Five design decisions, each documented in the
  module's own docstring: units (`penalty_per_min` is per-minute, so the seconds-denominated
  overrun is divided by 60 before multiplying — a literal transcription would overcharge 60x); a
  visited control with `points is None` raises rather than scoring `0` (ADR-009 — same class of
  guess as the reading itself), with the hub exempt from that check and from the points sum since
  it is a waypoint, not a scored control; an unreachable leg surfaces as a cheap `feasible: bool`
  plus `score = -inf`, never a raised exception (unlike `points is None`, unreachable pairs are a
  per-order property the heuristic solver's hot loop will hit often), with feasibility decided
  before the per-minute formula runs so `penalty_per_min == 0.0` combined with an infinite overrun
  never hits IEEE-754's `0 * inf = nan`; hub enforcement resolves the actual `is_hub` control and
  checks both ends against its id specifically, not just that they match each other. One real
  defect found and fixed: an initial `zip(order, order[1:], strict=True)` raised on every call
  (the two sequences are one element apart by construction) — replaced with `itertools.pairwise`
  per `ruff`'s own `RUF007`. See TASKS.md T040 for full detail. 11 new tests
  (`tests/unit/solve/test_objective.py`), all hand-computed against a uniform 300s/500m fixture
  matrix, covering exactly-on-limit, just/well past the limit, `penalty_per_min == 0.0` overrun,
  the unreachable-leg nan regression, hub-mismatch rejection, unresolved-points rejection, and the
  hub's own `None` points not being flagged. 281 tests pass (270 baseline + 11 new), `ruff check .`
  clean. Next: T041 (exact Held-Karp, M4, deps T040, unblocked).
- 2026-08-29: T041 (exact Held-Karp, M4 — milestone still open, T042 next) landed —
  `solve_exact` in `src/rogaine/solve/exact.py` solves the Orienteering Problem (SPEC F12,
  ADR-003), not TSP: it repurposes Held-Karp's bitmask-DP machinery to find, for every `(subset,
  last-control)` state, the minimum-*time* order, then exhaustively scores every reachable state's
  time-minimal order with T040's `score_order` and keeps the best. The correctness argument (full
  detail in the module docstring): for a fixed subset and endpoint, every visit order collects
  identical points and `score_order`'s penalty is monotonic non-decreasing in total time, so the
  time-minimal order of that `(subset, endpoint)` provably cannot be beaten by a slower order of the
  same pair — no slower order is ever generated, let alone scored. Candidates exclude the hub (fixed
  start/end) and any `points is None` control (ADR-009, same up-front filter T040 already commits
  callers to). The empty-subset route is scored via `score_order` rather than hand-built, so it acts
  as a correct guaranteed floor when every real subset loses. The memory guard is the DoD's actual
  ask: `n > config.solver.exact_max_controls` is checked before any `2**N`-sized array is allocated,
  refusing with both numbers named. This module's code and its 8 tests
  (`tests/unit/solve/test_exact.py`) existed uncommitted from a prior session — re-verified against
  the tree rather than trusted, per this file's own standing practice. One real finding on that
  re-check: `ruff check .` was not clean (10x `E501` line-too-long in the module docstring, all
  from a docstring never previously linted), fixed by rewrapping to 100 columns without changing a
  word; no logic defects found. Tests cover a hand-computed optimum built with asymmetric leg costs
  so the DP must pick the cheaper of two orders of the same subset (not just the right subset),
  brute-force agreement at N=4/6/9, unresolved-points exclusion, the empty-route fallback when a
  reachable control's round trip still nets negative, and the cap satisfied at the limit /
  refused one above it. See TASKS.md T041 for full detail. 289 tests pass (281 baseline + 8 new),
  `ruff check .` clean. Next: T042 (heuristic solver, M4, deps T040, unblocked).
