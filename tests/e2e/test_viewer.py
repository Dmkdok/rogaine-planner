"""T062's browser end-to-end guard for the web viewer (F17, T060/T061).

SPEC F17's acceptance bar (verbatim): "A Playwright script completes the full flow on the fixture
map with no manual steps." PLAN.md's test-strategy line: "Playwright drives the viewer's full flow
(upload, calibrate, edit a control, run, export)." This module is that script.

Unlike `tests/unit/web/test_app.py`, which drives `rogaine.web.app:app` in-process via
`TestClient`, Playwright needs a real browser talking real HTTP to a real server -- `TestClient`
does not expose a URL a browser can navigate to. `_live_server` below binds an ephemeral
`127.0.0.1` port, runs `uvicorn.Server` in a background thread, and polls `GET /` until it answers
before handing the test a base URL; teardown sets `should_exit` and joins the thread. `RUNS_ROOT`
is monkeypatched to a per-test `tmp_path` first (same isolation `test_app.py` uses), so nothing
here ever touches the real project's `runs/`.

The fixture map is `tests/conftest.py`'s session-scoped `synthetic_map` (1:30000, 300 dpi,
1600x1200, the default small preset -- not `full_size_synthetic_map`, reserved for
`tests/perf/test_budgets.py`). It is not a coincidence this is the same fixture
`tests/unit/web/test_app.py::TestFullFlow` already proves finds a hub and >=1 control via the real
CV detector: T061's own landing note in `docs/TASKS.md` records a live manual run against this
exact map finding "13 controls including the hub" -- reusing it here means detection succeeding
is already established, not something this test is gambling on.

"Move one control" is done through the controls table's `#control-{id}-x`/`-y` inputs, not a
canvas pointer-drag: T061's landing note explains the marker `<button>` elements exist precisely so
keyboard/table editing has full parity with dragging, and the table path is far more robust to
drive from a test than simulating pointer/canvas drag maths. The edit dispatches a real `change`
event (what a blur/Enter would fire in a live browser) so `saveControlsNow()` runs immediately
(no debounce, unlike the marker-drag/keyboard-nudge paths) -- the test then explicitly waits for
that `PUT .../controls` response before clicking run, so there is no race against a plan that
would otherwise run against the pre-edit controls.

Scale is applied via the ratio+DPI fields (`#scale-denominator`/`#scale-dpi`), using the fixture's
own `scale_denominator`/`dpi` -- SPEC F3's other calibration path (a drawn/typed line) is exercised
by nothing here; ratio+DPI is simpler to drive and this task only needs *a* correct calibration.
The run form posts only `base_speed_mps`/`time_limit_s`/`penalty_per_min` (see `app.js`'s
`initRunForm`); `RunConfig`'s own defaults (`strategy="auto"`, `alternatives=3`, `seed=0`) apply,
exactly as a real user's click would produce. At the fixture's control count `exact_max_controls`
(`config/default.toml`, 15) keeps "auto" on the deterministic Held-Karp path, not the RNG-driven
heuristic, so this test carries no seed-flakiness risk of its own.
"""

from __future__ import annotations

import json
import re
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import cv2
import httpx
import numpy as np
import pytest
import uvicorn
from playwright.sync_api import Page, expect

import rogaine.web.app as web_app
from rogaine.models import Leg, Route
from rogaine.solve.alternatives import AlternativesResult
from rogaine.vision.calibrate import CalibrationResult

pytestmark = pytest.mark.e2e

#: Generous budgets for the two real background-thread stages this test waits on -- segmentation
#: plus auto-detect (chained: `onSegmentDone` kicks off `runDetect` itself) is the slower of the
#: two, planning is fast at this fixture's control count (see module docstring). Both comfortably
#: clear `tests/unit/web/test_app.py::_wait_for_job`'s own 30s budget for a single stage.
_SEGMENT_AND_DETECT_TIMEOUT_MS = 60_000
_PLAN_TIMEOUT_MS = 45_000


def _write_png(path: Path, image_rgb: np.ndarray) -> None:
    """Write an RGB array to *path* as a PNG (cv2 wants BGR) -- matches `tests/e2e/test_cli.py`'s
    and `tests/unit/web/test_app.py`'s own helper of the same name/pattern."""
    ok, buf = cv2.imencode(".png", image_rgb[:, :, ::-1])
    assert ok
    path.write_bytes(buf.tobytes())


@pytest.fixture()
def _live_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Start the real FastAPI app on a free `127.0.0.1` port for Playwright to drive.

    Function-scoped: this module has one test, so there is no benefit to the extra bookkeeping a
    module-scoped server (manual `RUNS_ROOT` save/restore instead of the plain `monkeypatch`
    fixture) would need.
    """
    monkeypatch.setattr(web_app, "RUNS_ROOT", tmp_path / "runs")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()  # small TOCTOU race accepted -- test-only local server (T062 brief)

    config = uvicorn.Config(web_app.app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 10.0
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(base_url + "/", timeout=1.0)
            if resp.status_code == 200:
                break
        except httpx.TransportError as exc:
            last_error = exc
        time.sleep(0.05)
    else:
        raise RuntimeError(f"live server did not come up in time: {last_error}")

    yield base_url

    server.should_exit = True
    thread.join(timeout=5.0)


class TestFullViewerFlow:
    def test_upload_calibrate_move_control_run_export(
        self, _live_server: str, page: Page, synthetic_map, tmp_path: Path
    ) -> None:
        sm = synthetic_map
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)
        width = sm.shape[1]

        page.goto(_live_server + "/")

        # --- 1. Upload -------------------------------------------------------------------
        page.set_input_files("#map-file-input", str(map_path))
        page.click("#upload-btn")
        expect(page.locator("#run-id-display")).to_be_visible()
        expect(page.locator("#scale-fieldset")).to_be_enabled()

        # --- 2. Calibrate (ratio + DPI mode, the default-checked radio) ------------------
        page.fill("#scale-denominator", str(sm.scale_denominator))
        page.fill("#scale-dpi", str(sm.dpi))
        page.click("#apply-scale-btn")

        # Segment, then auto-detect (app.js chains them -- see module docstring), land the
        # controls table. Waiting on rows existing is a stronger gate than any status-text
        # match: it can only pass once both background jobs are actually done.
        page.wait_for_selector(
            "#controls-tbody tr", state="attached", timeout=_SEGMENT_AND_DETECT_TIMEOUT_MS
        )
        expect(page.locator("#hub-warning")).to_be_hidden()

        # --- 3. Move one (non-hub) control via the table X/Y inputs ----------------------
        control_id = page.evaluate(
            """() => {
                for (const row of document.querySelectorAll('#controls-tbody tr')) {
                    const radio = row.querySelector('input[type=radio]');
                    if (radio && !radio.checked) return row.id.replace('control-row-', '');
                }
                return null;
            }"""
        )
        assert control_id is not None, "expected at least one detected non-hub control"

        x_selector = f"#control-{control_id}-x"
        current_x = float(page.input_value(x_selector))
        # Shift towards the map's centre by a fixed 40px -- controls are placed with a comfortable
        # margin from every edge (`_place_controls`, tests/fixtures/synth_map.py), so this never
        # needs the clamp below in practice; the clamp is defensive, not load-bearing.
        delta = 40.0 if current_x < width / 2 else -40.0
        new_x = min(max(current_x + delta, 5.0), width - 5.0)

        with page.expect_response(
            lambda r: r.request.method == "PUT" and r.url.endswith("/controls")
        ) as resp_info:
            # Set the value and dispatch a real `change` event directly -- what a blur/Enter
            # would fire in a live browser -- rather than relying on Playwright's `fill()` event
            # semantics, which are not guaranteed to include `change` for a script-set value.
            page.evaluate(
                """([sel, val]) => {
                    const el = document.querySelector(sel);
                    el.value = val;
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }""",
                [x_selector, str(new_x)],
            )
        put_response = resp_info.value
        assert put_response.status == 200, put_response.text()

        updated_x = float(page.input_value(x_selector))
        assert abs(updated_x - current_x) > 1.0, "control x did not change after the table edit"

        # --- 4. Run ------------------------------------------------------------------------
        page.click("#run-btn")  # auto-waits for enabled (hub present, segment ready)
        page.wait_for_selector(
            "#legs-tbody tr", state="attached", timeout=_PLAN_TIMEOUT_MS
        )
        expect(page.locator("#route-results")).to_be_visible()

        # --- Assert the leg table -----------------------------------------------------------
        leg_rows = page.locator("#legs-tbody tr")
        n_legs = leg_rows.count()
        assert n_legs >= 1
        for i in range(n_legs):
            expect(leg_rows.nth(i)).to_have_attribute("id", f"leg-row-{i}")
        # A rogaine route starts at the hub (SPEC F14) -- the first leg's "From" cell says so.
        expect(leg_rows.nth(0).locator("td").nth(1)).to_have_text("Хаб")  # noqa: RUF001 -- Russian UI copy under test, not a look-alike typo

        # --- Assert the exported JSON --------------------------------------------------------
        export_href = page.eval_on_selector("#export-json-link", "el => el.href")
        assert "export/route.json" in export_href
        export_response = page.request.get(export_href)
        assert export_response.ok, export_response.text()
        route_json = export_response.json()

        for key in (
            "schema_version",
            "order",
            "legs",
            "total_seconds",
            "total_meters",
            "points",
            "penalty",
            "score",
            "solver",
            "optimal",
            "seed",
            "run_config",
        ):
            assert key in route_json, f"route.json missing {key!r}"
        assert len(route_json["order"]) >= 2
        assert route_json["order"][0] == route_json["order"][-1]
        assert len(route_json["legs"]) == len(route_json["order"]) - 1
        assert route_json["total_seconds"] > 0
        assert route_json["total_meters"] > 0


class TestViewerLayout:
    """T085 (F17, ADR-021): the map viewport and the controls panel are both inside the browser
    viewport at once -- nothing has to be scrolled out of view to reach the other -- and
    selecting a marker/table row cross-highlights the other. New behaviour, no prior coverage;
    reuses `TestFullViewerFlow`'s own upload/calibrate/detect setup rather than duplicating the
    slow segmentation+detect pipeline in a second test.
    """

    def test_map_and_controls_visible_together_with_highlight_sync(
        self, _live_server: str, page: Page, synthetic_map, tmp_path: Path
    ) -> None:
        sm = synthetic_map
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)

        # ADR-021's own bug report scenario: a standard desktop viewport.
        page.set_viewport_size({"width": 1366, "height": 768})
        page.goto(_live_server + "/")

        page.set_input_files("#map-file-input", str(map_path))
        page.click("#upload-btn")
        expect(page.locator("#scale-fieldset")).to_be_enabled()

        page.fill("#scale-denominator", str(sm.scale_denominator))
        page.fill("#scale-dpi", str(sm.dpi))
        page.click("#apply-scale-btn")

        page.wait_for_selector(
            "#controls-tbody tr", state="attached", timeout=_SEGMENT_AND_DETECT_TIMEOUT_MS
        )

        # --- Select the first row: bring the *whole table* into view (not just the one row --
        # scrolling only the row can leave the table's later rows, and so its full bounding box,
        # below the fold) and click it -----------------------------------------------------------
        rows = page.locator("#controls-tbody tr")
        first_row = rows.first
        page.locator("#controls-table").scroll_into_view_if_needed()
        first_row.locator("td").first.click()

        first_id = (first_row.get_attribute("id") or "").removeprefix("control-row-")
        assert first_id

        # --- Both the map and the (now-visible) controls table fit the browser viewport at
        # once, with no scroll of either needed to reach the other -- F17/ADR-021's core bar. ---
        expect(page.locator("#map-viewport")).to_be_in_viewport(ratio=1)
        expect(page.locator("#controls-table")).to_be_in_viewport(ratio=1)

        # --- Selecting a row highlights its marker (new behaviour, T085) -----------------------
        expect(first_row).to_have_class(re.compile(r"\brow-selected\b"))
        first_marker = page.locator(f"#marker-{first_id}")
        expect(first_marker).to_have_class(re.compile(r"\bmarker--selected\b"))

        # --- ...and vice versa: clicking a different marker moves the highlight to its row -----
        second_row = rows.nth(1)
        second_id = (second_row.get_attribute("id") or "").removeprefix("control-row-")
        assert second_id and second_id != first_id
        second_marker = page.locator(f"#marker-{second_id}")
        second_marker.click()

        expect(second_marker).to_have_class(re.compile(r"\bmarker--selected\b"))
        expect(second_row).to_have_class(re.compile(r"\brow-selected\b"))
        expect(first_marker).not_to_have_class(re.compile(r"\bmarker--selected\b"))
        expect(first_row).not_to_have_class(re.compile(r"\brow-selected\b"))


class TestAutoScale:
    """T088 (F21, ADR-022): the Scale panel's third action, "Определить автоматически".

    `_live_server` runs `web_app.app` in-process via a background *thread*, not a subprocess (see
    its own docstring) -- so `monkeypatch.setattr(web_app, "calibrate_map", ...)` here reaches the
    exact same module attribute `_auto_scale_worker` calls, giving both tests below a
    deterministic outcome without needing a real scale-bar/grid/circle signal on the fixture map
    (same stubbing approach as `tests/unit/test_cli.py`'s T087 tests and this task's own
    `tests/unit/web/test_app.py::TestAutoScale`).

    The success case asserts the detected tier from the `/auto-scale` job's own network response
    rather than from transient `#status-message` text: `app.js`'s scale-form submit handler sets
    that tier status and then calls the unchanged `runSegment()` in the same synchronous stretch
    of the handler (no `await` in between) -- `runSegment` immediately overwrites
    `#status-message` with its own "Сегментация карты…" text before the browser ever paints the
    tier text, so polling the DOM for it would be a timing race, not a real assertion. The
    detected values landing in the ratio-mode fields are asserted from the DOM instead, since
    nothing downstream of the auto-scale job ever touches those fields again.
    """

    def test_auto_scale_success_populates_ratio_fields_and_reports_tier(
        self, _live_server: str, page: Page, synthetic_map, tmp_path: Path, monkeypatch
    ) -> None:
        sm = synthetic_map
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)

        stub = CalibrationResult(
            source="circle", scale_denominator=sm.scale_denominator, dpi=sm.dpi
        )
        monkeypatch.setattr(
            web_app, "calibrate_map", lambda image, config: (stub, sm.scale_denominator)
        )

        page.goto(_live_server + "/")
        page.set_input_files("#map-file-input", str(map_path))
        page.click("#upload-btn")
        expect(page.locator("#scale-fieldset")).to_be_enabled()

        page.check("#scale-mode-auto")
        with page.expect_response(
            lambda r: r.request.method == "POST" and r.url.endswith("/auto-scale")
        ) as post_info:
            page.click("#apply-scale-btn")
        job_id = post_info.value.json()["job_id"]

        deadline = time.monotonic() + 10.0
        job = None
        while time.monotonic() < deadline:
            job = page.request.get(f"{_live_server}/api/jobs/{job_id}").json()
            if job["status"] in ("done", "error"):
                break
            time.sleep(0.05)
        assert job is not None and job["status"] == "done", job
        assert job["result"] == {
            "source": "circle",
            "scale_denominator": sm.scale_denominator,
            "dpi": sm.dpi,
        }

        # The client-supplied stub matches the fixture's own real scale/dpi, so the flow proceeds
        # through the exact same, unchanged /segment endpoint the manual ratio path already uses
        # -- segmentation and auto-detect land the controls table exactly as that path does.
        page.wait_for_selector(
            "#controls-tbody tr", state="attached", timeout=_SEGMENT_AND_DETECT_TIMEOUT_MS
        )
        expect(page.locator("#scale-mode-ratio")).to_be_checked()
        assert float(page.input_value("#scale-denominator")) == sm.scale_denominator
        assert float(page.input_value("#scale-dpi")) == sm.dpi

    def test_auto_scale_failure_shows_error_and_leaves_manual_entry_available(
        self, _live_server: str, page: Page, synthetic_map, tmp_path: Path, monkeypatch
    ) -> None:
        sm = synthetic_map
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)

        monkeypatch.setattr(web_app, "calibrate_map", lambda image, config: (None, None))

        page.goto(_live_server + "/")
        page.set_input_files("#map-file-input", str(map_path))
        page.click("#upload-btn")
        expect(page.locator("#scale-fieldset")).to_be_enabled()

        page.check("#scale-mode-auto")
        page.click("#apply-scale-btn")

        expect(page.locator("#error-message")).to_be_visible()
        expect(page.locator("#error-message")).to_contain_text("вручную")

        # Manual entry is still available: switching back to ratio mode and applying it goes
        # through the ordinary, unaffected /segment flow (the stubbed `calibrate_map` failure
        # only ever fires on the /auto-scale path).
        page.check("#scale-mode-ratio")
        page.fill("#scale-denominator", str(sm.scale_denominator))
        page.fill("#scale-dpi", str(sm.dpi))
        page.click("#apply-scale-btn")
        page.wait_for_selector(
            "#controls-tbody tr", state="attached", timeout=_SEGMENT_AND_DETECT_TIMEOUT_MS
        )

    def test_auto_scale_fractional_values_leave_a_second_submit_working(
        self, _live_server: str, page: Page, synthetic_map, tmp_path: Path, monkeypatch
    ) -> None:
        """C1 regression: `calibrate_map`'s real dpi/scale_denominator are essentially never
        round numbers (e.g. `296.83464566929132`) -- writing them straight into `#scale-dpi`
        (`step="0.1"`) and `#scale-denominator` (`step="1"`) fails HTML5 `stepMismatch`
        constraint validation on the *next* submit while `#scale-dpi` sits inside the now-
        `[hidden]` ratio panel (calibrate mode) -- the browser can't show a validation bubble for
        a hidden field, so `#scale-form`'s `submit` event silently never fires again for the rest
        of the session. Guards the `Math.round(...)` fix in `app.js`'s auto-scale success
        handler; unlike the exact-300.0 success test above, this stub is deliberately fractional.
        """
        sm = synthetic_map
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)

        fractional_dpi = 296.83464566929132
        fractional_scale = 24999.7
        stub = CalibrationResult(
            source="circle", scale_denominator=fractional_scale, dpi=fractional_dpi
        )
        monkeypatch.setattr(
            web_app, "calibrate_map", lambda image, config: (stub, fractional_scale)
        )

        page.goto(_live_server + "/")
        page.set_input_files("#map-file-input", str(map_path))
        page.click("#upload-btn")
        expect(page.locator("#scale-fieldset")).to_be_enabled()

        page.check("#scale-mode-auto")
        with page.expect_response(
            lambda r: r.request.method == "POST" and r.url.endswith("/auto-scale")
        ) as post_info:
            page.click("#apply-scale-btn")
        job_id = post_info.value.json()["job_id"]

        deadline = time.monotonic() + 10.0
        job = None
        while time.monotonic() < deadline:
            job = page.request.get(f"{_live_server}/api/jobs/{job_id}").json()
            if job["status"] in ("done", "error"):
                break
            time.sleep(0.05)
        assert job is not None and job["status"] == "done", job

        # The auto-scale success handler's own runSegment() call (not a native form submit)
        # already reached /segment once -- wait for it to land the controls table before
        # touching the form again, so the assertion below is unambiguously about a *second*,
        # user-initiated submit.
        page.wait_for_selector(
            "#controls-tbody tr", state="attached", timeout=_SEGMENT_AND_DETECT_TIMEOUT_MS
        )
        assert float(page.input_value("#scale-dpi")) == round(fractional_dpi * 10) / 10
        assert float(page.input_value("#scale-denominator")) == round(fractional_scale)

        # Switch to calibrate mode -- this hides the ratio panel (and the fractional
        # #scale-dpi/#scale-denominator fields it still holds), reproducing C1's exact failure
        # mode.
        page.check("#scale-mode-calibrate")
        page.fill("#calib-x1", "10")
        page.fill("#calib-y1", "10")
        page.fill("#calib-x2", "110")
        page.fill("#calib-y2", "10")
        page.fill("#calib-meters", "100")

        with page.expect_request(lambda r: r.method == "POST" and r.url.endswith("/segment")):
            page.click("#apply-scale-btn")


class TestControlsPointsAutoFill:
    """T092 (ADR-024, F22): the controls table's points field auto-fills from a control's number
    using T091's corrected rule (`Math.floor(number / 10)`, JS equivalent of Python's `number //
    10`), unless that control's points has been hand-edited since its last detect/import
    (sticky-off, per-control, in-memory client state). Reuses `TestFullViewerFlow`'s own
    upload/calibrate/detect setup (see that class's docstring) rather than a shared fixture --
    this module has none, for the reason `TestViewerLayout` gives for its own copy.
    """

    def test_number_edit_autofills_points_until_points_hand_edited(
        self, _live_server: str, page: Page, synthetic_map, tmp_path: Path
    ) -> None:
        sm = synthetic_map
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)

        page.goto(_live_server + "/")
        page.set_input_files("#map-file-input", str(map_path))
        page.click("#upload-btn")
        expect(page.locator("#scale-fieldset")).to_be_enabled()

        page.fill("#scale-denominator", str(sm.scale_denominator))
        page.fill("#scale-dpi", str(sm.dpi))
        page.click("#apply-scale-btn")

        page.wait_for_selector(
            "#controls-tbody tr", state="attached", timeout=_SEGMENT_AND_DETECT_TIMEOUT_MS
        )

        control_id = (
            page.locator("#controls-tbody tr").first.get_attribute("id") or ""
        ).removeprefix("control-row-")
        assert control_id

        number_selector = f"#control-{control_id}-number"
        points_selector = f"#control-{control_id}-points"

        def _set_field(selector: str, value: str) -> None:
            # Same approach as `TestFullViewerFlow`'s table edit: set the value and dispatch a
            # real `change` event directly (what a blur/Enter would fire in a live browser),
            # then wait for the resulting PUT .../controls to land before asserting on state.
            with page.expect_response(
                lambda r: r.request.method == "PUT" and r.url.endswith("/controls")
            ):
                page.evaluate(
                    """([sel, val]) => {
                        const el = document.querySelector(sel);
                        el.value = val;
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }""",
                    [selector, value],
                )

        # --- Editing the number auto-fills points via T091's corrected rule (F22: 123 -> 12) ---
        _set_field(number_selector, "123")
        assert page.input_value(points_selector) == "12"

        # --- Hand-editing points marks this control's points manually-set (sticky-off) ---------
        _set_field(points_selector, "99")
        assert page.input_value(points_selector) == "99"

        # --- A further number edit no longer overwrites the hand-edited points (45 -> 4 skipped,
        # per F22: "once points has been hand-edited for that control, further number edits no
        # longer overwrite it") ------------------------------------------------------------------
        _set_field(number_selector, "45")
        assert page.input_value(number_selector) == "45"
        assert page.input_value(points_selector) == "99"


class TestRouteAlternativesSwitcher:
    """T093 (ADR-025): the viewer exposes the plan response's `alternatives` as switch controls,
    switching between them client-side with no new server round-trip. Reuses
    `TestFullViewerFlow`'s own upload/calibrate/detect setup, like `TestControlsPointsAutoFill`.

    The two cases below each force a specific `alternatives` shape onto an otherwise real
    upload/segment/detect/plan flow, rather than gambling on whether the real GRASP-restart search
    happens to find something structurally distinct on this one fixture map:
    - the "switcher appears" case monkeypatches `web_app.solve_alternatives` itself -- the same
      technique `TestAutoScale` already uses for `web_app.calibrate_map` -- so the two
      alternatives' scores/totals are known exactly rather than read back and trusted blind. Only
      the alternatives search is stubbed; upload, segment, detect, and the primary route (the real
      `solve_exact`) are untouched.
    - the "hidden" case instead forces `RunConfig.alternatives=1` onto the real `/plan` POST body
      via Playwright request interception (`app.js`'s run form has no field for it) -- the
      server's own `top = ranked[:k]` cap (`solve/alternatives.py`) then guarantees exactly one
      entry back, real end to end, regardless of how many distinct candidates the real search
      would otherwise find.
    """

    def test_two_alternatives_show_a_switcher_that_redraws_client_side(
        self, _live_server: str, page: Page, synthetic_map, tmp_path: Path, monkeypatch
    ) -> None:
        sm = synthetic_map
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)

        def _stub_solve_alternatives(controls, matrix, run_config, config):
            hub = next(c for c in controls if c.is_hub)
            candidates = [c for c in controls if not c.is_hub]
            assert len(candidates) >= 2, "fixture needs >=2 non-hub controls for this stub"
            routes = []
            for i, control in enumerate(candidates[:2]):
                leg_out = Leg(from_id=hub.id, to_id=control.id, seconds=100.0, meters=50.0)
                leg_back = Leg(from_id=control.id, to_id=hub.id, seconds=100.0, meters=50.0)
                routes.append(
                    Route(
                        order=[hub.id, control.id, hub.id],
                        legs=[leg_out, leg_back],
                        total_seconds=200.0 + i * 1000.0,
                        total_meters=100.0,
                        points=1,
                        penalty=0.0,
                        score=50.0 - i * 20.0,
                        solver="heuristic",
                        optimal=False,
                        seed=run_config.seed,
                    )
                )
            return AlternativesResult(
                routes=routes, interestingness=routes[0].score - routes[-1].score
            )

        monkeypatch.setattr(web_app, "solve_alternatives", _stub_solve_alternatives)

        page.goto(_live_server + "/")
        page.set_input_files("#map-file-input", str(map_path))
        page.click("#upload-btn")
        expect(page.locator("#scale-fieldset")).to_be_enabled()

        page.fill("#scale-denominator", str(sm.scale_denominator))
        page.fill("#scale-dpi", str(sm.dpi))
        page.click("#apply-scale-btn")

        page.wait_for_selector(
            "#controls-tbody tr", state="attached", timeout=_SEGMENT_AND_DETECT_TIMEOUT_MS
        )

        page.click("#run-btn")
        page.wait_for_selector("#legs-tbody tr", state="attached", timeout=_PLAN_TIMEOUT_MS)

        switcher = page.locator("#route-switcher")
        expect(switcher).to_be_visible()
        buttons = switcher.locator("button")
        expect(buttons).to_have_count(3)  # primary + 2 stubbed alternatives
        expect(buttons.nth(0)).to_have_attribute("aria-pressed", "true")
        expect(buttons.nth(1)).to_have_attribute("aria-pressed", "false")
        expect(buttons.nth(2)).to_have_attribute("aria-pressed", "false")

        primary_score = page.inner_text("#route-score")

        # --- Selecting the lower-scored alternative redraws the summary/legs client-side, with
        # no new network request of any kind -----------------------------------------------------
        requests: list[str] = []
        page.on("request", lambda req: requests.append(f"{req.method} {req.url}"))

        buttons.nth(2).click()

        expect(buttons.nth(2)).to_have_attribute("aria-pressed", "true")
        expect(buttons.nth(0)).to_have_attribute("aria-pressed", "false")
        expect(page.locator("#route-score")).to_have_text("30.0")
        assert page.inner_text("#route-score") != primary_score
        expect(page.locator("#legs-tbody tr")).to_have_count(2)
        assert requests == [], f"selecting an alternative fired network requests: {requests}"

        # --- Switching back to the primary restores its own numbers (idempotent) -----------------
        buttons.nth(0).click()
        expect(page.locator("#route-score")).to_have_text(primary_score)
        expect(buttons.nth(0)).to_have_attribute("aria-pressed", "true")

    def test_at_most_one_alternative_hides_the_switcher(
        self, _live_server: str, page: Page, synthetic_map, tmp_path: Path
    ) -> None:
        sm = synthetic_map
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)

        # `app.js`'s run form posts no `alternatives` field -- force it onto the real `/plan` POST
        # body instead; the server still runs a real solve, and `solve_alternatives`'s own
        # `top = ranked[:k]` cap guarantees at most one entry comes back.
        def _cap_alternatives_at_one(pw_route, request):
            payload = json.loads(request.post_data or "{}")
            payload["alternatives"] = 1
            pw_route.continue_(post_data=json.dumps(payload))

        page.route(re.compile(r"/plan$"), _cap_alternatives_at_one)

        page.goto(_live_server + "/")
        page.set_input_files("#map-file-input", str(map_path))
        page.click("#upload-btn")
        expect(page.locator("#scale-fieldset")).to_be_enabled()

        page.fill("#scale-denominator", str(sm.scale_denominator))
        page.fill("#scale-dpi", str(sm.dpi))
        page.click("#apply-scale-btn")

        page.wait_for_selector(
            "#controls-tbody tr", state="attached", timeout=_SEGMENT_AND_DETECT_TIMEOUT_MS
        )

        page.click("#run-btn")
        page.wait_for_selector("#legs-tbody tr", state="attached", timeout=_PLAN_TIMEOUT_MS)

        expect(page.locator("#route-switcher")).to_be_hidden()
        assert page.locator("#route-switcher").inner_html() == ""


class TestCalibrationToolArmedState:
    """T106 (F17, I6): the calibration-line tool (`#calib-start-btn`, `state.mode = "calibrate"`)
    used to place/overwrite a calibration point on the plain `pointerdown` that starts *any* map
    gesture -- so panning the map while the tool was armed corrupted the calibration line instead
    of panning. Only upload is needed here (no scale apply/detect/plan): `loadMapPreview` already
    calls `view.fit()` once the map preview image loads, which is all `screenToMap`/`panBy` need.

    `view.panBy` (`view.js`) is a plain unclamped `panX += dx`, so a real drag is provable without
    reading any internal JS state: click the same screen point again after a drag and the mapped
    coordinates must differ (proving the view moved), whereas an unmoved click maps to the same
    point every time.
    """

    def test_drag_pans_without_placing_point_click_places_one(
        self, _live_server: str, page: Page, synthetic_map, tmp_path: Path
    ) -> None:
        sm = synthetic_map
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)

        page.goto(_live_server + "/")
        page.set_input_files("#map-file-input", str(map_path))
        page.click("#upload-btn")
        expect(page.locator("#scale-fieldset")).to_be_enabled()

        page.check("#scale-mode-calibrate")
        page.click("#calib-start-btn")

        # --- Armed-state affordance: distinct from an ordinary `aria-pressed` button (T106) ------
        expect(page.locator("#calib-start-btn")).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#map-viewport")).to_have_class(re.compile(r"\bmode-calibrate\b"))

        box = page.locator("#map-canvas").bounding_box()
        assert box is not None
        cx = box["x"] + box["width"] / 2
        cy = box["y"] + box["height"] / 2

        # --- A genuine click (no meaningful movement) places a calibration point -----------------
        page.mouse.move(cx, cy)
        page.mouse.down()
        page.mouse.up()
        expect(page.locator("#calib-x1")).not_to_have_value("")
        expect(page.locator("#calib-x2")).to_have_value("")
        x1_before = page.input_value("#calib-x1")
        y1_before = page.input_value("#calib-y1")

        # --- A drag (well past the click/drag threshold) pans the map instead of placing or
        # overwriting a calibration point: the single point placed above must survive untouched
        # and no second point appears ------------------------------------------------------------
        page.mouse.move(cx, cy)
        page.mouse.down()
        page.mouse.move(cx + 120, cy + 60, steps=10)
        page.mouse.up()
        assert page.input_value("#calib-x1") == x1_before
        assert page.input_value("#calib-y1") == y1_before
        expect(page.locator("#calib-x2")).to_have_value("")

        # --- Proof the drag actually panned the view (not merely a no-op): clicking the exact
        # same screen point again now lands the *second* calibration point (state.calibration had
        # only one point) at map coordinates that differ from the first click's, since the same
        # screen pixel now maps elsewhere on the (unclamped) panned view ---------------------------
        page.mouse.move(cx, cy)
        page.mouse.down()
        page.mouse.up()
        expect(page.locator("#calib-x2")).not_to_have_value("")
        assert (page.input_value("#calib-x2"), page.input_value("#calib-y2")) != (
            x1_before,
            y1_before,
        )


class TestAddControlClickToPlace:
    """T107 (F17, I6): `#add-control-btn` used to drop a control at the view centre on click,
    the moment it was pressed. It now arms a one-shot `state.mode = "add-once"` instead -- the
    next map click (via `beginArmedPointerGesture`, T106's shared armed-gesture helper) places the
    control exactly there and immediately returns to idle, matching `#calib-start-btn`'s own
    click-to-place flow. The pre-existing `#toggle-add-mode-btn` multi-placement flow
    (`state.mode = "add"`) is untouched and not exercised here.

    Needs the full upload -> apply-scale -> segment+detect setup (`TestFullViewerFlow`'s own path)
    because `#add-control-btn` stays `disabled` until `state.segment` is set
    (`updateAvailability`), unlike T106's calibration test which only needed `view.fit()`.
    """

    def test_click_arms_then_places_at_click_point_and_returns_to_idle(
        self, _live_server: str, page: Page, synthetic_map, tmp_path: Path
    ) -> None:
        sm = synthetic_map
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)

        page.goto(_live_server + "/")
        page.set_input_files("#map-file-input", str(map_path))
        page.click("#upload-btn")
        expect(page.locator("#scale-fieldset")).to_be_enabled()

        page.fill("#scale-denominator", str(sm.scale_denominator))
        page.fill("#scale-dpi", str(sm.dpi))
        page.click("#apply-scale-btn")
        page.wait_for_selector(
            "#controls-tbody tr", state="attached", timeout=_SEGMENT_AND_DETECT_TIMEOUT_MS
        )
        rows_before = page.locator("#controls-tbody tr").count()

        def last_row_id() -> str:
            row_ids = page.evaluate(
                "() => [...document.querySelectorAll('#controls-tbody tr')].map((r) => r.id)"
            )
            return row_ids[-1].replace("control-row-", "")

        def place_at(screen_x: float, screen_y: float) -> tuple[float, float]:
            page.click("#add-control-btn")
            expect(page.locator("#add-control-btn")).to_have_attribute("aria-pressed", "true")
            expect(page.locator("#map-viewport")).to_have_class(re.compile(r"\bmode-add-once\b"))
            page.mouse.move(screen_x, screen_y)
            page.mouse.down()
            page.mouse.up()
            row_id = last_row_id()
            return (
                float(page.input_value(f"#control-{row_id}-x")),
                float(page.input_value(f"#control-{row_id}-y")),
            )

        # --- Clicking the panel button arms the tool without placing anything -------------------
        page.click("#add-control-btn")
        expect(page.locator("#add-control-btn")).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#map-viewport")).to_have_class(re.compile(r"\bmode-add-once\b"))
        assert page.locator("#controls-tbody tr").count() == rows_before
        page.click("#add-control-btn")  # disarm again; the placements below re-arm explicitly
        expect(page.locator("#add-control-btn")).to_have_attribute("aria-pressed", "false")

        box = page.locator("#map-canvas").bounding_box()
        assert box is not None

        # --- The next map click places the control at that exact point, then returns to idle,
        # proven by placing at two different points and getting two different, click-dependent
        # map positions -- the old behaviour placed at `view.viewCenterMap()` regardless of any
        # later map click, which would give identical x/y both times ------------------------------
        xa, ya = place_at(box["x"] + box["width"] * 0.25, box["y"] + box["height"] * 0.75)
        expect(page.locator("#controls-tbody tr")).to_have_count(rows_before + 1)
        expect(page.locator("#add-control-btn")).to_have_attribute("aria-pressed", "false")
        expect(page.locator("#map-viewport")).not_to_have_class(re.compile(r"\bmode-add-once\b"))

        xb, yb = place_at(box["x"] + box["width"] * 0.75, box["y"] + box["height"] * 0.25)
        expect(page.locator("#controls-tbody tr")).to_have_count(rows_before + 2)

        assert (xa, ya) != (xb, yb)
        assert xb > xa  # second click was to the right of the first
        assert yb < ya  # second click was above the first

    def test_enter_key_places_at_view_center_and_returns_to_idle(
        self, _live_server: str, page: Page, synthetic_map, tmp_path: Path
    ) -> None:
        """Review finding H2 (I6 milestone review): the button handler focuses `#map-viewport` on
        arming, so a keyboard user who never touches the mouse needs an `Enter` path too -- `add`
        and `calibrate` both already have one, `add-once` didn't until this fix. Without it,
        arming via the button and pressing `Enter` was a dead end.
        """
        sm = synthetic_map
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)

        page.goto(_live_server + "/")
        page.set_input_files("#map-file-input", str(map_path))
        page.click("#upload-btn")
        expect(page.locator("#scale-fieldset")).to_be_enabled()

        page.fill("#scale-denominator", str(sm.scale_denominator))
        page.fill("#scale-dpi", str(sm.dpi))
        page.click("#apply-scale-btn")
        page.wait_for_selector(
            "#controls-tbody tr", state="attached", timeout=_SEGMENT_AND_DETECT_TIMEOUT_MS
        )
        rows_before = page.locator("#controls-tbody tr").count()

        page.click("#add-control-btn")
        expect(page.locator("#add-control-btn")).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#map-viewport")).to_be_focused()

        page.keyboard.press("Enter")
        expect(page.locator("#controls-tbody tr")).to_have_count(rows_before + 1)
        expect(page.locator("#add-control-btn")).to_have_attribute("aria-pressed", "false")
        expect(page.locator("#map-viewport")).not_to_have_class(re.compile(r"\bmode-add-once\b"))


class TestToggleAddModeArmedState:
    """Review finding H-1 (I6 milestone review): `#toggle-add-mode-btn`'s persistent
    multi-placement `add` mode used to place a control straight on `pointerdown` -- unlike
    `calibrate` (T106) and `add-once` (T107), it never went through the shared click-vs-drag
    gesture helper, so a drag while armed dropped a spurious control at the drag origin instead of
    panning, the exact bug T106 fixed for `calibrate`. Mirrors
    `TestCalibrationToolArmedState`'s own drag-pans/click-places proof, but for a persistent mode:
    unlike `add-once`, placing one control does not return it to idle.

    Needs the full upload -> apply-scale -> segment+detect setup, same as
    `TestAddControlClickToPlace`, because `#toggle-add-mode-btn` stays `disabled` until
    `state.segment` is set.
    """

    def test_drag_pans_without_placing_control_click_places_one_and_stays_armed(
        self, _live_server: str, page: Page, synthetic_map, tmp_path: Path
    ) -> None:
        sm = synthetic_map
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)

        page.goto(_live_server + "/")
        page.set_input_files("#map-file-input", str(map_path))
        page.click("#upload-btn")
        expect(page.locator("#scale-fieldset")).to_be_enabled()

        page.fill("#scale-denominator", str(sm.scale_denominator))
        page.fill("#scale-dpi", str(sm.dpi))
        page.click("#apply-scale-btn")
        page.wait_for_selector(
            "#controls-tbody tr", state="attached", timeout=_SEGMENT_AND_DETECT_TIMEOUT_MS
        )
        rows_before = page.locator("#controls-tbody tr").count()

        page.click("#toggle-add-mode-btn")
        expect(page.locator("#toggle-add-mode-btn")).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#map-viewport")).to_have_class(re.compile(r"\bmode-add\b"))

        box = page.locator("#map-canvas").bounding_box()
        assert box is not None
        cx = box["x"] + box["width"] / 2
        cy = box["y"] + box["height"] / 2

        # --- A drag (well past the click/drag threshold) pans the map instead of placing a
        # control -- before the fix this placed one at the drag's start point on raw pointerdown --
        page.mouse.move(cx, cy)
        page.mouse.down()
        page.mouse.move(cx + 120, cy + 60, steps=10)
        page.mouse.up()
        assert page.locator("#controls-tbody tr").count() == rows_before
        # still armed -- a persistent mode, unlike add-once, survives a pan
        expect(page.locator("#toggle-add-mode-btn")).to_have_attribute("aria-pressed", "true")

        # --- A genuine click (no meaningful movement) places a control, and the mode stays armed
        # for further placements (unlike add-once, which returns to idle) ------------------------
        page.mouse.move(cx, cy)
        page.mouse.down()
        page.mouse.up()
        expect(page.locator("#controls-tbody tr")).to_have_count(rows_before + 1)
        expect(page.locator("#toggle-add-mode-btn")).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#map-viewport")).to_have_class(re.compile(r"\bmode-add\b"))

        page.click("#toggle-add-mode-btn")  # disarm
        expect(page.locator("#toggle-add-mode-btn")).to_have_attribute("aria-pressed", "false")
        expect(page.locator("#map-viewport")).not_to_have_class(re.compile(r"\bmode-add\b"))

        # --- After disarming, mode is back to idle: a drag on the canvas just pans, it does not
        # place a third control -----------------------------------------------------------------
        cx, cy = box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5
        page.mouse.move(cx, cy)
        page.mouse.down()
        page.mouse.move(cx + 80, cy + 40, steps=10)
        page.mouse.up()
        expect(page.locator("#controls-tbody tr")).to_have_count(rows_before + 1)
