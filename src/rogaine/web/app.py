"""FastAPI backend for the local web viewer (T060, SPEC F17).

Wraps the same vision/cost/solve pipeline `cli.py`'s `segment_cmd`/`detect_cmd`/`plan_cmd` already
exercise -- read those three for the call order and arguments this module mirrors. The CLI is
stateless per invocation (SPEC user flow 2); this backend instead persists each stage's output as
a file under `runs/<uuid4>/` so later stages can be re-entered without redoing earlier work: the
uploaded map under a server-generated name, `terrain.npz` (segment), `controls.csv` (detect's
output *and* the format `PUT /controls` writes -- SPEC F9's CSV round trip, `read_controls`/
`write_controls` used both directions), `run_state.json` (the dpi `segment` resolved, so
`detect`/`plan` reload the map at the same pixel grid without the client re-supplying --dpi --
see `_read_run_state`), and `route.json`/`route.png` (plan).

Long-running stages (segment/detect/plan) run via `BackgroundTasks`: the endpoint validates its
input synchronously -- a bad scale/calibrate, or an artefact an earlier stage hasn't produced yet,
fails fast with a 4xx -- and returns a `job_id` immediately; `GET /api/jobs/{job_id}` polls
status/result/error. Jobs live in an in-memory registry -- fine for a local, single-process,
single-user tool with no persistence-across-restart requirement (unlike run artefacts, which are
files precisely so they survive one).

Security (PLAN.md): binds 127.0.0.1 by default (`cli.py`'s `serve_cmd`); uploads are sniffed by
magic bytes and capped in size, never trusted by client filename/Content-Type, and written under
`runs/<uuid4>/` with a server-picked name -- the client's filename is never used as a path; no
shell-out anywhere in this module.

No root `/` page and no static file serving here -- T061 builds `src/rogaine/web/static/**`
against this API.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from rogaine.config import load_config
from rogaine.cost.field import compute_cost_field
from rogaine.cost.graph import build_grid_graph
from rogaine.cost.travel import build_travel_matrix
from rogaine.io.controls_csv import read_controls, write_controls
from rogaine.io.raster import load_raster, resolve_dpi
from rogaine.io.route_json import write_route_json
from rogaine.io.scale import Calibration, mpp_from_dpi
from rogaine.models import Control, RunConfig
from rogaine.render.overlay import write_overlay
from rogaine.solve.alternatives import solve_alternatives
from rogaine.solve.exact import solve_exact
from rogaine.solve.heuristic import solve_heuristic
from rogaine.vision.controls import detect_controls
from rogaine.vision.ocr import read_control_numbers
from rogaine.vision.segment import load_terrain_map, save_terrain_map
from rogaine.vision.segment import segment as run_segmentation

#: Created relative to CWD -- mirrors `cli.py`'s own `--out-dir` default of `.`; identical on the
#: host and in the container, whose WORKDIR is `/app`. Already gitignored.
RUNS_ROOT = Path("runs")

#: Generous cap well above any real map scan (cf. `raster.MAX_DECODED_PIXELS`'s own reasoning):
#: the owner's real scan corpus tops out under 30 MB per file; 200 MB leaves comfortable headroom
#: for an uncompressed TIFF or a multi-page PDF while still refusing anything absurd before it is
#: ever fully decoded.
MAX_UPLOAD_BYTES = 200_000_000

#: (magic bytes, extension) -- checked in order against the *actual* uploaded bytes, never the
#: client-supplied filename or Content-Type header (PLAN.md security section).
_MAGIC_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"BM", "bmp"),
    (b"II*\x00", "tif"),
    (b"MM\x00*", "tif"),
    (b"%PDF-", "pdf"),
]

app = FastAPI(title="rogaine web viewer")


# -------------------------------------------------------------------------------------------
# Request/response models. `Control`/`RunConfig` (frozen, extra="forbid" -- see models.py's
# docstring) are reused directly wherever they already carry exactly what an endpoint needs;
# small local models fill the gaps (dpi/scale/calibrate) that only this API needs.
# -------------------------------------------------------------------------------------------


class CalibrationIn(BaseModel):
    """A two-point calibration, replacing `scale` (SPEC F3) -- mirrors `cli.py`'s `--calibrate`."""

    model_config = ConfigDict(extra="forbid")

    x1: float
    y1: float
    x2: float
    y2: float
    meters: float = Field(gt=0.0)


class SegmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dpi: float | None = Field(default=None, gt=0.0)
    scale: float | None = Field(default=None, gt=0.0)
    calibrate: CalibrationIn | None = None
    page: int = Field(default=0, ge=0)


class JobStatusOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    run_id: str
    kind: Literal["segment", "detect", "plan"]
    status: Literal["queued", "running", "done", "error"]
    result: Any = None
    error: str | None = None


# -------------------------------------------------------------------------------------------
# Job registry -- in-memory, module-level (design decision: no Celery/Redis/multiprocessing for
# a local single-user tool; see module docstring).
# -------------------------------------------------------------------------------------------


@dataclass
class _JobRecord:
    job_id: str
    run_id: str
    kind: Literal["segment", "detect", "plan"]
    status: Literal["queued", "running", "done", "error"] = "queued"
    result: Any = None
    error: str | None = None


_jobs: dict[str, _JobRecord] = {}
_jobs_lock = threading.Lock()


def _create_job(run_id: str, kind: Literal["segment", "detect", "plan"]) -> str:
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = _JobRecord(job_id=job_id, run_id=run_id, kind=kind)
    return job_id


def _update_job(job_id: str, **updates: Any) -> None:
    with _jobs_lock:
        record = _jobs[job_id]
        for key, value in updates.items():
            setattr(record, key, value)


# -------------------------------------------------------------------------------------------
# Run directory helpers.
# -------------------------------------------------------------------------------------------


def _require_run(run_id: str) -> Path:
    """The run directory for *run_id*, or a 404 -- also rejects a malformed id before it ever
    reaches a filesystem path (run ids are server-generated `uuid4().hex`, never client input
    trusted as a path component).
    """
    try:
        uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown run id {run_id!r}") from None
    run_dir = RUNS_ROOT / run_id
    if not run_dir.is_dir():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown run id {run_id!r}")
    return run_dir


def _map_path(run_dir: Path) -> Path:
    matches = sorted(run_dir.glob("map.*"))
    if not matches:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no map uploaded for this run")
    return matches[0]


def _write_run_state(run_dir: Path, *, dpi: float) -> None:
    """Persist the dpi `segment` resolved, so `detect`/`plan` reload the same map at the same
    pixel grid without the client re-supplying (or risking disagreeing on) dpi/scale.
    """
    (run_dir / "run_state.json").write_text(json.dumps({"dpi": dpi}), encoding="utf-8")


def _read_run_state(run_dir: Path) -> float | None:
    path = run_dir / "run_state.json"
    if not path.is_file():
        return None
    return float(json.loads(path.read_text(encoding="utf-8"))["dpi"])


def _sniff_extension(data: bytes) -> str | None:
    for magic, ext in _MAGIC_SIGNATURES:
        if data.startswith(magic):
            return ext
    return None


def _resolve_mpp(dpi: float, scale: float | None, calibrate: CalibrationIn | None) -> float:
    """Meters-per-pixel from `scale` (+ dpi) or `calibrate`, never both, never neither -- same
    contract as `cli.py`'s private `_resolve_mpp` (not imported: that one belongs to `cli.py`).
    """
    if scale is not None and calibrate is not None:
        raise ValueError("pass either scale or calibrate, not both")
    if scale is not None:
        return mpp_from_dpi(dpi, scale)
    if calibrate is not None:
        cal = Calibration(
            calibrate.x1, calibrate.y1, calibrate.x2, calibrate.y2, calibrate.meters
        )
        return cal.meters_per_pixel
    raise ValueError("pass scale (with dpi) or calibrate to resolve meters-per-pixel")


# -------------------------------------------------------------------------------------------
# Background workers -- mirror `cli.py`'s `segment_cmd`/`detect_cmd`/`plan_cmd` bodies exactly in
# which library functions they call, in what order, with what arguments.
# -------------------------------------------------------------------------------------------


def _segment_worker(
    job_id: str, run_dir: Path, map_path: Path, dpi: float, mpp: float, page: int
) -> None:
    _update_job(job_id, status="running")
    try:
        cfg = load_config()
        image = load_raster(map_path, page=page, dpi=dpi)
        terrain_map = run_segmentation(image, dpi, mpp, cfg)
        save_terrain_map(run_dir / "terrain.npz", terrain_map)
        _write_run_state(run_dir, dpi=dpi)
    except (ValueError, OSError) as exc:
        _update_job(job_id, status="error", error=str(exc))
        return
    h, w = terrain_map.shape
    _update_job(
        job_id,
        status="done",
        result={"width": w, "height": h, "meters_per_pixel": mpp, "dpi": dpi},
    )


def _detect_worker(job_id: str, run_dir: Path, map_path: Path, dpi: float) -> None:
    _update_job(job_id, status="running")
    try:
        cfg = load_config()
        image = load_raster(map_path, dpi=dpi)
        controls = detect_controls(image, dpi, cfg)
        controls, flags = read_control_numbers(image, controls, dpi, cfg)
        write_controls(run_dir / "controls.csv", controls)
    except (ValueError, OSError) as exc:
        _update_job(job_id, status="error", error=str(exc))
        return
    # Unlike `detect_cmd`, a missing hub does not fail the job: SPEC user flow 3 has the user add
    # one by hand via PUT /controls, so the (mostly correct) detected circles must still reach the
    # client to edit rather than be thrown away behind an error-only poll result.
    result = {
        "controls": [c.model_dump() for c in controls],
        "flags": flags,
        "hub_found": any(c.is_hub for c in controls),
    }
    _update_job(job_id, status="done", result=result)


def _plan_worker(
    job_id: str, run_dir: Path, map_path: Path, dpi: float, run_config: RunConfig
) -> None:
    _update_job(job_id, status="running")
    try:
        cfg = load_config()
        terrain_map = load_terrain_map(run_dir / "terrain.npz")
        controls = read_controls(run_dir / "controls.csv")
        image = load_raster(map_path, dpi=dpi)

        cost_field = compute_cost_field(terrain_map, run_config.base_speed_mps, cfg)
        graph = build_grid_graph(cost_field, cfg)
        matrix = build_travel_matrix(controls, graph, terrain_map.meters_per_pixel, cfg)

        n_candidates = sum(1 for c in controls if not c.is_hub and c.points is not None)
        if run_config.strategy == "exact":
            route = solve_exact(controls, matrix, run_config, cfg)
        elif run_config.strategy == "heuristic":
            route = solve_heuristic(controls, matrix, run_config, cfg)
        elif n_candidates <= cfg.solver.exact_max_controls:
            route = solve_exact(controls, matrix, run_config, cfg)
        else:
            route = solve_heuristic(controls, matrix, run_config, cfg)

        if len(route.order) <= 2:
            _update_job(
                job_id,
                status="error",
                error="no reachable route: no candidate control could be reached within the "
                "time limit",
            )
            return

        alt_result = solve_alternatives(controls, matrix, run_config, cfg)

        write_route_json(run_dir / "route.json", route, run_config)
        write_overlay(run_dir / "route.png", image, route, controls)
    except (ValueError, OSError) as exc:
        _update_job(job_id, status="error", error=str(exc))
        return

    result = {
        "route": route.model_dump(),
        "alternatives": [r.model_dump() for r in alt_result.routes],
        "interestingness": alt_result.interestingness,
    }
    _update_job(job_id, status="done", result=result)


# -------------------------------------------------------------------------------------------
# Endpoints.
# -------------------------------------------------------------------------------------------


@app.post("/api/runs", status_code=status.HTTP_201_CREATED)
async def create_run(file: Annotated[UploadFile, File()]) -> dict[str, str]:
    """Upload a map. Sniffs the actual bytes for PNG/JPEG/BMP/TIFF/PDF magic bytes -- never the
    client-supplied filename or Content-Type (PLAN.md security section) -- and stores the file
    under `runs/<uuid4>/map.<sniffed-ext>`, a server-generated name and location.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1 << 20)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"upload exceeds the {MAX_UPLOAD_BYTES:,} byte cap",
            )
        chunks.append(chunk)
    data = b"".join(chunks)

    ext = _sniff_extension(data)
    if ext is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "unrecognized file format (checked PNG/JPEG/BMP/TIFF/PDF magic bytes)",
        )

    run_id = uuid.uuid4().hex
    run_dir = RUNS_ROOT / run_id
    run_dir.mkdir(parents=True)
    (run_dir / f"map.{ext}").write_bytes(data)
    return {"run_id": run_id}


@app.post("/api/runs/{run_id}/segment", status_code=status.HTTP_202_ACCEPTED)
def start_segment(
    run_id: str, body: SegmentRequest, background_tasks: BackgroundTasks
) -> dict[str, str]:
    run_dir = _require_run(run_id)
    map_path = _map_path(run_dir)
    try:
        dpi = resolve_dpi(map_path, user_dpi=body.dpi)
        mpp = _resolve_mpp(dpi, body.scale, body.calibrate)
    except (ValueError, OSError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    job_id = _create_job(run_id, "segment")
    background_tasks.add_task(_segment_worker, job_id, run_dir, map_path, dpi, mpp, body.page)
    return {"job_id": job_id}


@app.post("/api/runs/{run_id}/detect", status_code=status.HTTP_202_ACCEPTED)
def start_detect(run_id: str, background_tasks: BackgroundTasks) -> dict[str, str]:
    run_dir = _require_run(run_id)
    map_path = _map_path(run_dir)
    dpi = _read_run_state(run_dir)
    if dpi is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "run segment first (no scale/dpi resolved for this run yet)",
        )

    job_id = _create_job(run_id, "detect")
    background_tasks.add_task(_detect_worker, job_id, run_dir, map_path, dpi)
    return {"job_id": job_id}


@app.get("/api/runs/{run_id}/controls", response_model=list[Control])
def get_controls(run_id: str) -> list[Control]:
    run_dir = _require_run(run_id)
    path = run_dir / "controls.csv"
    if not path.is_file():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "no controls yet for this run -- run detect first"
        )
    return read_controls(path)


@app.put("/api/runs/{run_id}/controls", response_model=list[Control])
def put_controls(run_id: str, controls: list[Control]) -> list[Control]:
    """Persist hand-edited controls (SPEC F9's CSV round trip). Validated by writing to a
    scratch file and reading it back through `read_controls` -- the one place the hub/id
    invariants are enforced -- so an invalid edit (no hub, duplicate ids, ...) 400s without
    touching the run's current `controls.csv`.
    """
    run_dir = _require_run(run_id)
    tmp_path = run_dir / "controls.csv.tmp"
    write_controls(tmp_path, controls)
    try:
        validated = read_controls(tmp_path)
    except ValueError as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    tmp_path.replace(run_dir / "controls.csv")
    return validated


@app.post("/api/runs/{run_id}/plan", status_code=status.HTTP_202_ACCEPTED)
def start_plan(
    run_id: str, run_config: RunConfig, background_tasks: BackgroundTasks
) -> dict[str, str]:
    run_dir = _require_run(run_id)
    map_path = _map_path(run_dir)
    dpi = _read_run_state(run_dir)
    if dpi is None or not (run_dir / "terrain.npz").is_file():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "run segment first (no terrain for this run yet)"
        )
    if not (run_dir / "controls.csv").is_file():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "no controls for this run yet -- run detect or PUT controls first",
        )

    job_id = _create_job(run_id, "plan")
    background_tasks.add_task(_plan_worker, job_id, run_dir, map_path, dpi, run_config)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}", response_model=JobStatusOut)
def get_job(job_id: str) -> JobStatusOut:
    with _jobs_lock:
        record = _jobs.get(job_id)
        if record is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown job id {job_id!r}")
        return JobStatusOut(
            job_id=record.job_id,
            run_id=record.run_id,
            kind=record.kind,
            status=record.status,
            result=record.result,
            error=record.error,
        )


#: export artifact name -> (filename in the run dir, media type).
_EXPORTS: dict[str, tuple[str, str]] = {
    "route.json": ("route.json", "application/json"),
    "route.png": ("route.png", "image/png"),
    "controls.csv": ("controls.csv", "text/csv"),
}


@app.get("/api/runs/{run_id}/export/{artifact}")
def export_artifact(run_id: str, artifact: str) -> FileResponse:
    run_dir = _require_run(run_id)
    if artifact not in _EXPORTS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown export artifact {artifact!r}")
    filename, media_type = _EXPORTS[artifact]
    path = run_dir / filename
    if not path.is_file():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"{artifact} does not exist yet for this run"
        )
    return FileResponse(path, media_type=media_type, filename=filename)
