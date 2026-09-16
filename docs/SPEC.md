# Product Spec — Rogaine Route Planner

## Summary
A local, offline-by-default tool that turns a rogaine map raster into a scored route plan (I7/F23:
an optional, disabled-by-default OCR fallback may call an external vision API for control-*number*
reading only, never position detection — see `## Integrations`). It classifies the
map's terrain from ISOM colours, finds the purple control circles, builds a per-pixel travel-time
field for a given runner speed, computes exact travel times between all controls, and solves the
Orienteering Problem (maximise points inside a time limit, start = finish, points lost per minute
late). Delivered as a Python CLI plus a local web viewer.

Reference implementation this reproduces: https://habr.com/ru/articles/1065342/

## Users & scenarios
### Primary
- Competitor planning a route before a start: has the map raster and the time limit, knows their own
  pace, wants the best loop and its predicted time.
### Secondary
- Same person analysing a past event: "how many points did I leave on the table?", "how much does
  the far cluster cost?"

## User flows

1. **CLI, one shot**
   `plan --map map.png --scale 10000 --dpi 300 --limit 4h --speed 2.0 --hub 1240,890`
   produces `out/route.json`, `out/route.png`, and a terminal summary (points, time, penalty, legs).
   `--auto-scale` (I3, F21) replaces `--scale`/`--calibrate` with a best-effort automatic attempt;
   on failure it reports why and asks for one of the other two, rather than guessing.

2. **CLI, staged (review between steps)**
   `segment` produces `terrain.npz` + `terrain_preview.png`;
   `detect` produces `controls.csv` (editable by hand);
   `plan --controls controls.csv` produces the route artefacts.

3. **Web viewer**
   Open `http://localhost:8000`, drop a map file, set scale (enter 1:N + DPI, drag a calibration
   line and type its length in metres, **or** try automatic detection — I3, F21, best-effort, falls
   back to the two manual options on failure). The map and the controls list stay simultaneously
   visible (I3, F17) as the user fixes markers (drag / add / delete / edit number and points), sets
   time limit, speed and penalty, presses Run, and gets the route drawn over the map with a leg
   table plus JSON/PNG/CSV export.

4. **Solver honesty check**
   `bench --controls controls.csv --limit 2h` runs both solvers on a reduced instance and prints the
   heuristic-vs-exact gap.

## Functional requirements

| ID | Requirement | Acceptance |
|----|-------------|------------|
| F1 | Load map raster from PNG/JPG/BMP/TIFF and from a single PDF page | Each format loads to the same RGB array within 1 LSB; a multi-page PDF loads page 1 by default and `--page N` selects another |
| F2 | Scale from 1:N plus DPI | `mpp = (25.4 / dpi) * N / 1000`; 1:10000 at 300 dpi gives 0.08467 m/px within 1e-6 |
| F3 | Scale by two-point calibration | User gives two pixel points and a ground length; resulting `mpp` matches F2 within 1% on a synthetic map of known scale |
| F4 | Classify every pixel into the ISOM terrain classes (open land, rough open, runnable forest, slow-run green, walk green, fight green, marsh, uncrossable water, shallow water, bare rock, paved road, road, vehicle track, footpath, out-of-bounds, contour, unknown) | On the synthetic fixture with known ground truth: per-class IoU at least 0.95 for area classes and 0.80 for linear classes. On a real scan whose printed water ink drifts from the configured palette (I6, `data/maps/ogps-6802_4a769f64b455f9b4675552284c3681b1`): a genuine lake/river with a black bank line classifies `water_uncrossable`, while a legitimately crossable ditch/shallow watercourse on the same map stays `water_shallow`/passable — the fix must not widen the uncrossable band broadly enough to catch the latter. A hatched/screened area symbol's enclosed interior (I7, `data/maps/ogps-8620_502cda4f6c774e8ecb86d063a71895f6`: an ISOM 709 out-of-bounds polygon and a lake) classifies consistently with its boundary ink rather than leaking through as whatever colour happens to print in the gaps between hatch lines |
| F5 | Recover linear features (roads, tracks, paths) as connected corridors, not scattered black pixels | On the fixture, a path drawn end-to-end is recovered as one connected component covering at least 90% of its length. A power line (ЛЭП) does not receive a genuine path's speed/proximity treatment on a real scan where its printed ink is measurably distinguishable from a footpath/track/road (I7, `data/maps/ogps-8620_502cda4f6c774e8ecb86d063a71895f6`); if no safe distinguishing signal is found on measurement, this stays a documented, named gap rather than a guessed fix (T111/T112) |
| F6 | Derive a slope penalty from contour density, without reconstructing elevation | Contour-dense regions cost strictly more to traverse than flat regions of the same terrain class; the coefficient is config-driven |
| F7 | Detect control circles (ISOM 5-6 mm at the base scale, or a larger hand-drawn size within `config/default.toml`'s `[detector].circle_scale_multipliers` range, in any ink colour listed in the same file's `[detector].ink_hue_ranges` — purple by default, plus others as real scans require) and the start marker | On the fixture: recall at least 0.95, precision at least 0.90, centre error at most a quarter of the circle radius. On a real scan whose controls use a configured non-purple ink and/or an oversized hand-drawn circle within the configured scale range (I1, `data/maps/grid-lines-red-controls/`): recall at least 0.90, precision at least 0.90, hub found. A per-candidate raw-fitted-radius outlier filter was considered for I5 but measured unsafe on real scans and not implemented (ADR-032's own amendment: Hough's own search window already confines every candidate to within the configured tolerance of the nominal radius, leaving no safe margin for a stricter cutoff). The ISOM 709 out-of-bounds symbol (printed in the same ink family as the control ring) is excluded from detection entirely, on any map (I6, `data/maps/ogps-7302_5d8c290224a04f49e2c95484d2fbaf92`), and stays impassable in the graph (F10). A candidate whose measured confidence falls below a fixed, corpus-measured floor is dropped rather than auto-placed — the owner completes it manually instead of the system guessing (I6, ADR-033/ADR-035) |
| F8 | Read control numbers and derive points | OCR per control; points rule configurable (first_digit, constant, or from CSV). Unreadable numbers are emitted with null points and flagged, never silently guessed — except a sub-1.0-scale circle-detection candidate in a junk-dominated set (more than 85% of that set unread), which is dropped rather than surfaced as a flagged control (I5/ADR-032, an explicit, owner-chosen trade-off). The OCR crop reaches the full configured search radius even when the control sits near the raster's edge — the crop window slides to stay in-bounds rather than truncating (I5/ADR-032). The crop's ink mask admits a control's number even when printed in a different colour from its own ring (I6, `data/maps/ogps-8078_8295c94963b2c249d6f4d94fd0c35fa1`), without reintroducing contour-line bleed into the crop (ADR-023). See F23 for the opt-in VLM fallback this same unread/low-confidence outcome may now trigger — with the fallback disabled (the shipped default), this row's behaviour is unchanged |
| F9 | Import/export controls as CSV (`id,x,y,number,points,confidence`) | Round-trip is lossless; a hand-edited CSV overrides detection entirely |
| F10 | Build a per-pixel travel-time field, `t = mpp / (v_base * k_terrain * k_slope)` | Impassable classes are excluded from the graph; the graph is 8-connected with sqrt(2) diagonal weighting. `veg_fight` (ISOM 410, dark-green "fight"/"оливка") is impassable by default (I7/ADR-037, the owner's own ruling for this event's rules: forbidden to enter, not merely 20x slower) — configurable like every other class via `config/default.toml` (F18) |
| F11 | Compute travel time between every pair of controls plus the hub, and keep the actual paths | Dijkstra from each control over the cost grid; the matrix is symmetric within numeric tolerance; every pair's polyline is reconstructible |
| F12 | Exact Orienteering Problem solver (Held-Karp over subsets) | Provably optimal for N up to 15 controls; brute force agrees for N up to 9 |
| F13 | Heuristic solver for 30-80 controls | Returns a feasible route within a configurable time budget; gap versus exact at most 5% on instances where exact is computable |
| F14 | Objective `score = sum(points) - penalty_per_min * max(0, T - limit)`, route starts and ends at the hub | A very large `penalty_per_min` produces a route strictly inside the limit; zero lets the solver overrun |
| F15 | Route artefacts: JSON (order, per-leg time and distance, cumulative time, points, penalty, polylines) and PNG (route over the map, numbered) | JSON validates against the documented schema; PNG legs match the JSON polylines |
| F16 | Alternative routes: top-K structurally distinct solutions with their scores | K configurable; alternatives differ by at least one visited control; doubles as the map's "interestingness" measure. The web viewer (F17) surfaces these as switchable routes whenever more than one exists, not only the primary route (I4) |
| F17 | Local web viewer: upload, calibrate, edit controls, run, inspect, export | A Playwright script completes the full flow on the fixture map with no manual steps; the map and the controls list are both visible at once on a standard viewport (I3) — assigning a control's number never requires scrolling the map out of view. The calibration-line and add-control tools give a visibly distinct "armed" affordance while active, and panning the map while either is armed never places or corrupts a point — only a genuine click does (I6). The add-control panel button places a control exactly where the user next clicks the map, then immediately returns to idle so the map is draggable again, matching the calibration-line tool's own click-to-place flow (I6) |
| F18 | Every tunable (terrain coefficients, slope factor, circle radius range, solver budgets, penalty) lives in one config file, overridable per run | Changing a coefficient in the config changes the route with no code edit |
| F19 | Deterministic runs | Same inputs and same seed produce byte-identical JSON |
| F20 | Non-terrain map ink (grid lines, magnetic-north lines) is never misread as a real terrain feature | On a real scan with full-height grid lines (I1, `data/maps/grid-lines-red-controls/`): the grid columns classify as `unknown`, not `water_uncrossable`; a real water body in the same fixture family still classifies as water |
| F21 | Best-effort automatic scale detection (reuses `vision/calibrate.py::calibrate_map`'s scale-bar / grid / circle-diameter tiers), offered as an explicit opt-in action in both the CLI and the web viewer, alongside the existing manual paths (F2/F3) (I3, ADR-022) | On a map where a tier fires: CLI/viewer report which tier (`scale_bar`/`grid`/`circle`) and the resulting mpp/dpi. On a map where none fires: a clear "auto-detection unavailable, enter manually" outcome, never a crash or a silently guessed value. Auto-detection only runs on explicit user action and never overrides an explicit `--scale`/`--calibrate` (CLI) or `scale`/`calibrate` (viewer) value |
| F22 | Web viewer auto-fills a control's points from its number using the `first_digit` rule (all digits but the last), editable; a manual points edit is sticky and survives further number edits (I4, ADR-024) | Typing/editing a freshly-detected or never-points-edited control's number auto-fills points (`123` -> `12`, `45` -> `4`); once points has been hand-edited for that control, further number edits no longer overwrite it. Resets to auto-fill on reload/re-import (CSV import already overrides detection wholesale, F9) |
| F23 | Opt-in VLM OCR fallback for control numbers only (I7, ADR-039, amends ADR-009): when `[ocr_fallback].enabled=true` and a backend is configured (I7/ADR-040: a cloud vision API key, or a reachable local Ollama server), a control whose Tesseract read is empty or below `[ocr_fallback].trigger_confidence` is retried against that backend before falling back to F8's existing null-flagged behaviour | Disabled by default — F8's existing behaviour is byte-for-byte unchanged with the fallback off, and it is off in every test that does not explicitly enable it. No API key or no network reachability degrades gracefully to F8's existing behaviour, never a crash. A control resolved by the fallback is marked distinctly (not indistinguishable from a Tesseract read) so a human reviewing the output can see which numbers were VLM-assisted. On `data/maps/ogps-8620_502cda4f6c774e8ecb86d063a71895f6` with the fallback enabled: every one of the owner's originally-reported unread numbers is either read or still explicitly flagged, never silently wrong |

## Non-functional
- Performance on a 4000x3000 map at 1:10000, CPU only: segmentation at most 30 s, all-pairs travel
  times for 60 controls at most 60 s, heuristic solve at most 30 s.
- Security: no network calls at runtime, **except** F23's OCR fallback (I7/ADR-039), which is
  disabled by default and requires both an explicit config flag and a configured backend (a cloud
  vision API key, or a reachable local Ollama server, I7/ADR-040) to make any call at all — the
  guarantee holds unconditionally whenever the fallback is off or unconfigured. The
  viewer binds to `127.0.0.1` only; uploaded files stay in a run directory under the project; nothing
  shells out to user-controlled strings.
- A11y: viewer is keyboard-operable, focus is visible, controls are labelled, legible in light and dark.
- SEO: not applicable (local tool).

## Content / data model
- `TerrainClass` — enum plus config entry (`speed_factor`, `passable`, `color_rgb`, `isom_code`).
- `MapContext` — raster, `meters_per_pixel`, source path, page.
- `Control` — `id`, `x`, `y` (pixels), `number`, `points`, `confidence`, `source` (detected/manual),
  `is_hub`.
- `CostField` — float32 seconds-per-pixel raster, passability mask, and the parameters behind it.
- `TravelMatrix` — (N+1)x(N+1) seconds plus a per-pair polyline reference.
- `Route` — ordered control ids, legs (time, distance, polyline), total time, points, penalty, score.
- `RunConfig` — speed, time limit, penalty, solver choice and budget, seed.

## Integrations
None by default. No external APIs, no telemetry. **Exception (I7/F23/ADR-039, backend choice
I7/ADR-040):** an opt-in, disabled-by-default OCR fallback may call a configured vision backend —
either an external API over HTTPS, or a local Ollama server — sending only a
single control's cropped ink region — never the full map, never any other field — and only when
Tesseract's own read is empty or low-confidence. No telemetry beyond that one API call; no data is
sent anywhere when the fallback is disabled or unconfigured (the shipped default).

## Non-goals
- GPS georeferencing, GPX export, GeoTIFF, world files.
- ~~VLM-based control detection (the article's Yandex Cloud Qwen path).~~ Narrowed 2026-09-14 by
  ADR-039 (I7): control **position**/circle detection stays classical CV and remains a non-goal for
  VLM — only control-*number* reading gains an opt-in VLM fallback (F23), disabled by default.
- Fatigue or time-varying speed.
- ~~Automatic detection of the map's scale bar.~~ Withdrawn 2026-09-07 by ADR-022 (I3) — now F21,
  opt-in only, manual entry stays the default.
- Hosting, accounts, multi-user, persistence beyond local run directories.
- Parsing OCAD `.ocd` vector geometry (rasters rendered from OCAD are in scope; the binary format is
  not).

## Risks & assumptions
1. **Palette classification breaks on photos.** Assumption: inputs are renders and scans, not phone
   photos. Mitigation: white-balance and illumination normalisation before classification; the
   optional SegFormer milestone exists precisely for this, trained on palette-generated masks.
2. **Map text and symbols pollute the terrain classes.** Black numbers and symbols look like rock or
   path; grid/magnetic-north lines read as water by colour alone (I1, F20). Mitigation: size and
   elongation filters plus an `unknown` class filled from its neighbourhood.
3. **Contour density is a proxy, not a slope.** It cannot tell uphill from downhill, so route
   direction does not change cost. Accepted for v1 and stated in the output. Real elevation
   integration is deferred pending research (I4, ADR-028, `docs/research/terrain-relief-integration.md`) —
   not started, no implementation commitment yet.
4. **OCR of control numbers is the most fragile step.** Mitigation: it is never load-bearing — points
   fall back to a constant, and the CSV/viewer edit path is a first-class flow, not a repair hatch.
   Four rounds of classical-CV tuning (T079-T105) still leave real scans with unread numbers;
   an opt-in VLM fallback (I7, F23, ADR-039) is a second mitigation layer for owners who accept its
   cost/network/determinism trade-off, on top of — not instead of — the CSV/viewer repair flow.
5. **No real map fixture exists yet.** Mitigation: a synthetic ISOM map generator produces a fixture
   with exact ground truth; the owner's own maps then serve as the acceptance check.
6. **Heuristic optimality is unverifiable at 60 controls.** Mitigation: report the gap wherever exact
   is computable, always report the objective, never claim optimality.
7. **8 GB VRAM caps SegFormer training** (MiT-B4 at 512 px needs mixed precision and a small batch).
   Affects only the optional milestone.

## Launch checklist
- `docker compose run --rm tests` green, including the synthetic-fixture end-to-end test.
- Playwright viewer flow green.
- `bench` prints a heuristic-versus-exact gap on the fixture, within F13.
- Owner runs their own map through both CLI and viewer and accepts the route.
- README covers install, run, config reference, JSON schema, and known limitations.
