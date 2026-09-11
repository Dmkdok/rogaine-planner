# Iteration I4 — OCR scale-invariance, points auto-fill, viewer route alternatives, route-choice quality, relief prep

- **Source:** Owner request, in-chat (2026-09-11), partly serving as M9/I2's own T082 owner
  spot-check (see "T082 closure" below).
- **Opened:** 2026-09-11
- **Milestone:** `M11` in `docs/TASKS.md`
- **Baseline:** `docker compose run --rm tests` — 472 passed, exit 0; `ruff check .` clean.
  2026-09-11, branch `iteration/I2-vision-recognition-fix` (continued — see "Branching note" below),
  tree clean apart from the pre-existing, unrelated `docker-compose.yml` port change already
  recorded in I2/I3's own baselines (owner still has not said keep/commit/revert; left alone again).

## T082 closure (M9/I2)

The owner's report that control-number recognition "стало лучше, но всё равно очень многие очень
чёткие цифры не распознаются, особенно на больших картах" is this session's real spot-check of the
post-M9 detection/OCR fixes (ADR-019's acceptance gate) — recorded as **T082 done, partial pass** in
`docs/TASKS.md`, closing M9. The follow-up is this iteration's OCR-numbers item below, not a reopened
T082. **T086** (I3's own open manual sign-off — viewer "reads as more concise/modern") is untouched
by this message and stays open separately, unblocked.

## In scope

| Item | Why now |
|------|---------|
| **OCR-scale** — control-number OCR/detection still misses many legible numbers, correlated with the map's physical scale (large sheet photographed from afar vs. small sheet photographed close up) | Direct owner report, is T082's real result; two concrete, code-grounded hypotheses already exist (ADR-026) |
| **Points-autofill** — viewer should derive points from a typed control number (`123` -> 12 points, not 1), editable | Direct owner request; found along the way that the *existing* OCR pipeline's own `first_digit` rule already computes this wrong for 3+-digit numbers (real bug, ADR-024) |
| **Route-alternatives** — viewer should offer several good routes, switchable by button, when no single route clearly dominates | Direct owner request; backend (F16, `solve_alternatives`) already computes and returns these — the viewer has just never consumed them |
| **Route-choice quality** — routes often look implausible to an experienced orienteer; owner asked for a cheap-model literature pass distilled into applicable rules | Direct owner request, explicitly scoped to research-then-apply this round (Phase 1 answer) |
| **Relief-prep** — future terrain-relief (elevation) handling needs study before implementation | Direct owner request, explicitly framed as future preparation only ("подготовиться к дальнейшей реализации") |

## Out of scope this round

| Item | Reason | Recorded as |
|------|--------|-------------|
| Actually implementing terrain relief/elevation in the cost model | Owner explicitly framed as future work; also genuinely blocked on a georeferencing decision this project's own Non-goals currently excludes | ADR-028, T096 |
| A guaranteed OCR read-rate floor for "any scale" | No corpus reaches 100%, and OCR stays explicitly non-load-bearing (ADR-009); owner accepted "measure the whole corpus, improve it" over naming specific target files | Phase 1 answer, ADR-026 |
| Any solver-architecture change for route-choice (new search algorithm, ML scoring) | Owner asked for rules distilled from real practice, applied as cost-model tunables; a full rewrite is out of this round's budget | ADR-027 |
| T086 (I3's viewer visual review) and any other I3 follow-up | Independent, already tracked, unaffected by this iteration | `docs/TASKS.md` M10 |

## Impact map

| Item | Touches | SPEC: changes / preserves | Existing coverage | Class | Regression proof |
|------|---------|---------------------------|--------------------|-------|-------------------|
| OCR-scale | `src/rogaine/vision/controls.py` (`_select_best_scale`, `_detect_circles`, `circle_scale_multipliers`), `src/rogaine/vision/ocr.py` (`_ocr_crop`), `src/rogaine/vision/calibrate.py` (only if default-on changes), `config/default.toml`, possibly `cli.py`/`web/app.py` (only if auto-scale's opt-in default changes, ADR-022) | preserves F7 (recall/precision floors), F21 (auto-scale never overrides an explicit manual value); changes no SPEC text this round — implementation-fidelity work, same precedent as I3's OCR item | `TestRealScanReadRateFloor`, `TestScaleAwareCropOnRealScan` (`tests/unit/vision/test_ocr.py`); `tests/unit/vision/test_controls.py`'s scale-sweep coverage | Local (diagnosis, T089) escalating to **Contract** only if T090 changes the CLI/viewer auto-scale default (both sides change together) | T089's measured baseline vs. T090's after counts, per-map, same shape as ADR-023; existing floors raised, not lowered |
| Points-autofill | `src/rogaine/vision/ocr.py` (`_apply_points_rule`), `config/default.toml` (comment), `src/rogaine/web/static/app.js` (`numberInputCell` commit handlers for `control-*-number`/`control-*-points`), `tests/unit/vision/test_ocr.py` | changes: new F22; preserves F8's null/flag-on-unreadable contract, F9 (CSV import still overrides wholesale) | `TestPointsRule` (2-digit only, unaffected by the fix) | Local | New unit test: 3-digit number -> correct points; new e2e case: typing a number auto-fills points, editing points then the number again leaves points untouched |
| Route-alternatives | `src/rogaine/web/static/app.js` (`onPlanDone`, `renderRouteResults`, new switch-control rendering), `index.html`, `style.css` | changes: F16's acceptance (viewer exposure clause); preserves F17's existing flow | none — `alternatives` key in the `/plan` response has never been read by the viewer | Local (`web/app.py`'s response shape is unchanged, already carries `alternatives`) | New e2e case: multi-alternative map shows switch controls and switching redraws both overlay and legs table; single/zero-alternative map shows none; existing `TestFullViewerFlow` unchanged |
| Route-choice quality | `docs/research/route-choice-heuristics.md` (review pass), `docs/DECISIONS.md` (new ADR), then `src/rogaine/cost/`, `src/rogaine/solve/`, `config/default.toml`, `tests/unit/cost/`, `tests/unit/solve/` for T095 | T094 changes no SPEC text (research); T095's SPEC line is added when it lands, scope TBD from T094 (same pattern as T078's original filing) | `tests/unit/cost/test_field.py`, `tests/unit/solve/*` cover the current physical-only cost model; nothing covers route "plausibility" | T094: Local (docs only). T095: Local, unless a rule needs a new field on `Control`/`TerrainMap` shared by other modules, in which case Shared primitive | T094: every cited source verified to actually support its rule (a spot-check during intake already found one mismatch). T095: before/after routes on a real map, owner-reviewed; existing cost/solve tests unchanged unless T094's ADR says a specific assertion's expectation was wrong |
| Relief-prep | `docs/research/terrain-relief-integration.md` only | no SPEC change; Risks & assumptions #3 gets a trailing pointer note, not a rewrite | none (nothing implemented) | Local | Document exists and covers the four points ADR-028 names; no code/config touched, verified by `git diff --stat` |

### Ordering

See the milestone note in `docs/TASKS.md` M11: T091 (points-rule fix, quick, independent) lands
before T090 (OCR-scale fix) since both own `vision/ocr.py`; T092 (viewer points-autofill) lands
before T093 (viewer alternatives) since both own `app.js`. T094 → T095 is a hard dependency (no
cost-model code before the synthesis ADR exists). T096 and T089 (diagnosis-only) are parallel-safe
with everything.

## Expectations that change

None yet. `TestPointsRule`'s assertions are preserved exactly (the 2-digit fixture numbers give
the same result under both the old and the corrected formula) — the behaviour change only becomes
observable for 3+-digit numbers, which nothing tested before. Any real-scan OCR floor changes from
T090 are additions/raises, not edits to a passing assertion's expected value going down.

## Exit criteria

- [ ] Corpus-wide control-number read rate and circle-detection recall/precision measurably improve
  beyond T089's own measured baseline (no single-file target — Phase 1 answer); existing per-map
  floors hold or rise; the synthetic fixture's 11/12 floor holds.
- [ ] Typing a control's number in the viewer auto-fills its points using the corrected `first_digit`
  rule (`123` -> 12); a manually-edited points value is never silently overwritten by a later number
  edit on the same control.
- [ ] When a planned route has more than one structurally distinct alternative, the viewer offers
  switchable buttons between them, each redrawing the map and leg summary; the primary route stays
  the default.
- [ ] `docs/research/route-choice-heuristics.md` exists with verified sources; a follow-up ADR names
  which rules this iteration actually implements in the cost model, and at least one lands,
  owner-reviewed on a real map.
- [ ] `docs/research/terrain-relief-integration.md` exists, covering data sources, pipeline
  integration points, the new-parameter shape, and the georeferencing tension — no code changes.
- [ ] Baseline suites green at their Phase 0 count (472 passed) or better; `ruff check .` clean.

## Branching note

I4 continues directly on `iteration/I2-vision-recognition-fix`, same reasoning as I3: I2/I3 have not
merged to `master` yet (T086 still open, manual-only), and this iteration's OCR-scale work builds
directly on I2's T077/T079-T081 and I3's T083-T084/ADR-023. All three iterations merge together once
every open manual sign-off (T086, and none new from I4) is done.
