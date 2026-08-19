"""Render an OCAD map to a raster plus per-terrain-class ground-truth masks (spike T006).

Runs on the *host*, not in the image: it drives OpenOrienteering Mapper's console binary, a Qt
desktop application that has no business in a test container. See ``tools/ocd_render.md`` for the
route, its known failure modes, and where to install Mapper.

    python tools/ocd_render.py data/maps/ivanovo/map.ocd --dpi 300

Writes ``map.png`` and ``mask_<class>.png`` next to the input.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rogaine.config import load_config
from rogaine.models import TerrainClass

#: Mapper's console binary. Named differently per platform; the first one found wins.
CONSOLE_NAMES = ("mapper-console", "Mapper", "OpenOrienteering-Mapper")


def find_mapper(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise SystemExit(f"--mapper {path} does not exist")
        return path
    for name in CONSOLE_NAMES:
        found = shutil.which(name)
        if found:
            return Path(found)
    raise SystemExit(
        "OpenOrienteering Mapper was not found on PATH. Install it (see tools/ocd_render.md) "
        "or pass --mapper with the full path to its console binary."
    )


def symbol_codes_by_class() -> dict[TerrainClass, tuple[str, ...]]:
    """ISOM symbol codes per terrain class, read out of ``config/default.toml``.

    The config states the mapping once, as ``isom = "502,503"``; this reads it backwards so the
    spike and the classifier can never drift apart.
    """
    mapping: dict[TerrainClass, tuple[str, ...]] = {}
    for spec in load_config().terrain:
        codes = tuple(c.strip() for c in spec.isom.split(",") if c.strip())
        if codes:
            mapping[spec.name] = codes
    return mapping


def export_raster(mapper: Path, source: Path, target: Path, dpi: int) -> None:
    cmd = [str(mapper), "--export-raster", "--dpi", str(dpi), str(source), str(target)]
    print(" ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(
            f"Mapper failed ({result.returncode}).\n"
            f"stdout: {result.stdout.strip()}\nstderr: {result.stderr.strip()}\n"
            "If the message mentions the file version, see the failure table in "
            "tools/ocd_render.md."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ocd", type=Path, help="the .ocd file to render")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--mapper", default=None, help="path to Mapper's console binary")
    parser.add_argument(
        "--masks",
        action="store_true",
        help="also export one mask per terrain class (slow: one Mapper run per class)",
    )
    args = parser.parse_args(argv)

    if not args.ocd.is_file():
        raise SystemExit(f"{args.ocd} does not exist")

    mapper = find_mapper(args.mapper)
    out_dir = args.ocd.parent
    export_raster(mapper, args.ocd, out_dir / "map.png", args.dpi)
    print(f"wrote {out_dir / 'map.png'}")

    if args.masks:
        # Mapper has no symbol filter on the command line, so this needs a per-class copy of the
        # map with the other symbols hidden. Left unimplemented until a real .ocd file exists to
        # test it against — writing it blind would be writing fiction.
        codes = symbol_codes_by_class()
        print("\nSymbol codes that would be exported, per class:")
        for cls, cc in codes.items():
            print(f"  {cls.value:20s} {', '.join(cc)}")
        print(
            "\nMask export is not implemented yet: it needs a real .ocd file to develop against "
            "(see tools/ocd_render.md, 'Findings')."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
