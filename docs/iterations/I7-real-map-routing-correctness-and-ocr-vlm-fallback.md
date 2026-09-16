# Iteration I7 — Real-map routing correctness (out-of-bounds/water/ЛЭП/olive) and an opt-in VLM OCR fallback

- **Source:** Owner bug report, in-chat 2026-09-14, two annotated screenshot crops from
  `data/maps/ogps-8620_502cda4f6c774e8ecb86d063a71895f6/map.jpg` (a solved route crossing a
  magenta-hatched ISOM 709 out-of-bounds polygon, and the same route crossing a lake), plus a text
  report of a route crossing dark-green "olive" vegetation and a power line (ЛЭП) being treated as a
  normal path, plus at least 6 unread control numbers on the same map. The owner asked for
  externally-researched grounding: the reference article (https://habr.com/ru/articles/1065342/,
  already SPEC.md's own cited reference implementation) and a companion demo video the owner
  downloaded and supplied locally (`C:\Users\dmkdok\Downloads\videoplayback.mp4`, 58s, frames
  extracted and read this session via `ffmpeg` — YouTube itself would not serve a transcript/
  description to any fetch tool tried).
- **Opened:** 2026-09-14
- **Milestones:** `M14` (map/routing correctness, T108-T112) and `M15` (OCR VLM fallback,
  T113-T115) in `docs/TASKS.md` — split into two milestones at the owner's own choice (M14 is
  smaller, deterministic, closes and ships independently; M15 is a genuine architecture reversal
  that deserves its own weight in review).
- **Baseline:** `docker compose run --rm tests` — **522 passed**, exit 0, 491.89s, 1 warning
  (pre-existing `httpx`/`starlette` deprecation notice, unrelated); `ruff check .` clean. 2026-09-14,
  this session's own run, branch `iteration/I2-vision-recognition-fix` @ `5f929c0`, tree clean.

## Research grounding (owner-requested, before any design)

**Reference architecture (article, verified by direct fetch, and the video, verified by extracting
and reading 30+ frames this session):** terrain is classified by a **trained segmentation network**
(SegFormer MiT-B4, sliding-window tiled inference over ~200 training maps, 16 classes) — not
per-pixel nearest-colour matching. Control numbers are read by a **VLM** (the video shows Yandex
Cloud Qwen, tiled into 4 overlapping 1024px windows with a per-tile confidence score, e.g. "VLM тайл
2/4 → #21 ✓ (0.95)"), with classical CV used only to **snap** the VLM's approximate pixel coordinate
to the true circle centre ("3/6 Refine: КП 22: refine Δ=7.6px") — the article's own words: "жёстко
уточняем... находя в окрестностях окружность около-розового цвета." Route planning is Dijkstra over
a per-pixel cost field feeding a Held-Karp-style DP over control subsets — both **already this
project's own architecture** (ADR-002, ADR-003); the video's final routes visibly hug roads for most
of their length, consistent with `docs/research/route-choice-heuristics.md`'s own Rule 2/7 finding.

**Route-choice heuristics were already researched and mostly already implemented** — this iteration
does not repeat that work. `docs/research/route-choice-heuristics.md` (T094, 19 sources verified
individually) covers the owner's own "бег в мешок" concept (handrails/catching features, Rules 2+7 —
implemented, T095/ADR-029, proximity bonus enabled) and "road beats bushwhacking" (Rule 1 — already
solved exactly by the existing Dijkstra solve, no rule-of-thumb needed). What remains deferred there
(attack points/Rule 3, vegetation fatigue, directional slope) is deferred for reasons independent of
this iteration (they need concepts — path-history dependence, elevation data — the current per-pixel
cost field cannot express without a solver redesign) and stays deferred; this iteration does not
reopen that research. **What this iteration actually found is a different, narrower problem: the
terrain and OCR *inputs* fed to that already-good solver are wrong on real scans** — an out-of-bounds
polygon and a lake are being classified as passable terrain, a power line as a normal path, and
control numbers as unread — not that the solver mishandles correctly-classified input.

**Pre-existing decisions this iteration knowingly revisits (flagged for the gate, not silently
overridden):** `docs/SPEC.md`'s own `## Integrations` line ("None. No external APIs, no VLM, no
telemetry"), its `## Non-goals` line ("VLM-based control detection (the article's Yandex Cloud Qwen
path)"), its NFR-Security line ("no network calls at runtime"), and `docs/DECISIONS.md` ADR-009
("Tesseract OCR, explicitly non-load-bearing... a VLM costs money and determinism") all currently
rule out exactly the OCR-fallback mechanism M15 proposes. The owner chose to revisit this (this
session's `AskUserQuestion`, "Гибрид: Tesseract первым, VLM — только на кружках, где Tesseract не
прочитал/дал низкий confidence") with the scope narrowed to opt-in, number-reading-only, so circle/
position detection stays 100% classical CV (that part of the Non-goal is **not** withdrawn) and the
tool stays fully offline whenever the fallback is disabled or unconfigured (the default).

## In scope

| Item | Why now |
|------|---------|
| T108/T109 — Out-of-bounds (ISOM 709) region interior leaks through as passable | Reproduced exactly on `ogps-8620`; root mechanism already admitted in `vision/palette.py`'s own docstring (`palette.py:39-54`) as an unowned gap since M1 — per-pixel classification has no notion of an enclosed hatched polygon's interior |
| T110 — Lake crossing on `ogps-8620` | Same screenshot, same map; `_consolidate_banked_water`'s own docstring already names "a hatched/screened shallow pond or marsh with no [adjacent black bank] border is untouched" as a known gap (measured on a *different* map, `ogps-6802`, by T101) — needs its own measurement on this map before assuming the same fix applies |
| T111 — ЛЭП (power line) costed as a normal footpath | Confirmed by code recon: zero symbol-aware handling anywhere in `vision/linear.py`, purely stroke-width bucketing (`linear.py:174-175`); whatever bucket it lands in also gets T095's full proximity speed bonus |
| T112 — Dark-green "fight" vegetation (ISOM 410, "оливка") stays `passable=true` | Owner's explicit ruling for this event's rules: fully forbidden, not merely 20x slower — a deliberate reinterpretation of `config/default.toml`'s current `veg_fight` entry, owner's own choice over keeping it as a very-high-cost-but-legal edge |
| T113/T114 — OCR gives up rather than escalate | 4th tuning round (T079→T105) on the same classical Tesseract pipeline; still >=6 unread numbers on `ogps-8620`. Reference article/video both solve this with a VLM, not further classical tuning — owner chose a scoped, opt-in hybrid over a 5th classical round |
| T115 — No measured evidence the fallback actually closes the gap | Needed before this iteration can close — mirrors every prior OCR round's own "measured, not asserted" discipline |

## Out of scope this round

| Item | Reason | Recorded as |
|------|--------|-------------|
| Adopting the reference's SegFormer segmentation network for terrain (instead of the region-closure CV fix below) | The reported defects are explained and fixable by a much cheaper, deterministic, no-new-dependency CV step (closing hatched-polygon interiors); a trained segmenter needs ~200 labelled maps, GPU training infra and ongoing model maintenance ADR-001 already scoped as "optional" — disproportionate to this specific symptom | ADR-001 unchanged, still "SegFormer is optional"; not reopened |
| VLM-based **circle/position** detection (only number-*reading* becomes VLM-assisted) | Owner's own scoping in this session's `AskUserQuestion` — narrower revision of the SPEC Non-goal, not a full repeal | SPEC `## Non-goals`, amended in place, ADR-039 |
| Attack points / backward route planning ("Rule 3"), vegetation fatigue, directional (uphill/downhill) slope | Already researched and deferred by T094/ADR-027, for reasons unrelated to this iteration (need path-history-dependent cost or elevation data, a solver-level redesign) | `docs/research/route-choice-heuristics.md` §Rule 3/5/6, unchanged |
| Lighter vegetation classes (ISOM 406/408) reclassified alongside 410 | Owner's ruling was specifically about the darkest "fight" class; the lighter two were not reported as a problem and its already-implemented, already-verified speed factors (Rule 5) are not being second-guessed here | Left as-is in `config/default.toml` |
| A corpus-wide hunt for further out-of-bounds/water/ЛЭП failures beyond `ogps-8620` | Diagnosis-first per ADR-026/033 precedent means measuring the reported map, not fishing for more; the fix must not regress the wider corpus (existing regression tests), but finding new failure modes elsewhere is a future iteration's intake, not this one's | Not filed as a task; corpus-wide regression floors are the check, not a new hunt |

## Impact map

| Item | Touches | SPEC: changes / preserves | Existing coverage | Class | Regression proof |
|------|---------|---------------------------|--------------------|-------|-------------------|
| T108 diagnose out-of-bounds fill | `vision/palette.py` (read-only diagnosis script, gitignored per ADR-010) | preserves F4, F7 (709 already excluded from *control* detection, T103) | none — new real-scan measurement | Local | Measured ink-density/interior-classification numbers written into the task's own DoD, no code change |
| T109 fix out-of-bounds region closure | `vision/palette.py::classify_palette` (new step between `classify_labels` and `_consolidate_banked_water`/`fill_unknown`); possibly `config/default.toml` (`[palette]`, new tunable) | changes F4 (adds real-scan acceptance line for `ogps-8620`); preserves F4's existing IoU floors on the synthetic fixture and F20 (grid-line exclusion) | `tests/unit/vision/test_segment.py`'s IoU floor tests (must not regress); no existing region-closure coverage | **Shared primitive** — `classify_palette`'s output feeds control detection's masks, `vision/linear.py`, and `cost/field.py` directly | Lands first, serially, ahead of T110-T114. New real-scan test: a probe point deep inside the reported out-of-bounds polygon on `ogps-8620` classifies `out_of_bounds`, `strict_impassable`; every existing synthetic IoU floor unchanged; full suite re-run after landing before any dependent task starts |
| T110 fix lake crossing | `vision/palette.py` (`_consolidate_banked_water` or the same closure step as T109, per T108/its own diagnosis) | changes F4's `ogps-8620` acceptance line further if the mechanism differs from T109's; preserves the `ogps-6802` acceptance line T101 already added | `TestBankedWaterConsolidationOnRealScan` (T101, on `ogps-6802` — must stay green) | Local once T109 lands (same file, but a distinct measured mechanism per this map) | `GridGraph.block_passable` false at the lake's deepest interior point (same style of check as T101), gitignored real-scan test skipped when the scan is absent |
| T111 diagnose ЛЭП ink | `vision/linear.py` (read-only diagnosis script, gitignored) | preserves F5 | none — new real-scan measurement | Local | Measured dash/gap pattern vs. footpath's, written into the task's own DoD; may conclude "not safely separable this round" (T098 precedent) with no code change |
| T112 fix ЛЭП costing | `vision/linear.py::extract_linear_features`; possibly `config/default.toml` (`[linear]`) | changes F5 (adds real-scan acceptance line); preserves existing `elongation_ratio_min`/`aspect_ratio_min`/width-bucketing behaviour for genuine roads/tracks/footpaths | `tests/unit/vision/test_linear.py`'s width-bucketing tests (must not regress) | Local | New real-scan test pinning ЛЭП ink no longer getting road/track/footpath's speed treatment (or, if T111 finds no safe signal, task closes with no code change, ADR amendment records why — T098 precedent) |
| T110 (config) veg_fight impassable | `config/default.toml` (`[[terrain]] name="veg_fight"`, `passable` flag) | changes F10's acceptance (impassable classes list); preserves F4 (classification itself, only the `passable`/`speed_factor` interpretation changes) | `cost/field.py`/`cost/graph.py` unit tests keyed off `config/default.toml`'s shipped values — will need updating, not just re-running (expectations-that-change item, below) | Local (single config value + its direct consumers) | New test: a `veg_fight`-labelled block is unreachable/excluded from the graph exactly like `out_of_bounds`/`water_uncrossable`; existing synthetic-fixture route tests that currently route *through* `veg_fight` (if any) re-verified or updated |
| T113 VLM OCR client module | New `vision/ocr_vlm.py`; `pyproject.toml` (new optional dependency group, not the base install) | adds F23 (new requirement); preserves F8's existing null-flagged-unread behaviour as the fallback's own fallback | none — new module | Local (new file, no existing callers yet) | Unit tests against a fake/mocked client — no real network call in CI, matching ADR-010's offline-test philosophy |
| T114 wire fallback into OCR pipeline + SPEC/NFR amendment | `vision/ocr.py`/`vision/controls.py` (trigger condition only — existing Tesseract path untouched when disabled); `config/default.toml` (new `[ocr_fallback]` section); `docs/SPEC.md` (`## Summary`, `## Integrations`, `## Non-goals`, NFR-Security, F8, Risks #4); `docs/DECISIONS.md` (amends ADR-009) | changes F8 (extends acceptance), NFR-Security (carves out the opt-in exception), `## Non-goals` (partial withdrawal, number-reading only); preserves F8's existing behaviour byte-for-byte when `[ocr_fallback].enabled=false` (the shipped default) | `tests/unit/vision/test_ocr.py`'s existing confidence/flagging tests (must stay green with the fallback disabled, the default in every existing test's config) | **Cross-cutting policy** (touches the NFR-Security "no network calls at runtime" line) — requires explicit gate sign-off and a Phase 6 security-review pass regardless of size | Disabled-by-default path: full existing suite unchanged. Enabled path: mocked-client integration test proves the trigger condition (unread or low confidence) and the graceful no-key/no-network skip; a real, manual, non-CI run against `ogps-8620` is T115's own job |
| T115 measure the fallback on real scans | none (measurement only, `data/maps/_i7_ocr_fallback_measure.py`, gitignored) | proves F23's acceptance number | none — this task supplies the first evidence | Local | Before/after read-rate on `ogps-8620` (must recover the reported >=6 previously-unread numbers) and a broader owner-corpus sample; API call count and estimated cost per map recorded in the task's own `docs/TASKS.md` entry |

**Ordering:** T109 (shared primitive) lands first, serially — the whole suite re-run before T110/T112
start. T110 depends on T109 landing and on T108's own diagnosis (may reuse T109's mechanism or need
its own). T111→T112 is its own independent pair (different file, `vision/linear.py`, untouched by
T109). The `veg_fight` config task is independent of all of the above (different file, no shared
symbol) and may run in parallel with T108/T109. T113→T114→T115 is a strictly serial chain (module,
then wiring, then measurement) and is independent of every M14 task (different files entirely) —
M15 may run in parallel with M14 or after it; the owner's own choice to split into two milestones
was partly so M14 could close and ship without waiting on M15's larger review.

## Expectations that change

- `cost/field.py`/`cost/graph.py` tests asserting `veg_fight` is traversable (if any exist) change to
  assert it is excluded from the graph like `out_of_bounds`/`water_uncrossable` — a direct
  consequence of the owner's own ruling (T110/config item), not a bug fix to an existing assertion.
  ADR-037 records this as the owner's explicit reinterpretation, not a measured discovery.
- `docs/SPEC.md`'s NFR-Security line ("no network calls at runtime") stops being universally true —
  amended, not silently narrowed, to name the opt-in exception. ADR-039 records this and why the
  default keeps the old guarantee.
- No test currently asserting `out_of_bounds`/water passability behaviour on the synthetic fixture is
  expected to change — T109/T110 are real-scan-only fixes (the synthetic fixture has no hatched
  region wide enough to exhibit the gap; its own IoU floors already pass and must stay passing).

## Exit criteria

- [ ] T108: measured, named root cause for the out-of-bounds interior leak on `ogps-8620`, feeding
      T109's design
- [ ] T109: `rogaine plan`/`detect` on `ogps-8620` no longer routes through the reported magenta
      out-of-bounds polygon; synthetic-fixture IoU floors unchanged; full suite green
- [ ] T110: same map's reported lake crossing fixed, measured; `ogps-6802`'s own T101 coverage
      unchanged
- [ ] T111: measured, named finding on this map's ЛЭП ink pattern (fix or documented no-safe-fix,
      either is a valid close)
- [ ] T112: if T111 found a safe signal, ЛЭП ink no longer costed as a normal path on `ogps-8620`;
      genuine roads/tracks/footpaths unaffected
- [ ] T110 (config): `veg_fight` excluded from the graph on every map, not only `ogps-8620`
- [ ] T113/T114: OCR fallback lands disabled by default; existing full suite green with it disabled;
      mocked-client tests green with it enabled
- [ ] T115: measured read-rate improvement on `ogps-8620` (the >=6 previously-unread numbers) and a
      broader corpus sample, with API-call/cost numbers recorded
- [ ] `docs/SPEC.md`/`docs/DECISIONS.md` amendments for both milestones committed as part of the
      approved delta, before any code
- [ ] Baseline suites (522 passed) still green at close, or better

## Addendum — local Ollama backend for the OCR fallback (owner request, 2026-09-16)

- **Source:** Owner, in-chat 2026-09-16. T115 was blocked on the owner needing a real
  `ANTHROPIC_API_KEY` and explicit consent to real API cost (`docs/STATUS.md`'s 2026-09-16
  handoff). Asked how the reference article did it and whether a free alternative exists; on
  learning `qwen2.5vl:7b` is already installed locally via Ollama, decided: "Давай использовать
  ollama. Локальные модели установлены уже на этом компьютере."
- **In:** T116 (new) — a selectable local Ollama backend for the T113/T114 OCR VLM fallback,
  additive to the existing Anthropic path. T115's DoD widened to accept either backend.
- **Out:** Replacing the Anthropic path — rejected, kept as an available option (ADR-040). A
  corpus-wide accuracy comparison between the two backends — not asked for; T115 measures whichever
  backend is configured for that run, not both.
- **Impact map:**

  | Item | Touches | SPEC: changes / preserves | Existing coverage | Class | Regression proof |
  |------|---------|---------------------------|--------------------|-------|-------------------|
  | T116 add Ollama backend | New `vision/ocr_vlm_ollama.py`; `vision/ocr.py::_try_vlm_fallback` (new dispatch branch); `config.py::OcrFallbackSettings` (new `provider`/`base_url` fields); `config/default.toml` (`[ocr_fallback]` new keys, shipped `provider="anthropic"`); `pyproject.toml` (new optional dependency group) | adds to F23 (backend choice), NFR-Security/Integrations (already amended above, ADR-040); preserves F23/F8's existing behaviour byte-for-byte since the shipped `provider` is unchanged | `tests/unit/vision/test_ocr.py`'s existing fallback tests (`_with_ocr_fallback`, built on `default_config()`) — must stay green untouched | Local (new file; `ocr.py`'s existing `provider="anthropic"` branch is unmodified logic, just now reached via an explicit dispatch) | New `test_ocr_vlm_ollama.py` mirrors T113's mocked-client pattern (ADR-010, no real network call); every existing `test_ocr.py` fallback test re-run unmodified and green |
  | T115 (re-scoped) | none (measurement script, gitignored) | same F23 acceptance line, now satisfiable via either backend | — | Local | Ollama run: read-rate before/after on `ogps-8620` plus the broader corpus sample, cost recorded as $0 |

- **Ordering:** T116 depends on T114 (already landed); T115 depends on T116. Independent of every
  M14 item.
- **Expectations that change:** none — this delta is additive by construction (see impact map).
- **Exit criteria:** T116 lands with the full suite green and every existing OCR fallback test
  unmodified; T115 then closes using the Ollama backend, recording read-rate and $0 cost.
