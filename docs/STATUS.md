# Status

phase: implement
approved: true
approved_at: 2026-08-19
current: Iteration I7 (M14+M15) — M14 complete (T108-T112), M15's automatable half complete
  (T113/T114); only T115 (real-API-key measurement) remains, blocked on the owner. Three older,
  unrelated manual owner sign-offs also remain open (none block I7) — see "Blocked on the owner".
  Full project history through Iteration I6 (M0-M13): `docs/status-archive.md`.

## Baseline I7
`docker compose run --rm tests` — **522 passed**, exit 0, 491.89s, 1 warning (pre-existing
`httpx`/`starlette` deprecation notice, unrelated); `ruff check .` clean. 2026-09-14, branch
`iteration/I2-vision-recognition-fix` @ `5f929c0`, tree clean.

## Resume here

**2026-09-16: M14 and M15's automatable half both closed out this session.** Branch
`iteration/I2-vision-recognition-fix`, tree clean, 78 commits ahead of `master` / 0 behind. Full
suite **545 passed**, `ruff check .` clean — this session's own foreground run (`docker compose run
--rm tests`, not piped through `tail`), commit `5f43df6`.

**T110** (`1b6bc26`) — lake crossing on `ogps-8620` shares `_consolidate_banked_water`'s territory
(T101), not T109's region-closure mechanism: retuned `min_bank_fraction` 0.3→0.23 plus a new
`min_component_area_px=500` guard, verified against all four real scans the function touches.
`veg_fight` (ISOM 410) reclassified impassable per ADR-037 (owner ruling). Full account:
`docs/TASKS.md` T110's own entry.

**T114** (`5f43df6`) — wired T113's VLM OCR fallback behind `[ocr_fallback]`
(`enabled=false` shipped). **Caught and fixed a real bug in review before committing**: the
first-pass wiring gated the fallback on Tesseract's own `min_ocr_confidence` flag in addition to
`trigger_confidence`, which silently no-ops the fallback whenever an operator configures
`trigger_confidence` above `min_ocr_confidence` — exactly the case that setting exists to enable.
Fixed (dropped the extra gate) with a new regression test pinning it. Full account: `docs/TASKS.md`
T114's own entry.

**Both landing sessions hit the same background-test-run failure mode flagged at the 2026-09-15
pause** (a dispatched subagent backgrounds `docker compose run --rm tests` and ends its own turn
before the result lands) — T110's implementer avoided it, T114's implementer repeated it and had
to be stopped (`TaskStop`) mid-loop; its remaining work (the bug above, the final verification,
docs) was finished directly in this session instead of re-dispatched. Third occurrence of this
exact pattern across three sessions — worth a standing rule in `CLAUDE.md` if a fourth happens.

**Next concrete actions, in order:**
1. **T115** (M15 close-out) is blocked on the owner: needs a real `ANTHROPIC_API_KEY` and explicit
   consent to real API cost against `ogps-8620` and a broader corpus sample — not something a
   session can do unsupervised (no key configured in this environment as of 2026-09-16). Ask the
   owner for the key/budget before attempting it.
2. M14 (T108-T112) is fully landed and could get its own milestone-level `reviewer` pass now,
   independent of T115 — same pattern as every prior iteration's own step 6 (see
   `docs/status-archive.md`'s Iteration I3-I6 entries). Not yet run.
3. Three older, unrelated manual owner sign-offs remain open in parallel, none blocking I7 (see
   "Blocked on the owner" below) — no session action, just don't forget them when the owner is next
   asked for input.

Iteration I7's own live progress checklist is below, under "Iteration I7".

## Iteration I7: real-map routing correctness (out-of-bounds/water/ЛЭП/olive) and an opt-in VLM OCR fallback (M14 complete, M15 7/8 landed, branch `iteration/I2-vision-recognition-fix`)

Owner report, in-chat 2026-09-14, two screenshot crops from
`data/maps/ogps-8620_502cda4f6c774e8ecb86d063a71895f6`: a solved route crossing a magenta ISOM 709
out-of-bounds polygon and a lake; plus text reports of dark-green "fight" vegetation ("оливка")
crossed as merely slow, a power line (ЛЭП) costed as a normal path, and >=6 unread control numbers.
Full research, intake and impact map:
`docs/iterations/I7-real-map-routing-correctness-and-ocr-vlm-fallback.md`. New ADRs: ADR-036
(region-closure fill for hatched ISOM area symbols), ADR-037 (`veg_fight`/ISOM 410 reclassified
impassable by owner ruling), ADR-038 (out-of-bounds/water/ЛЭП items are diagnosis-first), ADR-039
(opt-in VLM OCR fallback, revisits ADR-009, narrows SPEC's "no network calls"/"no VLM" lines to an
opt-in, disabled-by-default, number-reading-only exception). SPEC
F4/F5/F8/F10/Summary/Integrations/Non-goals/NFR-Security/Risks#4 extended in place; F23 added.

Split into two milestones at the owner's own choice: **M14** (map/routing correctness, T108-T112)
is smaller and fully deterministic/offline; **M15** (T113-T115) is the OCR architecture reversal.

Explicitly out of scope, recorded with reasons in the iteration doc: the reference article's
SegFormer segmentation network; VLM-based control *position*/circle detection (only number-reading
gets the fallback); attack points/vegetation fatigue/directional slope (already researched and
deferred by T094/ADR-027); lighter vegetation classes (406/408) alongside 410; a corpus-wide hunt
for further failures beyond `ogps-8620` this round.

Progress (M14+M15 in `docs/TASKS.md`, T108-T115):
- [x] 0 baseline recorded (see "Baseline I7" above)
- [x] 1 delta intake agreed — `docs/iterations/I7-real-map-routing-correctness-and-ocr-vlm-fallback.md`
- [x] 2 impact map written — same file
- [x] 3 docs amended (SPEC extended + F23 added; DECISIONS ADR-036..039; TASKS M14 T108-T112 + M15
  T113-T115)
- [x] GATE — approved by the owner 2026-09-15 («Утверждаю, продолжи»)
- [ ] 4 implementation — **7/8 landed**: T108, T109, T110, T111, T112 (M14, complete), T113, T114
  (M15). See each task's own `docs/TASKS.md` entry for the full diagnosis/fix/measurement account.
  Full suite 545 passed, `ruff check .` clean, 2026-09-16. **Remaining: T115** (M15, blocked on the
  owner — real API key + cost consent, see "Resume here" above).
- [ ] 5 verification
- [ ] 6 review
- [ ] 7 closed
- [ ] 8 deploy (optional, not yet decided)

## History
Full project narrative through Iteration I6 (M0-M13), every closed iteration's own progress
checklist, the original Phase 0-7 checklist, old baselines/test-report entries, and early
elicitation notes: `docs/status-archive.md`. Read it only when the history itself is the question —
this file's own "Resume here" is authoritative for current state.

## Test report

`docker compose run --rm tests` — **545 passed**, exit 0 (539 baseline + 6 new `TestVlmFallback`
tests), 614.03s, 1 warning (pre-existing `httpx`/`starlette` deprecation, unrelated); `ruff check .`
clean. 2026-09-16, branch `iteration/I2-vision-recognition-fix` @ `5f43df6`, tree clean — this
session's own foreground run, not piped through `tail`/trusted from a subagent's report.

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

Nothing here blocks Iteration I7's own remaining work items. Four items are open, all manual /
unautomatable (ADR-019 precedent — owner acceptance, not a measurable floor):

- **T115** (Iteration I7/M15) — needs a real `ANTHROPIC_API_KEY` and explicit consent to real API
  cost before running the VLM OCR fallback against `ogps-8620` and a broader corpus sample. No key
  is configured in this environment as of 2026-09-16.
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
