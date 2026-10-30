# Interactive density map

`scripts/build_interactive_map.py` produces a standalone HTML file — open it
in any browser, no server needed — showing Customer Potential results as
H3 hexagon density, at 3 selectable resolutions (7/8/9). Same visual system
as the rest of the skill (dark, IBM Plex Mono/Sans, E5FF01 accent).

## Why hexagons only, no points or polygons

This mirrors Kin's Prospección map in structure and feel, but with one
deliberate difference: **the output HTML never contains a single raw PDV
coordinate.** Prospección's map ships raw lat/long points to the browser
and bins them into hexagons with client-side JS, which is fine when the
data isn't confidential. Customer Potential results are, so the binning
happens once, offline, in this script — the HTML only ever gets hexagon
boundaries (a fixed function of the H3 grid, not of any specific PDV) and
aggregated statistics per hexagon. Do not add a points or polygons layer to
this map without re-checking that requirement with whoever owns the data.

**If you're ever unsure whether a change leaks something it shouldn't:**
grep the generated HTML for a handful of exact (lat, lng) pairs from the
source CSV, at full precision, checked *as an adjacent pair* — not just
whether either number appears somewhere (rounded hex boundary vertices
will legitimately share short numeric prefixes with nearby real points;
that's not a leak, only an exact adjacent pair would be).

## What it needs beyond the standard CSV schema

Everything in `references/csv-schema.md`, plus:

| Role | Default column | Required? |
|---|---|---|
| `latitude` | `Latitude` | Yes — this is the whole point of the map |
| `longitude` | `Longitude` | Yes |
| `gec` | `GEC` | Optional — only needed if you want the GEC filter; falls back to "N/D" if absent |

Override any of these the same way as the main schema — via `--mapping`.
Rows with missing/invalid lat or long are silently dropped from the map
(the script prints how many); everything else still gets the standard
16-slide deck normally.

## Usage

Needs the `h3` Python package (H3 v4 API); install it first if it's not
already there: `pip install h3 --break-system-packages`.

```
python scripts/build_interactive_map.py --csv data.csv --manual-inputs manual_inputs.json \
    [--mapping mapping.json] --resolutions 7,8,9 --out <Bottler>_Mapa_Interactivo.html
```

Offer to build this whenever the CSV has coordinates — it's a natural
companion to the deck, and a good replacement for slide 14's "paste a
screenshot" placeholder (tell whoever's presenting to open the HTML file
live during the meeting instead, or link to it from the deck).

## What's in it

- **Ver por**: toggle between coloring hexagons by client density (count)
  or by growth-potential density (summed UC).
- **Tamaño de hexágono**: switch between H3 resolutions 7 (coarser, city-
  level) / 8 / 9 (finer, neighborhood-level).
- **Filtros**: Segmento (VH/H/M/L, multi-select), Categoría prioritaria,
  Ciudad, Subcanal, GEC — all combinable.
- **Hover tooltip**: PDV count, VH/H/M/L breakdown, potencial UC/mes, %
  of the operation's total potential, and current sales (ventas
  actuales) — all for that hexagon under the active filters.
- **Color-scale editor**: a histogram of the hexes currently on screen, with
  the bucket cutoffs shown as draggable markers on it (plus exact numeric
  inputs below for typing a value directly). The min/max labels at each end
  are the dataset-wide range for whichever mode is active — they never shift
  as you drag, so adjusting one cutoff doesn't visually move the others (an
  earlier version rescaled each slider's range from the current cutoffs,
  which felt like everything was moving at once). Reset button restores the
  computed quantile defaults.

## Basemap (user, 2026-10-27)

- **OpenFreeMap** (`https://tiles.openfreemap.org/styles/positron`): OpenStreetMap vector tiles, free, no
  API key, no account, no quota. No Mapbox, CARTO or any keyed service — CARTO now needs a key, Mapbox
  needed a personal token embedded in the HTML, and OSM's raster tile server forbids this usage pattern.
- Drawn by MapLibre GL inside Leaflet (`maplibre-gl@4.7.1` + `@maplibre/maplibre-gl-leaflet@0.1.3`, from
  unpkg), so hexagons, tooltips and controls stay plain Leaflet. The GL layer must be added **after** the
  first `fitBounds`/`setView` (it reads `map.getCenter()` when added; before that it throws `Invalid
  LatLng (NaN, NaN)` and the map stays blank).
- The ODbL attribution (OpenFreeMap · OpenMapTiles · OpenStreetMap) must stay visible: don't hide
  `.leaflet-control-attribution` again.
- Needs internet when the HTML is opened (the hexes and data are embedded; only the basemap is remote).
- Screenshot for the deck (paso 3, `capturar_mapa`): Edge headless driven over CDP with real waiting until
  `areTilesLoaded()`; `--virtual-time-budget` doesn't wait for vector tiles and left the basemap empty.
  WebGL by software (`--use-angle=swiftshader --enable-unsafe-swiftshader`), `preserveDrawingBuffer: true`.

## Known limitations

- No visual QA was done in a real browser while building this (the sandbox
  this skill was developed in has no network access to download a headless
  browser). The data pipeline and the core filtering/aggregation logic were
  verified directly (unit-tested the JS aggregation against the Python
  totals, checked for coordinate leaks, syntax-checked the script) but
  actually opening it and clicking around hasn't been done by a human yet.
  Do that before sending it to a client the first few times.
- Resolution is capped at the 3 precomputed values (7/8/9) — adding a 4th
  means re-running the script with `--resolutions`, not a live in-browser
  option, since resolution changes require re-aggregating offline (see the
  privacy note above for why).
- Very long city/subchannel/category names can wrap awkwardly in the
  narrow sidebar dropdown rows; no automatic truncation is applied yet.
