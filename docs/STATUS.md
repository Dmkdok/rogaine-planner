# Status

phase: implement
approved: true
approved_at: 2026-08-19
current: M0 — T001 scaffold, T002 contract, T003 config, T004 synthetic fixture

## Checklist
- [x] Phase 0 intake
- [x] Phase 1 elicit (DoR met)
- [x] Phase 2 SPEC.md
- [x] Phase 3 PLAN.md + TASKS.md
- [x] GATE user approved (2026-08-19, «утверждаю»)
- [ ] Phase 4 implementation
- [ ] Phase 5 tests green
- [ ] Phase 6 review clean (or accepted waivers)
- [ ] Phase 7 handoff

## Test report
- No suite yet; T001 creates it.

## Notes
- Source of the idea: https://habr.com/ru/articles/1065342/ (rogaine route optimisation:
  SegFormer segmentation, VLM control detection, A* + Held-Karp).
- Owner decisions taken during elicitation (2026-08-18):
  - Success = route quality equal to or better than the article's; method is free.
  - Inputs on disk: map rasters (PNG/JPG/PDF/scan) plus a few `.ocd` files. On 2026-08-19 the owner
    offered 200+ scans and further help; roles and sizing settled in ADR-010, tasks T005/T006/T017.
    **Paths still not supplied — see BRIEF.md open questions.**
  - Control detection: CV plus manual correction. No VLM.
  - Delivery: CLI plus a local web viewer.
  - Scale: 30-80 controls, heuristic solver acceptable, exact solver kept as the oracle.
  - Map scale: manual entry plus calibration line.
  - Movement model: base speed x terrain coefficient + contour-based slope penalty.
  - Rules: start = finish, points penalty per minute late.
  - Georeferencing/GPX: out of scope.
  - Acceptance: solver self-check (heuristic vs exact gap) plus the owner's own judgement.
- Environment probed: Windows 11, Python 3.14.3 host, Docker 29.3.1 / Compose v5.1.1,
  NVIDIA RTX 3060 Ti 8 GB, git 2.55.0. Project is **not** a git repository yet.
- Serena project `map-planer` created and activated at `E:\Dev\_AI_\map-planer`; onboarding not run
  (no source code yet).
- Next action after approval: M0 tasks T001-T004, then three parallel workstreams (WS-A vision,
  WS-B routing, WS-C delivery) per PLAN.md.
