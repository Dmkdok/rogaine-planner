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
