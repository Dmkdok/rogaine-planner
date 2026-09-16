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
- [x] **T082** — Owner spot-check across the real-scan corpus (ADR-019) — paths: none (validation
  only; a throwaway script under `data/maps/` if useful, gitignored like its siblings) — deps:
  T077, T079, T080, T081 — DoD: re-run `rogaine detect` (and/or the viewer) on 2-3 of the owner's
  own maps post-fix; owner reviews the output and confirms circle positions, hub, and numbers look
  right. Recorded in `docs/STATUS.md`, not a new automated floor (ADR-019 — no ground truth exists
  for these files).

  **Done, partial pass (2026-09-11).** Owner: control-number recognition "стало лучше" (better than
  before) but still misses many clearly legible numbers, specifically on maps far from the base
  print scale (large physical sheet photographed from afar, or a small sheet photographed close
  up). Treated as this task's real spot-check result, not deferred — closes M9. The follow-up
  (measured diagnosis + fix) is filed as Iteration I4, M11, T089-T090; not reopening this task.

## M10 — Viewer UX, scale auto-detection exposure, control-number OCR (Iteration I3, `docs/iterations/I3-viewer-ux-and-detection.md`)

> Three independent workstreams, each internally serial, freely parallel with each other: OCR
> (T083 -> T084), UI (T085 -> T086, `T085` is the shared-primitive layout row and must land first),
> and the CLI half of scale-auto (T087, no shared files with the other two). `T088` (the web half of
> scale-auto) waits on both `T086` (shares `web/static/*`) and `T087` (mirrors its contract) — see
> the iteration doc's impact map for the full five-question breakdown per item.

- [x] **T083** — Diagnose control-number OCR failure on the owner's real scans — paths: none
  (diagnosis only; a throwaway measurement script under `data/maps/`, gitignored like its siblings)
  — deps: T077 — DoD: measure `_ocr_crop`/`_read_digits`'s actual behaviour against every owner real
  scan under `data/maps/` that has numbered controls (not just `grid-lines-red-controls`), recording
  a per-map read rate and the concrete, numbers-backed failure mode for each unread control (crop
  still misframed, wrong ink surviving the mask, resolution too low for Tesseract's assumptions,
  digit glyphs occluded by ring/hatching remnants, wrong `psm`/whitelist, etc.) — measured, not
  guessed, matching this project's own established practice (T079-T081). Findings and the resulting
  fix design get a new ADR in `DECISIONS.md` and feed T084 directly; no product-code changes in this
  task.

  **Landed** (commit `be8eccb`, ADR-023) — **checkbox found stale during this session, corrected
  per this project's own "trust the tree" rule**; no first-hand landing note exists for this task
  specifically because its findings were written directly into ADR-023 and then folded into T084's
  own "Mode 1"/"Mode 2" writeup above (T083 made no product-code change, per its own DoD). See
  ADR-023 in `DECISIONS.md` for the full measured diagnosis this task produced.
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

  **Landed** (commit `5957120`) — followed the recommended design as-is: auto-scale is its own job kind,
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

  **Follow-up fix, same session, independent verification** (commit `14bbccb`): the deviation
  above was real and worth closing, not just noting — DoD says success "states which tier produced
  them," and a message with no rendered frame does not do that for an actual person. Fixed with the
  minimal change that doesn't touch `runSegment` (still shared by all three branches, still
  untouched otherwise): a 1200ms `await new Promise((resolve) => setTimeout(resolve, 1200))`
  between setting the tier status text and falling through to `runSegment(body)`, giving the
  browser a real frame to paint it in before it's overwritten. Verified: full suite still 470
  passed (the new Playwright test already asserted the tier from the job's network response and
  the durable field values, not the transient DOM text, so it was insensitive to this timing
  either way and needed no change); `ruff check .` doesn't apply (`.js`, not `.py`).

  **Independent review, 2026-09-09 (verdict FAIL, then fixed same session)** — a `reviewer`
  subagent scoped to the `ead5510..14bbccb` diff (all of M10) found one Critical and one High
  defect, both in this task's own scope, plus two one-line Medium items; PASS confirmed after
  fixing all four (commit `f756da4`):
  - **C1 (Critical)** — the auto-scale success handler wrote `calibrate_map`'s raw
    `dpi`/`scale_denominator` straight into `#scale-dpi` (`step="0.1"`) and `#scale-denominator`
    (`step="1"`). Those values are essentially never round numbers (e.g.
    `296.83464566929132`), so the write fails HTML5 `stepMismatch` constraint validation on the
    *next* form submit — and because `#scale-dpi` sits inside whichever panel is currently
    `[hidden]` in calibrate mode, the browser can't even show a validation bubble, so
    `#scale-form`'s `submit` event silently stops firing for the rest of the session, in *both*
    scale modes. Reproduced live via Playwright before the fix (`stepMismatch: True`, `submit
    fired: False`). Fixed by rounding both fields to their own `step` precision on write
    (`Math.round(dpi * 10) / 10`, `Math.round(scale)`) — the unrounded values still flow into the
    `/segment` request body unchanged, so segmentation precision is untouched, only the two
    display/edit fields are affected. New regression test,
    `test_auto_scale_fractional_values_leave_a_second_submit_working`
    (`tests/e2e/test_viewer.py`), stubs a deliberately fractional dpi/denominator, drives
    auto-scale to success, switches to calibrate mode (reproducing the hidden-panel failure mode
    exactly), and asserts a second submit still reaches `/segment`.
  - **H1 (High)** — `/auto-scale` always measured PDF page 0 (`_auto_scale_worker`'s
    `load_raster` call took no `page`), while `cli.py`'s equivalent `--auto-scale` path correctly
    honours the user-selected page — a CLI/viewer contract drift ADR-022 explicitly meant to
    prevent. Fixed: new `AutoScaleRequest` body model (mirrors `SegmentRequest.page`'s
    `Field(default=0, ge=0)` convention) threaded through `start_auto_scale` ->
    `_auto_scale_worker` -> `load_raster(map_path, page=page, ...)`; `app.js`'s auto-scale submit
    branch now sends the same already-computed `page` value the ratio/calibrate branches use.
    New unit test, `test_auto_scale_passes_the_page_argument_to_load_raster`
    (`tests/unit/web/test_app.py`), stubs `load_raster` directly (not `calibrate_map`, which never
    sees the page number) and asserts `page == 3` reaches it.
  - **M3 (Medium, one-line)** — `aria-selected="true"` was being set on `#controls-table`'s plain
    `<tr>` rows, which carry no `role="grid"`/`treegrid` — an invalid ARIA attribute in this
    context (axe's `aria-allowed-attr`). Fixed by removing both the select and deselect call sites
    in `app.js`; the row's own `.row-selected` class and the map marker's `aria-current="true"`
    already carry the same information validly and are untouched.
  - **M4 (Medium, one-line)** — the auto-scale failure message
    (`"auto-scale: no calibration signal found..."`) was in English, landing straight in
    `#error-message` of an otherwise fully-Russian viewer — against CLAUDE.md's "User-facing
    language: Russian." Fixed by translating `web/app.py`'s message to Russian (the CLI's own
    English message in `cli.py` is intentionally untouched — CLI output stays English by this
    project's own convention, only the web viewer is Russian-facing); both the unit and e2e tests'
    assertions updated from the English substring to the Russian one.

  Also fixed, review-flagged, zero-risk comment corrections (no logic change): `ocr.py`'s
  `_MIN_INK_AREA_FACTOR` docstring described the formula backwards (implied `0.20 * h**2`, actual
  code computes `(h * 0.20) ** 2`, i.e. `0.04 * h**2` — the code was always right, only the
  comment was wrong); `style.css`'s `.table-scroll` comment still said the old "440px side column"
  pre-T086 number instead of the landed 460px.

  Independently re-verified, not trusted from the fixing subagent's own report: own read of the
  full diff, own `docker compose run --rm tests` — **472 passed**, exit 0 (470 baseline + 2 new:
  1 e2e, 1 unit); own `docker compose run --rm tests ruff check .` clean; own isolated run of
  `tests/e2e/test_viewer.py::TestAutoScale` + `tests/unit/web/test_app.py::TestAutoScale` (7
  passed, none skipped); own `git diff --stat` confirmed only the seven files named in the fix
  brief were touched, nothing else. Two manual owner sign-offs (T086's visual review, M9's T082
  spot-check) remain open — not something a review pass can close.

## M11 — OCR scale-invariance, points auto-fill, viewer route alternatives, route-choice heuristics, relief prep (Iteration I4, `docs/iterations/I4-ocr-scale-and-route-quality.md`)

> Five independent workstreams. **OCR** (T089 diagnose -> T090 fix) and **points-rule** (T091) both
> own `src/rogaine/vision/ocr.py`/`config/default.toml`/`tests/unit/vision/test_ocr.py` — land T091
> first (small, independent of T089's findings), then T090 after both T089 and T091 close, to avoid
> two concurrent edits to the same files. **Viewer-alternatives** (T093) and **points-viewer**
> (T092) both own `src/rogaine/web/static/app.js` — land T092 first (T091 depends on it anyway),
> then T093. **Route-choice** (T094 -> T095) and **relief-prep** (T096) touch neither vision nor web
> paths and are freely parallel with everything above.

- [x] **T089** — Diagnose control-number OCR/detection failure across map physical scale and DPI —
  paths: none (diagnosis only; a throwaway script under `data/maps/`, gitignored like its siblings)
  — deps: T084 — DoD: measure `detect_controls`/`read_control_numbers` end to end against every
  raster in `data/maps/` (owner's corpus at minimum; `ogps-*` harvest sample budget-permitting),
  bucketed by resolved DPI and, where derivable, approximate physical sheet size; explicitly test
  ADR-026's two hypotheses (DPI/auto-calibration accuracy for photographed maps; the
  `circle_scale_multipliers` ladder never sweeping below `1.0`) against the data, not assumed.
  Findings plus a fix design go into a new ADR and feed T090 directly; no product-code changes.

  **Landed** (ADR-030) — owner corpus reproduces T084's 205/416 (49.3%) baseline exactly. H1
  (DPI/calibration) not supported: owner-corpus DPI=300 maps alone span 4%-81% read rate; the full
  204-dir `ogps-*` sweep (203 loaded, 1 pre-existing decompression-bomb load failure) sits in a flat
  17.6%-29.9% band across every `cal_source`/`cal_tier`/DPI-bucket/sheet-size-bucket split, `measured`
  beating `assumed_default` by only 1.5 points. H2 (no sub-1.0 multiplier) is real but not uniformly
  helpful: apples-to-apples OCR (not just scorer preference) on the 7 owner maps where an extended
  0.3-6.0 sweep picks a different multiplier than production shows 3 genuine wins (kkm-toksovo
  4%→32%, lembolovo-kkm 35%→59%, novo-kavgolovsky-lesopark 29%→70%, +23 combined) and 4 regressions
  (history-race-2024-michurinskoe, history-race-primorsk, kkm-3-2020, ozero-shchuche, −47 combined) —
  net −24 if the ring-coverage scorer alone picked among a widened ladder. Traced to two distinct
  mechanisms: genuinely undersized hand-drawn circles (the 3 wins) vs. the same correctly-matched
  ring getting a smaller, mis-sized OCR crop (`_ocr_crop`'s crop/digit-size math scales with the
  matched radius) on 3 of the 4 regressions, plus one ADR-015-style false-cluster win on the fourth.
  Fix design for T090: add measured-justified sub-1.0 rungs (`0.5`, `0.85`; not lower — `0.4` is
  where the false-cluster failure appeared), gate any sub-1.0 winner behind an OCR-outcome check
  (run `read_control_numbers` on both candidates, keep whichever reads more) rather than trusting
  ring coverage alone, and re-verify the OCR crop-sizing constants across the full matched-scale
  range, not just the base scale. `docker compose run --rm tests` — 491 passed (this session's two
  concurrent T093/T095 landings had already raised the baseline from 475 by the time this commit was
  made; T089 itself added/removed none, diagnosis-only, no `src/` changes), `ruff check .` clean.

- [x] **T090** — Fix OCR/detection scale-invariance per T089's findings — paths:
  `src/rogaine/vision/controls.py`, `src/rogaine/vision/ocr.py`, `src/rogaine/vision/calibrate.py`
  (only if auto-calibration defaulting changes), `config/default.toml`, `src/rogaine/cli.py` /
  `src/rogaine/web/app.py` (only if auto-scale's opt-in default changes per T089's findings — a
  contract change needs both sides updated together, ADR-022 precedent), tests under
  `tests/unit/vision/` and, if the CLI/web default changes, `tests/unit/web/` — deps: T089, T091 —
  DoD: corpus-wide read rate and circle-detection recall/precision measurably improve beyond T089's
  own baseline, before/after counts recorded per-map in `docs/DECISIONS.md` (same style as
  T079-T081/ADR-023); `TestRealScanReadRateFloor`'s existing floors don't regress (raised or
  superseded with T090's own measured numbers); the synthetic fixture's 11/12 floor
  (`test_at_least_eleven_of_twelve_controls_read_correctly`) holds.

  **Landed** (ADR-031) — `config/default.toml`'s `circle_scale_multipliers` gains measured sub-1.0
  rungs `0.5`/`0.85`; `vision/controls.py::_detect_circles` gates any sub-1.0 winner behind a new
  `_ocr_gate_sub_base_scale` OCR-outcome check (runs `read_control_numbers` against both the sub-1.0
  and production candidate sets, keeps whichever reads strictly more). `vision/ocr.py`'s crop-sizing
  constants were re-verified (`data/maps/_t090_crop_sweep.py`, ADR-030 point 3) and left unchanged —
  no single value helps all 3 affected maps (kkm-toksovo improves monotonically with a wider crop
  margin, lembolovo-kkm peaks then regresses, novo-kavgolovsky-lesopark is flat) — measured, not a
  guess. Neither `calibrate.py` nor the CLI/web auto-scale default needed touching (T089's H1 found
  no case for it). Owner corpus: 205/416 (49.3%) -> 228/420 (54.3%), all +23 reads on the 3 maps
  ADR-030 predicted as genuine wins (kkm-toksovo +7, lembolovo-kkm +6, novo-kavgolovsky-lesopark
  +10), all 4 predicted regressions correctly avoided by the gate. Full `ogps-*` corpus (203/204
  loaded, same pre-existing decompression-bomb failure as T089): 2372/10343 (22.9%) -> 2796/11051
  (25.3%), every split that moved moved up, none regressed. `TestRealScanReadRateFloor` floors:
  `novo-kavgolovsky-lesopark` raised `>=5` (of 21) -> `>=13` (of 23, now 23 circles not 21 — its
  gated scale is 0.5); two new floors added, `kkm-toksovo` (`>=6` of 25) and `lembolovo-kkm` (`>=10`
  of 22, now 22 circles not 20). Full account, including the complete before/after per-map and
  per-split tables: `docs/DECISIONS.md` ADR-031. Corpus-wide rate (25.3%) is real but modest —
  ADR-030's own leading remaining suspect (leftover non-digit ink defeating Tesseract's `psm 7`,
  ADR-023's mode 1, never re-tested at `ogps-*` scale) is still open, flagged for the owner/a future
  iteration rather than silently left undocumented.

  **Independent review (scoped `reviewer` subagent, `473c410..HEAD`) found 2 real issues in T090
  itself, both fixed and re-verified same session** (499 passed = 493 + 6 new tests, `ruff check .`
  clean): (1) `_detect_hub_triangle` shared `circle_scale_multipliers` with `_detect_circles`, so
  the new sub-1.0 rungs fed hub matching with no OCR-style gate to catch a bad one — turned a
  correct "no hub found" into a spurious hub (confidence 0.298) on `history-race-primorsk`; fixed
  by sweeping only the `>=1.0` entries for hub matching (no measured evidence of an undersized hub
  anywhere in this corpus, unlike circles). (2) `_ocr_gate_sub_base_scale` had no direct unit test
  (only real-scan floor tests, all `skipif`-guarded on gitignored files) — added 5 tests driving
  all 4 branches with a stubbed `read_control_numbers`. A third proposed fix (bias
  `_select_best_scale`'s tie-break toward multiplier `1.0`) was investigated and **reverted**:
  `kkm-toksovo` ties in exactly the flagged way yet its two scales' OCR outcomes differ sharply
  (1/25 vs 8/25), so the bias would have skipped the gate and silently reverted this task's own
  headline win back to 4% — ring-coverage ties are not proof of OCR-outcome ties. Full account:
  ADR-031's own "Amendment" paragraph. Three lower-severity findings from the same review pass
  (T093's export-links/keyboard-focus bugs, T095's route-time-numbers framing) are outside T090's
  scope, tracked in `docs/STATUS.md`'s Iteration I4 section rather than fixed here.

- [x] **T091** — Fix `first_digit` points rule to use all digits but the last (ADR-024) — paths:
  `src/rogaine/vision/ocr.py`, `config/default.toml` (comment only), `tests/unit/vision/test_ocr.py`
  — deps: none — DoD: `_apply_points_rule`'s `first_digit` branch computes `number // 10`; existing
  `TestPointsRule` assertions unchanged (2-digit numbers give the same result under both formulas);
  new test covers a 3-digit number (`123` -> `12`) and documents the single-digit edge case
  (`7` -> `0`).

  **Landed** (`f4f0b15`) — `number // 10` replaces `int(str(number)[0])`; two new tests
  (`test_first_digit_uses_all_digits_but_the_last_for_a_three_digit_number`,
  `test_first_digit_floors_a_single_digit_number_to_zero`) call `_apply_points_rule` directly.
  474 passed (472 baseline + 2), `ruff check .` clean, diff confirmed scoped to the three named
  paths only.

- [x] **T092** — Viewer auto-fills points from a control's number, sticky-off once manually edited
  (ADR-024, F22) — paths: `src/rogaine/web/static/app.js` — deps: T091 — DoD: editing a control's
  number in the viewer auto-fills its points field via T091's corrected rule, unless that control's
  points has been hand-edited since its last detect/import (per-control, in-memory, resets on
  reload/re-import); covered by a new e2e case in `tests/e2e/test_viewer.py`.

  **Landed** (`c9ad78c`) — a module-level `WeakMap` (`pointsManuallySet`) keyed by control
  object identity, not `control.id`, so it resets for free whenever `state.controls` is replaced
  wholesale (a fresh detect or reload); kept out of the `PUT /api/runs/{runId}/controls` payload
  since that schema is `extra="forbid"`. The number-field handler auto-fills
  `Math.floor(number / 10)` (JS equivalent of T091's `number // 10`) unless the flag is set; the
  points-field handler sets it. New e2e case
  (`TestControlsPointsAutoFill::test_number_edit_autofills_points_until_points_hand_edited`) drives
  a real number edit (123 -> points 12), a hand-edit of points (-> 99), then a further number edit
  (-> 45) and asserts points stays 99. 475 passed (474 baseline + 1), `ruff check .` clean, `git
  diff --stat` scoped to `app.js` and the new test only.

- [x] **T093** — Viewer exposes the solver's existing top-K alternative routes, switchable (ADR-025)
  — paths: `src/rogaine/web/static/app.js`, `src/rogaine/web/static/index.html`,
  `src/rogaine/web/static/style.css` — deps: T092 (shares `app.js`) — DoD: when a plan response's
  `alternatives` array has more than one route, the viewer shows switch controls (labelled by
  rank/score, primary route always its own first option); selecting one redraws the map overlay and
  legs/summary panel client-side, no new server round-trip; hidden/absent when `alternatives` has
  zero or one entries; covered by a new e2e case.

  **Landed** — new `#route-switcher` button row (`role="group"`, above the summary `<dl>`) plus
  three `state` fields (`planPrimaryRoute`, `planAlternatives`, `selectedRouteIndex`); `onPlanDone`
  now takes `alternatives` too and delegates to `selectRouteOption(index)` (0 = primary, i =
  `planAlternatives[i-1]`), which redraws `view.setRoute`/`renderRouteResults`/`refreshControlsUI`
  and rebuilds the switcher client-side only (no fetch). `renderRouteSwitcher` hides the row
  entirely, not just empties it, unless `planAlternatives.length > 1`; `resetForNewRun` clears all
  three new fields and the row between runs. Two new e2e cases in `TestRouteAlternativesSwitcher`:
  one monkeypatches `web_app.solve_alternatives` (same technique `TestAutoScale` already uses for
  `calibrate_map`) for two deterministic, score-distinguishable alternatives and asserts 3 switcher
  buttons appear, selecting one updates `#route-score`/`#legs-tbody` to that alternative's own
  numbers with zero network requests fired, and reselecting the primary restores its own numbers;
  the other forces `RunConfig.alternatives=1` onto the real `/plan` POST body via Playwright request
  interception (the run form has no field for it) and asserts `#route-switcher` stays hidden and
  empty. `tests/e2e/test_viewer.py` alone: 8 passed (6 baseline + 2 new). `ruff check .` clean. Full
  suite: 474 passed, 3 failed — all three (`TestGoldenRegression`, cost `TestHandCheckedFormula`,
  vision `TestKSlope`) are in files this task never touched, caused by another agent's concurrent
  uncommitted work in the same tree (`config/default.toml`, `src/rogaine/cost/field.py`,
  `src/rogaine/vision/contours.py`); `git diff --stat` confirmed this task's own diff scoped to
  exactly the five paths named above.

- [x] **T094** — Route-choice heuristics: literature pass + human synthesis (ADR-027) — paths:
  `docs/research/route-choice-heuristics.md` (review/correct the existing haiku-drafted pass — a
  spot-check during intake found at least one mischaracterized/misattributed source, so citations
  need verifying, not just the rules list), `docs/DECISIONS.md` (new ADR selecting which rules this
  iteration actually implements) — deps: none — DoD: every cited source in the research document is
  verified to actually support its claimed rule (fetch and check, not trusted from the draft); the
  new ADR names which rules become T095's concrete scope and which are named explicitly as
  deferred/future (e.g. rules needing a concept this codebase doesn't have yet, like attack points).

  **Landed** (ADR-029) — every citation fetched and checked directly. Confirmed the intake
  spot-check: `baoc.org`'s "Attack_Point" page (cited for Rules 2 and 3) is a generic links
  directory, discusses neither — removed. A second misattribution found independently (Orienteering
  USA's "root cause" article, cited for Rule 4) — replaced. Five unsupported numbers removed (a
  "~5 contour lines" threshold, "5-10s/control", "5-15s/leg", "10-20% fatigue", Rule 8's pace
  bands). Cross-checked the surviving rules against actual `config/default.toml`/`cost/`/`solve/`
  code: Rule 1 (path-vs-direct) is already solved exactly by the existing Dijkstra grid solve, and
  Rule 5's vegetation speeds are already faithfully calibrated — neither explains the owner's "cuts
  through slow terrain" complaint; that points at the missing handrail/catching-feature attraction
  instead. ADR-029 scopes T095 to a linear-feature proximity bonus (Rules 2+7) plus a slope-penalty
  retune (Rule 6); defers attack points (Rule 3), vegetation fatigue (Rule 5 half), slope direction
  (Rule 6 half, ADR-028/T096's track), pace segmentation (Rule 8), and the rogaine time-safety
  buffer (Rule 9 half) as named future work. `git diff --stat` confirmed only
  `docs/research/route-choice-heuristics.md` changed by this task.

- [x] **T095** — Apply T094's selected route-choice rules to the cost/solve model — paths:
  `src/rogaine/cost/`, `src/rogaine/solve/`, `config/default.toml`, `tests/unit/cost/`,
  `tests/unit/solve/` — deps: T094 — DoD: set precisely by T094's synthesis ADR; bounded to
  cost-model tunables/config (no new search algorithm or ML scoring model, ADR-027); at least one
  measured, concrete improvement to route plausibility lands; owner reviews example routes
  before/after on a real map before this is considered done, not only a green suite.

  **Landed (implementation + measured before/after; owner review still open).** Two mechanisms
  per ADR-029, both `cost/`-level config/tunables, no new search algorithm or scoring model:

  1. **Linear-feature proximity bonus** (`src/rogaine/cost/proximity.py`, new) — distance-decay
     speed multiplier near any `road`/`vehicle_track`/`footpath` pixel (`k_proximity`), computed
     once via `scipy.ndimage.distance_transform_edt` and folded into `cost/field.py`'s
     `seconds_per_pixel` alongside `k_terrain`/`k_slope` (a third multiplicative factor). New
     `[proximity]` section in `config/default.toml` (`enabled`, `decay_distance_m`,
     `bonus_magnitude`), **shipped off by default** (ADR-029's own words) — with defaults
     unchanged, `k_proximity` returns exact `1.0` everywhere (no distance transform even run),
     confirmed bit-for-bit identical to the pre-T095 formula by a new regression test.
  2. **Slope-penalty retune** (`vision/contours.k_slope`, `config/default.toml [slope]`) — added a
     `density_exponent` knob (`1.0` recovers the old linear formula exactly); shipped default
     `penalty` 2.0 -> 6.0, `density_exponent` (new) -> 2.0 (quadratic). The two curves cross at
     density = 1/3: below it, a crossing now costs the same or less (small/sparse contours barely
     matter); above it, cost grows convexly and disproportionately (density 0.5: +25%; density
     1.0: +133%) — the literature's "2-storey vs 10-storey climb" framing (Rule 6). This is a
     direct default change, not gated behind a toggle.
  3. Rule 1 (path-vs-direct) and Rule 5's speed half: no code/config change, per ADR-029 point 3
     (already exactly/correctly solved) — no pinning test added, judged not worth the extra
     surface for something ADR-029 itself says isn't broken.

  Tests: `tests/unit/cost/test_proximity.py` (new, 9 cases — disabled-by-default returns exact
  `1.0`; hand-computed exponential-decay formula; peak bonus exactly on the feature pixel;
  monotonic decay; input validation) plus `tests/unit/cost/test_field.py` (+2 — bit-for-bit
  unchanged-by-default regression, and a synthetic near-vs-far-from-footpath case proving the
  enabled bonus strictly lowers `seconds_per_pixel`) and `tests/unit/vision/test_contours.py` (+3
  — shipped-default formula hand-checked, the convexity crossing point, `density_exponent=1.0`
  recovers the old linear formula exactly). `tests/e2e/golden_route.json` regenerated (route
  order/points/score/solver unchanged — only leg times/polylines shift with the retuned slope
  default, as expected; hand-verified against a fresh `plan --strategy exact` run on the same
  fixture/seed, same pattern as T053's original golden).

  Measured before/after (real map `data/maps/pervomayskoe`, real `segment` ->
  `compute_cost_field` -> `build_grid_graph` -> `build_travel_matrix` pipeline call path, no
  reimplementation — throwaway `data/maps/_t095_compare.py`, gitignored): two points 45m either
  side of a curved local footpath, offset perpendicular into the surrounding terrain. BEFORE
  (pre-T095 formula, proximity mechanism absent): 200.2s / 215.7m, cutting fairly directly away
  from the footpath. AFTER (T095 defaults, proximity bonus turned on at a concrete non-default
  value — `decay_distance_m=40`, `bonus_magnitude=0.5`, since it ships off): 146.2s / 253.3m —
  the route visibly bends to hug the nearby footpath instead, +17.5% distance for -26.9% time, a
  deliberate and clearly worthwhile trade, not a regression. Before/after overlay PNGs (full map
  + cropped) saved under `data/maps/_t095_compare_out/` (gitignored) for the owner's review.
  Separately, the slope retune alone (proximity still off, as shipped) already shows on the
  synthetic e2e fixture: total route time 10786.3s -> 10216.6s (-5.3%), same 6-control
  order/points/score.

  **Correction (independent review of the full M11 diff, after this landed):** the two time-delta
  numbers above (-26.9%, -5.3%) are not solely evidence of a *better* route — both new mechanisms
  lower `seconds_per_pixel` monotonically wherever they apply (`k_proximity >= 1.0` everywhere the
  bonus is enabled; the retuned slope formula's `density**2 <= density` on `[0, 1]`), so route
  *time* falls under the new cost model regardless of which route is chosen — confirmed directly on
  the synthetic-fixture case: `order`/`points`/`score`/`solver`/`optimal` are all bit-identical in
  `tests/e2e/golden_route.json`'s diff, only `total_seconds`/`total_meters` moved, a pure re-pricing
  of the same route, not a different one. The `pervomayskoe` case genuinely does pick a different,
  visibly better route (+17.5% distance to bend and hug the footpath) — that geometric claim is
  real and is what the owner's still-open review gate should be judged on — but the paired "-26.9%
  time" framing should not be read as independent supporting evidence for the route being better,
  since a worse route through the same terrain would also read a smaller number under the new cost
  model than under the old one. Not re-measured with an apples-to-apples fixed cost model (out of
  this review's scope); flagged here so the owner's sign-off is anchored on the route geometry, not
  the time delta.

  Verified: `docker compose run --rm tests` — 491 passed, 0 failed (14 new: 9 in
  `test_proximity.py`, 2 in `test_field.py`, 3 in `test_contours.py`). `ruff check .` clean.
  `git status` scoped to `config/default.toml`, `src/rogaine/config.py`, `src/rogaine/cost/field.py`
  (+new `proximity.py`), `src/rogaine/vision/contours.py`, `tests/e2e/golden_route.json`,
  `tests/unit/cost/test_field.py` (+new `test_proximity.py`), `tests/unit/vision/test_contours.py`,
  `docs/TASKS.md` — nothing under `data/maps/` staged (gitignored throwaway scripts/output only).

  **Owner sign-off received 2026-09-12** — closes the DoD's remaining manual gate. Reviewed
  against the geometric claim per the review's own correction above (+17.5% distance to bend and
  hug the footpath on `pervomayskoe`), not the paired time-delta framing. Owner decision:
  `[proximity].enabled` `false` -> `true` in `config/default.toml`, `decay_distance_m`/
  `bonus_magnitude` unchanged (still the real-map best-effort starting point, not a
  corpus-validated final tuning — a future retune is a separate task). Five tests whose premise was
  "off by default" were updated to match the new default rather than left red or silently reverted
  — `test_proximity.py`'s `TestDisabledByDefault` split into `TestEnabledByDefault` (new
  shipped-default assertion, +1 net test) and `TestDisabledExplicitly` (the same off-path, now via
  an explicit override); `test_field.py`'s `TestHandCheckedFormula` fixture now explicitly forces
  `proximity.enabled=False` so it keeps testing the base two-factor formula in isolation regardless
  of the shipped default; `TestProximityBonusIntegration`'s "default leaves seconds_per_pixel
  unchanged" test became "default applies the bonus" against the same three-factor formula
  `cost/field.py` itself computes. `tests/e2e/golden_route.json` regenerated a second time (same
  script/inputs as the first regeneration above): `order`/`points` (35) unchanged, `total_seconds`
  10216.6 -> 9444.1 (-7.6%), consistent with the real-map example's direction/magnitude. Full
  account: ADR-029's own amendment paragraph. 499 total pre-existing -> 500 passed (3 tests edited,
  1 net new), `ruff check .` clean — this session's own run, independently re-verified, not trusted
  from a self-report.

- [x] **T096** — Terrain relief (elevation/DEM) integration: research and prep, no implementation
  (ADR-028) — paths: `docs/research/terrain-relief-integration.md` — deps: none — DoD: document
  covers realistic elevation data sources given the Non-goals georeferencing constraint; how a real
  slope signal would plug into `cost/field.py`'s existing `k_slope`/`compute_cost_field` contract;
  what a separate off-road/forest base-speed parameter needs beyond the current 17-class
  `speed_factor` table; the georeferencing tension stated as an open question for the owner. No
  code, no config, no SPEC requirement added.

  **Landed** (`fc82460`) — checkbox was stale (still `[ ]`) despite the commit already on the tree;
  corrected per this project's own "trust the tree" rule, backfilled from the commit rather than
  re-done. See `docs/research/terrain-relief-integration.md` for the document itself.

## M12 — Control detection false negatives/positives on real scans (Iteration I5, `docs/iterations/I5-control-detection-false-negatives.md`)

> T097 (OCR crop edge clamp) and T098 (raw-radius consistency filter) touch different functions
> (`vision/ocr.py::_ocr_crop` vs. `vision/controls.py::_detect_circles`) and are freely parallel.
> T099 depends on T098 (both touch `_detect_circles`'s per-candidate data; land T098 first so T099
> doesn't thread the same raw-radius field twice). T100 depends on all three — it measures the
> combined effect and is the last task.
>
> **T098 closed with no code change** (see its own entry below — measured unsafe on real scans),
> so T099's stated dependency on it never materializes; T099 proceeds directly against the
> pre-existing `(x, y, r, coverage)` 4-tuple shape.

- [x] **T097** — OCR crop window slides instead of truncating at the raster edge — paths:
  `src/rogaine/vision/ocr.py`, `tests/unit/vision/test_ocr.py` — deps: none — DoD: `_ocr_crop`'s
  `(x0, y0, x1, y1)` window keeps its full configured half-width even when the control sits near
  the image boundary, by sliding the window rather than clamping-and-shrinking it (falls back to
  the current shrink behaviour only if the raster itself is smaller than the window); a new test
  with a control placed near each of the four edges confirms the crop reaches full size; every
  existing centred-control OCR test stays byte-identical (window unchanged when not near an edge).
  **Landed** (`c0ae26d`) — 5 new edge-adjacent-control tests, 505 passed overall (500 baseline + 5).

- [x] **T098** — Per-candidate raw-radius consistency filter in `_detect_circles` — paths:
  `src/rogaine/vision/controls.py`, `tests/unit/vision/test_controls.py` — deps: none — DoD: each
  Hough candidate's raw fitted radius (computed today, then discarded in favour of the matched
  scale's nominal `r_mid`, T077/ADR-020) is threaded alongside `r_mid` for this filter only; a
  candidate whose raw radius is a clear outlier against the winning scale's own accepted-candidate
  cluster is rejected. `Control.radius_px`/`_ocr_crop` continue to use `r_mid` unchanged — T077's
  reasoning for keeping crop sizing off the noisy raw fit is untouched. New synthetic test: one
  true-ring cluster plus a deliberately mis-sized coincidental blob at the same nominal scale —
  filter rejects the blob, keeps the cluster. Existing `_select_best_scale`/ring-coverage tests
  (ADR-015) stay green unchanged.
  **Closed, no code change — measured unsafe, not shipped.** A median+MAD modified-z-score filter
  on the raw radius was built and tried; it stripped genuine, already-validated detections on all
  3 of the real-scan read-rate floor tests measured (`kkm-toksovo` 25→21 circles, `lembolovo-kkm`
  22→20, `novo-kavgolovsky-lesopark` 23→13 — its own floor test's exact failure output) and failed
  its own synthetic decoy test (rejected a genuine ring, not the decoy). Root cause is structural,
  not a threshold-tuning miss: Hough's
  `minRadius`/`maxRadius` for a given multiplier are already `r_mid*(1∓circle_diameter_tolerance)`
  (`config.py::circle_radius_px`, tolerance `0.35`), so *every* raw candidate Hough can return for
  that multiplier already sits inside `[0.65, 1.35]×r_mid` by construction — there is no wider
  range for an outlier to occupy. Measured real raw/r_mid ratios on the 5 maps checked span
  0.663-1.333, i.e. genuine detections already routinely use the *entire* admissible band; no
  threshold inside that band can reject a "clear outlier" without also rejecting real controls
  that legitimately sit near the same edge. Same precedent as T080 (measured, not speculative;
  closed with no code change) — full account: `docs/DECISIONS.md` ADR-032's amendment.

- [x] **T099** — Per-candidate OCR gate for sub-1.0 scale winners — paths:
  `src/rogaine/vision/controls.py` — deps: none (T098 closed with no code change; the per-candidate
  data shape T099 works with is unaffected) — DoD: `_ocr_gate_sub_base_scale` (T090/ADR-031)
  changes from keeping/discarding its two whole candidate sets to gating each sub-1.0 candidate
  individually against its own OCR outcome, keeping only the ones that read a plausible number;
  the production (`>=1.0`) path is unchanged. Existing ADR-031 real-scan read-rate floors
  (`kkm-toksovo`, `lembolovo-kkm`, `novo-kavgolovsky-lesopark`) must not regress; new synthetic case
  with a mixed genuine-control-plus-glyph-false-positive sub-1.0 set proves the genuine one survives
  and the glyph one does not.
  **Landed** (`a0f6d59`), **then amended same session after the owner's T100 sign-off found it too
  aggressive.** First version also generalised beyond the DoD's letter (per-candidate probe running
  even with no `>=1.0` candidate to compare against, closing item 4's cover-page/legend-text gap
  even without a production alternative) and measured clean against the 3 ADR-031 real-scan floors
  (circle counts dropped, absolute `n_read` unchanged in every case). But T100's own visual
  spot-check (not just the aggregate counts) found this first version silently dropped confirmed
  real, legible, correctly-positioned controls (91, 92, 72, 52 on `kkm-toksovo`) that Tesseract
  simply never read — before T099 these still appeared detected-but-unread (flagged); after, they
  vanished entirely, an F8-spirit regression the aggregate floor numbers alone did not surface.
  **Amended** (ADR-032's own amendment): `_ocr_gate_sub_base_scale` now only filters down to the
  reading candidates when the sub-1.0 set looks junk-dominated (`_SUB_BASE_JUNK_UNREAD_FRACTION =
  0.85`, the owner's own chosen resolution among 3 options put to them, explicitly accepting this
  threshold is calibrated against only 2 real points); below that fraction the whole set is kept,
  flagged unread like any production-scale detection. Re-verified: owner's 14-map corpus circles
  420→420 (net 0 — none of the 14 crosses the 85% line), reads 228→229 (+1, T097's own
  contribution), rate 54.3%→54.5%; 40-map `ogps-*` sample circles 1877→1629 (-13.2%), reads 528→527
  (-1, noise); `ogps-3771`'s own clean win (213 pink-hatching false positives removed) confirmed
  unchanged at 17/17. Two stale unit tests replaced with four exercising both sides of the
  junk-fraction line; the 3 ADR-031 floor tests' `len(circles) ==` assertions reverted to their
  T090 values (25, 22, 23) — `n_read >=` floors untouched throughout, since the absolute
  successful-read count never changed. 509 passed, `ruff check .` clean.

- [x] **T100** — Confirm the colour heuristic's coverage and measure the combined effect — paths:
  `tests/unit/vision/test_controls.py` (pinning test only if a gap is found), throwaway
  `data/maps/_t100_measure.py` (gitignored, same convention as T089/T090's own scripts) — deps:
  T097, T098, T099 — DoD: confirm `purple_mask`/`ink_hue_ranges` already gate every detection and
  OCR-crop code path (add a regression test only if an actual gap is found, not speculatively);
  re-measure false-positive rate and OCR read rate across the owner's real corpus (`data/maps/` +
  an `ogps-*` sample) before/after T097-T099, recorded in `docs/DECISIONS.md`'s ADR-032 regardless
  of direction; before/after crops for controls matching the owner's own reported examples sent to
  the owner for the manual sign-off this milestone's DoD requires (ADR-019 precedent) before this
  checkbox closes.
  **Done.** Colour-heuristic coverage confirmed (no gap, no speculative test added). First
  measurement pass (T099's first version) found a real trade-off — `ogps-3771` cleanly dropped 213
  pink-hatching false positives, but the owner's own `kkm-toksovo` also silently dropped confirmed
  real, legible controls (91/92/72/52) — put to the owner as 3 options (keep / fully revert / a
  junk-fraction heuristic); **owner chose the heuristic**, T099 amended accordingly (own entry
  above, ADR-032's amendment). Final re-measurement after the amendment: owner's 14-map corpus
  circles 420→420 (net 0), reads 228→229 (+1, T097's own contribution), rate 54.3%→54.5%; 40-map
  `ogps-*` sample circles 1877→1629 (-13.2%), reads 528→527 (-1, noise); `ogps-3771`'s own clean win
  confirmed unchanged at 17/17. Before/after crops and the amendment's own resolution sent to the
  owner via `SendUserFile`. Full account: `docs/DECISIONS.md` ADR-032's amendments.

## M13 — Real-map detection gaps and viewer UX (Iteration I6, `docs/iterations/I6-real-map-detection-gaps-and-viewer-ux.md`)

> T103 before T105 (both touch `vision/controls.py`'s `_detect_circles` candidate list — T103 must
> remove the forbidden-symbol false positives before T105's confidence floor is measured against a
> clean corpus). T102 before T104 assumed both would touch `vision/ocr.py::_ocr_crop`'s masking
> step — **T104's own diagnosis found this wrong (ADR-034): its real cause is a `_select_best_scale`
> tie-break gap in `vision/controls.py`, not an ink-masking issue at all**, so this ordering
> constraint turned out not to apply (landed independently of T102, though after it in session
> order). T106 before T107 (both touch `app.js`'s pointer/mode machinery — T106 fixes the shared
> click-vs-drag distinction and active-state affordance, T107 reuses it for the panel's single-shot
> add-control flow). T101 is independent (own file, `vision/palette.py`) and freely parallel with
> everything else.

- [x] **T101** — Fix real-scan water/river misclassification — paths: `src/rogaine/vision/palette.py`,
  `tests/unit/vision/test_segment.py`, possibly `config/default.toml` — deps: none — DoD: diagnose
  (against `data/maps/ogps-6802_4a769f64b455f9b4675552284c3681b1`) why this map's river ink does not
  land in `water_uncrossable`'s configured Lab band before designing a fix (ADR-026 precedent);
  `rogaine plan` on this map no longer routes through the river; a known crossable ditch/shallow
  watercourse on the same map stays passable; every existing synthetic-fixture IoU floor
  (`test_segment.py`) unchanged; a new real-scan classification test pins the fixed behaviour,
  skipped when the gitignored scan is absent (ADR-010 convention). **Landed.** Diagnosed first
  (`data/maps/_t101_diagnose.py`, gitignored): the river's ink is not outside the configured Lab
  band at all — `classify_labels`'s per-pixel nearest-shade choice fragments one continuous,
  bank-lined river into thousands of tiny `water_uncrossable` islands (largest single fragment
  341px) inside an otherwise `water_shallow` blob, nowhere near enough to block a route. Fix:
  `_consolidate_banked_water` (new, `palette.py`) promotes a whole connected water blob to
  `water_uncrossable` once >=30% of its own boundary ring sits within 2px of `road`-shaded
  (`black_100`) ink — the one signal `config/default.toml` already documents as distinguishing the
  two shades ("emphasised by a black bank line") — vectorised via `scipy.ndimage` (~0.4s vs. a
  measured ~120s per-component Python loop on this 3107x3278 scan). A hatched/screened marsh with
  no such border is untouched by construction (measured: a bbox at the marsh's own location stays
  93% `water_shallow`, wu=200/ws=2825). `rogaine plan` verified end to end (`data/maps/_t101_plan_
  before`/`_after`, gitignored): before, a solved route crossed the river at 7px of measured
  overlap near control 58; after, 0px. Pinned as a deterministic structural check instead
  (`GridGraph.block_passable` at the river's own deepest interior point is `False`) rather than a
  full solve — `solve_heuristic`'s real wall-clock time budget made its own tour non-reproducible
  run-to-run (measured: 3 identical runs gave 89/59/162px of incidental overlap even before this
  distinction), an unusable regression signal; same precedent as T103's own out-of-bounds
  confirmation (checked at the mechanism, not by solving). New
  `TestBankedWaterConsolidationOnRealScan` (2 cases) in `test_segment.py`; every existing IoU/
  grid-ink floor unchanged. 518 passed (together with T102, T103's own fix), `ruff check .` clean.
  **Milestone review finding M-4 (2026-09-14, see T107's own entry for the full review account):**
  `_consolidate_banked_water` runs inside `classify_palette` itself, so `segment.py`'s module
  docstring no longer accurately promised `reclassify_grid_ink` the palette's classification
  "untouched by any later stage" — corrected. In practice this still doesn't collide with
  `reclassify_grid_ink`'s own column/row test (it sums across both water classes, blind to a
  promotion within that sum), but a real, not yet corpus-tested risk was named: a shallow
  watercourse 8-connected to a genuinely bank-lined body (e.g. a ditch draining into a river) is
  promoted whole along with it, since `_consolidate_banked_water` promotes by connected component —
  outside this task's own diagnosed case (`ogps-6802`'s marsh, a disjoint blob). Not fixed here
  (no measured instance to fix against, same precedent as T098's reverted unmeasured filter);
  filed as a follow-up for the owner/a future iteration.

- [x] **T102** — Fix missing OCR reads on `ogps-6802` controls 42/53/72 — paths:
  `src/rogaine/vision/ocr.py`, `tests/unit/vision/test_ocr.py` — deps: none — DoD: diagnose which
  known real-scan OCR failure mode (ADR-023's leftover-ink/ring-erasure families) or new mechanism
  applies to these three controls before changing `_ocr_crop`; a new `TestRealScanReadRateFloor`
  case for this map with 42/53/72 (or a documented subset) reading correctly; every existing
  `TestRealScanReadRateFloor` floor re-run and unchanged or improved, never silently dropped.
  **Landed, documented subset.** Diagnosed each of the three individually by cropping
  (`data/maps/_t102_inspect_unread.py`, gitignored) — three different, unrelated root causes, not
  one shared bug: **72** — a contour-line/mark fragment survived `_strip_thin_ink`'s area floor and
  sat 43px (~1.2x digit height) above the real digits, a genuine new mechanism (leftover-ink
  clusters), not one of ADR-023's two named families. **42** and **53** — both crops are already
  clean (no stray ink); Tesseract itself reads "42" at 0% confidence and misreads "5" as "9" ("93")
  at 41% respectively — a confidence-calibration and a character-confusion problem, neither an
  ink-masking issue, out of this task's scope (documented, not silently dropped, per the DoD's own
  "or a documented subset" clause). Fix: `_keep_largest_ink_cluster` (new, `ocr.py`) keeps only the
  largest dilation-connected group of remaining ink (a control's own digits are always one such
  group), dropping a farther, unrelated leftover blob. `_INK_CLUSTER_GAP_FACTOR=0.5` (digit
  heights) swept 0.0/0.3/0.4/0.5/0.65/0.8/1.0 against the synthetic fixture and every existing
  real-scan floor (`data/maps/_t102_sweep.py`, gitignored) — every value from 0.3 to 1.0 left every
  floor unchanged or improved. **One real finding, guarded before landing:** an early version
  (winner = largest group, no further check) turned a pre-existing wrong read on `kkm-toksovo`
  control 13 (a stray unerased-ring artifact discarded correctly, but the true number's own leading
  digit was separately clipped by the crop window) from a safe "no digits found" into a confidently
  wrong short number ("2" of a true "72") — found by a per-control before/after diff
  (`data/maps/_t102_diff_check.py`) and a visual crop, not assumed. Fixed by discarding the winning
  cluster outright when it both had real competition (more than one group existed) and touches the
  crop's own edge — narrow enough that it does not touch the many real scans where a full,
  correctly-captured number legitimately sits close to the margin with nothing to compete against
  (a blanket "reject any edge-touching cluster" was tried first and rejected: it cost ~25
  previously-correct reads across the owner corpus for this one avoided wrong guess). This guard
  incidentally also caught two more pre-existing wrong reads elsewhere (`pervomayskoe` control 14
  read "5" of a true "35"; `kkm-toksovo` control 10 read "3" of a longer number) — both now
  correctly flagged unread instead (ADR-009: never a guess) — and, on the synthetic fixture, fixed
  the one control the module's own docstring had documented as a known unreadable limitation since
  T021 (`id=8`, truth 83, purple out-of-bounds hatching inside the crop margin) — now reads
  correctly like every other control; `TestPointsRule`'s two "unreadable" cases and
  `TestReadsNumbersOnFixture`'s boundary-control case were re-pointed at a directly-constructed
  blank-ink crop instead of depending on that now-fixed incidental fixture noise. New
  `test_ogps_6802_control_72_reads_correctly` in `TestRealScanReadRateFloor` (circles==35, n_read
  >=30, control at (1175, 2475) == 72); `pervomayskoe`/`novo-kavgolovsky-lesopark`/`kkm-toksovo`/
  `lembolovo-kkm` floors all re-verified, values unchanged, actual counts documented per-map (some
  moved down slightly from a wrong-read correction, all still comfortably above their own floor).
  **Milestone review finding M-5 (2026-09-14, see T107's own entry for the full review account):**
  the competition+edge guard above (originally added to fix the `kkm-toksovo` control-13 case)
  covers only an edge-clipped false positive; a group split by a wide inter-digit gap that also has
  unrelated competing ink elsewhere, but away from the crop edge, would still be silently discarded
  in favour of a confidently-wrong shorter read. Not reproduced against any map in either corpus (the
  0.3-1.0 gap-factor sweep measures read *counts*, which can't distinguish a new correct read from a
  new wrong one), so not fixed here — same precedent as T098's reverted unmeasured filter; filed as
  a follow-up for the owner/a future iteration, not silently dropped.

- [x] **T103** — Exclude the ISOM 709 out-of-bounds symbol from control detection and confirm it
  stays impassable in routing — paths: `src/rogaine/vision/controls.py`, possibly a new dependency
  on `vision/palette.py`'s terrain labels, `tests/unit/vision/test_controls.py` — deps: none — DoD:
  diagnose the symbol's actual rendering on `data/maps/ogps-7302_5d8c290224a04f49e2c95484d2fbaf92`
  (solid fill vs. hatch) before choosing between reusing `classify_palette`'s `out_of_bounds` mask
  as an exclusion region and a dedicated shape discriminator; a new synthetic test (an
  `out_of_bounds` block plus real control circles) shows zero spurious candidates inside the block
  and all real circles still found; `ogps-7302`'s own circle count drops from dozens of false
  positives to the map's true control count; confirm (no code change expected) that routing already
  excludes `out_of_bounds` once correctly classified — `cost/graph.py`'s existing
  `strict_impassable` path, not a new mechanism. **Landed** (`0c5f1f7`/`fe863b3`, checkbox backfilled
  per trust-the-tree — the landing session ran out of budget before its own docs bookkeeping).
  Diagnosed on `ogps-7302`: ISOM 709 renders as dense diagonal cross-hatch in the same purple ink as
  a 703 ring, not a solid fill, so `classify_palette`'s `out_of_bounds` mask (hatch-line pixels
  only) can't bound it; `_ring_coverage`'s circumference check alone can't reject it either (hatch
  density saturates it to 1.000). Fix: `_interior_ink_fraction` samples a disc well inside the
  fitted circle, clear of its own ring stroke — a real ring's interior is bare (measured
  0.000-0.099), a hatch-crossing false fit still has ink there (measured 0.622-0.844) — rejecting
  above 0.3. `ogps-7302` candidate count 65 -> 35, hub still found, routing confirmed unaffected
  (`strict_impassable`, no code change). New synthetic `TestOutOfBoundsHatchExcluded`. **Landed in
  an isolated worktree with no `data/maps/` (gitignored real scans), so its own 503-passed/
  11-skipped verification never ran the real-corpus `TestRealScanReadRateFloor` suite** — merging to
  the main tree and actually running it (this session) found the per-candidate interior-ink filter
  also, correctly, excludes a long-standing false positive on 3 unrelated maps: a club mascot logo
  (a running figure, printed in two colour bands both inside `purple_mask`'s hue range) that fit a
  spurious ring on `novo-kavgolovsky-lesopark`/`kkm-toksovo`/`lembolovo-kkm`, confirmed by visual
  crop (`data/maps/_t103_crop_dropped.py`, gitignored) — `interior_ink_fraction` measured 1.0 on
  every instance, far past the 0.3 threshold. Not a regression: these were never real controls, just
  uncaught by any earlier discriminant; their circle-count floors moved down by exactly the false
  positives removed (23->21, 25->24, 22->21) with the reason documented inline, `n_read` (true
  positives) unchanged throughout (fix commit `b91677a`).

- [x] **T104** — Extend OCR to read a control's number when printed in a different colour from its
  own ring — paths: `src/rogaine/vision/ocr.py` — deps: T102 (same function, `_ocr_crop`'s masking
  step; land T102 first) — DoD: diagnose `data/maps/ogps-8078_8295c94963b2c249d6f4d94fd0c35fa1`'s
  exact two-colour print style before widening the crop's ink mask; the widening must not reintroduce
  contour-line bleed into the crop (ADR-023's own past failure mode — its regression test must stay
  green); a new `TestRealScanReadRateFloor` case for `ogps-8078` with previously-unread numbers now
  reading; existing floors unchanged or improved. **Landed, but not as titled — the DoD's own
  premise did not survive diagnosis (ADR-034).** Direct pixel sampling of the printed numbers
  found no two-colour issue at all: "66"/"38"/etc. are the same purple/red ink `purple_mask`
  already detects, confirmed by eye. The real cause is in `vision/controls.py`, not `ocr.py`:
  `_select_best_scale` ties multipliers 2.0/2.5/3.0 on this map (same 52 physical rings, near-
  identical coverage, all bucketed to the same `_SCALE_TIE_EPS` tier — a thick/doubled printed
  ring passes `_ring_coverage` at several nested radii) and its sweep-order default picks the
  smallest tied multiplier, undersizing `_ocr_crop`'s ring-erase disk for this map's true (larger)
  print size — 2/52 read. Forcing every radius to multiplier 3.0 confirmed the mechanism directly
  (30/52). Fix: `_ocr_gate_tied_scales` (new), scoped to `>=1.0` ties only (never touches
  `_ocr_gate_sub_base_scale`'s already-tuned sub-1.0 territory, ADR-031) — probes real OCR outcome
  across only the tied multipliers and keeps whichever reads most, the same principle as ADR-031's
  own gate, not a blind directional bias (which `_select_best_scale`'s own docstring already shows
  is unsafe in the other direction: `kkm-toksovo` ties `0.85` against `1.0`, and `0.85` is
  correct). `ogps-8078`: 2/52 → 40/52. Measured before landing: full suite 518 passed (one
  pre-existing `ogps-6802` test's expectation updated, see below, not silently broken); owner's own
  14-map corpus, every map unchanged or improved, zero regressions (`kkm-toksovo` exactly
  unchanged — 24/12 before and after, confirming the sub-1.0 pathway is untouched;
  `pervomayskoe` 18→32, `history-race-2024-michurinskoe` 13→25 reads); a random 30-map `ogps-*`
  sample, circle counts unchanged everywhere (1110→1110), reads 582→690 (+18.6%), zero
  regressions, 4 maps changed and all four improved. `ogps-6802`'s own scale ties too (`2.25`ish
  against `3.0`) — the gate now correctly prefers `3.0` map-wide (33/35 vs 32/35), which
  incidentally fixes the *other* two of the owner's three T102-named controls (42, 53 — their
  "Tesseract confidence/misread quirk" diagnosis in T102 turns out to have been a downstream
  symptom of this same undersized-scale problem, both now read at 96% confidence) at the cost of
  72 reading only a truncated "7" at 0% confidence instead — refused safely (ADR-009), not a wrong
  guess. `TestRealScanReadRateFloor::test_ogps_6802_control_72_reads_correctly` renamed/updated to
  `test_ogps_6802_named_controls`, pinning all three controls' new (still correct) outcome.

- [x] **T105** — Confidence-gated auto-placement floor — paths: `src/rogaine/vision/controls.py`
  (`_detect_circles`'s final candidate filter) — deps: T103 (land after the forbidden-symbol
  exclusion so the corpus measurement below is not contaminated by those false positives); informally
  sequenced after T102/T104 (an OCR fix changes which candidates are worth keeping) — DoD: pick a
  conservative, corpus-measured confidence floor (ADR-033: shipped directly, no intermediate owner
  review step) below which a candidate is dropped rather than auto-placed as a `Control`; corpus-wide
  before/after circle-count measurement (owner's 14-map corpus + an `ogps-*` sample, T099/T100's own
  method) recorded in `docs/DECISIONS.md` regardless of direction; every existing circle-count floor
  (`TestRealScanReadRateFloor` et al.) re-verified — any that must move is a named, measured change,
  never a silent regression; a new synthetic test with a deliberately marginal false-positive
  candidate confirms it is dropped, not auto-placed. **Landed (ADR-035).** Measured the owner's
  14-map corpus plus the three named `ogps-*` maps (524 real detections) before picking a value:
  the confidence (`_ring_coverage`) distribution has no natural gap — 88% at [0.99,1.0), the rest
  spread smoothly down to 0.764, every one below 0.85 individually cropped and visually confirmed
  a genuine control (imperfect ring-fit from terrain ink/print noise), not a false positive. No
  known false positive exists in this corpus below 1.0 confidence for a floor to actually catch.
  `_AUTO_PLACEMENT_CONFIDENCE_FLOOR = 0.80` chosen as a small, named, accepted cost (per ADR-033's
  own advance risk acceptance) rather than a measured win: drops exactly 4/524 (0.76%) real
  detections, all confirmed genuine, none on the owner's most-inspected maps
  (`kkm-*`/`toksovo-*`/`pervomayskoe`/`ogps-6802`/`ogps-7302`/`ogps-8078`/`michurinskoe`/
  `ozero-shchuche`/`grid-lines-red-controls` all unaffected). New `TestAutoPlacementConfidenceFloor`
  (a synthetic ring missing 80/360 degrees, coverage ~0.778 — clears the base 0.75
  `_RING_COVERAGE_MIN` but not this floor — confirmed dropped alongside genuine full rings kept).
  519 passed (518 + this task's own test), `ruff check .` clean; every existing circle-count floor
  unchanged (the 4 dropped detections are not on any pinned-floor map).

- [x] **T106** — Calibration tool active-state UX and click-vs-drag fix — paths:
  `src/rogaine/web/static/app.js` (`initMapViewport`'s `pointerdown` handler, `setMode`,
  `setCalibrationPoint`), `src/rogaine/web/static/style.css` — deps: none — DoD: while `calibrate`
  mode is armed, a pointer-down-move-up gesture (a drag) pans the map instead of placing or
  overwriting a calibration point — only a genuine click (no meaningful movement between down and
  up) places one; the armed state gets a visibly distinct affordance beyond the existing
  `button[aria-pressed="true"]` accent colour already used for ordinary primary actions elsewhere
  (e.g. a red/warning treatment), so the user cannot mistake it for a normal button; a new
  `tests/e2e/test_viewer.py` case exercises both the drag-pans and click-places behaviours.
  **Landed** (`774f10c`/`b1f2e06`, checkbox backfilled per trust-the-tree — same interrupted-session
  gap as T103). New `CLICK_DRAG_THRESHOLD_PX` + `beginArmedPointerGesture` helper in
  `initMapViewport`'s `pointerdown` handler distinguish a genuine click from a pan drag while
  `calibrate` mode is armed, so panning never places or corrupts a calibration point; the armed
  state gets a distinct danger-toned affordance (button + map outline) beyond the existing
  `aria-pressed` accent. New e2e case covers both drag-pans and click-places. Landed in an isolated
  worktree (503 passed, 11 skipped, no `data/maps/`); re-verified against the main tree this session
  as part of the full-suite run below — JS/e2e change, unaffected by the real-corpus vision floors
  T103 collided with.
  **Milestone review findings M-1/M-2/M-3 (2026-09-14, see T107's own entry for the full review
  account):** M-1 — `.map-viewport:focus-visible` (equal specificity to the armed-mode outline
  rules, and earlier in source order) always lost to them, so a keyboard user tabbing to the map
  while a tool was armed — the default path, since both arming handlers focus the viewport — saw no
  distinguishable focus indicator; fixed with a later, same-specificity `:focus-visible` rule that
  wins only while actually focused. M-2 — the warning-toned armed outline (T107's own state, see
  below) measured ~1.9:1 against a light/white scanned map, short of WCAG 1.4.11's 3:1 (T106's own
  danger-toned outline needed no such fix, ~5.9:1); fixed with a 1px inset `--text` line. M-3 —
  `beginArmedPointerGesture` removed its `pointermove`/`pointerup` listeners only inside `onUp`, so a
  `pointercancel` (touch palm rejection, pointer disconnect, an OS gesture taking over) left both
  bound to the canvas; a later, unrelated stationary click would then still fire the stale `onUp` and
  place a point while every other affordance already read idle — fixed with `pointercancel` teardown
  and a mode guard captured at arm time. All three fixed same session as T107's milestone review.

- [x] **T107** — Manual add-control click-to-place flow — paths:
  `src/rogaine/web/static/app.js` (`add-control-btn`'s click handler) — deps: T106 (reuses its fixed
  pointer/mode machinery rather than duplicating a second path) — DoD: clicking "Добавить контроль"
  arms add-mode without placing anything; the next map click places the control exactly there (not
  the view centre); placement immediately returns the tool to idle so the map is draggable again,
  matching the calibration-line tool's own click-to-place flow; the existing `toggle-add-mode-btn`
  multi-placement flow is untouched; a new `tests/e2e/test_viewer.py` case covers click-to-place plus
  the immediate return to idle.
  **Landed.** New `state.mode = "add-once"`: `#add-control-btn`'s click handler now calls
  `setMode("add-once")` instead of placing at `view.viewCenterMap()` immediately (clicking again
  while armed disarms it, same convention as `#calib-start-btn`); `initMapViewport`'s `pointerdown`
  handler routes `add-once` through T106's own `beginArmedPointerGesture` helper with an `onClick`
  that places the control at the click's map coordinates and calls `setMode("idle")` — exactly the
  extension point that helper's own docstring had already reserved for this task, no second
  pointer-handling path added. `toggle-add-mode-btn`'s pre-existing `state.mode = "add"` multi-
  placement path is untouched (separate branch, separate mode string). One addition beyond the
  DoD's own text: SPEC F17 states plainly that *both* the calibration-line and add-control tools
  need "a visibly distinct armed affordance" (not just the click-to-place mechanics), so
  `#add-control-btn[aria-pressed="true"]` and `.map-viewport.mode-add-once` get the existing
  `--warning-bg`/`--warning-border` tokens (not `--danger`, reserved for the calibration tool's own
  overwrite-risk framing per T106's own CSS comment — placing a control has no such risk) instead of
  being left at the shared, easily-confused `button[aria-pressed="true"]` accent. New
  `TestAddControlClickToPlace` (`tests/e2e/test_viewer.py`): arming without placing; two placements
  at different screen points landing at two different, click-dependent map positions (the concrete
  proof the old view-centre bug did not survive — a fixed centre would give identical positions
  both times) with a directional check (`xb > xa`, `yb < ya`, matching the two click points' own
  screen offsets) rather than reading internal JS module state (`state`/`view` are ES-module-scoped,
  not reachable from `page.evaluate`'s global context — read from the `#control-{id}-x`/`-y` table
  inputs instead, same technique `TestFullViewerFlow` already uses); armed-state
  aria-pressed/CSS-class assertions mirroring T106's own test; a final drag proving the tool
  returned to idle (pans, does not place a third control). 520 passed (519 + this task's own test),
  `ruff check .` clean; `git status` confirmed only the three touched files changed at landing time
  (see the milestone review below for what changed after).

  **Milestone review, 2026-09-14.** Scoped `reviewer` subagent, `ba27ff1..HEAD` (the full M13 diff,
  T101-T107, plus a working tree that already carried two uncommitted fixes from an earlier review
  pass whose own session was interrupted before it could commit or write up docs — H1/H2 below).
  **Verdict: PASS WITH WAIVERS.** Reviewer independently ran `docker compose run --rm tests` (520
  passed) and `ruff check .` (clean) itself, not trusted from any commit message.

  No Critical. **One High, fixed same session:**
  - **H-1** — T106's own scope note named both `calibrate` and the `add` toggle as consumers of the
    shared click-vs-drag fix ("T106 fixes the shared click-vs-drag distinction and active-state
    affordance, used by both `calibrate` and `add` modes"), and SPEC F17 says panning while
    *either* tool is armed never places or corrupts a point — but T107 only extended `add-once`'s
    flow; the persistent `add` toggle (`toggle-add-mode-btn`) still placed straight on
    `pointerdown`, so a drag while it was armed dropped a spurious control at the drag origin
    instead of panning, the exact bug T106 fixed for `calibrate`. Fixed: `app.js`'s `pointerdown`
    handler now routes `add` through `beginArmedPointerGesture` too (a persistent mode, so
    `onClick` does not call `setMode("idle")`); `style.css` gives
    `toggle-add-mode-btn[aria-pressed="true"]` and `.map-viewport.mode-add` the same warning-toned
    affordance `add-once` already had. New `TestToggleAddModeArmedState`
    (`tests/e2e/test_viewer.py`) mirrors T106's own drag-pans/click-places proof for the persistent
    mode.

  **Six Medium, all fixed same session** (M-1/M-2/M-3 recorded in T106's own entry above, since they
  are in the shared `beginArmedPointerGesture`/CSS mechanism T106 introduced; M-4/M-5 recorded in
  T101's/T102's own entries, since they are about those tasks' own mechanisms and were left as named
  follow-ups rather than fixed): **M-6** — the H1/H2 fixes below, and the SPEC F7 "configured" →
  "fixed" wording correction, were sitting uncommitted, untested (no case covered the H2 keyboard
  path) and unrecorded; committed this session, `TestAddControlClickToPlace` gained
  `test_enter_key_places_at_view_center_and_returns_to_idle`. **M-7** —
  `test_ogps_6802_named_controls` pinned control 72's read as `assert control_72.number is None`;
  the surrounding comment's own intent is "not a wrong guess", not "must stay unread forever", so a
  future OCR improvement correctly reading 72 would have read as a regression — loosened to
  `in (None, 72)`.

  **Six Low:** three fixed as trivial prose/markup corrections — `docs/TASKS.md`'s T102 entry said
  `_keep_largest_ink_cluster` keeps the "tightest" group, the code and its own docstring say
  "largest"; `test_segment.py`'s 341px-fragment citation pointed at `docs/DECISIONS.md` ADR-033,
  which contains no such measurement (it's in T101's own `docs/TASKS.md` entry) — repointed;
  `#add-control-btn` gains `aria-pressed="false"` in `index.html`'s markup, matching its two sibling
  toggles (`#toggle-add-mode-btn`, `#calib-start-btn`) instead of relying on `setMode`'s runtime
  call alone. Three left as documented, non-blocking notes: `docs/CONVENTIONS.md`, which `CLAUDE.md`
  names as required subagent context, does not exist under `docs/` — pre-existing, not an M13
  regression, but affects every subagent briefed on this project; `_ocr_gate_tied_scales` runs one
  full OCR pass per tied multiplier, unbounded by tie count (harmless at the corpus's own tie sizes,
  no NFR budget covers detection); `_INTERIOR_INK_MAX=0.3`'s area-based margin could in principle be
  cleared by two ~4px crossing lines at the base scale's own radius — a margin note, not a
  reproduced defect (`grid-lines-red-controls`'s own F7 floor stayed green).

  **H1 and H2 (found already fixed, uncommitted, in the working tree at the start of this review —
  from an earlier review pass whose own session ran out of budget before it could commit or write
  up docs, same interrupted-session pattern as T103/T106's own backfills) were independently
  re-verified correct and sufficient, not just trusted:** **H1** —
  `#add-control-btn[aria-pressed="true"]` had no explicit `color`, so the shared
  `button[aria-pressed="true"]` rule's white `--accent-contrast` still applied over the pale warning
  background (measured ~1.1:1 light, ~1.4:1 dark, against WCAG's 4.5:1 text-contrast floor); fixed
  with `color: var(--text)` (measured ~16.1:1 light, ~10.2:1 dark). **H2** — `add-once` had no
  `Enter`-key path while `add`/`calibrate` both already did, and the arming handler focuses the
  viewport (the default keyboard path), so a keyboard-only user's path dead-ended; fixed by
  mirroring the pointer path's own `addControlAt` + `setMode("idle")`.

  Full account, including exact contrast numbers and file:line citations: `docs/DECISIONS.md`
  ADR-033's own review amendment. Re-verified after every fix: **522 passed** (520 + this task's
  own test + `TestToggleAddModeArmedState`), `ruff check .` clean, this session's own run.

## M14 — Real-map terrain/routing correctness on `ogps-8620` (Iteration I7, `docs/iterations/I7-real-map-routing-correctness-and-ocr-vlm-fallback.md`)

> T108 before T109 before T110 (all three touch `vision/palette.py`'s classification output —
> T108's diagnosis must land before T109's region-closure fix is designed, and T109's fix must land
> before T110 decides whether the lake crossing shares its mechanism, per ADR-038). T109 is a
> **shared primitive** (`classify_palette`'s output feeds control detection's ink masks,
> `vision/linear.py`, and `cost/field.py`) — it lands serially, full suite re-run before T110/T112
> start. T111 before T112 (`vision/linear.py`'s own diagnosis-then-fix pair, ADR-038) — independent
> of T108-T110's file. The `veg_fight` config task is independent of everything else in this
> milestone (different file, no shared symbol) and may run any time.

- [x] **T108** — Diagnose real-scan out-of-bounds region-interior leak — paths: none (read-only
  diagnosis script under `data/maps/`, gitignored per ADR-010) — deps: none — DoD: measure, on
  `data/maps/ogps-8620_502cda4f6c774e8ecb86d063a71895f6`, the reported magenta ISOM 709 polygon's
  hatch ink density and the per-pixel classification breakdown of its interior (what fraction lands
  `out_of_bounds` vs. `white`/`unknown`/`forest_runnable`/other); confirm or refute
  `vision/palette.py:39-54`'s own documented hypothesis (per-pixel classification has no notion of
  "enclosed"); findings and a concrete fix design for T109 written into this task's own entry before
  T109 starts (ADR-038).
  **Diagnosed — confirms `palette.py:39-54`'s hypothesis, and sharpens it.** This map carries three
  real `out_of_bounds` polygons of different sizes (not one polygon plus purple control circles as
  first assumed — this map's own control circles print in red); measured on the largest (bbox
  387x468 px at (2179,1504); interior 89,054 px after closing the hatch mask and filling its
  contour). Raw `classify_labels` hatch-ink density inside the interior is 56.75% (50,537/89,054
  px); the rest is 25.09% `unknown`, 15.23% `forest_runnable`, and <2% each of
  `road`/`bare_rock`/`paved_area`/other — exactly "whatever colour prints in the gaps," not a bug in
  the nearest-shade math. `fill_unknown`'s own radius-3 majority vote already closes most of the
  `unknown` slice as a side effect (56.75% → 81.06% `out_of_bounds` after the full `classify_palette`
  pipeline: narrow hatch gaps fail the CIELAB threshold and get voted into their oob-majority
  neighbourhood) — but it cannot touch the 15.94% that lands a *confident* nearest-shade match on
  `forest_runnable` (wider gaps where the true white background wins outright); that residual is the
  actual leak. `cost/graph.py::_aggregate_blocks`'s any-passable-pixel rule then amplifies it
  sharply: at `downsample=4`, 84.26% of the 5,737 graph blocks overlapping this interior (4,834 of
  them) come out block-passable — the cost graph treats the large majority of a polygon that is 81%
  correctly pixel-classified as freely traversable, which is why a solved route crossed it.
  **Fix design for T109**: add a region-closure step to `classify_palette`, run on
  `classify_labels`'s raw output *before* `_consolidate_banked_water`/`fill_unknown` (so
  `fill_unknown` becomes a no-op inside an already-closed region instead of doing partial,
  order-sensitive work). Mirror `_consolidate_banked_water`'s proven shape (T101): for the
  `out_of_bounds` label, `cv2.morphologyEx(MORPH_CLOSE)` the raw hatch mask with a kernel sized to
  the hatch's own line pitch (kernel=25px closed this map's hatch cleanly at 265.991 dpi — T109
  should derive this from `meta.toml`'s dpi/scale rather than hardcode one map's pixel count), take
  each closed component's external contour, fill it, and promote every pixel inside the fill to
  `out_of_bounds` — but only if that filled interior's own raw hatch-ink density clears a safety
  threshold, the same "don't swallow unrelated terrain" role `min_bank_fraction` plays in T101's
  function. Calibration point from this map: the three real polygons measured 36-57% density, while
  one small unrelated purple symbol (a start-triangle fragment, same `purple_100` ink) measured only
  15% — a ~25% threshold cleanly separates them here, though T109 should confirm the gap holds
  against more of the corpus, especially a map with genuine purple control circles
  (`config/default.toml`'s own note that `out_of_bounds` and control circles share ink), which this
  map happens not to have. **Risk flagged for T109**: because `fill_unknown` already masks part of
  the defect (57%→81% oob from the existing radius-3 vote alone), an eyeballed spot-check of the
  labelled output can look "mostly fixed" while the graph still leaks 84% block-passable through the
  remaining 16-19% pixel-level hole; T109's acceptance check must measure interior composition the
  way this diagnosis did, not eyeball the label map. Script: `data/maps/_t108_diagnose_oob.py`
  (gitignored, not committed).
- [x] **T109** — Close hatched-polygon interiors for out-of-bounds classification — paths:
  `src/rogaine/vision/palette.py`, `tests/unit/vision/test_segment.py` — deps: T108 — DoD: per
  T108's design, a region-closure step in `classify_palette` makes the whole enclosed
  `out_of_bounds` polygon interior classify consistently (ADR-036); `rogaine plan`/`detect` on
  `ogps-8620` no longer routes through the reported polygon; every existing synthetic-fixture IoU
  floor unchanged; a new real-scan test pins a probe point deep inside the polygon as
  `out_of_bounds`/impassable, skipped when the gitignored scan is absent; full suite green before
  T110/T112 start (shared-primitive ordering, ADR-036).
  **Landed.** `_close_out_of_bounds_regions` (`vision/palette.py`) wired into `classify_palette`
  ahead of `_consolidate_banked_water`/`fill_unknown`, per T108's design: close the raw hatch mask
  with a `hatch_close_mm`-derived kernel, fill each closed component's external contour, promote to
  `out_of_bounds` only past two density guards (`min_density_fraction=0.25`,
  `min_closed_fraction=0.70`). Verified against all three of `ogps-8620`'s real polygons, not just
  T108's own largest measurement target: component densities 48.25%/36.21%/56.75%, all three close
  to a fully `out_of_bounds` 10x10 probe box at each polygon's own deepest interior point
  (`data/maps/_t109_verify_all_polygons.py`, gitignored). The unrelated purple start-triangle
  fragment T108 flagged (density 15.35%) correctly stays unclosed (8/100px in the same probe size,
  not force-filled) — the false-positive guard holds. Two new real-scan tests added to
  `TestOutOfBoundsClosureOnRealScan` in `test_segment.py` pinning the second/third polygon and the
  false-positive case, alongside the two pre-existing tests for the largest polygon (pixel probe +
  routing-graph block-passability). 26/26 `test_segment.py` real-scan tests pass.

  **Second finding, caught by the full suite this session (not by the killed prior session, which
  never ran it to completion): a real regression on the synthetic fixture's own IoU floor.**
  `test_palette.py::TestPaletteIoUAgainstFixture::test_area_classes_on_the_clean_render` failed
  post-fix: `open_land` IoU dropped to 0.9020 (floor 0.95). Diagnosed
  (`data/maps/_t109_diagnose_fixture_regression.py`, deleted after use) to one specific cause: the
  fixture's course-overprint controls share `purple_100` ink with `out_of_bounds` (same real-world
  ambiguity `config/default.toml` already documents), and one control on this fixture's seeded
  layout (`seed=20260819`) happens to land close enough to the fixture's own out-of-bounds blob (a
  few px of raw-ink gap) that the closing kernel bridges the two into one component. The merged
  "dumbbell" measured density 0.319 / closed_fraction 0.847 — statistically indistinguishable from
  a genuine large polygon (`ogps-8620`'s own largest measured 0.567/1.0) — so neither existing guard
  can reject it; T108's own diagnosis had flagged exactly this untested edge case (`ogps-8620`'s
  controls print red, never exercising the purple-shared-ink collision against a real polygon).

  Tried and rejected: switching the fill mechanism from "trace external contour, fill solid" to
  proper topological hole-filling (`scipy.ndimage.binary_fill_holes`) — measured no improvement
  (`data/maps/_t109_test_fillholes_fix.py`, deleted after use): the contamination comes from
  `cv2.MORPH_CLOSE`'s own dilate-then-erode smoothing the boundary where the two ink sources are
  close, not from the subsequent fill step, so changing the fill step alone doesn't help.

  **Fix: a third guard, `min_solidity_fraction=0.70`** (`filled_area / convex_hull_area` of the same
  contour). Bridging two separate ink blobs across a gap leaves a concave waist between them that a
  single chunky polygon's own irregular-but-continuous boundary does not — measured
  (`data/maps/_t109_test_solidity_guard.py`, deleted after use) on `ogps-8620`: the three real
  polygons solidity 0.786-0.893, the rejected purple fragment 0.904 (already excluded on density);
  the bridged fixture false positive 0.598. `0.70` sits with comfortable margin on every side.
  Re-verified after the fix: `test_palette.py` 31/31 pass (IoU floors restored), `test_segment.py`
  26/26 pass (all three real polygons still close correctly, solidity guard does not reject them),
  full suite **537 passed** (522 baseline + 4 new closure tests + T113's 11), `ruff check .` clean
  — this session's own run, not trusted from any intermediate measurement alone.
- [x] **T110** — Fix lake crossing on `ogps-8620`, and reclassify `veg_fight` impassable — paths:
  `src/rogaine/vision/palette.py` (lake fix, if T108/T109 don't already cover it), `config/
  default.toml` (`veg_fight.passable`), `tests/unit/cost/test_field.py`/`test_graph.py`,
  `tests/unit/vision/test_segment.py` — deps: T109 (lake half only; the `veg_fight` half is
  independent and may land first) — DoD: **lake half** — measure whether the reported lake crossing
  shares T109's region-closure mechanism or needs `_consolidate_banked_water`'s own distinct
  treatment (T101 precedent); fix accordingly; `ogps-6802`'s own `TestBankedWaterConsolidationOnRealScan`
  (T101) unchanged; a new gitignored real-scan check confirms the lake's deepest interior point is
  impassable in the graph. **`veg_fight` half** — `config/default.toml`'s `veg_fight` entry's
  `passable` flips `true` -> `false` (ADR-037, owner ruling, not measurement); a `veg_fight`-labelled
  block is excluded from the graph like `out_of_bounds`/`water_uncrossable`, on every map, not only
  `ogps-8620`; any existing test asserting the old passable behaviour is updated to match, named in
  this task's own entry as an intended consequence, not a silent fix.

  **Lake half diagnosed and fixed — shares `_consolidate_banked_water`'s territory (T101), not
  `_close_out_of_bounds_regions`'s (T109).** Diagnosis (`data/maps/_t110_diagnose_lake.py`,
  gitignored, deleted after use) found the reported lake is a single solid raw connected component
  (213,675 px, bbox 923x924 at (1511,451), `wu_frac` only 0.5%) — unlike `ogps-6802`'s river it is
  not fragmented into thousands of tiny `water_uncrossable` islands; its interior already classifies
  almost entirely `water_shallow` outright and just needs whole-blob promotion. Its own boundary is
  genuinely bank-lined: measured boundary-bank fraction 0.2611 at `_consolidate_banked_water`'s
  original `border_radius=2` (`palette.py:294-414`), just under the original `min_bank_fraction=0.3`
  floor.

  Tried and rejected: widening `border_radius` instead of lowering the fraction floor (0.3009 at
  radius=4, 0.3665 at radius=8, a comfortable +22% margin on the lake alone) — measured to have
  collateral damage on a *third*, unrelated real scan outside this task's own scope:
  `data/maps/grid-lines-red-controls` (I1) carries 4 real, compact water bodies (9,191-116,505 px,
  aspect ratio 1.03-1.80 — genuine blobs, not that map's own grid-line ink) whose boundary-bank
  fraction (0.083-0.199 at radius=2) also crosses radius=8's widened search window, nearly doubling
  that map's routable-graph component count (9,685 vs the pinned 580) and breaking
  `TestGridInkOnRealScan::test_routable_graph_is_far_less_fragmented`'s own `< pre_n/5` floor
  (`data/maps/_t110_diagnose_grid_water.py`/`_t110_inspect_newly_promoted.py`, both gitignored,
  deleted after use).

  **Fix:** lowered `min_bank_fraction` to 0.23, `border_radius` left at its original 2 (so it can
  never newly discover ink a wider spatial search would have found) — confirmed safe by
  re-measuring the same 4 grid-lines-red-controls components at the unchanged radius: 0.083, 0.105,
  0.177, 0.199, all comfortably below the lake's 0.2611 (`_t110_check_threshold_alt.py`, gitignored,
  deleted after use); 0.23 sits near the middle of that 0.199-0.2611 gap, margin on both sides. A
  threshold low enough to clear the lake risked separately sweeping in `ogps-6802`'s own marsh —
  unlike the lake or the 12,252 px river, the marsh's raw water ink is itself sparsely fragmented
  (744 distinct raw components in the probed bbox alone, largest just 174 px,
  `_t110_marsh_component_sizes.py`, gitignored, deleted after use), and a handful-of-pixels
  component's boundary-bank fraction is statistically unreliable. Added `min_component_area_px=500`
  (comfortably above the marsh's 174 px, comfortably below the river's 12,252 px and the lake's
  213,675 px — same precedent as `[linear]`'s own raw-px noise floor, `config/default.toml`) to gate
  promotion by component size.

  Final combination (`_consolidate_banked_water`, `palette.py:294-414`: `border_radius=2`
  unchanged, `min_bank_fraction=0.23`, `min_component_area_px=500`) verified end to end against all
  four real scans this function touches (`_t110_final_verify_all.py`, gitignored, deleted after
  use): lake probe 100/100 `water_uncrossable`, `ogps-6802` river probe 100/100 unchanged (T101
  untouched), `ogps-6802` marsh ratio 19.44 (better than the pre-T110 baseline 14.12,
  `TestBankedWaterConsolidationOnRealScan`'s own `> 10` floor unmoved), grid-lines-red-controls
  fragmentation ratio 0.0614 (within rounding of its own pre-T110 baseline). New gitignored
  real-scan check kept per this task's own DoD (T109's cleanup precedent — confirming script stays,
  diagnosis scripts don't): `data/maps/_t110_verify_lake.py` confirms `GridGraph.block_passable` is
  `False` at the lake's deepest interior point (1749, 1231, block (307,437) at `downsample=4`). Two
  new pytest cases, `TestLakeConsolidationOnRealScan` in `test_segment.py` (pixel probe +
  routing-graph block-passability, same two-test shape as T109's own polygon coverage).

  **`veg_fight` half landed.** `config/default.toml`'s `veg_fight` entry flips `passable` `true` ->
  `false` (ADR-037, owner ruling). `TerrainSpec`'s own validator (`config.py:137-138`: "impassable
  terrain must have speed_factor 0") forced `speed_factor` to also drop from 0.05 to 0.0 — not an
  independent choice but a consequence of giving `veg_fight` the same treatment already given
  `out_of_bounds`/`water_uncrossable`; without it `load_config()` raises at import time and the
  whole suite fails to collect. Confirmed `cost/graph.py`'s mechanism needs no code change, by
  reading rather than assuming: `compute_cost_field` (`cost/field.py:56`) reads
  `cfg.passability()[labels]` straight from config; `build_grid_graph`/`_aggregate_blocks`
  (`cost/graph.py:133`, `cost/graph.py:214`) already exclude any block with no passable pixel under
  `strict_impassable` — the same path `out_of_bounds`/`water_uncrossable` already use.

  Two existing tests asserted the old passable/nonzero-speed behaviour and are updated as an
  intended consequence of ADR-037, not a silent fix: `tests/unit/test_config.py::TestDefaultConfig
  ::test_impassable_terrain_has_no_speed` now includes `VEG_FIGHT` in its impassable-classes tuple
  (previously only `WATER_UNCROSSABLE`/`OUT_OF_BOUNDS`); `test_vegetation_ordering_follows_isom_
  runnability` no longer asserts `fight > 0.0` as part of the strict speed ordering (ISOM 410 is no
  longer a graded-speed class) and instead asserts `not fight.passable and fight.speed_factor ==
  0.0` separately. No other existing test asserted `veg_fight` traversability: `tests/unit/cost/
  test_field.py`/`test_graph.py` derive expected passability from config itself rather than a
  hardcoded per-class list, so neither needed a change.

  Full suite **539 passed** (537 baseline [T109/T113] + 2 new `TestLakeConsolidationOnRealScan`
  cases), `ruff check .` clean — this session's own foreground `docker compose run --rm tests`/
  `ruff check .` runs, not trusted from any intermediate measurement alone.
- [x] **T111** — Diagnose ЛЭП (power line) ink vs. footpath ink on `ogps-8620` — paths: none
  (read-only diagnosis script, gitignored) — deps: none — DoD: measure this map's actual power-line
  symbol's ink pattern (dash/gap spacing, width, any tick/cross marks) against a genuine footpath's
  on the same map; determine whether `vision/linear.py`'s pure width-bucketing
  (`linear.py:174-175`) can be safely extended with a distinguishing signal, or whether none exists
  safely this round (T098 precedent — a valid, documented close); findings feed T112 (ADR-038).

  **Closed, no safe fix found this round — a candidate signal was measured and shown unsafe.** The
  ЛЭП at control 72 ("опора ЛЭП") is drawn as two parallel hairline strokes (~1px each, ~1-2px gap)
  with short perpendicular pylon ticks every ~172-177px (~16.7mm paper, ~400m real-world) —
  confirmed directly in the palette classifier's own raw `road`-placeholder mask, not just by eye on
  the JPEG. `close_radius_px=2` (meant to bridge dash-gaps in genuine footpaths/tracks) also bridges
  the ЛЭП's inter-hairline gap, merging both hairlines into one component whose median stroke width
  (3.39px) lands nearest `vehicle_track`'s nominal width (3.665px @ this map's 265.991dpi) — not
  because it is 3.4px of real ink, but because roughly half of that merged component's own footprint
  is blank paper closed shut. A genuine dotted footpath measured for contrast (component 1461:
  single stroke, ~1.8px median width, dot/gap runs ~2px/<1px) has no such structure. The natural
  signal this suggests — "ink fill ratio" (fraction of a closed component's own footprint that is
  real ink) — was measured across all 86 shape-filter-passing components on this map: the ЛЭП scores
  0.525, but several components already bucketed as genuine footpath/road/vehicle_track score as low
  or lower (0.366, 0.577, 0.644, 0.654, 0.697, 0.707, 0.713, 0.719, 0.764) — a threshold on fill
  ratio would misclassify real corridors elsewhere on this same map. Same precedent as T080/T098: a
  plausible-sounding signal was measured, not just designed, and shown unsafe before being built into
  `linear.py`. The double-hairline structure itself is real and visually unique to this ЛЭП among
  everything sampled here, but a safe detector for it needs a genuine two-band cross-sectional shape
  test (bimodal ink profile perpendicular to the skeleton, sustained along the component's length),
  not a width or fill-ratio number — not built or corpus-validated this round. T112 should close as
  a documented gap unless someone scopes building and validating that specific shape test across the
  full map corpus (the diagnosis script, gitignored at `data/maps/_t111_diagnose_lep.py`, has the
  measurement code and raw candidate numbers for that follow-up to start from).
- [x] **T112** — Fix ЛЭП costing, if T111 found a safe signal — paths:
  `src/rogaine/vision/linear.py`, `tests/unit/vision/test_linear.py`, possibly `config/default.toml`
  (`[linear]`) — deps: T111 — DoD: per T111's finding, either (a) ЛЭП-identified ink on `ogps-8620`
  no longer receives `footpath`/`vehicle_track`/`road`'s speed and T095 proximity-bonus treatment,
  with existing width-bucketing behaviour for genuine roads/tracks/footpaths unchanged and a new
  real-scan test pinning it (gitignored scan, skipped when absent); or (b) T111 found no safe
  distinguishing signal, task closes with no code change, the measured reason recorded in this
  task's own entry (T098 precedent) rather than a guessed fix landing.

  **Closed with no code change (T111 path b) — no safe distinguishing signal exists this round.**
  T111 measured the ЛЭП's double-hairline structure and the one candidate signal it suggested
  ("ink fill ratio" within a closed component's own footprint) against all 86 shape-filter-passing
  linear components on `ogps-8620`: the ЛЭП scores 0.525, but several components already correctly
  bucketed as genuine footpath/road/vehicle_track score as low or lower (0.366-0.764) — a threshold
  on it would misclassify real corridors on the very same map, same T080/T098 precedent (measure
  before building, not after). No other signal in `vision/linear.py`'s existing feature set (width,
  elongation, aspect ratio) separates the two either. A safe detector is plausible in principle — a
  genuine two-band cross-sectional shape test (bimodal ink profile perpendicular to the skeleton,
  sustained along the component's length) — but building and corpus-validating that test is real,
  unscoped work, not a small extension of the existing width-bucketing, and is not done this round.
  `vision/linear.py` is unchanged; `ogps-8620`'s ЛЭП stays a documented, named gap (SPEC F5's own
  acceptance line already states this as a valid outcome). Follow-up starting point if picked up
  later: T111's own diagnosis script, `data/maps/_t111_diagnose_lep.py` (gitignored), has the
  measurement code and raw per-component numbers.

## M15 — Opt-in VLM OCR fallback for control numbers (Iteration I7, `docs/iterations/I7-real-map-routing-correctness-and-ocr-vlm-fallback.md`)

> T113 before T114 before T115, strictly serial (module, then wiring, then measurement). Independent
> of every M14 task (disjoint files) — may run in parallel with M14 or after it; the owner's own
> choice to split into two milestones was partly so M14 could close without waiting on M15.

- [x] **T113** — VLM OCR client module — paths: `src/rogaine/vision/ocr_vlm.py` (new),
  `pyproject.toml` (new optional dependency group for the VLM client SDK, not the base install),
  `tests/unit/vision/test_ocr_vlm.py` (new) — deps: none — DoD: a client wrapper that takes a
  control's cropped ink region and returns a structured (digit string, confidence) result or a
  typed "no answer" outcome; reads its API key from an environment variable, never from
  `config/default.toml` or any committed file; unit tests exercise the module entirely against a
  fake/mocked client — no real network call anywhere in the test suite (ADR-010/ADR-039); base
  `pip install`/`docker compose run --rm tests` makes zero new network-capable code reachable
  (optional dependency group).
  **Landed.** `read_control_number(image_bytes, *, model=DEFAULT_MODEL, client=None)` forces tool
  use with a strict schema (`digit_string`, `confidence`); no `ANTHROPIC_API_KEY` (or an empty one)
  returns `VlmOcrResult.no_answer()` before ever constructing `anthropic.Anthropic()`; every client
  failure (rate limit, connection, other API status, malformed tool response) degrades to the same
  typed no-answer outcome via a most-specific-first exception chain, never raises. `anthropic` is
  imported in a `try`/`except ImportError` so the module and its test file both collect cleanly
  whether or not the optional `ocr_vlm` extra (`anthropic>=1.0`, `pyproject.toml`) is installed.
  `DEFAULT_MODEL = "claude-haiku-4-5"` confirmed current (no date suffix) against the live model
  table this session, cost/latency tier matches this task's own niche (1-3 printed digits from a
  small crop). The 3 test failures noted at pause never reproduced this session — 11/11
  `test_ocr_vlm.py` pass cleanly in the container, all mocked end to end, no real network call.
  `ruff check .` clean, full suite **537 passed** (see T109's own entry for the combined count).
- [x] **T114** — Wire the fallback into the OCR pipeline; amend SPEC/NFR — paths:
  `src/rogaine/vision/ocr.py` or `vision/controls.py` (trigger condition only), `config/
  default.toml` (new `[ocr_fallback]` section: `enabled`, `trigger_confidence`, model id), `tests/
  unit/vision/test_ocr.py` — deps: T113 — DoD: `[ocr_fallback].enabled=false` (shipped default)
  leaves F8's existing behaviour byte-for-byte unchanged, and the full existing suite (every test
  implicitly uses this default) stays green with zero new network calls; with `enabled=true` and a
  mocked client, a control whose Tesseract read is empty or below `trigger_confidence` is retried
  through the fallback and, on success, marked distinctly from a Tesseract-sourced read (F23); a
  missing API key or a client error with the fallback enabled degrades to F8's existing
  null-flagged behaviour, never a crash, never blocking a route; `docs/SPEC.md`'s Summary/
  Integrations/Non-goals/NFR-Security/F8/Risks#4 lines amended per this iteration's doc (ADR-039).

  **Landed.** `docs/SPEC.md`'s amendment was already in place from I7's own delta-intake commit
  (`d57ea35`, before implementation started) — verified, not re-touched. New `[ocr_fallback]`
  section in `config/default.toml` (`enabled=false` shipped, `trigger_confidence=0.6`,
  `model="claude-haiku-4-5"`) backed by a new `OcrFallbackSettings` (`config.py`), required on
  `AppConfig` the same way every other settings block is. `Control` gained `number_source:
  Literal["tesseract","vlm"] | None` (`models.py`) — distinct from the existing `source` field,
  which is about *position* detection provenance, not number-reading provenance — and it round-trips
  through `io/controls_csv.py`'s ninth column (blank on a hand-typed number, matching the existing
  ergonomic-defaulting convention for `confidence`/`source`).

  `vision/ocr.py::read_control_number` calls `ocr_vlm.read_control_number` (T113, unmodified) once
  per control, gated purely on `[ocr_fallback].enabled and (not digits or ocr_confidence <
  trigger_confidence)` — deliberately independent of `[detector].min_ocr_confidence`, so a caller
  can set `trigger_confidence` above `min_ocr_confidence` to also double-check a Tesseract read that
  already cleared its own floor, per ADR-039's literal text ("triggers only when Tesseract's own
  read... is empty or below trigger_confidence", no mention of `min_ocr_confidence` as a
  prerequisite). **Review caught a real bug in the first-pass wiring**: it additionally required
  `flag is not None` (Tesseract's own accept/reject verdict) before checking `trigger_confidence` at
  all, which silently no-ops the fallback exactly when an operator configures `trigger_confidence >
  min_ocr_confidence` — the one case that setting exists to enable. Fixed by dropping that extra
  condition; a new regression test
  (`TestVlmFallback::test_trigger_confidence_above_min_ocr_confidence_still_retries_an_accepted_read`)
  pins a Tesseract read that clears `min_ocr_confidence` (so Tesseract's own logic sets `number` and
  leaves `flag=None`) but sits below a higher `trigger_confidence`, and confirms the fallback still
  fires and overwrites the result.

  On a successful fallback read: `number`/`points` overwritten, `number_source="vlm"`, `flag`
  rewritten to name the VLM-sourced read (never left claiming "no digits found" on a control that
  was, in fact, read). On `NO_ANSWER` (disabled, no key, network error, genuinely unreadable):
  falls through to F8's original null-flagged behaviour unchanged. `_try_vlm_fallback` wraps
  `int(digit_string)` defensively (untrusted network-response content) even though
  `ocr_vlm.read_control_number` itself never raises — one bad control must not take down a batch.

  Six new tests, `TestVlmFallback` in `test_ocr.py`, all injecting a mocked `ocr_vlm.read_control_number`
  (never a real client/network call): disabled-by-default (spy unreachable), empty-read fallback
  success, low-confidence-read fallback success, `NO_ANSWER` falls through safely, already-above-
  `trigger_confidence` never invokes the fallback, and the `trigger_confidence`-independence
  regression above. Every pre-existing test in the file is untouched — the gating is additive by
  construction. Full suite **545 passed** (539 + 6 new), `ruff check .` clean — this session's own
  foreground run, not trusted from an intermediate/backgrounded one (a first attempt at this task
  backgrounded its own verification run and had to be stopped and re-verified directly).
- [ ] **T116** — Local Ollama backend for the OCR VLM fallback, amending ADR-039 — paths:
  `src/rogaine/vision/ocr_vlm_ollama.py` (new), `src/rogaine/vision/ocr.py` (`_try_vlm_fallback`
  dispatches on `cfg.ocr_fallback.provider`), `src/rogaine/config.py` (`OcrFallbackSettings` gains
  `provider: Literal["anthropic", "ollama"]` and `base_url: str`), `config/default.toml`
  (`[ocr_fallback]` gains `provider = "anthropic"` and `base_url = "http://localhost:11434"` —
  shipped `provider` stays `"anthropic"`, so no existing behaviour changes), `pyproject.toml` (new
  optional dependency group `ocr_vlm_ollama`, not the base install), `tests/unit/vision/
  test_ocr_vlm_ollama.py` (new) — deps: T114 — DoD: same typed `VlmOcrResult`/`Outcome` contract as
  T113's Anthropic client (imported from `ocr_vlm.py`, not duplicated); a local Ollama server that
  is unreachable, errors, or returns a malformed response degrades to `VlmOcrResult.no_answer()`,
  same as T113's contract, never raises; unit tests exercise the module entirely against a fake/
  mocked client, no real network/Ollama call anywhere in the default suite (ADR-010); base `pip
  install`/`docker compose run --rm tests` makes zero new network-capable code reachable (optional
  dependency group, same inertness guarantee as T113); every pre-existing `test_ocr.py` fallback
  test stays green unmodified (`provider="anthropic"` shipped default is byte-for-byte what those
  tests already exercise).
- [ ] **T115** — Measure the fallback on real scans — paths: none (measurement script under
  `data/maps/`, gitignored) — deps: T114, T116 — DoD: with the fallback enabled against either
  backend (a real `ANTHROPIC_API_KEY`, or a local Ollama server per T116 — owner's choice,
  2026-09-16: use Ollama, `qwen2.5vl:7b` already installed), run against
  `ogps-8620_502cda4f6c774e8ecb86d063a71895f6` and confirm every one of the owner's
  originally-reported unread numbers is either read or still explicitly flagged (never silently
  wrong); run against a broader owner-corpus sample and record the before/after read-rate; record
  the API call count and an estimated cost per map in this task's own entry (Ollama: $0, local
  compute only) — the concrete evidence the iteration's exit criteria and F23's acceptance line are
  judged against.
