# Review

Scope: M6 (T060 FastAPI backend, T061 canvas viewer UI, T062 Playwright e2e — SPEC F17), the
milestone STATUS.md/TASKS.md claim closes SPEC's whole M0-M6 scope. Re-verified independently:
own read of `src/rogaine/web/app.py` in full, all of `src/rogaine/web/static/**`,
`tests/unit/web/test_app.py`, `tests/e2e/test_viewer.py`, the `Dockerfile`/`docker-compose.yml`
diffs; own `docker compose run --rm tests` (372 passed, exit 0, run twice); own
`docker compose run --rm tests pytest tests/e2e/ -v` (3 passed, exit 0, isolated); own
`docker compose run --rm tests ruff check .` (clean, exit 0); own `git status` (clean tree, no
stray files); own live click-through of the built image in a real Chrome browser at 1400x900
(clean render, no lorem/broken layout).

## Verdict
PASS

M6's own deliverables (T060-T062, F17) are complete, correct, tested, and independently
reproduced. One pre-existing, SPEC-level gap (missing README) is flagged below — it is Phase 7's
deliverable, not a T060-T062 defect, but is called out now so it isn't silently skipped.

## Critical
None.

## High
- **No root README yet, though SPEC.md's own "Launch checklist" and PLAN.md's "Definition of
  Done" both require one** ("README covers install, run, config reference, JSON schema, and known
  limitations" / "...documents install, every CLI command, the config reference, the route JSON
  schema, and the known limitations"). Repo root has no `README.md` at all — confirmed by listing
  (`data/README.md` exists, covering only the map-corpus contract; nothing covers install/run/CLI
  reference/config/JSON schema at the project level). Not a T060-T062 regression — STATUS.md's own
  checklist correctly leaves Phase 7 ("handoff") unchecked, and `templates/product-factory/
  HANDOFF.template.md` is presumably where this lands. Flagging now, before Phase 7, so the
  Launch checklist item isn't skipped: this blocks calling the product handoff-ready per SPEC's
  own acceptance bar, independent of M6's code quality.

## Medium / polish
- ~~**S-001 (security, Medium)**~~ — **fixed 2026-09-05, ADR-017** (see docs/STATUS.md's "Resume
  here" and its 2026-09-05 Notes entry for the concrete diff and the one test regression it caught
  and fixed). Left below verbatim as the record of what was found.
- **S-001 (security, Medium)** — `SegmentRequest.dpi` (`src/rogaine/web/app.py:113`) and
  `RunConfig.heuristic_time_budget_s`/`time_limit_s`/`alternatives` (`src/rogaine/models.py:122-
  129`) validate a lower bound only (`gt=0`/`ge=0`), no upper bound. Verified directly: an extreme
  `dpi` on a PDF drives `pdfium.render(scale=dpi/72)` (`src/rogaine/io/raster.py:83`) toward an
  arbitrarily large bitmap allocation *before* `load_raster`'s `MAX_DECODED_PIXELS` cap ever runs
  (that check is post-decode, line 57-58) — the resulting `MemoryError` is not `ValueError`/
  `OSError`, so `_segment_worker`'s `except (ValueError, OSError)` doesn't catch it and the job
  hangs at `status: "running"` forever instead of erroring. Bounded today by the loopback-only
  default (`serve_cmd`'s `--host 127.0.0.1` default, `docker-compose.yml`'s `127.0.0.1:8000:8000`
  publish), but nothing in code stops `--host 0.0.0.0`, and even a same-host typo can wedge the
  server. Fix: add `le=` upper bounds (dpi in the low thousands, time budgets in sane minutes,
  `alternatives` capped at config's own ceiling), and widen the three worker `except` clauses (or
  wrap in a broad `except Exception` that still records `status="error"`) so an unexpected failure
  surfaces to the client instead of leaving a job stuck forever.
- **S-002 (security, Low)** — `pyproject.toml` pins floors only (`numpy>=2.1`, `fastapi>=0.115`,
  …), no lockfile — a rebuild can silently pull a newer transitive dependency with nothing pinned
  to audit against. Generate and commit a lockfile (`pip-compile`/`uv lock`), install from it in
  the `Dockerfile`.
- **S-003 (security, Low/info)** — `rogaine serve --host` accepts `0.0.0.0` with only a help-text
  warning ("never 0.0.0.0"), no code-level guard (`src/rogaine/cli.py:578-586`). No auth on any
  endpoint if that flag is ever used. Consider requiring an explicit opt-in flag before accepting a
  non-loopback bind.
- **S-004 (security, Low/info)** — no CSP on the static viewer. Low impact today (confirmed:
  same-origin only, `textContent`/`createElement` everywhere in `app.js`, no `innerHTML` fed
  untrusted data — the only `innerHTML = ""` calls are clears), but cheap defense-in-depth against
  a future regression.
- `web-design-guidelines` (the skill review-product's own checklist names for the UI pass) is not
  installed in this session's skill set, so it could not be run as instructed. Substituted a manual
  pass instead (see below) — worth running the real skill when it's available.
- A stray `.claude/worktrees/t061-viewer-ui/` git worktree remains from T061's implementer run
  (already flagged in STATUS.md as harmless/untracked). Not re-flagged as new; `git worktree
  remove` whenever convenient.

## What was verified clean
- **Tests**: `docker compose run --rm tests` — 372 passed, exit 0, reproduced twice (129s, 128s).
  `pytest tests/e2e/` in isolation — 3 passed, exit 0, 12s (includes the new
  `test_viewer.py::TestFullViewerFlow`, a real headless-Chromium run of the full upload -> calibrate
  -> auto-detect -> edit-a-control -> plan -> export flow). `ruff check .` — clean, exit 0.
- **Security** (full manual checklist, semgrep unavailable — see Medium/polish above for the four
  low/medium findings): upload handling sniffs magic bytes only (PNG/JPEG/BMP/TIFF/PDF), never
  client filename/Content-Type; 200 MB cap enforced mid-stream; server-generated `uuid4().hex` run
  id and `map.<ext>` name, client filename never touches a path. Every `run_id` validated as a real
  UUID before any filesystem join (`_require_run`); `export_artifact`'s `artifact` param is a fixed
  allowlist (`_EXPORTS`), not string-interpolated — no path traversal/IDOR in either. `Control`
  fields are all pydantic-typed through the CSV round-trip — no CSV-injection surface. No
  `subprocess`/`shell=True`/`eval`/`pickle.load` anywhere in `src/`. `serve_cmd` defaults to
  `127.0.0.1`; `docker-compose.yml` publishes only `127.0.0.1:8000:8000` (container binds
  `0.0.0.0` internally, which is the only address Docker's own port-forwarding can reach — the host
  boundary is what matters, and it's loopback-only). `solve_exact`'s `2**N` blowup is already
  guarded by `exact_max_controls`.
- **Correctness**: happy paths (upload -> segment -> detect -> edit -> plan -> export) exercised by
  both the unit `TestClient` suite and the real-browser Playwright test, both independently
  re-run and green. Error/empty states present and tested: bad magic bytes (400), oversized upload
  (413), unknown run/job id (404 everywhere, including the static-mount ordering regression guard),
  export before plan (404), detect before segment (400), no-hub-found (job still succeeds, surfaces
  a UI warning rather than failing silently), PUT-controls validation (invalid edit 400s without
  touching the live `controls.csv`), "no reachable route" (distinct error, not a crash).
- **UX/UI** (manual pass, `web-design-guidelines` skill unavailable this session — see Medium/
  polish): `index.html` has a skip-link, `role="status"`/`role="alert"` live regions, ARIA labels
  on every icon-only control, visually-hidden captions/legends, Russian UI strings throughout,
  keyboard-operable canvas viewport (arrow-key pan, +/-/0 zoom, Enter to place in add/calibrate
  mode) plus a fully keyboard-parity controls table (every marker action — drag, arrow-nudge,
  delete, add — has a table equivalent). `style.css` defines light/dark via
  `prefers-color-scheme` on the same custom properties, a `:focus-visible` outline, and a
  `.visually-hidden` helper. Live screenshot at 1400x900 (build's own `docker compose run` image,
  a real Chrome tab) confirmed clean rendering — no overlapping elements, no lorem/placeholder
  text, no broken links. A narrower-viewport screenshot did not visibly reflow (likely a
  window-resize/DPI quirk in the browser-automation tool, not re-investigated further) — the
  `@media (max-width: 900px)` single-column rule is present and correct in `style.css`, but the
  actual reflow was not visually confirmed; low priority for a local desktop planning tool.
  Functional, utilitarian design matches the brief (a competitor's planning tool, not a marketing
  page) rather than reading as a generic template.
- **Engineering**: structure matches PLAN.md (`src/rogaine/web/app.py`,
  `src/rogaine/web/static/**`). Diffs match TASKS.md's own accounting; every deviation outside a
  task's literal path list (T060's `test_cli.py`/`docker-compose.yml`, T061's two `app.py`
  additions, T062's `Dockerfile` line) is pre-flagged in TASKS.md with a concrete reason, and each
  was spot-checked against the actual diff rather than taken on the landing note's word — all
  judged correct, not scope creep. No dead code, no `TODO`/`FIXME`/`console.log`/`debugger` left in
  `src/rogaine/web/`. Test commands documented and reproducible
  (`docker compose run --rm tests`, per CLAUDE.md).

## Waivers (must cite DECISIONS.md)
None claimed. ADR-005 (vanilla JS + Canvas viewer) predates and is correctly followed by T061; no
new waiver was needed or invoked for M6.
