# Status archive

Historical `docs/STATUS.md` content, moved here per `close-session`'s step 4b (the live file was
124KB, far past the ~20KB budget, because this archival step had never been run before
2026-09-16). Moved verbatim, not summarised. Read `docs/STATUS.md`'s `## Resume here` for current
state — this file is history only, kept for when the *why* behind an old decision is the actual
question.

## Project narrative through 2026-09-15 (M0-M13, Iterations I1-I6)

This is the original `current:` field from `docs/STATUS.md`'s top-of-file status header — a
running chronological narrative that grew from a one-line field into the project's own history,
covering M0 through M13 (Iterations I1-I6) before Iteration I7 began.

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
  gate approved by the owner 2026-09-13 («Утверждаю, продолжи»).** **2026-09-13, next session
  (context-limit handoff): T103 and T106 found already landed on the tree** (`0c5f1f7`/`fe863b3`,
  `774f10c`/`b1f2e06`) **but their own docs bookkeeping was never written** — the landing session ran
  out of budget first. Backfilled per trust-the-tree; T103's own landing had verified only in an
  isolated worktree with no `data/maps/`, so its real-corpus floors had never actually run against
  the main tree — doing so this session found 3 floors regressed (a long-standing club-mascot-logo
  false positive T103 now correctly excludes, not a real regression), fixed
  (`b91677a`). **T101 and T102 landed** (`55f0d86`, `dc0fb1c`) — see their own `docs/TASKS.md`
  entries for the full diagnosis/fix/measurement account. 518 passed, `ruff check .` clean.
  **2026-09-14: T104 and T105 landed** (`255f1cf`/ADR-034 docs `73c5d34`, `3aeaaf2`/ADR-035 docs
  `74427aa` — all four commits predate this session; this session found them already on the tree,
  matching `docs/TASKS.md`'s own `[x]` checkboxes, trust-the-tree confirmed rather than assumed).
  T104's own diagnosis overturned its DoD's two-colour-print premise (ADR-034: the real cause was a
  `_select_best_scale` tie-break gap, `ogps-8078` 2/52→40/52 reads). T105 shipped a measured, named
  `_AUTO_PLACEMENT_CONFIDENCE_FLOOR = 0.80` (ADR-035) — a small accepted cost per ADR-033's own
  advance risk acceptance, not a measured win (drops 4/524 real detections, all confirmed genuine).
  **Same session: T107 landed** (add-control click-to-place, matching T106's calibration-line
  flow) — new `state.mode = "add-once"` routed through T106's own `beginArmedPointerGesture` helper
  (its docstring had already reserved this exact extension point); armed-state affordance uses the
  `--warning` tokens per F17's own text naming both tools, not just the click mechanics; new
  `TestAddControlClickToPlace` e2e case. **All 7/7 M13 tasks now landed** — see `docs/TASKS.md`
  T107's own entry for the full account. 520 passed (519 + T107's own test), `ruff check .` clean,
  `git status` confirmed only the three touched files changed (this session's own run, not trusted
  from any commit message). M13 implementation phase closed; verification/review still open.
  **2026-09-14, next session: milestone review run** (scoped `reviewer` subagent, `ba27ff1..HEAD`,
  the full M13 diff) — **verdict PASS WITH WAIVERS**, 1 High + 6 Medium + 6 Low, all fixed except
  two Medium named as measured follow-up risk (same T098 unmeasured-filter precedent) and three Low
  left as documented notes; also independently re-verified two fixes (H1 a CSS contrast bug, H2 a
  missing keyboard path) found already applied, uncommitted, in the working tree from an earlier
  review pass whose own session had run out of budget before it could commit or write up docs — same
  interrupted-session pattern as T103/T106's own backfills. Full account: `docs/DECISIONS.md`
  ADR-033's own review amendment, `docs/TASKS.md` T101/T102/T106/T107's own entries. Re-verified
  after every fix: 522 passed (520 + 2 new e2e cases), `ruff check .` clean, this session's own run.
  M13 implementation and review both closed; only the owner's own manual spot-check (ADR-019
  precedent, I6's own exit criterion) is left open before M13/I6 can close.
  **2026-09-14, same session: new owner bug report** — a fourth screenshot-backed report, this time
  on `data/maps/ogps-8620_502cda4f6c774e8ecb86d063a71895f6`: a solved route crossing a magenta ISOM
  709 out-of-bounds polygon and a lake, dark-green "fight" vegetation ("оливка") treated as merely
  slow rather than forbidden, a power line (ЛЭП) costed as a normal path, and >=6 unread control
  numbers — plus an explicit owner request to research orienteering route-choice theory and revisit
  the OCR approach from scratch, citing the project's own reference article
  (https://habr.com/ru/articles/1065342/) and a companion demo video the owner downloaded locally.
  Became **Iteration I7** (`docs/iterations/I7-real-map-routing-correctness-and-ocr-vlm-fallback.md`),
  split into **M14** (map/routing correctness, T108-T112, diagnosis-first per ADR-038) and **M15**
  (opt-in VLM OCR fallback, T113-T115, ADR-039) — delta intake, impact map and docs amendments
  (SPEC F4/F5/F8/F10/Summary/Integrations/Non-goals/NFR-Security/Risks#4, F23 added; DECISIONS
  ADR-036..039) all written this session; **gate approved 2026-09-15** («Утверждаю, продолжи»).
  Research already done, not deferred: `docs/research/route-choice-heuristics.md`
  (T094) already covers "бег в мешок"/handrails (Rules 2+7, implemented via T095) and "road beats
  bushwhacking" (Rule 1, already solved exactly by the existing Dijkstra solve) — this iteration's
  own finding is that the solver's *inputs* (terrain classification, OCR) are wrong on real scans,
  not that the route-choice heuristics feeding it are missing. The Habr article and the owner's own
  video (frame-extracted via `ffmpeg` this session, since no fetch tool could read YouTube's page)
  confirmed the reference implementation uses a trained SegFormer segmenter and a tiled VLM pass for
  control numbers — ADR-036 adopts a much cheaper region-closure CV fix for the terrain-classification
  half instead of the reference's neural segmenter (disproportionate for this defect), while ADR-039
  does adopt a narrow, opt-in VLM fallback for OCR specifically, explicitly revisiting ADR-009 and
  narrowing `docs/SPEC.md`'s "no network calls at runtime"/"no VLM" lines — flagged loudly to the
  owner before the gate, not silently overridden. **2026-09-15: implementation starting** — see
  "Iteration I7" below for the live progress checklist.

## Old `## Resume here` snapshots (2026-09-15 pause through 2026-09-16 mid-session)

**2026-09-16: T109 and T113 both landed and verified this session** (picked up from the
2026-09-15 pause below, which is now historical — kept for the failure-mode record). Branch
`iteration/I2-vision-recognition-fix`, tree not yet committed this session (see next action).
Full suite **537 passed**, `ruff check .` clean, this session's own foreground run (522 baseline +
4 new `test_segment.py` closure tests + T113's 11 `test_ocr_vlm.py` tests). Full account in
`docs/TASKS.md`'s own T109/T113 entries.

**T109**: verified against all three of `ogps-8620`'s real polygons (not just T108's own largest
measurement target) plus the purple-fragment false-positive check the prior session's kill
checkpoint had flagged as still outstanding. That verification surfaced a real second finding: a
synthetic-fixture IoU regression (`open_land` 0.9020, floor 0.95) caused by a course-overprint
control bridging into the real polygon via shared `purple_100` ink (the exact untested edge case
T108 had flagged) — fixed with a third guard, `min_solidity_fraction=0.70` (convex-hull solidity;
a bridged two-blob "dumbbell" measures far lower than any genuine polygon). Re-verified clean.

**T113**: the 3 test failures the prior session's kill checkpoint reported never reproduced this
session — `test_ocr_vlm.py` is 11/11 green in a fresh container run, `DEFAULT_MODEL =
"claude-haiku-4-5"` confirmed current against the live model table.

**2026-09-15 pause (historical — the kill-checkpoint failure mode T109/T113's own re-verification
fixed):** paused mid-implementation with T108/T111/T112 landed and T109/T113 mid-work, both killed
subagents having stuck in the same pattern — launching a background/Monitor-tracked test run then
ending their own turn before its notification arrived back to them, rather than running it inline.
T109 had already confirmed the fix on the largest polygon alone; T113 had an earlier,
never-diagnosed 3-failure suite run. Both were resolved the following session as described above —
logging the pattern here as the reason that session's own equivalent runs were kept in the
foreground / explicitly awaited instead. (The same background-test-run failure mode recurred once
more on 2026-09-16 during T114's own implementer dispatch — see `docs/STATUS.md`'s current Notes
for that instance; three sessions now show the same pattern, which is why the rule belongs in
`CLAUDE.md`, not just here.)

Also queued at that pause point, all now landed: T108 (out-of-bounds/water diagnosis), T111 (ЛЭП
diagnosis), T113 (VLM OCR client module) — no shared-file conflicts between the three. Ordering
that applied then: T109 (after T108, shared-primitive/serial, full suite re-run before T110/T112
start), T110 (after T109), T112 (after T111), T114/T115 (after T113, strictly serial).

`master` last release point 640dce9; working branch `iteration/I2-vision-recognition-fix`, not yet
merged. **Iteration I2 approved 2026-09-05; M9's four automated tasks (T079, T080, T081, T077) all
landed 2026-09-06. Only T082 (owner spot-check, manual, cannot be automated) is left open.** Full
intake + impact map: `docs/iterations/I2-real-scan-detection-failure.md`. New ADRs: ADR-018 (tighten
`purple_mask`'s red ink band by measurement), ADR-019 (acceptance is the owner spot-checking 2-3
real scans), ADR-020 (`Control.radius_px`, added for T077).

**Why (original bug, for context):** owner reported the app doesn't read control numbers at all and
misdetects controls on most maps. Reproduced on all 13 of the owner's own scans under `data/maps/`:
2x-10x over-detection, ~0% OCR read rate on 10/13, hub not found on 8/13.

**What actually landed, in order (M9, T079/T080/T081/T077):**
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
5. **T082** — owner spot-checks 2-3 of their own real maps (`rogaine detect`/`plan` output and/or
   the viewer) post-fix and confirms circle positions, hub, and numbers look right (ADR-019 — no
   automated floor, this is the acceptance gate). Done 2026-09-11, partial pass — M9 closed.

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

## Baseline I2
`docker compose run --rm tests` — 447 passed, exit 0; `ruff check .` clean. 2026-09-05, branch
`iteration/I2-vision-recognition-fix` off `master`@640dce9, tree clean apart from one pre-existing,
unrelated uncommitted change (`docker-compose.yml`, `app` service's host port 8000→8001 — not this
session's edit, doesn't touch the `tests` service, left alone; owner has not said whether to keep,
commit or revert it).

## Baseline I6
`docker compose run --rm tests` — 513 passed, exit 0 (own run, not piped through `tail`); `ruff
check .` clean (run inside the `tests` container — `docker compose run --rm app ruff check .` fails,
the `app` image has no `ruff` on `PATH`, use `tests`). 2026-09-13, branch
`iteration/I2-vision-recognition-fix` @ `ba27ff1`, tree clean.

## Iteration I6: real-map detection gaps and viewer UX (M13, all 7 tasks landed + reviewed 2026-09-14; closure still blocked on the owner's own manual spot-check)

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
- [x] 4 implementation — **7/7 tasks landed: T101 (`55f0d86`), T102 (`dc0fb1c`), T103 (`0c5f1f7`/
  `fe863b3`, fix `b91677a`), T104 (`255f1cf`/ADR-034), T105 (`3aeaaf2`/ADR-035), T106 (`774f10c`/
  `b1f2e06`), T107 (this session, not yet committed)** — see each task's own `docs/TASKS.md` entry
  for the full diagnosis/fix/measurement account (T103/T106 were landed by an earlier, budget-
  interrupted session and backfilled per trust-the-tree; T104/T105 landed by a session between that
  one and this one, found already on the tree and confirmed against `docs/TASKS.md`'s own checkboxes
  rather than assumed; T107 implemented this session). 520 passed (519 + T107's own test),
  `ruff check .` clean, `git status` confirmed clean apart from T107's own three touched files (this
  session's own run).
- [x] 5 verification green, baseline suites still green — same 520-passed/clean run as above,
  2026-09-14
- [x] 6 review — scoped `reviewer` subagent, `ba27ff1..HEAD` (the full M13 diff, all 7 tasks, plus
  the working tree). **Verdict: PASS WITH WAIVERS.** No Critical. One High (H-1: the `add` toggle's
  persistent multi-placement mode had been left on the old raw-pointerdown behaviour, no
  click-vs-drag protection and no armed affordance, when T107 only extended `add-once`'s flow —
  fixed). Six Medium, all fixed except two named as measured follow-up risk rather than an
  unmeasured code change (M-4: a shallow watercourse 8-connected to a bank-lined body could be
  over-promoted to uncrossable, not yet reproduced against a real map; M-5: `_keep_largest_ink_
  cluster`'s edge+competition guard doesn't cover a wide-gap split with off-edge competing ink, not
  yet reproduced either — both same precedent as T098's reverted unmeasured filter). Six Low, three
  fixed (prose/citation corrections, an `aria-pressed` markup gap), three left as documented notes
  (`docs/CONVENTIONS.md` referenced by `CLAUDE.md` doesn't exist — pre-existing, not an M13
  regression; two harmless margin/cost notes). Also independently re-verified, not just trusted: two
  fixes (H1 a CSS contrast bug on `#add-control-btn`'s armed state, H2 a missing keyboard `Enter`
  path for `add-once`) found already applied but uncommitted, untested and undocumented in the
  working tree — from an earlier review pass whose own session had run out of budget before it could
  commit or write up docs (same interrupted-session pattern as T103/T106's own backfills). Full
  account: `docs/DECISIONS.md` ADR-033's own review amendment, `docs/TASKS.md` T101/T102/T106/T107's
  own entries. Reviewer independently ran the full suite (520 passed) and `ruff check .` (clean)
  itself. Re-verified after every fix, this session's own run: **522 passed** (520 + 2 new e2e
  cases: `TestToggleAddModeArmedState`, `TestAddControlClickToPlace`'s new Enter-key case), `ruff
  check .` clean.
- [ ] 7 closed — blocked on the owner's own manual spot-check of `ogps-6802`/`ogps-7302`/`ogps-8078`
  plus the two viewer UX flows (ADR-019 precedent, I6's own exit criterion) — the only remaining
  exit criterion, not something a session can do unsupervised. **Still open as of 2026-09-16** — see
  `docs/STATUS.md`'s current `## Blocked on the owner`.
- [ ] 8 deploy (optional, not yet decided)

## Iteration I5: control-circle/number false negatives and false positives on real scans (closed, M12 complete)

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
  clean; 2026-09-12, tree clean (this session closed T095's own owner-sign-off first)
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

## Iteration I4: OCR scale-invariance, points auto-fill, viewer route alternatives, route-choice quality, relief prep (M11 implemented + reviewed; closure still blocked on I3's own T086)

Owner request, in-chat 2026-09-11 (five items — see the iteration doc's "In scope" table for the
one-line reason each is in this round). Doubles as M9/I2's own T082 owner spot-check (T082 — done,
partial pass, closed M9). Full intake + impact map: `docs/iterations/I4-ocr-scale-and-route-quality.md`.
New ADRs: ADR-024 (`first_digit` points rule + viewer auto-fill), ADR-025 (viewer exposes
alternative routes), ADR-026 (OCR scale-invariance is diagnosis-first, two named hypotheses),
ADR-027 (route-choice heuristics: cheap-model research feeds a human synthesis step before any
code), ADR-028 (terrain relief is research-only this round). New SPEC: F16 acceptance extended, F22
added, Risks & assumptions #3 gets a pointer note. `docs/research/route-choice-heuristics.md`
already drafted by a background `haiku`-model agent (19 sources, 9 rules) — verified by T094 after
an intake-time spot-check found one citation mischaracterized.

Progress (M11 in `docs/TASKS.md`, T089-T096):
- [x] 0 baseline recorded — `docker compose run --rm tests` 472 passed, exit 0; `ruff check .`
  clean; 2026-09-11
- [x] 1 delta intake agreed (in / out / deferred) — `docs/iterations/I4-ocr-scale-and-route-quality.md`
- [x] 2 impact map written — same file
- [x] 3 docs amended (SPEC F16/F22/Risks#3, DECISIONS ADR-024..028, TASKS M11 T089-T096, M9's T082
  closed)
- [x] GATE — approved by the owner 2026-09-11 («Утверждаю»)
- [x] 4 implementation — **all 8/8 tasks landed**; T095's own owner-review sign-off gate **received
  2026-09-12**. T091 (`f4f0b15`+`9a4866e` docs), T094 (`f8b6243`, ADR-029), T096 (`fc82460`,
  checkbox was stale — backfilled per trust-the-tree), T092 (`c9ad78c`+`4eb1640` docs, ADR-024/F22
  viewer points auto-fill, 475 passed), T093 (`b3953eb`, ADR-025 viewer route-alternatives switcher
  — independently re-verified, isolated `tests/e2e/test_viewer.py` run 8/8 passed, diff read
  clean), **T095** (`f0fa41f`, ADR-029 linear-feature proximity bonus off-by-default +
  slope-penalty retune — independently re-verified: own full suite 491 passed exit 0, own
  `ruff check .` clean, own diff read of all 10 changed files, own spot-check of
  `golden_route.json`'s diff confirming only leg timings moved, `order`/`points`/`score` untouched),
  **T089** (`ce3d0c6`, ADR-030 — independently re-verified: own full suite 491 passed exit 0, own
  `ruff check .` clean, own read of the full ADR. H1 (DPI/auto-calibration accuracy) not supported
  by either corpus. H2 (no sub-1.0 `circle_scale_multipliers` rung) is real but not safely
  actionable by the existing ring-coverage scorer alone — apples-to-apples OCR comparison on the 7
  owner maps where it fires found 3 genuine wins and 4 regressions, net −24 reads if naively
  widened. Fix design for T090: add measured `0.5`/`0.85` rungs, gate any sub-1.0 winner behind an
  OCR-outcome check rather than trusting ring coverage alone), **T090** (`c3b0071`, ADR-031 —
  `circle_scale_multipliers` gains measured sub-1.0 rungs `0.5`/`0.85`; `_detect_circles` gates any
  sub-1.0 winner behind a new `_ocr_gate_sub_base_scale` OCR-outcome check against the production
  winner, keeping whichever reads strictly more numbers. Owner corpus 205/416 (49.3%) -> 228/420
  (54.3%). Full `ogps-*` corpus 2372/10343 (22.9%) -> 2796/11051 (25.3%). Independent review found 2
  real issues in T090 itself, both fixed same session — a shared-config side effect on hub
  detection, and no direct unit test for the OCR gate. Final: 499 passed, `ruff check .` clean).
- [x] 5 verification — baseline suites still green: 499 passed exit 0, `ruff check .` clean
  (2026-09-12, after T090 + its review fixes)
- [x] 6 review — scoped `reviewer` subagent, `473c410..HEAD` (the full M11 diff, all 8 tasks).
  **Verdict: PASS WITH WAIVERS.** No Critical. Two High findings in T090 itself (fixed). Waived as
  documented follow-up debt, not blocking: T093's export-JSON/PNG links keep pointing at the
  primary route after switching to an alternative, with no indication (Medium); T093's
  route-switcher rerender drops keyboard focus to `<body>` on every click, defeating Tab navigation
  (Medium, SPEC's keyboard-operability non-functional line); plus several Low items (T095's
  `f0fa41f` touching 3 files outside its own declared path list, already disclosed; a wasted
  full-raster allocation on the proximity-disabled default path; a double-counting edge case at
  distance 0, inert while off-by-default; a T092 sticky-flag edge case; the pre-existing
  uncommitted `docker-compose.yml` port change).

  **Amendment, 2026-09-12 — T095's owner sign-off received.** Judged on the geometric claim
  (+17.5% distance to bend and hug the footpath on `pervomayskoe`). `[proximity].enabled` flipped
  `false` -> `true` in `config/default.toml`. Five tests whose premise was "off by default" were
  updated to match. `tests/e2e/golden_route.json` regenerated a second time — `order`/`points`
  unchanged, `total_seconds` -7.6%. 500 passed, `ruff check .` clean.

  Two of the review's own waived Low items stopped being inert once the default flipped on: the
  "wasted full-raster allocation" is moot now; the "double-counting edge case at distance 0" (a
  linear-feature pixel gets both its own favourable `k_terrain` speed factor *and* the maximum
  possible `k_proximity` bonus) went from inert-while-off to live, and was filed as a follow-up
  design question for the owner/a future iteration rather than fixed in this session (not a
  reproduced-wrong-output bug — outside this session's actual task).
- [ ] 7 closed — blocked on one remaining manual owner sign-off (ADR-019 precedent): I3's own
  still-open T086 visual review (unaffected by I4, tracked separately). **Still open as of
  2026-09-16** — see `docs/STATUS.md`'s current `## Blocked on the owner`.

## Iteration I3: viewer UX, scale auto-detection exposure, control-number OCR (M10 implemented + reviewed; closure still blocked on the owner's own T086 review)

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
`master` — I2 was not yet merged, and T084/T087/T088 depend on I2's own T077/T078.

Progress (M10 in `docs/TASKS.md`, T083-T088):
- [x] 0 baseline recorded — `docker compose run --rm tests` 457 passed, exit 0; `ruff check .`
  clean; 2026-09-07, tree clean apart from the pre-existing unrelated `docker-compose.yml` change
  (see Baseline I2 above)
- [x] 1 delta intake agreed (in / out / deferred) — `docs/iterations/I3-viewer-ux-and-detection.md`
- [x] 2 impact map written — same file
- [x] 3 docs amended (SPEC F17/F21/Non-goals, DECISIONS ADR-021/022, TASKS M10 T083-T088)
- [x] GATE — approved by the owner 2026-09-07 («Утверждаю, продолжай»)
- [x] 4 implementation — **all six landed**: T083, T085, T087, T084 (commits `be8eccb`/ADR-023,
  `fec2e7c`, `cc03275`, `d40047f`+`0631783`), then T086 (`7b6f561`) and T088 (`5957120` +
  `14bbccb` follow-up fix). T083/T085/T087 landed with no `TASKS.md`/`STATUS.md` record at the
  time (found stale in later sessions, backfilled into `TASKS.md` from their commit diffs). **Two
  manual sign-offs from the owner remain open, both explicitly unautomatable by the DoD itself**:
  T086 ("owner reviews a live instance and confirms it reads as more concise/modern") and M9's T082
  (owner spot-checks 2-3 real scans, since done) — same precedent, ADR-019.
- [x] 5 verification green, baseline suites still green — **472 passed, exit 0, `ruff check .`
  clean** (2026-09-09, this session's own independent run, after the review fixes below)
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
- [ ] 7 closed — blocked on T086's visual review ("reads as more concise/modern"), the only
  remaining manual owner sign-off from this iteration (M9/T082's own spot-check is done). Neither
  is automatable (ADR-019 precedent). **Still open as of 2026-09-16** — see `docs/STATUS.md`'s
  current `## Blocked on the owner`.

## Iteration I1: real-scan vision robustness (closed, merged to `master`)

Owner found two real defects while manually trying the app on a real scan — separate from the three
already-tracked M7 blockers. Both fixed and merged to `master` as part of M8.

- **T073** (real-scan control false-positive suppression) — purple ink from hand-written control
  numbers and page borders was clearing the same ring-coverage floor a genuine control circle does;
  fixed with a combination of shape/size/context filters, all measured against the real scan rather
  than guessed.
- **T074** (grid-line/red-control real-scan regression) — a synthetic adversarial map (five true
  rings at 2.5x losing to a perfect-mean base-scale decoy) exposed a second false-positive mode
  around long straight ink runs (grid lines); fixed with a width cap plus (after review)
  `min_elongation_ratio = 10.0` as an image-size-relative second guard — the width cap alone stops
  discriminating on a small/cropped raster. Measured: all 8 known columns drop from 0.338-0.898 to
  0.000; zero pixels of the synthetic fixture change (its own IoU-floor test is unaffected).
- **T075** (`_CORE_COLOR` collision) — the route-overlay's core colour changed from red
  (`255,36,36`, which T073 turned into a colour the map can now legitimately print) to a pure
  magenta (`255,0,255`). Verified minimum CIELAB distance to all seven forbidden inks is ~48.3
  (nearest: purple), against `PaletteSettings.lab_distance_threshold`'s 35.0 bar. Review found
  magenta's OpenCV hue (150) sits inside the widened purple band (140-175) — the Lab-distance
  guarantee still holds, so this isn't a DoD failure, but the module docstring now states the
  guarantee precisely instead of implying hue uniqueness.
- **T076** (ADR-015) — `DetectorSettings.circle_scale_multipliers` (default
  `[1.0, 1.5, 2.0, 2.5, 3.0]`); `vision/controls.py::_detect_circles`/`_detect_hub_triangle` sweep
  the printed-size radius window through every configured multiplier. Landed in two rounds: round 1
  (`_select_best_scale`, mean ring-coverage per scale) reached recall 1.000 but precision only
  0.448 against pre-existing base-scale false positives; round 2 (from independent review) fixed a
  tie-break failure mode by scoring `(mean bucketed to _SCALE_TIE_EPS=0.02, candidate count)`
  instead of mean alone. Final: real-scan recall 1.000, precision 1.000, hub found at 2.73px error.
  Filed T077 (OCR crop sizing) rather than fixed in scope. 389 tests pass, `ruff check .` clean.

Also verified end to end (not just unit-level): `rogaine plan` with hand-built controls straddling
the real scan's grid column at x~535 (`--controls`, bypassing detection) solves and writes
`route.json`/`route.png` normally. The graph-wide measurement is the permanent regression test,
`TestGridInkOnRealScan::test_routable_graph_is_far_less_fragmented`: connected components drop
9463 -> 580, the giant component grows from 96.3% to 99.8% of all nodes.

### Baseline I1
Branch cut from `master` at commit `c2f2e1e` (2026-09-02), tree clean except the untracked test
scan (later moved to `data/maps/grid-lines-red-controls/`, itself gitignored). `docker compose run
--rm tests pytest -q` — **372 passed**, exit 0 (this pytest config prints no final summary line;
count taken from the dot tally, all dots, zero `F`/`E`).

## Checklist (original `orchestrate-product` Phase 0-7, superseded by `iterate-product`'s own per-iteration checklist since Iteration I2)

- [x] Phase 0 intake
- [x] Phase 1 elicit (DoR met)
- [x] Phase 2 SPEC.md
- [x] Phase 3 PLAN.md + TASKS.md
- [x] GATE user approved (2026-08-19, «утверждаю»)
- [ ] Phase 4 implementation — M0-M6 done (SPEC's full required scope); M7 optional/blocked (see
  the corpus items under "Blocked on the owner" history below)
- [x] Phase 5 tests green — 372 passed, 2026-09-02
- [x] Phase 6 review clean — `/review-product`, verdict PASS, 2026-09-02 (docs/REVIEW.md; two
  non-blocking follow-ups)
- [ ] Phase 7 handoff — README.md done (2026-09-05); still needs the owner accepting a route on
  their own map

## Test report history (superseded — current test report is in `docs/STATUS.md`)

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

## Blocked on the owner — historical detail (corpus arrival, harvest, a deleted file; all resolved/closed)

None of these blocked M1 — the synthetic fixture carried it. **2026-08-25: the map corpus
arrived** — 13 scans + 1 `.ocd` file, relocated from a root-level `maps/` drop into
`data/maps/<slug>/map.*` per the documented contract (ids transliterated from the owner's
filenames; see T005 in TASKS.md for the full list). `rogaine corpus list` read all 14.

**2026-09-02: ADR-010's "owner supplies 200+ scans" premise got a second source** — public
rogaine event maps scraped from o-gps-center.ru, cited (not committed; still gitignored
`data/maps/`, no `meta.toml`, same as the owner's 15). o-gps-center.ru's `robots.txt` disallows
crawling its `/viewer/?event_list...` search listing (only `/viewer/event/{id}/` itself is
`Allow`ed), so the harvester walked bare event IDs directly instead of that search — the whole
platform's event catalog (all sports, ~26,000 IDs total, not rogaine-specific), filtering titles
for «рогейн» client-side after fetch.

**2026-09-04: owner approved continuing the harvest, explicitly targeting ~200 maps for T070**
(M7's training corpus). ADR-014 flipped `proposed` -> `accepted` to record this. Run mechanism
changed from a Claude subagent to a plain background shell loop after two `Agent` tool calls
failed mid-task with an org-level API error that session (see the infrastructure note above).
`scratchpad/harvest_loop.sh` called `python data/maps/_ogps_harvest.py 540` in a loop and checked
the manifest/checkpoint itself; zero LLM tokens spent while it ran.

**2026-09-04, later same day: harvest finished, self-stopped clean.** Final line of
`_ogps_harvest_loop.log`: `STOP: target reached (205 rows)` — 204 data rows (maps). Verified
against the filesystem: 204 `data/maps/ogps-<id>/map.jpg` directories, each a real downloaded
JPEG. Plus the 15 owner scans = 219 maps total. T070's volume blocker (ADR-010/014) was cleared.
Its metadata blocker (no `meta.toml` on any of the 219, embedded JFIF `dpi` untrustworthy on
127/204) was resolved separately by T078's per-map auto-calibration (ADR-016).

**`crop_dense.png` is gone, deleted by accident, not by the owner.** It sat unexplained at repo
root (a small cropped fragment of a real map — olive rough-open terrain, blue-hatched marsh, a
purple control numbered 37) with a standing instruction not to touch it without asking. On
2026-08-29, while self-testing T050's `detect` command, the implementer subagent deleted it
alongside a stray `controls.csv` its own test run had written into the repo root by mistake — both
untracked, so `git` carries no copy of either. Checked immediately: not in the Windows Recycle Bin,
no accessible Volume Shadow Copy on this host. Unrecoverable from this machine; only the owner
having another copy of the source it was cropped from would restore it. Flagged to the owner the
same session.

## Notes (original elicitation, 2026-08-18/19, and early-project facts)

- Source of the idea: https://habr.com/ru/articles/1065342/ (rogaine route optimisation:
  SegFormer segmentation, VLM control detection, A* + Held-Karp).
- Owner decisions taken during elicitation (2026-08-18):
  - Success = route quality equal to or better than the article's; method is free.
  - Inputs on disk: map rasters (PNG/JPG/PDF/scan) plus a few `.ocd` files. On 2026-08-19 the owner
    offered 200+ scans and further help; roles and sizing settled in ADR-010, tasks T005/T006/T017.
  - Control detection: CV plus manual correction. No VLM (later narrowly revisited for OCR only —
    see ADR-039 in `docs/STATUS.md`'s current Iteration I7).
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
