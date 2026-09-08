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
        expect(page.locator("#error-message")).to_contain_text("manually")

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
