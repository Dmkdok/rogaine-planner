# Brief

## Pitch
A local tool that reads a rogaine map image, understands its terrain, finds the control points, and
plans the highest-scoring loop a runner of a given fitness can actually finish inside the time limit.

## Problem / JTBD
- Rogaine route choice is the whole sport: pick a subset of controls and an order so that score is
  maximised while total travel time fits the limit. Competitors do this by eye, under stress, on
  paper, in the 1-2 hours before the start.
- Reference: https://habr.com/ru/articles/1065342/ — the pipeline this project reproduces
  (map segmentation -> control detection -> traversal cost -> A* + orienteering-problem solver).
- Jobs: (1) "given this map and 4 hours at my pace, what should I run?"; (2) "how much do I lose if
  I skip the far cluster?"; (3) "is this map interesting — are there several close-to-optimal
  options, or one obvious loop?"

## Primary user
- The map owner: a rogaine / orienteering competitor with map rasters on disk, planning a route
  before a start or analysing a past event. Technical enough to run a CLI and a local web page.

## Success (30 days)
- Owner feeds one of their own map rasters, sets scale + time limit + pace, and gets a route they
  judge as good as the article's results — "не хуже качеством" (their words).
- Route quality is defensible, not just plausible: on small instances the heuristic solver is
  compared against the exact Held-Karp optimum and the gap is reported.

## In scope (v1)
- Input: map raster (PNG / JPG / PDF page / scan). A few OCAD `.ocd` files exist and may be used as
  a rendering source, but the product path is raster-first.
- Terrain segmentation into ISOM classes (open / forest by runnability / vegetation / water /
  marsh / roads and paths / rock / out-of-bounds / contours).
  Primary method: deterministic ISOM palette classifier. Optional second stage: SegFormer MiT-B4
  trained on palette-generated masks, for photos and noisy scans.
- Control point detection: HSV purple mask + Hough circles + OCR of numbers, with a manual
  correction path (CSV import/export and click-to-edit in the viewer). No external VLM API.
- Scale: user enters map scale + DPI, or calibrates by drawing a line of known length.
- Movement model: base road speed x terrain traversal coefficient + contour-crossing (slope)
  penalty; all coefficients in a config file, editable without touching code.
- Route rules: start = finish (single hub), score maximised, late return costs points per minute
  (penalty coefficient configurable).
- Solvers: exact Held-Karp for small instances (and as the test oracle) + heuristic
  (GRASP/ILS-style local search) for 30-80 controls.
- Delivery: Python CLI producing JSON + a rendered PNG overlay, plus a local web viewer to upload a
  map, set parameters, inspect the route, and fix mis-detected controls.

## Out of scope
- GPS georeferencing and GPX export (explicitly declined for v1).
- Any hosted service, accounts, multi-user, or persistence beyond local files.
- VLM / paid API calls for control detection.
- Fatigue modelling (speed decaying over the distance) — deferred, it breaks distance-matrix
  precomputation.
- Automatic scale detection from the map's scale bar.
- Mobile app, offline packaging, installers.

## Constraints
- Stack: Python. Deterministic CV first (OpenCV / NumPy / scikit-image), PyTorch + SegFormer only in
  the optional training milestone. Local web viewer served by the same Python process.
- Hosting: local only, `localhost`.
- Auth: none.
- Integrations: none required.
- Languages: user-facing UI and chat in Russian; all code, docs, and identifiers in English.
- A11y: keyboard-operable viewer, readable contrast; not a public site, so no formal WCAG target.
- Environment: Windows 11 host, Python 3.14.3 on host, Docker 29.3.1 + Compose v5.1.1 available,
  NVIDIA RTX 3060 Ti (8 GB VRAM) local. Tests run via `docker compose run --rm tests` — pytest hangs
  on the Windows host. Inference must stay CPU-only capable; GPU is for the optional training stage.

## Brand & content
- Tone: instrument, not a toy. Dense, map-like, quiet chrome — the map is the interface.
- Visual references: the article's route renders; OCAD/ISOM cartography itself.
- Copy source: draft OK (Russian UI strings).
- Imagery: the user's own map rasters.

## Acceptance bar (user words)
- «Достижение результата, когда программа будет строить качественный маршрут, как в статье,
  желательно не хуже качеством.»
- Verification: solver self-check (heuristic vs exact Held-Karp gap on small instances, reported
  numerically) plus the owner's own eyeball verdict on their own map.

## Data the owner can supply (offered 2026-08-19)
- 200+ scanned maps, a couple of `.ocd` files, and willingness to help with whatever unblocks the
  build. Sized by role in ADR-010: 10-20 scans retire the palette risk (T017), the full 200+ are M7
  training data (T070), the `.ocd` files may yield symbol-exact ground truth (T006 spike).

## Open questions
- Path on disk for the corpus, once assembled → `data/maps/` (gitignored, layout in T005).
- Is OCAD itself available for rendering `.ocd`, or do we install OpenOrienteering Mapper? (T006)
- One map with the owner's own reference route (time limit, pace, control order) — the acceptance
  oracle for "не хуже качеством".
- Controls list with points for one event, and the DPI/scale the scans are made at.
