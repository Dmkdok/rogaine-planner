# CLAUDE.md

<!-- product-factory:start -->
For greenfield sites/apps, use skill `orchestrate-product`.

- User-facing language: Russian
- Artifacts under `docs/`: English
- No application code until the user approves the plan (`утверждаю`)
- After approval: implement → test → review → handoff
- Prefer subagents: product-planner, architect, implementer, tester, reviewer

## This project

- Resuming work? `docs/STATUS.md` is the handoff — read it first, never summarise a previous chat.
  Trust the tree over the checkboxes in `docs/TASKS.md`, and run the suite before believing "green".
- Code intelligence: **Serena**. Activate by path (names collide on this machine). Explore with
  `get_symbols_overview` → `find_symbol`; edit with `replace_symbol_body` / `replace_content`.
  Whole-file `Read` on source is a last resort.
- Tests: `docker compose run --rm tests` (pytest hangs on the Windows host). In Bash never pipe a
  test run through `tail` — you get the pipe's exit code and a red suite reads as green. In
  PowerShell a cmdlet pipe leaves `$LASTEXITCODE` alone, so
  `... 2>&1 | Tee-Object $log | Select-Object -Last 30; $LASTEXITCODE` is safe there.
- Give subagents only their own SPEC/TASKS sections plus `docs/CONVENTIONS.md`, never the full docs.
- Docs carry only live work: `docs/TASKS.md` holds open milestones, `docs/DECISIONS.md` opens with an
  ADR index. Read one ADR or one milestone, never the whole file. History is in
  `docs/status-archive.md`, `docs/tasks-archive.md` and `docs/iterations/` — open it only when the
  history itself is the question.
- Fan-out searches ("where does X live?") go to the `Explore` subagent, so the file dumps stay out of
  the main thread.
- Report in `concise-mode`'s register by default: no preamble, no narration of what you are about to
  do — but every path, command, number and error message kept verbatim.
<!-- product-factory:end -->

## Git

- Commits and PR bodies carry no co-author or attribution trailer. The owner is the sole author of
  record; the history was rewritten once to strip it, so re-adding it would undo that on the next commit.
  Enforced by `attribution.commit` in `.claude/settings.json` — the older `includeCoAuthoredBy` key is
  deprecated, don't reintroduce it.

