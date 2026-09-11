# Route-Choice Heuristics in Orienteering and Rogaining

A synthesis of published orienteering coaching materials, racing strategy guides, and practitioner experience to inform cost-model engineering.

## Overview

Experienced orienteers and rogainers apply a set of learned heuristics when choosing between route options. These heuristics are grounded in:
- Trade-offs between distance, climbing, vegetation density, and navigation risk
- The asymmetric cost of navigation errors (relocation and misnavigation typically exceed route-choice mistakes)
- Psychological and physical fatigue under terrain difficulty
- The value of linear features (paths, fences, streams) as "handrails" and confidence anchors

This document distills nine concrete rules from published sources that a route-costing algorithm could plausibly encode.

## Verification note (T094, second pass)

This document was drafted by a `haiku`-tier pass (ADR-027) and then verified source-by-source:
every cited URL was fetched directly and checked against the specific claim it was attributed to,
with a search-engine fallback where a fetch failed. Two sources did not hold up: one (`baoc.org`'s
"Attack_Point" wiki page) turned out to be a generic links directory, cited in the draft as if it
discussed both handrails and attack points, when it discusses neither — removed. Another
(Orienteering USA's "root cause" route-analysis article) was cited for Rule 4's core empirical claim
but does not make that comparison anywhere in its text — removed and replaced with a source that
does. Several specific numbers in the draft (a "~5 contour lines" climb/contour threshold, a
"5-10 seconds per control" safety-margin figure, "5-15 seconds per leg" catching-feature savings, a
"10-20% fatigue" late-event speed penalty, numeric pace-percentage bands for Rule 8) do not appear
in any source checked and have been removed as unsupported rather than left in place. Two corrected
sources are added (a North West Orienteering Club article for Rule 9's actual "stay inside the line"
source, and a Human Kinetics article for Rule 3's backward-planning technique). Every remaining
claim below is either a direct quote from a fetched source or explicitly marked as inference. Each
rule's "Cost model mapping" note has also been re-checked against this codebase's actual
`config/default.toml` and `src/rogaine/cost/`/`solve/` code, not just asserted — several rules turn
out to already be implemented, and one (Rule 1) turns out to be handled more precisely by the
existing Dijkstra solve than the literature's own rule-of-thumb threshold.

---

## Route-Choice Rules

### Rule 1: Path-vs-Direct Terrain Tradeoff

**If** a direct line through terrain is shorter than a path-based detour, **then** prefer direct
terrain when its runnability is roughly 60% or more of path speed; below that, whether the path is
worth taking depends heavily on the leg's geometry (how far the control sits from the path, and at
what angle) — not on one universal percentage.

- **Verified thresholds** (from [Derwent Valley Orienteers](https://derwentvalleyorienteers.org.uk/2026/09/06/route-choice-path-versus-direct/), a worked numerical analysis of three real leg geometries):
  - Terrain runnability ≥60% of path speed: direct wins in every case examined ("Go Straight").
  - Same leg, runnability ≤50%: the path saves only ~13s (3.5% of leg time) — a small edge.
  - A leg where the control sits deep into the terrain (path detour far off the direct line): even at 40% terrain runnability, the path shows "no benefit in any path running" — direct still wins.
  - A leg where the control sits close to the path (the detour is nearly on-line): 70% terrain runnability still saves 14s (5.5%); 50% saves 59s (16.5%).
- **Correction**: the earlier draft collapsed these three distinct leg geometries into one flat "40–50%: saves 13–59s" range and asserted a "<30%: path strongly preferred" threshold the source never states. The real finding is that the runnability threshold shifts with how far off-line the path detour runs — there is no single cutoff.
- **Cost model mapping**: Already handled — and more precisely than the literature's own rule of thumb. `cost/graph.py` builds a full 8-connected grid over the per-pixel `CostField` and `solve`'s multi-source Dijkstra (ADR-002) already finds the true minimum-time path through it. That *is* the continuous version of this heuristic: a human uses "60% runnability" as a mental shortcut for a tradeoff the solver already computes exactly, pixel by pixel, given accurate `speed_factor`s. No new mechanism, no new tuning — the existing `[[terrain]]` table (`config/default.toml`) already puts every off-path class below 60% of road speed (`open_land` 0.55 down to `veg_fight` 0.05), so the solver already prefers a path/road detour over cross-country travel whenever the literature says it should. This means the owner's "cuts through slow terrain implausibly" complaint (ADR-027's Context) is **not** explained by a Rule‑1‑shaped gap — it points at the rules below instead (missing handrail/catching-feature attraction, Rules 2 and 7).

**Source**: [Derwent Valley Orienteers](https://derwentvalleyorienteers.org.uk/2026/09/06/route-choice-path-versus-direct/) (verified — live numeric worked example), [Orienteering ACT Lesson 12](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-12-route-choice/) (verified — general distance/climb/forest-thickness/track-vs-terrain framing, no numbers)

---

### Rule 2: Handrails and Linear Features Reduce Navigation Risk and Enable Speed

**If** a linear feature (path, stream, fence, ridge, powerline) runs parallel to or near a control,
**then** prefer routes that stay on or close to it, even where the direct bearing is geometrically
shorter.

- Handrails cut mental navigation load, verified directly: "It takes much less concentration to follow a handrail than a compass bearing and is usually more accurate" ([Michigan Adventure Race](https://miadventurerace.com/navigation-lesson-5-handrails/)).
- Not unconditional — the same source explicitly warns that winding, thickly-vegetated, or deadfall-prone handrails "can backfire," so following one is a strategic choice, not a reflex.
- [Better Orienteering](https://betterorienteering.org/intermediate-techniques/) lists "following a Hand Rail" as one of its core route-choice strategies, alongside attack points and catching features (verified — substantive article content, not a link index).
- **Correction**: the earlier draft also cited `baoc.org/wiki/.../Attack_Point` here. Fetched directly: that page is BAOC's general resources/links directory (external links to Attackpoint.org, OCAD, course-design tools) — it does not discuss handrails, or navigation technique at all. Removed. This is the mischaracterized source the T094 intake spot-check flagged.
- **Cost model mapping**: New mechanism required — the current per-pixel cost field (`cost/field.py`) has no proximity/attraction term; a pixel one metre off a path gets no benefit from that path today. A distance-decay bonus keyed to distance-to-nearest-linear-feature is buildable cheaply on top of `vision/linear.py`'s existing corridor extraction (T014) as a new `cost/field.py` term — a new cost coefficient, not a new search algorithm, so still inside T095's stated `cost/`-level budget (ADR-027).

**Source**: [Michigan Adventure Race: Handrails](https://miadventurerace.com/navigation-lesson-5-handrails/) (verified), [Better Orienteering: Intermediate Techniques](https://betterorienteering.org/intermediate-techniques/) (verified)

---

### Rule 3: Attack Points Anchor the Final Approach, and Are Planned Backwards

**If** a control lies in complex or featureless terrain, **then** identify a clear attack point (an
obvious feature near the control) and plan the route to arrive there confidently — treating the
final approach, not the leg's geometric middle, as the highest-risk segment.

- Definition and risk claim, both verified directly: "An attack point is a large or obvious feature near the control that will be easy to find," and "If there is no obvious attack point, it is a warning that extra care must be taken" ([Orienteering ACT Lesson 8](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-8-attack-points/)).
- Backward planning is a real, named, sourced technique — the CAR method (Control → Attack point → Route), verified directly: "you find the closest feature near the control... to use as a good attack point, and then you work your route backward... from where you are. If you start route planning from where you are and work toward the control, you will tend to move in increments, often causing you to miss better routes." Attributed there to Winnie Stott, *Armchair Orienteering II* (1987, Canadian Orienteering Federation) ([Human Kinetics: Five Techniques](https://us.humankinetics.com/blogs/excerpt/five-techniques-that-are-the-key-to-successful-orienteering)).
- **Correction**: the earlier draft's "practiced by elite orienteers... forward planning is suboptimal, per a British study" framing does not trace to any source checked (including a general web search for the underlying study) — dropped. The CAR-method citation above is a directly-quoted, correctly-attributed replacement for the same underlying claim.
- **Cost model mapping**: Not expressible in the current model, which has no notion of "which feature is the attack point for this control" or any backward-from-control planning bias. Confirmed **deferred** — this is ADR-027's own worked example of a rule needing a concept the codebase doesn't have.

**Source**: [Orienteering ACT Lesson 8](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-8-attack-points/) (verified), [Human Kinetics: Five Techniques](https://us.humankinetics.com/blogs/excerpt/five-techniques-that-are-the-key-to-successful-orienteering) (verified), [Better Orienteering: Intermediate Techniques](https://betterorienteering.org/intermediate-techniques/) (verified)

---

### Rule 4: Navigation-Error Cost Exceeds Route-Optimization Gain

**If** choosing between a slightly shorter/faster route and a navigationally simpler one (more
handrails, clearer catching features), **then** the literature consistently favors the simpler
route — errors cost more than the optimization saves.

- Core claim, verified directly: "the most important consideration is to choose a route that minimises the risk of errors by utilising line features and picking a strong attack point," because "more time is lost making navigational errors than from poor route choice" — stated as true even for elites ([Orienteering ACT Lesson 12](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-12-route-choice/)).
- Indecision has a measured cost, verified directly: "If indecision adds in more than 30 seconds you would probably have been better off just getting on with your first choice," and separately, "it is easy to lose 10 seconds a leg by stopping too much — with 15 legs on a course that is 2.5 minutes" ([Better Orienteering: Intermediate Techniques](https://betterorienteering.org/intermediate-techniques/)).
- **Correction**: the earlier draft's specific "accept a 5–10 second detour per control" figure, and its citation of [Orienteering USA's route-analysis article](https://orienteeringusa.org/2026/08/from-time-loss-to-root-causea-practical-approach-to-route-analysis/) for it, do not hold up. Fetched directly: that article's only relevant case study (a competitor losing ~50s to indecision) is classified there as a *route-choice* mistake, not a navigation error, and the article draws no comparison between the two categories' typical costs. Removed as a citation for this rule; the "10s/leg" and "30s indecision" figures above (both directly quoted from a verified source) replace it as the rule's actual quantitative grounding.
- **Cost model mapping**: Not independently expressible — this rule is the *rationale* for Rules 2 and 7's proximity mechanism (handrails, catching features), not a separate cost term. Once those exist, "navigationally safer" routes already cost less by construction; there is no separate "risk penalty" to add on top without double-counting the same effect.

**Source**: [Orienteering ACT Lesson 12](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-12-route-choice/) (verified), [Better Orienteering: Intermediate Techniques](https://betterorienteering.org/intermediate-techniques/) (verified)

---

### Rule 5: Vegetation Runnability Classes Are Already IOF-Standard Percentages

**If** a terrain segment is classified by ISOM vegetation symbol, **then** its speed factor should
follow the IOF's own published runnability bands, expressed as a fraction of open-forest speed.

- Verified directly against the primary IOF-derived source, read in full ([BKO: Know Your Vegetation](https://www.bko.org.uk/sites/default/files/basicpage/KYS-Vegetation.pdf), PDF): "Forest: easy running" 80–100%, "Forest: slow running" 60–80%, "Forest: difficult to run" 20–60%, "Vegetation: very difficult to run, impassable" 0–20% (all as a fraction of open-forest running speed) — with an equivalent pair of bands (60–80%, 20–60%) for dense *undergrowth* (brambles, bracken, cut branches) independent of tree density.
- Cross-checked against ISOM symbol 407 via a search-engine index (direct fetch returned HTTP 403, likely bot-blocking rather than a dead page — a second independent search snippet gives the identical 60–80% figure): [O-Map Wiki, symbol 407](https://omapwiki.orienteering.sport/symbols/407-vegetation-slow-running-good-visibility-2/).
- **Correction**: the earlier draft's URL for this source (`.../407-vegetation-slow-running-good-visibility/`, missing a `-2` suffix) does not match the site's current path; corrected above.
- **Already implemented, closely calibrated — no T095 work needed**: `config/default.toml`'s own comments show this exact "% of open-forest speed" logic already drives the terrain table. `veg_slow_run` (ISOM 406) is commented `"60-80% of normal speed -> 0.7 x forest"`, giving `speed_factor = 0.25` against `forest_runnable`'s `0.35` (0.25/0.35 ≈ 0.71×, inside the 60–80% band). `veg_walk` (408) is commented `"20-60% -> 0.4 x forest"` (0.14/0.35 = 0.40, the band's own midpoint). `veg_fight` (410) is commented `"less than about 20% -> 0.15 x forest"` (0.05/0.35 ≈ 0.14, inside the band). This rule is already faithfully encoded, not merely "expressible."
- **Unsupported and separable**: the draft's second half of this rule — a persistent "fatigue" cost that degrades *later* performance, beyond the instantaneous speed reduction above — is not supported by either vegetation source; the BKO document's only related remark is that classification is "a judgement" call for the *mapper*, not a claim about runner fatigue carrying forward. It is also a materially different kind of mechanism: the existing per-pixel cost field assumes path-independent edge costs (needed for Dijkstra to be both correct and fast); a route-history-dependent fatigue term breaks that assumption and would need a different solver treatment, not just a new config knob. **Deferred**, separately from this rule's well-supported first half.

**Source**: [BKO: Know Your Vegetation](https://www.bko.org.uk/sites/default/files/basicpage/KYS-Vegetation.pdf) (verified, read in full), [O-Map Wiki: Vegetation Symbol 407](https://omapwiki.orienteering.sport/symbols/407-vegetation-slow-running-good-visibility-2/) (verified via search index; direct fetch returns HTTP 403)

---

### Rule 6: Contour Density Already Drives a Climbing Penalty; No Literature Threshold Exists for "Contour vs. Climb"

**If** a control lies across a hill, **then** the literature confirms climbing has a real,
height-proportional cost, and confirms "go over or round" is a real route-choice question — but
does **not** give any specific contour-count or distance threshold for choosing one over the other.

- Verified directly: "A 2 contour hill is a similar height to a two storey apartment block and doesn't take too much effort to climb. A 10 contour hill... is equivalent to a 10 storey apartment block and will take considerable time and effort to climb" — but the same lesson explicitly offers no specific contour count or building height at which contouring becomes preferable to climbing ([Orienteering ACT Lesson 10](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-10-improving-contour-navigation/)).
- **Correction**: the earlier draft's "~5 contour lines (~50m, a 5-storey building)" threshold does not appear in this source, or in either contours source checked below — it was fabricated. Removed; replaced with the honest "no fixed threshold in the literature" finding above.
- A distinct, real execution technique, verified via search index (see note below): on a genuinely steep slope, "climb or drop the full contour difference right at the start... then contour at the new level as fast as you can go," rather than contouring diagonally across the whole slope ([Wessex Orienteering Club: Contouring Technique](http://www.wessex-oc.org/2012/02/03/contouring-technique/)). The page itself now returns HTTP 404 on direct fetch — treat this link as a citation of record (the content is confirmed real via a second, independent search-engine snippet quoting the same passage), not a guaranteed-live reference.
- Confirmed as a real route-choice category (no new number, but grounds the concept): "over or round" and "down or round" legs are deliberately designed by course planners, per the IOF-affiliated source, read in full ([BKO: Know Your Contours](https://www.bko.org.uk/sites/default/files/basicpage/KYS-Contours.pdf), PDF).
- **Cost model mapping — split rule**: The height-proportional-cost half is **already a knob**. `[slope]` in `config/default.toml` already applies `speed /= (1 + penalty * density)` (`cost/field.py` via `vision/contours.k_slope`), i.e. cost already scales with contour density — this project's own established proxy for "how many contour lines cross this pixel" (ADR-006). T095 can cheaply retune `slope.penalty` (currently `2.0`) or reshape the density→penalty curve (e.g. make it convex, so dense contour crossings cost disproportionately more, matching the "10-storey climb is not just 5× harder than 2-storey" intuition above) — no new mechanism. The *directional* half of this rule (uphill costs more than downhill, which is what "go around vs. over" actually trades off) is **not** expressible today — contour density cannot distinguish uphill from downhill, SPEC's own stated limitation — and is already the explicit subject of ADR-028's deferred DEM research. Penalty-shape retuning is in scope for T095; directional slope is deferred, cross-referenced to ADR-028/T096.

**Source**: [Orienteering ACT Lesson 10](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-10-improving-contour-navigation/) (verified), [Wessex Orienteering Club: Contouring Technique](http://www.wessex-oc.org/2012/02/03/contouring-technique/) (verified via search index only — direct fetch 404s), [BKO: Know Your Contours](https://www.bko.org.uk/sites/default/files/basicpage/KYS-Contours.pdf) (verified, read in full)

---

### Rule 7: Catching Features Let a Runner Simplify a Leg and Commit to Speed

**If** a route option has an obvious feature beyond the control that will "catch" an overshoot
(water, a major path, a fence line), **then** the leg can be run with less continuous map-checking,
using that feature as a confidence backstop.

- Verified directly: "Catching Features or Backstops... identify obvious features a short distance beyond the checkpoint that, when you arrive at them, tell you you've gone too far. Trails, roads, fences, streams, ditches, ridge lines, power lines, fields..." ([Michigan Adventure Race: Catching Features](https://miadventurerace.com/navigation-lessons-6-7-aiming-off-handrails/)).
- Also verified: "What Catching Feature will stop me just before the control, or afterwards if I miss it?" as a standard route-planning question ([Better Orienteering: Intermediate Techniques](https://betterorienteering.org/intermediate-techniques/)); picking "a large catching feature (such as a fence or track)" as a safety net ([Orienteering ACT Lesson 12](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-12-route-choice/)).
- **Correction**: no source checked gives a "5–15 seconds per leg" savings figure for this — dropped as unsupported.
- **Cost model mapping**: Same underlying mechanism as Rule 2, not a separate one — a catching feature is a handrail that happens to sit beyond the control rather than alongside the route. If Rule 2's proximity-bonus term is built, it already covers this rule with no extra code, only extending which features count as attractors (a control's own catching feature, not just en-route handrails).

**Source**: [Michigan Adventure Race: Catching Features](https://miadventurerace.com/navigation-lessons-6-7-aiming-off-handrails/) (verified), [Better Orienteering: Intermediate Techniques](https://betterorienteering.org/intermediate-techniques/) (verified), [Orienteering ACT Lesson 12](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-12-route-choice/) (verified)

---

### Rule 8: Pre-Committed Pace Segmentation ("Traffic Lights"), Not a Cost-Model Rule

**If** a leg has mixed terrain complexity, **then** pre-assign segments as green/orange/red by
confidence, and commit rather than re-deciding mid-leg — a real, well-sourced coaching heuristic,
but about how a runner executes an already-chosen route, not which route a solver should pick.

- Verified directly, both sources give the same three-tier scheme in the runner's own words: "sections – red = slow, orange = moderate speed, green = faster" ([Better Orienteering: Intermediate Techniques](https://betterorienteering.org/intermediate-techniques/)); "Green" for confident running on linear features, "Orange" for areas needing slower navigation, "Red" for very slow movement through complex terrain, plus "10 seconds can save 10 minutes!" on the value of a quick map check before committing ([Orienteering ACT Lesson 12](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-12-route-choice/)).
- **Correction**: the earlier draft's specific pace percentages (green 90–100%, orange 60–80%, red 20–40%) do not appear in either source — neither gives numeric pace bands, only the qualitative three-tier labels. Removed as unsupported; kept the qualitative scheme, which both sources do support.
- **Cost model mapping**: Unchanged from the draft's own conclusion — this is a route-*rendering*/pacing-advisory concept for a human runner, not a term in the per-pixel cost formula a solver optimizes. **Out of `cost/`/`solve/` scope entirely** — not merely deferred to a later iteration of the same work, but a different kind of feature (viewer/UX pacing guidance) that ADR-027 never asked T095 to build.

**Source**: [Better Orienteering: Intermediate Techniques](https://betterorienteering.org/intermediate-techniques/) (verified), [Orienteering ACT Lesson 12](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-12-route-choice/) (verified)

---

### Rule 9: Rogaine Time-Budget Buffering — Directly On-Domain, Not a Tangent

**If** planning a rogaine route to maximize points within a time limit, **then** build in a safety
margin against the final stretch — a concrete, sourced technique: mark a boundary at a fixed
distance from the finish and check progress against it well before the deadline, not only at the
deadline itself.

- **Correction, important**: the earlier draft's own cost-model note called this rule "not directly applicable to this project's orienteering focus." This project's own `docs/SPEC.md` title is "Rogaine Route Planner," solving the "Orienteering Problem" (maximize points within a time budget) — so rogaine-specific route-planning heuristics are, if anything, *more* directly on-domain than generic single-loop orienteering technique. That framing is corrected here.
- The "stay inside a boundary line" technique is real, but does not trace to the source the draft cited for it — verified directly at a different, corrected source: "I also draw on my map an arc that is one km from the finish... to ensure I am on or inside this line at the 80 minute mark" of that article's own worked 90-minute event — a ~10-minute buffer before the deadline, not a universal "80% of elapsed time" rule as the draft implied (the source gives one worked example, not a general percentage formula) ([North West Orienteering Club (NZ): Rogaine Planning](https://www.nwoc.org.nz/resources/rogaine-planning/)).
- Average-speed planning assumption, verified directly: "an average speed for working out your distance might be 4km/hr[, allowing] for negotiating fences, walking around unforeseen obstacles, stopping to look at your map" ([South Australian Rogaining Association: Route Planning](https://sarogaining.com.au/news/rogaining-tips-route-planning/)). The draft's added "~5 km/h brisk pace" does not appear in this source — it mentions 6km/h only as a treadmill-conditions contrast, not a field "brisk pace" figure — and is dropped.
- Iterative route-building, verified directly (same source): plan segment by segment and "piece together a full route," implicitly dropping low-value controls to fit the time budget — note this specific optimization (which controls to keep within a budget) is exactly what this project's existing solver (`solve/exact.py`/`solve/heuristic.py`, the Orienteering Problem solvers, F12/F13) already computes optimally; a human doing this by hand is solving the same problem this tool automates.
- Night-navigation team-task assignment, verified directly: "Some teams have one member pace counting, another marching on a compass bearing and the other closely following the map," with pace counts of "around 60" steps per 100m ([South Australian Rogaining Association: Night Navigation](https://sarogaining.com.au/news/rogaining-tips-night-navigation/)).
- **Unsupported and removed**: the draft's "final-stage fatigue reduces effective speed by 10–20%" figure does not appear in either SA Rogaining article, or anywhere else checked. Dropped.
- **Cost model mapping**: The buffer/margin idea is a genuine, cheap, in-domain `solve/`-level candidate — `RunConfig.time_limit_s` (`models.py`) already feeds `solve/objective.py`'s `overrun_s` computation; a new optional safety-margin config value (plan against a fraction of `time_limit_s`, report the real limit unchanged) needs no new search algorithm, just a smaller effective budget handed to the existing solver. The control-selection/route-building half needs no new work — it is what the existing exact/heuristic solvers already do. The team-task-division and pace-counting content is real but is execution advice for humans in the field, not something a route-costing algorithm expresses — noted, not actioned.

**Source**: [North West Orienteering Club: Rogaine Planning](https://www.nwoc.org.nz/resources/rogaine-planning/) (verified — new source, replaces a misattributed citation), [South Australian Rogaining Association: Route Planning](https://sarogaining.com.au/news/rogaining-tips-route-planning/) (verified), [South Australian Rogaining Association: Night Navigation](https://sarogaining.com.au/news/rogaining-tips-night-navigation/) (verified), [Orienteering USA: What is Rogaining](https://orienteeringusa.org/explore/what-is-rogaining/) (verified — general background/definition only: format, scoring, adaptability; not a source for any specific numeric claim above)

---

## Summary by Theme

| Theme | Rule | Mapping to Current Model |
|-------|------|--------------------------|
| Path vs. direct terrain | Rule 1 | Already solved exactly by the existing Dijkstra solve over the per-pixel cost field — no new work |
| Handrails / linear features | Rule 2 | New mechanism: proximity bonus, cheap (builds on existing `vision/linear.py` corridor extraction) |
| Attack points | Rule 3 | New concept needed — **deferred**, ADR-027's own worked example |
| Navigation risk vs. route optimization | Rule 4 | Rationale for Rules 2/7's mechanism, not its own separate cost term |
| Vegetation runnability (speed) | Rule 5, speed half | Already implemented and closely calibrated — no new work |
| Vegetation fatigue (carry-forward) | Rule 5, fatigue half | **Deferred** — breaks the per-pixel cost field's path-independence assumption |
| Slope penalty magnitude/shape | Rule 6, penalty half | Already a knob (`slope.penalty`); cheap to retune/reshape this iteration |
| Directional slope (uphill/downhill) | Rule 6, directional half | **Deferred** — needs DEM data, already ADR-028's scope |
| Catching features | Rule 7 | Same mechanism as Rule 2, no extra cost once that exists |
| Pace segmentation / traffic lights | Rule 8 | **Out of scope entirely** — viewer/UX pacing guidance, not a cost term |
| Rogaine time-budget buffering | Rule 9, buffer half | Cheap `solve/`-level config addition on top of existing `time_limit_s` |
| Rogaine control selection | Rule 9, selection half | Already solved by the existing exact/heuristic Orienteering Problem solvers |

---

## Key Takeaways for Engineering

1. Two rules turn out to already be correctly implemented (Rule 1's path-vs-terrain tradeoff, solved exactly by the existing Dijkstra solve; Rule 5's vegetation-speed percentages, already calibrated in `config/default.toml`'s own comments). Verifying this closes a question rather than opening a task — and it means the owner's "implausible route" complaint (ADR-027's Context) is not explained by either of these, pointing instead at the handrail/catching-feature gap below.
2. One new mechanism — a distance-to-nearest-linear-feature proximity bonus in the cost field — covers two rules at once (Rule 2 handrails, Rule 7 catching features) and is buildable on the linear-corridor extraction this project already has (T014/`vision/linear.py`). This is the single highest-leverage new mechanism this literature pass surfaced.
3. The slope-penalty magnitude (Rule 6) is already a knob and can be retuned or reshaped cheaply; the directional half of the same rule (contour-around vs. climb-over) is not — it needs real uphill/downhill data, which is explicitly ADR-028's separate, already-deferred research track.
4. Attack points (Rule 3) remain the literature's clearest example of a rule this codebase cannot express without a new concept, exactly as ADR-027 anticipated. Vegetation fatigue-carry-forward (half of Rule 5) turns out to be a second one, for a different reason: it needs path-history-dependent cost, which breaks the per-pixel independence that makes the existing Dijkstra-style solve both correct and fast.
5. Two rules are not cost-model material at all: pace segmentation (Rule 8) is a pacing/UI concept, and rogaine control-selection-under-budget (half of Rule 9) is already what the existing Orienteering Problem solver computes. Only Rule 9's safety-margin-buffer half is genuinely new, and it is cheap `solve/`-level work.

---

## Sources

All sources below were fetched and checked directly against the claims attributed to them in this
document (two via search-engine index only, noted inline and here, where a direct fetch failed).
Two sources present in the earlier draft (`baoc.org`'s "Attack_Point" wiki page — a links directory
misattributed as attack-point/handrail content — and Orienteering USA's "root cause" route-analysis
article — cited for a claim it does not make) were removed; they supported nothing in this document
after verification.

- [Better Orienteering: Intermediate Techniques](https://betterorienteering.org/intermediate-techniques/) — verified
- [Better Orienteering: Basic Techniques](https://betterorienteering.org/basic-techniques/) — verified, general background (not cited for a specific claim above)
- [Orienteering ACT: Lesson 12 – Route Choice](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-12-route-choice/) — verified
- [Orienteering ACT: Lesson 8 – Attack Points](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-8-attack-points/) — verified
- [Orienteering ACT: Lesson 10 – Contour Navigation](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-10-improving-contour-navigation/) — verified
- [Derwent Valley Orienteers: Route Choice Path vs Direct](https://derwentvalleyorienteers.org.uk/2026/09/06/route-choice-path-versus-direct/) — verified
- [Michigan Adventure Race: Handrails](https://miadventurerace.com/navigation-lesson-5-handrails/) — verified
- [Michigan Adventure Race: Catching Features & Aiming Off](https://miadventurerace.com/navigation-lessons-6-7-aiming-off-handrails/) — verified
- [South Australian Rogaining: Route Planning](https://sarogaining.com.au/news/rogaining-tips-route-planning/) — verified
- [South Australian Rogaining: Night Navigation](https://sarogaining.com.au/news/rogaining-tips-night-navigation/) — verified
- [Orienteering USA: What is Rogaining](https://orienteeringusa.org/explore/what-is-rogaining/) — verified, general background
- [North West Orienteering Club (NZ): Rogaine Planning](https://www.nwoc.org.nz/resources/rogaine-planning/) — verified; new source, correct attribution for Rule 9's boundary-buffer technique
- [Human Kinetics: Five Techniques That Are the Key to Successful Orienteering](https://us.humankinetics.com/blogs/excerpt/five-techniques-that-are-the-key-to-successful-orienteering) — verified; new source, correct attribution for Rule 3's CAR/backward-planning technique
- [O-Map Wiki: Vegetation Symbol 407](https://omapwiki.orienteering.sport/symbols/407-vegetation-slow-running-good-visibility-2/) — verified via search index (direct fetch returns HTTP 403)
- [BKO: Know Your Vegetation](https://www.bko.org.uk/sites/default/files/basicpage/KYS-Vegetation.pdf) — verified, read in full
- [BKO: Know Your Contours](https://www.bko.org.uk/sites/default/files/basicpage/KYS-Contours.pdf) — verified, read in full
- [Wessex Orienteering Club: Contouring Technique](http://www.wessex-oc.org/2012/02/03/contouring-technique/) — verified via search index only (direct fetch returns HTTP 404)
