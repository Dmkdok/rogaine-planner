# Spike T006 — `.ocd` to raster and per-class masks

**Status: route documented and scripted, not yet executed** — no `.ocd` file has reached
`data/maps/` at the time of writing. Timeboxed by design: if the export turns out not to work on
the owner's files, M1 proceeds on the synthetic fixture alone (T004) and this task is closed with
the finding recorded here. It never blocks M1.

## Why bother

The palette classifier (T013) is measured by per-class IoU. On the synthetic fixture the truth is
known because we drew it. On a real scan nobody knows the truth without hand-labelling, which is
the cost ADR-001 exists to avoid. An `.ocd` file is the exception: it is a *vector* map where every
object carries its ISOM symbol number. Rendering the same file twice — once in full colour, once
with a single symbol class visible — produces a raster and its exact mask, for free, at any DPI.

That makes one `.ocd` worth more for validation than fifty scans, and it is the only path to a
labelled dataset large enough for the optional SegFormer in M7 (ADR-010).

## The route

OCAD's own command line is Windows-only and licence-gated. OpenOrienteering Mapper reads `.ocd`
(versions 6-12) and ships a CLI, so that is the primary path.

```
mapper-console --export-raster --dpi 300 map.ocd map.png
```

Per-class masks come from exporting repeatedly with a symbol filter. Mapper has no
`--only-symbols` flag, so the filter is applied to a copy of the map file: load, hide every symbol
whose code is not in the wanted set, export, repeat. `ocd_render.py` drives that loop.

Symbol codes are ISOM 2017-2 codes with a decimal suffix (`405.0` is runnable forest), which is why
`config/default.toml` carries an `isom` field per terrain class — the mapping from symbol code to
`TerrainClass` is that field read backwards.

### Where it can fail

| Failure | What we do |
| --- | --- |
| Mapper cannot open the file (OCAD 2018+, version 13+) | Ask the owner to "save as" OCAD 11 from OCAD itself, or export the raster from OCAD directly and drop the mask half. |
| Mapper's CLI has no raster export in the installed build | Use the GUI once per map by hand; 2 files is tolerable, 200 is not. |
| Symbols are custom, not ISOM codes | Record the observed codes here and map them by hand — a rogaine map with local conventions is still worth one table. |
| Anti-aliased export blurs mask edges | Export masks with anti-aliasing off; the raster keeps it, the mask must not. |

## Installing Mapper

Not in the image: it is a Qt desktop application, ~200 MB, needed twice per corpus rather than on
every test run. Install it on the host —
<https://www.openorienteering.org/apps/mapper/> — and run `ocd_render.py` there. The outputs
(`map.png` and `mask_*.png`) go into the map's directory under `data/maps/` and everything
downstream reads those, never the `.ocd`.

## Findings

_(To be filled in when the owner's `.ocd` files arrive. Record: Mapper version, OCAD file version,
whether raster export worked, whether symbol hiding worked, the observed symbol codes, and the
per-class pixel counts of the first mask set.)_
