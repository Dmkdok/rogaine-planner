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
| 014 | o-gps-center.ru scraped maps supplement ADR-010's owner-corpus premise | proposed |

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

## ADR-014 — o-gps-center.ru scraped maps supplement ADR-010's owner-corpus premise (proposed)
- Date: 2026-09-02
- Status: proposed — needs the owner's sign-off before harvesting past the sample already taken.
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
