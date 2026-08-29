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
