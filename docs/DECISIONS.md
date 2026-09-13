# Decisions

## Index
| ADR | Title | Status |
|-----|-------|--------|
| 001 | ISOM palette classifier is the primary segmenter; SegFormer is optional | accepted |
| 002 | Multi-source Dijkstra for the travel matrix, not pairwise A* | accepted |
| 003 | Two solvers: exact Held-Karp as oracle, heuristic for real sizes | accepted |
| 004 | Docker + Python 3.12 is the supported runtime; host 3.14 is best-effort | accepted |
| 005 | Vanilla JS + Canvas viewer, no node toolchain | accepted |
| 006 | Contour density as a slope proxy, no elevation reconstruction | accepted |
| 007 | No georeferencing or GPX in v1 | accepted |
| 008 | `models.py` is a frozen contract after M0 | accepted |
| 009 | Tesseract OCR, explicitly non-load-bearing | accepted |
| 010 | Real map corpus validates; synthetic fixture tests; neither is committed | accepted |
| 011 | Control ink is a configured list of hue bands, not a fixed purple; the default ships both purple and red | accepted |
| 012 | Grid/annotation ink is excluded from colour classification by shape, not by narrowing the colour threshold | accepted |
| 013 | Track-derived travel-cost calibration from o-gps-center GPS tracks | proposed |
| 014 | o-gps-center.ru scraped maps supplement ADR-010's owner-corpus premise | accepted |
| 015 | Control-circle/hub detection sweeps multiple size scales, not a fixed ISOM print size | accepted |
| 016 | Per-map auto-calibration from the printed scale bar, not embedded scan DPI | proposed |
| 017 | Upper bounds on `RunConfig`'s numeric fields (S-001) | accepted |
| 018 | Ink-hue false-positive rate is tightened by measurement; the red band is narrowed, not removed | accepted |
| 019 | The owner's real-scan corpus stays spot-checked, not a full labelled ground-truth set, this iteration | accepted |
| 020 | `Control` carries the matched scale's nominal circle radius, so OCR can size its crop from it | accepted |
| 021 | Viewer layout becomes a fixed split view — map pinned, controls list independently scrollable | accepted |
| 022 | Auto-calibration is exposed as an opt-in path in the CLI and viewer, not only the M7 corpus tool | accepted |
| 023 | Real-scan OCR failure is dominated by leftover non-digit ink and ring-erasure undershoot, not crop framing | accepted |
| 024 | `first_digit` points rule uses all digits but the last; viewer auto-fills points from the control number | accepted |
| 025 | The web viewer exposes the solver's existing top-K alternative routes, switchable | accepted |
| 026 | Control-number OCR scale-invariance work is diagnosis-first (T089), mirroring T083, not a speculative fix | accepted |
| 027 | Route-choice heuristics: a cheap-model literature pass feeds a human synthesis step before any cost-model code changes | accepted |
| 028 | True terrain relief (elevation/DEM) integration is deferred; research/options document only | accepted |
| 029 | T095 implements a linear-feature proximity bonus and slope-penalty retuning; several rules deferred | accepted |
| 030 | T089 diagnosis: H1 (DPI/calibration) unsupported by the corpus; H2 (missing sub-1.0 circle-scale multipliers) is real for some maps but the ring-coverage scorer can't safely act on it alone | accepted |
| 031 | T090 fixes H2 with measured sub-1.0 `circle_scale_multipliers` rungs gated behind an OCR-outcome check; OCR crop-sizing constants are re-verified and left unchanged (no clean win found) | accepted |
| 032 | Real-scan control detection: OCR crop windows slide instead of truncating at the raster edge; a per-candidate raw-radius consistency filter and a per-candidate sub-1.0 OCR gate replace their set-level predecessors | accepted |

---

## ADR-001 — ISOM palette classifier is the primary segmenter; SegFormer is optional
- Date: 2026-08-18
- Status: accepted
- Context: The article trains SegFormer MiT-B4 on ~200 OCAD maps. This project has a handful of
  rasters and a few `.ocd` files — nowhere near that dataset. ISOM is a printing specification, so
  the colours on a rendered or scanned map are standardised, not learned.
- Decision: Classify terrain by nearest ISOM colour in CIELAB with an `unknown` fallback. Keep
  SegFormer as milestone M7, trained on masks this classifier generates, and only after the owner
  accepts the route quality.
- Consequences: No dataset, no GPU and no training time before the first useful route; near-exact
  masks on renders and scans. Weak on phone photos, which is exactly what M7 addresses. Adds a
  dependency on the ISOM colour table being correct — sourced from IOF Appendix 1 and cited in
  `config/default.toml`.

## ADR-002 — Multi-source Dijkstra for the travel matrix, not pairwise A*
- Date: 2026-08-18
- Status: accepted
- Context: The route needs travel time between every pair of controls. The article runs A* per pair.
  At 60 controls that is 1830 searches over a multi-million-node grid.
- Decision: Run one Dijkstra sweep per control (61 sweeps) over the CSR grid graph via
  `scipy.sparse.csgraph`, reading every pair off the resulting distance rows. Keep A* only for the
  viewer's interactive single-pair queries.
- Consequences: Roughly 30x fewer searches and C-speed execution. Each sweep explores the whole map
  rather than stopping early, and predecessor arrays cost memory, so `graph_downsample` (default 4)
  is a first-class config knob with a performance guard on it.

## ADR-003 — Two solvers: exact Held-Karp as oracle, heuristic for real sizes
- Date: 2026-08-18
- Status: accepted
- Context: Held-Karp is exact but 2^N in state; the owner's maps carry 30-80 controls. Reporting a
  heuristic route with no quality evidence would fail the acceptance bar ("не хуже качеством").
- Decision: Ship both. Held-Karp solves and proves optimality up to a configured cap (N<=15) and
  serves as the test oracle; a seeded GRASP + local search handles real instances. `bench` prints
  the measured gap.
- Consequences: More code and a second correctness surface, bought back as verifiable quality. The
  product never claims optimality at 60 controls — it reports the objective and the measured gap
  where the exact answer is computable.

## ADR-004 — Docker + Python 3.12 is the supported runtime; host 3.14 is best-effort
- Date: 2026-08-18
- Status: accepted
- Context: The host runs Python 3.14.3, ahead of most CV wheel matrices. `CLAUDE.md` already requires
  `docker compose run --rm tests` because pytest hangs on this Windows host.
- Decision: One image, `python:3.12-slim` plus tesseract and the opencv runtime libraries, shared by
  the `app` and `tests` services. Host installation is documented but unsupported.
- Consequences: Reproducible runs and a working test path; the viewer needs a published port, and
  file paths cross the container boundary, which the CLI must handle.

## ADR-005 — Vanilla JS + Canvas viewer, no node toolchain
- Date: 2026-08-18
- Status: accepted
- Context: The viewer is one page: a zoomable map canvas, draggable markers, a parameter panel, a
  results table.
- Decision: FastAPI serves static HTML/CSS/JS drawing on Canvas 2D. No React, no bundler, no
  `node_modules`.
- Consequences: The whole product stays a single Python install and one process, and Playwright can
  drive it directly. Complex UI state is hand-rolled; if the viewer grows well past this scope, this
  ADR gets superseded rather than stretched.

## ADR-006 — Contour density as a slope proxy, no elevation reconstruction
- Date: 2026-08-18
- Status: accepted
- Context: The article penalises contour crossings. Reconstructing a DEM from contour lines needs
  line tracing, height assignment and interpolation — a project of its own, and fragile on a raster
  where contours are broken by symbols and text.
- Decision: Extract the brown contour mask, blur it into a local density field, and derive a
  multiplicative slope penalty from it.
- Consequences: Cheap, robust, and close to the reference behaviour. It cannot distinguish uphill
  from downhill, so a leg costs the same in both directions — stated in the output and in the README
  rather than hidden.

## ADR-007 — No georeferencing or GPX in v1
- Date: 2026-08-18
- Status: accepted
- Context: The owner explicitly declined GPX export; the route is consumed as a picture and a table.
- Decision: Everything stays in map pixel coordinates. No world files, no GeoTIFF, no GPX.
- Consequences: Removes an entire coordinate-transform surface from v1. Adding it later means a
  two-point affine calibration and a GPX writer, additive rather than structural.

## ADR-008 — `models.py` is a frozen contract after M0
- Date: 2026-08-18
- Status: accepted
- Context: Three workstreams (vision, routing, delivery) run in parallel after M0 and must not block
  on each other or edit the same files.
- Decision: All shared types live in `src/rogaine/models.py`, defined in M0 and frozen. Changing them
  afterwards requires a new ADR and a coordinated update.
- Consequences: Routing develops against synthetic terrain and hand-built matrices while vision is
  still in progress; delivery develops against recorded fixture JSON. The cost is that a modelling
  mistake in M0 is expensive to correct later.

## ADR-009 — Tesseract OCR, explicitly non-load-bearing
- Date: 2026-08-18
- Status: accepted
- Context: Control numbers give the points under the common rogaine convention (first digit = value).
  Reading two digits from a map is the most fragile step in the pipeline. EasyOCR pulls in torch; a
  VLM costs money and determinism.
- Decision: Tesseract from the Docker image, with a confidence per control. Unread numbers produce
  `points: null` plus a flag; the points rule can fall back to a constant, and CSV or viewer editing
  is a designed flow, not a repair hatch.
- Consequences: A system dependency in the image, and OCR quality never gates a route. If Tesseract
  proves too weak on map typography, a small digit-template matcher replaces it without touching any
  other module.

## ADR-010 — Real map corpus validates; synthetic fixture tests; neither is committed
- Date: 2026-08-19
- Status: accepted
- Context: The owner can supply 200+ scanned maps and a couple of `.ocd` files. Tests need exact
  ground truth and must run anywhere; real scans have no labels but carry the real distribution of
  map styles, printers and scanner colour shifts.
- Decision: Split the two roles. The synthetic generator (T004) stays the test fixture — exact
  labels, deterministic, in-repo, small. The real corpus (T005) is a validation set living in a
  gitignored `data/maps/`, driving T017's palette report and, later, M7's training data. A `.ocd`
  render spike (T006) may add a third, best-of-both artefact: a real map with symbol-exact masks.
  Sizing: 10-20 scans retire the palette risk; the full 200+ are for M7 only.
- Consequences: CI stays fast and self-contained, while the claim "this works on real maps" rests on
  real maps. The corpus is never committed, so results referencing it must be reproducible from the
  report artefacts rather than from the repo. If T006 succeeds, some synthetic-fixture assertions get
  a stronger real counterpart; T004 is not removed either way.

## ADR-011 — Control ink is a configured list of hue bands, not a fixed purple; the default ships both purple and red
- Date: 2026-09-02
- Status: accepted
- Context: Iteration I1. `vision/controls.py`'s detector matched only the ISOM purple hue band
  (F7's original text). A real scan the owner tried had every control hand-marked in red — a
  different ink family, not a white-balance-shifted purple — and `detect_controls` returned zero
  controls and no hub. `web/app.py` calls `load_config()` with no path argument at every one of its
  three use sites (grep-confirmed); there is no per-run config override anywhere in the web viewer,
  so an opt-in-only fix would never reach the interface the owner actually hit this on.
- Decision: `DetectorSettings.purple_hue_range: tuple[int,int]` becomes `ink_hue_ranges:
  list[tuple[int,int]]`; `purple_mask` unions the mask across every configured band. The *shipped*
  `config/default.toml` carries both the existing purple band and a new red band (measured against
  the real scan, not guessed) — not an opt-in the owner would have no way to reach from the web
  viewer. The existing shape gate (Hough circle fit + ring-coverage ≥ 0.75, T020) is the actual
  false-positive guard and is unchanged; widening the colour band alone does not manufacture false
  controls out of stray red pixels that aren't circular.
  Deferred out of this iteration: fully adaptive/arbitrary ink-colour detection — no real corpus
  exists yet to tune or validate a general approach against (same M7 data blocker as T017), so this
  is bounded to the two ink families actually observed rather than solving a problem with no
  evidence of its true shape.
- Consequences: `tests/unit/vision/test_controls.py::TestPurpleMask::test_rejects_a_saturated_non_purple_colour`
  no longer holds for red under default config and is rewritten to assert against a colour still
  genuinely outside both configured bands. `render/overlay.py`'s route colour, chosen specifically
  because no ISOM ink is red, must change too (its own module docstring's stated invariant would
  otherwise silently break for red-ink maps) — a new constant, verified distinct from all seven
  now-forbidden inks via `cmyk_to_srgb`, not eyeballed. A map that happens to use red ink for
  something other than controls is a new, real, currently unmeasured false-positive class; the
  shape gate is the mitigation, not a colour-threshold retune.

## ADR-012 — Grid/annotation ink is excluded from colour classification by shape, not by narrowing the colour threshold
- Date: 2026-09-02
- Status: accepted
- Context: Iteration I1. The same real scan's magnetic-north/grid lines (thin, solid, full-height
  verticals — a standard ISOM/orienteering-map convention) read close enough to the water reference
  colour that `vision/segment.py` classified five full-height columns as `water_uncrossable`
  (speed_factor 0.0), slicing the routable graph into disconnected strips and producing
  "no reachable route" for a hub/control pair 600m apart with no real barrier between them.
  SPEC's own Risk #2 already names this class of defect ("map text and symbols pollute the terrain
  classes") and its established mitigation (shape/size filters, `vision/linear.py`'s T014
  precedent) — this is that same failure mode showing up in a colour class T014 never touched
  (`road`), not a new category of problem.
- Decision: A new shape-based pass, positioned in `segment()` right after `classify_palette`
  alongside `extract_linear_features`, reclassifies extreme-elongated components of
  `water_shallow`/`water_uncrossable` that span most of the image's height or width to `unknown`
  (`config/default.toml`'s existing conservative "assume forest" fallback, speed_factor 0.35) rather
  than narrowing the water hue/saturation thresholds. Rejected alternative: tightening the water
  colour range to exclude this particular blue — T017's own findings (cited in `docs/STATUS.md`)
  already warn that hue thresholds are measured against one map's printing, and moving one without a
  real corpus to check against risks trading this false positive for a different one on a different
  scan, with nothing to catch it.
- Consequences: A real lake still classifies as `water_uncrossable` (compact, not extremely
  elongated) — the fixture's existing IoU floor is the regression guard, unchanged. New,
  currently-untested edge: a genuinely long, thin real water feature (a river) sitting close to the
  same elongation threshold could misclassify to `unknown` (passable, `speed_factor` 0.35, instead
  of correctly impassable); no such feature exists in the synthetic fixture or the one real sample
  to check against, so this is named here rather than silently accepted. Full validation against a
  larger real corpus stays blocked on the owner (M7, `docs/STATUS.md`'s "Blocked on the owner"); this
  iteration fixes the one confirmed failure mode, it does not close that blocker.

## ADR-013 — Track-derived travel-cost calibration from o-gps-center GPS tracks (proposed, not started)
- Date: 2026-09-02
- Status: proposed — no task exists for this, nothing implemented, revisit only if the owner
  chooses to invest beyond M7.
- Context: While scoping T070's corpus source (o-gps-center.ru, see the M7 corpus-harvest work this
  session), two more open, unauthenticated endpoints were found: `/viewer/event/{id}/competitors`
  (roster: id, trackId, name, bib, start time — no score/place/result field on any of 4 events
  checked) and `/viewer/viewer_tracks?track_{id}=0` (a competitor's full raw GPS track: dense
  `{t, lat, lon}` points). The owner's idea: rogaine fields skew toward experienced navigators, so
  where many competitors' tracks converge between two controls, that convergence marks a good route
  choice — aggregate crowd tracks as a free proxy for route quality.
- What this would actually feed: not the Orienteering Problem solver (control selection/order is a
  scoring decision tracks can't inform — different runners run different subsets by strategy, not
  comparably). It targets the travel-cost model instead — the terrain-coefficient and slope-penalty
  side of ADR-002/ADR-006 — as a calibration or validation signal for `config/default.toml`'s
  numbers, which are currently reasoned/researched rather than measured against real movement.
- Open problems, why this isn't a task yet:
  1. **Confounded density.** Convergence at a forced bottleneck (single bridge, gap in a fence) is
     not evidence of a good route, just the only route. Pack-following (visually trailing whoever is
     ahead) also produces convergence unrelated to independent route judgement. Raw overlap density
     needs both effects filtered out before it means anything — at minimum, restrict analysis to
     corridors where the terrain genuinely offered a choice, and ideally weight by pace/independence,
     neither of which the site's data exposes directly.
  2. **No skill signal.** The site returns no result/place/score field (checked across 4 events
     including a national championship) — there is no way to isolate strong navigators from
     beginners sharing the same open start. Pace on unambiguous terrain is the only available
     surrogate, itself unvalidated.
  3. **No georeferencing.** Tracks are WGS84 lat/lon; the pipeline is pixel-space only (ADR-007, out
     of scope for v1). A per-map affine calibration is needed before a track can be overlaid on our
     raster at all. Candidate bootstrap, not yet tried: match a track's near-zero-speed "punch" dwell
     points, in visiting order, against this project's own pixel-space control detections
     (HSV+Hough) to get calibration point pairs semi-automatically — cheaper than manual calibration
     per map, but unproven.
  4. **Personal data.** Unlike anonymous map scans, tracks carry real names, bib numbers and start
     times — a step up in sensitivity from the T070 map corpus; worth the owner's explicit sign-off
     before any bulk collection, separate from the map-harvest approval.
- Decision: none. Not scheduled under any milestone. If pursued, it needs its own ADR superseding
  this one (with a real decision on the georeferencing bootstrap and the skill-filtering method) and
  does not belong under M7 (M7 is visual segmentation, T070-T072; this is travel-cost calibration,
  unrelated code paths).
- Consequences: none yet — nothing implemented, no task created, no corpus collected.

## ADR-014 — o-gps-center.ru scraped maps supplement ADR-010's owner-corpus premise
- Date: 2026-09-02
- Status: accepted — owner approved continuing the harvest 2026-09-04, explicitly targeting ~200
  maps for T070 (M7's training corpus), beyond the 10-20 that alone would retire T017's palette
  risk. A harvester agent was dispatched the same session to sweep further (see docs/STATUS.md).
- Context: ADR-010 assumed "the owner can supply 200+ scanned maps"; only 15 exist (see
  docs/STATUS.md "Blocked on the owner"). A second, free source is available: o-gps-center.ru
  publishes a participant-facing scanned map per event, plain HTTP GET, no auth, no JS. Its
  `robots.txt` disallows crawling the `/viewer/?event_list...` search listing but explicitly
  `Allow`s `/viewer/event/{id}/` — a compliant harvester therefore walks bare event IDs (~26,000
  total across the whole platform, all sports, not rogaine-specific) and keeps only pages whose
  title matches «рогейн», downloading that page's map link. Verified this session: responses are
  plain `image/jpeg`, one download was opened and visually confirmed as a real ISOM rogaine map
  with control circles and a legend.
- Decision (proposed): treat this scrape as a second, cited (not committed) input to T070's
  corpus, alongside the owner's own scans — same `data/maps/<id>/` contract, no `meta.toml`
  fabricated (scale/DPI stays unknown until measured or calibrated, same rule as ADR-010). A
  manifest (`data/maps/_ogps_harvest_manifest.csv`) records `map_id, event_id, event_title,
  source_url, downloaded_at` for attribution and reproducibility. Harvesting is resumable
  (`data/maps/_ogps_harvest.py`, checkpointed by last event ID checked in
  `data/maps/_ogps_harvest_checkpoint.json`) rather than one-shot, since a full sweep is several
  hours at a polite ~0.4s/request rate limit.
- Consequences: this is scraped third-party content, not owner-supplied — course setters, not this
  project, hold rights to each map. Treated as fine for internal, non-redistributed
  validation/training input (same non-commit rule as the owner's own scans; ADR-010's rasters are
  never in git either), but publishing or redistributing any harvested map would need separate
  clearance from its original author — the manifest's `source_url` exists so that clearance, or a
  takedown, is always traceable to one map. Sizing math is unchanged: 10-20 real scans still retire
  the palette risk (T017); 200+ (for M7) needs either a much longer sweep of this source or
  another one entirely. Not run to completion — 1 map harvested as a timeboxed sample
  (`ogps-367_180afd874454c167cddab2aa89c78354`, "Рогейн-2015"); the owner decides whether/how much
  further to run it.

## ADR-015 — Control-circle/hub detection sweeps multiple size scales, not a fixed ISOM print size
- Date: 2026-09-04
- Status: accepted
- Context: Iteration I1, following ADR-011. T073 fixed control-ink *colour* on the real scan
  (`data/maps/grid-lines-red-controls/map.jpeg`) but `detect_controls` still finds no real
  controls: `circle_radius_px(dpi)` predicts a Hough radius window from ISOM's fixed 6mm
  printed-circle spec, but this file's hand-drawn circles measure ~56px radius at 200dpi — ~2.37x
  the predicted window — so every raw Hough detection is a false positive on hand-written digit
  glyphs instead (recall 0/13, precision 0/16, hub not found; independently measured, confirmed not
  a DPI-metadata bug via PIL JFIF `jfif_unit=1`, see docs/STATUS.md).
- Decision: `DetectorSettings` gains `circle_scale_multipliers: list[float]` (shipped default
  `[1.0, 1.5, 2.0, 2.5, 3.0]`, measured against the real scan's ~2.37x ratio). `_detect_circles`
  runs its existing Hough search once per multiplier against the scaled radius window, gating every
  candidate through the existing, unmodified ring-coverage check (same threshold, same band
  fraction, applied per scale — never weakened). `_detect_hub_triangle` similarly sweeps the same
  multiplier list for `expected_side`, picking the single best match across scales by normalised
  relative error.
  **Landed mechanism differs from this ADR's first draft** (which proposed pooling every scale's
  passing circle candidates and reducing them with cross-scale non-max suppression): implementing
  and measuring that against the real scan found it insufficient — `detect_controls` reached
  recall 1.000 but precision only 0.448 (29 detections, 16 false), because the pre-existing
  base-scale false positives on hand-written digit glyphs (T073's own documented, unfixed problem)
  each individually clear the *same* 0.75 ring-coverage floor a true ring does; no per-candidate
  threshold, however tuned, separates the two, since NMS only ever collapses duplicates of the
  *same* physical ring across scales, not distinct false features at a different scale. What
  actually separates them, measured directly: the true scale's candidates clear ring-coverage far
  more convincingly *on average* (real scan: ~0.99 mean coverage at the correct scale vs. ~0.88 at
  the false-prone base scale, every individual candidate on both sides still ≥0.75). `_detect_circles`
  therefore computes each multiplier's candidates and their mean coverage, then keeps only the
  single best-scoring multiplier's candidates — comparing scales as *sets*, not individual
  candidates. `1.0` stays first in the sweep, so on the synthetic fixture (printed at exact ISOM
  scale, the only scale with any candidates at all there) the returned set is unchanged from before
  this task. Selecting one scale also makes cross-scale duplicate-counting structurally impossible,
  so the separate NMS step is no longer needed.
  **Second amendment, from independent review before this landed:** scoring by raw mean coverage
  alone, with ties broken toward the smaller multiplier, has its own failure mode — `_ring_coverage`
  saturates at exactly `1.0` for *any* candidate sitting inside a solid ink blob, not only a
  genuine ring, so two scales tying at a perfect mean is the normal case, not a rare edge case, and
  the tie-break then always favours the (often wrong) smaller scale. Demonstrated, not theorised: a
  synthetic map with five true rings at multiplier 2.5 plus one incidental filled purple blob at
  multiplier 1.0 lost all five true rings to the one perfect-mean decoy under the mean-only rule.
  Fixed by scoring `(mean coverage bucketed to a tolerance, candidate count)` instead — a
  meaningfully higher mean still wins outright, but among scales close enough to call a tie, the
  one with more corroborating candidates wins, since a real map's true scale finds many consistent
  circles and a lucky false positive finds one. `TestOversizedRingsBeatABaseScaleDecoy`
  (`tests/unit/vision/test_controls.py`) is the permanent regression test; the real scan's own
  selection is unaffected (still multiplier 2.0, mean 0.9943, 13/13 recall and precision).
  Known limitation of the landed design, not fixed here: it still assumes one map uses one
  hand-drawn circle scale throughout, and the count-based tie-break only protects against a tie
  against *few* false candidates — a wrong scale producing *many* same-bucket false fits (more than
  the true scale's real candidate count) would still win. No evidence of either case exists in this
  project's corpus to design or test against further. `_detect_hub_triangle` was left on its
  original per-candidate normalised-error rule rather than given the same set-level treatment — a
  hub is a single expected symbol, so there is no "many corroborating candidates" signal available
  to weigh in the first place; review specifically tried to break it with a base-scale decoy
  triangle and could not (the true hub still won, 0.996 confidence).
  Rejected: a single widened Hough window spanning both scales — the literal repeat of T073's own
  failure mode, since digit-glyph- and true-ring-scale candidates would then compete inside the same
  Hough call and the same `minDist` instead of being judged independently per scale; a manual
  per-map size override — needs new config-override plumbing to reach the web viewer (no per-run
  config path exists, per ADR-011's own grep-confirmed finding) and does not generalise past one
  manually-measured map, the same objection ADR-011 raised against an opt-in colour override.
- Consequences: `vision/ocr.py::_ocr_crop` still sizes its number-search crop from
  `circle_radius_px(dpi)` at the base scale only (`Control` carries no matched-scale/radius field)
  — OCR on a control found at a non-1.0 multiplier will crop the wrong window size. Flagged and
  filed as T077 (docs/TASKS.md), not fixed here. `detect_controls` now runs Hough multiple times
  per image (once per configured multiplier) — measured on the real scan (1708x2379): 0.05s before
  this task, 0.24s after (4.45x), a real but small absolute cost; no NFR names a detection-time
  ceiling.

## ADR-016 — Per-map best-effort auto-calibration for the M7 training corpus; scale is secondary to content recognition there
- Date: 2026-09-04, revised and **accepted 2026-09-05** (`утверждаю`)
- Status: accepted. Superseded its own first draft same-session: the original version made a
  correctly-calibrated scale bar the *gate* (uncalibratable maps excluded from T070's corpus). The
  owner overrode that after seeing real corpus numbers (below): auto-calibration is now explicitly
  **secondary** to T070's real goal — the 204 scraped maps exist to improve *object/content*
  recognition (controls, terrain classes), not to produce distance-accurate output. Rationale in
  the owner's own words: "Карты изначально скачивались для улучшения распознавания самого
  содержания карт... автоопределение масштаба это второстепенная задача... Масштаб всегда может
  скорректировать и задать пользователь" — a real end user's own map is calibrated through the
  existing manual path (SPEC F3, `io/scale.py::Calibration` — pick two points, enter the true
  distance), unaffected by anything here. Also noted: each organiser draws their map somewhat
  differently (inconsistent circle sizes, grid conventions, legend styles), so no single automatic
  signal was ever going to reach the whole corpus — confirmed empirically below.
- Context: the harvest (ADR-014) reached 204 scraped maps, clearing T070's volume blocker, but
  every one of them still lacks `meta.toml`. `dpi` is not purely cosmetic even for training-mask
  generation: `vision/controls.py`, `segment.py`, `linear.py` and `contours.py` convert this
  project's mm-based ISOM print-size tunables to pixels through it, so the heuristic
  palette-classifier masks T070 exports do depend on it, if only loosely (ADR-015's multi-scale
  sweep already buys some tolerance to an approximate value). Checked before designing further —
  **the article this project follows for M7 (habr.com/ru/articles/1065342/) does not cover scale
  calibration at all**: its own SegFormer training works purely in pixel space (`image.jpg` +
  `channels.npy` tiles, no real-world units), real distance appearing only in its separate
  travel-cost/speed model — the same separation this project already keeps between `segment.py`
  and `io/scale.py`. Also checked: JFIF `dpi` metadata survives in 127/204 scraped JPEGs but mixes
  real scanner presets with image-editor defaults (72/96, 44 files) indistinguishably — not
  trustworthy alone, and a rendering artefact possible for the sub-population of these maps that
  turn out to be OSM-rendered digital exports rather than physical scans (seen in the visual
  sample, not universal).
  **Corpus survey** (crude heuristics, random sample of 40/204, throwaway scripts —
  `data/maps/_survey_calibration.py`, `_survey_grid_color.py`, gitignored): OCR-detected scale-ratio
  text ("1:20000"-style) 8/40 (20%, some garbled); regularly-spaced grid/magnetic-north-style lines
  4/40 (10%, grayscale Hough) to 6/40 (15%, blue-channel-aware — the better estimate); both signals
  together on the same map 1/40. No graphical scale bar (a labelled ruler, as opposed to a bare
  ratio) was confirmed in the sample at all. Net: an auto-detector chasing only trustworthy,
  cross-validated signals would calibrate on the rough order of a quarter to a third of the corpus
  at best — a real number, not a guess, and the reason the owner chose to stop optimising this path
  further rather than sink more design time into raising it.
- Decision: T078 builds one lightweight, best-effort layered detector, tried in this priority order
  per map (reusing `io/scale.py::Calibration` throughout — no new maths):
  1. printed graphical scale bar (rare per the survey, but most trustworthy where found — its
     pixel length against its own printed labels needs no assumption about grid/scale convention);
  2. coordinate/magnetic-north grid spacing (`grid` ink, ADR-012), **only** accepted when
     cross-validated against an OCR'd scale-ratio text on the same map (grid alone cannot
     distinguish a real coordinate grid at a known interval from magnetic-north lines drawn at an
     arbitrary spacing for visual clarity — the risk the first draft of this ADR missed);
  3. control-circle diameter (`config.circle_diameter_mm`, reusing ADR-011/012/015's existing
     detection) as a **fallback/cross-check only, never primary** — organiser-to-organiser
     variance in hand-drawn circle size makes it too unreliable to trust standalone, per the
     owner's own instinct, and per ADR-015's already-documented limitation ("assumes one map uses
     one hand-drawn circle scale throughout").
  When none of the three yield a confident value (expected majority of the corpus, per the
  survey), the map is **not excluded**. It gets a real `meta.toml` with an assumed default —
  `dpi`/`scale_denominator` set to the median of whatever this session's successful measurements
  turn out to be (a data-informed default, not an arbitrary pick) — and an explicit
  `calibration_source = "assumed_default"` field, versus `"measured"` for the maps calibration
  actually succeeded on. This is a deliberate, scoped, owner-approved exception to ADR-010/014's
  no-fabrication rule, narrowed specifically to this internal M7 training corpus: never presented
  as measured fact, machine-distinguishable from real calibration via `calibration_source`, and
  with zero effect on the production/user-facing path (a real user's own map still requires actual
  calibration to be `is_plannable`, per `io/corpus.py`, completely unchanged by this ADR).
- Consequences: T070 still depends on T078 (order in M7 unchanged) but T078's scope is now
  bounded — one detector pass, no chase for ever-higher auto-calibration coverage. Forward note,
  not scoped here: the owner's stated next milestone beyond M7 is relief/terrain recognition (real
  elevation from contour spacing), which ADR-006/007 currently exclude from v1 — that future work
  will need real `meters_per_pixel`, not the assumed-default fallback this ADR introduces, so
  `calibration_source` exists precisely so that future work can filter to `"measured"` maps only
  rather than re-deriving this distinction from scratch.

## ADR-017 — Upper bounds on `RunConfig`'s numeric fields (S-001)
- Date: 2026-09-05
- Status: accepted
- Context: docs/REVIEW.md's S-001 (Medium, security): `SegmentRequest.dpi` (`web/app.py`) and
  `RunConfig.time_limit_s`/`heuristic_time_budget_s`/`alternatives` (`models.py`) validate a lower
  bound only. An extreme `dpi` on a PDF drives `pdfium.render(scale=dpi/72)`
  (`io/raster.py::load_raster`) toward an arbitrarily large bitmap allocation *before*
  `MAX_DECODED_PIXELS`'s own cap ever runs (that check is post-decode) — the resulting
  `MemoryError` isn't `ValueError`/`OSError`, so the background workers' narrow `except` clause
  didn't catch it and the job hung at `status: "running"` forever instead of erroring. `models.py`
  is a frozen contract (ADR-008): changing `RunConfig` needs its own ADR.
- Decision: Add `le=` upper bounds — `dpi` 2400 (`web/app.py`'s `SegmentRequest`, not frozen, no
  ADR needed for that half), `time_limit_s` 86400 (24h), `heuristic_time_budget_s` 600 (10min),
  `alternatives` 20 — all judgement calls, generous enough that no real run ever hits them, tight
  enough to keep a single request's resource use bounded. Widen the three background workers'
  `except (ValueError, OSError)` to bare `except Exception` (REVIEW.md's own suggested fix) rather
  than enumerate more exception types one at a time — a job that fails for *any* reason should
  reach the client as `status: "error"`, never hang at `"running"` forever.
- Consequences: Rejects a `dpi`/time/`alternatives` value above these ceilings at the API boundary
  (422) instead of deep inside a worker; an unexpected failure of any kind now surfaces to the
  client rather than only `ValueError`/`OSError` ones. No behaviour change for any value already in
  range — every existing test, fixture, and the M7 corpus run stay within bounds.

## ADR-018 — Ink-hue false-positive rate is tightened by measurement; the red band is narrowed, not removed
- Date: 2026-09-05
- Status: accepted
- Context: Iteration I2. Owner bug report ("не видит цифры контролей ... вообще, а контроли
  распознает ... неправильно"), reproduced on all 13 of the owner's own scans
  (`docs/iterations/I2-real-scan-detection-failure.md`): `detect_controls` over-detects by 2x-10x
  and OCR reads ~0% of numbers on every one. Root cause measured on `ozero-shchuche/map.jpg`:
  `purple_mask` flags 6.82% of the image (3.5x `grid-lines-red-controls`' 1.93%, the file F7's
  floor is measured against); 88% of the masked pixels sit in `ink_hue_ranges`' red band (ADR-011),
  mean RGB `(161, 106, 90)` — a brownish contour-line colour, not control ink. Restricting the mask
  to the purple band alone drops detections on this file from 71 to 21. This is ADR-015's own
  documented caveat ("a wrong scale producing many same-bucket false fits ... would still win. No
  evidence of either case exists in this project's corpus") turning out to have evidence once the
  owner's own scans — never in the corpus ADR-011/015 were tuned or tested against — were run.
- Decision: Tighten the red band's discriminating power (exact mechanism — narrower
  saturation/value floor for that band specifically, and/or an added red-vs-brown check such as a
  minimum `R-G`/`R-B` channel gap — is an implementation-measured choice, not fixed here) rather
  than removing the red band outright. Removing it would silently regress `grid-lines-red-controls`
  (ADR-011's whole reason for the band existing: a real scan with every control hand-marked in
  red). The two existing real-scan assertions this must keep clearing are the actual specification:
  `TestRealScanRedInk::test_purple_mask_flags_the_real_red_ink` (>=95% coverage of the strict-red
  ink on `grid-lines-red-controls`) and `::test_recall_and_hub_match_the_true_positions`
  (recall/precision >=0.90, hub found, same file). If one measured threshold cannot satisfy both
  that floor and a materially lower false-positive rate on the owner's other scans, that is a
  finding for the owner, not a reason to quietly loosen either assertion (I2's "Expectations that
  change: none").
- Consequences: `config/default.toml`'s `[detector]` gains whatever new/adjusted keys the
  implementation needs (`DetectorSettings` is `extra="forbid"`, so a stale local config with only
  the old keys will fail loudly, not silently ignore the new ones — same migration story as
  ADR-011's own `ink_hue_ranges` rename). `_select_best_scale` and `_detect_hub_triangle` are downstream of
  `purple_mask` and are re-measured against the tightened mask (T080, T081) rather than assumed
  fixed by this change alone — the hub-triangle failure on `ozero-shchuche` was independently
  confirmed to persist even under a mask restricted to the pure purple band, so it has its own,
  separate cause.

## ADR-019 — The owner's real-scan corpus stays spot-checked, not a full labelled ground-truth set, this iteration
- Date: 2026-09-05
- Status: accepted
- Context: Iteration I2's intake asked how to define "fixed" with no ground-truth CSV for any of
  the owner's 13 real scans. Producing hand-labelled `(x, y, number)` ground truth for all 13 —
  the only way to compute exact recall/precision the way F7's fixture and
  `grid-lines-red-controls` do — is a distinct, disproportionate effort next to fixing the
  detection defect itself, and ADR-010 already established that these rasters are validation input,
  never a committed test fixture.
- Decision: Acceptance for this iteration is the owner manually reviewing 2-3 of their own maps
  (CLI output and/or the viewer) post-fix and confirming the result looks right by eye — not a new
  automated floor across the full 13-map corpus. `grid-lines-red-controls` (the one owner scan that
  already carries a `meta.toml` and hand-verified ground truth) remains the only real scan with a
  numeric recall/precision assertion in the suite.
- Consequences: A regression on one of the 10 real scans without a spot-check is not
  automated-test-visible; it would surface the same way this bug did — an owner running their own
  map and getting a wrong answer. `docs/TASKS.md`'s M7 gate ("owner runs their own map through both
  CLI and viewer and accepts the route") is exactly this same open Launch-checklist item — this
  iteration is a direct attempt to clear it, not a separate track.

## ADR-020 — `Control` carries the matched scale's nominal circle radius, so OCR can size its crop from it
- Date: 2026-09-06
- Status: accepted
- Context: T076/ADR-015 made control-circle detection scale-aware (`circle_scale_multipliers`), so a
  real, hand-drawn control can now be found at a size several times the ISOM base print size.
  `vision/ocr.py::_ocr_crop` still sizes its number-search crop and ring-erase disk from
  `circle_radius_px(dpi)` alone — the *base* scale, unconditionally — because `Control` (T020's
  output, `models.py`, frozen per ADR-008) carries no matched-radius field to size from instead.
  On a control actually found at a larger multiplier, the crop is too small for the digits it's
  meant to isolate; today this fails safe (`min_ocr_confidence` gates a bad read to `number=None`
  plus a flag, never a silent wrong guess, per ADR-009/F8) but is untested and unfixed at non-base
  scale — filed as T077 during the T076 review, pulled into this iteration (M9) because it shares
  `vision/controls.py` with T079-T081.
- Decision: Add one field to `Control`: `radius_px: float | None = Field(default=None, ge=0.0)` —
  `None` for the hub (a triangle has no radius) and for any control this project's own model
  creates other ways (e.g. a future manual edit). `_detect_circles` (`vision/controls.py`) computes
  this per Hough candidate and previously discarded it after `_ring_coverage` filtering; it is
  threaded through `_select_best_scale` (widening its candidate tuples from `(x, y, coverage)` to
  `(x, y, r, coverage)`) and into `detect_controls`'s `Control(...)` construction instead of being
  dropped. **`r` is the matched multiplier's own nominal mid radius (`(r_min + r_max) / 2` at that
  scale), not Hough's raw per-candidate fit — measured, not the first design tried.** Threading the
  raw fit through directly regressed `TestReadsNumbersOnFixture` on the clean synthetic fixture
  from 11/12 to 9/12: Hough's per-circle radius jitters roughly ±10% around the nominal mid-radius
  even at the base scale, and `_ocr_crop`'s crop-margin constants
  (`_CROP_MARGIN_FACTOR`/`_CIRCLE_MASK_RADIUS_FACTOR`) were tuned against the noiseless nominal
  value, not that jitter. Using the nominal mid radius instead removes the regression entirely and
  is bit-identical to `_ocr_crop`'s own pre-T077 fallback for any base-scale (multiplier 1.0)
  control, since that fallback already computed the same `(r_min + r_max) / 2` from
  `circle_radius_px(dpi)` — so this change is strictly additive: only a control matched at a
  non-base multiplier sees a different (correctly larger) crop. `_ocr_crop` (T077, not this ADR)
  uses `control.radius_px` when present, falling back to `circle_radius_px(dpi)`'s own mid-value
  for a `Control` where it's `None`.
- Consequences: `Control`'s JSON shape gains one optional key; every existing constructor call
  (fixtures, CLI, tests, the web layer) that doesn't pass `radius_px` keeps working unchanged
  (pydantic default `None`, `extra="forbid"` only rejects *unknown* keys, not missing optional
  ones). `web/app.py`'s `model_dump()` calls pick it up automatically. `io/controls_csv.py`'s
  `FIELDNAMES` is SPEC F9's own fixed, hand-editable column list (`id,x,y,number,points,
  confidence,source,is_hub`) and does not gain `radius_px` — it never needs to survive a CSV round
  trip, since `detect_controls` and `read_control_numbers` (T077) run back to back on the same
  in-memory list, before `write_controls` is ever called (`cli.py`'s `detect_cmd`/`route_cmd`).
  A `Control.radius_px` reader elsewhere in future should not assume it is the literal fitted
  circle edge — it is that scale's nominal size, deliberately smoothed of per-candidate fit noise.

## ADR-021 — Viewer layout becomes a fixed split view — map pinned, controls list independently scrollable
- Date: 2026-09-07
- Status: accepted
- Context: Iteration I3. Owner reported that assigning a control's number requires scrolling the
  page down, at which point the map (static, not pinned) scrolls out of view — no way to see which
  marker on the map corresponds to which row being edited. Confirmed structurally, not just by
  report: `.layout` (`style.css`) is a two-column grid whose right column stacks six `<details>`
  panels (map upload, scale, controls, run parameters, results, export) vertically inside a fixed
  380px column, with no `position: sticky`/independent scroll region anywhere; the controls table
  inside that same 380px carries seven `white-space: nowrap` columns, forcing an inner horizontal
  scroll that hides most of a row's values at once. Both are the direct mechanism of the reported
  bug, not a cosmetic complaint.
- Decision: Restructure `index.html`/`style.css` so the map viewport and the controls-list panel are
  both always in view without vertically scrolling either out of frame — the map column becomes
  independently positioned/sized against the viewport height rather than flowing with the rest of
  the page, and the controls panel gets its own scroll region sized to fit alongside it. Add a
  marker <-> table-row highlight/selection sync (new behaviour; none exists today) so it is visually
  unambiguous which point belongs to which list entry. `tests/e2e/test_viewer.py` gains an assertion
  that both regions' bounding boxes are inside the viewport at once.
- Consequences: A real (if scoped) structural change to markup and CSS that a later visual redesign
  (same iteration, different task, serialized after this one since both own the same files) builds
  on rather than reverts. The existing A11y non-functional requirement (keyboard-operable, focus
  visible, labelled, legible light/dark) is a hard constraint on the new structure, not something
  this ADR trades away. `ADR-005` (vanilla JS + Canvas, no build tooling) is unaffected — this is a
  layout/CSS change, no new dependency.

## ADR-022 — Auto-calibration is exposed as an opt-in path in the CLI and viewer, not only the M7 corpus tool
- Date: 2026-09-07
- Status: accepted
- Context: Iteration I3. The owner could not find anywhere in the product where scale
  auto-detection happens, despite `vision/calibrate.py::calibrate_map` (T078) already implementing a
  three-tier best-effort detector (scale bar -> grid -> circle diameter). Confirmed by reference
  search: `calibrate_map` is called from exactly one place, `calibrate_corpus`, itself only reachable
  from the M7 training-corpus tooling — neither `cli.py` nor `web/app.py` ever calls it. This is not
  a bug; it is ADR-016's explicit, owner-approved scope ("a real end user's own map is still
  calibrated manually... unaffected by this task") and SPEC's own `## Non-goals` line ("Automatic
  detection of the map's scale bar"). Re-asked directly this iteration: the owner wants the existing
  detector reachable from their own real-map workflow, understanding (from ADR-016's own corpus
  survey) that it will only fire on roughly a quarter to a third of real maps.
- Decision: Wire `calibrate_map` into both `cli.py` (a new `--auto-scale` flag, mutually exclusive
  with `--scale`/`--calibrate`, same three-way contract as today's two) and `web/app.py` plus the
  viewer's Scale panel (a third, explicit action alongside the existing ratio/calibrate options).
  Both report which tier fired (`scale_bar`/`grid`/`circle`) and the resulting mpp/dpi on success; on
  failure both give a clear "auto-detection unavailable, enter manually" outcome and let the existing
  manual paths complete normally — never a crash, never a silently guessed value, and auto-detection
  never runs or overrides anything without an explicit user action. `calibrate_map` itself is reused
  unmodified (or behind a thin single-image wrapper, if one is needed) — no new detection logic.
  SPEC gains F21 for this; the withdrawn Non-goals line is marked, not deleted, per this project's
  own documentation convention.
- Consequences: This narrows, but does not reverse, ADR-016 — the M7 corpus path (`calibrate_corpus`)
  is untouched, and manual entry (F2/F3) stays the default and the only load-bearing path (ADR-009's
  same non-load-bearing principle now applies to calibration as it already does to OCR). The
  real-world hit rate stays whatever ADR-016's corpus survey measured (~20-30%) — this ADR does not
  claim or require a higher one, only that the existing detector becomes reachable and honest about
  its own success or failure. CLI and viewer must report identically (a `Contract`-class change, per
  the iteration's impact map) so the two interfaces don't silently drift.

## ADR-023 — Real-scan OCR failure is dominated by leftover non-digit ink and ring-erasure undershoot, not crop framing
- Date: 2026-09-07
- Status: accepted
- Context: T083 (I3). T077 raised `grid-lines-red-controls` from 0/13 to 3/13 by sizing `_ocr_crop`
  from `Control.radius_px` instead of the base ISOM scale, but every other real scan stayed
  unmeasured. Measured `_ocr_crop`/`_read_digits` end to end (via `detect_controls` +
  `read_control_numbers`, the real pipeline call path, no re-implementation) against all 14
  raster-bearing directories under `data/maps/` that are the owner's own corpus (ADR-010), excluding
  `rfar2016-for-stroganov` (`.ocd` only, no raster) and the `ogps-*` o-gps-center.ru scrape
  (ADR-014, a separate supplementary set, not owner-supplied). `kkm-3-2020/map.jpg` and
  `ozero-shchuche/map.jpg` are byte-identical (matching sha256
  `d34e486b3fdcb8090f0028b2b065340cad70eff824a01462a2a64ca3712e44c9`, confirmed), so this is 13
  unique scans, matching the number already used informally — 416 detected non-hub circles total
  (395 across the 13 unique files).

  Per-map read rate (controls whose OCR met the shipped `min_ocr_confidence=0.6` floor, same
  criterion `read_control_number` uses):

  | Map | Read rate |
  |---|---|
  | toksovo-1 | 17/21 (81%) |
  | toksovo-zubry | 11/31 (35%) |
  | history-race-primorsk | 14/49 (29%) |
  | treugolnoe | 17/58 (29%) |
  | michurinskoe | 9/37 (24%) |
  | grid-lines-red-controls | 3/13 (23%, matches T077's own recorded baseline exactly) |
  | lembolovo-kkm | 3/20 (15%) |
  | kkm-3-2020 / ozero-shchuche (duplicate file) | 2/21 (10%) each |
  | history-race-2024-michurinskoe | 2/37 (5%) |
  | kkm-5-2020, kkm-toksovo, novo-kavgolovsky-lesopark, pervomayskoe | 0/21, 0/25, 0/21, 0/41 (0%) |

  Corpus-wide: 80/416 read (19%) — measurably above the "effectively 0%" impression the iteration
  doc opened with, but nowhere near acceptable, and four maps really are 0%. Of the 336 failures,
  280 (83%) are Tesseract finding **no text at all** (`digits == ""`), not a misread; the remaining
  56 (17%) recognised something but were rejected — 11 of those are 1-2 clean digits at confidence
  0.40-0.59, just under the 0.6 floor (e.g. `grid-lines-red-controls` control 11 reads `"60"` at
  confidence 0.43, matching the large `"60"` visibly printed on that control's own label in the raw
  crop); the other 45 are lower-confidence, mostly single-digit (27/45) reads consistent with
  partial/garbled recognition.

  Inspecting actual crops, masks and a drawn overlay of the erasure disk `_ocr_crop` uses
  (`r_mid * _CIRCLE_MASK_RADIUS_FACTOR`, throwaway script, not committed) against the true printed
  ring identifies three distinct causes behind the 280 empty reads, plus the 11-strong near-miss
  cluster as a fourth, smaller effect:

  1. **Leftover non-digit ink defeats `psm 7`'s single-line assumption, even when the crop is
     correctly framed and the ring is correctly erased.** `novo-kavgolovsky-lesopark` control 1: the
     ring-erased crop shows a clean, isolated "91" with no visible contamination near it, yet
     `_read_digits` returns `("", 0.0)` — a squiggly ink trail (a nearby shoreline/contour boundary
     whose anti-aliased edge pixels pass the configured hue/saturation/value floor) elsewhere in the
     482x482 crop is enough to break psm 7's "this whole image is one text line" segmentation.
     `kkm-toksovo` controls 1/5 show the same pattern quantitatively: ring erasure geometry matches
     the drawn ring almost exactly (overlay-confirmed), digits ("52"/"51") are legible by eye, but
     `ink_px_in_crop` is 8002 and 4120 against a ~1500-1700px baseline on maps that do read (contour
     line ink bleeding into the mask on this densely-contoured terrain). This is the single largest
     contributor by control count — nearly every plain `digits==""` result across every
     under-50%-reading map fits this shape (circle detected at high confidence, ring erasure
     geometrically correct, still nothing recognised).
  2. **The ring-erasure disk undershoots the real printed ring on some scans.** `pervomayskoe`
     control 5 and `kkm-5-2020` control 1: the overlay shows the true drawn circle extending visibly
     past the green `r_mid * 1.25` erasure disk — a full, unerased ring outline survives in the crop
     next to the digits (confirmed in both the raw ink mask and `_ocr_crop`'s own output, not just
     the overlay). Both maps read 0% across the board. `1.25` was tuned against the synthetic
     fixture's crisp vector rendering (T021); real JPEG scans widen a printed line's effective stroke
     via scan blur/compression, and/or `_select_best_scale`'s multiplier ladder
     (`[1.0, 1.5, 2.0, 2.5, 3.0]`) under-fits these particular scans' true print scale — T083 did not
     isolate which of the two dominates and flags this open for T084.
  3. **Circle false positives** (not an OCR bug — `vision/controls.py`'s domain, out of `ocr.py`'s
     files, noted for completeness): `kkm-toksovo` control 2's "circle" is the round Cyrillic letter
     "О" inside a map label ("К КОРОБКЕ"), confirmed by the raw crop showing only label text, no
     digit anywhere in reach; `pervomayskoe` control 32 centres on a "T"-shaped trail-junction
     symbol. `_read_digits` correctly returns nothing for these (ADR-009's contract holds — no false
     `points`), but they consume denominator slots that no OCR fix can ever raise.
  4. **`min_ocr_confidence=0.6` rejects some genuinely-correct reads on real scans.** 11 of 416
     controls (2.6%) recognised a clean 1-2 digit string at confidence 0.40-0.59 — e.g.
     `history-race-primorsk` control 37 reads `"58"` at 0.52, and `michurinskoe` alone has three such
     near-misses (`"38"` at 0.52, `"37"` at 0.49, `"47"` at 0.53) sitting alongside other controls on
     the same map that read the same-length numbers at 0.9+ — real-scan JPEG noise measurably
     depresses Tesseract's own confidence estimate below what the synthetic-fixture-tuned floor
     expects, even for what is very likely a correct read (no ground truth exists to confirm, per
     ADR-010/ADR-019).

- Decision: T084 should attack mode 1 first — it is the dominant cause (accounts for the bulk of the
  280 empty reads across every under-performing map) and is squarely `ocr.py`'s own code, unlike mode
  3. Concrete knobs, in priority order:
  1. Strip thin, low-area ink before handing the crop to Tesseract — a morphological opening (or a
     connected-component area/stroke-width filter) on the post-ring-erasure mask, sized so a 4mm-tall
     digit stroke survives but a hairline contour/boundary trace does not. This is the direct fix for
     mode 1 and does not touch crop geometry at all.
  2. Re-measure `_CIRCLE_MASK_RADIUS_FACTOR` against a real scan exhibiting mode 2 (`pervomayskoe`,
     `kkm-5-2020`), not just the synthetic fixture, and/or widen it conditionally when a full closed
     ring contour is still detectable in the post-erasure mask (a cheap contour-count check) — this
     targets mode 2 without letting the fixture's own already-tuned 11/12 regress.
  3. Once mode 1 is addressed, re-measure whether `min_ocr_confidence` still needs to sit at 0.6 or
     can drop slightly (e.g. 0.5) to recover mode 4's 11 near-misses — only after mode 1's fix,
     since a cleaner crop should itself raise confidence on genuine reads, and lowering the floor
     first (before cleanup) risks admitting more of the 45 low-confidence/garbage reads instead.
  4. Mode 3 (false-positive circles) is out of `ocr.py`'s scope for T084 (`vision/controls.py`
     territory) — record it as a known ceiling on any real-scan read-rate number T084 reports (a
     map with false-positive circles cannot reach 100% no matter how good OCR gets) but do not fold
     a detection-side fix into T084's DoD.
- Consequences: T084's fix must not regress the synthetic fixture's existing 11/12 floor
  (`test_at_least_eleven_of_twelve_controls_read_correctly`) — the fixture has none of mode 1's
  contour-line contamination or mode 2's oversized rings, so an ink-area filter or a widened erasure
  factor should be neutral there, but T084 must verify this rather than assume it. OCR stays
  explicitly non-load-bearing (ADR-009): an unreadable number still emits `points: null` plus a flag,
  never a guess, regardless of which of these fixes lands. T084's own before/after counts should be
  reported per-map in the same shape as this ADR's table, not just a single aggregate number, since
  the corpus is not uniform — a fix effective against mode 1 may leave the 0%-reading mode-2 maps
  unchanged, and that should be visible, not averaged away. This diagnosis rests on inspecting
  individual crops and one throwaway overlay script (not committed, gitignored under `data/maps/`)
  rather than a large labelled sample, so treat the three-mode split as directional — if T084's
  measured before/after does not follow the shape this ADR predicts (mode-1 fix moving the
  under-50% maps furthest), that is new information, not a contradiction to paper over.

## ADR-024 — `first_digit` points rule uses all digits but the last, not the literal first character; the viewer auto-fills points from the control number, editable
- Date: 2026-09-11
- Status: accepted
- Context: Iteration I4. `vision/ocr.py::_apply_points_rule`'s `first_digit` branch is
  `int(str(number)[0])` — the *literal first character* of the decimal string. This is silently
  wrong for any 3+-digit control number: rogaine convention (config/default.toml's own comment,
  "control 45 is worth 4 points") means the point value is every digit except the last one, which
  only coincides with "first character" for 2-digit numbers. Control 123 should be worth 12 points;
  the shipped code returns 1. `tests/unit/vision/test_ocr.py::TestPointsRule` only ever exercises
  the synthetic fixture's 2-digit control numbers, so this has never been caught by the suite.
  Separately, the web viewer's manual controls editor (`app.js`, `numberInputCell` for
  `control-*-number`/`control-*-points`) has never auto-derived points from a typed-in number at
  all — the two fields are independent inputs with no relationship, so every manually-entered
  control number requires separately typing its points too.
- Decision: `_apply_points_rule`'s `first_digit` branch becomes `number // 10` (integer division),
  matching the documented convention exactly for any digit count instead of only 2-digit numbers by
  coincidence. A single-digit control number (rare/atypical for this sport, no example exists in
  the corpus or the fixture) floors to `0` under this formula rather than returning the digit
  itself; treated as an accepted, documented edge case, not a reason to special-case digit count.
  The web viewer's control-number field gains the same computation client-side: typing/editing a
  control's number auto-fills its points field using the corrected rule. Per the owner's explicit
  answer this iteration, auto-fill is **sticky-off once touched**: the first manual edit to a
  control's points field marks it manually-set for that control, and further edits to the same
  control's number no longer overwrite points — matching how a human would expect a field they just
  corrected not to be silently reverted. A freshly detected/imported control (never manually
  points-edited) keeps auto-filling on every number edit.
- Consequences: `TestPointsRule`'s existing assertions are unaffected for 2-digit numbers (`45 // 10
  == int(str(45)[0]) == 4`), so no existing test's expectation changes; a new test covers a 3-digit
  number (123 -> 12) and the single-digit edge case (7 -> 0), both previously unspecified. The
  viewer's "manually-set" flag is per-control, in-memory client state (not persisted to
  `controls.csv`'s schema, F9) — reloading a run or re-importing a CSV resets it, which is
  consistent with the CSV import path already overriding detection wholesale (F9's "a hand-edited
  CSV overrides detection entirely").

## ADR-025 — The web viewer exposes the solver's existing top-K alternative routes, switchable, not only the single primary route
- Date: 2026-09-11
- Status: accepted
- Context: Iteration I4. F16 (`solve/alternatives.py::solve_alternatives`, `RunConfig.alternatives`,
  default 3) has computed top-K structurally distinct routes since M4 and `web/app.py`'s `/plan`
  handler has returned them under the response's `"alternatives"` key since that same landing — but
  neither `app.js` nor `view.js` ever reads that key. The viewer has only ever rendered the single
  primary `route`. The owner reports that when no route is a clear stand-out winner, seeing only one
  option hides a real, already-computed choice.
- Decision: the viewer keeps the primary `route` (from `solve_exact`/`solve_heuristic`) as the
  default selected/displayed route, and — only when a plan response's `alternatives` array has more
  than one entry — adds a row of switch controls (one per alternative, labelled by rank/score) above
  the route summary. Selecting one re-runs the existing client-side draw path
  (`view.setRoute`/`renderRouteResults`) against that alternative's `Route` object; no new server
  round-trip, since the full alternative routes (legs, polylines, scores) are already in the plan
  response. `route` and `alt_result.routes[0]` are two independently-run searches (main objective
  solve vs. the alternatives search) and are not guaranteed bit-identical, so the primary `route` is
  always its own, clearly-labelled first option ("основной") rather than assumed identical to
  `alternatives[0]`.
- Consequences: purely additive on the wire contract (the `alternatives` key already exists and is
  unchanged); `tests/unit/solve/test_alternatives.py`'s existing coverage
  (`TestKConfigurable`, `TestStructurallyDistinctAndRanking`, etc.) is untouched. New coverage is
  viewer-side only: an e2e case asserting the switch controls appear when `alternatives` has more
  than one route, are absent/hidden when it has zero or one (a map with only one feasible route),
  and that switching updates both the map overlay and the legs table without a new job/run id.

## ADR-026 — Control-number OCR scale-invariance work is diagnosis-first (T089), mirroring T083, not a speculative fix
- Date: 2026-09-11
- Status: accepted
- Context: Iteration I4. T084/ADR-023 raised corpus-wide read rate 19%→49%, but the owner reports
  many maps still fail to read clearly-legible numbers, specifically calling out that map *physical*
  scale (an A3 sheet vs. an A5 sheet photographed close-up, so printed features vary hugely in pixel
  size across the owner's own corpus) seems to matter. Two concrete, code-grounded hypotheses exist,
  neither yet measured against the corpus this iteration:
  1. `DetectorSettings.circle_radius_px(dpi)` derives the expected circle pixel size from `dpi`
     alone by design ("the map scale never enters into it" — the docstring's own words, correct for
     a flatbed scan at a known, correct DPI). For a *photograph* of a map, `dpi` is not a physical
     scan resolution — it is inferred (JFIF metadata, "found untrustworthy" per `docs/STATUS.md`'s
     T078 note: 72/96 checked values are indistinguishable from camera/editor defaults) or must come
     from auto-calibration (`vision/calibrate.py::calibrate_map`, T078), which ADR-022 made an
     **opt-in** action in both CLI and viewer, not the default. A map photographed close-up (so an
     A5 sheet fills the frame) and one photographed from further back (so an A3 sheet fits) can
     carry near-identical JFIF `dpi` while their controls' true pixel size differs by several times —
     if the owner is not invoking auto-scale/calibration explicitly, this alone would explain
     systematic misses correlated with physical map size, independent of any detector-quality bug.
  2. `DetectorSettings.circle_scale_multipliers` (default `[1.0, 1.5, 2.0, 2.5, 3.0]`) only sweeps
     circles at or *above* the base ISOM print size — there is no multiplier below `1.0`. A map
     whose controls render smaller than the base-scale window (e.g. a genuinely small-format print,
     or a correct-DPI scan where the base assumption itself runs slightly large) is structurally
     unreachable by `_select_best_scale` today, regardless of how well-tuned the rest of the pipeline
     is.
  Both are stated as hypotheses to verify, not assumed causes — this project's own established
  practice (T079-T081, T083) is to measure real scans before designing a fix, and T080 closed with
  no code change specifically because its assumed trigger did not reproduce.
- Decision: T089 measures `detect_controls`/`read_control_numbers` end to end against every raster
  in `data/maps/` (owner's corpus plus, budget permitting, a sample of the `ogps-*` harvest),
  bucketed by the map's resolved DPI and, where derivable, its approximate physical sheet size, and
  explicitly checks whether read/detection rate correlates with either hypothesis above or with
  neither. No product-code changes in T089 (script-only, gitignored, same convention as T083); its
  output is a measured diagnosis plus a fix design, written into a follow-up ADR, that T090
  implements against.
- Consequences: T090's actual scope (which of the two hypotheses, if either, drives a real fix; a
  simple default-on auto-calibration is one plausible outcome but not committed to yet) is
  deliberately left open until T089 reports. `TestRealScanReadRateFloor`'s existing floors
  (`pervomayskoe` >= 15/41, `novo-kavgolovsky-lesopark`'s own floor) must not regress; T090 raises
  them, or adds new per-map floors, using T089's own measured before/after numbers, not a guess.

## ADR-027 — Route-choice heuristics: a cheap-model literature pass feeds a human synthesis step before any cost-model code changes
- Date: 2026-09-11
- Status: accepted
- Context: Iteration I4. The owner is often unhappy with proposed routes' plausibility (e.g.
  cutting through slow/rough terrain where a real orienteer would obviously detour via a road) and
  asked specifically for a cheap-model pass over published route-choice advice from orienteering/
  rogaine practice, distilled into applicable rules. The existing cost model
  (`cost = mpp / (v_base * k_terrain * k_slope)`, F10) is pure physical-speed cost — it has no
  concept of navigation risk, handrails/catching features, or attack points, all of which real
  route-choice literature treats as first-order factors, not refinements.
- Decision: T094 runs a `general-purpose` subagent on the `haiku` model (the cheapest tier
  available) to gather and synthesize published route-choice material into
  `docs/research/route-choice-heuristics.md` — sources plus a distilled, if-then-shaped rules list,
  each flagged against whether this project's cost model already has a knob for it (terrain
  `speed_factor`, contour-density `k_slope`) or would need a new mechanism. The haiku output is
  treated as raw research material, not an approved design: a human/architect synthesis step
  (T094's own second half) selects which rules are both well-supported and cheaply encodable as
  cost-model tunables this iteration, and writes that selection as its own follow-up entry in this
  file before T095 touches any code. T095's scope is bounded to `cost/`/`solve/`-level tunables and
  config, explicitly not a solver-architecture rewrite (no new search algorithm, no route-choice
  ML/heuristic scoring model) — anything larger than that is out of this iteration's budget and
  becomes its own future item.
- Consequences: there is a real risk the literature pass surfaces good ideas that do not reduce to a
  config-tunable cost term (e.g. "prefer routes that pass attack points" needs a notion of attack
  points this codebase does not have) — T094's synthesis is expected to name those explicitly as
  deferred/future work rather than force-fitting them. T095's DoD is intentionally not fully
  specified at gate time (same pattern as T078's original filing): the owner reviews before/after
  example routes on a real map before T095 is considered done, not only a green test suite.

## ADR-028 — True terrain relief (elevation/DEM) integration is deferred; this iteration produces a research/options document only
- Date: 2026-09-11
- Status: accepted
- Context: Iteration I4. SPEC's own Risks & assumptions #3 already states the honest limitation:
  "Contour density is a proxy, not a slope. It cannot tell uphill from downhill, so route direction
  does not change cost. Accepted for v1." The owner now wants this actively worked toward — routes
  currently sometimes prefer a route that "ismarter" only because the model has no real slope
  signal — but also explicitly frames this as future preparation, not this iteration's
  implementation: "нужно изучить вопрос... подготовиться к дальнейшей реализации." Real elevation
  integration is a materially larger problem than a config tweak: it needs an elevation data source
  per map (a DEM API, contour-derived elevation reconstruction, or manual input), and — the sharper
  issue — a scanned/photographed orienteering map has no known real-world georeference by design
  (SPEC's own Non-goals line: "GPS georeferencing, GPX export, GeoTIFF, world files" is explicitly
  out of scope). Any DEM-based approach needs *some* way to align map pixels to real-world elevation
  samples, which is either a new georeferencing step (reopening that Non-goals line) or a
  contour-line-only elevation reconstruction that stays entirely inside the map's own pixel space
  (no external data, no georeferencing, but bounded by how much real elevation information printed
  contour lines actually carry — index-line labels, contour interval — versus the current
  density-only proxy).
- Decision: T096 produces `docs/research/terrain-relief-integration.md` only — no code, no new
  config fields, no SPEC requirement added this iteration. It must cover: realistic elevation data
  sources and their feasibility given the Non-goals constraint above; how a real slope signal would
  plug into the existing `k_slope`/`compute_cost_field` pipeline (`cost/field.py`) without breaking
  its current contract; what a separate, explicit off-road/forest base-speed parameter would need
  beyond the existing 17-class `speed_factor` table (`config/default.toml`); and the georeferencing
  tension above, stated as an open question for the owner rather than resolved unilaterally.
- Consequences: Risks & assumptions #3 gets a trailing note pointing at this ADR and the research
  document, not a rewrite — the limitation itself is unchanged this iteration, only the plan to
  eventually address it now exists in writing. Any future iteration that implements this needs its
  own gated delta, informed by T096's findings, and — if a georeferencing step is chosen — its own
  explicit reversal of the current Non-goals line via a superseding ADR.

## ADR-029 — T095 implements a linear-feature proximity bonus and slope-penalty retuning; attack points, catching-feature-specific numbers, vegetation fatigue, and pace segmentation are deferred
- Date: 2026-09-11
- Status: accepted
- Context: T094's second half verified every citation in `docs/research/route-choice-heuristics.md`
  against its source, fetching each directly rather than trusting the haiku-tier draft. The
  intake-time spot-check's suspicion was confirmed: `baoc.org`'s "Attack_Point" wiki page, cited for
  both Rule 2 (handrails) and Rule 3 (attack points), is a generic links directory that discusses
  neither — removed. A second source (Orienteering USA's "root cause" article, cited for Rule 4's
  core empirical claim) also did not hold up on direct fetch — replaced. Several specific numbers in
  the draft (a "~5 contour lines" climb/contour threshold, "5-10 seconds per control" safety-margin
  figure, "5-15 seconds per leg" catching-feature savings, "10-20% fatigue" late-event speed penalty,
  numeric pace-percentage bands for Rule 8) do not appear in any source checked and were removed as
  unsupported rather than left in place. Cross-checking the verified rules against this codebase's
  actual `config/default.toml` and `cost/`/`solve/` code (not just the draft's own claims about them)
  also surfaced two corrections to the draft's own "cost model mapping" judgments: Rule 1
  (path-vs-direct tradeoff) is not merely "expressible" via `speed_factor` — `cost/graph.py`'s
  8-connected grid Dijkstra already solves it exactly, more precisely than the literature's own
  60%-runnability rule of thumb; and Rule 5's vegetation-speed percentages are already faithfully
  encoded (`config/default.toml`'s own comments show the same "% of open-forest speed" arithmetic the
  source PDF gives). This means the owner's "routes cut through implausibly slow terrain" complaint
  (ADR-027's own framing) is not explained by either of those — it points at the missing
  handrail/catching-feature attraction instead (Rules 2 and 7).
- Decision: T095's concrete scope is a linear-feature proximity cost term plus a slope-penalty
  retune, both `cost/`-level config/mechanism additions, no solver-algorithm change:
  1. **New mechanism — linear-feature proximity bonus** (Rules 2 and 7, same mechanism): a
     distance-decay cost reduction near any linear feature already extracted by `vision/linear.py`
     (T014) — roads, tracks, footpaths — computed once as a distance-transform layer and folded into
     `cost/field.py`'s per-pixel rate alongside the existing `k_terrain`/`k_slope` factors.
     Config-tunable (decay distance, bonus magnitude), off by default until tuned against the corpus.
     This single mechanism covers both "prefer running near a handrail" (Rule 2) and "prefer a leg
     with an obvious catching feature beyond the control" (Rule 7) — the latter needs no separate
     code, only treating a control's nearby linear features the same way as en-route ones.
  2. **Retune — slope-penalty magnitude/shape** (Rule 6, penalty half only): `[slope].penalty`
     (currently `2.0`) and/or the density→penalty curve shape (linear → convex) in
     `vision/contours.k_slope`, re-tuned against the corpus so steep/dense contour crossings cost
     disproportionately more, consistent with the literature's "2-storey vs. 10-storey climb"
     framing. Existing knob, no new mechanism.
  3. **No change** for Rule 1 (already exactly solved by the existing Dijkstra solve) and Rule 5's
     speed half (already correctly calibrated) — T095 may add a regression test pinning current
     behavior for both, but no code/config change is expected.
  Deferred/future, named explicitly rather than force-fit:
  - **Rule 3 (attack points)** — needs a "which feature is this control's attack point" concept and
    backward-from-control route bias this codebase has none of. ADR-027's own anticipated example.
  - **Rule 5, fatigue half (vegetation fatigue carrying into later legs)** — needs
    path-history-dependent cost, which breaks the per-pixel cost field's path-independence assumption
    Dijkstra correctness relies on; a different solver treatment, not a config knob.
  - **Rule 6, directional half** (uphill vs. downhill, "contour around" vs. "climb over" as a real
    directional choice) — needs real elevation data; already ADR-028/T096's separate, already-deferred
    research track. T095 should not duplicate that work.
  - **Rule 8 (pace segmentation / traffic-light zones)** — not a cost-model rule at all; a
    viewer/UX pacing-advisory feature for a human runner, out of `cost/`/`solve/` scope entirely.
    Left for a future, separate task if the owner wants it.
  - **Rule 9, selection half** (which controls to visit within budget) — already solved by the
    existing exact/heuristic Orienteering Problem solvers (F12/F13); nothing to add.
  - **Rule 9, buffer half** (a rogaine time-safety-margin) is verified, cheap, and directly on-domain
    (this project is a rogaine planner, not generic orienteering) but is scoped as its own follow-up
    rather than bundled into T095, since it touches `solve/objective.py`'s budget semantics rather
    than `cost/field.py`'s per-pixel term, and needs its own owner-facing decision (does the margin
    apply by default, is it visible/editable in the viewer) that the two `cost/`-level items above
    don't.
  - **Rule 4** (navigation-risk-exceeds-optimization) is not separately implemented — it is the
    rationale for item 1 above, not an independent cost term.
- Consequences: T095's diff footprint is `cost/field.py` (new proximity term), `cost/graph.py` if
  the distance-transform needs a new `TerrainMap`/`CostField` field, `vision/linear.py` (expose
  corridor geometry for the distance transform if not already convenient), `vision/contours.py`/
  `config/default.toml` (slope retune), plus new unit tests and at least one before/after route
  comparison on a real map the owner reviews (ADR-027's own DoD: owner review of example routes, not
  only a green suite). Rule 9's buffer half and Rules 3/5-fatigue/6-directional/8 stay out of T095
  and need their own future task filings before any code is written for them — this ADR is not a
  commitment to build them this iteration or any specific future one.
- **Amendment, 2026-09-12 (owner sign-off, T095's own gate):** `[proximity].enabled` flipped
  `false` -> `true` in `config/default.toml` — the owner's explicit decision, made directly
  (not conditioned on further corpus tuning), confirmed after the before/after crop overlays
  already sent via `SendUserFile` (`data/maps/pervomayskoe`: -26.9% time for +17.5% distance,
  bending to hug a nearby footpath instead of cutting through terrain/contours). `decay_distance_m`
  and `bonus_magnitude` are unchanged, still the real-map best-effort starting point, not a
  corpus-validated final tuning. Five tests whose premise was "off by default" were updated to
  match, not left red or silently reverted: `test_proximity.py`'s `TestDisabledByDefault` split into
  `TestEnabledByDefault` (new shipped-default assertion) and `TestDisabledExplicitly` (the same
  off-path, now via an explicit override rather than the default); `test_field.py`'s
  `TestHandCheckedFormula` fixture now explicitly forces `proximity.enabled=False` so it keeps
  testing the base two-factor formula in isolation regardless of the shipped default;
  `TestProximityBonusIntegration`'s "default leaves seconds_per_pixel unchanged" test became
  "default applies the bonus", checked against the same three-factor formula `cost/field.py` itself
  computes. `tests/e2e/golden_route.json` regenerated (same script the test itself runs, same
  seed=8/n_controls=6/`--strategy exact`/`--seed 0` inputs): visit `order` and `points` (35)
  unchanged, `total_seconds` 10216.6 -> 9444.1 (-7.6%), consistent with the real-map example's
  direction and magnitude — not independently re-tuned, and not evidence toward a future numeric
  retune of `decay_distance_m`/`bonus_magnitude` themselves, which stays out of scope here.
  499 total pre-existing (5 failing on the flip alone, confirmed by running the suite with the
  config change but none of these test fixes first) -> 500 passed (3 tests edited in place, 1 net
  new from the `TestDisabledByDefault` split), `ruff check .` clean.

## ADR-030 — T089 diagnosis: H1 (DPI/calibration) is unsupported by the corpus; H2 (missing sub-1.0 circle-scale multipliers) is real for some maps, but the ring-coverage scorer can't safely act on it alone
- Date: 2026-09-12
- Status: accepted
- Context: T089 measured `detect_controls`/`read_control_numbers` end to end (real pipeline call
  path, no re-implementation — `data/maps/_t089_measure.py`, `_t089_h2_apples.py`, both throwaway
  and gitignored per T083/T084's own precedent) against the owner's full 14-directory corpus (13
  unique files — `kkm-3-2020`/`ozero-shchuche` are byte-identical, md5
  `effb08bbca48870b94dfad9a79bf6ee8`, same duplicate ADR-023 already documented) and the full
  204-directory `ogps-*` harvest (203 loaded; `ogps-5962_ee6127c2617fdb1199f49df1722d35f0` fails to
  load — `10258x14796 = 151,777,368px`, over `load_raster`'s 150,000,000px decompression-bomb cap,
  an unrelated pre-existing guard, not a T089 finding). Owner-corpus total reproduces T084's own
  49% baseline exactly: **205/416 (49.3%)**.

  **H1 (DPI/auto-calibration accuracy)**: not supported by either corpus.
  - Owner corpus: every map's `resolved_dpi` came from a successful JFIF probe (`probed_dpi ==
    resolved_dpi` in all 14 rows) — auto-calibration is never invoked here (ADR-022's opt-in default;
    these are the owner's own scans, "out_of_scope, never touched" per `docs/STATUS.md`'s T078 note).
    Read rate does not track the DPI value itself: the six `dpi=300` maps alone span 4%-81%.
  - `ogps-*` corpus (full 204-dir sweep, 203 measured, 10,343 circles): corpus-wide 2372/10343
    (22.9%). Every bucket sits in a narrow 17.6%-29.9% band, with no directional story matching the
    "physical-scale mismatch" hypothesis:
    | Split | n maps | circles | read | rate |
    |---|---|---|---|---|
    | `cal_source=measured` | 45 | 2844 | 683 | 24.0% |
    | `cal_source=assumed_default` | 158 | 7499 | 1689 | 22.5% |
    | `cal_tier=circle` | 35 | 1987 | 515 | 25.9% |
    | `cal_tier=grid` | 9 | 855 | 168 | 19.6% |
    | `cal_tier=scale_bar` | 1 | 2 | 0 | 0.0% |
    | dpi [0,150) | 61 | 3347 | 590 | 17.6% |
    | dpi [150,250) | 25 | 1561 | 414 | 26.5% |
    | dpi [250,320) | 110 | 5230 | 1318 | 25.2% |
    | dpi [400,∞) | 7 | 205 | 50 | 24.4% |
    | sheet [0,250)mm | 36 | 551 | 119 | 21.6% |
    | sheet [250,350)mm | 26 | 1256 | 376 | 29.9% |
    | sheet [350,450)mm | 25 | 1742 | 433 | 24.9% |
    | sheet [450,∞)mm | 116 | 6794 | 1444 | 21.3% |

    `measured` beats `assumed_default` by 1.5 points — noise-level, not the large effect ADR-026
    hypothesised. DPI and sheet-size buckets are non-monotonic (the best-reading sheet bucket is the
    *middle* one, not the smallest or largest). Auto-calibration accuracy is not the bottleneck this
    diagnosis can find; something else keeps the whole corpus in the low 20s regardless of
    calibration or scale.

  **H2 (`circle_scale_multipliers` has no entry below 1.0)**: real, but only for a subset of maps,
  and the existing selector cannot be trusted to find that subset unaided. `_t089_measure.py`'s
  extended sweep (multipliers 0.3-6.0, same `_select_best_scale`/`_ring_coverage` gate) found a
  different winning multiplier than production's `[1.0, 1.5, 2.0, 2.5, 3.0]` ladder on 7 of the 14
  owner maps. `_t089_h2_apples.py` then ran `read_control_numbers` against *both* candidate sets on
  all 7 (not just which multiplier the coverage scorer prefers — the actual OCR outcome, reusing
  `read_control_numbers` unmodified):

  | Map | production mult/n/ok | ext-selected mult/n/ok | centre overlap | mean radius Δ | verdict |
  |---|---|---|---|---|---|
  | kkm-toksovo | 1.0 / 25 / 1 (4%) | 0.85 / 25 / 8 (32%) | 25/25 (100%) | −5.3px | **EXT BETTER (+7)** |
  | lembolovo-kkm | 1.0 / 20 / 7 (35%) | 0.5 / 22 / 13 (59%) | 20/22 (91%) | −17.7px | **EXT BETTER (+6)** |
  | novo-kavgolovsky-lesopark | 1.0 / 21 / 6 (29%) | 0.5 / 23 / 16 (70%) | 21/23 (91%) | −35.4px | **EXT BETTER (+10)** |
  | history-race-primorsk | 1.0 / 49 / 17 (35%) | 0.5 / 53 / 7 (13%) | 48/53 (91%) | −17.7px | EXT WORSE (−10) |
  | kkm-3-2020 | 1.0 / 21 / 17 (81%) | 0.85 / 23 / 5 (22%) | 21/23 (91%) | −5.3px | EXT WORSE (−12) |
  | ozero-shchuche (dup) | 1.0 / 21 / 17 (81%) | 0.85 / 23 / 5 (22%) | 21/23 (91%) | −5.3px | EXT WORSE (−12) |
  | history-race-2024-michurinskoe | 2.0 / 37 / 13 (35%) | 0.4 / 3 / 0 (0%) | 0/3 (0%) | n/a | EXT WORSE (−13) |

  Totals across the 7: production 78/194 (40.2%) vs. ext-selected 54/172 (31.4%) — **naively
  widening the ladder and letting the existing scorer pick is a net loss of 24 correct reads**, even
  though it is a clear win on 3 of the 7 maps individually (+23 combined there). Two distinct
  mechanisms, both traced through code, explain the split:
  1. **Genuine undersized rings** (kkm-toksovo, lembolovo-kkm, novo-kavgolovsky-lesopark, 91-100%
     centre overlap with production's own candidates): these maps' hand-drawn control circles really
     are smaller than the base ISOM assumption predicts — the same phenomenon ADR-015 first measured
     (`grid-lines-red-controls`' circles at ~2.37x the ISOM print size; here it runs the other way).
     `circle_scale_multipliers`' missing sub-1.0 floor is a real, structural gap for these maps.
  2. **Same ring, wrong crop, worse OCR** (history-race-primorsk, kkm-3-2020, ozero-shchuche — also
     91% centre overlap, i.e. the *same* real rings production already finds correctly): forcing a
     smaller matched radius onto an already-correctly-matched ring degrades OCR, traced to
     `vision/ocr.py::_ocr_crop`: `half = r_mid * (1 + number_search_radius + _CROP_MARGIN_FACTOR)`
     shrinks the crop window, and `digit_height_px = number_font_height_mm * (dpi/25.4) * (r_mid /
     base_r_mid)` shrinks the expected-digit-size estimate `_strip_thin_ink` uses in lockstep — both
     mis-sized relative to the digits' true (base-scale) printed size. The candidate is right; the
     crop math built for a single matched scale is not being asked to generalise correctly.
  3. **A small false-positive cluster winning outright** (history-race-2024-michurinskoe, 0%
     overlap, only 3 ext candidates): exactly ADR-015's own documented failure mode — mean ring
     coverage saturates near 1.0 for a small blob cluster, letting it outscore a much larger genuine
     set — reproduced here at a smaller multiplier (0.4) instead of the larger one ADR-015 originally
     found it at.
- Decision: neither hypothesis alone explains the owner's complaint; H1 is not supported by measured
  data (drop it — do not make auto-calibration default-on off the strength of this diagnosis, the
  1.5-point `measured` vs. `assumed_default` gap does not justify it) and H2 is real but only
  actionable with a design change beyond "add more multipliers":
  1. **Extend `circle_scale_multipliers` with measured-justified sub-1.0 rungs** — `0.5` and `0.85`
     both won outright on real maps in this data; `0.4` is where the false-cluster failure mode
     appeared, so the floor should sit at `0.5`, not lower, absent further measurement.
  2. **Replace (or gate) pure ring-coverage scoring with OCR-outcome validation before committing to
     a sub-base-scale winner.** This diagnosis's own `overlap_stats`/`controls_from_candidates`
     helpers (`data/maps/_t089_h2_apples.py`) are a ready-made template: when the coverage scorer's
     preferred multiplier is below `1.0`, run `read_control_numbers` against both it and the
     production-ladder winner (bounded to two extra OCR passes, not one per multiplier) and keep
     whichever reads strictly more valid numbers. This is what would have picked correctly on all 7
     divergent maps in this data set, where coverage-alone scoring is wrong 4 times out of 7.
  3. **Re-verify `_CIRCLE_MASK_RADIUS_FACTOR`/`_CROP_MARGIN_FACTOR`/`_MIN_INK_AREA_FACTOR` across the
     matched-scale range**, not just the base scale — ADR-023 already flagged this as open for T084;
     this diagnosis reproduces the same undershoot/overshoot shape at non-base multipliers, so it is
     still open, now with a second, independent reproduction.
  4. The dominant cause of the corpus staying in the low 20s-50s regardless of DPI/calibration/scale
     is still most likely ADR-023's own mode 1 (leftover non-digit ink defeating `psm 7`) generalised
     across the wider corpus — T089 did not re-run that specific crop-by-crop inspection at `ogps-*`
     scale (out of this task's budget), so T090 should treat it as the leading remaining suspect, not
     a re-opened question.
- Consequences: `TestRealScanReadRateFloor`'s existing floors are compatible with this diagnosis's
  own numbers — `pervomayskoe` (`>= 15/41`) was not among the 7 divergent maps (H2 does not touch it)
  and `novo-kavgolovsky-lesopark` (`>= 5/21`, currently reading 6/21) is one of the 3 genuine H2
  wins measured here at 16/21 — T090 should raise this floor toward that number if its landed fix
  reproduces this diagnosis's own measurement, not guess a new value. `kkm-toksovo` (currently the
  worst owner-corpus reader, 1/25) and `lembolovo-kkm` are the other two concrete, measured targets
  T090's own before/after table should report against by name. This diagnosis rests on the owner
  corpus's 7 divergent maps plus a full (not sampled) `ogps-*` sweep for H1 — the H2 mechanism
  analysis (mask 1 vs. mask 2 above) is not exhaustively tested against `ogps-*` due to budget; if
  T090's landed fix does not reproduce the +23/-47 split measured here, that is new information for
  T090 to report, not a contradiction to paper over (same posture ADR-023 took toward its own
  three-mode split).

## ADR-031 — T090 fixes H2 with measured sub-1.0 `circle_scale_multipliers` rungs gated behind an OCR-outcome check; OCR crop-sizing constants are re-verified and left unchanged (no clean win found)
- Date: 2026-09-12
- Status: accepted
- Context: T090 implements ADR-030's three-point fix design against its own measured findings.
  1. **Sub-1.0 rungs**: `circle_scale_multipliers` gains `0.5`/`0.85` (config/default.toml),
     ADR-030's own measured floor — `0.4` is where a false-positive blob cluster won outright on a
     real scan, so it stays excluded.
  2. **OCR-outcome gate**: `vision/controls.py::_detect_circles` now checks whether
     `_select_best_scale`'s winner sits below multiplier `1.0`; if so, `_ocr_gate_sub_base_scale`
     runs `read_control_numbers` (unmodified) against both the sub-1.0 candidate set and whatever
     `_select_best_scale` would pick from the >=1.0 (production) subset alone, and keeps whichever
     reads strictly more valid numbers — ties (including both reading zero) fall back to production.
     Bounded to at most two extra `read_control_numbers` passes (one per candidate set), only paid
     when a sub-1.0 candidate would otherwise be chosen blind, on top of the pipeline's own later
     OCR pass over whichever set is finally returned. This is exactly ADR-030's own
     `_t089_h2_apples.py` technique, promoted from a throwaway diagnostic into the shipped code path.
  3. **Crop-sizing constants** (`_CIRCLE_MASK_RADIUS_FACTOR`/`_CROP_MARGIN_FACTOR`/
     `_MIN_INK_AREA_FACTOR` in `vision/ocr.py`): re-verified per ADR-030 point 3, via
     `data/maps/_t090_crop_sweep.py` sweeping `_CROP_MARGIN_FACTOR` from the shipped `0.6` up to
     `2.0` against the 3 maps a sub-1.0 gate win now touches. No single value helps all three:
     `kkm-toksovo` improves monotonically with a wider margin (10/25 at margin 1.0 -> 12/25 at
     margin 2.0), but `lembolovo-kkm` peaks at margin 1.2 (18/22) and then gets *worse* than its
     margin-1.0 reading as the margin widens further (14/22 at margin 2.0, vs. 17/22 at 1.0) —
     `novo-kavgolovsky-lesopark` is flat at 18/23 across the whole sweep, insensitive either way.
     Left unchanged — a global constant retune here is a net loss on at least one real map for any
     value tried, the same "measured, not speculative" bar ADR-030/T080 already applied.

  **Owner corpus, per-map before ([T089/ADR-030's own count](#adr-030) — production ladder
  `[1.0, 1.5, 2.0, 2.5, 3.0]` only) vs. after (this task, landed gate, ladder widened to
  `[0.5, 0.85, 1.0, 1.5, 2.0, 2.5, 3.0]`):**

  | Map | before mult/n/ok | after mult/n/ok | Δ reads |
  |---|---|---|---|
  | grid-lines-red-controls | 2.0 / 13 / 10 | 2.0 / 13 / 10 | 0 (unaffected — winner was already >=1.0) |
  | history-race-2024-michurinskoe | 2.0 / 37 / 13 | 2.0 / 37 / 13 | 0 (gate correctly rejected the 0.4 false-cluster winner) |
  | history-race-primorsk | 1.0 / 49 / 17 | 1.0 / 49 / 17 | 0 (gate correctly rejected the 0.5 same-ring-worse-crop candidate) |
  | kkm-3-2020 | 1.0 / 21 / 17 | 1.0 / 21 / 17 | 0 (gate correctly rejected the 0.85 same-ring-worse-crop candidate) |
  | kkm-5-2020 | 2.0 / 21 / 11 | 2.0 / 21 / 11 | 0 (unaffected) |
  | **kkm-toksovo** | 1.0 / 25 / 1 (4%) | **0.85 / 25 / 8 (32%)** | **+7** |
  | **lembolovo-kkm** | 1.0 / 20 / 7 (35%) | **0.5 / 22 / 13 (59%)** | **+6** (+2 circles: 2 more real rings found) |
  | michurinskoe | 2.0 / 37 / 23 | 2.0 / 37 / 23 | 0 (unaffected) |
  | **novo-kavgolovsky-lesopark** | 1.0 / 21 / 6 (29%) | **0.5 / 23 / 16 (70%)** | **+10** (+2 circles) |
  | ozero-shchuche (dup of kkm-3-2020) | 1.0 / 21 / 17 | 1.0 / 21 / 17 | 0 (gate correctly rejected) |
  | pervomayskoe | 1.5 / 41 / 19 | 1.5 / 41 / 19 | 0 (unaffected) |
  | toksovo-1 | 1.5 / 21 / 19 | 1.5 / 21 / 19 | 0 (unaffected) |
  | toksovo-zubry | 1.5 / 31 / 24 | 1.5 / 31 / 24 | 0 (unaffected) |
  | treugolnoe | 1.5 / 58 / 21 | 1.5 / 58 / 21 | 0 (unaffected) |
  | **TOTAL** | **205/416 (49.3%)** | **228/420 (54.3%)** | **+23 reads, +4 circles, +5.0 points** |

  The gate reproduces ADR-030's own apples-to-apples prediction exactly: the 3 genuine H2 wins land
  (+7/+6/+10 = +23, matching ADR-030's "+23 combined" for the winning subset) and all 4 predicted
  regressions (history-race-primorsk, kkm-3-2020, ozero-shchuche, history-race-2024-michurinskoe) are
  correctly avoided by falling back to production — none of ADR-030's measured "-47 combined" net
  loss materialises. Circle-detection recall improves on the 2 maps whose true (smaller) scale finds
  more real rings than the base-scale-only ladder did (lembolovo-kkm 20->22, novo-kavgolovsky-lesopark
  21->23); precision is unaffected — the gate only ever substitutes one already-ring-coverage-passing
  candidate set for another, never adds an unfiltered one.

  **`ogps-*` corpus, full 204-dir sweep (203 loaded, same 1 pre-existing decompression-bomb load
  failure as ADR-030), before (ADR-030's own numbers) vs. after (this task):**

  | Split | before | after |
  |---|---|---|
  | corpus-wide | 2372/10343 (22.9%) | **2796/11051 (25.3%)** |
  | `cal_source=measured` | 2844→683 (24.0%) n=45 | 3190/839 (26.3%) n=45 |
  | `cal_source=assumed_default` | 7499→1689 (22.5%) n=158 | 7861/1957 (24.9%) n=158 |
  | `cal_tier=circle` | 1987/515 (25.9%) n=35 | 2291/636 (27.8%) n=35 |
  | `cal_tier=grid` | 855/168 (19.6%) n=9 | 855/176 (20.6%) n=9 |
  | `cal_tier=scale_bar` | 2/0 (0.0%) n=1 | 44/27 (61.4%) n=1 |
  | dpi [0,150) | 3347/590 (17.6%) n=61 | 3347/590 (17.6%) n=61 (unchanged — no gate win in this bucket) |
  | dpi [150,250) | 1561/414 (26.5%) n=25 | 1598/451 (28.2%) n=25 |
  | dpi [250,320) | 5230/1318 (25.2%) n=110 | 5901/1705 (28.9%) n=110 |
  | dpi [400,∞) | 205/50 (24.4%) n=7 | 205/50 (24.4%) n=7 (unchanged) |
  | sheet [0,250)mm | 551/119 (21.6%) n=36 | 1171/413 (35.3%) n=36 |
  | sheet [250,350)mm | 1256/376 (29.9%) n=26 | 1259/387 (30.7%) n=26 |
  | sheet [350,450)mm | 1742/433 (24.9%) n=25 | 1748/447 (25.6%) n=25 |
  | sheet [450,∞)mm | 6794/1444 (21.3%) n=116 | 6873/1549 (22.5%) n=116 |

  Corpus-wide: +708 circles found (+6.8%), +424 correct reads (+17.9% relative, +2.4 points
  absolute). The gate generalises past the 14-map owner corpus it was designed against — every
  split that moved, moved up, none regressed; the untouched dpi/[0,150) and dpi/[400,∞) buckets
  (identical circle and read counts before/after) show the gate is genuinely conditional, not a
  blanket change that happens to net positive.
- Decision: land the multiplier ladder change + OCR-outcome gate as implemented; leave
  `vision/ocr.py`'s crop-sizing constants unchanged (point 3 above — re-verified, no value helps
  every map, ADR-030's own item closed by measurement rather than guesswork); raise
  `TestRealScanReadRateFloor`'s `novo-kavgolovsky-lesopark` floor from `>= 5` (of 21 circles) to
  `>= 13` (of 23 circles, measured 16/23) and add two new floors in the same class,
  `kkm-toksovo` (`>= 6` of 25, measured 8/25) and `lembolovo-kkm` (`>= 10` of 22, measured 13/22).
- Consequences: the corpus-wide `ogps-*` rate (25.3%) confirms this fix is real but not the
  dominant lever — ADR-030 point 4's leading remaining suspect (ADR-023's own mode 1, leftover
  non-digit ink defeating Tesseract's `psm 7`, generalised across the wider corpus, never re-run at
  `ogps-*` scale by either T089 or T090) is still unaddressed and still most likely the largest
  remaining source of unread numbers; a corpus still reading barely one in four controls is not
  "fixed", only measurably better. Flagged for the owner/a future iteration to decide whether it is
  worth another diagnose-then-fix round in the same style as T083/T084 and T089/T090, rather than
  silently left as a documented rate.

  **Amendment, from independent review after this landed:** a scoped `reviewer` subagent pass over
  the full M11 diff (`473c410..HEAD`) found two real issues in T090 itself, both fixed and
  independently re-verified this session (499 passed — 493 + 6 new tests, `ruff check .` clean —
  own run, not trusted from the subagent's report), plus one proposed fix investigated and
  reverted after it was measurably wrong:
  1. **Hub (start/finish triangle) detection regression, fixed.** `_detect_hub_triangle` shares
     `circle_scale_multipliers` with `_detect_circles`, so T090's new `0.5`/`0.85` rungs fed hub
     matching too, with no OCR-style gate to catch a bad one (a hub carries no digits). Measured:
     on `history-race-primorsk`, sweeping the widened ladder turned a correct "no hub found" into a
     spurious hub at confidence 0.298 — the lowest in the owner corpus — because the smaller rungs
     shrink `max_diff`'s absolute tolerance band enough for an unrelated contour to fit. No map in
     this project's corpus has ever shown evidence of an undersized hub triangle (unlike circles,
     ADR-030's H2), so `_detect_hub_triangle` now sweeps only the `>=1.0` entries of
     `circle_scale_multipliers`, unconditionally. Re-measured across all 14 owner maps: hub output
     is now bit-identical to the pre-T090 ladder on every map (`history-race-primorsk` back to no
     hub, `toksovo-zubry`'s confidence back to 0.709 from an incidentally higher 0.838) — the
     circle-detection side of T090 (the table above) is unaffected, since hub and circle detection
     use separate functions.
  2. **`_ocr_gate_sub_base_scale` had no direct unit test, fixed.** Its only prior coverage was the
     three real-scan floor tests, all `skipif`-guarded on gitignored owner-corpus files (ADR-010) —
     the gate ran unexercised on any machine without that corpus, CI included. Five new tests in
     `tests/unit/vision/test_controls.py::TestOcrGateSubBaseScale` drive all four branches directly
     with a stubbed `read_control_numbers` (the deferred import inside the gate function makes
     `monkeypatch.setattr` trivial): sub-base wins on strictly more reads, production wins on
     strictly more reads, both tie cases (zero-zero and equal-nonzero) fall back to production, and
     no production candidates existing at all returns the sub-base set without ever calling
     `read_control_numbers` (asserted via a stub that raises if called).
  3. **Tie-break bias toward multiplier `1.0`, investigated and reverted — not a real fix.**
     Proposed to stop the gate firing "needlessly" when a sub-1.0 and a `>=1.0` window tie on
     ring-coverage score (measured on `history-race-primorsk`). Reverted after `kkm-toksovo`
     falsified the premise: it ties in exactly the same way (`0.85` and `1.0` both score `n=25` at
     equal bucketed coverage) yet the two scales' *OCR outcomes* are not equivalent — `1.0` reads
     1/25, `0.85` reads 8/25, the ADR-030 "same ring, differently-sized crop" mechanism applying
     even when the candidate sets tie on coverage. A tie-break biased toward `1.0` would have picked
     `1.0` directly, skipping the OCR gate entirely (it only runs when the winner is itself
     sub-1.0) and silently reverting this task's own headline win back to 4%. Ring-coverage ties
     are not proof of OCR-outcome ties; `_select_best_scale` keeps its original two-tier score.
  4. **Cost wording corrected.** "Bounded to at most one extra OCR pass" (both here and in
     `_detect_circles`'s own docstring) undercounted by one — the gate always runs
     `read_control_numbers` on *both* candidate sets when it fires (two passes), on top of the
     pipeline's own later pass over whichever set is returned. Wording fixed in both places; no
     behaviour change.

  Three lower-severity findings from the same review (viewer export links not following a selected
  route alternative, T093; keyboard focus lost on every route-switcher rerender, T093; T095's
  before/after route-*time* numbers being partly an artifact of the cost-model change itself rather
  than only the route choice, T095) are outside T090's own scope and are tracked separately rather
  than fixed here — see `docs/STATUS.md`'s Iteration I4 section for how each is being handled.

## ADR-032 — Real-scan control detection: OCR crop windows slide instead of truncating at the raster edge; a per-candidate raw-radius consistency filter and a per-candidate sub-1.0 OCR gate replace their set-level predecessors
- Date: 2026-09-12
- Status: accepted
- Context: Owner bug report, in-chat, with two annotated screenshots of real (`ogps-*`-harvested)
  maps showing controls (72/44/66/42/53) whose printed number is clearly legible to a human but
  came back unread, plus one correctly-read control (71) for contrast, and a separate report of
  spurious tiny "controls" detected inside cover-page/legend text. The owner proposed four
  heuristics (colour, known circle size, edge-of-segment failure, text false positives). Code
  inspection (not the owner's claims taken at face value) found each already partially addressed,
  with one concrete gap per item — full detail in
  `docs/iterations/I5-control-detection-false-negatives.md`. Owner chose to design all four fixes
  directly rather than a separate measurement-first diagnosis pass first (ADR-026/I4's precedent),
  an explicit, recorded departure — Phase 5 verification still measures against the real corpus
  before anything lands.
- Decision: four bounded fixes, all within `vision/controls.py`/`vision/ocr.py`'s existing
  mechanisms, no new detection algorithm:
  1. **T097 — OCR crop no longer truncates at the raster edge.** `_ocr_crop`'s window clamp
     (`vision/ocr.py`) changes from independently clamping each axis (which shrinks the window when
     a control sits near the scan's physical boundary, potentially cutting off a number printed
     toward that side) to sliding the fixed-size window to stay in-bounds, keeping the full
     configured half-width whenever the raster is large enough to hold it (true for every real
     scan). Falls back to the old shrink-to-fit behaviour only if the raster itself is smaller than
     the crop window.
  2. **T098 — a per-candidate raw-radius consistency filter.** `_select_best_scale` (ADR-015)
     already picks one global scale per map and assigns every accepted candidate the same nominal
     `r_mid` (T077/ADR-020) — but nothing today compares an individual candidate's own *raw*
     Hough-fitted radius (computed, then discarded, in `_detect_circles`) against the cluster of
     other accepted candidates at the winning scale. A coincidental ink blob (e.g. inside a bold
     digit/letter glyph) that clears `_ring_coverage`'s threshold at the right scale is accepted
     with no further shape check today. `_detect_circles` threads the raw radius alongside `r_mid`
     for this filter only; `Control.radius_px`/`_ocr_crop` keep using `r_mid`, unchanged — T077's
     own reasoning for why the raw fit must not drive crop sizing is untouched.
  3. **T099 — the sub-1.0 OCR gate becomes per-candidate.** `_ocr_gate_sub_base_scale` (T090/
     ADR-031) compares two whole candidate *sets* (sub-1.0 vs. the >=1.0 production winner) by
     aggregate valid-read count and keeps one set entirely — so a few genuine sub-1.0 controls
     mixed with glyph false positives can still let the false positives through as part of the
     winning set. Generalised to gate each sub-1.0 candidate individually: keep only the ones whose
     own crop actually yields a plausible read, when the winning scale is itself sub-1.0.
  4. **T100 — confirm, measure, don't re-design, the colour heuristic.** No gap found in the colour
     signal itself (`purple_mask`/`ink_hue_ranges` already gate every detection and OCR-crop code
     path) — add a pinning regression test if none already exists, then re-measure false-positive
     rate and OCR read rate across the owner's real corpus before/after T097-T099, as the concrete
     evidence for the owner's manual sign-off.
  Deferred, named rather than silently dropped: a full diagnosis-first measurement pass before
  design (owner's explicit choice this round); retuning `ink_hue_ranges`/`purple_mask` itself (no
  gap found — becomes its own task if T100's measurement finds one); a general spatial
  non-maximum-suppression/declustering pass (broader, higher-risk than T098's narrower check, only
  attempted if T100 shows a residual text-shaped false-positive class); DPI/scale auto-calibration
  retuning (ADR-030/T089 already measured this is not the corpus's dominant driver).
- Consequences: diff footprint is `vision/ocr.py` (T097), `vision/controls.py` (T098, T099), plus
  new unit tests for each and a real-corpus before/after measurement (T100) recorded here once
  landed. T098 and T097 are independent of each other and of T099; T099 should land after T098
  since both touch `_detect_circles`'s per-candidate data (landing T098 first avoids threading the
  same raw-radius field twice). Acceptance is the owner's manual spot-check of example controls
  (ADR-019 precedent, same as T082/T086/T095) — no numeric corpus-wide floor required for this
  iteration's gate, though T100's own measurement is recorded regardless of direction.

- **Amendment, 2026-09-13 — T098 closed with no code change, measured unsafe.** A per-candidate
  filter was built exactly as decided above: `_detect_circles` threaded each Hough candidate's raw
  fitted radius alongside `r_mid` as a 5th internal tuple element (stripped back off before
  returning, so every caller's `(x, y, r, coverage)` shape stayed unchanged), and
  `_reject_raw_radius_outliers` scored the winning scale's own cluster by a median + median-
  absolute-deviation modified z-score (threshold 3.5, the standard Iglewicz & Hoaglin robust cutoff),
  with a synthetic regression test (one true-ring cluster plus a deliberately mis-sized coincidental
  filled blob at the same nominal scale).

  Both the synthetic test and the full suite failed. The synthetic test itself rejected a *genuine*
  ring, not the decoy — one true ring's own raw Hough fit landed far enough from the cluster's
  median to trip the same 3.5 threshold meant to catch the decoy. Against the real corpus, the same
  mechanism stripped already-validated genuine detections from all 3 of the sub-1.0-scale read-rate
  floor tests (ADR-031): `kkm-toksovo` 25→21 circles, `lembolovo-kkm` 22→20, and
  `novo-kavgolovsky-lesopark` 23→13 (its own floor test's exact failure output — the worst hit, more
  than a third of its real controls stripped as "outliers").

  Root cause, measured, not a threshold that just needed retuning: for a given
  `circle_scale_multipliers` entry, Hough's own `minRadius`/`maxRadius` are already
  `r_mid × (1 ∓ circle_diameter_tolerance)` (`config.py::circle_radius_px`, tolerance `0.35` in
  `config/default.toml`) — so *every* raw candidate Hough can return for that multiplier is already
  confined to `[0.65, 1.35] × r_mid` by construction, before any filter runs. Measuring the actual
  raw-radius/`r_mid` ratios of the winning scale's own accepted cluster across 5 real maps
  (`kkm-toksovo`, `lembolovo-kkm`, `novo-kavgolovsky-lesopark`, `grid-lines-red-controls`,
  `ozero-shchuche`) found genuine controls routinely sitting anywhere across that entire admissible
  band (observed ratios 0.663-1.333, i.e. essentially edge to edge). There is no room inside an
  already-narrow, already-enforced window for a *further* per-candidate statistical cutoff to
  separate "clear outlier" from "genuine control near the window's own edge" — any threshold tight
  enough to reject a hypothetical coincidental blob would, and measurably did, also reject real
  controls that legitimately land near the same edge.

  No known real-corpus false positive of item 2's originally-hypothesised shape (a same-scale,
  same-`r_mid` coincidental ink blob, e.g. inside a bold digit glyph) was ever actually observed to
  motivate this filter in the first place — the gap was inferred from code inspection, not
  reproduced. Closed with no code change, same precedent as T080 (measured, not speculative); full
  before/after counts and the exact `raw/r_mid` ratio tables live in this session's own throwaway
  measurement (not committed, same convention as T089/T090's own scripts). `Control.radius_px`,
  `_ocr_crop`, `_select_best_scale`, and `_ocr_gate_sub_base_scale` are all unaffected — none of
  their behaviour or reasoning (T077/ADR-020, ADR-015, ADR-031) changes.

- **Amendment, 2026-09-13 — T099 landed, generalised one branch beyond its own DoD's letter.**
  `_ocr_gate_sub_base_scale` now probes each sub-1.0 candidate's own crop individually and keeps
  only the ones that read a plausible number, comparing that survivor count against the production
  side's own aggregate read count exactly as before. Beyond the DoD as written, the per-candidate
  probe now also runs when no `>=1.0` candidate exists at all to compare against — T090's version
  returned the whole unfiltered sub-1.0 set unconditionally in that branch, treating an OCR pass
  there as pure waste with nothing to compare against. That reasoning held for T090's own scope
  (choosing between two sets), but leaves exactly item 4's failure mode unguarded: a map whose only
  Hough hits are sub-1.0 (e.g. a cover page with no real controls, only small round glyph loops)
  never reaches the comparison branch at all, so the false positives inside it would ride straight
  through. Recorded here as a deliberate, reasoned departure from the literal DoD, not a silent
  scope change — same category as I5's own "designed all four fixes now" departure from ADR-026's
  precedent, just one level down.

  A real, explicit trade-off this filter accepts, worth naming rather than leaving implicit: a
  genuine sub-1.0 control whose specific printed number happens to be illegible (faded ink, a torn
  scan corner) is indistinguishable, from inside this function, from a glyph coincidence that was
  never a control at all — both read `None` from their crop — so both are now dropped from the
  returned detections entirely, rather than surfacing the illegible one as a flagged, unread control
  per SPEC F8's general contrast ("emitted with null points and flagged, never silently guessed").
  This gate's own narrow scope keeps the blast radius small: it only ever fires on the already-
  gated sub-1.0 path (ADR-031), never on the production (`>=1.0`) detection path, where a genuinely
  illegible real control is still surfaced and flagged exactly as SPEC F8 requires.

  Measured against the 3 real-scan floors ADR-031 established: `novo-kavgolovsky-lesopark` circle
  count moved 23→16, `kkm-toksovo` 25→8, `lembolovo-kkm` 22→13 — in every case the dropped
  candidates were exactly the ones that were never contributing a successful read in the first
  place, so each map's *absolute* `n_read` is unchanged (16, 8, 13 respectively — now 100% of a
  smaller detected set, not a reduced count). The existing `n_read >=` floors did not need to move;
  only the exact circle-count assertions did (`tests/unit/vision/test_ocr.py`). Two new unit tests
  in `TestOcrGateSubBaseScale` cover the mixed genuine-plus-glyph case and the now-gated
  no-production branch; the 4 pre-existing branch tests are unchanged and still pass unmodified,
  since every sub-1.0 candidate in each of those stubbed scenarios uniformly reads or doesn't (so
  per-candidate filtering changes nothing about which side wins there) — itself the regression
  proof that T099 left T090's own already-covered branches undisturbed. 506 passed, `ruff check .`
  clean.

- **Amendment, 2026-09-13 — T100 measurement, and a real trade-off found that needs the owner's
  own call before this milestone closes.** Confirmed first (DoD item 1): `purple_mask`/
  `ink_hue_ranges` already gate every detection and OCR-crop code path (`detect_controls` computes
  one mask and passes it to both `_detect_hub_triangle` and `_detect_circles`; `_ocr_crop`
  re-applies the same `purple_mask` function to its own crop) — no gap found, no speculative test
  added.

  Corpus-wide before/after (throwaway `data/maps/_t100_measure.py`, T083/T084/T089's own method,
  no re-implementation; "before" = commit `989c08f`, pre-I5; "after" = current tree with T097+T099,
  T098 closed with no change): **owner's 14-map corpus** circle count 420→387 (-7.9%), absolute
  successful reads 228→229 (+1), rate 54.3%→59.2%. **A 40-map `ogps-*` sample**: circle count
  1877→1526 (-18.7%), absolute reads 528→527 (-1, noise-level), rate 28.1%→34.5%. In both corpora
  the story is the same shape: a large fraction of previously-detected circles disappear, while the
  total count of *successfully read* numbers barely moves — meaning most of what disappeared was
  never contributing a read either way.

  **What that removal actually is, checked by eye on real maps, not assumed:** on
  `ogps-3771_0da0ae4ad426ed5d03089615dbe38a1f` this is unambiguously a win — 230→17 circles, 17/17
  now reading (100%, was 7%). Visual inspection found the map prints a large pink/magenta hatched
  "no-crossing zone" (its own legend confirms: "РОЗОВОЙ ШТРИХОВКОЙ ОБОЗНАЧЕНЫ ЗОНЫ, ЗАПРЕЩЕННЫЕ ДЛЯ
  ПЕРЕСЕЧЕНИЯ УЧАСТНИКАМИ") in the same ink family `ink_hue_ranges` matches — the hatch texture's
  crossings coincidentally clear `_ring_coverage` by the hundreds, and T099 discards essentially all
  of them while every real, green-circled control on the same map survives untouched.

  On the owner's own `kkm-toksovo`, the same mechanism is **not** a clean win. 25→8 circles, 8/8
  reading (100%, was 32%) — but a by-hand check of a sample of the 17 dropped candidates
  (`data/maps/_t100_crop_xy.py`) found several that are unambiguously real, clearly-legible,
  correctly-positioned controls (91, 92, 72, 52 confirmed by eye against the map's own printed
  labels) that Tesseract simply never read at this map's own print style/scale — a pre-existing OCR
  weakness (this map read only 8/25 *before* I5 too, unrelated to T097/T099), not something these
  tasks introduced. T099 cannot distinguish "real control, illegible to Tesseract" from "coincidental
  ink texture, never a control" — both read `None` from their own crop and are structurally
  indistinguishable to this gate. Before T099, such a control still appeared in the output as a
  detected-but-unread `Control` (flagged, position correct, ready for the owner to type its number
  in by hand). After T099, it is silently absent from the output entirely — the owner would have to
  notice it is missing and re-add it from scratch (position and number both), not just fill in a
  number. This is the exact trade-off T099's own landing note (above) already named in the abstract;
  seeing it materialise on a real, important map with multiple confirmed real controls is why it is
  called out here explicitly rather than treated as already settled.

  This is a genuine product/UX judgement call, not a correctness bug with one right answer: keep
  T099's current behaviour (fewer false positives shown, at the cost of some real-but-illegible
  controls vanishing instead of surfacing flagged), or amend it to keep every sub-1.0 candidate in
  the output (flagged unread instead of dropped) and use the per-candidate read outcome only to
  decide *which scale wins* — reopening exactly the "false positives ride along in the winning set"
  risk T099 was built to close. No code change made in response to this finding without the owner's
  own decision (ADR-019 precedent: manual sign-off is this iteration's acceptance gate, not a
  numeric floor) — see `docs/TASKS.md` T100's own entry and the session's report to the owner for
  the question as put and, once answered, the resolution.

  Before/after crops sent to the owner via `SendUserFile`: the `kkm-toksovo` full-map overview
  (before/after), the 4 confirmed-real dropped-control crops (91/92/72/52), and the
  `ogps-3771` full-map overview (before/after) as the contrasting clean-win case. A third, subtler
  T097 case was also measured (control `72` on `ogps-3592_2b186961d73c0efb57200e3baee226d9`,
  matching the owner's own reported example number exactly: unread before, reads "72" after) but its
  crop-size change is only ~5px at the edge the control does not actually sit closest to, so it is
  recorded as a real, reproduced flip rather than a visually dramatic "digit was chopped off" story
  — Tesseract's own layout analysis is evidently sensitive to a smaller margin change than a human
  eye would guess, not fully root-caused pixel-by-pixel here.
