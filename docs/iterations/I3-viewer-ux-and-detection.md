# Iteration I3 — Viewer UX, scale auto-detection exposure, control-number OCR

- **Source:** Owner request, in-session report (2026-09-07), surfaced while attempting T082
  (M9/I2's owner spot-check).
- **Opened:** 2026-09-07
- **Milestone:** `M10` in `docs/TASKS.md`
- **Baseline:** `docker compose run --rm tests` — 457 passed, exit 0; `ruff check .` clean.
  2026-09-07, branch `iteration/I2-vision-recognition-fix` (continued, not re-branched — I3 builds
  directly on I2's landed T077/T079-T081, not yet merged to `master`; see Resume here for the
  reasoning), tree clean apart from the pre-existing, unrelated `docker-compose.yml` port change
  already recorded in I2's own baseline.

## In scope

| Item | Why now |
|------|---------|
| **OCR-numbers** — control numbers read on none of the owner's real scans | Core complaint; SPEC F8 exists but the real-world read rate is effectively 0% before diagnosis (T077 only raised `grid-lines-red-controls` to 3/13) |
| **UI-layout** — map and controls list are never simultaneously visible | Blocks exactly the workflow (assign a control's number) the viewer exists for; confirmed structurally, not just reported |
| **UI-redesign** — moderate visual modernization, same structure/stack | Owner asked directly; bundled with UI-layout since both touch the same files (`index.html`/`style.css`) |
| **Scale-auto** — expose `vision/calibrate.py::calibrate_map` as an opt-in action in CLI + viewer | The detector already exists (T078) but was deliberately scoped to the M7 training-corpus tool only (ADR-016); the owner never found it because it isn't in the product's user-facing flow at all |

## Out of scope this round

| Item | Reason | Recorded as |
|------|--------|-------------|
| Full UX restructure (new navigation paradigm, not just layout+style) | Owner chose "bugs + moderate style redesign" over a full rebuild, to bound this round's regression risk | Phase 1 answer, this file |
| Guaranteed 100% OCR read rate on every real scan | Owner accepted "measurable improvement"; OCR stays explicitly non-load-bearing (ADR-009) | Phase 1 answer |
| New auto-calibration detector tiers beyond what `calibrate_map` (T078) already does | Only wiring the existing three tiers (scale bar / grid / circle diameter) into the product flow — no new detection logic | this file |
| T082 (owner spot-check of I2's circle/hub detection fixes) | Independent, manual-only task, already tracked and still open in M9 — unaffected by I3 | `docs/TASKS.md` M9 |

## Impact map

| Item | Touches | SPEC: changes / preserves | Existing coverage | Class | Regression proof |
|------|---------|---------------------------|--------------------|-------|-------------------|
| OCR-numbers | `src/rogaine/vision/ocr.py` (`_ocr_crop`, `_read_digits`, `_TESSERACT_CONFIG`), possibly `config/default.toml`'s OCR-adjacent tunables, `tests/unit/vision/test_ocr.py` | preserves F8 (unreadable → null + flag, never guessed), ADR-009; changes no SPEC text, implementation quality only | `test_at_least_eleven_of_twelve_controls_read_correctly` (synthetic, 11/12 floor); `test_radius_aware_crop_does_not_regress_the_base_scale_read_rate` (real scan, skip-guarded, current 3/13 on `grid-lines-red-controls`) | Local | Both existing tests keep their current floors; T084's new real-scan counts recorded in `TASKS.md` the same way T079-T081 were |
| UI-layout | `src/rogaine/web/static/index.html`, `style.css`, `app.js` (marker↔table-row highlight sync — does not exist today), `tests/e2e/test_viewer.py` | changes F17's acceptance (adds simultaneous-visibility clause); preserves the A11y non-functional line (keyboard-operable, focus visible, labelled, legible light/dark) | `tests/e2e/test_viewer.py` (T062) covers the full flow but asserts no layout geometry or this a11y scenario today | **Shared primitive** (`.layout`/`.side-column`/`.map-viewport` underlie every panel) — lands first, serially | Extended Playwright case: after selecting/editing a control, both the map viewport's and the controls table's bounding boxes are inside the browser viewport at once; existing flow assertions unchanged |
| UI-redesign | `style.css` (tokens, spacing, type scale), `index.html` (class-level tweaks only, no new interactive elements) | preserves F17, the A11y line, ADR-005 (no build tooling); no SPEC text changes | `tests/e2e/test_viewer.py` must stay green unmodified; no automated "looks modern" floor exists or is planned | Local (depends on UI-layout only because both own the same files) | Playwright flow green; owner sign-off on a live instance (subjective call, same precedent as ADR-019) |
| Scale-auto | `src/rogaine/cli.py` (`_resolve_mpp`, `segment_cmd`, `plan_cmd`), `src/rogaine/web/app.py` (`_resolve_mpp`, `CalibrationIn`/new field, `start_segment`, `start_plan`), `src/rogaine/web/static/index.html`+`app.js`+`api.js` (new "auto" action in the Scale panel), `src/rogaine/vision/calibrate.py::calibrate_map` (reused, not modified unless a thin single-image wrapper is needed) | changes SPEC Non-goals (withdraws the scale-bar line) and adds new F21; preserves F2/F3 (manual paths stay default and always available) | `tests/unit/vision/test_calibrate.py` covers `calibrate_map` itself (corpus-only caller today); no CLI or web test exists for an auto path | **Contract** (CLI and viewer must report the same three outcomes — tier name, or a clear failure — with matching semantics) | New CLI test(s): `--auto-scale` success (stubbed/synthetic) and failure, exits/messages correctly, never overrides an explicit `--scale`/`--calibrate`. New Playwright case: viewer's third scale option, stubbed success and failure. F2/F3's existing tests/flows unchanged |

### Ordering

Three independent workstreams, each internally serial, freely parallel with each other:

1. **OCR:** T083 (diagnose, no product-code paths) → T084 (fix, deps T083).
2. **UI:** T085 (layout fix, shared primitive — lands first) → T086 (visual redesign, deps T085,
   same files).
3. **Scale, CLI half:** T087 (deps: none new — T078 already landed) — independent of 1 and 2.

Then, once both UI and the CLI half are done: **T088** (scale-auto in the web viewer) — deps T086
(shares `index.html`/`app.js`/`style.css`, must land after the redesign settles to avoid rework) and
T087 (mirrors its wording/semantics so CLI and viewer report auto-scale identically).

## Expectations that change

None. Every row above adds coverage; no existing test's passing assertion is edited or weakened.

## Exit criteria

- [ ] Control numbers read on a measurably higher fraction of the owner's real scans than today's
  3/13 (`grid-lines-red-controls`) / 0/13 (the other 12), exact target set by T083's measurement;
  synthetic-fixture 11/12 floor unchanged; OCR still non-load-bearing (ADR-009).
- [ ] The map and the controls list are both visible at once on a standard viewport while editing a
  control's number — no scrolling one out of view to reach the other.
- [ ] The controls table's columns and the parameters panel are legible at their working width — no
  content clipped or requiring horizontal scroll to read.
- [ ] The viewer reads as more concise/modern than the current 6-stacked-accordion layout — owner
  sign-off (subjective, no automated floor, same precedent as ADR-019).
- [ ] Auto-scale is reachable and documented in both the CLI (`--auto-scale`) and the viewer (a
  labelled action in the Scale panel); on a map where no tier fires, the user gets a clear message
  and can still complete manual entry with no crash or silent guess.
- [ ] Baseline suites green at their Phase 0 counts (457 passed) or better; `ruff check .` clean.

## Resume here (branching note)

I3 continues directly on `iteration/I2-vision-recognition-fix` rather than a fresh branch off
`master`: I2 has not merged yet (T082, manual-only, is still open in M9) and T084/T087/T088 build
directly on I2's own T077 (`Control.radius_px`) and T078 (`calibrate_map`). Branching from `master`
now would mean either duplicating those commits or blocking I3 on a manual step nobody but the owner
can perform. Both iterations merge to `master` together once T082's manual check and I3's work are
both done.
