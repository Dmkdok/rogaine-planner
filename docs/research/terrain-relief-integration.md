# Terrain relief (elevation/DEM) integration — research and options

Research/prep only, per **ADR-028** (`docs/DECISIONS.md`). No code, no config, no SPEC changes.
Produced for T096 (Iteration I4, M11) to inform a future gated iteration, not to start one. Where
this document presents options it does not pick between them — see §6, which the owner still has
to resolve.

## 1. What exists today (grounding)

The current pipeline, exactly as implemented, so the proposals below plug into a real contract
rather than a guessed one:

- `TerrainMap` (`src/rogaine/models.py:215-234`) carries `labels` (per-pixel terrain class),
  `contour_density` (H×W float32 in `[0, 1]`), and a single scalar `meters_per_pixel`.
- `contour_density()` (`src/rogaine/vision/contours.py:55-87`) Gaussian-blurs the binary `contour`
  mask (the brown ISOM 101 ink, already separated by the palette classifier) with
  `config.slope.density_sigma_px(dpi)`. It is explicitly *not* a slope: "a single contour crossing
  is a thin, discrete event; what actually correlates with slope is how many of them sit near a
  given point" (module docstring).
- `k_slope(density, config)` (`contours.py:90-118`) is `1 / (1 + penalty * density)`, `penalty`
  from `config/default.toml`'s `[slope]` (currently `2.0`). Its own docstring states the limit
  plainly: "the signature takes only a density field — no 'from' pixel, no 'to' pixel, no travel
  direction ... a leg costs the same in both directions." This is ADR-006's accepted trade-off, not
  an oversight.
- `compute_cost_field()` (`src/rogaine/cost/field.py:50-91`) computes
  `t = mpp / (v_base * k_terrain * k_slope)` **per pixel**, isotropically: one scalar
  `seconds_per_pixel[y, x]`, no direction of travel anywhere in the computation. This is the
  structural reason direction-blindness cannot be fixed by feeding a smarter number into
  `k_slope` alone — see §4.
- Scale, not georeference: `mpp_from_dpi()` (`src/rogaine/io/scale.py:14-25`) —
  `mpp = (25.4 / dpi) * scale_denominator / 1000` — turns the map's own printed scale ratio
  (1:N) and scan DPI into ground metres per pixel; `Calibration` (`io/scale.py:28+`) does the same
  from two picked points and a known ground distance. Both give a **uniform ratio**: how big one
  pixel is on the ground. Neither gives an **origin, orientation, or projection**: where any given
  pixel actually sits on the Earth. That distinction is the crux of §2 and §6.
- The 17-class speed table (`config/default.toml`'s `[[terrain]]` blocks): a static `speed_factor`
  per ISOM class, sourced from ISOM 2017-2's symbol descriptions and the reference article's rough
  ratios, shared by every runner and every run. See §5.
- Two prior decisions this document revisits without overturning: **ADR-006** (contour density
  instead of DEM reconstruction, "a project of its own and fragile on a raster where contours are
  broken by symbols and text") and **ADR-007** (no georeferencing/GPX in v1 — "adding it later
  means a two-point affine calibration and a GPX writer, additive rather than structural").

## 2. External elevation data sources — feasibility given the Non-goals constraint

### 2.1 Global satellite-derived DEMs

| Source | Resolution | Reported vertical accuracy (RMSE) | Notes |
|---|---|---|---|
| SRTM | 30 m (global 1-arcsec release, was 90 m outside the US before 2015) | ~7.25 m | C-band radar; partially penetrates canopy but still biased high over dense forest |
| ASTER GDEM | 30 m | ~8.12 m | Optical stereo; noisier, more artefacts, but sometimes better in high-relief mountain terrain |
| Copernicus GLO-30 / NASADEM | 30 m | Best of the "raw" global set in recent comparisons | Copernicus is explicitly a **DSM** (surface, including canopy and buildings) |
| FABDEM | 30 m (derived from Copernicus) | ~6.53 m, ranked first in a recent multi-DEM comparison | Corrects Copernicus specifically for forest-canopy and building bias |

Sources: [OpenTopography — ASTER GDEM vs SRTM](https://opentopography.org/blog/comparison-aster-gdem-srtm),
[MDPI 12(21):3482 — vertical accuracy of ASTER/AW3D30/MERIT/TanDEM-X/SRTM/NASADEM](https://www.mdpi.com/2072-4292/12/21/3482),
[Tandfonline — Copernicus/NASADEM/ASTER/AW3D assessment](https://www.tandfonline.com/doi/full/10.1080/10095020.2023.2296010),
[OpenTopography — Copernicus GLO-30](https://portal.opentopography.org/raster?opentopoID=OTSDEM.032021.4326.3),
[Copernicus Data Space — COP-DEM description](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM).

**Why the DSM/DTM distinction matters specifically for this project:** this project's own
17-class table is dominated by forest classes — `forest_runnable`, `veg_slow_run`, `veg_walk`,
`veg_fight` are four of the five most common non-trail classes. A DSM reports the top of the
canopy, not the ground a runner is actually on; canopy-height noise varies pixel-to-pixel far more
than real ground slope does over the same distance, so sampling SRTM/ASTER/plain-Copernicus
directly under dense forest risks a *worse* slope signal than today's contour-density proxy, not a
better one. FABDEM is the one product in this set built specifically to correct that bias and
would be the safer first candidate of the global DEMs, license terms permitting (verify at
acquisition time — this document doesn't certify its licence).

Access: all four are queryable through [OpenTopography's Global Dataset API](https://portal.opentopography.org/datasetMetadata?otCollectionID=OT.032021.4326.1)
(free personal API key) or the [AWS Registry of Open Data](https://registry.opendata.aws/copernicus-dem/)
for Copernicus specifically — both need a **lat/lon (or projected-CRS) bounding box or point list**
as the query, which is exactly the information this project's pixel-space pipeline does not have
(§2.4).

### 2.2 National LIDAR-derived DTMs

Bare-earth (ground-only, not canopy-top) LIDAR DTMs are the accuracy tier above the global
products above, where they exist. Worked example: the US **USGS 3DEP** programme publishes 1 m
bare-earth DTMs derived from LIDAR across most of the conterminous US, public domain, queryable via
[OpenTopography's USGS 1m DEM dataset](https://portal.opentopography.org/datasetMetadata?otCollectionID=OT.012021.4269.3)
or [The National Map downloader](https://www.usgs.gov/the-national-map-data-delivery/gis-data-download).
Several other national mapping/cadastre agencies publish comparable open LIDAR-derived DTMs for
their own territory (see the roundup at [GIS Geography — Top 6 Free LiDAR Data Sources](https://gisgeography.com/top-6-free-lidar-data-sources/));
coverage, resolution, format and licence all vary per country and would need a per-map lookup —
not researched exhaustively here, flagged as a real option with per-map effort attached.

This tier removes the DSM/canopy-bias concern from §2.1 (true bare-earth) but does not remove the
georeferencing requirement — see §2.4.

### 2.3 Manual elevation input

An organiser or map preparer could type in known spot heights — index-contour labels, a start
point's known altitude, a few peaks — by hand. Cheapest to build, but it still has to answer "at
*which pixel*" for each entered value, which is the same coordinate-mapping question as §2.1/2.2
unless the values are entered as *contour-line* elevations rather than point elevations, in which
case this option converges with §3 rather than staying a DEM source.

### 2.4 The common blocker

Every option in §2.1-2.3 needs, at minimum, a way to answer "what are the real-world coordinates
of pixel (x, y)?" — a DEM API call needs a lat/lon; a manual spot height needs to know which pixel
it labels. The project currently has only the scalar in §1 (`meters_per_pixel`): how big a pixel
is, not where it is. Turning a scan into something a DEM API can query needs a genuine
**georeference** — an origin, an orientation, and (for anything beyond a purely local patch) a
projection — which is precisely SPEC's Non-goals line ("GPS georeferencing, GPX export, GeoTIFF,
world files") and precisely what ADR-007 declined for v1. This is not a decision this document
makes; it is stated as the open question in §6.

## 3. Contour-line-only reconstruction (stays inside the map's own pixel space)

An alternative that needs no external data and no georeference: reconstruct a *local, relative*
elevation surface directly from the printed contour lines already on the map, entirely in pixel
space.

**What's already extracted, reusable as a starting point:** `contour_mask()`
(`contours.py:40-52`) — the binary brown-ink mask, already isolated by the palette classifier.
T014's linear-feature extraction (`vision/linear.py`, skeletonisation, width/elongation filtering)
is architecturally the closest prior art in this codebase for turning ink into vectorised
geometry, though it targets roads/tracks/paths, not contour topology.

**What's needed beyond what exists — new work, not a config tweak:** contour *vectorisation and
topology* — tracing each line into an ordered curve, closing loops, and bridging the breaks the
mask has wherever a symbol or label overprints a line. `contours.py`'s own module docstring already
names this exact fragility as ADR-006's reason for not attempting it originally: "fragile on a
raster where contours are broken by overprinted symbols and text." A density blur tolerates gaps
gracefully; a vectoriser that needs continuous lines to establish adjacency does not — this is a
materially harder vision problem than what exists today, not an incremental extension of it.

**Established algorithms — prior art to build on, not reinvent:**
- ANUDEM / ArcGIS "Topo to Raster" (Hutchinson 1988-2011): a hydrologically-constrained
  interpolator purpose-built for contour input, reads points off each contour and imposes drainage
  consistency — see [Esri — How Topo to Raster works](https://pro.arcgis.com/en/pro-app/latest/tool-reference/3d-analyst/how-topo-to-raster-works.htm).
- Weighted moving average (Watson 1992): interpolates a grid value from geometric relationships
  between adjacent contour lines via inverse-distance weighting.
- Contour dilation, iterative erosion (Taud/Parrot/Alvarez 1999), and medial-axis interpolation:
  simpler, lower-cost alternatives for the same problem.
- Survey: [A combined contour-lines iteration algorithm and Delaunay triangulation](https://www.tandfonline.com/doi/full/10.1080/10095020.2022.2070553),
  [DEM interpolation via medial axis transformation](https://link.springer.com/chapter/10.1007/978-3-642-31125-3_17).

**What CAN be recovered without any georeference — the key finding of this section:**
- The **relative elevation gain** between two adjacent contour lines is exactly the configured
  contour interval. ISOM 2017-2 standardises this at 2 or 2.5 m, with every fifth line drawn
  bolder as an index contour (10 or 12.5 m) — see [O-Map Wiki — Index contour](https://omapwiki.orienteering.sport/symbols/102-index-contour/)
  and [ISOM 2017-2 (IOF)](https://www.swiss-orienteering.ch/files/kommission_karten/ISOM_2017-2_IOF.pdf).
  This value is a map-metadata constant, not something that needs measuring per map.
- **Local gradient from spacing.** Given the perpendicular spacing `s` between two adjacent
  contour lines (pixels, measured on the vectorised geometry) and the interval `h` (metres, from
  the constant above), the slope is `atan(h / (s * mpp))` — using the *existing*
  `meters_per_pixel` from §1, not a new coordinate system. This is the same class of arithmetic
  `io/scale.py` already performs and the project already trusts (`mpp_from_dpi`); it needs no
  origin, no orientation, no projection — only the map's own already-established scalar scale plus
  vectorised, topologically-connected contour geometry. **This means full local-gradient
  reconstruction does not, by itself, require reopening the Non-goals georeferencing line** — only
  §2's *external DEM sampling* does. That is the concrete boundary this document draws between "in
  scope without a Non-goals reversal" and "needs one."

**What CANNOT be recovered:**
- Absolute elevation — not actually needed for a slope-driven cost field, which only needs relative
  steepness.
- **Uphill/downhill direction at a bare crossing.** Contour spacing alone is symmetric: a tightly
  packed set of lines looks identical whether it's a hill or a depression. Resolving the sign needs
  one of: (a) closed-loop topology plus a convention (e.g. index-line thickening direction, form
  lines/hachures where drawn), (b) OCR'ing index-contour elevation labels and propagating them by
  adjacency — the same fragility class SPEC's Risk #4 already flags for control-number OCR, "the
  most fragile step" — or (c) a handful of known spot heights (§2.3) to anchor the sign locally.
  None of these is free; all are new work beyond vectorisation itself.
- Sub-interval detail: a uniformly-sloped flank and a stepped terrace both look identical from
  spacing alone when the step is smaller than one contour interval (2-2.5 m).
- Overall reliability is bounded twice over: by the printed contour interval itself (a hard floor
  on vertical resolution no algorithm recovers past), and by how intact the vision pipeline's
  extracted mask is where real maps overprint contours with symbols and text.

**Feasibility verdict:** real and bounded, with no Non-goals conflict for the gradient-from-spacing
core — but it is a genuine new vision milestone (contour vectorisation + topology + optional
index-label OCR for direction), not a config tweak, and a separate line of work from the
DEM-sourcing path in §2. The two are not mutually exclusive: §3 could supply a *direction-blind but
now-real-gradient* signal on its own, with §2's external elevation (once/if georeferencing is
resolved) supplying direction on top.

## 4. Plugging a real slope signal into `k_slope` / `compute_cost_field`

**Why direction cannot fit into today's contract no matter what values are computed.**
`compute_cost_field` produces one scalar `seconds_per_pixel[y, x]` per pixel — an isotropic cost
with no "from" or "to." Slope direction is a property of an *edge* (a pair of pixels), not of a
single pixel. This means the fix is not "compute a better `k_slope`" — any per-pixel array,
however derived, is structurally incapable of representing "costs more this way than that way."
The real plug-in point has to sit one level up, wherever per-pixel costs become graph **edges**
(the downsampling step referenced by `config/default.toml`'s `[graph]` section, T031 — out of this
document's read scope, but the only place a "from" pixel and a "to" pixel coexist simultaneously).

**Two concrete, non-breaking-by-default seams**, for whoever scopes the future implementation:

1. `TerrainMap` gains an optional new field carrying real elevation information — e.g.
   `elevation: np.ndarray | None` (metres, relative or absolute) or a directional gradient pair
   `(dz_dx, dz_dy)` — populated from either §2 (a sampled DEM, once georeferencing is resolved) or
   §3 (reconstructed from contour spacing). `None` preserves every current behaviour exactly:
   `compute_cost_field`'s existing isotropic `seconds_per_pixel` contract stays untouched as the
   fallback path, so this is additive to `models.py`'s frozen contract (ADR-008), not a break of
   it.
2. The directional cost itself gets computed where graph edges are built, not inside
   `compute_cost_field`. For an edge from pixel A to pixel B: `rise = elevation[B] - elevation[A]`,
   `run` = horizontal ground distance along that edge (from the downsample factor and
   `meters_per_pixel`, already known quantities). **Tobler's hiking function** is the standard,
   well-documented off-the-shelf model for turning that `(rise, run)` pair into a direction-aware
   speed multiplier: `V = 6 · exp(−3.5 · |S + 0.05|)` km/h, `S = rise/run`, asymmetric around zero
   (downhill is faster than flat up to roughly −2.86°, then slows again on steep descents) — see
   [Wikipedia — Tobler's hiking function](https://en.wikipedia.org/wiki/Tobler's_hiking_function).
   Tobler's own model also publishes an **off-path multiplier of 3/5** applied to the on-path
   speed — direct prior art for the off-road/forest question in §5, worth noting there too. How
   this multiplier composes with the existing multiplicative `k_terrain` (replace it, multiply
   alongside it, or something else entirely) is an implementation-time modelling choice this
   document does not resolve.

No change to `compute_cost_field`'s signature, `CostField`'s fields, or `k_slope`'s contract is
proposed now — this section only names where the seam is for whoever scopes that iteration.

## 5. What a separate off-road/forest base-speed parameter needs

**What exists today:** `speed_factor` is static per ISOM class, defined once in
`config/default.toml`, shared across every runner and every run — map-dependent, not
runner-dependent.

**Gap 1 — category mismatch.** `base_speed_mps` is already explicitly treated as a *per-run*
parameter rather than config: `field.py`'s own module docstring gives the reason — "the same
terrain classification is reused across a runner's different attempts at different speeds." A
runner's off-road/forest aptitude (some runners are disproportionately slower off-trail regardless
of vegetation class — ankle strength, trail-running experience, footwear) is the same *kind* of
quantity: a property of the runner-on-this-day, not of the map. It belongs alongside
`base_speed_mps` as a second explicit per-run scalar argument, not as a new row in the
map-independent 17-class table.

**Gap 2 — a single scalar has a uniform-scaling ceiling.** One added multiplier scales all
sixteen non-road classes identically; it cannot express a runner who runs `rough_open` at normal
relative speed but is disproportionately worse in `veg_fight` specifically. Capturing that needs
either a per-class correction vector (up to 17 numbers, not one) or accepting the coarser
single-number model as a deliberate first approximation — a genuine trade-off to flag for the
owner, not a gap this document closes. (Tobler's own off-path 3/5 multiplier, §4, is exactly this
single-scalar approach in an established model — evidence it's a reasonable starting
approximation, not evidence it's sufficient long-term.)

**Gap 3 — no calibration data exists.** Fitting either a 1-parameter or a 17-parameter model needs
real performance samples: GPS-tracked splits (or timed segments) run against terrain the vision
pipeline has already classified, across enough runners and enough terrain variety to fit something
more than a guess. Nothing in the project today collects that. This is a prerequisite for
calibrating *any* such parameter, not a detail to solve inside a future implementation task — it
needs its own data-collection story first.

## 6. Open question for the owner — georeferencing (not decided here)

ADR-028 assigns this decision to the owner explicitly; this document lays out the options without
picking one.

- **Option A — reopen Non-goals, add a georeferencing step.** Gains access to §2's external DEM
  sources (FABDEM/national-LIDAR forest-bias caveats still apply). Real scope growth: needs an
  origin, orientation, and (for anything beyond a small local patch) a projection — not the
  scalar-only scale the project has today. ADR-007's own wording, written when georeferencing was
  declined, is worth re-reading here: "adding it later means a two-point affine calibration and a
  GPX writer, additive rather than structural" — suggesting a *minimal* version (a small number of
  known-coordinate anchor points, enough to locate the map's controls on a DEM, not a full GIS
  reprojection pipeline) might be a materially smaller decision than "add georeferencing" sounds.
  Whether that minimal version still counts as reopening the Non-goals line in spirit, or is a
  distinct and smaller decision, is itself part of what needs the owner's call.
- **Option B — stay inside pixel space, pursue §3 only.** No Non-goals conflict, no external data
  dependency, no per-map licence/coverage lookup. Bounded by the printed contour interval and by
  how intact the extracted contour mask is on a given scan. Needs new vision work (vectorisation +
  topology, optionally index-label OCR for direction) that doesn't exist yet in any form.
  Direction-blind unless the topology/OCR pieces are also built.
  Realistically the largest amount of *new* engineering per unit of resolved georeferencing risk.
- **Option C — manual per-map elevation input.** Smallest immediate engineering footprint (a data
  entry step, not new vision), but recurring: a workflow cost every future map pays, and it still
  needs to answer the "at which pixel" question from §2.4/§2.3 for point input, or converges into
  §3 for contour-line input. Could supplement either A or B rather than replace them (e.g. spot
  heights anchoring the sign for §3's gradient).

This tension — a scanned/photographed orienteering map has no known real-world georeference by
design, and every external elevation source needs one — is stated here as the open question T096
was scoped to surface, not resolved unilaterally by this document.

## Sources

- [OpenTopography — Comparison of ASTER GDEM to SRTM](https://opentopography.org/blog/comparison-aster-gdem-srtm)
- [MDPI Remote Sensing 12(21):3482 — Vertical Accuracy of Freely Available Global DEMs](https://www.mdpi.com/2072-4292/12/21/3482)
- [Taylor & Francis — Assessment of Copernicus, NASADEM, ASTER, AW3D in Central/Southern Africa](https://www.tandfonline.com/doi/full/10.1080/10095020.2023.2296010)
- [OpenTopography — Copernicus GLO-30 DEM dataset](https://portal.opentopography.org/raster?opentopoID=OTSDEM.032021.4326.3)
- [OpenTopography — Copernicus Global DEM metadata / API](https://portal.opentopography.org/datasetMetadata?otCollectionID=OT.032021.4326.1)
- [Copernicus Data Space Ecosystem — COP-DEM description](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM)
- [Registry of Open Data on AWS — Copernicus DEM](https://registry.opendata.aws/copernicus-dem/)
- [OpenTopography — USGS 1 m DEM (3DEP)](https://portal.opentopography.org/datasetMetadata?otCollectionID=OT.012021.4269.3)
- [USGS — The National Map data delivery](https://www.usgs.gov/the-national-map-data-delivery/gis-data-download)
- [GIS Geography — Top 6 Free LiDAR Data Sources](https://gisgeography.com/top-6-free-lidar-data-sources/)
- [Esri — How Topo to Raster works (ANUDEM)](https://pro.arcgis.com/en/pro-app/latest/tool-reference/3d-analyst/how-topo-to-raster-works.htm)
- [Taylor & Francis — Combined contour-lines iteration + Delaunay triangulation for terrain modelling](https://www.tandfonline.com/doi/full/10.1080/10095020.2022.2070553)
- [Springer — DEM Interpolation from Contours Using Medial Axis Transformation](https://link.springer.com/chapter/10.1007/978-3-642-31125-3_17)
- [O-Map Wiki — 102 Index contour](https://omapwiki.orienteering.sport/symbols/102-index-contour/)
- [ISOM 2017-2 (IOF, adjusted January 2019)](https://www.swiss-orienteering.ch/files/kommission_karten/ISOM_2017-2_IOF.pdf)
- [Wikipedia — Tobler's hiking function](https://en.wikipedia.org/wiki/Tobler's_hiking_function)
