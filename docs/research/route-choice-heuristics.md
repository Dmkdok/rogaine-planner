# Route-Choice Heuristics in Orienteering and Rogaining

A synthesis of published orienteering coaching materials, racing strategy guides, and practitioner experience to inform cost-model engineering.

## Overview

Experienced orienteers and rogainers apply a set of learned heuristics when choosing between route options. These heuristics are grounded in:
- Trade-offs between distance, climbing, vegetation density, and navigation risk
- The asymmetric cost of navigation errors (relocation and misnavigation typically exceed route-choice mistakes)
- Psychological and physical fatigue under terrain difficulty
- The value of linear features (paths, fences, streams) as "handrails" and confidence anchors

This document distills nine concrete rules from published sources that a route-costing algorithm could plausibly encode.

---

## Route-Choice Rules

### Rule 1: Path-vs-Direct Terrain Tradeoff

**If** a direct line through terrain is shorter than a path-based detour, **then** prefer direct terrain only if terrain runnability is ≥60% of path speed.

- **Quantitative thresholds** (derived from [Derwent Valley Orienteers](https://derwentvalleyorienteers.org.uk/2026/09/06/route-choice-path-versus-direct/)):
  - Terrain runnability ≥60%: direct route is faster
  - Terrain runnability 40–50%: path-based approach saves 13–59 seconds (3–17% of leg time)
  - Terrain runnability <30%: path-based approach is strongly preferred
- **Baseline assumption**: road/path speed ~6 min/km; terrain speed scales down as a percentage of this baseline.
- **Cost model mapping**: Existing terrain `speed_factor` knob handles this; rule is already expressible via tuning k_terrain multipliers. No new mechanism required.

**Source**: [Derwent Valley Orienteers](https://derwentvalleyorienteers.org.uk/2026/09/06/route-choice-path-versus-direct/), [Orienteering ACT Lesson 12](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-12-route-choice/)

---

### Rule 2: Handrails and Linear Features Override Geometry

**If** a linear feature (path, stream, fence, ridge, powerline) is available parallel to or near a control, **then** prefer to follow or stay close to that feature even if the direct bearing is geometrically shorter.

- Handrails enable faster, more confident running because they reduce mental navigation load.
- Running "on a handrail" costs only feature-following attention; running cross-country in featureless terrain requires constant compass and map cross-checking.
- Visibility and catching features on a handrail allow acceleration.
- **Cost model mapping**: Requires new mechanism—explicit linear-feature proximity bonus or "handrail-following" cost reduction. Current model has no term for feature attraction.

**Source**: [BAOC Training](http://baoc.org/wiki/Training/BulletinTrainingTips/Attack_Point), [Michigan Adventure Race Handrails Lesson](https://miadventurerace.com/navigation-lesson-5-handrails/), [Better Orienteering](https://betterorienteering.org/intermediate-techniques/)

---

### Rule 3: Attack Points Matter More Than Route Middle

**If** a control lies in complex or featureless terrain, **then** allocate route-planning effort and safety margin to a clear attack point (an obvious feature 50–200 m from the control), not to the geometric mid-leg.

- The final approach to a control is the highest-risk segment; misnavigation near a control is expensive.
- Orientation (location) must be crisp at the attack point; intermediate leg geometry is secondary.
- Backwards planning (from control → attack point → start) is practiced by elite orienteers; forward planning is suboptimal.
- **Cost model mapping**: Not directly expressible in current model. Requires a scoring term that penalizes routes lacking a clear pre-control attack point or increases cost for controls in high-terrain-complexity areas without linear-feature approaches.

**Source**: [BAOC Attack Point Guide](http://baoc.org/wiki/Training/BulletinTrainingTips/Attack_Point), [Orienteering ACT Lesson 8](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-8-attack-points/), [Better Orienteering](https://betterorienteering.org/intermediate-techniques/)

---

### Rule 4: Navigation Error Cost Exceeds Route Optimization Gain

**If** a route choice reduces navigation risk (uses handrails, limits bearing work, maintains obvious catching features), **then** accept a time cost of 5–10 seconds per control compared to an optimized but navigationally harder route.

- Empirical observation: elite and intermediate orienteers lose more time from misnavigation than from suboptimal route selection.
- Relocation (recovering from lost location) costs minutes; a safe route preventing relocation is worth seconds of detour.
- Indecision time: if reconsidering a route choice takes >30 seconds, the first choice was better than the revised one.
- **Cost model mapping**: Could be expressed via a "navigation-risk penalty" term tied to terrain complexity or lack of nearby linear features, applied only if no better current mechanism (handrail bonus) is active.

**Source**: [Better Orienteering](https://betterorienteering.org/intermediate-techniques/), [Orienteering USA Route Analysis](https://orienteeringusa.org/2026/08/from-time-loss-to-root-causea-practical-approach-to-route-analysis/), [Lesson 12: Route Choice](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-12-route-choice/)

---

### Rule 5: Vegetation "Fight" Has Fatigue Cost Beyond Speed Reduction

**If** a terrain segment is classified as "fight" (walking speed, bracken, undergrowth, <20% runnability), **then** add a fatigue/difficulty penalty beyond the speed-factor reduction.

- Standard runnability classes:
  - Slow running with good visibility (~60–80% of road speed): minimal fatigue penalty
  - Slow running or walk (~20–60%): moderate fatigue and mental load
  - Fight (<20%): high fatigue; causes pace deterioration over time
- Dense undergrowth, brambles, and boulder fields force constant attention and micro-routing decisions, increasing cognitive load and physical effort beyond nominal speed penalty.
- **Cost model mapping**: Current model uses terrain speed_factor but does not distinguish "fatigue cost" from "speed cost." New mechanism: a fatigue term that scales with vegetation density and affects later-leg performance (e.g., reduced willingness to re-attempt difficult terrain).

**Source**: [O-Map Wiki: Vegetation Symbols 406–410](https://omapwiki.orienteering.sport/symbols/407-vegetation-slow-running-good-visibility/), [Better Orienteering: Know Your Vegetation](https://www.bko.org.uk/sites/default/files/basicpage/KYS-Vegetation.pdf)

---

### Rule 6: Contouring Around a Hill vs. Climbing Over It

**If** a control is on the far side of a significant hill, **then** contour around (stay at constant elevation near the hillside) rather than climb over if the elevation gain exceeds ~5 contour lines (~50 m, or "a 5-storey building").

- **Climbing overhead cost**: 2-contour hill (20 m) is equivalent to a 2-storey climb; 10-contour (100 m) is a 10-storey climb.
- Elite practice: for steep sections, climb or drop elevation at the start, then contour fast at the new level rather than contouring the entire slope.
- Contouring is most efficient on rocky or heavily contoured terrain where direct paths are obstructed; flat or gentle slopes favor the direct route.
- **Cost model mapping**: Requires a realistic elevation cost based on contour density (already present via k_slope penalty), combined with a contouring bonus when staying at one elevation on steep slopes. The current k_slope model (crude, based on ink density) should be complemented by explicit climbing-cost increment for steep sections.

**Source**: [Orienteering ACT Lesson 10: Contours](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-10-improving-contour-navigation/), [Wessex Orienteering Club: Contouring Technique](http://www.wessex-oc.org/2012/02/03/contouring-technique/), [BKO: Know Your Contours](https://www.bko.org.uk/sites/default/files/basicpage/KYS-Contours.pdf)

---

### Rule 7: Catching Features Simplify Route and Enable Speed

**If** a route option includes a large, obvious "catching feature" (a water body, cliff, powerline, or major path perpendicular to the route beyond the control), **then** simplify the leg to run toward the catching feature at full speed and use it as a confidence anchor.

- Catching features (features that will "catch" you if you overshoot) allow runners to reduce attention to map during leg middle and increase pace.
- Route simplification (running on confidence rather than constant cross-checking) saves 5–15 seconds per leg and reduces error risk.
- Works especially well on easier terrain and long legs; less applicable in technically dense courses.
- **Cost model mapping**: New mechanism required. A "catching-feature bonus" or "route-simplification score" that reduces cost for routes with obvious perpendicular features beyond the control. Could also be framed as a reduction in required navigation attention (faster effective speed where catching features exist).

**Source**: [Michigan Adventure Race: Catching Features](https://miadventurerace.com/navigation-lessons-6-7-aiming-off-handrails/), [Better Orienteering](https://betterorienteering.org/intermediate-techniques/), [Lesson 12: Route Choice](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-12-route-choice/)

---

### Rule 8: Pace Decisions and Traffic-Light Segmentation

**If** a leg has mixed terrain complexity, **then** pre-assign segments as "green" (run fast on linear features or obvious terrain), "orange" (slow and focus), or "red" (walk and navigate carefully), and commit to pace at control rather than re-deciding mid-leg.

- Green: clear paths, easy handrails, obvious features → run 90–100% of sustainable pace
- Orange: mixed visibility, navigational attention required → run 60–80% pace, frequent map checks
- Red: complex contours, featureless terrain, or close approach to control → walk 20–40% pace, continuous map and compass work
- Indecision costs >30 seconds; pre-committing saves time and reduces navigation error.
- **Cost model mapping**: This is more a route-rendering and UI rule than a cost-model rule. Could be mapped to suggested pace zones based on terrain complexity, path density, and distance-to-next-control. Complements rather than changes the underlying cost model.

**Source**: [Better Orienteering](https://betterorienteering.org/intermediate-techniques/), [Lesson 12: Route Choice](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-12-route-choice/), [Intermediate Techniques](https://betterorienteering.org/intermediate-techniques/)

---

### Rule 9: Rogaine Route Continuity and Time Buffering

**If** planning a rogaine route to maximize points within time, **then** identify a "stay inside this line" boundary (typically 1 km from finish) to be reached by 80% of elapsed time, allowing a final buffer for fatigue and navigation errors.

- Route planning is iterative: link all controls, then drop low-value or distant controls until estimated time fits the time limit.
- Average speed assumptions: ~4 km/h for walking, ~5 km/h for brisk pace; adjust per terrain and team fitness.
- Night-navigation sections require pace-counting or compass-bearing discipline; assign one team member per task (pace count, compass, map reading).
- Final-stage fatigue typically reduces effective speed by 10–20% compared to early-event pace.
- **Cost model mapping**: Not directly applicable to this project's orienteering focus, but useful context. Route cost should factor in cumulative fatigue if multi-leg sequences are analyzed; current model treats each leg independently, which may underestimate the cost of sustained difficult terrain.

**Source**: [South Australian Rogaining Association: Route Planning](https://sarogaining.com.au/news/rogaining-tips-route-planning/), [Rogaining Tips: Night Navigation](https://sarogaining.com.au/news/rogaining-tips-night-navigation/), [Orienteering USA: What is Rogaining](https://orienteeringusa.org/explore/what-is-rogaining/)

---

## Summary by Theme

| Theme | Rules | Mapping to Current Model |
|-------|-------|--------------------------|
| **Road/path vs direct terrain** | Rule 1 | Exists: terrain speed_factor |
| **Handrails and linear features** | Rule 2 | **New mechanism needed** |
| **Attack points** | Rule 3 | **New mechanism needed** |
| **Navigation risk and error cost** | Rule 4 | **Partial (new risk term)** |
| **Vegetation/runnability** | Rule 5 | Exists (k_terrain), needs fatigue cost extension |
| **Contour/slope handling** | Rule 6 | Partial (k_slope), needs explicit climbing increment |
| **Catching features** | Rule 7 | **New mechanism needed** |
| **Route segmentation and pacing** | Rule 8 | UI/rendering, not cost-model |
| **Rogaine/multi-leg fatigue** | Rule 9 | Out of scope (orienteering focus) |

---

## Key Takeaways for Engineering

1. **Handrails and linear features** are the single most underrepresented heuristic in typical physics-based cost models. Adding a proximity or attraction term to linear features would substantially improve route plausibility.

2. **Navigation risk** (error cost, relocation cost) is empirically more important than raw distance or speed optimization. A cost term penalizing navigationally complex routes without attack points or handrails would shift the model toward safer, more practiced choices.

3. **Vegetation fatigue** extends beyond speed reduction. Dense undergrowth causes cognitive load and pacing deterioration; a fatigue model that affects subsequent-leg performance would capture this.

4. **Attack-point and catching-feature planning** is a distinct mental phase in real orienteering. Current distance-minimization models do not reward this structure; adding an explicit term for "control approach simplicity" would encourage it.

5. **Contour-based elevation cost** (climbing vs. contouring) requires better terrain model. The current ink-density proxy is crude; even a simple per-contour climbing increment would improve hill-crossing decisions.

---

## Sources

- [Better Orienteering: Intermediate Techniques](https://betterorienteering.org/intermediate-techniques/)
- [Better Orienteering: Basic Techniques](https://betterorienteering.org/basic-techniques/)
- [BAOC: Attack Point Training](http://baoc.org/wiki/Training/BulletinTrainingTips/Attack_Point)
- [Orienteering ACT: Lesson 12 – Route Choice](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-12-route-choice/)
- [Orienteering ACT: Lesson 8 – Attack Points](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-8-attack-points/)
- [Orienteering ACT: Lesson 10 – Contour Navigation](https://act.orienteering.asn.au/resources/skills/advanced-skills/lesson-10-improving-contour-navigation/)
- [Orienteering USA: From Time Loss to Root Cause](https://orienteeringusa.org/2026/08/from-time-loss-to-root-causea-practical-approach-to-route-analysis/)
- [Derwent Valley Orienteers: Route Choice Path vs Direct](https://derwentvalleyorienteers.org.uk/2026/09/06/route-choice-path-versus-direct/)
- [Michigan Adventure Race: Handrails](https://miadventurerace.com/navigation-lesson-5-handrails/)
- [Michigan Adventure Race: Catching Features & Aiming Off](https://miadventurerace.com/navigation-lessons-6-7-aiming-off-handrails/)
- [South Australian Rogaining: Route Planning](https://sarogaining.com.au/news/rogaining-tips-route-planning/)
- [South Australian Rogaining: Night Navigation](https://sarogaining.com.au/news/rogaining-tips-night-navigation/)
- [Orienteering USA: What is Rogaining](https://orienteeringusa.org/explore/what-is-rogaining/)
- [O-Map Wiki: Vegetation Symbol 407](https://omapwiki.orienteering.sport/symbols/407-vegetation-slow-running-good-visibility/)
- [BKO: Know Your Vegetation](https://www.bko.org.uk/sites/default/files/basicpage/KYS-Vegetation.pdf)
- [BKO: Know Your Contours](https://www.bko.org.uk/sites/default/files/basicpage/KYS-Contours.pdf)
- [Wessex Orienteering Club: Contouring Technique](http://www.wessex-oc.org/2012/02/03/contouring-technique/)
