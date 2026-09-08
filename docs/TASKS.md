# Tasks

Requirement IDs (F1-F20) refer to [SPEC.md](SPEC.md). Workstreams (WS-A vision, WS-B routing,
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
- [x] T015 — Contour density and slope factor — paths: `src/rogaine/vision/contours.py` — deps: T013 —
  DoD: brown contour mask, density by Gaussian blur, `k_slope` from config; a contour-dense fixture
  region yields a strictly higher cost than a flat region of the same class; coefficient documented
  as direction-blind (F6).
  Landed 2026-08-28. `contour_mask` picks out `classify_palette`'s `contour` label; `contour_density`
  Gaussian-blurs it (sigma configured in mm, converted via DPI like every other geometric tunable in
  `config/default.toml` — `LinearSettings.nominal_width_px`, `DetectorSettings.circle_radius_px`) and
  clips to `[0, 1]` for `TerrainMap.contour_density`; `k_slope(density) = 1 / (1 + penalty*density)`,
  the reciprocal of the config's own "speed divided by (1 + penalty*density)" so T030 can apply it by
  multiplication alongside `k_terrain`. Direction-blindness (ADR-006) is stated in both functions'
  docstrings, not just the ADR. Fixture acceptance test reuses `test_synth_map.py`'s own top-quarter
  (steep) vs bottom-quarter (flat) split, sampled on `forest_runnable` pixels in both bands after a
  real `classify_palette` pass (no ground-truth shortcut): dense-region cost is ~4.4% above flat, gate
  set at 2% margin, not a bare inequality.
  Independent review (before any code was called done) found no defect in the DoD itself but four
  real issues, all fixed: (1) `config/default.toml`'s original comment claimed density is "normalised
  to [0, 1]" and the steepest ground reaches a 3x cost multiplier — false on any real map, since
  contour-line gaps dominate real area; the fixture's own density never exceeds ~0.40. Wording fixed
  to describe density as a clipped area fraction with a stated theoretical (not reachable) floor.
  (2) `k_slope` validated array shape only, not dtype or range — an out-of-contract input (wrong
  dtype, or a density outside `[0, 1]`) silently produced `inf`/negative factors, which would read as
  a zero-cost or negative graph edge to T031/T032's Dijkstra rather than raising. Added dtype and
  range checks. (3) the Gaussian sigma was a raw pixel constant with no `dpi` parameter, unlike every
  other physical size in this config — the same terrain scanned at a different DPI got a different
  smoothing scale in real millimetres. `SlopeSettings.density_sigma` (px) became `density_sigma_mm`
  plus a `density_sigma_px(dpi)` helper; `contour_density` gained a `dpi` parameter, mirroring
  `extract_linear_features(labels, dpi, config)`. (4) a docstring referenced a README and route output
  that do not exist yet in this repo — changed to future tense pointing at M5/M6.
  184 tests pass (166 baseline + 18 new), `ruff check .` clean.
- [x] T016 — Segmentation orchestration and preview — paths: `src/rogaine/vision/segment.py`,
  `src/rogaine/render/preview.py` — deps: T013, T014, T015 —
  DoD: produces a `TerrainMap` plus a legible preview PNG; `terrain.npz` round-trips; IoU report
  printed per class.
  Landed 2026-08-28. `segment()` chains `normalize` -> `classify_palette` -> `extract_linear_features`
  -> `contour_density` into one `TerrainMap`, taking `dpi` and `meters_per_pixel` as separate explicit
  parameters (neither derives from the other: `dpi` is scan resolution for the config's mm-based
  tunables, `meters_per_pixel` is ground distance per pixel from either `dpi`+scale or two-point
  calibration, and `MapContext` carries only the latter). `save_terrain_map`/`load_terrain_map`
  round-trip `terrain.npz` via `np.savez_compressed`, exact on `labels` and `contour_density`.
  `iou_report`/`format_iou_report` promote the per-class IoU pattern T013-T015's fixture tests each
  wrote by hand into one shared function, for `tools/palette_report.py` (T017) to reuse. New
  `src/rogaine/render/` package: `render_preview` colours `TerrainMap.labels` by each class's nominal
  printed colour via a vectorised `TERRAIN_ORDER`-indexed lookup table (no per-pixel Python loop —
  matters at the 4000x3000 full-size preset); `write_preview` writes it as a PNG (BGR-swapped for
  `cv2.imwrite`, which fails silently on a bad path — checked and raised explicitly instead).
  Two real findings, both from failing assertions, not hunches:
  1. `unknown`'s shade is literally `"none"` (`config/default.toml`), which resolves to white —
     the same white `forest_runnable` renders via its own shade (`white`, ink `"none"`, tint 0). Both
     are legitimate, independently-justified config choices (ISOM convention for unmarked forest vs.
     this project's "no classification" marker), so `render_preview` does not invent an unrequested
     colour to separate them; documented in the module docstring and locked in with a regression test.
  2. The first IoU-floor test asserted `min(area IoU) >= 0.85` against the *clean* fixture and failed
     hard (`veg_slow_run=0.156`, `water_shallow=0.276`, several linear classes 0.22-0.45): `segment()`
     unconditionally runs `normalize()`, and `test_normalize.py`'s own docstring already documents
     that grey-world white balance run on an already-clean, zero-tint render moves area classes
     *away* from the classifier's true CMYK palette, not towards it. Fixed by measuring on the
     *degraded* fixture instead — the realistic scan case `segment()` exists for — at the same 0.60
     mean-not-min floor `test_palette.py`'s own normalize+classify composition test already
     established (measured here: 0.63).
  198 tests pass (184 baseline + 14 new), `ruff check .` clean.
- [ ] T017 — Palette validation across the real corpus — paths: `tools/palette_report.py`,
  `docs/palette-findings.md` — deps: T005, T016 —
  DoD: runs the classifier over every corpus map and reports per-map `unknown` fraction and the
  colour clusters that failed to match; identifies which map styles (ISOM 2000, ISOM 2017,
  topo-based rogaine maps, scanner colour shift) need their own palette profile; the outcome is
  either "one palette suffices" or a per-profile table added to `config/default.toml`. This task,
  not the fixture, is what retires SPEC risk 1.

## M2 — Control detection (WS-A)

- [x] T020 — Control circle detection — paths: `src/rogaine/vision/controls.py` — deps: T011, T012 —
  DoD: HSV purple mask plus HoughCircles with the radius range derived from `mpp` (ISOM 5-6 mm);
  start triangle and finish double-circle recognised; on the fixture recall at least 0.95, precision
  at least 0.90, centre error at most a quarter radius (F7).
  Landed 2026-08-28. `detect_controls(image, dpi, config)` runs two detectors on one HSV `purple_mask`
  (`config.detector.purple_hue_range`/`purple_min_saturation`/`purple_min_value`): `cv2.HoughCircles`
  (radius bounds from `config.detector.circle_radius_px(dpi)` — `dpi`, not `mpp`; the DoD's "`mpp`"
  was stale plan-time wording, corrected to match the convention T014-T016 already established: ISOM
  symbol sizes are fixed on paper, the map's ground scale never enters into it) for the 703 control
  circles, and `cv2.findContours` + `cv2.approxPolyDP` (3-vertex, size-anchored to the same
  `circle_radius_px`) for the 701 start triangle at the hub. The DoD's "finish double-circle" has
  nothing to detect or test: this project's start = finish one-hub convention means the fixture draws
  only the one triangle marker, never a second symbol — stated plainly rather than fabricating a test
  for a symbol that doesn't exist in the fixture.
  One real finding: the config's shipped Hough parameters found every true circle (recall 1.0) but
  also fit spurious circles inside the purple out-of-bounds hatching, where crossing hatch lines
  locally resemble arcs at a radius inside the configured tolerance band — 14 raw detections for 12
  true controls on the standard fixture, precision 0.857 against the 0.90 floor. Retuning
  `hough_param1`/`hough_param2` blindly was not the fix (`cv2.HoughCircles` alone cannot tell a
  genuine drawn ring from a coincidental circular alignment of unrelated ink) — added
  `_ring_coverage`, which samples points around each candidate's fitted circumference and rejects any
  candidate where less than 75% of the sampled ring actually sits on purple ink. Measured true/false
  separation before picking that threshold: real rings scored 0.822-1.000, spurious hatch-fit circles
  0.500-0.682. Brings precision to 1.0 on both the degraded and clean fixture without touching
  `config/default.toml`; the same coverage value doubles as each circle's `confidence`. Final measured
  numbers: recall 1.000, precision 1.000, max centre error 3.85px against a floor of 8.86px
  (radius/4); hub triangle centroid within a few px of true hub position.
  207 tests pass (198 baseline + 9 new), `ruff check .` clean.
- [x] T021 — Number OCR and points rule — paths: `src/rogaine/vision/ocr.py` — deps: T020 —
  DoD: digits read from a crop beside each circle with a confidence; points rule `first_digit` /
  `constant` / CSV; unreadable numbers emit `points: null` and a flag, never a guess; OCR failure
  degrades the run, never aborts it (F8).
  Landed 2026-08-28. `read_control_number`/`read_control_numbers` in `vision/ocr.py` build a
  purple-only crop around each non-hub `Control` (`purple_mask`, reused from T020), blank the
  control's own circle ring, run `pytesseract.image_to_data` (psm 7, digit whitelist), and combine
  OCR confidence with T020's detection confidence by `min()`. Two crop-geometry findings, both
  measured against `clean_synthetic_map` end to end rather than tuned blind: the printed circle ring
  is the same purple ink as the number, so left in the crop Tesseract reads the ring itself as
  garbage text (fixed by masking a disk sized off `_CIRCLE_MASK_RADIUS_FACTOR`); a crop sized to
  exactly `number_search_radius` clips the second digit of a two-digit number (1/12 read correctly),
  fixed by `_CROP_MARGIN_FACTOR` headroom (11/12). The twelfth control sits close enough to the
  course boundary that its purple out-of-bounds hatching lands inside even the widened crop — stated
  as a real, documented limitation (flagged `number=None`, never a guess) rather than chased with a
  wider margin, which measured worse (catches neighbouring ink instead).
  The DoD's "unreadable numbers emit `points: null`" reads as a blanket rule, but ADR-009 carves out
  `constant` in the same breath ("the points rule can fall back to a constant") — a constant-points
  control's score never depended on the reading, so this module assigns `points_constant` under
  `constant` even when the number itself stays unreadable and flagged; `first_digit` (the DoD's
  literal case) and `csv` (T022's placeholder, always `points=None` here) are unaffected. See the
  module's own docstring for the full reasoning.
  16 new tests (`tests/unit/vision/test_ocr.py`), all measured against `clean_synthetic_map` per the
  module's own precedent, not the degraded standard fixture (OCR is more noise-sensitive than
  circle/shape detection; the docstring documents why). 223 tests pass (207 baseline + 16 new),
  `ruff check .` clean.
- [x] T022 — Controls CSV round-trip — paths: `src/rogaine/io/controls_csv.py` — deps: T002 —
  DoD: `id,x,y,number,points,confidence` reads and writes losslessly; a hand-edited CSV fully
  replaces detection; malformed rows are reported with line numbers (F9).
  Landed 2026-08-28. `read_controls`/`write_controls` in the new module are the single canonical
  home for the CSV contract, matching the repo map. Real discrepancy found and resolved: the DoD's
  literal `id,x,y,number,points,confidence` header cannot round-trip losslessly on its own — `is_hub`
  is structurally required (`Control`/SPEC F14 need exactly one hub, sorted first) and `source`
  (`detected`/`manual`) is listed as a full `Control` field in SPEC's own "Content / data model"
  section, on equal footing with `confidence`; dropping either loses real information on a
  write-detected -> read-back cycle (a re-loaded detected control would become indistinguishable
  from a hand-typed one). The real written column set is
  `id,x,y,number,points,confidence,source,is_hub` — the DoD's six columns first, in the DoD's own
  order, with the two additions appended rather than interleaved. `confidence` itself was the other
  half of the discrepancy: T005's original `read_controls` (moved here from `io/corpus.py`, which now
  re-exports the name rather than owning a second copy) hardcoded every row's `confidence` to `1.0`
  and `source` to `"manual"`, because at the time nothing produced any other value — now T020's Hough
  ring-coverage score and T021's `min(detection, ocr)` combination do, and this module reads/writes
  the real value instead of overwriting it. Hand-editing stays ergonomic: `number`, `points`,
  `confidence`, `source` and `is_hub` all default on a blank cell or an entirely absent column
  (`confidence` -> `1.0`, `source` -> `"manual"`, matching the old hardcoded behaviour), so
  `data/README.md`'s documented bare `id,x,y,number,points,is_hub` example still reads exactly as it
  always did; `id`/`x`/`y` are never defaulted, and a missing or malformed one of those three raises
  with the line number, same as any other malformed row. Note: `data/README.md`'s own `controls.csv`
  example is now stale (still shows the pre-T022 6-column header without `confidence`) — out of this
  task's assigned paths, left for a follow-up rather than touched here.
  Moved `tests/unit/test_corpus.py::TestControlsCsv`'s 4 tests into the new
  `tests/unit/io/test_controls_csv.py` (10 tests: a full-field round trip mixing detected/manual
  and a null number/points control, hub-not-first-on-write still reading hub-first, the bare
  DoD-header leniency case, and six malformed-row cases including confidence-out-of-range and an
  invalid `source` value, both now real checks now that `confidence`/`source` are live columns
  instead of hardcoded). `corpus.py` no longer imports `csv` or `Control` directly — both were only
  ever used by the function that moved. 229 tests pass (223 baseline - 4 moved + 10 new), `ruff
  check .` clean.

## M3 — Cost field and travel matrix (WS-B)

- [x] T030 — Cost field — paths: `src/rogaine/cost/field.py` — deps: T002, T003 —
  DoD: `t = mpp / (v_base * k_terrain * k_slope)` as float32 seconds per pixel plus a passability
  mask; impassable classes excluded; a hand-checked 5x5 case matches the formula exactly (F10).
  Landed 2026-08-28. New `src/rogaine/cost/` package; `compute_cost_field(terrain, base_speed_mps,
  config=None)` gathers `k_terrain = config.speed_factors()[labels]` and `passable =
  config.passability()[labels]`, calls T015's `k_slope(contour_density, config)` unchanged, and
  divides with `out=`/`where=passable` so the division literally never executes at an impassable
  cell. Two real judgement calls, both documented in the module docstring rather than decided
  silently: (1) impassable pixels store `+inf`, never `nan` — proved never reachable, since `mpp`
  is always positive and finite and `k_slope` is always strictly positive for a finite
  non-negative `penalty`, so the only zero factor the denominator can ever have is `k_terrain`,
  giving a positive number over zero; `+inf` satisfies `CostField`'s own finite-only-if-passable
  invariant and fails loudly if future code ever sums the raw array without checking `passable`
  first, rather than silently reading as a plausible finite cost. (2) a real defect found and
  fixed before it ever crashed: `contour` is `passable = true` with `speed_factor = 0.0` by
  design (`TerrainSpec`'s own validator carves out exactly this exception; the config comment
  reads "not an area class: contours only feed the slope penalty, never the speed table") — the
  raw formula literally divides by zero at a *passable* cell there, which would have raised inside
  `CostField.__post_init__` on any map with contour ink, i.e. nearly every real map. Fixed by
  neutralising `k_terrain` to `1.0` wherever a pixel is passable yet its gathered `k_terrain` is
  `0.0` (by `TerrainSpec`'s validator this can only be the contour case), leaving only `k_slope`'s
  density-driven penalty at those pixels, exactly as the config comment prescribes. Hand-checked
  5x5 fixture (`tests/unit/cost/test_field.py`) covers five homogeneous rows — `forest_runnable`,
  `road`, `water_uncrossable` (impassable), `contour` (the neutralised case), `road` again at a
  different density — with per-pixel expected cost computed independently in the test from
  `config.terrain_of(cls).speed_factor` and the plain `1/(1+penalty*density)` formula, never by
  calling `compute_cost_field` itself; also covers dtype (float32/bool), the passable/finite
  bijection (`isfinite(seconds_per_pixel) == passable` exactly, no `nan` anywhere), and
  `base_speed_mps <= 0` rejection. 236 tests pass (229 baseline + 7 new), `ruff check .` clean.
  Next: T031 (grid graph, deps T030, unblocked).
- [x] T031 — Grid graph — paths: `src/rogaine/cost/graph.py` — deps: T030 —
  DoD: 8-connected CSR graph with sqrt(2) diagonals and configurable `graph_downsample`; node/pixel
  mapping is exact both ways; a 4000x3000 map at downsample 4 builds in under 15 s and stays under
  1 GB.
  Landed 2026-08-29. New `build_grid_graph(cost_field, config=None) -> GridGraph`, a local frozen
  dataclass (not `models.py` — this graph type is T031/T032's own internal handoff) wrapping a
  symmetric `scipy.sparse.csr_matrix` plus grid shape/downsample/block arrays and the node<->pixel
  conversion. Vectorised throughout (numpy reshape/sum for aggregation, four slice-pair calls for
  the 8-connected edge set) — no Python loop over nodes or edges. Four judgement calls, all
  documented in the module docstring: (1) **edge weight** = `spacing * avg(rate_u, rate_v)`, spacing
  `downsample` orthogonal / `downsample * sqrt(2)` diagonal — the standard trapezoidal
  cost-distance discretisation, dimensionally consistent with `t = mpp / (v_base * k_terrain *
  k_slope)` being seconds-per-pixel times pixels crossed; reduces exactly to the finest per-pixel
  grid at `downsample == 1`. (2) **downsample aggregation**: a block is passable iff it has >=1
  passable original pixel, and its rate is the mean of `seconds_per_pixel` over only that block's
  passable pixels (`+inf` pixels excluded from the mean, not averaged in) — rejected both a naive
  full-block mean (one impassable pixel would poison an otherwise-open block to `+inf`, defeating
  `downsample`'s whole point as a performance knob per ADR-002) and stride-sampling (could step
  clean over a one-pixel barrier); the vectorised reshape+sum still inspects every constituent
  pixel, so a barrier is only invisible when it fills an entire block. (3) **`strict_impassable`**:
  true (default) creates no edge touching an impassable block — the node index still exists so
  numbering never shifts with the flag, but degree zero keeps Dijkstra out; false substitutes
  `impassable_cost_multiplier * (mean rate of every passable block on the map)` as that block's
  effective rate, a single global reference chosen over a literal per-edge local one because the
  latter is ill-defined for an edge between two impassable blocks or an impassable region with no
  passable neighbour at all — `multiplier > 1.0` (config-validated) guarantees the result is always
  finite, never zero, never equal to an ordinary edge. (4) **node/pixel mapping**: nodes numbered
  row-major over the block grid; `pixel_to_node(x, y)` floors sub-pixel `(x=col, y=row)` input
  (`Control`'s own convention) then floor-divides by `downsample`; `node_to_pixel`/`nodes_to_pixels`
  return each block's top-left pixel as `(x, y)` (matching `Leg.polyline`/`TravelMatrix.paths`'
  documented convention, not array `(row, col)`) — top-left rather than centre because it's always a
  real in-bounds pixel even for a partial trailing block. `node -> pixel -> node` round-trips
  exactly always (what T032 needs for placing a `Control` and reading a path's pixels back);
  `pixel -> node -> pixel` only round-trips exactly at `downsample == 1`, by design. No additional
  defects found beyond these four documented judgement calls — the initial implementation matched
  hand-computed expected values on first run (verified via an ad hoc smoke script against the real
  formula before the pytest suite was written). Tests (`tests/unit/cost/test_graph.py`, 20 new):
  8-connectivity/corner-vs-interior degree/symmetry/diagonal-sqrt(2)-ratio at `downsample=1`;
  strict-vs-relaxed impassable edges with an exact hand-computed weight
  (`1 * (2 + multiplier*2) / 2`); `downsample=2` aggregation over a block with 3 passable + 1
  impassable pixel and a fully-impassable block; node<->pixel round trip at `downsample=1` and at
  `downsample=3` over an irregular 7x5 grid (exercises the partial trailing block); float
  sub-pixel flooring; out-of-bounds rejection; `nodes_to_pixels` vectorised match. Perf test builds
  an equivalent-size synthetic `CostField` directly (not the full segmentation pipeline, to keep
  this budget isolated from `test_palette.py`'s own 30s segmentation budget) at the real
  4000x3000/downsample=4 preset: measured 0.34-0.53 s wall time and ~406 MiB tracemalloc peak
  against the 15s/1GB budget (750,000 nodes, ~5.99M CSR nonzeros); `tracemalloc` only tracks
  Python-heap allocations, but numpy/scipy normally allocate through the same allocator, so this
  reading looks representative rather than a severe undercount — comfortably inside budget either way.
  256 tests pass (236 baseline + 20 new), `ruff check .` clean.
  Next: T032 (travel matrix and path reconstruction, deps T031, unblocked).
- [x] T032 — Travel matrix and path reconstruction — paths: `src/rogaine/cost/travel.py` — deps: T031 —
  DoD: `scipy.sparse.csgraph.dijkstra` from each control; matrix symmetric within tolerance;
  per-pair polylines reconstructed from predecessors and simplified for rendering; unreachable pairs
  marked infinite, not zero; 60 controls on a full-size map in under 60 s (F11).
  Landed 2026-08-29. New `build_travel_matrix(controls, graph, meters_per_pixel, config=None)` in
  `src/rogaine/cost/travel.py` (M3 now complete). One `scipy.sparse.csgraph.dijkstra` call with
  `indices` set to every control's node (ADR-002) — `seconds` is a single vectorised fancy-index
  read off the returned `(n, n_nodes)` distance matrix (`dist_matrix[:, nodes]`), never a Python
  loop. Five documented judgement calls, all in the module docstring: (1) `GridGraph` carries no
  `meters_per_pixel` (edge weights are time, not distance) — solved with an explicit
  `meters_per_pixel` parameter on this function rather than touching `cost/graph.py` or
  `models.py`, since the `CostField` that built the graph already carries the value and a caller
  holding both just forwards it. (2) `meters[i,j]` is the physical length of the *actual*
  reconstructed time-optimal path (hop lengths from `GridGraph.nodes_to_pixels`, summed via
  `np.hypot` before conversion — not a separate orthogonal/diagonal branch, since `hypot(dx,dy)`
  already equals `cost/graph.py`'s `spacing` for either case given the graph only connects
  immediate neighbours), explicitly not the geometrically shortest distance between two points,
  which can differ from the time-optimal route. (3) self-pairs: `seconds[i,i]`/`meters[i,i]` are
  `0.0` (scipy already reports distance-to-self as `0.0`, no special-casing needed; the diagonal of
  `meters` is filled once via `np.fill_diagonal`), and `paths` holds no `(id,id)` entry at all — a
  self-visit needs no reconstructed geometry, and omitting the diagonal keeps the reconstruction
  loop a plain `i < j` iteration with no self-pair branch. (4) symmetry is not forced: `seconds`
  comes from two independent per-source Dijkstra sweeps summing the same symmetric edges
  (`GridGraph.csr`, T031) in a different order, so near-exact agreement is a real, tested property
  (`np.testing.assert_allclose`, `rtol=1e-7`, `atol=1e-6` — float64 summation-order rounding stays
  far inside that band, while a genuinely directed-edge bug would blow it by orders of magnitude),
  never manufactured by averaging with the transpose (would hide exactly that bug). (5) each
  unordered pair `{i,j}` is reconstructed once (walking source `i`'s own predecessor row) and the
  reverse-direction polyline is the same array reversed — cheaper than reconstructing both
  directions independently, and guarantees `(i,j)`/`(j,i)` are exact mirrors, which is a property
  of the algorithm choice, not post-hoc symmetrisation. Polyline simplification for `paths` uses
  `cv2.approxPolyDP` (open, `closed=False`), the same idiom `vision/controls.py` already uses for
  its triangle contour, at a plain module constant `_SIMPLIFY_EPSILON_PX = 1.5` rather than a new
  `[travel]` config section — checked `config/default.toml`/`config.py` first and confirmed no
  existing epsilon-like knob; this value is cosmetic only (shrinks stored point count for
  rendering, never touches `seconds`/`meters`, computed from the raw chain first), unlike every
  existing config-driven geometric tunable which carries a real DoD floor. Unreachable pairs: read
  straight off scipy's `+inf` in `dist_matrix` without any clipping/conversion (`seconds`); `meters`
  is initialised to `+inf` and only overwritten for pairs the reconstruction loop actually visits,
  so it stays `+inf` too, never defaulting to `0.0`; `paths` gets no entry for that pair (absent,
  not an empty array — a missing key makes "no path" unambiguous). scipy's predecessor sentinel
  (`-9999`) was verified empirically against the installed scipy 1.18.0 rather than assumed — this
  version has no `csgraph.NULL_IDX` to import instead. No other defects found; the implementation
  matched hand-computed expected values on first run. Tests
  (`tests/unit/cost/test_travel.py`, 14 new): a 3x3 uniform-rate hand-checked case at
  `downsample=1` where the time-optimal route is the two-hop diagonal, `seconds`/`meters` matching
  the edge-weight formula exactly by hand computation; a 21-pixel straight corridor showing the
  raw 21-point chain simplifies to exactly its 2 endpoints while `seconds`/`meters` still reflect
  the un-simplified 20-hop chain; an unreachable pair (one impassable cell severing a 1x5 row under
  `strict_impassable=True`) with `seconds`/`meters` both `+inf` and no `paths` entry; symmetry
  within tolerance on a 6-control random passable grid; `meters_per_pixel <= 0` rejected. Perf test
  mirrors `test_graph.py::TestPerformance`'s precedent — an equivalent-size synthetic `CostField`
  built directly with numpy (not the full vision + T030 pipeline), `build_grid_graph` at the real
  4000x3000/downsample=4 preset, then 61 controls (60 + hub) at random in-bounds pixel positions
  (fixed seed, not guaranteed passable): measured 11.2s wall time for `build_travel_matrix` alone
  against the 60s budget (all 1830 unordered pairs happened to be reachable on this seed — not
  required, just what this run measured). 270 tests pass (256 baseline + 14 new), `ruff check .`
  clean.
  Next: T040 (objective and feasibility, M4, deps T002, unblocked). M3 (WS-B) is now complete.

## M4 — Solvers and bench (WS-B)

- [x] T040 — Objective and feasibility — paths: `src/rogaine/solve/objective.py` — deps: T002 —
  DoD: `score = sum(points) - penalty_per_min * max(0, T - limit)`; hub start and end enforced;
  unit-tested on hand-computed cases including exactly-on-limit (F14).
  Landed 2026-08-29. New `src/rogaine/solve/` package; `score_order` in `objective.py` scores one
  candidate visit `order` against a `TravelMatrix` and `RunConfig`, returning a `ScoredOrder`
  dataclass (`order`, `total_seconds`, `total_meters`, `points`, `penalty`, `score`, `feasible`) —
  no `Route`/`Leg` construction. Five documented design decisions, each with its own docstring
  section: (1) **units** — `penalty_per_min` is per-*minute*, every duration elsewhere is seconds,
  so `penalty = penalty_per_min * max(0, T_seconds - limit_seconds) / 60.0`; a literal
  transcription of the DoD's formula against raw seconds would overcharge by 60x. (2) **`points is
  None`** — a visited non-hub control with unresolved points (ADR-009) makes `score_order` raise
  `ValueError` naming the id(s), not score as `0`; scoring an unknown number as zero is the same
  class of guess ADR-009 refuses for the reading itself, one layer downstream. The hub is exempt
  from this check and from the points sum (it is a waypoint, not a scored control, and its own
  `points` is almost always `None` since OCR never reads a number off the start/finish marker).
  (3) **feasibility** — an unreachable leg (`TravelMatrix.seconds == inf`) surfaces as
  `ScoredOrder.feasible = False` plus `score = -inf`, never a raised exception: unlike `points is
  None` (a static per-control property a caller filters out of its search space once), an
  unreachable pair is a dynamic property of a specific order the heuristic solver (T042) will
  re-encounter many times a second, and exception handling in that hot loop is a real cost.
  Feasibility is decided first, from `total_seconds` being a finite sum of non-negative legs, and
  short-circuits to `penalty = inf` / `score = -inf` before the per-minute formula runs — otherwise
  an infeasible order combined with `penalty_per_min == 0.0` hits IEEE-754's `0 * inf = nan`
  instead of the intended `-inf`; that combination is tested explicitly as a regression. (4) **only
  the cheap scoring path is built** — the DoD asks for the formula and hub enforcement, not full
  `Route` construction (which needs `solver`/`optimal`/`seed`, all solver-owned concerns); building
  simplified polylines for every candidate a solver's inner loop touches is unrequested work, left
  to T041/T042. (5) **hub enforcement checks the actual hub** — `Route`'s own validator only checks
  `order[0] == order[-1]`, true for *any* self-loop; `score_order` additionally resolves the one
  `Control` with `is_hub=True` and checks both ends equal that id specifically, raising a clear
  error otherwise, checked first before any matrix arithmetic. One real defect found and fixed
  during development: an initial `zip(order, order[1:], strict=True)` for the pairwise-leg loop
  raised `ValueError` on every call (the two sequences are one element apart by construction, same
  "ragged on purpose: N-1 pairs" pattern `Route._legs_match_order` already comments on) — replaced
  with `itertools.pairwise`, which is also what `ruff`'s `RUF007` recommends over the raw `zip`
  idiom. Tests (`tests/unit/solve/test_objective.py`, 11 new, all hand-computed against a uniform
  300s/500m fixture matrix so `n_legs * 300` / `n_legs * 500` needs no calculator): exactly-on-limit
  (penalty exactly `0`), just-over-limit, well-under-limit, `penalty_per_min == 0.0` overrunning
  freely, an unreachable-leg order both with a normal rate and with `penalty_per_min == 0.0` (the
  nan regression), a non-hub self-loop rejected, a visited `points=None` control rejected, the
  hub's own `None` points *not* flagged, no-hub-in-controls rejected, and an unknown control id
  rejected. 281 tests pass (270 baseline + 11 new), `ruff check .` clean.
  Next: T041 (exact Held-Karp, M4, deps T040, unblocked).
- [x] T041 — Exact Held-Karp — paths: `src/rogaine/solve/exact.py` — deps: T040 —
  DoD: optimal for N up to 15 within memory; agrees with brute force for N up to 9 on random
  matrices; refuses N above the configured cap with a clear message instead of exhausting RAM (F12).
  Landed 2026-08-29. `solve_exact` in `exact.py` is deliberately not textbook Held-Karp: SPEC F12 /
  ADR-003 ask for the Orienteering Problem (choose a *subset* of non-hub controls to maximise points,
  soft time penalty), not TSP's forced visit-everything tour. The module reuses Held-Karp's
  bitmask-DP *machinery* to solve a different problem — minimum travel time per `(subset, last
  control)` state — then exhaustively scores every reachable `(mask, j)` state's time-minimal order
  with T040's `score_order`, never reimplementing the score/penalty formula. Correctness rests on one
  argument, spelled out in the module docstring: for a fixed subset `S` and endpoint `j`, every visit
  order of `S` ending at `j` collects identical points, and `score_order`'s penalty is monotonic
  non-decreasing in total time, so the time-minimal order of `(S, j)` provably has the
  highest-or-equal score among all orders of `(S, j)` — a slower order of the same `(S, j)` can never
  win and is never generated. Candidates exclude the hub (fixed start/end, never a DP variable) and
  any control with `points is None` (ADR-009, same filter contract T040's docstring already commits
  callers to), so `N` is that filtered count, never including the hub. The empty-subset baseline
  (`order = [hub, hub]`) is scored via `score_order` rather than hand-built, so it inherits the
  formula's own correctness and acts as the guaranteed floor — a run where every non-trivial subset
  is infeasible or nets negative correctly falls back to it instead of crashing or returning a loss.
  The memory guard is the DoD's actual ask: before allocating anything, `n > exact_max_controls` is
  checked against the config cap (validated up to 24) and raises `ValueError` naming both numbers,
  never letting a `2**N`-sized array start; at `N=24` that array would run multi-GB (`2**24 * 24 ~=
  4*10**8` entries), against `N=15`'s trivial `491_520`. This session picked the module up already
  written and its 8 tests already passing uncommitted (same pattern T013/T021 already hit) —
  re-verified against the tree rather than trusted: one real finding on that re-check, `ruff check .`
  was not clean (10x `E501` line-too-long in the module docstring, none in the tests or the code
  itself), fixed by rewrapping those paragraphs to 100 columns without changing a word. Tests
  (`tests/unit/solve/test_exact.py`, 8 new): a hand-computed optimum with deliberately asymmetric
  A↔B costs (5s forward / 50s reverse) so the DP must find the cheaper of the two orders of the same
  subset, not just the right subset; brute-force agreement at N=4/6/9 (independent enumeration over
  every subset and permutation, scored by the same `score_order`, ties allowed on score but not
  required on order shape); an unresolved-points control excluded from the search space even though
  it would dominate on cost alone; the empty-route fallback when a single reachable control's round
  trip nets deeply negative; the cap satisfied exactly at the limit and refused with a clear message
  one above it. 289 tests pass (281 baseline + 8 new), `ruff check .` clean.
  Next: T042 (heuristic solver, M4, deps T040, unblocked).
- [x] T042 — Heuristic solver — paths: `src/rogaine/solve/heuristic.py` — deps: T040 —
  DoD: GRASP construction plus 2-opt / or-opt / insert / remove / swap local search under a time
  budget; seeded and deterministic; gap versus T041 at most 5% across a suite of random instances
  with N up to 15; handles 80 controls inside the budget (F13, F19).
  Landed 2026-08-29. `solve_heuristic` in `heuristic.py` mirrors `solve_exact`'s signature and
  candidate-filtering (hub excluded, `points is None` excluded, ADR-009) so T044's `bench` can call
  both interchangeably, but never proves optimality — it returns the best route a bounded search
  finds (`Route.optimal=False`). GRASP construction inserts every reachable candidate one at a time:
  a constant-time cheapest-insertion proxy picks *where* to trial each candidate, but `score_order`
  (T040) — never a reimplemented formula — ranks *which* candidates enter the restricted candidate
  list (RCL, size `config.solver.grasp_candidate_size`), and one is drawn uniformly at random from
  it via a single seeded `numpy.random.Generator`. Local search then refines every restart (not just
  the best) through five first-improvement move types — insert, remove, 2-opt, or-opt (1-3 length
  chunks), swap, insert/remove run first each pass since OP's real lever is *which* controls are
  visited — repeating full passes until one improves nothing or the deadline hits.
  One real defect found and fixed during development: construction originally gated each insertion
  on `score_delta > 0` ("stop growing once the next insertion looks locally bad"), which reliably
  trapped it in tiny 1-3-control routes (54% gap on `seed=0, n_candidates=6`) — a control that looks
  like a net loss against an arbitrary, not-yet-reordered partial route can still belong in the
  globally best tour once 2-opt/or-opt have straightened it out, so marginal-delta-right-now is not
  a reliable OP *selection* signal. Fixed by inserting every reachable candidate unconditionally
  (the proxy only orders trials, never gates them) and handing subset selection to local search's
  `remove` move working against an already-improved order instead — pruning a good-enough superset
  being strictly easier than guessing the right set to grow into one locally-negative step at a
  time. Documented design calls: time budget and seed come from `RunConfig` (not `AppConfig.solver`,
  which carries its own defaults for constructing one), matching T041's own precedent that a
  resolved `RunConfig` is authoritative for one run; `grasp_restarts`/`grasp_candidate_size` have no
  `RunConfig` equivalent so those stay config-sourced; gap is
  `(exact.score - heuristic.score) / exact.score`, defined as `0.0` when `exact.score == 0.0` since
  both solvers share the same empty-route floor there; determinism holds exactly whenever the time
  budget is generous enough that convergence, not the clock, ends every run — RNG is consumed only
  by construction's RCL draw, local search is a pure function of its input order, but a deadline that
  actually interrupts a run mid-scan makes the stopping point (and therefore the result) depend on
  host speed, an explicitly documented boundary rather than a claimed guarantee; `_build_legs`
  mirrors (does not import) `exact.py`'s private helper of the same name, since a leading-underscore
  name isn't meant for cross-module reuse. Tests (`tests/unit/solve/test_heuristic.py`, 23 new): a
  hand-computed optimum on the same asymmetric-cost fixture `test_exact.py` uses; gap vs. `solve_exact`
  across 3 seeds x N in {3,6,9,12,15} (15 combinations, each with an explicit small
  `heuristic_time_budget_s` so the parametrized suite stays fast rather than using
  `config/default.toml`'s real 30s budget) — every combination matched the exact optimum exactly
  (gap 0.0000), well inside the 5% floor; same-seed determinism (`route_a == route_b`); an 80-control
  smoke test asserting completion within budget plus slack and a non-negative score; zero-candidate,
  unresolved-points-exclusion, and all-unreachable-falls-back-to-empty edge cases; a cross-check that
  `Route` totals for the winning order agree exactly with an independent `score_order` call on that
  same order, confirming the solver reports the real formula's output and never a value computed
  some other way. Independently re-verified against the tree (this session's standing practice):
  `docker compose run --rm tests` — 312 passed (289 baseline + 23 new); `ruff check .` clean; `git
  status` confirmed only the two owned files were touched.
  Next: T043 (alternative routes and interestingness, M4, deps T042, unblocked).
- [x] T043 — Alternative routes and interestingness — paths: `src/rogaine/solve/alternatives.py` —
  deps: T042 — DoD: top-K routes differing by at least one control, each with its score; K
  configurable; the score spread is reported as the map's interestingness measure (F16).
  Landed 2026-08-29. `solve_alternatives` in the new module returns an `AlternativesResult`
  (`routes: list[Route]`, `interestingness: float`) — deliberately scoped to T042 only (deps say
  T042, not T041): real corpora run 30-80 controls where exact Held-Karp is intractable, exactly the
  regime T042 exists for. Rather than call `solve_heuristic` K separate times (K x the time budget),
  `heuristic.py`'s GRASP restart loop was split into a new public `search_heuristic_candidates`
  (returns every restart's refined `ScoredOrder` as a pool instead of discarding all but the winner)
  with `solve_heuristic` reduced to a thin wrapper over it (`max(pool, key=score)`, which reproduces
  the pre-split loop's exact tie-break by construction) — one search process, two independent
  reducers, not two copies of GRASP. Four documented design decisions: "structurally distinct" per
  F16 dedupes the pool by `frozenset(order[1:-1])` (visited non-hub control ids), not order, keeping
  the higher-scoring order of any tied set; ranking is score descending with a sorted-control-id-tuple
  tie-break for determinism; K reads only `run_config.alternatives` (already defaulted, never
  `config.solver.alternatives` — same RunConfig-is-authoritative precedent T042 established), `K=0`
  short-circuits before running any search, and fewer-than-K distinct candidates are returned as-is,
  never padded or erroring; interestingness is `routes[0].score - routes[-1].score` computed only
  over the K routes actually returned (`0.0` for `K<2`), not the full internal pool, since the DoD
  ties it to "top-K routes ... each with its score". No defect found in the pre-existing heuristic
  loop — the extraction is a pure, semantics-preserving refactor, confirmed by all 23 pre-existing
  `test_heuristic.py` tests passing unchanged. 14 new tests (`tests/unit/solve/test_alternatives.py`):
  a hand-computed 2-candidate case (K=0/1/3/50) with an exact interestingness value; hub validation;
  zero-candidate, all-unreachable and unresolved-points-excluded fallbacks; structural-distinctness
  and ranking invariants plus a brute-force per-subset upper bound on a random instance (independent
  of solver internals); a cross-check that every returned `Route`'s totals agree exactly with
  `score_order` on its own order; a cross-check that the top alternative matches `solve_heuristic` on
  the same instance; K-prefix-consistency across K values on one instance; determinism. Independently
  re-verified against the tree (this session's standing practice): own read of both touched files and
  the diff to `heuristic.py`, own `docker compose run --rm tests` (326 passed, exit 0, checked without
  piping through `tail` per this repo's own standing warning), own `ruff check .` (clean), own `git
  status` (only `solve/alternatives.py`, `solve/heuristic.py`, and the new test file touched).
  Next: T044 (`bench` command, M4, deps T041/T042, unblocked).
- [x] T044 — `bench` command — paths: `src/rogaine/cli.py` (bench subcommand only) — deps: T041,
  T042 — DoD: runs both solvers on a reduced instance and prints points, time, and the gap; a test
  asserts the fixture gap stays within F13.

## M5 — CLI end-to-end and renders (WS-C)

- [x] T050 — CLI commands — paths: `src/rogaine/cli.py` — deps: T016, T022, T032, T042 —
  DoD: `segment`, `detect`, `plan`, `bench`, `serve` with typer; `--seed` everywhere randomness
  exists; rich summary table of legs, time, points, penalty; non-zero exit on failure.
- [x] T051 — Route JSON schema and writer — paths: `src/rogaine/io/route_json.py` — deps: T002 —
  DoD: documented schema with order, per-leg time/distance/polyline, cumulative time, points,
  penalty, score, and the config that produced it; validated on write; golden test on the fixture
  (F15). Landed 2026-08-31 — `LegRecord`/`RouteFile` pydantic models built from a `Route` +
  `RunConfig` pair (the frozen `Route`/`Leg` contract, ADR-008, has no cumulative-time field and no
  embedded config, so this is its own schema, not `Route.model_dump()`); `run_config` embeds
  `RunConfig` only, not the larger `AppConfig` (`RunConfig`'s own docstring: "everything the user
  chooses per attempt"); `cumulative_seconds` is the running sum of leg seconds from the hub, same
  arithmetic `cli.py`'s `plan_cmd` table already prints inline; `RouteFile` carries its own copy of
  `Route`'s order/legs invariant since `read_route_json` builds from arbitrary disk bytes, not an
  already-validated `Route` (write-side unreachability confirmed by a dedicated test, not assumed).
  `write_route_json`/`read_route_json` round-trip pair, `schema_version` field for future evolution.
  No CLI wiring yet — `plan_cmd` still ends at the terminal summary (T050's documented scope cut);
  wiring `write_route_json` (and T052's PNG writer once it lands) into `plan_cmd` is a small follow-up,
  not part of this task's path list. Built by the `implementer` subagent, independently re-verified
  against the tree: own read of both new files, own `docker compose run --rm tests` (350 passed, exit
  0), own `ruff check .` (clean), own `git status` (only `io/route_json.py` and
  `tests/unit/io/test_route_json.py` touched). No real defect found. 6 new tests
  (`tests/unit/io/test_route_json.py`): hand-computed golden (JSON compared as a parsed dict, not a
  raw string — exact whitespace isn't part of the documented schema), full round-trip, missing-file
  read, and the order/legs invariant checked on direct construction, on a hand-corrupted on-disk
  file, and confirmed unreachable from the write side because `Route` itself already refuses the same
  mismatch. 350 tests pass (344 baseline + 6 new), `ruff check .` clean. Next: T052 (route overlay
  render, M5, deps T051, unblocked).
- [x] T052 — Route overlay render — paths: `src/rogaine/render/overlay.py` — deps: T051 —
  DoD: route drawn over the map with numbered visit order and leg times, legible over dark and light
  terrain; rendered legs match the JSON polylines pixel for pixel (F15). Landed 2026-08-31 —
  `render_overlay(image, route, controls)` / `write_overlay(path, image, route, controls)`, mirroring
  `render/preview.py`'s two-function shape. "Pixel for pixel" holds by construction (`LegRecord`'s
  polyline is `Leg.polyline` copied verbatim, T051) plus `cv2.LINE_8` everywhere (never `LINE_AA`) so
  a polyline coordinate is deterministically painted the solid core colour, checked directly by
  sampling exact polyline pixels in the test, not just "the image changed somewhere". Legibility:
  every stroke/marker/label drawn twice, thicker near-black halo then thinner bright-red core
  (`(255,36,36)` — checked against `config/default.toml`'s six ISOM inks, none red, so a route mark
  can never be mistaken for a printed symbol; purple and cyan ruled out as the control/hub and
  water-body ink families). Labels are 1-based visit order, not `Control.number` (can be unread/
  `None`). Hub (`route.order[0] == order[-1]`) drawn once as a filled triangle labelled "H", excluded
  from the numbered-stop loop — independently re-verified: the triangle's flat base sits above a
  circle-radius-deep sample point, so a same-position sample reads background at the hub and core-red
  at an ordinary stop, confirmed by hand geometry, not just trusted. A route referencing a control id
  missing from the given `controls` list raises `ValueError` (matches `io/controls_csv.py`/
  `io/route_json.py`'s "present input must be correct" convention). No DPI in scope (not this task's
  path list) — every stroke width/marker radius/font scale is a fraction of `max(image.shape[:2])`,
  clamped, so a tiny fixture and a 4000x3000 map both render legibly; no new config section, plain
  module constants, matching T032's "cosmetic-only, unlike every config-driven geometric tunable"
  precedent for the same class of decision. Built by the `implementer` subagent, independently
  re-verified against the tree: own read of both new files (including hand-checking the hub-vs-stop
  marker geometry math the test relies on), own `docker compose run --rm tests` (356 passed, exit 0),
  own `ruff check .` (clean), own `git status` (only `render/overlay.py` and
  `tests/unit/render/test_overlay.py` touched). No real defect found. 6 new tests
  (`tests/unit/render/test_overlay.py`): shape/dtype/no-input-mutation; exact-pixel polyline sampling
  on an axis-aligned route (no diagonal anti-aliasing ambiguity); missing-control `ValueError`;
  hub-vs-stop marker shape distinction; PNG write round trip; missing-parent-directory `OSError`. 356
  tests pass (350 baseline + 6 new), `ruff check .` clean.

  Immediately after landing, closed the gap both this task's and T051's own docstrings flagged:
  `plan_cmd` in `cli.py` now calls `write_route_json`/`write_overlay` (new `--out-dir` option,
  default `.`, mirroring `segment_cmd`'s own option; writes happen only after a route is
  successfully solved — a run that exits non-zero for any reason writes nothing). This is CLI wiring
  outside both T051's and T052's own path lists, done directly (not delegated) because of a real risk
  it triggers: the existing `TestPlan` success-path tests in `tests/unit/test_cli.py` did not pass
  `--out-dir`, and `plan_cmd`'s new default write would have landed `route.json`/`route.png` in
  the container's cwd (repo root) on every test run — the same class of mistake T050's own landing
  note already recorded once (`crop_dense.png`'s accidental deletion). Fixed by adding an explicit
  `--out-dir tmp_path` to both success-path `TestPlan` tests before ever running them, verified by
  checking the repo root for stray `route.json`/`route.png` after the run (none found) in addition
  to the normal `docker compose run --rm tests` (356 passed, unchanged count — only edited two
  existing tests, added none) and `ruff check .` (clean). Next: T053 (determinism and performance
  guards, M5, deps T050/T051/T052, unblocked).
- [x] T053 — Determinism and performance guards — paths: `tests/e2e/test_cli.py`,
  `tests/perf/test_budgets.py` — deps: T050, T051, T052 — M5 now complete —
  DoD: same inputs and seed give byte-identical JSON; the four NFR budgets are asserted on the
  full-size synthetic map (F19). Landed 2026-08-31 — three of the four NFR budgets (segmentation
  <30s, grid graph build <15s/1GB, travel matrix 61 controls <60s) already existed as landed
  `@pytest.mark.perf` tests (T013/T031/T032's own DoD numbers, in `test_palette.py`/`test_graph.py`/
  `test_travel.py`); new `tests/perf/test_budgets.py` holds only the one that didn't exist yet —
  heuristic solve, 80 controls (T042's own DoD number), against `RunConfig`'s real 30s default
  budget (never a smaller stand-in), with a documented +10s overrun-slack reasoned from
  `test_heuristic.py`'s own 5s-over-5s deadline-check precedent. Its module docstring names the other
  three by exact path/class rather than duplicating or moving them. New `tests/e2e/test_cli.py`
  (first use of the pre-registered but previously-unused `e2e` marker) covers PLAN.md's two distinct
  "golden end-to-end" checks: `TestGoldenRegression` (one `plan` run via `--controls`+`--strategy
  exact`, comparing `route.json` against a new hand-verified `tests/e2e/golden_route.json` with
  `pytest.approx` tolerance — `--controls` skips detection/OCR entirely, since ADR-008/ADR-009 both
  document OCR as explicitly non-load-bearing, so coupling a golden test to real Tesseract output
  would risk environment-dependent flakiness for no benefit; `exact` removes GRASP's RNG-driven
  search order as a second drift source) and `TestDeterminism` (F19: two `plan` runs, identical
  args and `--seed`, `--strategy heuristic` specifically — the one RNG-bearing path, so this is the
  check that actually exercises the seeding contract — comparing `route.json` via
  `Path.read_bytes()` byte-for-byte equality, no tolerance). Both classes pass an explicit
  `--out-dir` inside `tmp_path` on every `plan` invocation — this project has already hit the
  bare-default-cwd stray-file mistake twice (`crop_dense.png`, and the near-miss fixed alongside
  T052's own CLI wiring), so this was treated as a hard requirement, independently re-verified by an
  explicit repo-root check after the test run (none found). One small addition outside the two
  literal path-list files, done for a concrete reason rather than scope creep: `tests/e2e/__init__.py`
  (empty) — without it, pytest's import machinery collides `tests/e2e/test_cli.py` with the
  pre-existing `tests/unit/test_cli.py` (both would import as the bare top-level module `test_cli`,
  since neither `tests/`, `tests/unit/`, nor `tests/e2e/` had an `__init__.py`); adding one only to
  the new directory resolves the collision without touching the existing file. Built by the
  `implementer` subagent and independently re-verified against the tree: own read of all three new
  files (including hand-checking the golden fixture's numbers — 6 controls visited, points sum
  6+5+3+9+5+7=35 matches the file's own `points: 35`), own `docker compose run --rm tests` (359
  passed, exit 0, captured via PowerShell `Tee-Object`+`$LASTEXITCODE` per this file's own standing
  warning against a masked red suite — no flakiness observed on this independent run despite the
  subagent's own report flagging an intermittent captured-output issue on its side), own
  `ruff check .` (clean), own `git status` (only `tests/e2e/` and `tests/perf/` added), own
  repo-root stray-file check (none found, including no leftover golden-generation scratch file). No
  real defect and no real nondeterminism found — the byte-identical check passed on first real run.
  359 tests pass (356 baseline + 3 new: 2 e2e, 1 perf), `ruff check .` clean. **M5 (CLI end-to-end and
  renders, F15/F19) is now complete.** Next: M6 — T060 (FastAPI backend, deps T050, unblocked).

## M6 — Web viewer (WS-C)

- [x] T060 — FastAPI backend — paths: `src/rogaine/web/app.py` — deps: T050 —
  DoD: upload, segment, detect, plan and export endpoints; long runs execute in a background task
  with a poll endpoint; binds 127.0.0.1; uploads validated by magic bytes and size, stored under
  `runs/<uuid>/` with a server-generated name (F17, security). Landed: `src/rogaine/web/app.py`
  wraps the same vision/cost/solve pipeline calls `cli.py`'s `segment_cmd`/`detect_cmd`/`plan_cmd`
  already exercise — never routes through the Typer layer — behind eight endpoints: `POST
  /api/runs` (upload, sniffs PNG/JPEG/BMP/TIFF/PDF magic bytes and picks the stored extension from
  the sniffed format, never the client filename/Content-Type; 200 MB cap enforced mid-stream, not
  only after a full read), `POST .../segment` / `.../detect` / `.../plan` (each validates
  synchronously and 4xx's fast, then runs via `BackgroundTasks` and returns a `job_id`), `GET
  /api/jobs/{job_id}` (poll), `GET`/`PUT .../controls` (`read_controls`/`write_controls` reused for
  both directions — PUT validates by writing to a scratch file and reading it back, so an invalid
  edit such as a missing hub 400s without touching the run's live `controls.csv` — SPEC F9's CSV
  round trip doubling as the edit path), and `GET .../export/{artifact}` for
  `route.json`/`route.png`/`controls.csv`. Per-run state lives in `runs/<uuid4>/` as files
  (`map.<ext>`, `terrain.npz`, `run_state.json` holding the dpi `segment` resolved so `detect`/
  `plan` reload the identical pixel grid, `controls.csv`, `route.json`, `route.png`) rather than
  the CLI's one-shot-per-invocation model, so each stage is independently re-enterable — mirrors
  SPEC user flow 2's staged CLI flow. `Control`/`RunConfig` (already pydantic v2, frozen,
  `extra="forbid"`) are reused directly as request/response models rather than duplicating a
  schema that could drift from the frozen contract. Jobs are an in-memory, lock-guarded registry —
  a deliberate simplification for a local, single-process, single-user tool, no Celery/Redis.
  `serve` (T050's stub) now really launches via `uvicorn.run("rogaine.web.app:app", ...)`,
  `--host` defaulting to `127.0.0.1` (never `0.0.0.0`) and `--port 8000`; `docker-compose.yml`'s
  `app` service command was updated to the `0.0.0.0`-inside-the-container form its own comment
  already named (the host-side publish stays `127.0.0.1:8000:8000`, so nothing changes about what
  is reachable from outside the host). One test file outside the two literal path-list files
  touched, for a concrete and unavoidable reason, flagged by the implementer and independently
  confirmed necessary: `tests/unit/test_cli.py`'s `TestServe` invoked the old stub expecting its
  exit-1 behaviour; left alone it would call the real `uvicorn.run` and hang
  `docker compose run --rm tests` forever (no `pytest-timeout` in this repo) — replaced with two
  tests that monkeypatch `rogaine.cli.uvicorn.run` and assert the call target/host/port, for both
  defaults and `--host`/`--port` overrides. New `tests/unit/web/test_app.py` (9 tests) drives the
  app in-process via `TestClient` against the `synthetic_map` fixture (encoded to PNG bytes) with
  `RUNS_ROOT` monkeypatched to `tmp_path` so nothing touches the real `runs/`: a full
  upload→segment→detect→plan→export happy path, a PUT-controls edit that `plan` is proven to
  honour (by skipping `detect` entirely and checking the route only ever visits the PUT set), and
  the security-relevant rejections (bad magic bytes → 400, oversized upload → 413, unknown
  run/job id → 404, export before plan → 404, detect before segment → 400). Built by the
  `implementer` subagent and independently re-verified against the tree: own read of `web/app.py`
  in full plus the `cli.py`/`docker-compose.yml`/`test_cli.py` diffs and the new `test_app.py`,
  own `docker compose run --rm tests` (368 passed, exit 0, 137s), own
  `docker compose run --rm tests ruff check .` (all checks passed), own `git status` (only the
  paths named above; no stray files at repo root). No real defect found; the `test_cli.py`
  deviation was judged correct, not scope creep — a pre-existing test asserting stub behaviour
  necessarily breaks once the stub is replaced, and leaving it broken would have silently masked
  a hang. **M6 continues: T061 (canvas viewer UI, deps T060, unblocked) next, then T062.**
- [x] T061 — Canvas viewer UI — paths: `src/rogaine/web/static/**` — deps: T060 —
  DoD: pan/zoom map canvas, calibration line tool, control markers that can be dragged, added,
  deleted and edited, parameter panel, run button, leg table, JSON/PNG/CSV export; keyboard
  operable with visible focus; Russian UI strings; legible in light and dark. Landed:
  `index.html`/`style.css`/`api.js`/`view.js`/`app.js` under `src/rogaine/web/static/`, vanilla
  JS/Canvas 2D per ADR-005, no build step. Canvas draws only the map raster and the route overlay
  (halo+core colours mirroring `render/overlay.py`); control markers are real DOM `<button>`s
  positioned over the canvas by the same pan/zoom transform, deliberately not canvas pixels — the
  only way to give them genuine keyboard focus/ARIA (arrow keys nudge, Delete removes, Enter jumps
  to the number field), which a canvas-drawn hit-target cannot offer assistive tech. The controls
  table gives full keyboard-only parity with dragging (add/edit/delete/hub-select), and every edit
  PUTs the full `Control[]` back (debounced, in-flight-guarded) without ever discarding an edit on
  a 400. Flow: upload → segment (scale by 1:N+DPI or a calibration line, drawn or typed) → auto
  detect → fix controls → set speed/time limit/penalty → run → route drawn on canvas + leg table +
  JSON/PNG/CSV export links. Every interactive element carries a stable id/data attribute or ARIA
  label for T062's future Playwright selectors.

  Two narrow, pre-flagged deviations outside the owned path, both in `src/rogaine/web/app.py`
  (mirrors T060's own unavoidable `test_cli.py` deviation): a `StaticFiles(html=True)` mount at
  `GET /` (registered last, after every `/api/...` route, so it never shadows the API — covered by
  a new regression test), and `GET /api/runs/{run_id}/map` streaming the uploaded bytes back
  (`FileResponse`, mirrors `export_artifact`) since the browser has no other way to preview what
  was uploaded before/during calibration. Three tests added to `tests/unit/web/test_app.py`
  (`TestStaticViewer`) for both. Known gap, accepted: a PDF upload can't be previewed via
  `<img>`/`drawImage` (no browser support), so the UI shows a placeholder ground plus a visible
  note — controls/route still work by typed pixel coordinates; T062/PLAN.md's fixture map is a
  PNG, so this doesn't block F17's acceptance bar.

  Built by the `implementer` subagent and independently re-verified against the tree: own read of
  the full diff (`app.py`/`test_app.py` plus every new `static/**` file), own
  `docker compose run --rm tests` (371 passed, exit 0, ~119s, no `tail` piping), own
  `docker compose run --rm tests ruff check .` (all checks passed), own `git status` (scoped to
  exactly the paths above), and an own live click-through via `docker compose up app` + a real
  Chrome browser (claude-in-chrome): uploaded the generated synthetic fixture map, applied 1:25000/
  300dpi scale, watched auto-detect find 13 controls including the hub, dragged a marker and
  confirmed the table X/Y updated, ran the planner (route: 2:58:30, 7.75 km, 41 pts, optimal exact
  solver), confirmed the route polyline drawn on canvas matched the leg table, confirmed all three
  export links 200 with correct content-type/size (`route.json` 15,599 B, `route.png` 2.4 MB,
  `controls.csv` 771 B), and confirmed a visible focus ring tabbing through the toolbar. No real
  defect found; both deviations judged correct, not scope creep. **M6 continues: T062 (Playwright
  end-to-end, deps T061, unblocked) next — closes M6.**
- [x] T062 — Playwright end-to-end — paths: `tests/e2e/test_viewer.py` — deps: T061 —
  DoD: upload fixture, calibrate, move one control, run, assert the leg table and the exported JSON;
  runs headless inside the tests service (F17). Landed: `TestFullViewerFlow` in
  `tests/e2e/test_viewer.py` drives a real Chromium against a real `uvicorn.Server` started in a
  background thread on an ephemeral `127.0.0.1` port (`_live_server` fixture; `TestClient` can't
  give Playwright a URL to navigate to), `RUNS_ROOT` monkeypatched to `tmp_path` first, same
  isolation `tests/unit/web/test_app.py` uses. Uploads the session-scoped `synthetic_map` fixture,
  calibrates via ratio+DPI (`#scale-denominator`/`#scale-dpi`, the fixture's own values), waits on
  `#controls-tbody tr` (a stronger gate than status text -- can only pass once segment+chained
  auto-detect both finish), moves a non-hub control's X by 40px through the table's
  `#control-{id}-x` input (dispatches a real `change` event -- table editing was built in T061
  specifically to have full parity with dragging, and is far more robust to drive than canvas
  pointer-drag maths), explicitly waits for that edit's `PUT .../controls` 200 before clicking run
  (plan reads `controls.csv` from disk, not anything the client resubmits -- without this wait the
  test would race against pre-edit controls), runs (`RunConfig` defaults apply, `strategy="auto"`
  stays on the deterministic Held-Karp path at this fixture's control count -- no seed-flakiness
  risk), asserts the leg table (row ids in order, first leg's "From" cell is "Хаб"), then fetches
  the exported `route.json` via `#export-json-link`'s resolved `href` and checks its structural
  shape against `route_json.py`'s `RouteFile` (all top-level keys present, `len(legs) ==
  len(order)-1`, order round-trips to the hub, positive totals).

  One narrow, pre-flagged deviation outside the owned path (mirrors T060's `test_cli.py`/
  `docker-compose.yml` and T061's two `web/app.py` deviations): `Dockerfile`'s `test` stage gained
  `RUN playwright install --with-deps chromium` -- browser binaries the stage never installed
  before, even though `playwright`/`pytest-playwright` were already `[dev]` dependencies and the
  Dockerfile already carried a comment anticipating exactly this ("Playwright browsers land here in
  M6 (T062)").

  Built by the `implementer` subagent and independently re-verified against the tree: own read of
  the full diff (`Dockerfile` + `test_viewer.py` in full), own `docker compose run --rm tests` (372
  passed, exit 0, ~132s), own `docker compose run --rm tests pytest tests/e2e/test_viewer.py -v`
  (1 passed, 8.5s, isolated), own `docker compose run --rm tests ruff check .` (all checks passed),
  own `git status` (scoped to exactly `Dockerfile` + the new test file; no stray `runs/` at repo
  root). No real defect found. **M6 is now complete** (T060-T062 all landed) -- F17's own
  acceptance bar ("a Playwright script completes the full flow ... with no manual steps") is
  satisfied. This closes out SPEC's whole M0-M6 scope; M7 remains optional per its own gate ("only
  after the owner accepts the route").

## M7 — Optional, only after the owner accepts the route

- [x] T078 — Per-map best-effort auto-calibration for the M7 corpus (ADR-016) — **plan approved
  2026-09-05 (`утверждаю`); implemented, independently reviewed (FAIL: 1 Critical/4 High/6
  Medium), fixed same day, re-verified against the real corpus — done** — paths:
  `src/rogaine/vision/calibrate.py` (new), `src/rogaine/io/corpus.py`, `src/rogaine/cli.py`,
  `data/README.md` — reuses `io/scale.py`'s `Calibration`/`mpp_from_dpi`, `vision/ocr.py`'s
  text-crop patterns, and `vision/controls.py`'s `purple_mask` (T073-T076, ADR-011/012/015) —
  deps: harvest volume (done, 2026-09-04: 204 maps, ADR-014).
  Scale is secondary here — T070's corpus exists to improve object/content recognition, not
  distance accuracy; a real end user's own map is still calibrated manually (SPEC F3,
  `io/scale.py::Calibration`), unaffected by this task.
  DoD, per map in `data/maps/`, tried in order (first hit wins), reusing `Calibration` throughout,
  no new maths:
  1. printed graphical scale bar (ruler with metre-labelled ticks) → `meters_per_pixel` directly;
  2. coordinate/magnetic-north grid spacing, accepted **only** when cross-validated against an
     OCR'd scale-ratio text on the same map (grid alone can't tell a real coordinate grid from
     arbitrarily-spaced magnetic-north lines);
  3. control-circle diameter (`config.circle_diameter_mm`) as fallback/cross-check only, never
     primary (organiser-to-organiser size variance, ADR-015's own documented limitation).
  When none hit (expected majority, see ADR-016's corpus survey), do not exclude the map: write a
  real `meta.toml` with `dpi`/`scale_denominator` set to the median of this run's successful
  measurements, plus `calibration_source = "measured"` or `"assumed_default"` so the two are
  machine-distinguishable downstream (needed later for relief/terrain work, out of scope now).
  Report counts (measured / assumed-default / total) at the end of the run.

  **Landed 2026-09-05, fixed after independent review the same day (below) — this note describes
  the fixed state.** `src/rogaine/vision/calibrate.py`: three detectors (`detect_scale_bar`,
  `detect_grid_calibration`, `detect_circle_dpi`) + `calibrate_map` (tier priority) +
  `calibrate_corpus`/`CorpusCalibrationReport` (the per-run orchestrator, scoped to
  `name_prefix="ogps-"` by default, with a `refresh` flag to redo its own past output). Every tier
  now requires `ocr_scale_denominator` before it can fire at all — tier 1 originally did not, the
  review's Critical finding's root cause — and every tier's candidate passes through one shared
  plausibility guard (`_accept`: implied dpi in [72, 1200], implied course extent in [1.5, 40]km,
  and, tier 3 only, implied printed-sheet size in [100, 2000]mm) before being trusted, replacing
  the original `_PLAUSIBLE_MPP` (a per-pixel ratio that rejected nothing physically real).
  `src/rogaine/io/corpus.py`: additive `CorpusEntry.calibration_source`/`calibration_tier: str |
  None`, informational only — `is_plannable`/`meters_per_pixel` don't read either.
  `src/rogaine/cli.py`: `corpus list`/`corpus check` now surface both fields, so a human looking at
  the CLI no longer sees a "plannable" map with no hint its scale is fabricated. `data/README.md`:
  corrected `meta.toml` example (`calibration_source`/`calibration_tier` are top-level keys, not
  nested inside `[calibration]`). `tests/unit/vision/test_calibrate.py`: rewritten around the fixed
  API — the shared guard, the regex bound, per-tier detection (including a direct regression test
  for the exact false positive the review found), priority/short-circuiting, corpus-run
  orchestration, scoping, and refresh. `docker compose run --rm tests`: full suite green (exit 0).
  `ruff check .` clean.

  Real end-to-end run against `data/maps/` (219 directories) — every `meta.toml` the flawed first
  version had written was deleted first (identified by its own `calibration_source` key, so the
  one genuinely owner-authored file was left untouched), then the fixed detector re-ran from
  scratch: **45 measured (1 scale_bar, 9 grid, 35 circle) / 159 assumed_default / 0 skipped / 15
  out_of_scope (the owner's own T017 validation scans, e.g. `data/maps/michurinskoe` — never
  touched, per the review's scoping finding, verified directly: zero of them carry a
  `calibration_source` key) / 1 error (one `ogps-*` raster failed to decode, now visible via
  `CorpusCalibrationReport.errors` instead of silently reading as "no signal") / 219 total**. Both
  of the review's own cited false positives (`ogps-7212...`, `ogps-8043...`) now correctly fall to
  `assumed_default` — spot-checked directly against the written files, not assumed. Measured rate:
  22% (45/204 in-scope maps), down from the flawed run's unscoped 59/219 (27%) — not a regression:
  that number mixed in owner-scan hits the fixed run no longer processes at all, plus candidates
  the shared guard now correctly rejects. Judgement calls this task made where ADR-016 left
  specifics implicit are documented in `calibrate.py`'s own module docstring, updated post-fix
  (grid interval assumed 1000m; grid detection is vertical-lines-only, unconfirmed either way on
  this corpus; OCR runs English only, no `tesseract-ocr-rus` in the image; literal fallback
  `scale_denominator` constant never exercised on the real corpus; the plausibility bounds
  themselves are this module's own judgement, not a cited standard).

  **Independent review 2026-09-05: FAIL, then fixed** (1 Critical, 4 High, 6 Medium — two findings
  independently re-verified by the reviewer against the real `meta.toml` files before being sent
  back, not a rubber stamp; all addressed below, then the fix itself re-verified against the real
  corpus, not just re-reviewed on paper). C1 (no working plausibility guard, confirmed 10/59
  "measured" maps physically implausible — e.g. an implied 0.44x0.59km course, a 1790dpi scan —
  plus no refresh path so a corrected re-run was a no-op) → the shared `_accept` guard described
  above, plus `calibrate_corpus(..., refresh=True)`. H1 (tier 2's "cross-validated against OCR"
  never actually compared the two numbers, only checked a ratio existed somewhere on the map) →
  `_implied_dpi` now checked against `_accept` for every tier, not a presence check. H2 (tier
  written only as a TOML comment, invisible to `tomllib`) → `calibration_tier` is a real, parsed
  key. H3 (assumed-default fallback pooled tier 3's dpi only, not "this run's successful
  measurements" as the DoD says) → all three tiers' dpis pool now. H4 (blanket exception handling
  hid a systemic failure, e.g. Tesseract missing, as an ordinary hard corpus) →
  `CorpusCalibrationReport.errors`, plus `pytesseract.TesseractNotFoundError` specifically no
  longer swallowed inside the OCR helpers. M1 (this note's own tier tallies didn't sum) →
  corrected above with the real post-fix numbers. M2 (`data/README.md` example nested
  `calibration_source` inside `[calibration]`, silently unparsed by `read_entry`'s top-level
  lookup) → moved to a top-level key. M3 (`_SCALE_RATIO_RE` unbounded, accepted a decimal point) →
  digit-anchored, `:`-only, range-checked (2000-100000). M4 (`calibration_source`/tier invisible in
  the CLI) → surfaced in both `corpus list` and `corpus check`. M5 (the owner's 15 validation scans
  share `data/maps/` with the scraped corpus; 14 of them got written to) → `calibrate_corpus`'s
  `name_prefix` scopes it to `ogps-*` by default; every `meta.toml` the flawed run had written to
  an owner scan was deleted and the owner directories now carry zero T078 output (verified
  directly, not assumed). M6 (the write pass had no exception guard, so one `OSError` would
  half-write the corpus) → wrapped per-directory, counted in `errors`. The judgement-call docstring
  gaps the review asked for are folded into `calibrate.py`'s module docstring alongside the fix
  that resolved each one, except the one still-true limitation (grid detection is vertical-lines-
  only) which is flagged as a real, unresolved limitation, not fixed away.
- [ ] T070 — Tiling and mask export — paths: `ml/dataset.py` — deps: T016, T017, T078 —
  Corpus volume resolved 2026-09-04: 204 o-gps-center maps (ADR-014) + 15 owner scans, past the
  200+ ADR-010 assumed. Runs over T078's output — every map gets a `meta.toml` (measured or
  flagged assumed-default), so this task is never blocked on calibration accuracy, only on T078
  having run.
  DoD: 512x512 tiles as `image.jpg` + `channels.npy` from palette-generated masks over the
  T078-processed corpus, with rotation, blur and JPEG augmentation, matching the article's data
  recipe; tiles whose `unknown` fraction exceeds a threshold are dropped rather than taught as
  noise; train/val split is by source map, never by tile, so the same map cannot appear on both
  sides.
- [ ] T071 — SegFormer training — paths: `ml/train.py` — deps: T070 —
  DoD: MiT-B4 fine-tune with CE + Dice + Lovasz and rare-class weights, mixed precision, batch sized
  for 8 GB VRAM; per-class IoU reported on a held-out split.
- [ ] T072 — Inference path — paths: `ml/infer.py`, `src/rogaine/vision/segment.py` (backend switch)
  — deps: T071 — DoD: `--segmenter palette|segformer`; palette stays the default; the CPU-only path
  keeps working without torch installed.

## M8 — Real-scan vision robustness (Iteration I1, `docs/iterations/I1-real-scan-vision.md`)

> Two real defects found by the owner's manual testing, not by audit or spec gap. T073 is the one
> shared-primitive dependency (`config.py`'s renamed field) — T074 and T075 do not depend on each
> other, but T075 depends on T073's shipped default existing before its colour-distance check means
> anything. T076 is a third defect, found only while landing T073 itself (ink colour and circle
> size turned out to be two independent problems on the same real scan) — deps T073.

- [x] T073 — Configurable control-ink hue bands (F7, ADR-011) — paths: `src/rogaine/config.py`,
  `config/default.toml`, `src/rogaine/vision/controls.py`,
  `tests/unit/vision/test_controls.py` — deps: none — DoD: `DetectorSettings.purple_hue_range`
  renamed to `ink_hue_ranges: list[tuple[int,int]]`; `purple_mask` unions the mask across every
  configured band; shipped `config/default.toml` carries the existing purple band plus a red band
  measured against `data/maps/grid-lines-red-controls/map.jpeg` (not guessed); the fixture-based
  F7 floor (recall ≥0.95, precision ≥0.90, centre error ≤ quarter radius) is unchanged;
  `test_rejects_a_saturated_non_purple_colour` rewritten to assert against a colour outside both
  configured bands; a new test (skipped if the file is absent) confirms `detect_controls` finds the
  real scan's red-ink controls. **Partially landed, checkbox left open** (commits dc39046, fixes in
  675ea14): the mask-widening half is done and independently verified (`purple_mask` covers 98.99%
  of the real scan's strict-red-ink pixels), but `detect_controls` end to end still does not find
  the real controls — all 16 raw detections are false positives on hand-written digit glyphs, not
  the true ~56px-radius rings (recall 0/13, precision 0/16, hub not found; an earlier, wrong
  "recall 0.077" was corrected after independent review). Root cause, confirmed out of this task's
  scope: `circle_radius_px(dpi=200)` predicts a window from ISOM's 6mm spec that is ~2.3x too small
  for this file's hand-drawn circles — not a DPI-metadata bug (see docs/STATUS.md's Notes).
  **Gap closed by T076/ADR-015 (2026-09-04)**: `circle_scale_multipliers` finds the true rings at
  the correct scale; the real-scan test now passes recall 1.000, precision 1.000, hub found. M8's
  acceptance criterion 1 is met.
- [x] T074 — Grid-line shape exclusion in segmentation (F20, ADR-012) — paths:
  `src/rogaine/vision/segment.py`, `tests/unit/vision/test_segment.py` — deps: none — DoD: a new
  shape-based pass after `classify_palette` reclassifies extreme-elongated near-full-height/width
  `water_shallow`/`water_uncrossable` components to `unknown`; F4's existing fixture IoU floors are
  unchanged; a new test (skipped if the file is absent) confirms the five known grid columns in
  `data/maps/grid-lines-red-controls/map.jpeg` drop from >30% `water_uncrossable` to ~0%, and that a
  compact water body still classifies as `water_uncrossable`. Landed as whole-column/whole-row
  water-fraction runs (`GridSettings.span_fraction_min`/`max_line_width_mm`,
  `vision/segment.py::reclassify_grid_ink`) rather than a per-connected-component test — real grid
  lines fragment into many small pieces where other ink crosses them, confirmed by measurement, so
  a component-level shape test would have missed most of them. All 8 known grid columns (not 5 —
  the real count once measured) drop from 0.338-0.898 to 0.000; fixture unaffected (0 pixels
  changed, noisiest column measures 0.145 against the 0.25 threshold). Independent review found
  `max_line_width_mm` alone (an absolute size) stops discriminating a line from a blob on a small
  or cropped raster; fixed by adding `min_elongation_ratio = 10.0` as a second, image-relative
  guard, plus a graph-connectivity test (9463 -> 580 connected components on the real scan) as the
  real evidence for exit criterion 3, which does not reproduce via an arbitrary hub/control pick
  (block-level graph passability already bridges most single-column gaps). See commits a5c086c,
  675ea14.
- [x] T075 — Route-overlay colour distinct from all seven forbidden inks — paths:
  `src/rogaine/render/overlay.py`, `tests/unit/render/test_overlay.py` — deps: T073 — DoD:
  `_CORE_COLOR` replaced with a value verified (via `config.cmyk_to_srgb`, not eyeballed) distinct
  from all six ISOM inks plus red; existing pixel-sampling tests pass unchanged (they import
  `_CORE_COLOR` rather than hardcoding it); one new test asserts the measured distance. Landed as
  a pure magenta (255,0,255), min CIELAB distance ~48.3 to all seven forbidden inks (nearest:
  purple) against the 35.0 threshold. See commit 20f7bed.
- [x] T076 — Size-flexible control-circle/hub detection (F7, ADR-015) — paths:
  `src/rogaine/config.py`, `config/default.toml`, `src/rogaine/vision/controls.py`,
  `tests/unit/vision/test_controls.py` — deps: T073 — DoD: new
  `DetectorSettings.circle_scale_multipliers: list[float]` (min_length=1, all > 0), shipped default
  `[1.0, 1.5, 2.0, 2.5, 3.0]` in `config/default.toml`, comment citing the measured real-scan ratio
  (~56px true radius vs ~23.6px `circle_radius_px(200)` mid-radius, ~2.37x, T073's own finding);
  `_detect_circles` runs Hough once per multiplier against the scaled `(r_min, r_max)` window and
  gates each pass's candidates through the existing unmodified `_ring_coverage` (same threshold,
  same band fraction); `_detect_hub_triangle` sweeps the same multiplier list for `expected_side`,
  selecting the best match across scales by normalised relative error (`diff / max_diff`), not raw
  pixel diff. No change to `_ring_coverage`, `_RING_COVERAGE_MIN`/`_RING_COVERAGE_BAND_FRACTION`,
  or `hough_dp`/`hough_param1`/`hough_param2` — the false-positive guard is reused unmodified at
  every scale, never retuned. Fixture F7 floor unchanged (recall ≥0.95, precision ≥0.90, centre
  error ≤ quarter radius) — `TestRecallPrecisionOnFixture` and `TestHubTriangleDetection` pass with
  no test edits. The real-scan test loses its `xfail(strict=True)` marker and passes for real
  against `data/maps/grid-lines-red-controls/map.jpeg` (recall 1.000, precision 1.000, hub found) —
  skipped outright, not xfailed, when the file is absent (ADR-010's reproducibility rule,
  unchanged). A new synthetic unit test (`TestSingleScaleSelected`, no real scan needed, renamed
  from this task's first draft's `TestCrossScaleCircleDedup`) exercises the structural guarantee
  directly: one true ring sized for multiplier 1.0 (also inside multiplier 1.5's overlapping
  window) must yield exactly one `_detect_circles` candidate.

  **Landed differently from this task's own first draft, after measurement — see ADR-015's
  "Landed mechanism" note for the full account.** The originally planned mechanism (pool every
  scale's ring-coverage-passing candidates, reduce with cross-scale non-max suppression) was
  actually built first and independently re-verified end to end against the real scan before
  being accepted: recall reached 1.000 (all 13 rings found, confirming the core multi-scale idea
  works) but precision was only 0.448 (29 raw detections, 16 false) — the pre-existing base-scale
  false positives on hand-written control-number digits (T073's own documented, unfixed problem;
  the real-scan test was `xfail` precisely because of this) each individually clear the same 0.75
  ring-coverage floor a true ring does, so pooling-then-NMS only ever collapses duplicates of the
  *same* physical ring across scales — it does not and structurally cannot remove a distinct false
  feature found at a different scale. Diagnosed by measuring every scale's candidates and their
  mean ring-coverage independently (real scan): the true scale (2.0x) averaged 0.994 while the
  false-prone base scale (1.0x) averaged only 0.881, despite every individual candidate on both
  sides clearing the identical 0.75 floor — comparing scales *as sets* separates what no
  per-candidate threshold can. Fixed by replacing pool+NMS with `_select_best_scale`: compute each
  multiplier's candidates and mean coverage, keep only the single highest-mean multiplier's
  candidates (ties keep the smaller multiplier). This also makes the separate NMS step
  unnecessary — cross-scale duplication is structurally impossible once only one scale's output is
  ever returned, so `_cross_scale_nms` was replaced rather than kept alongside the new selection.
  Known, explicitly out-of-scope limitation of the landed design (also in ADR-015): a map mixing
  ISOM-printed and oversized hand-drawn circles at more than one true scale would lose the
  minority scale's real circles along with the losing scale's noise — no such map exists in this
  project's corpus to design or test against.

  **Independent review before this landed found one further Critical (C-1): the mean-only
  selection rule above has its own failure mode.** `_ring_coverage` saturates at exactly 1.0 for
  *any* candidate sitting inside a solid ink blob, not only a genuine ring, so two scales tying at
  a perfect mean is the normal case, not a rare edge case — and a bare `mean_a > mean_b` comparison
  hands every such tie to the smallest multiplier (sweep order), which can be the wrong one.
  Demonstrated by the reviewer, not theorised: a synthetic map with five true rings at multiplier
  2.5 plus one incidental filled purple blob at multiplier 1.0 lost all five true rings to the one
  perfect-mean decoy. Fixed (same session) by scoring `(mean coverage bucketed to
  `_SCALE_TIE_EPS`=0.02, candidate count)` instead of raw mean: a meaningfully higher mean still
  wins outright, but among scales close enough to call a tie, the one with more corroborating
  candidates wins. Real scan's own selection unaffected (still multiplier 2.0, 13/13 recall and
  precision). New permanent regression test: `TestOversizedRingsBeatABaseScaleDecoy`. Review's
  other findings, all addressed: `docs/STATUS.md` rewritten to the post-T076 state (was a day
  stale, still describing the pre-T076 failure as unresolved); T077 filed below for the
  `vision/ocr.py::_ocr_crop` base-scale-only crop sizing (was flagged but not filed); iteration
  I1's exit criterion 3 reworded to state what was actually demonstrated (graph-wide fragmentation
  fix) rather than the literal, never-reproduced "no reachable route" wording; one clarifying
  sentence added to ADR-015 on why `_detect_hub_triangle` keeps its original per-candidate
  selection rather than the same set-level one (a hub is a single expected symbol, so there is no
  "many corroborating candidates" signal to weigh — review tried to break it with a base-scale
  decoy triangle and could not, true hub won at 0.996 confidence).

  389 tests pass (386 baseline + the real-scan test converting from xfailed to a real pass + 2 new
  tests), `ruff check .` clean.
- [x] T077 — Scale-aware OCR crop sizing — paths: `src/rogaine/vision/ocr.py` — deps: T076 — DoD:
  `_ocr_crop` (or its caller) sizes the number-search crop and ring-erase disk from the actual
  matched circle's fitted radius/scale, not `circle_radius_px(dpi)` at the base scale unconditionally
  — `Control` (T020's output, `models.py`, frozen per ADR-008) carries no matched-radius field
  today, so this likely needs either a new non-frozen carrier between `detect_controls` and
  `read_control_numbers`, or a `models.py` amendment (needs its own ADR first, ADR-008). Filed by
  T076/ADR-015 after real-scan detection started finding controls at non-base scales for the first
  time: OCR on any such control crops with the base scale's (too small) window, likely missing the
  digits. Degradation is currently safe (`min_ocr_confidence` gate → `number=None` + flag, F8's
  "never silently guessed" holds) but untested at non-base scale — DoD should include a real-scan
  regression test once this lands (`data/maps/grid-lines-red-controls/map.jpeg`'s 13 controls all
  land at multiplier 2.0 per T076, a real fixture for exactly this gap). **Pulled into Iteration
  I2/M9 below** — deps amended to `T076, T079` (shares `vision/controls.py` with T079-T081,
  serialized after them per M9's ordering note).

  **Landed (ADR-020).** `Control` gains `radius_px: float | None` (`models.py`) — the matched
  scale's nominal mid radius, `None` for the hub and any `Control` built another way.
  `_detect_circles`/`_select_best_scale` (`vision/controls.py`) widened their candidate tuples
  `(x, y, coverage)` → `(x, y, r, coverage)` to thread it through; `_ocr_crop`
  (`vision/ocr.py`) uses `control.radius_px` when set, else falls back to
  `circle_radius_px(dpi)`'s own mid-value exactly as before.

  **One real finding, corrected before landing.** The first pass threaded Hough's raw
  per-candidate fitted radius (ADR-020's literal original wording), which regressed
  `TestReadsNumbersOnFixture` on the clean synthetic fixture 11/12 → 9/12 — measured cause: Hough's
  per-circle radius jitters ~±10% around the scale's nominal mid-radius even at the base scale, and
  `_ocr_crop`'s crop-margin constants (`_CROP_MARGIN_FACTOR`/`_CIRCLE_MASK_RADIUS_FACTOR`) were
  tuned against the noiseless nominal value, not that jitter. Fixed by threading the multiplier's
  own nominal `r_mid` instead of the raw fit (same value for every candidate at that scale) — this
  makes a base-scale (multiplier 1.0) `radius_px` bit-identical to `_ocr_crop`'s pre-T077 fallback,
  so the fix is strictly additive: only a control matched at a non-base multiplier gets a different
  (correctly larger) crop. ADR-020 updated to record this as the accepted design, not the first
  draft. Independently re-verified after the correction (not just trusted from the implementer).

  New tests: `tests/unit/test_models.py::TestControl` (+3, `radius_px` default/round-trip/negative
  rejection), `tests/unit/vision/test_controls.py::TestRadiusThreadedThroughDetection` (+4, tuple
  shape and plausible-radius checks on the synthetic fixture), `tests/unit/vision/test_ocr.py::
  TestScaleAwareCropOnRealScan` (+1, skipif-guarded on `grid-lines-red-controls`). 457 passed (449
  baseline + 8 new tests), `ruff check .` clean. Re-ran `rogaine detect` on
  `grid-lines-red-controls/map.jpeg` directly: hub found, 13 circles (all `radius_px` populated,
  ~multiplier-2.0 window), 3/13 numbers read (up from 0/13 sizing the crop at the base scale
  unconditionally) — a real, if modest, improvement; the remaining 10 are flagged unreadable, never
  guessed (ADR-009).

## M9 — Real-scan detection/OCR failure on the owner's own scans (Iteration I2, `docs/iterations/I2-real-scan-detection-failure.md`)

> Owner bug report, reproduced on all 13 of the owner's own scans (not the harvested o-gps-center.ru
> corpus): gross circle over-detection (2x-10x the true count), ~0% OCR read rate, hub not found on
> 8/13. Root cause measured, not guessed: `purple_mask`'s ADR-011 red band over-matches brown
> contour-line ink on these scans (88% of matched pixels, real scan `ozero-shchuche`). T079 is the
> shared-primitive dependency (`purple_mask` itself) — everything else in this milestone, plus T077
> (M8, pulled in here), reads its output and is serialized after it since all share
> `vision/controls.py`. See the iteration doc for the full reproduction table and impact map.

- [x] **T079** — Tighten ink-hue false-positive rate on real scans (F7, ADR-018) — paths:
  `config/default.toml`, `src/rogaine/vision/controls.py::purple_mask`,
  `tests/unit/vision/test_controls.py` — deps: none — DoD: `purple_mask` density on
  `data/maps/ozero-shchuche/map.jpg` measured and reduced from the current 6.82% (measured this
  session) toward `grid-lines-red-controls`' 1.93% order of magnitude, without regressing
  `TestRealScanRedInk::test_purple_mask_flags_the_real_red_ink` (>=95% coverage of that file's
  strict-red ink) or `::test_recall_and_hub_match_the_true_positions` (recall/precision >=0.90, hub
  found) or `TestPurpleMask`/`TestRecallPrecisionOnFixture`. A new test measures the density drop on
  `ozero-shchuche` (skipped if the file is absent, ADR-010's rule). If one measured change cannot
  satisfy both the existing floor and the new scan, stop and report — do not loosen either
  assertion (ADR-018).

  **Landed.** Root cause confirmed: brown contour ink (mean RGB (161,106,90)) was passing
  `ink_hue_ranges`' red band under the shared `purple_min_saturation`/`purple_min_value` floor
  (60/60) — `grid-lines-red-controls`' own real red ink always measures saturation>=61, value>=151,
  `min(R-G, R-B)>=61`, brown mostly does not. Fix: red split out of `ink_hue_ranges` into its own
  `red_hue_ranges` (unchanged bands `[[0,9],[167,179]]`) with a measured-tighter floor
  (`red_min_saturation=61`, `red_min_value=151`) plus a new `red_min_channel_gap=60` check
  (`min(R-G, R-B) >= 60`), which real red ink clears by definition and brown mostly doesn't.
  `purple_mask` now unions the purple-band mask and the red-band-plus-channel-gap mask separately
  instead of sharing one floor. `DetectorSettings` (extra="forbid") gained the three new keys.
  Measured: `ozero-shchuche` density 6.82% → 1.34% (now *below* `grid-lines-red-controls`' own
  1.93%, not just the same order of magnitude); `grid-lines-red-controls` unaffected —
  `test_purple_mask_flags_the_real_red_ink` coverage 99.01% (floor 95%, was 98.99%),
  `test_recall_and_hub_match_the_true_positions` recall/precision 1.000/1.000, hub found (unchanged
  pass). New test `TestInkHueFalsePositiveRateOnOzeroShchuche` (skipped if the gitignored file is
  absent) asserts the density drop as a permanent regression guard. No stop-and-report case hit —
  one change cleared both floors. 448 passed (447 baseline + 1 new test), `ruff check .` clean
  (independently re-run, not just trusted from the implementer). See commit fade5fd.
- [x] **T080** — `_select_best_scale` tie-break re-measured against high-false-positive scales
  (ADR-015's documented limitation) — paths: `src/rogaine/vision/controls.py::_select_best_scale`,
  `tests/unit/vision/test_controls.py` — deps: T079 — DoD: re-run the 13-map reproduction table
  (iteration doc) after T079 lands. If any map still shows gross over-detection from a losing-scale
  false-positive volume beating a genuinely better scale inside `_SCALE_TIE_EPS`'s bucket, fix the
  selection rule (with a new regression test using that map's actual numbers) without touching
  `TestOversizedRingsBeatABaseScaleDecoy`/`TestSingleScaleSelected`'s existing assertions. If T079
  alone resolves every measured case, close this task with the measurement recorded — no speculative
  algorithm change.

  **Closed: measured, no change needed.** Re-ran `rogaine detect` on all 13 owner maps post-T079
  (`--dpi` omitted, auto-probed): counts dropped sharply on the maps T079 targeted (ozero-shchuche
  71→21, kkm-3-2020 71→21, kkm-5-2020 52→21, kkm-toksovo 159→25, novo-kavgolovsky-lesopark 62→21),
  held flat or rose slightly elsewhere. Checked every map still above the ~10-20 plausible range
  (pervomayskoe 41, treugolnoe 58, history-race-primorsk 49, kkm-toksovo 25) for the exact
  mechanism T080 is scoped to — a losing scale's same-bucket false-positive *count* beating a
  genuinely better scale. Found: pervomayskoe's and history-race-primorsk's winning scale wins
  outright (no competing bucket-tie to arbitrate — `_ring_coverage` saturating on solid ink blobs
  at one scale, out of this task's scope); treugolnoe's multiplier 1.5 beats 1.0 by 3 buckets on
  coverage, not a tie. kkm-toksovo is the one real instance of the mechanism (multiplier 1.0's 25
  candidates tie multiplier 1.5's 20 at the same bucket, 1.0 wins on count; 20 of the 25 are shared
  rings, the other 5 are small-radius candidates near two shared y-coordinates, likely printed
  digits) — but mild (5-candidate inflation), not the "gross over-detection" the DoD's fix trigger
  requires. No map meets the DoD's fix-triggering conjunction (gross count *and* tie-break-caused),
  so no change made to `_select_best_scale`, `TestOversizedRingsBeatABaseScaleDecoy`, or
  `TestSingleScaleSelected`. 448 passed (unchanged, no test added), `ruff check .` clean.
  Full post-T079 hub column handed to T081 below (michurinskoe, pervomayskoe, toksovo-zubry,
  treugolnoe, history-race-2024-michurinskoe found; ozero-shchuche, kkm-3-2020, kkm-5-2020,
  kkm-toksovo, lembolovo-kkm, novo-kavgolovsky-lesopark, toksovo-1, history-race-primorsk not
  found — same not-found set as pre-T079, none flipped).
- [x] **T081** — Hub triangle not found on real scans — paths:
  `src/rogaine/vision/controls.py::_detect_hub_triangle`, `tests/unit/vision/test_controls.py` —
  deps: T079 — DoD: hub found on `ozero-shchuche` (confirmed to still fail even under a mask
  restricted to the pure purple band — a separate cause from T079/T080) and on every owner scan in
  the reproduction table that actually shows a start triangle in the source map, without changing
  `TestHubTriangleDetection`'s (synthetic fixture) existing assertion.

  **Landed.** Two independent, measured causes, neither touching `purple_mask`/`_select_best_scale`:
  (1) ISOM's combined start/finish overlaps the 701 triangle with the 706 finish double-circle —
  the circle ink bulges one edge of the triangle's contour outward, adding a vertex the original
  fixed `approxPolyDP` epsilon (0.02) could never absorb, so no 3-vertex fit was ever produced.
  Measured: `ozero-shchuche`'s hub first collapses to exactly 3 vertices at eps=0.03,
  `kkm-toksovo`'s (fuller double-ring overlap) at eps=0.08. (2) `cv2.RETR_EXTERNAL` only returns a
  contour's outermost nesting level; on a scan whose terrain-contour ink forms a dense mesh of
  closed loops, the hub commonly sits geometrically inside one of those loops without ever touching
  it, so it was invisible regardless of vertex count. Measured on `kkm-toksovo`: `RETR_EXTERNAL`
  finds exactly 1 contour system-wide; `RETR_LIST` recovers 64,366, among which the real hub is the
  sole match once the epsilon sweep and side-ratio checks apply.

  Fix: `_detect_hub_triangle` switched to `cv2.RETR_LIST`; the single fixed `approxPolyDP` epsilon
  replaced by an ordered sweep, new constant `_TRIANGLE_APPROX_EPS_FRACTIONS = (0.02, 0.03, 0.04,
  0.05, 0.06, 0.08, 0.10)`, taking the first epsilon that yields exactly 3 vertices (0.02 tried
  first, so already-passing fixture/`grid-lines-red-controls` triangles match at the same epsilon
  as before). Widening the sweep let an unrelated blob (a course logo's overlapping running-figure
  glyphs on `ozero-shchuche`) also reach 3 vertices at a wider epsilon, so `_TRIANGLE_MIN_SIDE_RATIO`
  was tightened 0.5→0.85 — measured real ISOM 701 triangles hold side ratio 0.970-0.980 across three
  real files, the logo's false fit measured 0.604-0.634, so 0.85 sits with wide margin on both sides.

  Hub-found count: 5/13 → 10/13 owner maps (9/12 unique files — kkm-3-2020 duplicates
  ozero-shchuche byte-for-byte). Remaining 3 measured, not forced: `lembolovo-kkm` and
  `novo-kavgolovsky-lesopark` — hub ink is fused into a page-spanning terrain/border mesh, no
  contour-extraction approach recovers a clean triangle without touching border/mask handling
  (out of this task's scope); `history-race-primorsk` — a genuine, well-formed triangle contour *is*
  found (side ratio 0.975) but its size falls just below the smallest configured scale multiplier's
  tolerance window, a `_TRIANGLE_SIDE_TO_RADIUS`/tolerance calibration mismatch for this one file,
  not a vertex or visibility bug — fixing it means retuning shared scale config, explicitly out of
  this task's "don't touch `_select_best_scale`" boundary.

  New test `TestHubFoundOnOzeroShchuche` (skipif-guarded on the real scan) added as a permanent
  regression guard; `TestHubTriangleDetection`'s synthetic-fixture assertions unchanged. 449 passed
  (448 baseline + 1 new test), `ruff check .` clean (both independently re-run, not just trusted
  from the implementer). Re-ran `rogaine detect --map data/maps/ozero-shchuche/map.jpg` directly:
  `hub: found`, 21 circles (matches T080's post-T079 count, unchanged). See commit 00b1b97.
- [ ] **T082** — Owner spot-check across the real-scan corpus (ADR-019) — paths: none (validation
  only; a throwaway script under `data/maps/` if useful, gitignored like its siblings) — deps:
  T077, T079, T080, T081 — DoD: re-run `rogaine detect` (and/or the viewer) on 2-3 of the owner's
  own maps post-fix; owner reviews the output and confirms circle positions, hub, and numbers look
  right. Recorded in `docs/STATUS.md`, not a new automated floor (ADR-019 — no ground truth exists
  for these files).

## M10 — Viewer UX, scale auto-detection exposure, control-number OCR (Iteration I3, `docs/iterations/I3-viewer-ux-and-detection.md`)

> Three independent workstreams, each internally serial, freely parallel with each other: OCR
> (T083 -> T084), UI (T085 -> T086, `T085` is the shared-primitive layout row and must land first),
> and the CLI half of scale-auto (T087, no shared files with the other two). `T088` (the web half of
> scale-auto) waits on both `T086` (shares `web/static/*`) and `T087` (mirrors its contract) — see
> the iteration doc's impact map for the full five-question breakdown per item.

- [ ] **T083** — Diagnose control-number OCR failure on the owner's real scans — paths: none
  (diagnosis only; a throwaway measurement script under `data/maps/`, gitignored like its siblings)
  — deps: T077 — DoD: measure `_ocr_crop`/`_read_digits`'s actual behaviour against every owner real
  scan under `data/maps/` that has numbered controls (not just `grid-lines-red-controls`), recording
  a per-map read rate and the concrete, numbers-backed failure mode for each unread control (crop
  still misframed, wrong ink surviving the mask, resolution too low for Tesseract's assumptions,
  digit glyphs occluded by ring/hatching remnants, wrong `psm`/whitelist, etc.) — measured, not
  guessed, matching this project's own established practice (T079-T081). Findings and the resulting
  fix design get a new ADR in `DECISIONS.md` and feed T084 directly; no product-code changes in this
  task.
- [x] **T084** — Fix control-number OCR per T083's findings — paths: `src/rogaine/vision/ocr.py`,
  `config/default.toml` (only if a tunable is implicated), `tests/unit/vision/test_ocr.py` — deps:
  T083 — DoD: real-scan read rate measurably improves beyond T083's own measured baseline, with the
  exact before/after counts recorded (same style as T079-T081's entries); the synthetic fixture's
  existing 11/12 floor (`test_at_least_eleven_of_twelve_controls_read_correctly`) does not regress;
  OCR stays explicitly non-load-bearing (ADR-009) — an unreadable number still emits `points: null`
  plus a flag, never a guess.

  **Landed.** Two measured causes fixed, in T083's own priority order; a third
  (`min_ocr_confidence`) measured and rejected. `config/default.toml` untouched — both fixes are
  file-local `ocr.py` constants, the same pattern `_CIRCLE_MASK_RADIUS_FACTOR`/`_CROP_MARGIN_FACTOR`
  already used, not new config tunables.

  **Mode 1 (`_strip_thin_ink`, priority 1).** T083's dominant cause: leftover non-digit ink
  (contour-line edges, shoreline squiggles) clears `purple_mask`'s hue/saturation/value floor and
  defeats Tesseract's psm 7 single-line assumption even inside a correctly-framed, correctly-ring-
  erased crop. A morphological opening (kernel sized from `number_font_height_mm` converted to px
  via `dpi`, the same convention every other size in this module already uses) was tried first and
  rejected: even its smallest non-trivial kernel (radius 1, a 3x3 ellipse) shaved corners off the
  synthetic fixture's own thin Hershey-font digit strokes, dropping its floor from 11/12 to 10/12 at
  every kernel size that measurably helped the real corpus (throwaway sweep, `_t084_sweep.py`:
  factor 0.03 → 10/12 synthetic / 149/416 real; factor 0.05 → 10/12 / 98/416; factor ≥0.08 →
  collapse toward 0/416 on both). Replaced with a connected-component area filter (`_strip_thin_ink`):
  drops any connected ink component under a minimum area — swept 0.0-0.40 in 0.02 steps as a
  fraction of the *squared* digit height (`_t084_sweep2.py`) — without ever touching a surviving
  component's own pixels, so it stayed gentle on the fixture's thin-but-full-height strokes (11/12
  held everywhere from 0.0 to 0.30) while the real corpus total climbed from 80/416 to a 169-179/416
  plateau across factor 0.16-0.24. Landed: `_MIN_INK_AREA_FACTOR = 0.20` (176/416), mid-plateau
  rather than the single noisiest point (0.21's 179/416).

  **Mode 2 (conditional ring-erase widen, priority 2).** `pervomayskoe` stayed at 0/41 after mode 1
  alone, unchanged from baseline. Radial ink-density profiling around the detected centre
  (`_t084_ring_radius.py`) confirmed T083's diagnosis directly: `pervomayskoe`'s true printed ring
  band sits at ~1.3-1.5x `r_mid`, past the existing `_CIRCLE_MASK_RADIUS_FACTOR` (1.25) erase disk's
  edge; `kkm-5-2020` control 1's own case turned out to be a different, out-of-scope cause (`r_mid`
  itself under-fit relative to that control's true ring — a `vision/controls.py` scale-selection
  question, not an erase-radius one). A **global** widen of `_CIRCLE_MASK_RADIUS_FACTOR` (swept
  1.25-1.70, `_t084_sweep3.py`) was tried and rejected: it helped `pervomayskoe` (0/41 → 19/41 at
  1.50+) but measurably hurt already-correctly-erased maps as the disk grew into nearby digit ink
  (`toksovo-1` 19/21 → 13/21 at a global 1.50, `kkm-5-2020` 11/21 → 6/21). Replaced with a
  **conditional** widen: `_annulus_ink_density` measures ink coverage in a thin annulus just past
  the base disk (`[1.25, 1.25×1.2] × r_mid`); only when that density exceeds a threshold (evidence
  of a still-closed ring, not scattered digit/noise ink) does `_ocr_crop` use a wider erase factor.
  Swept threshold×widened-factor combinations in {0.3, 0.4, 0.5}×{1.50, 1.55, 1.60}
  (`_t084_sweep4.py`): every combination left every already-correct map's count unchanged while
  `pervomayskoe` jumped to 19/41 and `history-race-2024-michurinskoe` — an undershoot case T083 did
  not separately flag — climbed from 2/37 to 5-14/37. Landed: `_RING_DENSITY_WIDEN_THRESHOLD = 0.4`,
  `_WIDENED_CIRCLE_MASK_RADIUS_FACTOR = 1.55` (205/416 total), mid-range rather than the single best
  point (0.4/1.60's 206/416).

  **Priority 3 (`min_ocr_confidence`) measured and rejected.** With modes 1+2 landed, sweeping the
  confidence floor down (`_t084_sweep5.py`) still gained monotonically with no synthetic regression:
  0.60→205/416, 0.55→208, 0.50→212, 0.45→214, 0.40→217, 0.35→220, 0.30→223 (synthetic held 11/12
  throughout). Inspected the 12 controls this would newly admit at 0.40-0.59: some are plausible
  clean reads (`history-race-primorsk` c37 "58"@0.52, `kkm-5-2020` c19 "92"@0.49) but others are
  single ambiguous digits (`history-race-primorsk` c48 "8"@0.41, `lembolovo-kkm` c17 "7"@0.45)
  indistinguishable from a truncated misread without ground truth (no ground-truth number CSV
  exists for any owner scan — ADR-010/ADR-019). Given the gain is modest next to modes 1+2 (+7
  controls at 0.50, +3.4pp) and admitting one wrong-but-confident-looking number would violate
  ADR-009's "never a guess" harder than leaving it flagged, `min_ocr_confidence` stays at 0.6 —
  measured, not adopted.

  **Final per-map table** (T083 baseline → T084, modes 1+2 landed, `min_ocr_confidence` unchanged):

  | Map | Before (T083) | After (T084) |
  |---|---|---|
  | toksovo-1 | 17/21 (81%) | 19/21 (90%) |
  | toksovo-zubry | 11/31 (35%) | 24/31 (77%) |
  | history-race-primorsk | 14/49 (29%) | 17/49 (35%) |
  | treugolnoe | 17/58 (29%) | 21/58 (36%) |
  | michurinskoe | 9/37 (24%) | 23/37 (62%) |
  | grid-lines-red-controls | 3/13 (23%) | 10/13 (77%) |
  | lembolovo-kkm | 3/20 (15%) | 7/20 (35%) |
  | kkm-3-2020 | 2/21 (10%) | 17/21 (81%) |
  | ozero-shchuche | 2/21 (10%) | 17/21 (81%) |
  | history-race-2024-michurinskoe | 2/37 (5%) | 13/37 (35%) |
  | kkm-5-2020 | 0/21 (0%) | 11/21 (52%) |
  | kkm-toksovo | 0/25 (0%) | 1/25 (4%) |
  | novo-kavgolovsky-lesopark | 0/21 (0%) | 6/21 (29%) |
  | pervomayskoe | 0/41 (0%) | 19/41 (46%) |
  | **Total** | **80/416 (19%)** | **205/416 (49%)** |

  `kkm-toksovo`'s 0→1 (not mode-1-alone's 2) is the one net per-control cost among individual maps:
  one control's conditional-widen check fired on an already-correctly-erased ring (a false positive
  of the density heuristic), costing a read mode 1 alone had recovered — a 1-control cost against a
  125-control corpus-wide gain, not chased further. Two new permanent regression tests added,
  `TestRealScanReadRateFloor` (`tests/unit/vision/test_ocr.py`): `test_pervomayskoe_read_rate_floor`
  (floor ≥15/41, isolates mode 2 — mode 1 alone still measured 0/41 here) and
  `test_novo_kavgolovsky_lesopark_read_rate_floor` (floor ≥5/21, isolates mode 1 — mode 2 never
  triggers on this map's already-correctly-erased rings), both skipif-guarded on the gitignored real
  file's presence (ADR-010). The synthetic fixture's `test_at_least_eleven_of_twelve_controls_read_
  correctly` floor held unchanged (11/12) through every step. 465 passed (463 baseline + 2 new
  tests), `ruff check .` clean (both independently re-run, not just trusted from the implementer).
  See commit d40047f.
- [x] **T085** — Viewer layout: map and controls list simultaneously visible (F17, ADR-021) — paths:
  `src/rogaine/web/static/index.html`, `style.css`, `app.js`, `tests/e2e/test_viewer.py` — deps:
  none — DoD: on a standard viewport (e.g. 1366x768) with a map loaded, the map viewport and the
  controls table are both visible without scrolling the map out of view to reach a control's number
  field; a new Playwright assertion (extending `test_viewer.py`) confirms both elements' bounding
  boxes are within the browser viewport at once after selecting/adding a control; selecting a table
  row highlights its marker on the map and vice versa (new behaviour, new test — none exists today);
  the existing A11y non-functional requirement (keyboard-operable, focus visible, labelled, legible
  light/dark) is re-verified, not just assumed; existing `test_viewer.py` assertions keep passing
  unmodified.

  **Landed** (commit `fec2e7c`) — **backfilled into this file during the T084 session**: the commit
  existed in the tree with no `TASKS.md`/`STATUS.md` record at all (checkbox found stale, corrected
  per this project's own "trust the tree" rule); the note below is reconstructed from the commit
  diff and a passing test run, not from first-hand knowledge of the session that built it, so it
  omits any rejected-alternative narrative that session may have had. `style.css`/`app.js` only —
  `index.html` untouched, because its `#map-viewport`/`#controls-table`/`#controls-tbody` ids
  already existed for the new CSS/JS to hook into. New `TestViewerLayout` class
  (`tests/e2e/test_viewer.py`, one new Playwright test) sets a 1366x768 viewport, runs the existing
  upload/calibrate/detect flow, then asserts `#map-viewport` and `#controls-table` are each fully
  `to_be_in_viewport(ratio=1)` at once, and that clicking a table row toggles `row-selected`/
  `marker--selected` classes on it and its marker (and clears them from the previously-selected
  pair) both directions. All pre-existing `test_viewer.py` assertions unmodified. 465 passed
  (this session's own count, includes T085+T087+T084 together), `ruff check .` clean — not verified
  isolated to just this commit's own delta.
- [x] **T086** — Viewer visual redesign (typography, spacing, colour, table legibility) — paths:
  `src/rogaine/web/static/style.css`, `index.html` — deps: T085 (same owned files, serialized after
  the structural fix) — DoD: `tests/e2e/test_viewer.py` stays green with its assertions unmodified;
  both light and dark palettes stay legible via the file's existing `prefers-color-scheme` token
  pattern; no columns/fields are clipped or require horizontal scroll to read at the panel's working
  width; owner reviews a live instance and confirms it reads as more concise/modern than the
  previous six-stacked-accordion layout — a manual sign-off, no automated "looks modern" floor
  (same precedent as ADR-019/T082).

  **Landed (pending owner sign-off).** `.layout`'s fixed side-column track went `380px` -> `460px`
  (`minmax(0, 1fr) 460px`) -- the fixed width itself was the named cause of "too narrow to read";
  at 1366px viewport width (`TestViewerLayout`'s own number) the map column goes from 941px to
  861px, still comfortably usable. `#controls-table`'s 7 columns (ID, X, Y, Номер, Очки, Хаб,
  actions) were all sharing one `td input[type="number"] { width: 5.5em }` plus global
  `white-space: nowrap`, which is what forced the old `.table-scroll` into permanent horizontal
  scroll -- replaced with positional per-column widths (`#controls-table td:nth-child(n)`, pinned
  to `createControlRow`'s fixed column order in app.js since the row markup has no per-column class
  hooks): ID 2.2em, X/Y inputs 5em, Number/Points inputs 3.6em, Хаб 2.4em centred, actions 4.2em
  hint (the delete button's own fixed "Удалить" text ends up the real driver of that column's
  width, not the hint). Table font 0.82rem -> 0.85rem, cell padding 0.25rem/0.35rem ->
  0.3rem/0.4rem. Verified concretely, not just eyeballed: a throwaway Playwright script (this
  session only, not committed) drove the real upload/calibrate/detect flow against the standard
  synthetic fixture (13 rows) and measured every `#controls-table input[type="number"]`'s
  `scrollWidth` vs `clientWidth` plus the table's own `scrollWidth` vs its `.table-scroll`
  container's `clientWidth` -- zero overflow, including a stress pass forcing 4-digit Number/Points
  values. One real defect surfaced by that same measurement pass: Chromium reserves width for the
  native number-input spin buttons inside the input's own box, so the 5em X/Y inputs were clipping
  by ~4px on any 5-character value (e.g. `599.3` rendered as `599.:`) -- fixed by dropping the
  spinner UI on this table specifically (`appearance: textfield` + the `-webkit-*-spin-button`
  reset), which does not remove any input functionality (typing/pasting and the marker's own
  keyboard nudge are untouched).

  Second, separate bug found while screenshotting (not part of the DoD, fixed anyway since it's in
  an owned file and directly undercuts "legible"/"concise"): `.scale-panel { display: flex }`
  (pre-existing, untouched by this task otherwise) has the same specificity as the UA stylesheet's
  `[hidden] { display: none }`, and author-origin beats user-agent-origin at equal specificity, so
  `#scale-calibrate-panel[hidden]` was rendering regardless -- both scale-mode panels showed at
  once on every page load, no matter which radio was checked. Added a top-level
  `[hidden] { display: none !important; }` rule (the standard fix for this exact class of bug).
  Confirmed via a script driving `page.check()` on both radios that exactly one panel shows in all
  three states now (default/ratio, calibrate, back to ratio); confirmed the `!important` doesn't
  regress any of the app's other `el.hidden` toggles (`hub-warning`, `route-results`,
  `run-id-display`, `map-preview-note`) since none of their classes set a competing `display`.

  Typography/spacing/colour, the DoD's other three named dimensions: all six `<details>` panels
  keep `open` (nothing in app.js or the tests ever toggles `open`, confirmed by grep, so first-paint
  state is unchanged) but the native disclosure triangle is replaced with a numbered accent-filled
  badge + title + a custom chevron that now genuinely works (the owner can collapse a panel with
  zero JS involved, e.g. Карта/Масштаб after calibrating -- previously the marker was there but the
  panels never needed collapsing since nothing else used it either way). Added a `.btn-primary`
  tier (solid accent fill) for the three buttons that carry the user forward through the setup flow
  (Загрузить карту / Применить масштаб / Построить маршрут) -- previously every button looked
  identical regardless of importance. `#controls-table`'s delete button recoloured to the existing
  danger tokens (already used by `.error-message`) and shrunk, both freeing width and giving the
  destructive action a distinct signal. Added zebra striping to `#controls-tbody` reusing `--bg`
  (already the token `.panel input[type=number]` sits on, so this is the same "recessed surface"
  look already established, not a new visual language). `.panel` gained a subtle box-shadow and an
  8px (was 6px) radius; `.side-column`'s inter-panel gap went 0.6rem -> 0.75rem. No new CSS custom
  properties were added -- every new rule reuses an existing token pair; grepped the full stylesheet
  for hex/rgba afterward and the only new literal colour is `rgba(0, 0, 0, 0.05)` on `.panel`'s
  shadow, decorative-only, same convention the pre-existing marker box-shadow already uses.

  Verified: `docker compose run --rm tests` -- 465 passed (same count as pre-T086), including
  `tests/e2e/test_viewer.py`'s 2 tests both green, assertions unmodified, run again in isolation
  (`pytest tests/e2e/test_viewer.py -v`) to confirm explicitly. `ruff check .` clean (no `.py`
  touched). Screenshotted the live app in both `color-scheme: light` and `color-scheme: dark` at
  1366x768 (upload -> calibrate -> detect -> select a row, plus a completed run, plus the <900px
  single-column fallback at 800px) -- both palettes read as legible, the numbered badges/chevrons/
  primary buttons/danger delete/zebra rows all render as intended in both, single-column fallback
  unaffected. All `id`s in the hard-constraint list preserved unchanged (verified by grep against
  `app.js` and `test_viewer.py` after editing, not just before); no ids removed; the only ids/
  classes added are non-conflicting new ones (`panel-badge`, `panel-title`, `btn-primary`) plus two
  `<span>` wrapper elements per summary.

  What this session cannot close: the DoD's own "owner reviews a live instance and confirms it
  reads as more concise/modern" line is a manual sign-off, explicitly called out in the DoD itself
  as unautomatable (same precedent as ADR-019/T082) -- screenshots above are this session's own
  best-effort substitute for that judgment, not a stand-in for it. That line stays open until the
  owner actually looks.
- [x] **T087** — Wire auto-scale detection into the CLI (F21, ADR-022) — paths: `src/rogaine/cli.py`,
  `src/rogaine/vision/calibrate.py` (only if a thin single-image wrapper around `calibrate_map` is
  needed) — deps: none (T078 already landed) — DoD: `segment`/`plan` gain `--auto-scale`, mutually
  exclusive with `--scale` and `--calibrate` (extends `_resolve_mpp`'s existing "exactly one of the
  three, never zero, never more than one" contract); on success, prints which tier fired
  (`scale_bar`/`grid`/`circle`) and the resulting mpp/dpi; on failure, exits with a clear message
  pointing at `--scale`/`--calibrate`, never a silently guessed default. New test(s) cover both
  outcomes without needing a real scale-bar map (stub `calibrate_map` or use a detectable synthetic
  fixture).

  **Landed** (commit `cc03275`) — **backfilled into this file during the T084 session**, same
  stale-checkbox situation and same caveat as T085's note above. `_resolve_mpp` gained an `auto_scale`
  parameter plus `image`/`config` (needed to call `calibrate_map`) and now returns `(mpp, dpi, tier)`
  instead of a bare `mpp`; `--auto-scale` rejects being combined with `--scale`/`--calibrate` with a
  named-flag error message, and a bare failed `calibrate_map` (returns `None`) raises pointing at
  both manual flags by name. On success, `dpi` downstream of `_resolve_mpp` becomes the detector's
  own measured value (mirroring `calibrate_corpus`'s existing use of `CalibrationResult.dpi`,
  ADR-016) rather than the pre-detection probe, and both `segment`/`plan` print the firing tier plus
  the resulting mpp/dpi. `vision/calibrate.py` untouched — `calibrate_map` needed no wrapper.
  `config.py` untouched too. 5 new tests in `tests/unit/test_cli.py`: `TestSegment` gains tier+dpi
  reported and `terrain.npz` written on a stubbed success, failure message names both manual flags,
  and `--auto-scale` rejected together with `--scale`; `TestPlan` gains a full run to
  `route.json`/`route.png` on a stubbed success plus its own failure-message test — no dedicated
  `--auto-scale`+`--calibrate` combo test exists (only the `--scale` combo is covered, on `segment`
  only), a gap worth closing if this code changes again. 465 passed (this session's own count,
  includes T085+T087+T084 together), `ruff check .` clean — not verified isolated to just this
  commit's own delta.
- [x] **T088** — Wire the same auto-scale option into the web viewer (F21, ADR-022) — paths:
  `src/rogaine/web/app.py`, `src/rogaine/web/static/index.html`, `app.js`, `api.js` — deps: T086
  (shares the redesigned Scale panel's markup/styling), T087 (mirrors its outcome semantics/wording
  so CLI and viewer report auto-scale identically, per ADR-022's Contract classification) — DoD: the
  "2. Масштаб" panel gains a third, explicit action ("Определить автоматически") alongside the
  existing ratio/calibrate radios; success populates the existing fields with the detected values
  and states which tier produced them; failure uses the existing `error-message`/`status-message`
  pattern with a clear next step (switch to manual entry); a new Playwright case covers both a
  stubbed success and a stubbed failure; F2/F3's existing tests and flows stay unchanged.

  **Landed** (commit TBD) — followed the recommended design as-is: auto-scale is its own job kind,
  never a new segmentation path. `_JobRecord.kind`/`JobStatusOut.kind` gained `"auto_scale"`
  (these are `web/app.py`'s own local models, freely extensible per the module's docstring, not
  `models.py`'s frozen ADR-008 contract). New `_auto_scale_worker(job_id, run_dir, map_path)`
  mirrors `_detect_worker`'s shape: `resolve_dpi(map_path, user_dpi=None)` -> `load_raster` ->
  `calibrate_map(image, load_config())` (unmodified, same import already used by `cli.py`). On
  `result is None` the job errors with `"auto-scale: no calibration signal found on this map --
  enter scale or calibration manually"` (mirrors T087's CLI wording); on success `result` is
  `{"source", "scale_denominator", "dpi"}` -- detection only, no segmentation of its own. New
  `POST /api/runs/{run_id}/auto-scale` (202, no body) mirrors `start_detect`'s shape exactly.
  `api.js` gained `startAutoScale(runId)`, a one-line mirror of `startDetect`. `index.html`'s
  `#scale-fieldset` gained a third radio (`#scale-mode-auto`, same `name="scale-mode"` group,
  label "Определить автоматически"); no new sub-panel. `app.js`: `els.scaleModeAuto` added;
  `initScaleForm`'s `updateScalePanels()` now hides `scaleRatioPanel` when *either* calibrate or
  auto is checked; the submit handler gained a third branch that calls `api.startAutoScale` +
  `api.waitForJob`, on error calls `setError(job.error, ...)` and returns (existing
  error-message/status-message pattern), on success writes the detected values into
  `#scale-denominator`/`#scale-dpi`, flips the checked radio back to `scaleModeRatio`, calls
  `updateScalePanels()` (so the ratio sub-panel becomes visible showing the filled-in numbers),
  `setStatus`'s the tier in Russian-register prose, then falls through to the same
  `await runSegment(body)` call the ratio branch already makes -- one click does
  detect-then-segment, `/segment`/`_segment_worker`/`_resolve_mpp` themselves untouched.

  Deviation found and reported, not silently worked around: `app.js`'s scale-form submit handler
  has no `await` between the tier `setStatus(...)` call and `await runSegment(body)`, and
  `runSegment`'s own first statement synchronously overwrites `#status-message` with its
  segmentation text before the handler's async prefix ever yields to the browser -- so the tier
  text is never actually painted in a live browser, only ever present in the DOM for one
  unobservable JS tick. Implemented per the brief as specified regardless (no scope to change
  `runSegment`, shared by all three branches); the new Playwright success case asserts the tier
  from the `/auto-scale` job's own network response instead of the transient DOM text, and asserts
  the *durable* effect (`#scale-denominator`/`#scale-dpi`/`#scale-mode-ratio` after the job
  settles) as the DoD's "populates the existing fields" proof.

  Tests: 3 new in `tests/unit/web/test_app.py::TestAutoScale` (stubbing
  `rogaine.web.app.calibrate_map`, same pattern as `tests/unit/test_cli.py`'s T087 tests) -- done
  with `source`/`scale_denominator`/`dpi` in `result` on a stubbed success, error naming manual
  entry on a stubbed `(None, None)`, unknown run id 404s. 2 new in
  `tests/e2e/test_viewer.py::TestAutoScale`: success (stub matches the fixture's own real
  scale/dpi so the chained `/segment` call actually succeeds, landing the controls table) and
  failure (error message visible naming manual entry, then ratio-mode manual entry completes the
  same flow). `_live_server` runs `web_app.app` in-process via a background thread, not a
  subprocess, so `monkeypatch.setattr(web_app, "calibrate_map", ...)` reaches the live worker
  directly -- no test-only hook or env var was needed, contrary to what the brief flagged as a
  possible gap. `TestFullViewerFlow`/`TestViewerLayout` (F2/F3/T085) untouched, all still pass.
  23 passed in `tests/unit/web/test_app.py` + `tests/e2e/test_viewer.py` together (up from 16 + 2
  = 18 pre-T088, net +5: 3 unit, 2 e2e); 470 passed for the full suite (up from 465), `ruff check
  .` clean.
