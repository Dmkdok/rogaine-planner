# Iteration I6 — Real-map detection gaps and viewer UX (M13, T101-T107)

## Source

Owner report, in-chat 2026-09-13, with one annotated screenshot (a crop from
`data/maps/ogps-6802_4a769f64b455f9b4675552284c3681b1`) plus prose covering three named maps and two
UX complaints. Surfaces while the owner was doing exactly the kind of real-map spot-check ADR-019
established as this project's acceptance gate (same role as T082/T086/T095's owner sign-off, though
this round produced new findings rather than a clean pass). Praise recorded alongside the bugs, not
just the complaints: pathfinding hugging roads reads well, and `ogps-8078`'s circle detection is
correct despite an unusually adversarial two-colour print style.

## In scope

| # | Item | Map / area | Symptom |
|---|------|-----------|---------|
| 1 | River/lake crossing | `ogps-6802_4a769f64b455f9b4675552284c3681b1` | The solved route crosses a river. Ditches are legitimately crossable; lakes/rivers with a black bank line must stay impassable. |
| 2 | Missing OCR reads | same map | Controls 42, 53, 72: circle found precisely, number not read. |
| 3 | Calibration tool active-state UX | viewer (`Начать калибровку`) | No clear affordance that the draw tool is armed; a click meant to pan the map instead places/corrupts a calibration point, with no way to drag while armed. |
| 4 | Forbidden-area symbol misdetected as controls | `ogps-7302_5d8c290224a04f49e2c95484d2fbaf92` | ISOM 709 out-of-bounds symbol produces dozens of spurious control detections; must also block routing through it. |
| 5 | Manual "add control" flow | viewer (`Добавить контроль`) | Drops a pin at the view centre immediately, requires dragging into place. Wants click-to-place like the calibration line, then auto-deactivate. |
| 6 | Two-colour circle/number OCR | `ogps-8078_8295c94963b2c249d6f4d94fd0c35fa1` | Ring ink and number ink are different colours (non-standard print). All circles detected correctly; numbers not read. |
| 7 | Confidence-gated auto-placement | cross-cutting, all maps | When detection confidence is low, skip auto-placing the candidate rather than risk a false control — owner completes it manually instead. |

**Explicitly out of scope, owner's own words:** map 1 (`ogps-6802`) carries an unrelated, pre-existing
annotation artifact — someone overlaid a circled path on top of one trail — the owner says to ignore
it; it is not a detection defect and no task in this milestone touches it.

## Budget and non-negotiables (gate answers, 2026-09-13)

- **Budget:** all 7 items in one milestone, M13/T101-T107 — confirmed by the owner over the
  alternative (split map-detection vs. UX into two rounds), matching I4 (8 tasks) and I5 (4 tasks)
  already landing whole batches in one round.
- **Item 7's threshold:** the owner chose the conservative option directly — pick a measured,
  cautious confidence floor and ship it, without an intermediate before/after review step (unlike
  T099/T100's precedent, where the owner reviewed a trade-off before choosing). Recorded as ADR-033.
- **Non-negotiable:** none of the existing real-scan regression floors may regress —
  `TestRealScanReadRateFloor` (`tests/unit/vision/test_ocr.py`), `TestGridInkOnRealScan`
  (`tests/unit/vision/test_segment.py`), `TestRealScanRedInk` (`tests/unit/vision/test_controls.py`).
  A floor that must move because a fix legitimately changes counts is a stated, measured change,
  never a silent drop (same rule T099/T100 already established).
- **Non-negotiable:** ditches/crossable watercourses must stay crossable after item 1's fix — the
  fix corrects river/lake misclassification, it must not widen `water_uncrossable` broadly enough to
  catch legitimate thin blue crossable ink too.

## Diagnosis-first items (ADR-026 precedent)

Items 1, 2, 4 and 6 are real-scan detection/classification failures whose exact mechanism is not
yet known — each gets measured against its own named map before a fix is designed, exactly as
T089/T097-T100 did, not a guessed fix verified after the fact. Preliminary code-reading this session
(not yet corpus measurement) narrows each one:

- **Item 1** — `cost/graph.py`'s `strict_impassable=true` (default) already refuses any edge
  touching a `passable=false` block, and `water_uncrossable` (ISOM 301) is already `passable=false`.
  So the river is very likely not being *classified* as `water_uncrossable` on this map, not a
  routing-policy gap — `config/default.toml`'s own long-standing note flags `palette.
  lab_distance_threshold=35.0` as "provisional... if a fixed palette proves brittle [on a real map],
  fit it per map" (`docs/STATUS.md`'s "Two decisions worth keeping in view", never yet triggered).
  T101 measures whether this map's printed blue is outside the configured Lab band before deciding
  between a wider threshold and a per-map fit.
- **Item 2** — likely the same family of real-scan OCR failure already fixed twice this project
  (ADR-023's leftover-ink/ring-erasure modes, ADR-031's sub-1.0 scale gate) — T102 measures which
  known failure mode (or a new one) applies to 42/53/72 specifically before changing anything.
- **Item 4** — `config/default.toml` already carries an `out_of_bounds` (ISOM 709) terrain class
  with a note written in advance for exactly this collision: "printed in purple, same ink as the
  control circles — T020 must not confuse them." `vision/controls.py::detect_controls` builds its
  own `purple_mask` directly from the raster and never consults `classify_palette`'s terrain labels,
  so that anticipated collision was never actually guarded. T103 measures the symbol's actual shape
  on this map (solid fill vs. hatch) to choose between reusing the terrain classification as an
  exclusion mask and a dedicated shape discriminator.
- **Item 6** — `vision/ocr.py::_ocr_crop` masks its OCR crop with the same `purple_mask` (i.e. the
  same `ink_hue_ranges`) used for ring detection, then erases the ring disk and OCRs whatever ink
  remains. If the number is printed in a colour outside `ink_hue_ranges`, it is invisible to the
  crop before OCR ever runs — T104 confirms this against the actual map and designs the narrowest
  broadening (e.g. any sufficiently dark/saturated ink inside the already-erased-ring crop, not a
  second configured hue band) that does not reintroduce contour-line bleed (ADR-023's own past
  failure mode).

## Impact map

| Item | Touches | SPEC: changes / preserves | Existing coverage | Class | Regression proof |
|------|---------|---------------------------|-------------------|-------|------------------|
| 1. River crossing (T101) | `src/rogaine/vision/palette.py` (`classify_palette`), possibly `config/default.toml`'s `[palette]`/`[[terrain]]` tables | Changes F4 (terrain classification accuracy on this real scan); preserves F10 (impassable exclusion — untouched, already correct once classification is correct) | `tests/unit/vision/test_segment.py` (IoU floor on the synthetic fixture); no real-scan water-classification floor exists yet | Shared primitive (palette classifier runs on every map) | New real-scan test: `ogps-6802`'s river pixels classify `water_uncrossable`, a known ditch/crossable-water sample stays `water_shallow`/passable; existing synthetic IoU floors unchanged; `rogaine plan` on this map no longer crosses the river (manual spot-check, owner) |
| 2. Missing OCR 42/53/72 (T102) | `src/rogaine/vision/ocr.py` (`_ocr_crop`/`_strip_thin_ink`/related constants) | Changes F8's real-scan acceptance; preserves F8's fixture recall/precision floor | `TestRealScanReadRateFloor` (`test_ocr.py`) — pattern to extend with an `ogps-6802` floor; `test_ocr.py`'s fixture-level OCR tests | Shared primitive (`_ocr_crop` runs for every control on every map) | New `ogps-6802` read-rate floor test asserting 42/53/72 (or a documented subset) now read; all existing `TestRealScanReadRateFloor` floors re-run and must not drop |
| 3. Calibration tool UX (T106) | `src/rogaine/web/static/app.js` (`initMapViewport`'s `pointerdown` handler, `setMode`, `setCalibrationPoint`), `style.css` (`.mode-calibrate`, `button[aria-pressed]`) | Changes F17's acceptance (armed-tool affordance); preserves F17's existing Playwright full-flow coverage | `tests/e2e/test_viewer.py` (no test currently exercises pan-while-calibrating or the active-state affordance) | Local (viewer-only) | New Playwright case: enter calibrate mode, drag (pointerdown+move+up) without releasing over open space pans instead of placing a point; a plain click still places a point; the button/viewport carry a visibly distinct active state (assert a class/attribute, not colour) |
| 4. Forbidden-symbol exclusion (T103) | `src/rogaine/vision/controls.py` (`detect_controls`, `purple_mask`, `_detect_circles`) — likely also reads `classify_palette`'s `out_of_bounds` labels, a new dependency from `vision/controls.py` on `vision/palette.py` | Changes F7 (control detection must not fire inside `out_of_bounds` ink); preserves F4/F10 (the terrain class itself, already impassable, is untouched) | `tests/unit/vision/test_controls.py` (no existing case with an out-of-bounds symbol near controls) | Shared primitive (control detection runs on every map) | New synthetic test: a purple `out_of_bounds` hatch block plus real control circles — zero candidates inside the block, all real circles still found; `ogps-7302`'s own circle count drops from dozens of false positives to the true count (manual spot-check, owner); routing already excludes `out_of_bounds` once classified — no `cost/` change expected, confirmed not regressed |
| 5. Add-control click-to-place (T107) | `src/rogaine/web/static/app.js` (`add-control-btn`'s click handler, `setMode`, `addControlAt`) | Changes F17's acceptance (add-control flow); preserves the existing `toggle-add-mode-btn` multi-placement flow, untouched | `tests/e2e/test_viewer.py` (covers detect/edit flows; no case for the panel's `add-control-btn` specifically) | Local (viewer-only) | New Playwright case: click "Добавить контроль", click a map point, assert the control lands exactly there (not the view centre) and the tool is idle immediately after (map is draggable) |
| 6. Two-colour OCR (T104) | `src/rogaine/vision/ocr.py` (`_ocr_crop`'s masking step) | Changes F8's real-scan acceptance; preserves F8's fixture floor and ADR-023's contour-bleed fix (`_strip_thin_ink`) | `TestRealScanReadRateFloor`; `test_ocr.py`'s contour-density fixture case (ADR-023's own regression guard) | Shared primitive (same function as item 2/6) | New `ogps-8078` read-rate floor test; ADR-023's own contour-bleed regression test re-run unchanged; all existing `TestRealScanReadRateFloor` floors re-run and must not drop |
| 7. Confidence-gated placement (T105) | `src/rogaine/vision/controls.py` (`_detect_circles`'s final candidate filter, near `_RING_COVERAGE_MIN`) | Changes F7's acceptance (a new "not confident enough to auto-place" outcome, distinct from "detected but flagged unread" which is F8's territory); preserves F7's existing recall/precision floors | `tests/unit/vision/test_controls.py`'s scale-selection tests; all `TestRealScanReadRateFloor`/circle-count floors indirectly depend on the final candidate list | Shared primitive, same function family as item 4 | Corpus-wide before/after circle-count measurement (owner's 14-map corpus + `ogps-*` sample, same method as T099/T100) confirming the conservative floor drops near-zero genuine detections; all existing circle-count floors re-verified, any that must move are a named, measured change, not silent |

## Ordering constraints

- **T103 before T105** — both touch `vision/controls.py`'s candidate list in `_detect_circles`.
  T103 removes a whole class of false candidates (the forbidden-symbol ink); T105's conservative
  confidence floor must be measured against a corpus already clean of that contamination, not
  before it.
- **T102 before T104** — both touch `vision/ocr.py::_ocr_crop`'s masking step. T102 diagnoses and
  fixes the general real-scan OCR miss on `ogps-6802` first (established failure-mode family,
  ADR-023 precedent); T104 then extends whatever masking mechanism T102 leaves in place to also
  admit a second ink colour for the number, rather than the two tasks racing the same function.
- **T106 before T107** — both touch `app.js`'s mode/pointer-handling machinery. T106 fixes the
  shared click-vs-drag distinction and the active-state affordance (used by both `calibrate` and
  `add` modes); T107 then reuses that fixed machinery for the panel's single-shot add-control flow
  instead of duplicating a second pointer-handling path.
- **T101 is independent** of every other task (own file, `vision/palette.py`) — parallel-safe.
- **T105 (confidence floor) should land after T102/T104** (informally) since a real OCR fix changes
  which candidates are worth keeping even before the confidence question is asked — not a hard
  file-level dependency, but sequencing them in task-number order avoids re-measuring T105's floor
  twice.

## Tests whose expectations change

None identified. Every item above either adds new coverage (new real-scan floors, new synthetic
cases, new Playwright cases) or removes false positives that no existing test currently pins as
correct (item 4's forbidden-symbol false detections are not asserted as correct anywhere; item 7's
suppressed low-confidence candidates are, by definition, ones no existing floor test currently
requires). If a task's own measurement finds an existing assertion must change, it is reported at
that point, not assumed here.

## Exit criteria

- T101-T107 each landed with the evidence named in its own impact-map row, or closed with measured
  evidence if a designed approach turns out unsafe (T098's precedent).
- All pre-existing regression floors (`TestRealScanReadRateFloor`, `TestGridInkOnRealScan`,
  `TestRealScanRedInk`, every synthetic-fixture IoU/recall/precision floor) still pass at their
  current values or better.
- `docker compose run --rm tests` green, `ruff check .` clean, this session's own run.
- Owner spot-checks the three named maps (`ogps-6802`, `ogps-7302`, `ogps-8078`) and the two UX
  flows post-fix (ADR-019 precedent — this milestone's own acceptance gate, same role as T082/T086).
