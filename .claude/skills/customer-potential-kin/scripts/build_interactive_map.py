#!/usr/bin/env python3
"""
Builds a self-contained interactive HTML map of Customer Potential results,
aggregated into H3 hexagons at 3 selectable resolutions (7/8/9).

PRIVACY, BY CONSTRUCTION: this script needs exact lat/long per PDV to bin
them into hexagons, but the output HTML never contains a single raw
coordinate or per-PDV row. Only hexagon boundaries and hex-level aggregates
(counts, sums, breakdowns by segment/city/subchannel/category/GEC) get
embedded. Do not change this script to also emit a "points" layer or any
per-PDV latitude/longitude into the HTML -- that defeats the reason this
exists instead of just reusing a generic point-map template.

Why hex-level aggregation instead of client-side binning: a fully generic
map would ship raw points to the browser and bin them into hexagons with a
JS H3 library, so resolution could change on the fly. That's what Kin's
Prospección map does. This one can't work that way, because shipping raw
points is exactly what confidentiality rules out here. So the binning has
to happen once, offline, in this script, for every resolution the user
might want to look at (7, 8, 9) -- the trade-off is a slightly bigger file
and no on-the-fly resolution beyond those three, in exchange for the HTML
never holding a single exact PDV location.

Filtering (by segment, city, subchannel, priority category, GEC) still
needs to work in the browser without raw points. The trick: aggregate to
sparse (hex, segment, city, subchannel, category, GEC) tuples -- one row
per *combination that actually occurs*, each carrying a count and potential/
current UC sum -- rather than one row per hex. The browser sums the
matching rows for whichever filters are active. A hex only reveals
distribution statistics, never an individual PDV.

Usage:
    python build_interactive_map.py --csv data.csv --manual-inputs manual_inputs.json \
        [--mapping mapping.json] --resolutions 7,8,9 --out map.html
"""
import argparse
import json
import sys
from pathlib import Path

import h3
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_content import (  # noqa: E402  (reuse the same CSV mapping/normalization logic)
    DEFAULT_MAPPING, STANDARD_CATEGORIES, resolve_mapping, detect_mapping, normalize_segment,
    normalize_growth,
)

SEGMENT_ORDER = ["Very High", "High", "Moderate", "Low"]
DEFAULT_RESOLUTIONS = [7, 8, 9]


def require_map_columns(df, mapping):
    missing = []
    for role in ["client_id", "city", "subchannel", "current_uc", "potential_uc", "segment", "latitude", "longitude"]:
        col = mapping.get(role)
        if not col or col not in df.columns:
            missing.append(f"{role} (expected column '{col}')")
    if missing:
        sys.exit(
            "build_interactive_map.py: CSV is missing required columns for the map:\n  - "
            + "\n  - ".join(missing)
            + "\n\nThe map needs latitude/longitude per PDV in addition to everything "
              "generate_content.py needs (see references/csv-schema.md and "
              "references/interactive-map.md). Pass --mapping to point at the right columns."
        )


def build_lookup_index(values):
    """Stable list of unique values + a dict to look up each value's index."""
    uniq = sorted(set(str(v) for v in values))
    return uniq, {v: i for i, v in enumerate(uniq)}


def priority_category_per_row(df, mapping):
    """Same logic as generate_content.py's action-plan rows: whichever of the
    6 standard categories has the most potential for that specific PDV."""
    best_cat = pd.Series([None] * len(df), index=df.index, dtype=object)
    best_val = pd.Series([float("-inf")] * len(df), index=df.index)
    for key, label in STANDARD_CATEGORIES:
        cols = mapping["categories"].get(key)
        if not cols or cols["potential"] not in df.columns:
            continue
        v = pd.to_numeric(df[cols["potential"]], errors="coerce").fillna(0)
        better = v > best_val
        best_val[better] = v[better]
        best_cat[better] = label
    return best_cat.fillna("Sin categoría")


def aggregate_for_resolution(df, res, seg_idx, city_idx, sub_idx, cat_idx, gec_idx):
    df = df.copy()
    df["_hex"] = [h3.latlng_to_cell(lat, lng, res) for lat, lng in zip(df["_lat"], df["_lng"])]

    hex_ids = sorted(df["_hex"].unique())
    hex_index = {h: i for i, h in enumerate(hex_ids)}
    hex_polys = [[[round(lat, 5), round(lng, 5)] for lat, lng in h3.cell_to_boundary(h)] for h in hex_ids]

    group_cols = ["_hex", "_seg", "_city", "_sub", "_cat", "_gec"]
    grouped = df.groupby(group_cols, dropna=False).agg(
        n=("_potential", "size"), pot=("_potential", "sum"), cur=("_current", "sum"),
    ).reset_index()

    facts = {
        "hex": [hex_index[h] for h in grouped["_hex"]],
        "seg": [seg_idx[v] for v in grouped["_seg"]],
        "city": [city_idx[v] for v in grouped["_city"]],
        "sub": [sub_idx[v] for v in grouped["_sub"]],
        "cat": [cat_idx[v] for v in grouped["_cat"]],
        "gec": [gec_idx[v] for v in grouped["_gec"]],
        "n": grouped["n"].astype(int).tolist(),
        "pot": [round(float(x), 1) for x in grouped["pot"]],
        "cur": [round(float(x), 1) for x in grouped["cur"]],
    }

    # Default color-scale breaks (quantiles of each hex's UNFILTERED total) - the
    # browser lets the user drag these, this just picks a sane starting point.
    hex_totals_n = grouped.groupby("_hex")["n"].sum()
    hex_totals_pot = grouped.groupby("_hex")["pot"].sum()

    def quantile_breaks(series, n_buckets=5):
        if series.empty:
            return [1] * (n_buckets - 1)
        qs = [series.quantile(q) for q in [0.2, 0.4, 0.6, 0.8]]
        breaks, last = [], 0
        for q in qs:
            v = max(round(q), last + 1)
            breaks.append(v)
            last = v
        return breaks

    default_breaks = {
        "n": quantile_breaks(hex_totals_n),
        "pot": [round(b, 1) for b in quantile_breaks(hex_totals_pot)],
    }
    return {"ids": hex_ids, "polys": hex_polys, "defaultBreaks": default_breaks}, facts


def build(df, mapping, manual, resolutions):
    df = df.copy()
    df["_seg"] = df[mapping["segment"]].map(normalize_segment).astype(str)
    df["_current"] = pd.to_numeric(df[mapping["current_uc"]], errors="coerce").fillna(0)
    df["_potential"] = pd.to_numeric(df[mapping["potential_uc"]], errors="coerce").fillna(0)
    df["_city"] = df[mapping["city"]].astype(str)
    df["_sub"] = df[mapping["subchannel"]].astype(str)
    df["_cat"] = priority_category_per_row(df, mapping).astype(str)
    gec_col = mapping.get("gec")
    df["_gec"] = df[gec_col].astype(str) if gec_col and gec_col in df.columns else "N/D"
    df["_lat"] = pd.to_numeric(df[mapping["latitude"]], errors="coerce")
    df["_lng"] = pd.to_numeric(df[mapping["longitude"]], errors="coerce")

    n_before = len(df)
    df = df.dropna(subset=["_lat", "_lng"])
    n_dropped = n_before - len(df)
    # PDVs with no priority level (no potential computed, e.g. no sales) can't go in any of the 4
    # segment buckets the template hard-codes: leave them out of the map and report how many
    sin_seg = ~df["_seg"].isin(SEGMENT_ORDER)
    n_sin_segmento = int(sin_seg.sum())
    df = df[~sin_seg]

    cities, city_idx = build_lookup_index(df["_city"])
    subs, sub_idx = build_lookup_index(df["_sub"])
    cats, cat_idx = build_lookup_index(df["_cat"])
    gecs, gec_idx = build_lookup_index(df["_gec"])
    seg_idx = {s: i for i, s in enumerate(SEGMENT_ORDER)}

    hexes, facts = {}, {}
    for res in resolutions:
        h, f = aggregate_for_resolution(df, res, seg_idx, city_idx, sub_idx, cat_idx, gec_idx)
        hexes[str(res)] = h
        facts[str(res)] = f

    return {
        "resolutions": resolutions,
        "hexes": hexes,
        "facts": facts,
        "lookups": {"segments": SEGMENT_ORDER, "cities": cities, "subchannels": subs, "categories": cats, "gec": gecs},
        "totals": {
            "pdvs": int(len(df)),
            "potential": round(float(df["_potential"].sum()), 1),
            "current": round(float(df["_current"].sum()), 1),
            "dropped_no_coords": int(n_dropped),
            "dropped_no_segment": n_sin_segmento,
        },
        "meta": {
            "embotelladora": manual.get("embotelladora", ""),
            "mes_anio": manual.get("mes_anio", ""),
        },
    }


def render_html(map_data, title):
    template_path = Path(__file__).resolve().parent.parent / "assets" / "interactive_map_template.html"
    template = template_path.read_text(encoding="utf-8")
    payload = json.dumps(map_data, ensure_ascii=False, separators=(",", ":"))
    html = template.replace("__MAP_TITLE__", title).replace("__MAP_DATA_JSON__", payload)
    return html


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--manual-inputs", required=True)
    ap.add_argument("--mapping", default=None)
    ap.add_argument("--resolutions", default="7,8,9")
    ap.add_argument("--out", default="interactive_map.html")
    args = ap.parse_args()

    manual = json.loads(Path(args.manual_inputs).read_text(encoding="utf-8"))
    df = pd.read_csv(args.csv)

    if args.mapping:
        mapping = resolve_mapping(args.mapping)  # explicit --mapping always wins
    else:
        mapping = detect_mapping(df, manual) or resolve_mapping(None)
    # lat/long/gec aren't part of generate_content.py's role set (detect_mapping
    # already fills latitude/longitude when it finds a match; gec is map-only
    # and has no equivalent in the standard/business_english conventions yet)
    mapping.setdefault("latitude", "Latitude")
    mapping.setdefault("longitude", "Longitude")
    # GEC: "GEC" or, in the model output, size_class_internal (Andina AR) / size_class (Femsa VE)
    mapping.setdefault("gec", next((c for c in ("GEC", "size_class_internal", "size_class") if c in df.columns), "GEC"))
    if args.mapping:
        override = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
        for key in ("latitude", "longitude", "gec"):
            if key in override:
                mapping[key] = override[key]

    resolutions = [int(r) for r in args.resolutions.split(",")]

    require_map_columns(df, mapping)

    map_data = build(df, mapping, manual, resolutions)
    if map_data["totals"]["dropped_no_coords"]:
        print(f"Warning: {map_data['totals']['dropped_no_coords']} rows had no valid lat/long and were excluded from the map.")
    if map_data["totals"]["dropped_no_segment"]:
        print(f"Warning: {map_data['totals']['dropped_no_segment']} rows had no priority level (no potential) "
              "and were excluded from the map.")

    title = f"Customer Potential — {manual.get('embotelladora','')}"
    html = render_html(map_data, title)
    Path(args.out).write_text(html, encoding="utf-8")
    print(f"Wrote {args.out} ({len(html)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
