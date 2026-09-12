# Iteration I5 — control-circle/number false negatives and false positives on real scans

## Source

Owner bug report, in-chat 2026-09-12, with two annotated screenshots (crops from real
`ogps-*`-harvested maps, not a specific named file — the owner tested broadly across the `ogps-*`
corpus rather than one map) showing controls 72/44/66/42/53 whose printed number is clearly legible
to a human but came back unread (rendered as the viewer's "?" marker), plus one correctly-read
control (71) for contrast. The owner also separately reports the app sometimes detects spurious
tiny "controls" inside cover-page/legend text where no real control exists.

The owner proposed four heuristics; code inspection this session (not the owner's own claim taken
at face value) found each already partially addressed and identified the specific gap in each:

1. **"Controls are usually purple or red — use colour."** Already the primary detection signal:
   `detect_controls`/`_detect_circles` run Hough only on `purple_mask` (`ink_hue_ranges`, ADR-011/
   ADR-018), and `_ocr_crop` re-applies the same mask to the OCR crop. No gap found in the *signal
   used* — see "Out of scope" below for what this does not explain.
2. **"Once several controls are found, the size is known — use it."** Partially true already:
   `_select_best_scale` (ADR-015) picks one global radius scale for the whole map from
   ring-coverage statistics, and every accepted candidate at that scale shares one nominal radius
   (`r_mid`, T077/ADR-020) by construction. What is missing: no filter compares an individual
   candidate's own *raw* Hough-fitted radius (discarded today, see `_detect_circles`'s own inline
   comment) against the cluster of other accepted candidates at the same scale — a coincidental
   ink blob (e.g. inside a bold digit glyph) that clears `_ring_coverage`'s threshold at the
   winning scale is accepted with no further shape-consistency check.
3. **"A control at the edge of a segment may fail."** Confirmed as a real, distinct mechanism, not
   the owner's guessed "segment" (this codebase has no tiling yet — T070 unstarted): `_ocr_crop`
   (`vision/ocr.py`) clamps its crop window independently per axis to the *raster's own edge*
   (`max(0, ...)`, `min(w_img, ...)`), which shrinks the window rather than sliding it when a
   control sits near the scan's physical boundary — a number printed toward that side can fall
   outside the shrunk crop even though it is fully present in the source raster.
4. **"Spurious tiny detections in cover-page text."** Plausible mechanism identified, not yet
   measured: T090/ADR-031's sub-1.0 `circle_scale_multipliers` rungs (`0.5`, `0.85`) search a
   smaller radius window than the base ISOM print size, specifically to catch undersized
   hand-drawn circles — the same smaller window can also match a round loop inside a bold digit or
   letter glyph (e.g. a title, a course-number label) if it clears `_ring_coverage`. T090 already
   added `_ocr_gate_sub_base_scale`, but it gates at the *set* level (keep-or-discard the whole
   sub-1.0 candidate set based on aggregate valid-read count), so a few genuine sub-1.0 controls
   mixed with several glyph false positives can still let the false positives through as part of
   the winning set.

## In scope

Owner explicitly chose to design all four fixes now rather than a separate measurement-first
diagnosis pass (this iteration's own Phase 1 decision, recorded here rather than silently skipped
— departs from I4/ADR-026's "diagnosis first" precedent by the owner's own call, not a process
lapse). Real-map measurement still happens during Phase 5 verification, not skipped — the
departure is only "no separate pre-implementation diagnosis phase blocking the design."

- **T097** — `_ocr_crop`'s edge-window clamp: slide the fixed-size crop window to stay in-bounds
  instead of shrinking it, whenever the image is large enough to hold the full window (true for
  every real scan; falls back to the current shrink-to-fit behaviour only if the raster itself is
  smaller than the crop, which should not occur in practice).
- **T098** — a per-candidate shape-consistency filter: thread each candidate's raw Hough-fitted
  radius through `_detect_circles` (for this filter only — `Control.radius_px`/`_ocr_crop` keep
  using the matched scale's nominal `r_mid`, unchanged, per T077/ADR-020's own reasoning) and
  reject any candidate whose raw radius is a clear outlier against the winning scale's own
  candidate cluster.
- **T099** — generalise `_ocr_gate_sub_base_scale` from a set-level gate to a per-candidate gate
  when the winning scale is sub-1.0: keep only the individual sub-1.0 candidates whose own crop
  actually yields a plausible read, instead of keeping/discarding the whole set together.
- **T100** — confirm the colour heuristic already covers every code path (add a pinning regression
  test if none exists), then re-measure false-positive rate and OCR read rate across the owner's
  corpus (`data/maps/` real scans + a sample of `ogps-*`) before/after T097-T099, as the concrete
  before/after evidence for the owner's manual sign-off (acceptance below).

## Out of scope / deferred

- **A full diagnosis-first measurement pass before design** (ADR-026/I4 precedent) — owner's
  explicit choice this round; recorded as a deliberate departure, not a silent scope cut.
- **Retuning `ink_hue_ranges`/`purple_mask` itself** — no gap found in the colour signal; if T100's
  measurement finds one, it becomes its own follow-up task rather than expanding scope here.
- **A general non-maximum-suppression / spatial-declustering pass** (e.g. rejecting any candidate
  within one diameter of another as "probably text") — a broader, higher-risk mechanism than T098's
  narrower raw-radius check; not attempted this round unless T100's measurement shows T098+T099
  leave a residual, clearly text-shaped false-positive class.
- **DPI/scale auto-calibration retuning** — ADR-030/T089 already measured this is not the corpus's
  dominant driver; not reopened here.

## Acceptance

Manual owner spot-check (ADR-019 precedent, same as T082/T086/T095): before/after crops for
controls matching the owner's own examples (72/44/66/42/53-style cases) plus 1-2 more real maps
from the corpus, sent via `SendUserFile`. No numeric corpus-wide floor required for this iteration's
gate, though T100's measurement itself is recorded regardless (this project's "measured, not
guessed" convention) for the record and for `docs/DECISIONS.md`.

## Impact map

| Change | Touches | SPEC | Existing tests covering current behaviour | Blast radius | Regression proof |
|---|---|---|---|---|---|
| T097 crop-window slide | `vision/ocr.py::_ocr_crop` | F8 (OCR) | `tests/unit/vision/test_ocr.py` crop-geometry cases | Local — only the crop's `(x0,y0,x1,y1)` computation; ring-erase/digit-strip math downstream is unchanged in shape | New edge-adjacent-control unit test (crop reaches full configured half-width); existing centred-control cases must stay byte-identical (window unchanged when nowhere near an edge) |
| T098 raw-radius consistency filter | `vision/controls.py::_detect_circles` (per-candidate tuple gains a raw-radius field, internal only) | F7 (detection precision) | `tests/unit/vision/test_controls.py`'s existing scale-selection/ring-coverage suite | Local to `_detect_circles`; `_select_best_scale`'s own scoring, `Control.radius_px`, and every downstream OCR/crop path are untouched (still fed `r_mid`) | New synthetic case: one true-ring cluster plus one deliberately mis-sized coincidental blob at the same nominal scale, filter rejects the blob without touching the cluster; real-corpus false-positive count measured before/after (T100) |
| T099 per-candidate sub-1.0 gate | `vision/controls.py::_ocr_gate_sub_base_scale` (signature/behaviour change, same call site) | F7/F8 | `tests/unit/vision/test_controls.py`'s existing `TestOcrGateSubBaseScale`-style cases (ADR-031) | Local — only fires when the winning scale is itself sub-1.0 (already a narrow, already-gated path); production (>=1.0) scale path untouched | Existing `kkm-toksovo`/`lembolovo-kkm`/`novo-kavgolovsky-lesopark` read-rate floors (ADR-031) must not regress; new case with a mixed genuine+glyph sub-1.0 set proving per-candidate keeps the genuine one and drops the glyph |
| T100 measurement + colour-path pin | none (or a small new pinning test only) | F7/F8 acceptance text | full existing suite | None — read-only measurement plus, at most, one new test | The measurement itself is the proof; `docker compose run --rm tests` count must not drop |

**Ordering:** T097 and T098 are independent of each other and of T099 (different functions, no
shared primitive) — can land in either order or in parallel. T099 should land after T098 (both
touch `_detect_circles`'s per-candidate data; landing T098 first avoids T099 needing to thread the
same raw-radius field a second time). T100 is last, verifying all three.

## Exit criteria

- T097-T099 landed, each with its own before/after evidence and a passing regression test.
- Full suite green at or above its Phase 0 baseline count; `ruff check .` clean.
- T100's corpus measurement recorded in `docs/DECISIONS.md` (new ADR-032) regardless of direction.
- Owner spot-check of the same example controls (or equivalent), sign-off recorded before this
  milestone's checkbox closes (ADR-019 precedent — manual, not automatable).
