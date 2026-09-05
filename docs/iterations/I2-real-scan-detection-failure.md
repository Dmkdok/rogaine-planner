# Iteration I2 — Detection/OCR failure on the owner's real scans

- **Source:** Owner bug report (chat, 2026-09-05), four screenshots: two source maps with the
  owner's own hand/eye reference circled in magenta, two matching viewer screenshots showing the
  app's actual detections (amber markers, "?" label = unread number). Quote: "программа не видит
  цифры контролей с очками вообще, а контроли распознает на большинстве карт неправильно."
- **Opened:** 2026-09-05
- **Milestone:** `M9` in `docs/TASKS.md`
- **Baseline:** `docker compose run --rm tests` — 447 passed, exit 0; `ruff check .` clean
  (2026-09-05 10:4x, branch `iteration/I2-vision-recognition-fix`, off `master`@640dce9)

## In scope

| Item | Why now |
|------|---------|
| `purple_mask`'s red ink band over-matches non-control ink on real scans | Root cause, confirmed by measurement (below): drives both the circle over-detection and the OCR-never-reads-anything symptoms the owner reported |
| `_select_best_scale`'s coverage-tie-break can let a noisier base scale beat a genuinely better one | ADR-015's own documented "known limitation, not fixed here" — now observed for real, not theoretical |
| Hub (start/finish) triangle not found on most of the owner's scans | Blocks `plan` outright (exit 1); owner asked to fix in this iteration, not defer |
| T077 (already filed, M8, unstarted) — OCR crop sized from the base scale only | Same failure family; pulled into this iteration's scope rather than left to land separately |

### Reproduction (this session, `iteration/I2-vision-recognition-fix`)

`rogaine detect` run against all 13 of the owner's own scans under `data/maps/` (excluding the
`ogps-*` harvested corpus and the already-calibrated `grid-lines-red-controls` fixture):

| Map | Circles detected | Unreadable numbers | Hub |
|-----|------------------:|--------------------:|-----|
| ozero-shchuche | 71 | 71 | not found |
| kkm-3-2020 | 71 | 71 | not found |
| kkm-5-2020 | 52 | 51 | not found |
| kkm-toksovo | 159 | 159 | not found |
| lembolovo-kkm | 22 | 22 | not found |
| michurinskoe | 40 | 40 | found |
| novo-kavgolovsky-lesopark | 62 | 61 | not found |
| pervomayskoe | 41 | 41 | found |
| toksovo-1 | 22 | 22 | not found |
| toksovo-zubry | 22 | 22 | found |
| treugolnoe | 66 | 66 | found |
| history-race-2024-michurinskoe | 31 | 31 | found |
| history-race-primorsk | 49 | 34 | not found |

Typical real courses on these maps carry ~10-20 controls; every map over-detects by 2x-10x, and
every map's OCR read rate is at or near 0%. Hub not found on 8 of 13.

### Root cause, measured on `ozero-shchuche/map.jpg`

`purple_mask` flags 6.82% of the image's pixels — 3.5x `grid-lines-red-controls`' 1.93% (the one
real scan F7's floor is measured against). Of the 494,230 masked pixels, 436,091 (88%) fall in the
*red* band (`ink_hue_ranges`' `[0, 9]`/`[167, 179]`, added by ADR-011 for maps with red-marked
controls) with mean RGB `(161, 106, 90)` — a brownish contour-line colour, not control ink; only
58,139 (12%) are in the true purple band, mean RGB `(234, 66, 221)`.

Restricting `ink_hue_ranges` to the purple band alone (`[140, 175]`) on this same file drops
detections from 71 to 21 (all ring-coverage 1.00), much closer to the true control count — but hub
is *still* not found under this clean mask, confirming the hub-triangle failure is not fully
explained by ink-hue over-match and needs its own look (T081).

This lands squarely inside ADR-015's own documented caveat: "a wrong scale producing many
same-bucket false fits ... would still win. No evidence of either case exists in this project's
corpus." The owner's scans are exactly that case — they were never in the corpus T076/ADR-015 was
tuned or tested against (ADR-016 explicitly left the owner's scans untouched).

## Out of scope this round

| Item | Reason | Recorded as |
|------|--------|-------------|
| Fully automated ground-truth CSVs for all 13 owner scans | No labelled corpus exists; producing one is its own effort disproportionate to this bug fix | ADR-019 |
| Generalising ink-colour detection beyond the two known families (purple, red) | ADR-011 already deferred this pending a real corpus of a third ink family; none has appeared | Unchanged, no new ADR needed |
| T070 (tiling/mask export) and the rest of M7 | Unrelated to detection correctness; still gated on the Launch-checklist item this iteration is trying to unblock | Unchanged |

## Impact map

| Item | Touches | SPEC: changes / preserves | Existing coverage | Class | Regression proof |
|------|---------|---------------------------|--------------------|-------|-------------------|
| T079 ink-hue false-positive tightening | `config/default.toml` (`ink_hue_ranges`, `purple_min_saturation`/`purple_min_value`, possibly per-band), `src/rogaine/vision/controls.py::purple_mask` | preserves F7 (both fixture and `grid-lines-red-controls` floors); changes nothing in `SPEC.md` text | `TestPurpleMask`, `TestRealScanRedInk::test_purple_mask_flags_the_real_red_ink` (>=95% coverage on the real red-ink scan), `TestRecallPrecisionOnFixture`, `TestRealScanRedInk::test_recall_and_hub_match_the_true_positions` (recall/precision >=0.90, hub found) | Shared primitive — every other row reads `purple_mask`'s output | Both anchor tests above still pass; new test measures `purple_mask` density on `ozero-shchuche` drops to a stated ceiling (target: same order of magnitude as `grid-lines-red-controls`'s 1.93%) |
| T080 `_select_best_scale` tie-break hardening (contingent) | `src/rogaine/vision/controls.py::_select_best_scale`, `_SCALE_TIE_EPS` | preserves F7; ADR-015's tie-break decision superseded only if still needed after T079 | `TestOversizedRingsBeatABaseScaleDecoy`, `TestSingleScaleSelected` | Local (same file as T079 — serial after it, not parallel) | Re-run the 13-map reproduction table above after T079; if any map still shows gross over-detection, that map's Hough candidate counts per scale are the regression proof for the fix; if none do, this task closes as "measured, no change needed" rather than a speculative retune |
| T081 hub triangle not found on real scans | `src/rogaine/vision/controls.py::_detect_hub_triangle` (and its tunables: `_TRIANGLE_MIN_SIDE_RATIO`, `circle_diameter_tolerance`, the `approxPolyDP` epsilon) | preserves F7's hub clause; `TestHubTriangleDetection` (synthetic fixture) must keep passing unchanged | `TestHubTriangleDetection`, `TestRealScanRedInk::test_recall_and_hub_match_the_true_positions`'s hub assertion | Local (same file — serial after T079, since hub search runs against T079's corrected mask) | Hub found on `ozero-shchuche` plus every owner scan in the reproduction table where a start triangle is actually present in the source map (spot-checked list, T082) |
| T077 scale-aware OCR crop (M8, unstarted, pulled into this iteration) | `src/rogaine/vision/ocr.py::_ocr_crop`, `src/rogaine/models.py::Control` (new field, needs its own ADR per ADR-008's frozen-model rule), `src/rogaine/vision/controls.py::detect_controls` (populate the new field) | preserves F8; no `SPEC.md` text change | none dedicated yet — T077's own DoD calls for a new real-scan regression test | Data (schema change to a frozen model) — serial, alone, per the blast-radius rule; also shares `vision/controls.py` with T079/T080/T081 so scheduled after all three | New real-scan test: a control matched at a non-base scale (`grid-lines-red-controls`'s 13 controls all land at multiplier 2.0 per T076) reads its number correctly, not `None` |
| T082 owner spot-check | none (validation only) | proves F7/F8 hold in practice on real input, no requirement text change | manual, no automated coverage possible without ground truth | Local | Owner reviews CLI output (or viewer) for 2-3 of their own maps post-fix and confirms circle positions/hub/numbers look right; recorded in `docs/STATUS.md` |

**Ordering:** T079 first, serially (shared primitive — every other row depends on its output).
T080 and T081 both touch the same file and both need T079's result to know if/what remains broken;
serial after T079, and serial with each other since both touch `vision/controls.py`. T077 needs its
own `models.py` ADR and touches `vision/controls.py` too, so it lands last of the detection-side
work. T082 is the final step, after everything else.

## Expectations that change

None. Every existing test named above (`TestPurpleMask`, `TestRealScanRedInk` — both tests,
`TestRecallPrecisionOnFixture`, `TestHubTriangleDetection`, `TestOversizedRingsBeatABaseScaleDecoy`,
`TestSingleScaleSelected`) keeps its current assertion and floor. This is a hard constraint, not
an aspiration: if a task cannot satisfy both the fixture/`grid-lines-red-controls` floor and the
new owner-scan behaviour with one change, that is a finding to bring back to the owner, not a
reason to loosen an existing assertion quietly.

## Exit criteria

- [ ] `purple_mask` density on `ozero-shchuche/map.jpg` measured and reduced from 6.82%, without
      regressing `TestRealScanRedInk`'s two tests or `TestPurpleMask`/`TestRecallPrecisionOnFixture`
- [ ] `_select_best_scale`'s behaviour on the 13-map reproduction table re-measured after T079;
      fixed if still broken, left alone (documented) if not
- [ ] Hub found on every owner scan in the reproduction table that actually has a start triangle
- [ ] A control detected at a non-base scale reads its printed number (T077's DoD)
- [ ] Owner has manually spot-checked 2-3 of their own maps (T082) and confirms the result looks
      right
- [ ] Baseline suite green at 447 or better; `ruff check .` clean
