"""Controls CSV round-trip (T022, SPEC F9).

"Round-trip is lossless; a hand-edited CSV overrides detection entirely" (SPEC F9). This module is
the single canonical home for that read *and* write — `vision/controls.py` (T020) and
`vision/ocr.py` (T021) produce `Control` objects, this module is where they meet disk.

**Reconciling the DoD's column list with what round-tripping actually requires.** SPEC F9 and this
task's own DoD both write the header as `id,x,y,number,points,confidence`. Read literally, that
loses two fields on a real write-then-read cycle:

- `is_hub` is not optional decoration — the `Control` model and everything downstream (SPEC F14,
  `vision/controls.py`, the future solver) require exactly one hub, sorted first. A CSV that cannot
  say which row is the hub cannot represent a `Control` list at all, hand-edited or not.
- `source` (`"detected"` vs `"manual"`) is listed as a full `Control` field in SPEC's own
  "Content / data model" section, on equal footing with `confidence` — not an internal-only
  bookkeeping flag. Dropping it on read-back would silently turn a re-loaded *detected* control
  indistinguishable from a hand-typed one, which is exactly the kind of information loss "lossless"
  rules out.

So the real, written column set is `id,x,y,number,points,confidence,source,is_hub` — the DoD's six
columns first, in the DoD's own order, with the two structurally-required columns appended rather
than interleaved, so a CSV built from the DoD's literal example is a strict prefix of what this
module writes.

T114/ADR-039/F23 appends a ninth column, `number_source` (`"tesseract"`/`"vlm"`, blank for a still-
unread number or the hub) — the same auditability requirement as `source` above: F23 requires a
VLM-resolved number to stay "marked distinctly ... so a human reviewing the output can see which
numbers were VLM-assisted", and that marking is only real if it survives export, not just the
in-memory `Control`. Appended last for the same strict-prefix reason `is_hub` was.

`confidence` itself is the other half of the discrepancy: T005's original `read_controls` (moved
here from `io/corpus.py`) hardcoded every parsed row's `confidence` to `1.0` and `source` to
`"manual"`, because at the time nothing produced any other value. T020's Hough ring-coverage score
and T021's `min(detection, ocr)` combination now do, and a route exported and re-imported must keep
that number rather than silently resetting it to `1.0` — so this module reads and writes the real
value.

**Hand-editing stays ergonomic.** `number`, `points`, `confidence`, `source`, `is_hub` and
`number_source` all default when their cell — or the whole column — is blank: `number`/`points` to
`None` (the existing convention: blank means "let the config's points rule decide"), `confidence`
to `1.0`, `source` to `"manual"` (the same values the old hardcoded behaviour always produced, so a
bare `id,x,y,number,points,is_hub` file — `data/README.md`'s documented example — still reads
exactly as it always has), and `number_source` to `None` (a hand-typed number has no OCR
provenance at all — neither Tesseract's nor the VLM fallback's). `id`, `x` and `y` are not
defaulted: a control with no position is not a control, and a missing or malformed one of those
three raises with the offending line number, same as any other malformed row.

Malformed rows (a non-numeric field, an out-of-range `confidence`, an invalid `source`, a missing
`id`/`x`/`y` column) raise `ValueError(f"{csv_path} line {N}: ...")`, matching the convention
`io/corpus.py` already established. List-level problems — zero or more than one `is_hub` row,
duplicate ids — raise without a line number, since they are not about any single row.
"""

from __future__ import annotations

import csv
from pathlib import Path

from rogaine.models import Control

#: Header written to disk and accepted on read. The DoD's own six columns, in the DoD's own order,
#: plus the two this module's docstring explains are structurally required for a lossless round
#: trip, plus `number_source` (T114/ADR-039/F23's auditability column).
FIELDNAMES: tuple[str, ...] = (
    "id",
    "x",
    "y",
    "number",
    "points",
    "confidence",
    "source",
    "is_hub",
    "number_source",
)


def read_controls(csv_path: Path) -> list[Control]:
    """Load a controls CSV. Raises — a controls file that is present must be correct (SPEC F9)."""
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"{csv_path} has a header but no controls")

    controls: list[Control] = []
    for line, row in enumerate(rows, start=2):
        try:
            number = int(row["number"]) if (row.get("number") or "").strip() else None
            points = int(row["points"]) if (row.get("points") or "").strip() else None
            raw_confidence = (row.get("confidence") or "").strip()
            confidence = float(raw_confidence) if raw_confidence else 1.0
            raw_source = (row.get("source") or "").strip().lower()
            raw_number_source = (row.get("number_source") or "").strip().lower()
            controls.append(
                Control(
                    id=int(row["id"]),
                    x=float(row["x"]),
                    y=float(row["y"]),
                    number=number,
                    points=points,
                    confidence=confidence,
                    source=raw_source or "manual",
                    is_hub=(row.get("is_hub") or "").strip().lower() in {"true", "1", "yes"},
                    number_source=raw_number_source or None,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{csv_path} line {line}: {exc}") from exc

    hubs = [c for c in controls if c.is_hub]
    if len(hubs) != 1:
        raise ValueError(f"{csv_path}: exactly one row must set is_hub, found {len(hubs)}")
    ids = [c.id for c in controls]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{csv_path}: control ids are not unique")
    # The hub is index 0 everywhere downstream (SPEC F14), so put it there once, here.
    controls.sort(key=lambda c: (not c.is_hub, c.id))
    return controls


def write_controls(csv_path: Path, controls: list[Control]) -> None:
    """Write a controls CSV. A dumb serialiser — `read_controls` above is the one place that
    validates the hub/id invariants, so a round trip through this pair is the real test, not a
    guarantee this function enforces on its own.
    """
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for control in controls:
            writer.writerow(
                {
                    "id": control.id,
                    "x": control.x,
                    "y": control.y,
                    "number": control.number,
                    "points": control.points,
                    "confidence": control.confidence,
                    "source": control.source,
                    "is_hub": "true" if control.is_hub else "false",
                    "number_source": control.number_source or "",
                }
            )
