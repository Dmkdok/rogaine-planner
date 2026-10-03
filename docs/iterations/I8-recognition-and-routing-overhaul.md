# Iteration I8 — Recognition and routing overhaul: barriers that hold, lines identified positively, numbers found globally, a measured benchmark

- **Source:** Owner report, in-chat 2026-10-02: on `data/maps/toksovo-zubry` a fence was read as a
  road and the route ran along it, and the route crossed a black-banked river; on
  `data/maps/ogps-9905_f17e27b4a638ca8beb85738a0140f828` controls 64, 54, 92, 31, 33, 63, 41 came
  back unread. The owner's framing: ten iterations have patched the same symptoms without
  converging; asked for a root-cause review against the reference article
  (https://habr.com/ru/articles/1065342/) and a final fix. The review (this session, chat) found
  four root causes and offered options; the owner chose: graph **B**, terrain **A** (+ manual
  barrier tool), numbers **A+B+C**, benchmark **built by Claude from the existing corpus**;
  SegFormer deferred while the owner collects OCAD files.
- **Opened:** 2026-10-02
- **Milestones:** `M16` (benchmark) → `M17` (graph barriers) → `M18` (linear features + manual
  barriers) → `M19` (control numbers) in `docs/TASKS.md`, strictly in that order.
- **Baseline:** see `docs/STATUS.md` `## Baseline I8` — branch `iteration/I8-recognition-overhaul`
  cut from `iteration/I2-vision-recognition-fix` @ `638cdca`, tree clean.

## Root causes (measured this session, not inferred)

| # | Root cause | Evidence | Iterations that patched its symptoms |
|---|-----------|----------|--------------------------------------|
| R1 | Every elongated `black_100` component becomes `road`/`vehicle_track`/`footpath`, split by width alone (`vision/linear.py::extract_linear_features`). There is no barrier concept. | `toksovo-zubry`, fence by control 25 (black line with ticks) segments as `footpath`; the river's black banks by controls 45/63/64 segment as `unknown` (passable); blue marsh hatch partly segments as `water_uncrossable`. | I1 (grid lines), I6/I7 (banked water, T101/T110), I7 (power line, T111/T112) |
| R2 | Downsampled graph: a 4x4 block is passable if **any** pixel is (`cost/graph.py::_aggregate_blocks`), and diagonal edges cut corners. Any barrier thinner than ~8px vanishes. The module docstring claims the opposite. | `toksovo-zubry` river window (x 1150-1550, y 1650-1950): 5253 impassable pixels, **5** fully-impassable 4x4 blocks. The river's blue core is ~2px wide. | I6 (river), I7 (lake, out-of-bounds) |
| R3 | Number OCR reads a fixed square (3.4 radii) around each circle and assumes a 4mm digit; five layered heuristics (ring erase, area floor, largest cluster, edge-touch reject, ...) then patch its failures. The VLM fallback receives the same wrong crop. | `ogps-9905`: 22/22 circles found, 11/22 numbers read, `71` read as `7`. Digits there are large and placed further from the ring than the window allows (e.g. 54 sits well above its circle). | I2, I3, I4, I5, I6, I7, T117 |
| R4 | No labelled ground truth (ADR-019 declined it). Thresholds were tuned on 1-3 maps; a fix in one place silently broke another. | ADR-019; every iteration's "measured on map X" notes. | all |

Reference article (verified I7 and again this session): SegFormer on ~200 OCAD-rendered maps for
terrain; VLM (Qwen) over tiles finds controls and numbers, classical CV only snaps the centre.
Least-cost-path literature on orienteering maps (ICA Proc. 2021; CEUR Vol-2020 paper 5) models
barriers explicitly.

## In scope

| Item | Why now |
|------|---------|
| **Bench** — labelled benchmark (~20 maps) + `rogaine evaluate` metrics | R4: without it "done" is unmeasurable; every later milestone is accepted against it |
| **Graph** — edges vetoed by a full-resolution line-of-sight barrier check; fence crossings priced per crossing | R2; owner chose option B |
| **Lines** — positive identification of linear features (dash pattern, ticks, banks); unidentified solid lines neutral; marsh hatch not water | R1; owner chose option A |
| **Manual barriers** — viewer/CLI draw a barrier line or a forbidden polygon | Owner chose it alongside A; cheap insurance on any map |
| **Numbers** — global text-blob detection + per-map digit height + global assignment; RapidOCR (PP-OCR via ONNX) replaces Tesseract; uniqueness + legend cross-check; tiled whole-map VLM mode with circle snap, `auto` by default | R3; owner chose A+B+C, VLM default "auto" |

## Out of scope this round

| Item | Reason | Recorded as |
|------|--------|-------------|
| SegFormer terrain model (article's approach) | No OCAD/OMAP training corpus yet; owner is collecting files | ADR-049 |
| Relief/DEM | Unchanged deferral | ADR-028 |
| Three older open owner sign-offs (T086 etc.) | Independent, unaffected | `docs/STATUS.md` "Blocked on the owner" |
| A full labelled set of all 386 corpus maps | ~20 maps covers every reported failure family; more is labelling cost, not signal | ADR-042 |

## Impact map

| Item | Touches | SPEC changes / preserves | Existing coverage | Class | Regression proof |
|------|---------|--------------------------|-------------------|-------|------------------|
| Bench | new `src/rogaine/eval/` (truth loader, metrics), `cli.py` (new `evaluate` command), `data/maps/<map>/truth.toml` + `data/bench.toml` (gitignored, ADR-010) | adds F25; preserves all | none (new) | Local | new unit tests on the synthetic fixture with a generated truth file; evaluator output on the bench recorded in `docs/TASKS.md` |
| Graph | `cost/graph.py` (`_aggregate_blocks`, `_build_edges`, `build_grid_graph`), `config/default.toml` `[graph]` | changes F10 (barrier guarantee, fence crossing price); preserves F11, F19, perf budgets | `tests/unit/cost/test_graph.py` (`TestStrictImpassable`, `TestDownsampleAggregation`, `TestPerformance`), `tests/perf/test_budgets.py`, `tests/e2e/test_cli.py::TestGoldenRegression` | **Shared primitive** — every route depends on it; lands first after Bench, serially | new tests: 1px/2px horizontal, vertical, diagonal barriers at downsample 4 and 8 are never crossed; bench barrier probes 0 crossings; perf within budget |
| Lines | `vision/linear.py` (`extract_linear_features` + new pattern helpers), `vision/palette.py` (marsh hatch), `models.py` (`TerrainClass` **append** `fence`, `barrier`), `config/default.toml` `[[terrain]]` + `[linear]` | changes F4/F5, F20 extended; amends ADR-008 (append-only enum growth) | `tests/unit/vision/test_linear.py` (all classes), `test_segment.py::TestGridInkOnRealScan`, `tests/unit/test_models.py`, `test_config.py` | **Contract** (`TERRAIN_ORDER` is baked into `terrain.npz` and golden files — append only) | existing linear fixture IoU floors hold; new tests: dashed vs solid vs ticked synthetic lines; bench class probes |
| Manual barriers | `web/app.py` (new `GET/PUT /api/runs/{id}/barriers`), `web/static/{index.html,app.js,api.js,style.css}`, `cli.py` (`plan --barriers`), `cost/field.py` (rasterise as impassable) | adds F24; F17 extended; preserves F17's existing tool behaviour | `tests/e2e/test_viewer.py`, `tests/unit/web/*`, `tests/unit/test_cli.py` | Local (after Graph: relies on the veto) | new Playwright case: draw a line across the fixture route → route changes and does not cross it; API round-trip test; CLI test |
| Numbers | `vision/ocr.py` (`_ocr_crop` and helpers replaced by a global blob path; `read_control_numbers` signature kept), new `vision/ocr_rapid.py`, new `vision/vlm_controls.py` (tiled whole-map), `vision/ocr_vlm_ollama.py`/`ocr_vlm.py` (new prompt/entry), `vision/controls.py` (scale gates call the reader with VLM off — T117 rule kept), `config/default.toml` `[ocr]`/`[ocr_fallback]`, `pyproject.toml`, `Dockerfile` | changes F8, F23; Non-goal "VLM control detection" withdrawn; preserves F8's "never silently guessed", F19 (VLM responses cached) | `tests/unit/vision/test_ocr.py` (`TestRealScanReadRateFloor`, synthetic 11/12), `test_ocr_vlm*.py`, `test_controls.py` (scale gates) | **Contract** (the scale gates in `controls.py` consume OCR outcomes — changing the reader changes circle-scale selection) | synthetic floor ≥ 11/12; real-scan floors hold or rise; bench: number metrics; T117's "gates never see VLM" test kept |

## Expectations that change

- `tests/e2e/golden_route.json` — may change once barriers stop leaking (M17). Regenerated in its own
  commit naming the reason, only if the diff is explained by vetoed edges.
- `tests/unit/cost/test_graph.py::TestDownsampleAggregation` — asserts today's "any passable pixel"
  semantics; it is rewritten to the new guarantee (ADR-043).
- `tests/unit/vision/test_linear.py` width-only class assignment cases that draw *solid* thin lines
  and expect `footpath` — a solid thin line is no longer a footpath (ADR-044). Rewritten to draw
  dashed lines for footpath/track.
- `tests/unit/vision/test_ocr.py` crop-geometry tests (`_ocr_crop`, `_keep_largest_ink_cluster`,
  `_strip_thin_ink`) — deleted with the code they test (ADR-045); the read-rate floors stay.
- `TERRAIN_ORDER` grows by two members at the end; `test_models.py`/`test_config.py` count
  assertions update.

## Proposed acceptance targets (fixed at the gate, measured on the bench)

| Metric | Target |
|--------|--------|
| Circle recall / precision | ≥ 0.97 / ≥ 0.95 |
| Numbers read correctly, classical path (no VLM) | ≥ 85% of labelled controls |
| Numbers read correctly, `auto` with local VLM | ≥ 95% |
| Numbers read **wrongly** (any mode) | ≤ 1% — unread is acceptable, wrong is not |
| Barrier probes crossed by a planned path | 0 |
| Fence/bank probe points classified as road/track/path | 0 |
| Real road/track/path probe points still classified as such | ≥ 95% |

## Exit criteria

- [ ] `rogaine evaluate` runs on the bench and prints every metric above, per map and in total
- [ ] `toksovo-zubry`: no route runs along or across the fence by control 25 as a road; no route crosses the black-banked river except at a mapped crossing
- [ ] `ogps-9905`: 64, 54, 92, 31, 33, 63, 41 read correctly (classical path at least 5 of 7; `auto` all 7)
- [ ] A drawn barrier in the viewer changes the route and is never crossed
- [ ] All targets above met, or each miss named with its measured value and an owner decision
- [ ] Baseline suites green at their Phase 0 counts or better (minus tests deleted with their code, listed by name)
