# Iteration I1 — Real-scan vision robustness (control ink colour, grid-line misclassification)

- **Source:** owner's manual testing of the web viewer on a real scan, this session (2026-09-02).
  Two defects found and confirmed against `data/maps/grid-lines-red-controls/` (gitignored per
  ADR-010; `meta.toml` there records the fixture's own provenance and caveats).
- **Opened:** 2026-09-02
- **Milestone:** `M8` in `docs/TASKS.md`
- **Baseline:** `docker compose run --rm tests pytest -q` — 372 passed, exit 0, at 2026-09-02,
  branch `iteration/I1-real-scan-vision` cut from `master` at commit `c2f2e1e`.

## In scope

| Item | Why now |
|------|---------|
| Control/hub detector (`vision/controls.py`) only matches a fixed ISOM purple hue band | Confirmed on the real scan: 13 clearly visible red-circled numbered controls, `detect_controls` returns zero controls and no hub |
| Terrain segmenter (`vision/segment.py`) reads the map's grid/magnetic-north lines as `water_uncrossable` | Confirmed on the real scan: 5 full-height vertical columns >30% `water_uncrossable`; a hub/control pair straddling one got `no reachable route`, unrelated to the time limit |
| `render/overlay.py`'s route colour is hardcoded red, chosen because *no ISOM ink is red* | Direct consequence of the first item: once red is a recognised control ink, the route line and a real control marking on a red-ink map become visually indistinguishable — the invariant the module's own docstring states breaks |

## Out of scope this round

| Item | Reason | Recorded as |
|------|--------|-------------|
| Fully adaptive / arbitrary ink-colour detection (auto-discover "the ink colour" per map, any hue) | No real corpus to tune or validate it against yet — M7's data blocker (14 raw scans, none with `meta.toml`) applies here too; a threshold picked against one sample map is a guess, not a measurement | ADR-011 |
| Full segmentation validation against the M7 real corpus (T017) | Same data blocker; already tracked in `docs/STATUS.md`'s "Blocked on the owner" | ADR-012 (references the existing T017 blocker, does not reopen it) |
| A web-viewer UI for choosing/uploading a config override | Not needed this round — the fix ships in `config/default.toml`'s shipped defaults, reachable from every caller (CLI and web) without a new setting | — (design result of Phase 2, see impact map) |

## Acceptance

- Control ink: `rogaine detect --map data/maps/grid-lines-red-controls/map.jpeg` finds the map's
  red-circled controls (shape-filtered, not "any red pixel") without regressing the synthetic
  fixture's F7 floor (recall ≥ 0.95, precision ≥ 0.90).
- Grid lines: `rogaine segment --map data/maps/grid-lines-red-controls/map.jpeg` no longer reports
  the grid-line columns as `water_uncrossable`; a route between controls straddling one of them is
  no longer rejected as unreachable, without regressing F4's fixture IoU floors.
- Route rendering stays legible and unambiguous: the route colour is provably distinct (by the same
  kind of measurement `cmyk_to_srgb`'s own tests already use, not eyeballed) from all seven now-
  forbidden inks (six ISOM + red).

## Budget

Bounded to what item 1 and item 2 above need, plus the overlay-colour consequence they force. No
new UI, no new config-override plumbing, no corpus-wide validation.

## Non-negotiables

- Every existing test keeps passing except the one named in "Expectations that change" below.
- The synthetic-fixture floors (F4 IoU, F7 recall/precision/centre-error) do not regress.
- A real water body must still classify as `water_uncrossable` — this is a shape-based carve-out
  for grid/annotation ink, not a weakened colour threshold.

## Impact map

| Item | Touches | SPEC: changes / preserves | Existing coverage | Class | Regression proof |
|------|---------|---------------------------|--------------------|-------|-------------------|
| Control ink colour | `config.py::DetectorSettings` (rename `purple_hue_range: tuple[int,int]` → `ink_hue_ranges: list[tuple[int,int]]`); `config/default.toml`'s `[detector]` table (ships both the existing purple band and a new red band, measured against the real scan, not guessed); `vision/controls.py::purple_mask` (loops the configured ranges, unions the masks) and its two callers `_detect_circles`/`_detect_hub_triangle` (unchanged logic, just fed a wider mask); `vision/ocr.py::read_control_number` (calls the same mask function, benefits with no code change) | Changes F7 (edit in place: drop "purple" as the only ink, keep the fixture acceptance bar, add a real-scan acceptance line); preserves F8/F9 (OCR and CSV round-trip take whatever controls `detect_controls` hands them, unaware of ink colour) | `tests/unit/vision/test_controls.py::TestRecallPrecisionOnFixture` (must keep passing unchanged — fixture is purple-only); `TestPurpleMask::test_rejects_a_saturated_non_purple_colour` (**assertion changes**, see below) | Shared primitive (`config/default.toml` is read by every CLI command and by `web/app.py`'s `load_config()` — no per-run override path exists today, confirmed by grep; changing the shipped default is the only way this reaches the web viewer at all) | `pytest tests/unit/vision/test_controls.py` unchanged fixture numbers (recall/precision/centre-error) + a new test against `data/maps/grid-lines-red-controls/` (skipped if the file is absent, per ADR-010's reproducibility rule) |
| Grid-line misclassification | New shape-based pass in `vision/segment.py` (slots after `classify_palette`, alongside `extract_linear_features` — same file, same pipeline position); reclassifies extreme-elongated near-full-height/width components of `water_shallow`/`water_uncrossable` to `unknown` (config's own conservative "assume forest" fallback, `config/default.toml:248-253`) | Preserves F4 in full (no class added or removed, fixture IoU floors stated against the *existing* 17 classes are unaffected since the fixture has no grid lines); adds **F20** (new — real-scan-only failure mode, no fixture equivalent exists to floor it against) | `tests/unit/vision/test_segment.py::test_area_class_mean_iou_floor_on_the_degraded_render` (must keep passing unchanged) | Local (one new function, one call site, no signature change to `segment()`) | Same IoU test unchanged + a new check against `data/maps/grid-lines-red-controls/`: the five known grid columns' `water_uncrossable` fraction drops from >30% (measured this session) to ~0%, skipped if the file is absent |
| Route-overlay colour | `render/overlay.py::_CORE_COLOR` (one module constant; halo colour and every draw call are unaffected) | No SPEC line names an exact colour (F15 only asks for a legible PNG); preserves the module's own stated invariant ("route colour is not a colour the map prints") by extending it to seven inks instead of six | `tests/unit/render/test_overlay.py`'s pixel-sampling tests import `_CORE_COLOR` from the module rather than hardcoding the tuple — **no test edit needed**, they validate whatever the constant becomes automatically | Local | Same overlay tests, unchanged files, passing against the new constant; new constant's distance from all 7 forbidden inks computed via `config.cmyk_to_srgb` (same measured-not-guessed standard as T013's palette work), asserted in a new small test rather than eyeballed |

### Ordering
All three rows touch disjoint symbols (`config.py`+`vision/controls.py`, `vision/segment.py`,
`render/overlay.py`) and can be built in parallel once the `config.py` rename lands first (it is the
one shared-primitive dependency: `vision/controls.py` and `vision/ocr.py` both read the renamed
field). The overlay-colour row has no code dependency on the other two — it only depends on the
*decision* that red becomes a shipped default ink, made at this gate.

## Expectations that change

- `tests/unit/vision/test_controls.py::TestPurpleMask::test_rejects_a_saturated_non_purple_colour`
  — currently asserts a saturated red is rejected by the default-config mask. Once
  `config/default.toml` ships red as a second recognised control ink, this becomes false by design
  under default config. Fix: pick a colour still genuinely outside every configured band (e.g. a
  saturated green or a hue between the two configured bands) so the test keeps checking "an
  unconfigured colour is rejected," not "red specifically." Root cause: F7's own requirement text
  changes (see ADR-011); this is that change's test-visible edge.

## Exit criteria

- [ ] `rogaine detect --map data/maps/grid-lines-red-controls/map.jpeg` finds the map's red-ink
  controls (recall measured and stated, not just "some found")
- [ ] `rogaine segment --map data/maps/grid-lines-red-controls/map.jpeg` no longer marks the five
  known grid columns as majority `water_uncrossable`
- [ ] A plan across one of those columns, on this map, no longer fails with "no reachable route"
  for that reason
- [ ] `render/overlay.py`'s route colour is measurably distinct from all seven forbidden inks
- [ ] Baseline suite green at 372 passed or better (372 minus the one named edited assertion, plus
  whatever new tests this milestone adds)
