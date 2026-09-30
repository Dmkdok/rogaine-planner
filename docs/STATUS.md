# Status

phase: implement
approved: true
approved_at: 2026-08-19
current: Iteration I7 (M14+M15) — **closed**, and its review follow-up **T117 landed** 2026-09-30
  (`8ecae40`, `reviewer` PASS). The OCR VLM fallback no longer reaches circle/scale detection, so
  `[ocr_fallback].provider="anthropic"` is no longer blocked. Suite: 588 passed, ruff clean.
  Three older, unrelated manual owner sign-offs remain open — see "Blocked on the owner".
  Full project history through Iteration I6 (M0-M13): `docs/status-archive.md`.

## Baseline I7
`docker compose run --rm tests` — **522 passed**, exit 0, 491.89s, 1 warning (pre-existing
`httpx`/`starlette` deprecation notice, unrelated); `ruff check .` clean. 2026-09-14, branch
`iteration/I2-vision-recognition-fix` @ `5f929c0`, tree clean.

## Resume here

**2026-09-30, T117 landed.** Branch `iteration/I2-vision-recognition-fix`, tree clean. T117 (the
I7 milestone review's H-1 + M-1 + M-2, owner-approved «Утверждаю» 2026-09-30) is implemented in
`8ecae40`: scale gates probe with the VLM fallback forced off, a successful VLM read no longer sets
a flag, VLM digit strings are validated client-side. `reviewer` **PASS**, two Low waived (see the
T117 entry in `docs/TASKS.md`). Iteration I7's remaining waived debt (two Medium, six Low) is
unchanged — see the review narrative below.

**Next concrete actions, in order:**
1. The three older owner sign-offs below are still open — pick them up if the owner responds.
2. No iteration is open. Deploy (I7 checklist step 8) was never decided as in-scope — ask the
   owner if/when it matters.
3. Known undiagnosed gap (from T116): the ink-isolation steps in `_ocr_crop` erase real printed
   numbers on 16 controls across `ogps-8620`/`kkm-toksovo`/`lembolovo-kkm` — candidate for a
   future task if the owner wants more numbers read.

No subagents or background commands are running.

## Iteration I7: real-map routing correctness (out-of-bounds/water/ЛЭП/olive) and an opt-in VLM OCR fallback (closed, M14+M15/T108-T116 landed and reviewed, branch `iteration/I2-vision-recognition-fix`)

Owner report, in-chat 2026-09-14, two screenshot crops from
`data/maps/ogps-8620_502cda4f6c774e8ecb86d063a71895f6`: a solved route crossing a magenta ISOM 709
out-of-bounds polygon and a lake; plus text reports of dark-green "fight" vegetation ("оливка")
crossed as merely slow, a power line (ЛЭП) costed as a normal path, and >=6 unread control numbers.
Full research, intake and impact map:
`docs/iterations/I7-real-map-routing-correctness-and-ocr-vlm-fallback.md`. New ADRs: ADR-036
(region-closure fill for hatched ISOM area symbols), ADR-037 (`veg_fight`/ISOM 410 reclassified
impassable by owner ruling), ADR-038 (out-of-bounds/water/ЛЭП items are diagnosis-first), ADR-039
(opt-in VLM OCR fallback, revisits ADR-009, narrows SPEC's "no network calls"/"no VLM" lines to an
opt-in, disabled-by-default, number-reading-only exception), ADR-040 (2026-09-16 addendum:
`[ocr_fallback]` gains a selectable local Ollama backend alongside Anthropic, additive). SPEC
F4/F5/F8/F10/Summary/Integrations/Non-goals/NFR-Security/Risks#4 extended in place; F23
added, then amended again by ADR-040 to describe the backend generically.

Split into two milestones at the owner's own choice: **M14** (map/routing correctness, T108-T112)
is smaller and fully deterministic/offline; **M15** (T113-T115) is the OCR architecture reversal.

Explicitly out of scope, recorded with reasons in the iteration doc: the reference article's
SegFormer segmentation network; VLM-based control *position*/circle detection (only number-reading
gets the fallback); attack points/vegetation fatigue/directional slope (already researched and
deferred by T094/ADR-027); lighter vegetation classes (406/408) alongside 410; a corpus-wide hunt
for further failures beyond `ogps-8620` this round.

Progress (M14+M15 in `docs/TASKS.md`, T108-T116):
- [x] 0 baseline recorded (see "Baseline I7" above)
- [x] 1 delta intake agreed — `docs/iterations/I7-real-map-routing-correctness-and-ocr-vlm-fallback.md`
- [x] 2 impact map written — same file
- [x] 3 docs amended (SPEC extended + F23 added; DECISIONS ADR-036..039; TASKS M14 T108-T112 + M15
  T113-T115)
- [x] GATE — approved by the owner 2026-09-15 («Утверждаю, продолжи»)
- [x] 4 implementation — **9/9 landed**: T108, T109, T110, T111, T112 (M14, complete), T113, T114,
  T116, T115 (M15, complete). See each task's own `docs/TASKS.md` entry for the full diagnosis/fix/
  measurement account. Full suite 560 passed, `ruff check .` clean, 2026-09-16 @ `c130129`.

**2026-09-16 addendum (ADR-040, T116, T115 rescoped):**
- [x] 1 delta intake agreed — iteration doc's own "Addendum" section
- [x] 2 impact map written — same section
- [x] 3 docs amended (SPEC F23/NFR-Security/Integrations amended; DECISIONS ADR-040; TASKS T116
  inserted, T115 deps/DoD widened)
- [x] GATE — approved by the owner 2026-09-16 («Утверждаю»)
- [x] 4 implementation — **9/9 landed**: T116 (local Ollama backend, `1208c2d`), T115 (real-scan
  measurement, found and drove the ADR-041 fix). Full suite 560 passed, `ruff check .` clean,
  2026-09-16 @ `c130129`.
- [x] 5 verification — same run, this session's own foreground result (see "Resume here" and
  "Test report")
- [x] 6 review — milestone-level `reviewer` pass over M14+M15 (T108-T116), 2026-09-17. **Verdict:
  PASS WITH WAIVERS.** Own live suite run: 560 passed, exit 0, 538.70s; own live `ruff check .`:
  clean. No Critical. Every T108-T116 DoD independently confirmed satisfied, including the two
  points scrutinised hardest: the ADR-041 blank-crop guard (`ocr.py:404-406`, sits once before
  dispatch to *either* backend, pinned by a parametrized regression test over both providers) and
  the T114 `trigger_confidence` fix (`ocr.py:476`, genuinely decoupled from `min_ocr_confidence`,
  pinned by its own regression test). One High: **H-1** — `controls.py`'s scale-selection gates
  (`_ocr_gate_sub_base_scale`/`_ocr_gate_tied_scales`) call the OCR fallback too, so with
  `[ocr_fallback].enabled=true` a VLM's answers can influence circle *position*/scale selection,
  against SPEC Non-goals, and fan out an unmeasured number of paid calls over known-junk candidate
  sets on `provider="anthropic"`; not reachable at the shipped `enabled=false` default. Filed as
  **T117** (`docs/TASKS.md`, M15) along with two Medium findings that share its fix site: **M-1** a
  successful VLM read is still reported as "unreadable" via the `flag` field (`ocr.py:478-481`,
  contradicts `read_control_number`'s own docstring); **M-2** the model's returned digit string
  isn't validated client-side before `int()` — Ollama's structured output doesn't reliably enforce
  the schema's `^[0-9]{1,3}$` pattern the way Anthropic's `strict: True` does
  (`ocr_vlm.py:172`, `ocr_vlm_ollama.py:65`, `ocr.py:422`). Waived, no task filed: **M-3** T109's
  out-of-bounds closure fix has only negative test coverage without the gitignored real-scan corpus
  present (the false-terrain-swallow direction is genuinely covered; the true-positive direction
  isn't, on a clean checkout); **M-4** `OcrFallbackSettings` has no dedicated config-level tests.
  Six Low, recorded not actioned: a stale "two guards" comment (`palette.py:216`, there are three
  now); a potentially expensive per-contour full-raster allocation on maps with heavy purple
  overprint (`palette.py:277-281`); `number_source` isn't cleared on a manual number edit
  (`web/app.py:499`, consistent with the existing `source` field's own behaviour, not a regression);
  no `.env`/`*.key` entry in `.gitignore`; SPEC F23's "byte-for-byte unchanged" wording slightly
  overclaims (a 9th CSV column is always added, harmlessly); a missing Tesseract binary triggers the
  fallback for an entire map. Full findings: this session's reviewer subagent transcript (not
  separately filed — T117 and this entry are the durable record).
- [x] 7 closed
- [ ] 8 deploy (optional, not yet decided — ask the owner if/when relevant)

Deferred, undiagnosed finding from T115 (not fixed, out of T115/T116's own scope): 16 controls
across `ogps-8620` (6), `kkm-toksovo` (7) and `lembolovo-kkm` (3) have a crop with *zero ink at all*
after `_ocr_crop`'s masking — the ink-isolation pipeline itself is erasing real printed numbers on
these specific real scans, before any VLM (of either backend) ever sees the crop. Needs its own
future task. Full context: `docs/TASKS.md` T115's own entry.

## History
Full project narrative through Iteration I6 (M0-M13), every closed iteration's own progress
checklist, the original Phase 0-7 checklist, old baselines/test-report entries, and early
elicitation notes: `docs/status-archive.md`. Read it only when the history itself is the question —
this file's own "Resume here" is authoritative for current state.

## Test report

`docker compose run --rm tests` — **588 passed**, exit 0, 580.23s, 1 warning (pre-existing
`httpx`/`starlette` deprecation notice, unrelated); `ruff check src tests` clean. 2026-09-30,
T117's working tree (committed unchanged as `8ecae40`) — run by the `implementer` subagent, not
re-run in the main thread; the `reviewer` independently ran the four touched test files (124
passed, exit 0) and ruff. Previous full run: 560 passed, 2026-09-17 @ `e26b9fb`.

Earlier entries (2026-08-19 through 2026-09-14): `docs/status-archive.md`.

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
  closer palette or fixture can. If a fixed palette proves brittle, fit it per map (cluster the
  map's own colours in Lab) rather than widening the threshold until `unknown` stops meaning
  anything.

## Blocked on the owner

Nothing here blocks Iteration I7's own remaining work items. T115's owner blocker (a real
`ANTHROPIC_API_KEY` + cost consent) was resolved 2026-09-16 by adding a local Ollama backend
instead (ADR-040, T116) — no longer listed here. Three items are open, all manual /
unautomatable (ADR-019 precedent — owner acceptance, not a measurable floor):

- **Iteration I6 closure** — the owner's own manual spot-check of `ogps-6802`/`ogps-7302`/
  `ogps-8078` plus two viewer UX flows (calibration tool active-state, manual add-control
  click-to-place). M13's own 7/7 tasks are landed and reviewed; this is the only remaining exit
  criterion.
- **Iteration I3/T086** — the owner reviewing a live instance of the viewer and confirming it reads
  as "more concise/modern". M10's own 6/6 tasks are landed and reviewed; this is the only remaining
  exit criterion.
- Two Medium items waived as documented follow-up debt during Iteration I4's own review (not
  reproduced bugs, design/UX questions for the owner or a future iteration): T093's export-JSON/PNG
  links keep pointing at the primary route after switching to an alternative, with no indication;
  T093's route-switcher rerender drops keyboard focus to `<body>` on every click. Full context:
  `docs/status-archive.md`'s Iteration I4 entry.

Historical corpus-arrival/harvest/deleted-file detail (all resolved): `docs/status-archive.md`.

## Notes

- 2026-09-17: I7's milestone review (T117/H-1) found that `config.ocr_fallback` propagates
  unconditionally to every `read_control_numbers` caller, including `controls.py`'s scale-selection
  probes — which exist purely to pick a scale/candidate-set from Tesseract's own read-count signal,
  not to read numbers for real. Any future code path that calls into OCR machinery for a
  detection/scoring purpose (not the final read) needs to force `ocr_fallback.enabled=False` on its
  own probe config explicitly — the fallback being "opt-in, disabled by default" at the top level
  does not stop it from firing inside an internal probe once the owner has opted in for real reads.
- 2026-09-16: a subagent dispatched to implement a task, told explicitly (in its own prompt) to run
  the full test suite inline and wait for it, instead backgrounded `docker compose run --rm tests`
  and ended its own turn before the result came back — then kept re-notifying in a loop ("waiting
  for the suite to finish") without ever producing a real result, burning ~200k tokens across
  repeated stop/re-notify cycles before it was stopped with `TaskStop`. This is the third time this
  exact pattern has hit this project (see `docs/status-archive.md`'s "Old Resume here snapshots"
  for the first two, 2026-09-15). If a subagent's own prompt explicitly says "run inline, wait for
  it" and it still backgrounds the run, do not wait on repeated "still waiting" notifications from
  it — check `ListAgents`/the task's real status, and if it is looping, `TaskStop` it and finish the
  remaining work (verification, docs) directly rather than re-dispatching.
- Serena project `map-planer` is created and activated at `E:\Dev\_AI_\map-planer`.
