"""Endpoint tests for the FastAPI web backend (T060, SPEC F17).

Drives the app in-process via `TestClient` (bundled with fastapi/starlette): under `TestClient`,
`BackgroundTasks` run synchronously within the request/response cycle, so a job started by a POST
is normally already `done`/`error` by the time that POST returns -- `_wait_for_job` polls
regardless, so these tests do not depend on that timing detail holding forever.

`RUNS_ROOT` is monkeypatched to a per-test `tmp_path` (autouse fixture below) so these tests never
write into the real project's `runs/` directory.
"""

from __future__ import annotations

import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

import rogaine.web.app as web_app

client = TestClient(web_app.app)


@pytest.fixture(autouse=True)
def _isolated_runs_root(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "RUNS_ROOT", tmp_path / "runs")


def _encode_png(image_rgb: np.ndarray) -> bytes:
    """RGB array -> PNG bytes (cv2 wants BGR); matches `tests/unit/io/test_raster.py`'s pattern."""
    ok, buf = cv2.imencode(".png", image_rgb[:, :, ::-1])
    assert ok
    return buf.tobytes()


def _upload(image_rgb: np.ndarray) -> str:
    resp = client.post(
        "/api/runs", files={"file": ("ignored.png", _encode_png(image_rgb), "image/png")}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["run_id"]


def _wait_for_job(job_id: str, timeout: float = 30.0) -> dict:
    start = time.monotonic()
    while True:
        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data["status"] in ("done", "error"):
            return data
        if time.monotonic() - start > timeout:
            raise AssertionError(f"job {job_id} did not finish in time: {data}")
        time.sleep(0.05)


def _run_config(**overrides: object) -> dict:
    # heuristic + a small time budget regardless of candidate count -- keeps this test suite's
    # runtime bounded no matter how many controls a fixture map happens to carry.
    base: dict[str, object] = {
        "base_speed_mps": 2.0,
        "time_limit_s": 3600.0,
        "penalty_per_min": 1.0,
        "strategy": "heuristic",
        "heuristic_time_budget_s": 1.0,
        "alternatives": 2,
        "seed": 0,
    }
    base.update(overrides)
    return base


class TestFullFlow:
    def test_upload_segment_detect_plan_export(self, synthetic_map) -> None:
        sm = synthetic_map
        run_id = _upload(sm.image)

        resp = client.post(
            f"/api/runs/{run_id}/segment", json={"dpi": sm.dpi, "scale": sm.scale_denominator}
        )
        assert resp.status_code == 202, resp.text
        job = _wait_for_job(resp.json()["job_id"])
        assert job["status"] == "done", job
        assert job["result"]["dpi"] == sm.dpi

        resp = client.post(f"/api/runs/{run_id}/detect")
        assert resp.status_code == 202, resp.text
        job = _wait_for_job(resp.json()["job_id"])
        assert job["status"] == "done", job
        assert job["result"]["hub_found"] is True
        assert len(job["result"]["controls"]) >= 1

        resp = client.get(f"/api/runs/{run_id}/controls")
        assert resp.status_code == 200, resp.text
        assert any(c["is_hub"] for c in resp.json())

        resp = client.post(f"/api/runs/{run_id}/plan", json=_run_config())
        assert resp.status_code == 202, resp.text
        job = _wait_for_job(resp.json()["job_id"])
        assert job["status"] == "done", job
        order = job["result"]["route"]["order"]
        assert order[0] == order[-1]
        assert "alternatives" in job["result"]

        for artifact in ("route.json", "route.png", "controls.csv"):
            resp = client.get(f"/api/runs/{run_id}/export/{artifact}")
            assert resp.status_code == 200, resp.text
            assert len(resp.content) > 0


class TestEditedControls:
    def test_plan_honors_a_put_controls_edit(self, synthetic_map) -> None:
        sm = synthetic_map
        run_id = _upload(sm.image)

        resp = client.post(
            f"/api/runs/{run_id}/segment", json={"dpi": sm.dpi, "scale": sm.scale_denominator}
        )
        _wait_for_job(resp.json()["job_id"])

        # Replace whatever `detect` would have found with a small, hand-picked set -- skipping
        # `detect` entirely proves `plan` reads back exactly what was PUT, not a leftover result.
        hub = sm.hub.model_copy(update={"source": "manual"})
        a = sm.controls[1].model_copy(update={"points": 42, "source": "manual"})
        b = sm.controls[2].model_copy(update={"points": 7, "source": "manual"})
        edited = [hub, a, b]

        resp = client.put(
            f"/api/runs/{run_id}/controls", json=[c.model_dump(mode="json") for c in edited]
        )
        assert resp.status_code == 200, resp.text
        by_id = {c["id"]: c for c in resp.json()}
        assert by_id[a.id]["points"] == 42
        assert by_id[b.id]["points"] == 7

        resp = client.post(f"/api/runs/{run_id}/plan", json=_run_config())
        assert resp.status_code == 202, resp.text
        job = _wait_for_job(resp.json()["job_id"])
        assert job["status"] == "done", job
        assert set(job["result"]["route"]["order"]) <= {hub.id, a.id, b.id}


class TestSecurity:
    def test_rejects_bad_magic_bytes(self) -> None:
        resp = client.post(
            "/api/runs", files={"file": ("map.png", b"not a real image", "image/png")}
        )
        assert resp.status_code == 400
        assert "format" in resp.json()["detail"]

    def test_rejects_an_oversized_upload(self, monkeypatch) -> None:
        monkeypatch.setattr(web_app, "MAX_UPLOAD_BYTES", 10)
        data = _encode_png(np.full((50, 50, 3), 255, dtype=np.uint8))
        assert len(data) > 10
        resp = client.post("/api/runs", files={"file": ("big.png", data, "image/png")})
        assert resp.status_code == 413

    def test_unknown_run_id_is_404_everywhere(self) -> None:
        assert client.get("/api/runs/does-not-exist/controls").status_code == 404
        resp = client.post(
            "/api/runs/does-not-exist/segment", json={"dpi": 300, "scale": 30000}
        )
        assert resp.status_code == 404
        assert client.post("/api/runs/does-not-exist/detect").status_code == 404
        resp = client.post("/api/runs/does-not-exist/plan", json=_run_config())
        assert resp.status_code == 404
        assert client.get("/api/runs/does-not-exist/export/route.json").status_code == 404
        assert client.get("/api/runs/does-not-exist/map").status_code == 404

    def test_unknown_job_id_is_404(self) -> None:
        assert client.get("/api/jobs/does-not-exist").status_code == 404

    def test_export_before_plan_has_run_is_404(self, synthetic_map) -> None:
        run_id = _upload(synthetic_map.image)
        assert client.get(f"/api/runs/{run_id}/export/route.json").status_code == 404

    def test_detect_before_segment_is_a_clean_400(self, synthetic_map) -> None:
        run_id = _upload(synthetic_map.image)
        assert client.post(f"/api/runs/{run_id}/detect").status_code == 400

    # -- S-001 / ADR-017: upper bounds reject extreme values at the API boundary, before a
    # background worker ever runs -- validation happens ahead of the run-id lookup, so a
    # nonexistent run id still 422s rather than 404ing. --

    def test_dpi_above_bound_is_rejected(self) -> None:
        resp = client.post(
            "/api/runs/does-not-exist/segment", json={"dpi": 2400.1, "scale": 30000}
        )
        assert resp.status_code == 422

    @pytest.mark.parametrize(
        "overrides",
        [
            {"time_limit_s": 86400.1},
            {"heuristic_time_budget_s": 600.1},
            {"alternatives": 21},
        ],
    )
    def test_run_config_field_above_bound_is_rejected(self, overrides: dict) -> None:
        resp = client.post(
            "/api/runs/does-not-exist/plan", json=_run_config(**overrides)
        )
        assert resp.status_code == 422


class TestWorkerErrorHandling:
    """S-001 / ADR-017: the three background workers used to catch only `(ValueError, OSError)`,
    so any other failure (a `MemoryError` from an extreme dpi, say) left the job stuck at
    `status: "running"` forever instead of surfacing to the client.
    """

    def test_unexpected_error_still_marks_the_job_as_errored(
        self, synthetic_map, monkeypatch
    ) -> None:
        sm = synthetic_map
        run_id = _upload(sm.image)
        run_dir = web_app.RUNS_ROOT / run_id
        map_path = next(run_dir.glob("map.*"))
        job_id = web_app._create_job(run_id, "segment")

        def _boom(*args: object, **kwargs: object) -> None:
            raise MemoryError("simulated OOM")

        monkeypatch.setattr(web_app, "load_config", _boom)
        web_app._segment_worker(job_id, run_dir, map_path, sm.dpi, 1.0, 0)

        job = client.get(f"/api/jobs/{job_id}").json()
        assert job["status"] == "error"
        assert "simulated OOM" in job["error"]


class TestStaticViewer:
    """T061's `src/rogaine/web/static/**` mount, added alongside its own endpoints above."""

    def test_root_serves_the_viewer_page(self) -> None:
        resp = client.get("/")
        assert resp.status_code == 200, resp.text
        assert "map-viewport" in resp.text

    def test_api_routes_still_win_over_the_catch_all_static_mount(self) -> None:
        # A regression guard for mount-ordering: the static mount is registered last so it never
        # shadows an /api/* path, but a Mount("/") could easily start intercepting everything if
        # someone reordered the file -- this would 404 (empty static dir) or 200 with HTML instead
        # of the expected 404 detail if that ever regressed.
        resp = client.get("/api/runs/does-not-exist/controls")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "unknown run id 'does-not-exist'"

    def test_map_endpoint_streams_the_uploaded_bytes_back(self, synthetic_map) -> None:
        sm = synthetic_map
        data = _encode_png(sm.image)
        resp = client.post("/api/runs", files={"file": ("ignored.png", data, "image/png")})
        run_id = resp.json()["run_id"]

        resp = client.get(f"/api/runs/{run_id}/map")
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "image/png"
        assert resp.content == data
