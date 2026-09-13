# Status

phase: implement
approved: true
approved_at: 2026-08-19
current: M0-M6 complete and reviewed (docs/REVIEW.md, verdict PASS). **M8 complete and merged to
  `master`** (iteration I1, real-scan vision robustness): T073-T076 landed, independently reviewed
  (two review rounds, both FAIL-then-fixed — see Iteration I1 below), all 5 of I1's exit criteria
  met. M7 in progress: harvest complete (2026-09-04, 204 o-gps-center.ru maps, past the ~200
  target, ADR-014). **T078 (per-map best-effort auto-calibration, ADR-016) landed 2026-09-05 and
  merged to `master`** — independently reviewed, FAILed (1 Critical, 4 High, 6 Medium), fixed, fix
  independently re-verified against the real corpus (own read of the diff, own
  `docker compose run --rm tests`, own `ruff check .`, own tally of all 219 `meta.toml` files, not
  trusted from the subagent's report). Real corpus run: 45 measured / 159 assumed_default / 15
  out_of_scope (owner's own scans, never touched) / 1 error / 219 total. T070 unblocked — every
  in-scope map has a `meta.toml`, calibration accuracy no longer gates it (scale is secondary for
  this corpus; see ADR-016). **S-001 (docs/REVIEW.md, security, Medium) fixed 2026-09-05** —
  `le=` upper bounds on `SegmentRequest.dpi` and `RunConfig.time_limit_s`/
  `heuristic_time_budget_s`/`alternatives` (ADR-017, new since `models.py` is frozen), the three
  background workers' `except` widened to bare `except Exception` so no failure can wedge a job at
  `status: "running"` forever. `docker compose run --rm tests` — 447 passed, exit 0 (439 baseline +
  8 new); `ruff check .` clean. **Iteration I2 (real-scan detection/OCR failure) approved
  2026-09-05** (`утверждаю`) — M9 filed in `docs/TASKS.md`. **T079, T080, T081, T077 all landed
  2026-09-06** (commits `fade5fd`, `e6e730a`/`8a70639` docs, `00b1b97`, `7676556` docs, `e7e2017`
  ADR-020 docs, `a29d752`) — see Resume here for the measured detail on each. Only **T082** (owner
  spot-check, manual, ADR-019) remains open in M9 — but see immediately below, M9 has been
  overtaken by a second, larger iteration on the same branch. **Iteration I3 (viewer UX, scale
  auto-detect exposure, OCR fix) approved 2026-09-07** — M10 filed (T083-T088). **All six M10 tasks
  now landed** (commits `be8eccb`/ADR-023, `fec2e7c`, `cc03275`, `d40047f`+`0631783`, `7b6f561`,
  `5957120`+`14bbccb`) — real-scan OCR read rate 19%→49% corpus-wide (T084/ADR-023).
  Implementation closed 2026-09-09; independent review (scoped `reviewer` subagent) then FAILed on
  1 Critical + 1 High + 2 Medium in T088's scope, all fixed and independently re-verified same
  session (472 passed, `ruff check .` clean) — full account in T088's `docs/TASKS.md` entry.
  **2026-09-11: T082 done (partial pass)** — owner spot-checked, recognition "стало лучше" but still
  misses many numbers on maps far from the base print scale; M9 is now fully closed. That report,
  plus four further owner requests (points auto-fill, viewer route alternatives, route-choice
  quality, relief prep), became **Iteration I4** (M11, T089-T096,
  `docs/iterations/I4-ocr-scale-and-route-quality.md`) — delta written, **gate approved 2026-09-11**
  («Утверждаю»). **All 8 M11 tasks now landed** (T091, T092, T093, T094, T096, T089/ADR-030, T090/
  ADR-031, T095) — real-scan OCR read rate on the owner corpus 49.3%→54.3%, `ogps-*` corpus-wide
  22.9%→25.3% (T090/ADR-031). Milestone-level review run (scoped `reviewer` subagent, all 8 M11
  tasks): **PASS WITH WAIVERS** — 2 High findings in T090 fixed same session (499 passed after),
  several Low items waived as documented follow-up debt — see "Iteration I4" below for the full
  account. **2026-09-12: T095's owner sign-off received** — `[proximity].enabled` flipped to
  `true` in `config/default.toml` (ADR-029's amendment), 5 tests whose premise was the old
  off-by-default updated to match (not left red), `tests/e2e/golden_route.json` regenerated a
  second time. 500 passed, `ruff check .` clean. **One manual owner sign-off remains open**
  (ADR-019 precedent): I3's own T086 visual review — see "Iteration I3" for its detail.
  **2026-09-12, same session: new owner bug report** — control numbers still unread on many real
  scans despite being clearly legible, plus spurious tiny detections in cover-page/legend text.
  Became **Iteration I5** (M12, T097-T100, `docs/iterations/I5-control-detection-false-negatives.md`)
  — delta written, **gate approved 2026-09-12** («Утверждаю, продолжи»). **All 4 tasks landed and
  closed 2026-09-13** (T097, T099 — amended once after the owner's own T100 sign-off found its
  first version too aggressive — T098 closed with no code change, T100 measured). Independent
  review PASS WITH WAIVERS (1 High + 3 Medium fixed same session). **M12 complete** — 513 passed,
  `ruff check .` clean. See "Iteration I5" below for the full account.
  **2026-09-13, same session: new owner bug report** — a spot-check across three more real maps
  (`ogps-6802`, `ogps-7302`, `ogps-8078`) plus two viewer UX complaints (calibration tool active-state,
  manual add-control flow). Became **Iteration I6** (M13, T101-T107,
  `docs/iterations/I6-real-map-detection-gaps-and-viewer-ux.md`) — delta intake agreed and impact map
  written this session; **docs amended (SPEC F4/F7/F8/F17, DECISIONS ADR-033, TASKS M13 T101-T107),
  gate approved by the owner 2026-09-13 («Утверждаю, продолжи»).**

## Baseline I6
`docker compose run --rm tests` — 513 passed, exit 0 (own run, not piped through `tail`); `ruff
check .` clean (run inside the `tests` container — `docker compose run --rm app ruff check .` fails,
the `app` image has no `ruff` on `PATH`, use `tests`). 2026-09-13, branch
`iteration/I2-vision-recognition-fix` @ `ba27ff1`, tree clean.

## Baseline I2
`docker compose run --rm tests` — 447 passed, exit 0; `ruff check .` clean. 2026-09-05, branch
`iteration/I2-vision-recognition-fix` off `master`@640dce9, tree clean apart from one pre-existing,
unrelated uncommitted change (`docker-compose.yml`, `app` service's host port 8000→8001 — not this
session's edit, doesn't touch the `tests` service, left alone; owner has not said whether to keep,
commit or revert it).

## Resume here
**This section describes M9/I2, now historical — M9 is done apart from the manual T082 spot-check.
Active work is Iteration I3 (M10, T083-T088), all 6/6 tasks landed and independently reviewed
(FAIL-then-fixed) as of 2026-09-09 — jump to the "Iteration I3" section below for its own
Resume-here-equivalent progress checklist. Implementation and review are both closed; all that's
left is two manual owner sign-offs (T086's visual review, M9's T082 spot-check) before reading the
rest of this section.**

`master` last release point 640dce9; working branch `iteration/I2-vision-recognition-fix`, not yet
merged. **Iteration I2 approved 2026-09-05; M9's four automated tasks (T079, T080, T081, T077) all
landed 2026-09-06. Only T082 (owner spot-check, manual, cannot be automated) is left open.** Full
intake + impact map: `docs/iterations/I2-real-scan-detection-failure.md`. New ADRs: ADR-018 (tighten
`purple_mask`'s red ink band by measurement), ADR-019 (acceptance is the owner spot-checking 2-3
real scans), ADR-020 (`Control.radius_px`, added for T077).

**Why (original bug, for context):** owner reported the app doesn't read control numbers at all and
misdetects controls on most maps. Reproduced on all 13 of the owner's own scans under `data/maps/`:
2x-10x over-detection, ~0% OCR read rate on 10/13, hub not found on 8/13.

**What actually landed, in order:**
1. **T079** (`fade5fd`) — `purple_mask`'s red band split off into its own `red_hue_ranges` config
   surface with a measured floor (61/151) plus a `red_min_channel_gap=60` discriminator, fixing
   brown contour-line ink (88% of `ozero-shchuche`'s false matches) passing the old shared red
   floor. Ink density on that file dropped 6.82%→1.34%. 448 passed, `ruff check .` clean.
2. **T080** (`e6e730a`) — re-measured `_select_best_scale`'s tie-break (ADR-015) against all 13
   real maps post-T079: no map met the DoD's "gross over-detection *and* tie-break-caused" trigger
   (one mild 5-candidate case on `kkm-toksovo`, not gross). **Closed with no code change** —
   measured, not speculative. 448 passed, unchanged.
3. **T081** (`00b1b97`) — `_detect_hub_triangle` still missed the hub on 8/13 maps even under
   T079's clean mask. Two independent, measured causes, both now fixed: ISOM's combined
   start/finish (701 triangle overlapping the 706 finish double-circle — the owner's own hint,
   confirmed by measurement) adds a vertex a single fixed `approxPolyDP` epsilon couldn't absorb,
   fixed by a widened epsilon sweep (`_TRIANGLE_APPROX_EPS_FRACTIONS`); `cv2.RETR_EXTERNAL` hid a
   hub nested inside a terrain-mesh contour's hole, fixed by switching to `cv2.RETR_LIST`.
   `_TRIANGLE_MIN_SIDE_RATIO` tightened 0.5→0.85 (measured real triangles vs. a false-positive logo
   blob the wider sweep newly exposed). Hub found on 10/13 maps (was 5/13); the 3 remaining are
   measured, out of scope (2 have hub ink fused into a page-spanning border/mesh, 1 is a
   scale-tolerance mismatch needing `_select_best_scale` retuning, explicitly not touched). 449
   passed, `ruff check .` clean.
4. **T077** (`a29d752`, schema in `e7e2017`/ADR-020) — `Control.radius_px` (new optional field)
   carries the matched scale's nominal mid radius; `_ocr_crop` sizes its crop from it instead of
   always assuming the base ISOM print scale. **One real finding, corrected before landing:** the
   first design threaded Hough's raw per-candidate fitted radius, which regressed the clean
   synthetic fixture's OCR read rate 11/12→9/12 (Hough's per-circle fit jitters ~±10% around the
   nominal radius even at the base scale, and the crop-margin constants were tuned against the
   noiseless nominal value). Fixed by threading the matched multiplier's own nominal radius instead
   — bit-identical to the old base-scale behaviour for any base-scale control, so strictly
   additive. `grid-lines-red-controls` read rate 0/13→3/13. 457 passed, `ruff check .` clean.

**Only remaining M9 task:**
5. **T082** — owner spot-checks 2-3 of their own real maps (`rogaine detect`/`plan` output and/or
   the viewer) post-fix and confirms circle positions, hub, and numbers look right (ADR-019 — no
   automated floor, this is the acceptance gate). Not something a session can do unsupervised.

Fresh session: `/clear`, then «продолжай по docs/STATUS.md».

Deferred, unrelated to I2: **T070 (tiling/mask export)** still next in M7 after M9, not started —
deps T016/T017/T078 all satisfied, but M7's own gate ("owner accepts the route" on their own map) is
exactly what I2 is trying to clear, so T070 stays parked until I2 lands.

**Earlier infrastructure note (kept for reference, from the I1 session):** two `Agent` (subagent)
calls failed mid-task with `oauth_org_not_allowed` / "Your organization has disabled Claude
subscription access for Claude Code" (one implementer run, one haiku-model harvester run). Both are
`Agent`-tool API errors, not this project's bug. The implementer's work was not lost — its file
edits persisted on disk despite the agent's own final report never completing, and were
independently re-verified in that same session rather than trusted blind. A later `reviewer`
subagent call in that session succeeded normally, so this looks transient/intermittent rather than a
hard block — but if a future session sees the same error, know that subagent tool calls can fail
mid-task while still having committed real file edits before the failure; check `git status`/`git
diff` for real work before assuming nothing happened, rather than retrying blind.

## Iteration I6: real-map detection gaps and viewer UX (gate approved, implementation starting, branch `iteration/I2-vision-recognition-fix`, continued)

Owner report, in-chat 2026-09-13, with one annotated screenshot: a spot-check across three more
real maps surfaced a river-crossing routing bug and two missing-OCR cases (`ogps-6802`), a forbidden
-area (ISOM 709) symbol misdetected as dozens of controls (`ogps-7302`), and an unusual two-colour
ring/number print style whose numbers go unread despite every circle being found correctly
(`ogps-8078`); plus two viewer UX complaints (the calibration tool's active-state is unclear enough
that panning while armed can corrupt an already-placed line; manually adding a control drops a pin
immediately instead of click-to-place like the calibration line) and one cross-cutting policy
request (skip auto-placing a control the system isn't confident about, rather than risk a false
one). Full intake + impact map:
`docs/iterations/I6-real-map-detection-gaps-and-viewer-ux.md`. New ADR: ADR-033 (four items are
diagnosis-first, ADR-026 precedent; the confidence-gated auto-placement floor ships without an
intermediate owner review step, the owner's own choice over T099/T100's precedent). SPEC F4/F7/F8/
F17 acceptance text extended, no new requirement ids, no renumbering.

Explicitly out of scope, owner's own words: `ogps-6802` carries an unrelated, pre-existing
annotation artifact (someone overlaid a circled path on top of one trail) — not a detection defect,
no task touches it.

Progress (M13 in `docs/TASKS.md`, T101-T107):
- [x] 0 baseline recorded — `docker compose run --rm tests` 513 passed, exit 0; `ruff check .`
  clean; 2026-09-13, tree clean (see "Baseline I6" above)
- [x] 1 delta intake agreed (in / out / deferred) — all 7 items taken in one milestone (owner's own
  choice over splitting into two rounds); item 7's confidence floor shipped conservative and direct,
  no intermediate review step (owner's own choice) — both recorded in
  `docs/iterations/I6-real-map-detection-gaps-and-viewer-ux.md`
- [x] 2 impact map written — same file (per-item touches/SPEC/coverage/blast-radius/regression-proof
  table, plus ordering constraints: T103 before T105, T102 before T104, T106 before T107, T101
  independent)
- [x] 3 docs amended (SPEC F4/F7/F8/F17 extended, DECISIONS ADR-033, TASKS M13 T101-T107)
- [x] GATE — approved by the owner 2026-09-13 («Утверждаю, продолжи»)
- [ ] 4 implementation
- [ ] 5 verification
- [ ] 6 review
- [ ] 7 closed
- [ ] 8 deploy (optional, not yet decided)

## Iteration I5: control-circle/number false negatives and false positives on real scans (closed, branch `iteration/I2-vision-recognition-fix`, continued)

Owner bug report, in-chat 2026-09-12, with two annotated screenshots (crops from real
`ogps-*`-harvested maps — the owner tested broadly across that corpus, not one named file) showing
controls (72/44/66/42/53) whose printed number is clearly legible to a human but came back unread,
plus one correctly-read control (71) for contrast, and a separate report of spurious tiny
"controls" detected inside cover-page/legend text. The owner proposed four heuristics (colour,
known circle size, edge-of-segment failure, text false positives); code inspection this session
(not the owner's claims taken at face value) found each already partially addressed, with one
concrete gap per item. Full intake + impact map: `docs/iterations/I5-control-detection-false-negatives.md`.
New ADR: ADR-032 (crop window slides instead of truncating at the raster edge; a per-candidate
raw-radius consistency filter; the sub-1.0 OCR gate becomes per-candidate). SPEC F7/F8 acceptance
text extended, no new requirement id.

Owner explicitly chose to design all four fixes now rather than a separate measurement-first
diagnosis pass (I4/ADR-026's precedent) — a recorded departure, not a process lapse; Phase 5
verification still measures against the real corpus before anything lands.

Progress (M12 in `docs/TASKS.md`, T097-T100):
- [x] 0 baseline recorded — `docker compose run --rm tests` 500 passed, exit 0; `ruff check .`
  clean; 2026-09-12, tree clean (this session closed T095's own owner-sign-off first — see the
  `current:` line above and Iteration I4's own section)
- [x] 1 delta intake agreed (in / out / deferred) —
  `docs/iterations/I5-control-detection-false-negatives.md`
- [x] 2 impact map written — same file
- [x] 3 docs amended (SPEC F7/F8 acceptance extended, DECISIONS ADR-032, TASKS M12 T097-T100).
  **F7's extension was withdrawn 2026-09-13** (review finding H1) — the raw-radius outlier filter
  it described was T098, which closed with no code change (measured unsafe); F7 now describes that
  correctly instead of a mechanism that was never shipped. F8's extension stands, amended to name
  T099's own junk-fraction exception explicitly.
- [x] GATE — approved by the owner 2026-09-12 («Утверждаю, продолжи»)
- [x] 4 implementation — all four tasks resolved. **T097 landed** (`c0ae26d`) — `_ocr_crop`'s
  window now slides along an axis to stay in-bounds instead of shrinking, 5 new edge-adjacent-
  control tests. **T098 closed with no code change** — a median+MAD raw-radius outlier filter was
  built, tried, and measured unsafe (stripped genuine detections on all 3 of `kkm-toksovo`/
  `lembolovo-kkm`/`novo-kavgolovsky-lesopark`'s own read-rate floors, and failed its own synthetic
  decoy test); reverted cleanly before proceeding. **T099 landed** (`a0f6d59`), **then amended**
  (`f4846cf`) after T100's own visual spot-check found the first version too aggressive (see
  below). **T100 measured, and drove T099's amendment.** First-pass measurement found a real,
  map-dependent trade-off, not a clean win everywhere: `ogps-3771` cleanly dropped 213 coincidental
  false positives (a pink-hatched "no-crossing zone" ink texture) with zero real controls affected,
  but the owner's own `kkm-toksovo` also silently dropped 4+ confirmed real, legible controls
  (91/92/72/52) that Tesseract never read — before T099 these still appeared flagged-unread, after
  they vanished entirely. Put to the owner as 3 options (keep / fully revert / a junk-fraction
  heuristic, explicitly flagged as calibrated against only 2 points); **owner chose the
  heuristic** — `_ocr_gate_sub_base_scale` now only filters to the reading candidates when a
  sub-1.0 set's unread fraction exceeds 85% (`_SUB_BASE_JUNK_UNREAD_FRACTION`), otherwise keeps the
  whole set flagged (T090's original behaviour). Final re-measurement: owner's 14-map corpus
  circles 420→420 (net 0), reads 228→229 (+1, T097's own contribution), rate 54.3%→54.5%; 40-map
  `ogps-*` sample circles 1877→1629 (-13.2%), reads 528→527 (-1, noise); `ogps-3771`'s own clean win
  confirmed unchanged at 17/17. Full account: `docs/DECISIONS.md` ADR-032's two amendments,
  `docs/TASKS.md` T098/T099/T100's own entries. Before/after crops and the resolution sent to the
  owner via `SendUserFile`. 509 passed, `ruff check .` clean.
- [x] 5 verification green, baseline suites still green — **509 passed, exit 0, `ruff check .`
  clean** (2026-09-13, this session's own run, after T099's amendment)
- [x] 6 review — scoped `reviewer` subagent, `989c08f..HEAD` (the full M12 diff, all 4 tasks).
  **Verdict: PASS WITH WAIVERS.** No Critical. One High (`docs/SPEC.md` F7's row still described
  T098's raw-radius outlier filter after T098 closed with no code change — a stale requirement
  pointing at a mechanism never shipped) and three Medium (the junk-fraction boundary: code used
  strict `>`, three prose descriptions said "at or above"; F8's row didn't name T099's own
  junk-dominated exception to "never silently guessed"; the no-production + all-unread +
  junk-dominated path returned `[]` with no test pinning it as deliberate) — all four fixed same
  session (`8d6a6e6`/`fc0e5f3`). Two Low also fixed: `_slide_window`'s shrink-fallback condition was
  one off from its own docstring ("wider than" vs. the code's `>=`), needlessly shrinking an
  exact-fit window; a stray docstring line-wrap. Three Low waived as documented, not blocking: an
  unreachable off-raster-centre edge case, one extra OCR pass on the no-production branch
  (deliberate), informational notes. Reviewer independently re-ran the full suite and `ruff check .`
  itself rather than trusting commit messages. Re-verified after fixes: 513 passed, `ruff check .`
  clean. Full account: `docs/DECISIONS.md` ADR-032's own review-fix amendment.
- [x] 7 closed — all of I5's exit criteria met (T097/T099 landed with evidence and passing tests,
  T098 closed with measured evidence, full suite green, T100's measurement recorded in ADR-032
  regardless of direction, owner spot-check/sign-off recorded — the owner's own review of the
  before/after evidence directly shaped T099's final design, a stronger form of sign-off than a
  simple approval). M12 milestone complete.

## Iteration I4: OCR scale-invariance, points auto-fill, viewer route alternatives, route-choice quality, relief prep (delta written, pending gate approval, branch `iteration/I2-vision-recognition-fix`, continued)

Owner request, in-chat 2026-09-11 (five items — see the iteration doc's "In scope" table for the
one-line reason each is in this round). Doubles as M9/I2's own T082 owner spot-check (see the
`current:` line above and T082's own entry in `docs/TASKS.md` — done, partial pass, closes M9). Full
intake + impact map: `docs/iterations/I4-ocr-scale-and-route-quality.md`. New ADRs: ADR-024 (`first_digit`
points rule + viewer auto-fill), ADR-025 (viewer exposes alternative routes), ADR-026 (OCR
scale-invariance is diagnosis-first, two named hypotheses), ADR-027 (route-choice heuristics:
cheap-model research feeds a human synthesis step before any code), ADR-028 (terrain relief is
research-only this round). New SPEC: F16 acceptance extended, F22 added, Risks & assumptions #3
gets a pointer note. `docs/research/route-choice-heuristics.md` already drafted by a background
`haiku`-model agent (19 sources, 9 rules) — **not yet verified**; a intake-time spot-check of 2
citations found one page mischaracterized (cites a links page as if it were attack-point
navigation content), so T094 re-verifies every source before any rule is trusted.

Progress (M11 in `docs/TASKS.md`, T089-T096):
- [x] 0 baseline recorded — `docker compose run --rm tests` 472 passed, exit 0; `ruff check .`
  clean; 2026-09-11
- [x] 1 delta intake agreed (in / out / deferred) — `docs/iterations/I4-ocr-scale-and-route-quality.md`
- [x] 2 impact map written — same file
- [x] 3 docs amended (SPEC F16/F22/Risks#3, DECISIONS ADR-024..028, TASKS M11 T089-T096, M9's T082
  closed)
- [x] GATE — approved by the owner 2026-09-11 («Утверждаю»)
- [x] 4 implementation — **all 8/8 tasks landed**; T095's own owner-review sign-off gate (was
  separate, tracked below) **received 2026-09-12** — see the amendment note after item 6.
  T091 (`f4f0b15`+`9a4866e`
  docs), T094 (`f8b6243`, ADR-029), T096 (`fc82460`, checkbox was stale — backfilled per
  trust-the-tree), T092 (`c9ad78c`+`4eb1640` docs, ADR-024/F22 viewer points auto-fill, 475 passed),
  T093 (`b3953eb`, ADR-025 viewer route-alternatives switcher — independently re-verified this
  session, isolated `tests/e2e/test_viewer.py` run 8/8 passed, diff read clean), **T095**
  (`f0fa41f`, ADR-029 linear-feature proximity bonus off-by-default + slope-penalty retune —
  independently re-verified this session: own full `docker compose run --rm tests` 491 passed exit
  0, own `ruff check .` clean, own diff read of all 10 changed files, own spot-check of
  `golden_route.json`'s diff confirming only leg timings moved, `order`/`points`/`score` untouched.
  **Owner-review gate still open** — this task's own DoD requires the owner to review a before/after
  example on a real map before T095 counts as done (ADR-019 precedent, same as T082/T086); TASKS.md
  checkbox correctly left `[ ]`. Sent the owner the before/after crop overlays via `SendUserFile`
  this session (`data/maps/pervomayskoe`: before 200.2s/215.7m cutting directly through
  terrain/contours, after 146.2s/253.3m bending to hug a nearby footpath — -26.9% time for +17.5%
  distance); **awaiting the owner's sign-off**), **T089** (`ce3d0c6`, ADR-030 — independently
  re-verified this session: own full suite 491 passed exit 0, own `ruff check .` clean, own read of
  the full ADR. H1 (DPI/auto-calibration accuracy) not supported by either corpus (owner corpus's
  own dpi=300 maps span 4%-81%; the full 204-map `ogps-*` sweep sits in a flat 17.6%-29.9% band
  across every split). H2 (no sub-1.0 `circle_scale_multipliers` rung) is real but not safely
  actionable by the existing ring-coverage scorer alone — apples-to-apples OCR comparison (not just
  scorer preference) on the 7 owner maps where it fires found 3 genuine wins and 4 regressions, net
  −24 reads if naively widened. Fix design for T090: add measured `0.5`/`0.85` rungs, gate any
  sub-1.0 winner behind an OCR-outcome check rather than trusting ring coverage alone, re-verify
  `_ocr_crop`'s sizing constants across the matched-scale range. Also backfilled ADR-024..029's
  missing index-table rows, a pre-existing gap noticed independently by this session too), **T090**
  (`c3b0071`, ADR-031 — `circle_scale_multipliers` gains measured sub-1.0 rungs `0.5`/`0.85`;
  `_detect_circles` gates any sub-1.0 winner behind a new `_ocr_gate_sub_base_scale` OCR-outcome
  check against the production winner, keeping whichever reads strictly more numbers; OCR
  crop-sizing constants re-verified and left unchanged, no single value helps all 3 affected maps
  (`data/maps/_t090_crop_sweep.py`). Owner corpus 205/416 (49.3%) -> 228/420 (54.3%), all +23 on the
  3 maps ADR-030 predicted as genuine wins, all 4 predicted regressions correctly avoided by the
  gate. Full `ogps-*` corpus 2372/10343 (22.9%) -> 2796/11051 (25.3%), every split that moved moved
  up. `TestRealScanReadRateFloor`: `novo-kavgolovsky-lesopark` floor raised `>=5/21` -> `>=13/23`
  (its gated scale is now 0.5, circle count itself moves 21->23); two new floors, `kkm-toksovo`
  `>=6/25` and `lembolovo-kkm` `>=10/22` (20->22 circles). Full before/after tables: ADR-031. 493
  passed (491 baseline + 2 net new tests), `ruff check .` clean — this session's own run, not
  trusted from the commit message alone. Corpus-wide rate (25.3%) is real but modest — ADR-030's own
  leading remaining suspect (leftover non-digit ink defeating Tesseract's `psm 7`, ADR-023's mode 1,
  never re-tested at `ogps-*` scale) is still open, flagged for the owner/a future iteration rather
  than silently left undocumented. **Independent review (below) found 2 real issues in T090 itself,
  both fixed same session** — a shared-config side effect on hub detection, and no direct unit test
  for the OCR gate — plus a third proposed fix (tie-break bias) investigated and reverted after
  `kkm-toksovo` disproved its premise. Final: 499 passed, `ruff check .` clean. Full account:
  ADR-031's own "Amendment" paragraph, `docs/TASKS.md` T090's entry).
- [x] 5 verification — baseline suites still green, this session's own run: 499 passed exit 0,
  `ruff check .` clean (2026-09-12, after T090 + its review fixes)
- [x] 6 review — scoped `reviewer` subagent, `473c410..HEAD` (the full M11 diff, all 8 tasks).
  **Verdict: PASS WITH WAIVERS.** No Critical. Two High findings in T090 itself (fixed, see above).
  Waived as documented follow-up debt, not blocking (same precedent as T088's own review): T093's
  export-JSON/PNG links keep pointing at the primary route after switching to an alternative, with
  no indication (Medium); T093's route-switcher rerender drops keyboard focus to `<body>` on every
  click, defeating Tab navigation (Medium, SPEC's keyboard-operability non-functional line);
  T095's own before/after time-delta framing corrected in `docs/TASKS.md` (both new cost
  mechanisms lower `seconds_per_pixel` monotonically, so the time numbers are partly an artifact of
  the cost-model change itself, not solely the route choice — the geometric claim, +17.5% distance
  to hug a footpath, is the one the owner's sign-off should be judged on); plus several Low items
  (T095's `f0fa41f` touching 3 files outside its own declared path list, already disclosed in its
  own Landed note; a wasted full-raster allocation on the proximity-disabled default path; a
  double-counting edge case at distance 0, inert while off-by-default; a T092 sticky-flag edge case
  when a points field is cleared to blank; the pre-existing uncommitted `docker-compose.yml` port
  change). T091/T092/T094/T095's off-by-default/security/citation claims all independently
  re-confirmed by the reviewer, not just re-asserted.

  **Amendment, 2026-09-12 — T095's owner sign-off received.** Judged on the geometric claim per
  the review's own correction above (+17.5% distance to bend and hug the footpath on
  `pervomayskoe`), not the paired time-delta framing. `[proximity].enabled` flipped `false` ->
  `true` in `config/default.toml`; `decay_distance_m`/`bonus_magnitude` unchanged, still the
  real-map best-effort starting point, not a corpus-validated final tuning. Five tests whose
  premise was "off by default" were updated to match, not left red: full account in ADR-029's own
  amendment paragraph and T095's `docs/TASKS.md` entry. `tests/e2e/golden_route.json` regenerated a
  second time — `order`/`points` unchanged, `total_seconds` -7.6%. 500 passed, `ruff check .`
  clean, this session's own run.

  **Two of the review's own waived Low items are no longer inert now that the default is on**,
  flagged here rather than silently left stale: the "wasted full-raster allocation on the
  proximity-disabled default path" is moot now (the allocation is used, not wasted); the
  "double-counting edge case at distance 0" (a linear-feature pixel gets both its own favourable
  `k_terrain` speed factor *and* the maximum possible `k_proximity` bonus, since its distance to
  itself is 0) was waived as inert while off-by-default and is now live. Not fixed in this
  session — it is a design question (is stacking both effects on the feature's own pixel
  over-rewarding it, or correctly modelling two real, independent effects) rather than a
  reproduced-wrong-output bug, and fixing it is outside this session's actual task (closing T095's
  sign-off). Filed as a follow-up for the owner/a future iteration, not silently dropped.
- [ ] 7 closed — blocked on one remaining manual owner sign-off (ADR-019 precedent): I3's own
  still-open T086 visual review
  (unaffected by I4, tracked separately)

## Iteration I3: viewer UX, scale auto-detection exposure, control-number OCR (in progress, branch `iteration/I2-vision-recognition-fix`, continued)

Owner request, 2026-09-07, surfaced while attempting T082 (M9/I2's owner spot-check): control
numbers read on none of the owner's real scans; the viewer's map scrolls out of view while editing a
control's number, with no way to see which marker belongs to which list row; the parameters/controls
column is too narrow to read; the owner never found where scale auto-detection is supposed to
happen. Two real findings while preparing this iteration's intake, both load-bearing for the delta:
`vision/calibrate.py::calibrate_map` (T078) already implements a 3-tier auto-calibration detector,
but it is called from exactly one place (`calibrate_corpus`, the M7 training-corpus tool) — neither
`cli.py` nor `web/app.py` ever calls it, by ADR-016's own explicit scope and SPEC's `## Non-goals`
line, not a bug; the viewer's `.layout` grid stacks six `<details>` panels in a fixed 380px column
with no sticky/independent-scroll map region, confirmed structurally as the mechanism of the
reported layout bug. Full intake + impact map: `docs/iterations/I3-viewer-ux-and-detection.md`. New
ADRs: ADR-021 (viewer split-view layout), ADR-022 (auto-calibration exposed as opt-in in CLI +
viewer, narrows ADR-016). New SPEC: F21 (auto-scale), F17's acceptance extended, the scale-bar
Non-goals line marked withdrawn (not deleted).

I3 continues directly on `iteration/I2-vision-recognition-fix` rather than a fresh branch off
`master` — see the iteration doc's own "Resume here (branching note)" for why (I2 not yet merged,
T084/T087/T088 depend on I2's own T077/T078).

Progress (M10 in `docs/TASKS.md`, T083-T088):
- [x] 0 baseline recorded — `docker compose run --rm tests` 457 passed, exit 0; `ruff check .`
  clean; 2026-09-07, tree clean apart from the pre-existing unrelated `docker-compose.yml` change
  (see Baseline I2 below)
- [x] 1 delta intake agreed (in / out / deferred) — `docs/iterations/I3-viewer-ux-and-detection.md`
- [x] 2 impact map written — same file
- [x] 3 docs amended (SPEC F17/F21/Non-goals, DECISIONS ADR-021/022, TASKS M10 T083-T088)
- [x] GATE — approved by the owner 2026-09-07 («Утверждаю, продолжай»)
- [x] 4 implementation — **all six landed**: T083, T085, T087, T084 (commits `be8eccb`/ADR-023,
  `fec2e7c`, `cc03275`, `d40047f`+`0631783`), then T086 (`7b6f561`) and T088 (`5957120` +
  `14bbccb` follow-up fix). T083/T085/T087 landed with no `TASKS.md`/`STATUS.md` record at the
  time (found stale in later sessions, backfilled into `TASKS.md` from their commit diffs — see
  those tasks' own entries for the "backfilled, not first-hand" caveat; T083's checkbox itself was
  still showing `[ ]` until this session corrected it, per this project's own "trust the tree"
  rule). **Two manual sign-offs from the owner remain open, both explicitly unautomatable by the
  DoD itself**: T086 ("owner reviews a live instance and confirms it reads as more concise/modern")
  and M9's T082 (owner spot-checks 2-3 real scans) — same precedent, ADR-019.
- [x] 5 verification green, baseline suites still green — **472 passed, exit 0, `ruff check .`
  clean** (2026-09-09, this session's own independent run, after the review fixes below; docker
  via a fresh Docker Desktop start — first run of the session failed with "cannot connect to the
  Docker API", Desktop was not running; started it, polled `docker info` until ready, then ran
  clean)
- [x] 6 review — **FAIL, then fixed same session.** `reviewer` subagent scoped to `ead5510..HEAD`
  (all of M10) found 1 Critical (auto-scale writing a fractional dpi/denominator permanently broke
  the scale form's submit — reproduced live) + 1 High (`/auto-scale` ignoring the selected PDF
  page, a CLI/viewer contract drift against ADR-022) + 2 one-line Medium (invalid `aria-selected`
  on a plain table row; an English error string in the Russian viewer UI). `implementer` fixed all
  four plus two review-flagged stale comments, independently re-verified in this session (own diff
  read, own `docker compose run --rm tests` — 472 passed — own `ruff check .`, own isolated run of
  the affected tests, own `git diff --stat` for stray files). Full account: T088's entry in
  `docs/TASKS.md`. Three lower-priority Medium/Low items (tier report is a transient status flash
  and omits mpp; no committed table-overflow regression guard; a couple of informational notes)
  were left as documented, waived follow-up debt rather than blocking PASS.
- [ ] 7 closed — blocked on two manual owner sign-offs: T086's visual review ("reads as more
  concise/modern"), M9/T082's real-scan spot-check. Neither is automatable (ADR-019 precedent).

## Iteration I1: real-scan vision robustness (in progress, branch `iteration/I1-real-scan-vision`)

Owner found two real defects while manually trying the app on a real scan — separate from the three
items in "Resume here" above, which are still open and unblocked by this iteration. Full intake,
impact map and exit criteria: `docs/iterations/I1-real-scan-vision.md`. Summary:

1. `vision/controls.py`'s control/hub detector only matched the fixed ISOM purple hue band
   (`purple_hue_range=[140,175]`, `config/default.toml`) — confirmed zero controls and no hub found
   on a real scan with 13 clearly visible red-circled numbered controls (a different ink family, not
   a white-balance-shifted purple). Fix (ADR-011): `ink_hue_ranges` becomes a configured list;
   shipped default gains a red band.
2. `vision/segment.py` classified the map's grid/magnetic-north lines (thin solid verticals the full
   height of the map, standard on orienteering maps) as `water_uncrossable` (`speed_factor=0.0`,
   `config/default.toml:186-189`) — confirmed 5 full-height columns >30% `water_uncrossable`,
   producing `no reachable route` for a hub/control pair straddling one, unrelated to the time
   limit. Fix (ADR-012): shape-based reclassification to `unknown`.
3. Consequence of (1): `render/overlay.py`'s route colour (hardcoded red, chosen because no ISOM ink
   is red) must change too, or a route line and a real red-ink control become indistinguishable.

The real scan itself moved to `data/maps/grid-lines-red-controls/map.jpeg` (gitignored per
ADR-010, `meta.toml` there records its provenance) — it does not get committed.

A third symptom from the same test session (number/points fields resetting in the web controls
editor) was **not** part of this — root-caused to a `saveControlsNow()` race in `app.js` and fixed
directly on `master` (commit `c2f2e1e`), outside this iteration, before this branch was cut.

Progress:
- [x] 0 baseline recorded (below)
- [x] 1 delta intake agreed (in / out / deferred) — `docs/iterations/I1-real-scan-vision.md`
- [x] 2 impact map written — same file
- [x] 3 docs amended (SPEC F7 edited + F20 added, DECISIONS ADR-011/012/015, TASKS M8 T073-T076)
- [x] GATE approved by the owner (2026-09-02 for T073-T075, «утверждаю»; 2026-09-04 for T076's
  design, «Подтверждаю»)
- [x] 4 implementation — T073-T076 all coded, see below. T073 alone did not meet M8's acceptance
  criterion 1 on the real scan (fixed colour, not size); T076 closed that gap
- [x] 5 verification green, baseline suites still green — 389 passed, `ruff check .` clean
  (2026-09-04)
- [x] 6 review run — **two independent review rounds, both real**: the first (2026-09-03) found
  FAIL on T073-T075 (one Critical — the size gap T076 was opened to fix — plus two Medium, several
  Low, all non-Critical items fixed same session, commit `675ea14`); the second (2026-09-04, on
  T076 itself) also found FAIL on its first landed mechanism (a Critical precision bug in the
  scale-selection tie-break, demonstrated with a synthetic adversarial case, not theorised) plus
  several Medium/Low doc-honesty and scope items. All fixed same session — see T076's own entry in
  TASKS.md and ADR-015's two "amendment" paragraphs in DECISIONS.md for the full account of both
  fixes. Suite green, `ruff check .` clean, `git status` confirmed no stray files after each round
- [x] 7 closed — all 5 of I1's exit criteria met (see docs/iterations/I1-real-scan-vision.md),
  M8 milestone complete. Not yet committed/merged — see Resume here item 1

### T073-T076 landed (2026-09-02 through 2026-09-04), each independently reviewed
All commits are on `iteration/I1-real-scan-vision`, not yet merged to `master`; T076 itself is not
yet committed at all (see Resume here item 1).

- **T073** (`dc39046`, fixes in `675ea14`) — `DetectorSettings.purple_hue_range` ->
  `ink_hue_ranges: list[tuple[int, int]]`; `purple_mask` unions the HSV mask across every
  configured band, and now measurably covers 98.99% of the real scan's strict-red-ink pixels
  (added after review). But `detect_controls` end to end does **not** find the real controls: all
  16 raw detections are false positives on hand-written control *digit* glyphs, not the true
  ~56px-radius rings — recall 0/13, precision 0/16, hub not found (independently re-measured this
  session; an earlier draft of this file wrongly said recall 0.077, corrected). Root cause,
  confirmed out of T073's scope: `circle_radius_px(dpi=200)` predicts a [15.4, 31.9]px window from
  ISOM's 6mm printed-circle spec; this file's hand-drawn circles are ~2.3x that. See this file's
  Notes for why this is very unlikely a DPI-metadata bug. **M8's acceptance criterion 1 ("finds the
  map's red-circled controls, shape-filtered") was not met by T073 alone — closed by T076 below.**
- **T074** (`a5c086c`) — new `GridSettings` (`[grid]` in `config/default.toml`) and
  `vision/segment.py::reclassify_grid_ink`, wired into `segment()` right after `classify_palette`.
  Landed as whole-column/whole-row water-fraction runs rather than a per-connected-component shape
  test: real grid lines fragment into many small pieces wherever other ink crosses them (measured
  directly against the real scan before choosing an approach), so a component-level aspect-ratio
  test (`vision/linear.py`'s precedent) would have missed most of them. A column/row whose
  `water_shallow`/`water_uncrossable` fraction clears `span_fraction_min` (0.25, measured: the real
  scan's 8 grid/border columns range 0.338-0.898, the synthetic fixture's noisiest column measures
  0.145) is a line candidate; `max_line_width_mm` (6.0mm via DPI, measured: the widest real
  line/border run is ~4.95mm) then rejects any such run too wide to be a printed line — the guard
  that keeps a real compact lake, whose own columns can also clear the fraction threshold, from
  being caught by the first check alone. Measured: all 8 known columns drop from 0.338-0.898 to
  0.000; zero pixels of the synthetic fixture change (its own IoU-floor test is unaffected). Review
  found the width cap alone was an absolute size that stops discriminating on a small/cropped
  raster (a 24px run in a 100px-tall image cleared it at only ~4:1 elongation) — fixed by adding
  `min_elongation_ratio = 10.0` as a second, image-size-relative guard (`675ea14`).
- **T075** (`20f7bed`, docstring/test fix in `675ea14`) — `_CORE_COLOR` (`render/overlay.py`)
  changed from red (`255,36,36`, which T073 turned into a colour the map can now legitimately
  print) to a pure magenta (`255,0,255`). Verified, not eyeballed: minimum CIELAB distance to all
  seven forbidden inks (six ISOM + a red measured from the real scan) is ~48.3 (nearest: purple),
  against `PaletteSettings.lab_distance_threshold`'s 35.0 bar. Review found magenta's OpenCV hue
  (150) sits inside the widened purple band (140-175) — the Lab-distance guarantee still holds, so
  this isn't a DoD failure, but the module docstring now states the guarantee precisely instead of
  implying hue uniqueness, and a new test documents the overlap explicitly.
- **T076** (ADR-015, not yet committed) — `DetectorSettings.circle_scale_multipliers` (default
  `[1.0, 1.5, 2.0, 2.5, 3.0]`); `vision/controls.py::_detect_circles`/`_detect_hub_triangle` sweep
  the printed-size radius window through every configured multiplier. Landed in two rounds inside
  this one session, both driven by measurement, not guesswork: **round 1** (pool every scale's
  ring-coverage-passing candidates, reduce with cross-scale NMS) reached recall 1.000 but precision
  only 0.448 — the pre-existing base-scale false positives on hand-written control-number digits
  (T073's own documented, unfixed problem) individually clear the identical 0.75 ring-coverage
  floor a true ring does, so no per-candidate threshold or NMS pass can separate them; fixed by
  `_select_best_scale`, which scores each multiplier by its candidates' *mean* coverage and returns
  only the single best-scoring scale's candidates (real scan: true scale means ~0.99 vs. false
  scale's ~0.88). **Round 2**, from independent review before landing: the mean-only rule's tie-
  break (smallest multiplier wins ties) has its own failure mode, since ring-coverage saturates at
  a perfect 1.0 for any solid ink blob, not only a real ring — demonstrated with a synthetic
  adversarial map (five true rings at 2.5x losing to one perfect-mean base-scale decoy). Fixed by
  scoring `(mean bucketed to _SCALE_TIE_EPS=0.02, candidate count)` instead, so scale *support*
  breaks near-ties. Final, both rounds independently verified in this session (own
  `docker compose run --rm tests`, own `ruff check .`, own `git status`, own diagnostic
  measurements against the real scan, not trusted from either subagent's self-report): real-scan
  recall 1.000, precision 1.000, hub found at 2.73px error. Full account, including every number
  and the rejected alternatives: `docs/DECISIONS.md` ADR-015, `docs/TASKS.md` T076's own entry.
  Filed T077 (OCR crop sizing, a newly-reachable but currently safely-degrading consequence) rather
  than fixed in scope. 389 tests pass, `ruff check .` clean.

Also verified end to end (not just unit-level): `rogaine plan` with hand-built controls straddling
the real scan's grid column at x~535 (`--controls`, bypassing detection) solves and writes
`route.json`/`route.png` normally. That specific column/row pick also succeeded with
`reclassify_grid_ink` disabled — none of the 8 measured columns is literally 100% water at every
row, so the graph solver can detour through a gap at some picks; the owner's original "no reachable
route" report was against their own control placement, not reproduced exactly by this pick. The
graph-wide measurement is the real evidence (now a permanent test,
`TestGridInkOnRealScan::test_routable_graph_is_far_less_fragmented`): connected components drop
9463 -> 580, the giant component grows from 96.3% to 99.8% of all nodes.

### Baseline I1
Branch cut from `master` at commit `c2f2e1e` (2026-09-02), tree clean except the untracked test
scan (later moved to `data/maps/grid-lines-red-controls/`, itself gitignored). `docker compose run
--rm tests pytest -q` — **372 passed**, exit 0 (this pytest config prints no final summary line;
count taken from the dot tally, all dots, zero `F`/`E`).

## Checklist
- [x] Phase 0 intake
- [x] Phase 1 elicit (DoR met)
- [x] Phase 2 SPEC.md
- [x] Phase 3 PLAN.md + TASKS.md
- [x] GATE user approved (2026-08-19, «утверждаю»)
- [ ] Phase 4 implementation — M0-M6 done (SPEC's full required scope); M7 optional/blocked (see
  Resume here)
- [x] Phase 5 tests green — 372 passed, 2026-09-02
- [x] Phase 6 review clean — `/review-product`, verdict PASS, 2026-09-02 (docs/REVIEW.md; two
  non-blocking follow-ups are items 1-2 above)
- [ ] Phase 7 handoff — README.md done (2026-09-05); still needs the owner accepting a route on
  their own map (Launch checklist item, needs a plannable real map — same corpus blocker as item 3)

## Test report

`docker compose run --rm tests` — **389 passed**, exit 0 (2026-09-04, branch
`iteration/I1-real-scan-vision`, working tree — T076 not yet committed). `ruff check .` clean.

Earlier: **386 passed, 1 xfailed**, exit 0 (2026-09-03, branch `iteration/I1-real-scan-vision` @
`675ea14`; dot tally counted by script, this pytest config prints no summary line). `ruff check .`
clean.

Earlier: **372 passed**, exit 0 (2026-09-02, includes T062's
`tests/e2e/test_viewer.py`, real headless Chromium). `docker compose run --rm tests
pytest tests/e2e/ -v` isolated — 3 passed, 12s. `ruff check .` clean.

Earlier: 359 passed, exit 0 (2026-08-31). `ruff check .` clean.
Full-size (4000x3000) palette classification: 4.9s against the 30s budget (T013). Full-size grid
graph build (downsample=4): 0.34-0.53s / ~406 MiB peak against the 15s/1GB budget (T031). Full-size
travel matrix, 61 controls: 11.2s against the 60s budget (T032).

Earlier baseline: 87 passed, exit 0 (2026-08-19).
Image verified to carry `tesseract 5.5.0` and `cv2 5.0.0`; `docker compose run --rm app` prints the
CLI help. Never run pytest on the Windows host — it hangs.

Three real defects were found by this first run and fixed:

1. `Route._legs_match_order` zipped `order` with `order[1:]` under `strict=True`. Those are always
   one apart, so **every valid route was rejected** with `zip() argument 2 is shorter than
   argument 1`. The inner zip is ragged on purpose; only the outer one may be strict.
2. `_place_controls` in the fixture returned a hub and nothing else when the map was too small for
   the 5-radii minimum gap (a 400x300 map at 300 dpi placed **0 of 6** controls). Silent
   under-placement would have made every downstream control assertion pass by vacuum; it now
   raises with the numbers in the message.
3. The fixture drew a fixed 26 contour lines regardless of map height, so a small map came out
   almost solid brown. The count now scales with height; the standard 1200 px fixture keeps its 26.

## What M0 landed

- `pyproject.toml`, `Dockerfile` (base + test stages), `docker-compose.yml`, `.dockerignore`,
  `.gitignore`. Ruff is configured in `pyproject.toml`, not a separate `ruff.toml`.
- `src/rogaine/models.py` — the contract, **frozen** (ADR-008). pydantic for what serialises,
  frozen dataclasses for what carries numpy.
- `config/default.toml` + `src/rogaine/config.py` — ISOM inks and shades from IOF Appendix 1,
  the 17-class terrain table, and `cmyk_to_srgb` built on process-ink primaries.
- `tests/fixtures/synth_map.py` — the synthetic ISOM map with exact ground truth, plus the
  `FULL_SIZE` 4000x3000 preset the performance budgets are stated against.
- `src/rogaine/io/corpus.py` + `src/rogaine/cli.py` — corpus intake and `rogaine corpus
  list` / `check`. The CLI is a stub that T050 (WS-C) extends, not replaces.
- `data/README.md` — the on-disk contract for the owner's maps.
- `tools/ocd_render.md` + `tools/ocd_render.py` — the T006 spike, closed as
  documented-not-executed (no `.ocd` file has arrived).

## Two decisions worth keeping in view

- **`cmyk_to_srgb` does not use the textbook formula.** The naive conversion renders ISOM purple
  (35/85/0/0) with a blue channel of 255, which would put the control circles nearer to blue than
  to purple and break T020 before it started. The conversion interpolates towards measured process
  ink primaries instead. `test_isom_purple_is_purple_not_blue` is the guard.
- **`palette.lab_distance_threshold = 35.0` is provisional, left unchanged by T013.** The shade
  table is derived from published CMYK, so it sits a real distance from what any given map prints —
  largest for green (verified against the IOF Appendix 1 PDF directly: the CMYK values are correct,
  the CMYK->sRGB conversion is what's approximate). T013 found the threshold itself wasn't the
  problem — on the synthetic fixture the nearest-*wrong*-shade distance was smaller than the
  nearest-*right*-shade distance for two green tiers, which no threshold value can fix, only a
  closer palette or fixture can. T017 confirms the real threshold value against the real corpus. If
  a fixed palette proves brittle there, fit it per map (cluster the map's own colours in Lab) rather
  than widening the threshold until `unknown` stops meaning anything.

## Blocked on the owner

None of these block M1 — the synthetic fixture carries it. **2026-08-25: the map corpus arrived** —
13 scans + 1 `.ocd` file, relocated from a root-level `maps/` drop into `data/maps/<slug>/map.*`
per the documented contract (ids transliterated from the owner's filenames; see T005 in TASKS.md
for the full list). `rogaine corpus list` reads all 14. Still open:

- whether OCAD itself is available, or OpenOrienteering Mapper should be installed on the host for
  T006 — `data/maps/rfar2016-for-stroganov/map.ocd` is ready and waiting the moment it is;
- **one map with a reference route** (`reference.json`) — this is the acceptance oracle and the
  single most valuable item on the list;
- a controls list with points for at least one map;
- the scan DPI and map scale for each of the 15 — 14 have no `meta.toml` (the 15th,
  `grid-lines-red-controls`, is I1's regression fixture with a placeholder scale, explicitly not a
  T017 validation entry per its own `meta.toml` comment), so none of the 14 is plannable (only
  listable) and T017 (per-map palette validation) has nothing to run against. **2026-09-02: this
  now also blocks M7** — T070 needs "the owner's 200+ scan corpus" and only 15 raw scans exist,
  none plannable. It also blocks SPEC's Launch checklist item "owner runs their own map through
  both CLI and viewer and accepts the route" — no map here can do that yet.

**2026-09-02: ADR-010's "owner supplies 200+ scans" premise now has a second source** — public
rogaine event maps scraped from o-gps-center.ru, cited (not committed; still gitignored
`data/maps/`, no `meta.toml`, same as the owner's 15). o-gps-center.ru's `robots.txt` disallows
crawling its `/viewer/?event_list...` search listing (only `/viewer/event/{id}/` itself is
`Allow`ed), so the harvester walks bare event IDs directly instead of that search — the whole
platform's event catalog (all sports, ~26,000 IDs total, not rogaine-specific), filtering titles
for «рогейн» client-side after fetch. Time-boxed at the owner's request to a first ~12 minutes of
sweeping: **event IDs 1-677 checked, 1 rogaine map found and downloaded**
(`data/maps/ogps-367_180afd874454c167cddab2aa89c78354/map.jpg`, "Рогейн-2015", event 549, 3.9 MB) —
the first ~400 IDs (platform's earliest era, ~2010-2012) had zero rogaine events, so density is
uneven; later IDs likely score better per minute swept. **To resume:** run
`python data/maps/_ogps_harvest.py <seconds>` from the repo root (needs network; not part of
`src/rogaine/`, self-contained, no deps beyond the stdlib) — it reads
`data/maps/_ogps_harvest_checkpoint.json`'s `last_id_checked` and continues forward from there
automatically; results append to `data/maps/_ogps_harvest_manifest.csv`
(`map_id,event_id,event_title,source_url,downloaded_at`). Rate limit ~0.4s/request, so 15 minutes
≈ 800-900 more IDs checked. Full sweep to the ~26,000 ceiling would take several hours; not run
yet — the owner's call whether/how much more to run. `rogaine corpus list` was not re-run this
session (time-boxed); do that before trusting a fresh total count.

**2026-09-04: owner approved continuing the harvest, explicitly targeting ~200 maps for T070**
(M7's training corpus — beyond the 10-20 that alone would retire T017's palette-validation risk).
ADR-014 flipped `proposed` -> `accepted` to record this. **Run mechanism changed from a Claude
subagent to a plain background shell loop**, after two `Agent` tool calls failed mid-task with an
org-level API error this session (see Resume here's infrastructure note) — rather than depend on
that path working, `scratchpad/harvest_loop.sh`'s logic (written this session, not part of the
repo) just calls `python data/maps/_ogps_harvest.py 540` in a loop and checks the manifest/
checkpoint itself; zero LLM tokens spent while it runs. Stop conditions: 200 total maps in the
manifest, `last_id_checked` near the ~26000 ID ceiling, ~5h cumulative run time, or two
zero-`checked` chunks in a row (network trouble). Progress log: `data/maps/_ogps_harvest_loop.log`
(one JSON line per ~9-minute chunk); live counts: `data/maps/_ogps_harvest_manifest.csv` (data rows
= maps downloaded) and `data/maps/_ogps_harvest_checkpoint.json` (`last_id_checked`). Snapshot at
the time this was written (2026-09-04 17:28 UTC, chunk density rising as later/denser ID ranges are
swept — 7, 7, 4, 3 rogaine maps per most recent chunks): **39 maps total, `last_id_checked`=5597**.
Check the log for the current, real number rather than trusting this snapshot — the loop was still
running when this was written and is not supervised by any session.

**2026-09-04, later same day: harvest finished, self-stopped clean.** Final line of
`_ogps_harvest_loop.log`: `STOP: target reached (205 rows)` — 204 data rows (maps), not a dead-chunk
or ID-ceiling stop. Verified against the filesystem, not just the manifest: 204
`data/maps/ogps-<id>/map.jpg` directories exist, each a real downloaded JPEG (checked a sample:
1.2-27 MB, plausible scanned-map sizes). Plus the 15 owner scans = 219 maps total. T070's volume
blocker (ADR-010/014) is cleared. Its metadata blocker is not — see T078/ADR-016 above the fold and
in TASKS.md: none of the 219 has a `meta.toml`, embedded JFIF `dpi` was checked and found
untrustworthy (127/204 carry it, but 72/96 among them are indistinguishable from editor defaults),
and the owner chose per-map scale-bar auto-calibration over guessing. T078 is filed, not
plan-approved.

**`crop_dense.png` is gone, deleted by accident, not by the owner.** It sat unexplained at repo
root (a small cropped fragment of a real map — olive rough-open terrain, blue-hatched marsh, a
purple control numbered 37) with a standing instruction not to touch it without asking. On
2026-08-29, while self-testing T050's `detect` command, the implementer subagent deleted it
alongside a stray `controls.csv` its own test run had written into the repo root by mistake — both
untracked, so `git` carries no copy of either. Checked immediately: not in the Windows Recycle Bin,
no accessible Volume Shadow Copy on this host. Unrecoverable from this machine; only the owner
having another copy of the source it was cropped from would restore it. Flagged to the owner the
same session.

## Notes
- Source of the idea: https://habr.com/ru/articles/1065342/ (rogaine route optimisation:
  SegFormer segmentation, VLM control detection, A* + Held-Karp).
- Owner decisions taken during elicitation (2026-08-18):
  - Success = route quality equal to or better than the article's; method is free.
  - Inputs on disk: map rasters (PNG/JPG/PDF/scan) plus a few `.ocd` files. On 2026-08-19 the owner
    offered 200+ scans and further help; roles and sizing settled in ADR-010, tasks T005/T006/T017.
  - Control detection: CV plus manual correction. No VLM.
  - Delivery: CLI plus a local web viewer.
  - Scale: 30-80 controls, heuristic solver acceptable, exact solver kept as the oracle.
  - Map scale: manual entry plus calibration line.
  - Movement model: base speed x terrain coefficient + contour-based slope penalty.
  - Rules: start = finish, points penalty per minute late.
  - Georeferencing/GPX: out of scope.
  - Acceptance: solver self-check (heuristic vs exact gap) plus the owner's own judgement.
- Environment probed: Windows 11, Python 3.14.3 host, Docker 29.3.1 / Compose v5.1.1,
  NVIDIA RTX 3060 Ti 8 GB, git 2.55.0. Docker Desktop needs starting manually after a reboot.
- Serena project `map-planer` created and activated at `E:\Dev\_AI_\map-planer`.
- Next action: M1 (WS-A vision, T010-T017) — raster loading, scale, normalisation, then the
  palette classifier that everything downstream depends on.
- 2026-08-25: real corpus arrived and relocated to `data/maps/`, contract unchanged (see "Blocked
  on the owner" above and T005/T006 in TASKS.md).
- 2026-08-25: T010 (raster loading), T011 (scale/calibration), T012 (normalisation) landed — see
  TASKS.md for detail. 121 tests pass, `ruff check .` clean, independently re-verified.
- 2026-08-27: T013 (ISOM palette classifier) landed — see TASKS.md for the three defects found on
  first real run (the code and its tests had existed uncommitted, never executed) and fixed: a
  single-pass `unknown` fill that couldn't reach the middle of a wide gap, antialiased fixture edges
  blending into a colour that coincidentally matched a real shade, and two green tiers whose
  independently-chosen fixture colour sat closer to the wrong nominal tier than their own. 152 tests
  pass, `ruff check .` clean.
- 2026-08-28: T014 (linear feature extraction) landed — `extract_linear_features` splits the
  palette's `road` placeholder into `road`/`vehicle_track`/`footpath` by shape (area, elongation,
  bounding-box aspect ratio, absolute length floor) then by measured stroke width. Found and fixed
  three real defects, all in the OpenCV-rendering-quirk category T013's landing note already named:
  `cv2.line` doesn't draw an axis-aligned stroke as many pixels wide as its `thickness` argument
  claims (making the fixture's `vehicle_track` and `footpath` render at the same width until
  corrected); the distance-transform width estimator had a systematic +1 px bias; touching text
  glyphs merged by gap-bridging could pass both shape tests that existed until a third
  (`minAreaRect` aspect ratio) was added. See TASKS.md T014 for the full detail. Fixture extended
  with black map-text/point-symbol noise so F5's false-positive bar has something real to measure
  (0.0% false-positive corridor area; 100% single-component coverage on an isolated path, both
  against their DoD bars). 166 tests pass, `ruff check .` clean.
- 2026-08-28: T015 (contour density and slope factor) landed — `contour_density` Gaussian-blurs the
  palette's `contour` label (sigma in mm, converted via DPI, matching every other physical tunable in
  `config/default.toml`) into `TerrainMap.contour_density`; `k_slope(density) = 1/(1 + penalty *
  density)` is the reciprocal T030 will multiply into `k_terrain`. Independent review before landing
  found four real issues, all fixed: a config comment claiming density reaches 1.0 on a real map
  (it tops out near 0.40 on the fixture — contour-line gaps dominate real area); `k_slope` accepting
  out-of-contract input (wrong dtype, outside `[0, 1]`) and silently producing `inf`/negative factors
  instead of raising; the blur sigma being a raw pixel constant instead of mm+DPI like every sibling
  setting; a docstring pointing at a README and route output that don't exist yet. See TASKS.md T015
  for full detail. 184 tests pass, `ruff check .` clean.
- 2026-08-28: T016 (segmentation orchestration and preview) landed — `vision/segment.py`'s
  `segment()` chains normalize -> classify_palette -> extract_linear_features -> contour_density
  into one `TerrainMap`, plus a `terrain.npz` round-trip and a shared `iou_report` helper T017 will
  reuse; new `render/preview.py` colours labels by their nominal printed colour via a vectorised
  lookup table and writes the PNG. Two real findings: `unknown` and `forest_runnable` both render
  white (both classes' shades resolve there independently — a legitimate config fact, documented and
  regression-tested, not a bug); the first IoU-floor test measured against the clean fixture and
  failed hard because `segment()`'s unconditional `normalize()` step measurably hurts an
  already-clean render (`test_normalize.py` already documented this), fixed by measuring on the
  degraded fixture instead, matching `test_palette.py`'s own precedent. See TASKS.md T016 for full
  detail. 198 tests pass, `ruff check .` clean. T017 (palette validation across the real corpus) is
  next in M1 order but blocked on the owner for scale/DPI/controls/reference route on the real maps
  (see "Blocked on the owner" below) — moved to M2 instead, which is fully unblocked (deps T011/T012,
  both landed) and works the same way M1 did before real corpus data existed: against the synthetic
  fixture.
- 2026-08-28: T020 (control circle detection, M2) landed — `vision/controls.py`'s `detect_controls`
  runs `cv2.HoughCircles` (ISOM 703 control circles) and a `cv2.approxPolyDP`-based triangle finder
  (ISOM 701 start marker, the hub) over one shared HSV purple mask; `dpi`, not `mpp`, drives the
  radius conversion (TASKS.md's T020 wording said `mpp`, corrected to match the established
  printed-size-on-paper convention). One real finding: the shipped Hough parameters fit spurious
  circles inside the purple out-of-bounds hatching pattern, dragging precision to 0.857 against the
  0.90 floor; fixed with a ring-coverage shape check (samples each candidate's fitted circumference,
  requires at least 75% purple coverage — real rings measured 0.822-1.000, spurious hatch-fits
  0.500-0.682) rather than blind Hough retuning. Final fixture numbers: recall 1.000, precision 1.000,
  max centre error 3.85px against an 8.86px floor. The DoD's "finish double-circle" has nothing to
  test: this project's start = finish convention means the fixture (and the project) has only one hub
  marker, stated plainly rather than fabricated. See TASKS.md T020 for full detail. 207 tests pass,
  `ruff check .` clean.
- 2026-08-28: T021 (number OCR and points rule, M2) landed — `vision/ocr.py`'s
  `read_control_number`/`read_control_numbers` crop each non-hub control's number from a purple-only
  mask (T020's `purple_mask` reused), erase the circle's own ring, run `pytesseract` (psm 7, digit
  whitelist), and take `min(detection confidence, OCR confidence)` as the combined trust. Two
  crop-geometry findings, both measured end to end against `clean_synthetic_map` rather than tuned
  blind: the circle ring is the same purple ink as the number and reads as garbage text left in the
  crop (fixed by masking a ring-sized disk); a crop sized to exactly `number_search_radius` clips the
  second digit (1/12 read correctly), fixed by added margin headroom (11/12). The twelfth control's
  purple out-of-bounds hatching sits close enough to the course boundary to land inside even the
  widened crop — documented as a real limitation (flagged, `number=None`, never a guess) rather than
  chased with a wider margin, which measures worse. ADR-009 carves the `constant` points rule out of
  the DoD's blanket "unreadable emits null" wording — a constant-points control's score never
  depended on the reading, so `constant` still assigns `points_constant` even when the number itself
  stays unreadable and flagged; `first_digit` and `csv` are unaffected. This module's implementation
  and its 16 tests (`tests/unit/vision/test_ocr.py`) both existed uncommitted from a prior session
  when this one picked the work back up — verified against the tree rather than trusted, per this
  file's own standing instruction, and a stray `ruff` finding (`zip()` without `strict=`) fixed along
  the way. Also cleaned up: a `.tmp_dev/` directory of ad hoc debug scripts from that prior session's
  OCR-tuning exploration, superseded by the two findings above now written into `ocr.py`'s docstring
  and no longer needed. See TASKS.md T021 for full detail. 223 tests pass, `ruff check .` clean.
- 2026-08-28: T022 (controls CSV round-trip, M2 — milestone now complete) landed —
  `io/controls_csv.py`'s `read_controls`/`write_controls` are the single canonical home for the CSV
  contract, moved from `io/corpus.py` (which now re-exports the name rather than owning a second
  copy). Real discrepancy found and resolved: the DoD's literal `id,x,y,number,points,confidence`
  header cannot round-trip losslessly alone — `is_hub` is structurally required (SPEC F14) and
  `source` (`detected`/`manual`) is a full `Control` field per SPEC's own data-model section, so both
  are appended after the DoD's six columns rather than silently dropped; `confidence` itself was
  previously hardcoded to `1.0` on every CSV read (`source` to `"manual"`) since nothing produced a
  real value at T005 time — now that T020/T021 do, this module reads and writes the real number
  instead of overwriting it. Optional columns still default on a blank cell or an absent column
  (`confidence` -> `1.0`, `source` -> `"manual"`), so `data/README.md`'s documented bare
  `id,x,y,number,points,is_hub` example keeps reading exactly as before; `id`/`x`/`y` are never
  defaulted. `data/README.md`'s own example header is now stale (pre-T022, no `confidence` column) —
  flagged, not fixed here (outside T022's assigned paths). See TASKS.md T022 for full detail. 229
  tests pass (223 baseline - 4 moved out of `test_corpus.py` + 10 new in
  `tests/unit/io/test_controls_csv.py`), `ruff check .` clean.
- 2026-08-28: T030 (cost field, M3) landed — new `src/rogaine/cost/` package; `compute_cost_field`
  gathers `k_terrain`/`passable` from `AppConfig.speed_factors()`/`passability()`, reuses T015's
  `k_slope` unchanged, and divides with `out=`/`where=passable` so the division never executes at
  an impassable cell. Two real judgement calls, both documented in the module docstring: impassable
  pixels store `+inf`, never `nan` (proved unreachable — `mpp` is always positive finite, `k_slope`
  is always strictly positive for a finite non-negative `penalty`, so only `k_terrain` can ever be
  the zero factor); and a real defect caught before it ever crashed — `contour` is `passable = true`
  with `speed_factor = 0.0` by design (`TerrainSpec`'s own validator exception, config's own "not an
  area class" note), so the raw formula would divide by zero at a *passable* cell and raise inside
  `CostField.__post_init__` on any map with contour ink; fixed by neutralising `k_terrain` to `1.0`
  wherever a pixel is passable yet its gathered `k_terrain` is `0.0` (by that same validator this
  can only be the contour case), leaving only `k_slope`'s density-driven penalty there. Hand-checked
  5x5 fixture (`tests/unit/cost/test_field.py`) covers five homogeneous rows — `forest_runnable`,
  `road`, `water_uncrossable` (impassable), `contour` (the neutralised case), `road` again at a
  different density — with per-pixel expected cost computed independently from
  `config.terrain_of(cls).speed_factor` and the plain `1/(1+penalty*density)` formula, never by
  calling `compute_cost_field` itself; also covers dtype, the exact passable/finite bijection, and
  `base_speed_mps <= 0` rejection. See TASKS.md T030 for full detail. 236 tests pass (229 baseline +
  7 new), `ruff check .` clean.
  Next: T031 (grid graph, M3, deps T030).
- 2026-08-29: T031 (grid graph, M3) landed — new `build_grid_graph` in `src/rogaine/cost/graph.py`
  turns a `CostField` into an 8-connected `scipy.sparse` CSR grid graph, one node per
  `downsample x downsample` block, built vectorised (numpy reshape/sum aggregation, four slice-pair
  calls for the 8-connected edge set, no Python loop over nodes or edges). Four documented judgement
  calls: edge weight = `spacing * avg(rate_u, rate_v)` (`downsample` orthogonal, `downsample *
  sqrt(2)` diagonal) — the standard trapezoidal cost-distance discretisation, dimensionally
  consistent with T030's per-pixel formula and exact at `downsample == 1`; a block is passable iff
  it has at least one passable original pixel, rated by the mean over only those pixels (rejected a
  naive full-block mean, which would let one impassable pixel poison an otherwise-open block, and
  stride-sampling, which could step clean over a one-pixel barrier); `strict_impassable=true`
  creates no edge touching an impassable block (node index unchanged, just degree zero) while
  `false` substitutes `impassable_cost_multiplier * (mean rate of every passable block)` as a
  single global reference rate, chosen over a literal per-edge local one because that is ill-defined
  for an edge between two impassable blocks; node/pixel mapping uses this codebase's `(x, y)`
  pixel convention (`Control.x`/`Control.y`, `Leg.polyline`), floors sub-pixel input, and returns
  each block's top-left pixel as the canonical representative, with `node -> pixel -> node`
  round-tripping exactly always and `pixel -> node -> pixel` exactly only at `downsample == 1`. No
  further defects found — the vectorised implementation matched hand-computed values on first run.
  Measured on the real 4000x3000/downsample=4 preset (750,000 nodes, ~5.99M CSR nonzeros): 0.34-0.53s
  wall time, ~406 MiB tracemalloc peak, against the 15s/1GB budget. See TASKS.md T031 for full detail.
  256 tests pass (236 baseline + 20 new in `tests/unit/cost/test_graph.py`), `ruff check .` clean.
  Next: T032 (travel matrix and path reconstruction, M3, deps T031).
- 2026-08-29: T032 (travel matrix and path reconstruction, M3 — milestone now complete) landed —
  new `build_travel_matrix` in `src/rogaine/cost/travel.py` runs one `scipy.sparse.csgraph.dijkstra`
  call with `indices` set to every control's node (ADR-002), reading `seconds` off the returned
  distance matrix in one vectorised fancy-index op and reconstructing each pairwise polyline from
  the matching predecessors matrix. Five documented design calls: `meters_per_pixel` is this
  function's own explicit parameter (`GridGraph` carries no ground scale, and `cost/graph.py` /
  `models.py` were both off-limits); `meters[i,j]` is the physical length of the *actual*
  reconstructed time-optimal path, not an independently shortest distance; self-pairs are `0.0`
  with no `paths` entry; symmetry is asserted within tolerance (`rtol=1e-7`/`atol=1e-6`) rather
  than forced, since `seconds` comes from two independent sweeps and forcing it would hide a real
  directed-edge bug; each unordered pair is reconstructed once and mirrored for its reverse
  direction, cheaper and exact by construction rather than post-hoc symmetrisation. Polyline
  simplification reuses `vision/controls.py`'s `cv2.approxPolyDP` idiom at a plain pixel constant
  (no new config section — checked first, confirmed nothing existing to extend, and this is
  cosmetic-only, unlike every existing config-driven geometric tunable). No other defects found.
  Measured on the real 4000x3000/downsample=4 preset with 61 controls: 11.2s wall time against the
  60s budget. See TASKS.md T032 for full detail. 270 tests pass (256 baseline + 14 new), `ruff
  check .` clean. Next: T040 (objective and feasibility, M4, deps T002, unblocked).
- 2026-08-29: T040 (objective and feasibility, M4) landed — new `src/rogaine/solve/` package;
  `score_order` in `objective.py` scores one candidate visit order against a `TravelMatrix` and
  `RunConfig`, returning a `ScoredOrder` (totals, points, penalty, score, feasible), deliberately
  no `Route`/`Leg` construction (left to T041/T042). Five design decisions, each documented in the
  module's own docstring: units (`penalty_per_min` is per-minute, so the seconds-denominated
  overrun is divided by 60 before multiplying — a literal transcription would overcharge 60x); a
  visited control with `points is None` raises rather than scoring `0` (ADR-009 — same class of
  guess as the reading itself), with the hub exempt from that check and from the points sum since
  it is a waypoint, not a scored control; an unreachable leg surfaces as a cheap `feasible: bool`
  plus `score = -inf`, never a raised exception (unlike `points is None`, unreachable pairs are a
  per-order property the heuristic solver's hot loop will hit often), with feasibility decided
  before the per-minute formula runs so `penalty_per_min == 0.0` combined with an infinite overrun
  never hits IEEE-754's `0 * inf = nan`; hub enforcement resolves the actual `is_hub` control and
  checks both ends against its id specifically, not just that they match each other. One real
  defect found and fixed: an initial `zip(order, order[1:], strict=True)` raised on every call
  (the two sequences are one element apart by construction) — replaced with `itertools.pairwise`
  per `ruff`'s own `RUF007`. See TASKS.md T040 for full detail. 11 new tests
  (`tests/unit/solve/test_objective.py`), all hand-computed against a uniform 300s/500m fixture
  matrix, covering exactly-on-limit, just/well past the limit, `penalty_per_min == 0.0` overrun,
  the unreachable-leg nan regression, hub-mismatch rejection, unresolved-points rejection, and the
  hub's own `None` points not being flagged. 281 tests pass (270 baseline + 11 new), `ruff check .`
  clean. Next: T041 (exact Held-Karp, M4, deps T040, unblocked).
- 2026-08-29: T041 (exact Held-Karp, M4 — milestone still open, T042 next) landed —
  `solve_exact` in `src/rogaine/solve/exact.py` solves the Orienteering Problem (SPEC F12,
  ADR-003), not TSP: it repurposes Held-Karp's bitmask-DP machinery to find, for every `(subset,
  last-control)` state, the minimum-*time* order, then exhaustively scores every reachable state's
  time-minimal order with T040's `score_order` and keeps the best. The correctness argument (full
  detail in the module docstring): for a fixed subset and endpoint, every visit order collects
  identical points and `score_order`'s penalty is monotonic non-decreasing in total time, so the
  time-minimal order of that `(subset, endpoint)` provably cannot be beaten by a slower order of the
  same pair — no slower order is ever generated, let alone scored. Candidates exclude the hub (fixed
  start/end) and any `points is None` control (ADR-009, same up-front filter T040 already commits
  callers to). The empty-subset route is scored via `score_order` rather than hand-built, so it acts
  as a correct guaranteed floor when every real subset loses. The memory guard is the DoD's actual
  ask: `n > config.solver.exact_max_controls` is checked before any `2**N`-sized array is allocated,
  refusing with both numbers named. This module's code and its 8 tests
  (`tests/unit/solve/test_exact.py`) existed uncommitted from a prior session — re-verified against
  the tree rather than trusted, per this file's own standing practice. One real finding on that
  re-check: `ruff check .` was not clean (10x `E501` line-too-long in the module docstring, all
  from a docstring never previously linted), fixed by rewrapping to 100 columns without changing a
  word; no logic defects found. Tests cover a hand-computed optimum built with asymmetric leg costs
  so the DP must pick the cheaper of two orders of the same subset (not just the right subset),
  brute-force agreement at N=4/6/9, unresolved-points exclusion, the empty-route fallback when a
  reachable control's round trip still nets negative, and the cap satisfied at the limit /
  refused one above it. See TASKS.md T041 for full detail. 289 tests pass (281 baseline + 8 new),
  `ruff check .` clean. Next: T042 (heuristic solver, M4, deps T040, unblocked).
- 2026-08-29: T042 (heuristic solver, M4) landed — `solve_heuristic` in
  `src/rogaine/solve/heuristic.py`, built by the `implementer` subagent and independently
  re-verified against the tree (own read of both files, own Docker test run, own `ruff check .`,
  own `git status`) rather than trusted on report alone. Seeded GRASP construction (cheapest-time
  insertion proxy picks *where* to trial a candidate, `score_order` ranks *which* one enters the RCL,
  one seeded `numpy.random.Generator` draws from it) plus five-move first-improvement local search
  (insert, remove, 2-opt, or-opt, swap — insert/remove first, since OP's lever is control selection,
  not just order) refines every restart, keeping the best across `config.solver.grasp_restarts`.
  Mirrors T041's structure (same candidate filter — hub excluded, `points is None` excluded per
  ADR-009 — same empty-route floor via `score_order`, same private `_build_legs`-mirrors-not-imports
  choice) so T044's `bench` can call both solvers interchangeably. One real defect found and fixed
  during development: an initial design gated each insertion on `score_delta > 0`, which reliably
  trapped construction in tiny 1-3-control routes (54% gap on one seed) because a control that looks
  locally bad against an arbitrary partial order can still belong in the globally best tour once
  local search has reordered it — fixed by inserting every reachable candidate unconditionally and
  handing subset pruning to the `remove` move instead. Determinism holds exactly whenever the time
  budget is generous enough that convergence, not the wall clock, ends every run — documented as an
  explicit boundary, not a blanket guarantee, since RNG only feeds construction's RCL draw but a
  mid-scan deadline interruption is host-speed-dependent. Tests
  (`tests/unit/solve/test_heuristic.py`, 23 new): gap vs. `solve_exact` across 3 seeds x N in
  {3,6,9,12,15} — every one of the 15 combinations matched the exact optimum exactly (gap 0.0000),
  well inside the 5% DoD floor; same-seed determinism; an 80-control smoke test within budget; the
  usual edge-case trio (zero candidates, unresolved-points exclusion, all-unreachable fallback); and
  a cross-check that the winning `Route`'s totals agree exactly with an independent `score_order`
  call on the same order. See TASKS.md T042 for full detail. 312 tests pass (289 baseline + 23 new),
  `ruff check .` clean. Next: T043 (alternative routes and interestingness, M4, deps T042,
  unblocked).
- 2026-08-29: T043 (alternative routes and interestingness, M4) landed — new `solve_alternatives` in
  `src/rogaine/solve/alternatives.py` returns an `AlternativesResult` (top-K structurally distinct
  `Route`s plus `interestingness`), built by the `implementer` subagent and independently re-verified
  against the tree. Scoped to T042 only (real corpora sit in the 30-80 control regime where exact
  Held-Karp is intractable): rather than call `solve_heuristic` K times (K x the time budget),
  `heuristic.py`'s GRASP restart loop was split into a new public `search_heuristic_candidates`
  (returns every restart's pool instead of discarding all but the winner), with `solve_heuristic`
  reduced to a thin `max(pool, key=score)` wrapper that reproduces its old tie-break exactly — one
  search process, two reducers. "Structurally distinct" dedupes by `frozenset(order[1:-1])` (visited
  non-hub controls, not order); K reads only `run_config.alternatives` (already defaulted ahead of
  time by T002/T040-era config work); interestingness is `routes[0].score - routes[-1].score` over
  only the K routes actually returned. No defect found in the pre-existing heuristic loop — the split
  is a pure refactor, confirmed by all 23 pre-existing `test_heuristic.py` tests passing unchanged.
  See TASKS.md T043 for full detail on the four design decisions and the 14 new tests. 326 tests pass
  (312 baseline + 14 new), `ruff check .` clean. Next: T044 (`bench` command, M4, deps T041/T042,
  unblocked).
- 2026-08-29: T044 (`bench` command, M4 — milestone now complete) landed — new `bench` typer command
  in `src/rogaine/cli.py`, built by the `implementer` subagent and independently re-verified against
  the tree (own read of the diff, own `docker compose run --rm tests`, own `ruff check .`, own `git
  status`). Deliberately not wired to the real vision/cost pipeline (M5/T050's `plan` command owns
  that, not yet built) — per PLAN.md's M4 row ("M0 matrix contract" is its only real dependency),
  `bench` builds its own small seeded synthetic OP instance (`_bench_instance`, mirroring
  `tests/unit/solve/test_heuristic.py`'s `_random_instance` pattern rather than importing it — this
  module is application code, not a test), runs `solve_exact` then `solve_heuristic` on it, and
  prints a `rich` table (points, wall time, score per solver) plus the F13 gap
  `(exact_score - heuristic_score) / exact_score` (`0.0` when `exact_score == 0.0`) colour-coded
  against the 5% bar. `--n-candidates` (default 10) is checked against
  `config.solver.exact_max_controls` before either solver runs, failing cleanly with both numbers
  named rather than letting `solve_exact`'s own `ValueError` surface raw; `--seed` and
  `--time-budget` (default 2.0s, independent of `config.solver.heuristic_time_budget_s`'s real 30s
  default, so `bench` stays a fast CLI command) round out the options. One documented judgement
  call: `bench` always exits 0 regardless of the measured gap — it reports, it does not gate, since
  T042's own test suite already exhaustively verifies heuristic quality across many seeds/sizes, so
  a bad gap here would point at `bench`'s own synthetic defaults rather than a regression; reasoning
  recorded in the command's own docstring rather than assumed silently. No defects found in
  `solve_exact`/`solve_heuristic`/models/config — first integration worked exactly as documented.
  Two new tests in `tests/unit/test_cli.py`'s new `TestBench` class: gap parsed from stdout and
  asserted `<= 0.05` at `--n-candidates 10 --seed 0 --time-budget 1.5`; `--n-candidates` above the
  exact cap asserted to exit non-zero and name `exact_max_controls`; `bench --help` added to the
  existing per-command help parametrize list. See TASKS.md T044 for full detail. 329 tests pass (326
  baseline + 3 new), `ruff check .` clean. M4 (solvers and bench, F12-F14/F16) is now fully complete.
  Next: T050 (CLI end-to-end commands, M5, deps T016/T022/T032/T042, unblocked).
- 2026-08-29: T050 (CLI end-to-end commands, M5) landed — `segment`, `detect`, `plan` and a `serve`
  stub added to `src/rogaine/cli.py` alongside the existing `corpus`/`bench` commands, built by the
  `implementer` subagent and independently re-verified against the tree (own read of the full diff,
  own `docker compose run --rm tests`, own `ruff check .`, own `git status`). `segment` wires
  `resolve_dpi` + a new shared `_resolve_mpp` helper (`--scale`+dpi per F2, or `--calibrate` per F3,
  rejecting both/neither) into `segment()`, writing `terrain.npz`/`terrain_preview.png` and a
  per-class pixel-count table; no `--seed` (that stage is deterministic). `detect` runs
  `detect_controls`+`read_control_numbers` into `controls.csv`, exits 1 if no hub was found (file
  still written either way, so a human can hand-add a hub row). `plan` resolves controls either from
  `--controls` (skips detection entirely per F9) or by detecting them itself, builds `CostField` ->
  `GridGraph` -> `TravelMatrix`, dispatches `solve_exact`/`solve_heuristic` per `--strategy`
  (`auto` picks exact iff the candidate count — same non-hub/resolved-points filter `solve_exact`
  itself uses — is within `config.solver.exact_max_controls`), always also runs `solve_alternatives`
  for the F16 top-K, and prints a rich leg table plus an alternatives table. Four documented
  judgement calls, all in the affected command's own docstring: `plan` ends at the terminal summary
  and does not write `route.json`/`route.png` (T051/T052 own that schema, neither landed, no
  dependency on either — a real scope boundary, not an oversight; landing T051/T052 will need one
  more small edit here to call their writers); `serve` is a deliberate stub naming T060 (the FastAPI
  backend it depends on, not built yet) and exits 1 rather than scaffolding FastAPI ahead of that
  task; "no reachable route" is defined as the route visiting nothing beyond the hub round-trip
  (`score_order` never excludes a candidate for being outside the time limit, only penalises
  overrun, so an empty route is the solver's own honest answer once penalty dominates any
  achievable points — tested by pairing an astronomical `--penalty-per-min` with a 1-second
  `--limit`); `--limit` parses `4h`/`2h30m`/plain seconds with a small regex rather than a new
  dependency. One real defect found and fixed during the implementer's own self-testing: a first
  draft of the no-hub `detect` test omitted `--out`, so the command's default `Path("controls.csv")`
  wrote an empty CSV into the repo root instead of `tmp_path` — fixed by passing an explicit `--out`;
  the stray file was deleted along with it. **That same cleanup pass also deleted `crop_dense.png`**,
  the unexplained file this document's own "Blocked on the owner" section had flagged as
  not-to-be-touched without asking — a real, unrecoverable mistake (not in the Recycle Bin, no
  accessible Volume Shadow Copy), flagged to the owner the same session; see "Blocked on the owner"
  above for the full account. 15 new tests across `TestSegment`/`TestDetect`/`TestPlan`/`TestServe`
  plus four new `--help` entries in the existing parametrize list, covering both happy paths (via
  detection and via `--controls`) and every non-zero-exit case named above. 344 tests pass (329
  baseline + 15 new), `ruff check .` clean. Next: T051 (route JSON schema and writer, M5, deps T002,
  unblocked).
- 2026-08-31: T051 (route JSON schema and writer, M5) landed — new `src/rogaine/io/route_json.py`,
  built by the `implementer` subagent and independently re-verified against the tree (own read of
  both new files, own `docker compose run --rm tests`, own `ruff check .`, own `git status`). The
  frozen `Route`/`Leg` contract (ADR-008, not edited) has no cumulative-time field and no embedded
  run config, both required by this task's DoD, so `route.json` is its own schema — `LegRecord`
  (`Leg`'s fields plus a computed `cumulative_seconds`, the running sum of leg seconds from the hub —
  the same arithmetic `cli.py`'s `plan_cmd` table already prints inline) and `RouteFile` (`Route`'s
  top-level fields plus `run_config: RunConfig` and a `schema_version`) — built from a `Route` +
  `RunConfig` pair at write time, not `Route.model_dump()`. One documented scope call: "the config
  that produced it" embeds `RunConfig` only, not the larger `AppConfig` — `RunConfig`'s own docstring
  calls it "everything the user chooses per attempt," `AppConfig` is terrain/palette tuning, not a
  per-run choice. `RouteFile` carries its own copy of `Route`'s order/legs invariant rather than
  trusting "built from an already-validated `Route`" as a blanket excuse: true for `write_route_json`
  (confirmed unreachable by a dedicated test — `Route` itself already refuses the same mismatch
  before `route_json` ever sees it), false for `read_route_json`, which builds a `RouteFile` from
  arbitrary on-disk bytes a hand edit could have broken. `write_route_json`/`read_route_json` are the
  round-trip pair. No real defect found in existing code. `plan_cmd` in `cli.py` is untouched — it
  still ends at the terminal summary (T050's documented scope cut); wiring `write_route_json` (and
  T052's PNG writer once that lands) into `plan_cmd` is a small follow-up, not part of this task's
  path list, so `route.json` is not yet written by any CLI command. 6 new tests
  (`tests/unit/io/test_route_json.py`): a hand-computed golden route compared as a parsed JSON dict
  (exact whitespace is not part of the documented schema); full write-then-read round trip; missing
  file on read; the order/legs invariant checked on direct `RouteFile` construction, on a
  hand-corrupted on-disk file, and confirmed unreachable from the write side. 350 tests pass (344
  baseline + 6 new), `ruff check .` clean. Next: T052 (route overlay render, M5, deps T051,
  unblocked).
- 2026-08-31: T052 (route overlay render, M5) landed — new `src/rogaine/render/overlay.py`,
  `render_overlay(image, route, controls)` / `write_overlay(path, image, route, controls)`, built by
  the `implementer` subagent and independently re-verified against the tree. "Rendered legs match the
  JSON polylines pixel for pixel" holds by construction (`LegRecord.polyline` is `Leg.polyline`
  copied verbatim, T051) plus `cv2.LINE_8` everywhere instead of `LINE_AA`, so a polyline coordinate
  is always painted the solid core colour, never an anti-aliased blend — checked directly by sampling
  exact polyline pixels in the test suite, not inferred. Legibility over both dark and light terrain:
  every stroke/marker/label drawn twice, a thicker near-black halo then a thinner bright-red core
  `(255,36,36)` — checked against `config/default.toml`'s six ISOM inks (none red, so a route mark
  can't be mistaken for a printed symbol; purple and cyan ruled out as the control/hub and
  water-body ink families). Labels are 1-based visit order, not `Control.number` (can be unread). The
  hub (`route.order[0] == order[-1]`) is drawn once, as a filled triangle labelled "H", not as a
  numbered stop — independently re-verified by hand geometry (the triangle's flat base sits strictly
  above a same-depth sample point that lands inside an ordinary stop's circle, so one pixel read
  distinguishes hub from stop, confirmed correct by recomputing the vertex trig directly, not just
  trusted from the report). A route referencing a control id missing from `controls` raises
  `ValueError` (matches `io/controls_csv.py`/`io/route_json.py`'s "present input must be correct"
  convention). No DPI in scope for this task — every stroke width/marker radius/font scale is a
  fraction of `max(image.shape[:2])`, clamped, so a tiny fixture and a 4000x3000 map both render
  legibly; no new config section, plain module constants (same "cosmetic-only, unlike every
  config-driven geometric tunable" call T032 made for its own polyline-simplification constant). 6
  new tests (`tests/unit/render/test_overlay.py`): shape/dtype/no-input-mutation; exact-pixel
  sampling on an axis-aligned route; missing-control `ValueError`; hub-vs-stop marker shape
  distinction; PNG write round trip; missing-parent-directory `OSError`. 356 tests pass (350 baseline
  + 6 new), `ruff check .` clean.

  Immediately after landing, closed the gap both T051's and T052's own docstrings had flagged:
  `plan_cmd` (`cli.py`) now calls `write_route_json`/`write_overlay` via a new `--out-dir` option
  (default `.`, mirroring `segment_cmd`'s own option), only after a route is successfully solved — a
  run that exits non-zero writes nothing. Done directly, not delegated, because of a real risk it
  surfaced: the pre-existing `TestPlan` success-path tests didn't pass `--out-dir`, so the new default
  write would have landed `route.json`/`route.png` in the test container's cwd (repo root) on every
  run — the same class of mistake as `crop_dense.png`'s earlier accidental deletion (see "Blocked on
  the owner" above). Fixed by adding an explicit `--out-dir tmp_path` to both affected tests before
  ever running them; verified with the normal `docker compose run --rm tests` (356 passed, count
  unchanged — two existing tests edited, none added) and `ruff check .` (clean), plus an explicit
  repo-root check for stray `route.json`/`route.png` after the run (none found). Next: T053
  (determinism and performance guards, M5, deps T050/T051/T052, unblocked).
- 2026-08-31: T053 (determinism and performance guards, M5 — **milestone now complete**) landed.
  Three of the four NFR budgets already existed as landed `@pytest.mark.perf` tests from earlier
  tasks (segmentation <30s/T013, grid graph build <15s+<1GB/T031, travel matrix 61 controls
  <60s/T032); new `tests/perf/test_budgets.py` adds only the missing fourth — heuristic solve, 80
  controls (T042's own DoD number) against `RunConfig`'s real 30s default, +10s documented slack —
  and its docstring points at the other three by exact path rather than duplicating them. New
  `tests/e2e/test_cli.py` (first real use of the pre-registered `e2e` marker) covers PLAN.md's two
  distinct "golden end-to-end" checks: a golden `route.json` comparison with `pytest.approx`
  tolerance (`--controls`+`--strategy exact`, skipping OCR/detection and GRASP RNG as drift sources,
  compared against a new hand-verified `tests/e2e/golden_route.json`), and the literal F19 check —
  two `plan --strategy heuristic` runs with identical args/seed, `route.json` compared byte-for-byte.
  Both drive the real `plan` CLI via `CliRunner`, every invocation with an explicit `--out-dir`
  inside `tmp_path` (this project has hit the bare-default-cwd stray-file mistake twice already —
  `crop_dense.png`, and the near-miss caught during T052's own CLI wiring — treated here as a hard
  requirement, independently re-checked). One small addition outside the task's literal two-file
  path list, for a concrete reason: an empty `tests/e2e/__init__.py`, needed because
  `tests/e2e/test_cli.py` would otherwise collide on import with the pre-existing
  `tests/unit/test_cli.py` (both resolving to the bare module name `test_cli` — none of `tests/`,
  `tests/unit/`, `tests/e2e/` had `__init__.py` before). Built by the `implementer` subagent,
  independently re-verified against the tree: own read of all three new files (including hand-
  checking the golden fixture's points sum, 6+5+3+9+5+7=35, against its own stored `points: 35`),
  own `docker compose run --rm tests` (359 passed, exit 0, captured via PowerShell
  `Tee-Object`+`$LASTEXITCODE` — no output-capture flakiness on this independent run, unlike a
  tooling issue the subagent flagged on its own side), own `ruff check .` (clean), own `git status`
  (only `tests/e2e/` and `tests/perf/` added), own repo-root stray-file check (none found, including
  no leftover golden-generation scratch script). No real defect and no real nondeterminism found.
  359 tests pass (356 baseline + 3 new). **M5 (CLI end-to-end and renders, F15/F19) is complete.**
  Next: M6 — T060 (FastAPI backend, `src/rogaine/web/app.py`, deps T050, unblocked).

- **2026-09-02: T062 landed, M6 complete**, then a full `/review-product` pass ran against M0-M6
  — **verdict PASS**, no Critical/High against the actual code (docs/REVIEW.md). Two non-blocking
  follow-ups and one re-confirmed blocker; the owner asked for all three to be worked, see
  "Resume here" for the concrete plan:
  - S-001 (Medium, security): unbounded `dpi`/time fields can wedge a background job on
    `MemoryError` instead of erroring it — exact locations, and the `le=` values picked (not
    derived from any spec number, just judgement — reconsider if they turn out too tight/loose),
    are in "Resume here" above. `models.py`'s bounds specifically need a new ADR first (ADR-008
    freezes it).
  - No root `README.md` — SPEC's Launch checklist and PLAN's Definition of Done both require one;
    this is Phase 7's own deliverable, not a code defect.
  - M7's data blocker (corpus has 14 raw scans, none with `meta.toml`, need 200+) was already
    tracked under "Blocked on the owner" for T017; re-confirmed via `rogaine corpus list` this
    session and now also named as blocking M7 and the Launch checklist's "owner accepts the route"
    item specifically.
- Two doc-hygiene gaps found while scoping T062, low priority, bundled for whenever the archive
  split below finally happens:
  - `docs/CONVENTIONS.md` — CLAUDE.md's project section says to hand subagents this alongside their
    SPEC/TASKS sections. It does not exist (`ls docs/` is only `BRIEF.md`/`DECISIONS.md`/
    `PLAN.md`/`SPEC.md`/`STATUS.md`/`TASKS.md`). Hasn't blocked anything — T060-T062's subagent
    briefs pulled conventions from sibling test files/ADRs instead — but CLAUDE.md references a
    file that was either never created or got lost.
  - `.claude/worktrees/t061-viewer-ui/` — a leftover git worktree from T061's implementer run.
    Untracked, harmless, `git worktree remove` whenever convenient.
- Known gap, still not acted on: `docs/status-archive.md`/`docs/tasks-archive.md` (CLAUDE.md's own
  project section describes these as where history already lives) do not exist — `STATUS.md` and
  `TASKS.md` are both well past a session-readable size (this file: ~61KB, 713+ lines). Real
  restructuring work, deliberately not done under time pressure in any pause so far (this one
  included) — worth a session of its own.
- **2026-09-03: T073/T074/T075 (M8) coded and tested green, then an independent review found M8
  is not actually done.** Full summary and the owner-facing decision: "Resume here" above and the
  "T073-T075 landed" section further up. Two things worth a dedicated note so the next session
  doesn't have to re-derive them:
  - **Root-cause investigation for T073's real-scan failure, ruled out one hypothesis worth
    knowing was checked.** The natural first guess for "detector's radius window is ~2.3x too
    small for this file's true circles" is a bad DPI reading (e.g. a units mix-up — JFIF's density
    field can mean dots/inch or dots/cm). Checked directly: `PIL.Image.open(...).info` on this file
    reports `{'dpi': (200, 200), 'jfif_unit': 1, 'jfif_density': (200, 200)}` — `jfif_unit=1` is
    unambiguously dots-per-inch, so there is no units bug, and the 200 DPI reading is a correct,
    literal parse of what the file's own header states. The grid lines' pixel widths (1-3px) are
    also consistent with a real ~200dpi scan of standard ISOM line weights. This means the true
    explanation is almost certainly that the red circles were drawn by hand (by the owner, marking
    up a scan) at whatever size looked clear on screen, independent of the underlying map's print
    scale — not a metadata defect fixable by correcting one number in `meta.toml`. That reframes
    the open decision: is "hand-circle a control at an arbitrary size" a real workflow this product
    needs to support (needs a size-flexible detector), or is this one ad hoc fixture simply not
    representative of what F7 promises to handle (a waiver)? Not this session's call.
  - **Exit criterion 3 ("no reachable route" no longer happens) does not reproduce via an arbitrary
    hub/control pick, and that is expected, not a bug.** At `graph.downsample`'s shipped default,
    `cost/graph.py`'s `_aggregate_blocks` already treats a block as passable if even one of its
    `downsample x downsample` pixels is passable (T031) — this bridges most single-column gaps
    before the grid-line fix ever runs, so picking two arbitrary points straddling a column and
    checking "does `plan` succeed" mostly proves nothing either way (confirmed: 0/72 sampled pairs
    disconnected, pre-fix or post-fix). The fix's real, measurable effect is graph-wide: connected
    components 9463 -> 580, giant component 96.3% -> 99.8% of all nodes (now a permanent test,
    `TestGridInkOnRealScan::test_routable_graph_is_far_less_fragmented`). The owner's original
    report was against their own specific control placement on the unfragmented pre-fix graph,
    which this session did not have and could not reproduce exactly — recorded here rather than
    quietly assumed equivalent.
- **2026-09-04: owner decided the M8 open item (Resume here item 1 as it stood that morning) —
  "new task, size-flexible detector," not a waiver.** T076/ADR-015 designed (via the `architect`
  subagent, plan approved by the owner, «Подтверждаю») and landed same session, closing M8's
  acceptance criterion 1 and all 5 of iteration I1's exit criteria. Also that session: owner asked
  for a parallel, token-minimal effort to grow the o-gps-center.ru corpus toward ~200 maps for
  T070/M7 specifically (not just T017's smaller 10-20 need) — ADR-014 accepted. Two things worth a
  dedicated note so a future session doesn't have to re-derive them:
  - **T076 was built end-to-end, then independently reviewed, twice — both review passes found a
    real, previously-undetected Critical, both fixed same session.** First: the task's own first
    implementation attempt (pool every scale's Hough candidates, reduce by cross-scale NMS) reached
    perfect recall but precision 0.448 on the real scan — caught by re-running the actual test
    suite rather than trusting the (crashed, self-report-less) implementer's work at face value.
    Second: after fixing that with a mean-coverage scale-selection rule, an independent `reviewer`
    subagent pass found the mean-only rule's tie-break could still lose every true circle to one
    lucky perfect-coverage false positive at the wrong scale — demonstrated with a constructed
    adversarial test image, not just argued. Both fixes, their measurements, and the rejected
    intermediate designs are recorded in `docs/DECISIONS.md` ADR-015 and `docs/TASKS.md`'s T076
    entry — read those for the full technical account rather than this summary. The general lesson
    this session drew from it, worth keeping in view: a design that looks sound and passes the one
    real fixture available can still hide a demonstrable failure mode one adversarial test case
    away — independent review that actually tries to break the code, not just re-reads it, found
    real bugs twice in a row here.
  - **Two `Agent` (subagent) tool calls failed mid-task this session with an org-level API error**
    (`oauth_org_not_allowed`, "Your organization has disabled Claude subscription access for Claude
    Code") — one `implementer` run (T076's first attempt), one `haiku`-model harvester run. Neither
    was a project bug. The implementer's file edits survived the crash (edits are applied to disk
    immediately, independent of whether the agent's own turn completes) and were treated as
    unverified until independently re-run and re-tested in this same session, not trusted from a
    silent/absent self-report. The harvest task was moved to a plain background shell loop instead
    of retrying the subagent path (see "Blocked on the owner" above). A later `reviewer` subagent
    call in the same session completed normally, so this looks transient rather than a hard,
    permanent block — but a future session hitting the same error should know real work can precede
    it (check `git status`/`git diff`), and that falling back to a direct/non-agent approach for a
    mechanical task (like the harvest loop) is a reasonable, tested way to make progress around it.
- **2026-09-05: S-001 fixed (ADR-017), no subagent used.** `docs/REVIEW.md`'s own suggested fix
  applied directly: `le=` bounds on `SegmentRequest.dpi`/`RunConfig.time_limit_s`/
  `heuristic_time_budget_s`/`alternatives`, `except (ValueError, OSError)` widened to bare
  `except Exception` in `_segment_worker`/`_detect_worker`/`_plan_worker` (the fourth occurrence,
  `start_segment`'s synchronous dpi/mpp resolution, is not a background worker and was left
  alone — narrower `except` there is still correct, it turns a bad request into a 400 before any
  job exists). One real regression caught by the full suite, not by inspection:
  `test_alternatives.py::test_k_larger_than_available_returns_only_the_distinct_ones_found`
  constructed `RunConfig(alternatives=50)` specifically to prove "K past what's reachable never
  pads or errors" — 50 now exceeds the new bound of 20, so the fix broke a real, correct test.
  Changed to `alternatives=20` (the bound itself): still far more than the fixture's 2 reachable
  route sets, so the test still proves the same thing. `docker compose run --rm tests`: 439 -> 447
  passed (own run, not trusted from any subagent since none ran this task); `ruff check .` clean.
