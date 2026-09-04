# Map corpus

Nothing under `data/maps/` is committed — `.gitignore` excludes the rasters, the `.ocd` files and
the sidecars. This file is the contract the loader reads, so a map dropped here is usable without
anyone remembering how it was set up (ADR-010, T005).

## Layout

```
data/maps/
  <map-id>/
    map.png            # or .jpg .tif .pdf .ocd — one raster or source file per directory
    meta.toml          # required: scale and DPI. Everything else is optional.
    controls.csv       # optional: the true control positions and points
    reference.json     # optional: a route a human actually ran, for M4 acceptance
```

`<map-id>` is a slug: lowercase, digits, hyphens. It is what the CLI and the run log call the map,
so keep it stable once a reference route exists for it.

## `meta.toml`

```toml
name = "Ivanovskoe rogaine 2024"     # optional, for display
scale_denominator = 30000            # required — 1:30000
dpi = 300                            # required for scans; a PDF that carries its own DPI may omit it
# Both optional, top-level keys (NOT inside [calibration] below -- a key nested in that table
# parses as calibration.calibration_source, invisible to the loader's own top-level lookup).
# Written by the M7 corpus auto-calibrator (T078, ADR-016), absent on a hand-authored meta.toml.
# Purely informational: nothing in the loader reads either, downstream relief/terrain work will.
calibration_source = "measured"      # "measured" or "assumed_default"
calibration_tier = "grid"            # "scale_bar", "grid" or "circle" -- "measured" only
[calibration]                        # optional; overrides scale_denominator/dpi if present
# Two points on the map and the true ground distance between them (SPEC F3). Use this when the
# scan was cropped or resampled and the nominal DPI no longer describes the file.
x1 = 412
y1 = 1880
x2 = 1206
y2 = 1880
meters = 1000
```

Scale and DPI are what turn pixels into metres (`mpp = (25.4 / dpi) * scale / 1000`, SPEC F2). A
map with the wrong DPI does not fail — it silently plans a route for the wrong-sized area. The
loader therefore refuses a map whose `meta.toml` gives neither the pair nor a calibration line.

## `controls.csv`

Header required, one row per control, coordinates in **pixels of the raster in this directory**:

```csv
id,x,y,number,points,is_hub
0,1600,1200,,0,true
1,842,410,73,7,false
2,2150,980,45,4,false
```

- `is_hub` marks the start/finish. Exactly one row must set it (SPEC F14).
- `points` may be blank; then the `[detector].points_rule` in the config decides (`first_digit` by
  default, so control 73 is worth 7).
- Present, this file **replaces** detection. Absent, T020 detects and the viewer is where the
  owner corrects the result.

## `reference.json`

A route someone actually ran, used to answer "is our route as good as the article's" with a number
instead of an impression:

```json
{
  "time_limit_s": 14400,
  "base_speed_mps": 2.6,
  "order": [0, 3, 7, 12, 4, 0],
  "achieved_points": 38,
  "achieved_seconds": 14210,
  "note": "winning team, 4h rogaine, 2024-05-18"
}
```

The planner is run with the same `time_limit_s` and `base_speed_mps` and the two scores are
compared. `order` is optional — without it only the score comparison is possible, which is still
the comparison that matters.

## What each kind of file buys us

| File | Retires |
| --- | --- |
| `.ocd` source | The palette's ground truth: OCAD symbol codes give exact per-pixel classes without hand-labelling (T006). |
| `reference.json` | The acceptance question. One is enough to stop arguing about route quality. |
| 10-20 scans | The palette risk: whether one fixed shade table survives real printers and scanners, or T013 has to fit per map. |
| 200+ scans | Only M7 — training the optional SegFormer. Not needed for the CLI to work. |

## Loading

```
rogaine corpus list          # every map, its scale, and what metadata it is missing
rogaine corpus check <id>    # one map, verbosely
```

`corpus list` never fails on a bad entry: it reports what is missing per map, because a half-set-up
corpus is the normal state while files are still arriving.
