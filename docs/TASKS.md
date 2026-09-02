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
