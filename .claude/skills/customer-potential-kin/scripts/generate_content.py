#!/usr/bin/env python3
"""
Reads a Customer Potential model output CSV + a small set of manual inputs
(operation name, dates, run type) and produces content.json: every number
and every sentence needed to fill slides 9-13 and 15 of the Kin Analytics
Customer Potential Results template.

Why this exists: the template's narrative slides (S10, S12, S13, S15) are
all fill-in-the-blank patterns around the numbers ("El X% de los clientes
concentra el Y% de la oportunidad", "A + B en {subcanal} captura el Z%...").
There is no free creative writing needed here -- getting the numbers right
and slotting them into the known sentence patterns is the whole job. Keeping
that logic in one deterministic script means the same CSV always produces
the same deck, and a human (or Claude) can sanity-check the numbers in one
place (content.json) before anything gets near the pptx.

Usage:
    python generate_content.py --csv data.csv --manual-inputs manual.json \
        [--mapping mapping.json] --out content.json

See references/csv-schema.md for the expected CSV columns and the mapping
override mechanism.
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

STANDARD_CATEGORIES = [
    ("multi_serve", "Multi Serve"),
    ("coca_cola", "Coca Cola"),
    ("single_serve", "Single Serve"),
    ("hydration", "Hydration"),
    ("nutrition", "Nutrition"),
    ("sparkling", "Sparkling Flavors"),
]

SEGMENT_ORDER = ["Very High", "High", "Moderate", "Low"]

SEGMENT_ALIASES = {
    "vh": "Very High", "very high": "Very High", "veryhigh": "Very High",
    "h": "High", "high": "High",
    "m": "Moderate", "moderate": "Moderate", "med": "Moderate",
    "l": "Low", "low": "Low",
}

DEFAULT_MAPPING = {
    "client_id": "ClientID",
    "city": "Ciudad",
    "subchannel": "Subcanal",
    "current_uc": "PotentialQuantitative",
    "potential_uc": "PotentialQuantitativeFinal",
    "growth_pct": "PotentialEstimatedToCover",
    "segment": "PotentialQualitative",
    "mirror_client_id": "Comparative_Client_ID",
    "categories": {
        "multi_serve": {"potential": "ServingType_MultiServe_Potential", "current": "ServingType_MultiServe_Current"},
        "coca_cola": {"potential": "GlobalCat_CocaCola_Potential", "current": "GlobalCat_CocaCola_Current"},
        "single_serve": {"potential": "ServingType_SingleServe_Potential", "current": "ServingType_SingleServe_Current"},
        "hydration": {"potential": "GlobalCat_HydratationSports&Tea_Potential", "current": "GlobalCat_HydratationSports&Tea_Current"},
        "nutrition": {"potential": "GlobalCat_NutritionJuiceDairy&Plant_Potential", "current": "GlobalCat_NutritionJuiceDairy&Plant_Current"},
        "sparkling": {"potential": "GlobalCat_SparklingFlavors_Potential", "current": "GlobalCat_SparklingFlavors_Current"},
    },
}

REQUIRED_MANUAL_FIELDS = [
    "embotelladora", "mes_anio", "tipo_corrida", "cantidad_registros",
    "fecha_clientes", "origen_clientes", "corte_ventas", "fecha_altscore",
]

# Known column-naming conventions seen across bottlers so far. Every CSV we've
# gotten uses pos_id / pos_city / pos_subchannel / pos_latitude / pos_longitude
# for identity/location (that part hasn't varied), and always suffixes the
# per-role columns with "_TotalPortafolio" for the base 8 roles, or
# "_GlobalCat_X" / "_ServingType_X" / "_CustomCat_<name>" for categories --
# only the ROLE PREFIX itself differs between bottlers' exports.
#
# "business_english" was confirmed from an upstream rename snippet (Nico's
# pipeline) that converts "standard" column names into this convention for
# specific bottlers (first seen: Brasal Brasil) -- it also strips '&' from
# the two category suffixes that contain one, so those are spelled
# differently here than in "standard".
NAMING_CONVENTIONS = [
    {
        "name": "standard",
        "current_uc": "PotentialQuantitative_",
        "potential_uc": "PotentialQuantitativeFinal_",
        "growth_pct": "PotentialEstimatedToCover_",
        "segment": "PotentialQualitative_",
        "mirror_client_id": "Comparative_Client_ID_",
        "category_suffixes": {
            "multi_serve": "ServingType_MultiServe",
            "coca_cola": "GlobalCat_CocaCola",
            "single_serve": "ServingType_SingleServe",
            "hydration": "GlobalCat_HydratationSports&Tea",
            "nutrition": "GlobalCat_NutritionJuiceDairy&Plant",
            "sparkling": "GlobalCat_SparklingFlavors",
        },
    },
    {
        "name": "business_english",
        "current_uc": "Monthly Sales (Unit Cases)_",
        "potential_uc": "Monthly Growth Potential (Unit Cases)_",
        "growth_pct": "Percentage (%)_",
        "segment": "Priority Level_",
        "mirror_client_id": "Comparative client ID_",
        "category_suffixes": {
            "multi_serve": "ServingType_MultiServe",
            "coca_cola": "GlobalCat_CocaCola",
            "single_serve": "ServingType_SingleServe",
            "hydration": "GlobalCat_HydratationSportsTea",
            "nutrition": "GlobalCat_NutritionJuiceDairyPlant",
            "sparkling": "GlobalCat_SparklingFlavors",
        },
    },
]


def detect_mapping(df, manual):
    """Try to auto-build the column mapping from known naming conventions,
    so a bottler CSV using one of them doesn't need a hand-written
    mapping.json. Returns a mapping dict on a full match, else None (caller
    falls back to DEFAULT_MAPPING / an explicit --mapping file).
    """
    is_especial = manual.get("tipo_corrida", "").strip().lower().startswith("espe")
    categoria_especial = manual.get("categoria_especial", "").strip()

    for conv in NAMING_CONVENTIONS:
        base = {
            "client_id": "pos_id",
            "city": "pos_city",
            "subchannel": "pos_subchannel",
            "current_uc": conv["current_uc"] + "TotalPortafolio",
            "potential_uc": conv["potential_uc"] + "TotalPortafolio",
            "growth_pct": conv["growth_pct"] + "TotalPortafolio",
            "segment": conv["segment"] + "TotalPortafolio",
            "mirror_client_id": conv["mirror_client_id"] + "TotalPortafolio",
            "latitude": "pos_latitude",
            "longitude": "pos_longitude",
        }
        if not all(col in df.columns for role, col in base.items() if role not in ("latitude", "longitude")):
            continue  # this convention's base roles don't match this CSV

        categories = {}
        if is_especial:
            # find whichever single "*_CustomCat_<name>" column exists under
            # this convention's potential_uc prefix, rather than assuming the
            # CSV spells categoria_especial exactly like the manual input does
            prefix = conv["potential_uc"] + "CustomCat_"
            custom_cols = [c for c in df.columns if c.startswith(prefix)]
            if not custom_cols:
                continue
            custom_name = custom_cols[0][len(prefix):]
            for key, _label in STANDARD_CATEGORIES:
                categories[key] = {
                    "potential": conv["potential_uc"] + "CustomCat_" + custom_name,
                    "current": conv["current_uc"] + "CustomCat_" + custom_name,
                }
        else:
            for key, suffix in conv["category_suffixes"].items():
                categories[key] = {
                    "potential": conv["potential_uc"] + suffix,
                    "current": conv["current_uc"] + suffix,
                }
        if not all(c in df.columns for cols in categories.values() for c in cols.values()):
            continue  # base roles matched but categories didn't -- not this convention

        base["categories"] = categories
        print(f"generate_content.py: auto-detected '{conv['name']}' column-naming convention (no --mapping needed)")
        return base

    return None


def fmt_uc(value):
    """18611 -> '18,611' ; 2412345 -> '2.4M' ; 95400 -> '95.4K'"""
    value = float(value)
    if abs(value) >= 1_000_000:
        return f"{value/1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"{value/1_000:.1f}K"
    return f"{value:,.0f}"


def fmt_uc_small(value):
    """Adaptive-precision formatter for per-PDV UC values, which can be
    anywhere from ~50000 (Total Portfolio, large bottler) down to ~0.02
    (a single-SKU custom category on a low-volume market). A fixed
    zero-decimal format silently collapses every value under 0.5 to '0',
    which erases all signal for special-category runs. Same K/M scaling
    as fmt_uc above 1000; at or above 1, plain rounded integer (identical
    to the old behavior, so normal-scale decks look exactly as before);
    only below 1 -- where rounding to an integer would erase the value
    entirely -- does it fall back to enough decimals to stay legible.
    """
    value = float(value)
    if abs(value) >= 1_000_000:
        return f"{value/1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"{value/1_000:.1f}K"
    if abs(value) >= 1 or value == 0:
        return f"{value:,.0f}"
    return f"{value:.2f}"


def fmt_count(value):
    return f"{int(round(value)):,}"


def fmt_pct(value, signed=False, decimals=0):
    sign = "+" if signed and value >= 0 else ""
    return f"{sign}{value:.{decimals}f}%"


def normalize_segment(raw):
    key = str(raw).strip().lower()
    return SEGMENT_ALIASES.get(key, str(raw).strip())


def norm_id(value):
    """Normalize an ID for display and exact-match comparison. pandas often
    reads an all-numeric ID column as float64 -- e.g. because some other row
    in that column is blank -- which silently turns '523675' into '523675.0'.
    If the two ID columns being compared/matched (client_id vs mirror_client_id)
    don't both get this treatment, an exact string comparison between them
    fails 100% of the time without raising an error -- it just quietly
    produces an empty result (e.g. slide 15's worked-example sentence going
    blank). Strip a spurious trailing '.0' so both sides compare equal."""
    s = str(value).strip()
    if s.endswith(".0"):
        try:
            if float(s) == int(float(s)):
                s = s[:-2]
        except ValueError:
            pass
    return s


def normalize_growth(series):
    """Accept either fraction (0.38) or percent (38) growth values."""
    s = pd.to_numeric(series, errors="coerce")
    if s.dropna().abs().median() <= 1.5:
        s = s * 100
    return s


def resolve_mapping(user_mapping_path):
    mapping = json.loads(json.dumps(DEFAULT_MAPPING))  # deep copy
    if user_mapping_path:
        override = json.loads(Path(user_mapping_path).read_text(encoding="utf-8"))
        for k, v in override.items():
            if k == "categories" and isinstance(v, dict):
                for cat, cols in v.items():
                    mapping["categories"].setdefault(cat, {}).update(cols)
            else:
                mapping[k] = v
    return mapping


def require_columns(df, mapping):
    missing = []
    for role in ["client_id", "city", "subchannel", "current_uc", "potential_uc", "growth_pct", "segment"]:
        col = mapping[role]
        if col not in df.columns:
            missing.append(f"{role} (expected column '{col}')")
    for cat_key, cols in mapping["categories"].items():
        for role, col in cols.items():
            if col not in df.columns:
                missing.append(f"category '{cat_key}' {role} (expected column '{col}')")
    if missing:
        sys.exit(
            "generate_content.py: CSV is missing required columns:\n  - "
            + "\n  - ".join(missing)
            + "\n\nEither rename the columns in the CSV, or pass --mapping mapping.json "
              "overriding just the roles that differ. See references/csv-schema.md."
        )


def top_n_join(names):
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} + {names[1]}"
    return " + ".join(names[:3])


def pluralize_subcanal(n):
    return "subcanal" if n == 1 else "subcanales"


def build(df, mapping, manual):
    m = mapping
    df = df.copy()
    df["_segment"] = df[m["segment"]].map(normalize_segment)
    df["_growth"] = normalize_growth(df[m["growth_pct"]])
    df["_current"] = pd.to_numeric(df[m["current_uc"]], errors="coerce")
    df["_potential"] = pd.to_numeric(df[m["potential_uc"]], errors="coerce")

    # PDVs with an empty priority level got no potential from the model (e.g. no sales): they can't be
    # segmented, so the results slides are computed on the segmented PDVs and the count is reported
    sin_nivel = df[m["segment"]].isna()
    if sin_nivel.any():
        print(f"generate_content.py: {int(sin_nivel.sum())} PDVs without priority level (no potential) "
              "excluded from the results computations.")
        df = df[~sin_nivel]
    unknown = set(df["_segment"].unique()) - set(SEGMENT_ORDER)
    if unknown:
        sys.exit(f"generate_content.py: unrecognized segment values: {unknown}. "
                  f"Expected values mapping to {SEGMENT_ORDER}.")

    total_pdvs = len(df)
    total_current = df["_current"].sum()
    total_potential = df["_potential"].sum()
    overall_growth = (total_potential / total_current * 100) if total_current else 0.0

    # ---------- Top-20%-of-clients headline (S10) ----------
    df_sorted = df.sort_values("_potential", ascending=False).reset_index(drop=True)
    cutoff = max(1, int(round(total_pdvs * 0.20)))
    top_share_potential_pct = df_sorted["_potential"].iloc[:cutoff].sum() / total_potential * 100 if total_potential else 0
    top_share_client_pct = cutoff / total_pdvs * 100

    # ---------- Segments (S10 + S11) ----------
    segments = {}
    for seg in SEGMENT_ORDER:
        sub = df[df["_segment"] == seg]
        count = len(sub)
        segments[seg] = {
            "count": count,
            "pct_clients": count / total_pdvs * 100 if total_pdvs else 0,
            "sales_uc": sub["_current"].sum(),
            "potential_uc": sub["_potential"].sum(),
            "pct_of_potential": (sub["_potential"].sum() / total_potential * 100) if total_potential else 0,
            "avg_potential_per_pdv": (sub["_potential"].sum() / count) if count else 0,
            "growth_pct": sub["_growth"].mean() if count else 0,
            "range_min": sub["_potential"].min() if count else 0,
            "range_max": sub["_potential"].max() if count else 0,
        }
    segments["Total"] = {
        "count": total_pdvs,
        "pct_clients": 100.0,
        "sales_uc": total_current,
        "potential_uc": total_potential,
        "pct_of_potential": 100.0,
        "avg_potential_per_pdv": (total_potential / total_pdvs) if total_pdvs else 0,
        "growth_pct": None,
    }
    # range footnote: VH is open-ended above High's max; each band's floor is the band below's ceiling
    low_max = segments["Low"]["range_max"]
    mod_max = segments["Moderate"]["range_max"]
    high_max = segments["High"]["range_max"]
    range_footnote = (
        f"Rango VH: >{fmt_uc_small(high_max)} UC/mes  ·  High: {fmt_uc_small(mod_max)}–{fmt_uc_small(high_max)}"
        f"  ·  Moderate: {fmt_uc_small(low_max)}–{fmt_uc_small(mod_max)}  ·  Low: 0–{fmt_uc_small(low_max)}"
    )

    # ---------- Categories (S12), scoped to VH + High ----------
    vh_high = df[df["_segment"].isin(["Very High", "High"])]
    cats = []
    for key, label in STANDARD_CATEGORIES:
        cols = m["categories"][key]
        pot = pd.to_numeric(vh_high[cols["potential"]], errors="coerce").sum()
        cur = pd.to_numeric(vh_high[cols["current"]], errors="coerce").sum()
        growth = (pot / cur * 100) if cur else 0.0
        cats.append({"key": key, "name": label, "potential_uc": pot, "growth_pct": growth})
    cats.sort(key=lambda c: c["potential_uc"], reverse=True)
    for i, c in enumerate(cats):
        c["rank"] = i + 1
        c["priority"] = i < 2
    cat_total = sum(c["potential_uc"] for c in cats)
    top2 = cats[:2]
    top2_combined_pct = sum(c["potential_uc"] for c in top2) / cat_total * 100 if cat_total else 0
    non_priority = [c for c in cats if not c["priority"]]
    callout_cat = max(non_priority, key=lambda c: c["growth_pct"]) if non_priority else cats[-1]

    # ---------- Geography (S13), scoped to Very High ----------
    vh = df[df["_segment"] == "Very High"]
    vh_total_potential = vh["_potential"].sum()
    city_group = vh.groupby(m["city"]).agg(potential_uc=("_potential", "sum"), pdvs=("_potential", "size")).reset_index()
    city_group = city_group.sort_values("potential_uc", ascending=False).reset_index(drop=True)
    cities = city_group.head(6).to_dict("records")
    cum = 0.0
    top_n_cities = 1
    for i, row in enumerate(city_group.itertuples(), start=1):
        cum += row.potential_uc / vh_total_potential * 100 if vh_total_potential else 0
        if cum >= 70 or i >= 3:
            top_n_cities = i
            break
    top_n_cities = min(top_n_cities, 3)
    cum_pct_top_n = city_group["potential_uc"].iloc[:top_n_cities].sum() / vh_total_potential * 100 if vh_total_potential else 0

    subchan_group = vh.groupby(m["subchannel"]).agg(potential_uc=("_potential", "sum"), pdvs=("_potential", "size")).reset_index()
    subchan_group = subchan_group.sort_values("potential_uc", ascending=False).reset_index(drop=True)
    subchan_group["pct_share"] = subchan_group["potential_uc"] / vh_total_potential * 100 if vh_total_potential else 0
    subchannels = subchan_group.head(5).to_dict("records")
    top_subchannel = subchannels[0][m["subchannel"]] if subchannels else ""
    top_subchannel_pct = subchannels[0]["pct_share"] if subchannels else 0
    dominant_subchannel_count = 1 if top_subchannel_pct >= 40 else (2 if len(subchannels) > 1 and subchannels[0]["pct_share"] + subchannels[1]["pct_share"] >= 60 else 3)

    top_city_names = [str(c[m["city"]]) for c in cities[:top_n_cities]]

    # ---------- Potential per PDV by city (S12 "¿Dónde rinde más cada visita?") ----------
    # Template (Femsa Venezuela, 2026-10): 4 cities with the highest potential per PDV (2 tagged TOP 2),
    # then the 2 biggest remaining cities as contrast. Only cities with >= 1% of the PDVs, so a
    # 20-PDV town can't top the list.
    per_city = df.groupby(m["city"]).agg(pdvs=("_potential", "size"), potential_uc=("_potential", "sum"),
                                          vh_potential=("_potential", lambda s: s[df.loc[s.index, "_segment"] == "Very High"].sum()))
    per_city["per_pdv"] = per_city["potential_uc"] / per_city["pdvs"]
    big = per_city[per_city["pdvs"] >= total_pdvs * 0.01]
    dens_top = big.sort_values("per_pdv", ascending=False).head(4)
    dens_ref = big.drop(dens_top.index).sort_values("pdvs", ascending=False).head(2)
    dens_rows = pd.concat([dens_top, dens_ref])
    rest = per_city.drop(dens_top.index)
    avg_top = dens_top["potential_uc"].sum() / dens_top["pdvs"].sum() if len(dens_top) else 0
    avg_rest = rest["potential_uc"].sum() / rest["pdvs"].sum() if rest["pdvs"].sum() else 0
    vh_pot_total = per_city["vh_potential"].sum()
    dens = {
        "names": [str(c) for c in dens_top.index],
        "ratio": avg_top / avg_rest if avg_rest else 0,
        "pct_pdvs": dens_top["pdvs"].sum() / total_pdvs * 100 if total_pdvs else 0,
        "pct_potential": dens_top["potential_uc"].sum() / total_potential * 100 if total_potential else 0,
        "pct_vh": dens_top["vh_potential"].sum() / vh_pot_total * 100 if vh_pot_total else 0,
        "avg_top": avg_top, "avg_rest": avg_rest,
        "ref": [str(c) for c in dens_ref.index],
    }

    # ---------- Action plan (S15), scoped to VH + High ----------
    # In an "Especial" (custom single-category) run, mapping.json points all 6
    # STANDARD_CATEGORIES slots at the same CustomCat_<X> columns (that's the
    # only way to satisfy generate_content.py's column requirements when the
    # CSV only has one real category). max() over six equal values always
    # picks the first key in STANDARD_CATEGORIES ("Multi Serve"), which is
    # wrong and was being hand-patched after every Especial run. Use the
    # actual category name instead whenever this is an Especial run.
    is_especial_run = manual.get("tipo_corrida", "").strip().lower().startswith("espe")
    categoria_especial_name = manual.get("categoria_especial", "").strip()

    vh_high_sorted = vh_high.sort_values("_potential", ascending=False).reset_index(drop=True)
    top5_rows = []
    for _, row in vh_high_sorted.head(5).iterrows():
        cat_potentials = {}
        for key, label in STANDARD_CATEGORIES:
            cols = m["categories"][key]
            cat_potentials[label] = pd.to_numeric(pd.Series([row[cols["potential"]]]), errors="coerce").iloc[0]
        if is_especial_run and categoria_especial_name:
            prio_cat = categoria_especial_name
        else:
            prio_cat = max(cat_potentials, key=cat_potentials.get)
        # in an Especial run every entry in cat_potentials reads the same
        # underlying column, so any value works; cat_potentials[prio_cat]
        # would KeyError since prio_cat is now categoria_especial_name, which
        # isn't one of the STANDARD_CATEGORIES labels used as dict keys
        potential_in_cat = cat_potentials[prio_cat] if prio_cat in cat_potentials else next(iter(cat_potentials.values()))
        top5_rows.append({
            "pdv_id": norm_id(row[m["client_id"]]),
            "city": str(row[m["city"]]),
            "subchannel": str(row[m["subchannel"]]),
            "potential_uc": row["_potential"],
            "growth_pct": row["_growth"],
            "priority_category": prio_cat,
            "potential_in_category": potential_in_cat,
        })

    # ---------- Exploratory cuts (not used by any fixed slide) ----------
    # This is raw material for a judgment call, not a finished slide: look at these
    # and decide whether the standard deck is missing the actual story in this
    # operation's data. See SKILL.md's "optional insight slide" step.
    city_stats = df.groupby(m["city"]).agg(
        pdv_count=("_potential", "size"),
        total_potential=("_potential", "sum"),
        total_current=("_current", "sum"),
    ).reset_index()
    city_stats["potential_per_pdv"] = city_stats["total_potential"] / city_stats["pdv_count"]
    city_stats = city_stats[city_stats["pdv_count"] >= max(5, total_pdvs // 200)]  # drop noisy tiny cities
    top_by_density = city_stats.sort_values("potential_per_pdv", ascending=False).head(8)
    top_by_volume = city_stats.sort_values("pdv_count", ascending=False).head(8)
    # cities that are small (below median pdv_count) but punch above their weight
    # (top-quartile potential-per-pdv) - the "hidden opportunity" cut
    median_count = city_stats["pdv_count"].median() if len(city_stats) else 0
    p75_density = city_stats["potential_per_pdv"].quantile(0.75) if len(city_stats) else 0
    hidden_gems = city_stats[(city_stats["pdv_count"] <= median_count) & (city_stats["potential_per_pdv"] >= p75_density)]
    hidden_gems = hidden_gems.sort_values("potential_per_pdv", ascending=False).head(6)

    subchan_cat_matrix = []
    if len(vh_high):
        for sub, sub_df in vh_high.groupby(m["subchannel"]):
            if len(sub_df) < max(5, len(vh_high) // 100):
                continue
            best_cat, best_val = None, -1
            for key, label in STANDARD_CATEGORIES:
                v = pd.to_numeric(sub_df[m["categories"][key]["potential"]], errors="coerce").sum()
                if v > best_val:
                    best_cat, best_val = label, v
            subchan_cat_matrix.append({"subchannel": str(sub), "top_category": best_cat, "potential_uc": best_val, "pdv_count": len(sub_df)})
    subchan_cat_matrix.sort(key=lambda r: r["potential_uc"], reverse=True)

    outliers = []
    for seg in SEGMENT_ORDER:
        sub = df[df["_segment"] == seg]
        if len(sub) < 5:
            continue
        mean, std = sub["_growth"].mean(), sub["_growth"].std()
        if not std or pd.isna(std):
            continue
        sub = sub.assign(_z=(sub["_growth"] - mean) / std)
        for _, row in sub.sort_values("_z", ascending=False).head(2).iterrows():
            if row["_z"] < 1.5:
                continue
            outliers.append({
                "pdv_id": norm_id(row[m["client_id"]]), "segment": seg, "city": str(row[m["city"]]),
                "growth_pct": row["_growth"], "potential_uc": row["_potential"], "z_score": round(float(row["_z"]), 1),
            })
    outliers.sort(key=lambda r: r["z_score"], reverse=True)

    exploratory = {
        "note": "Not used by any fixed slide - scan this for a story the standard deck might be missing "
                "(see SKILL.md). Don't force an insight slide if nothing here actually stands out.",
        "top_cities_by_potential_density": top_by_density[[m["city"], "pdv_count", "potential_per_pdv", "total_potential"]].to_dict("records"),
        "top_cities_by_pdv_volume": top_by_volume[[m["city"], "pdv_count", "potential_per_pdv", "total_potential"]].to_dict("records"),
        "hidden_gem_cities": hidden_gems[[m["city"], "pdv_count", "potential_per_pdv", "total_potential"]].to_dict("records"),
        "subchannel_top_category": subchan_cat_matrix[:8],
        "growth_outlier_pdvs": outliers[:8],
    }

    # ---------- Worked example (S15), with a sanity-checked "mirror" ----------
    # The mirror/comparable client is meant to be a believable peer ("this PDV
    # like you, in your own environment, already sells X"). Some operations'
    # Comparative_Client_ID pairing doesn't filter for scale, so it can match a
    # normal PDV to a wholesale-sized outlier -- e.g. its comparable turning out
    # to be the single highest-volume account in the entire dataset, which reads
    # as absurd rather than persuasive in front of a salesperson. Walk down the
    # potential-sorted list (instead of always taking #1) until landing on a PDV
    # whose mirror isn't itself a regional outlier.
    current_p95 = df["_current"].quantile(0.95) if len(df) else 0

    # Data-quality check on the whole scored population, not just the example
    # candidate: if a large share of PDVs are paired with themselves as their
    # own "comparable client", that's an upstream issue in whatever produced
    # Comparative_Client_ID, worth flagging regardless of which single PDV ends
    # up as the worked example on this slide.
    mirror_col = df[m["mirror_client_id"]] if m["mirror_client_id"] in df.columns else None
    self_mirror_rate = None
    if mirror_col is not None:
        has_mirror = mirror_col.notna()
        if has_mirror.sum():
            client_norm = df[m["client_id"]].apply(norm_id)
            mirror_norm = mirror_col.apply(lambda v: norm_id(v) if pd.notna(v) else None)
            self_mirror_rate = float((client_norm == mirror_norm)[has_mirror].mean())
            if self_mirror_rate > 0.05:
                print(
                    f"Warning: {self_mirror_rate:.0%} of PDVs with a mirror/comparable client are matched "
                    f"to themselves (Comparative_Client_ID == client_id). generate_content.py already "
                    f"routes around this for the slide 15 worked example, but this may be worth flagging "
                    f"to whoever produces the model output.",
                    file=sys.stderr,
                )

    def _lookup_mirror(row):
        mirror_id = row.get(m["mirror_client_id"])
        if mirror_id is None or pd.isna(mirror_id):
            return None, None
        mirror_row = df[df[m["client_id"]].apply(norm_id) == norm_id(mirror_id)]
        if not len(mirror_row):
            return norm_id(mirror_id), None
        return norm_id(mirror_id), mirror_row["_current"].iloc[0]

    example = None
    skipped_outlier_mirrors = 0
    if len(vh_high_sorted):
        for _, cand in vh_high_sorted.iterrows():
            cand_id_norm = norm_id(cand[m["client_id"]])
            mirror_id_norm, mirror_sales = _lookup_mirror(cand)
            if mirror_id_norm is not None and mirror_id_norm == cand_id_norm:
                # some operations' Comparative_Client_ID pairing includes a PDV
                # matched to itself -- "your peer, who is also you" is not a
                # sentence to put in front of a client, so treat it the same as
                # a missing mirror rather than a usable (if degenerate) one.
                skipped_outlier_mirrors += 1
                continue
            if mirror_sales is not None and mirror_sales > current_p95:
                skipped_outlier_mirrors += 1
                continue
            cat_potentials = {}
            for key, label in STANDARD_CATEGORIES:
                cols = m["categories"][key]
                cat_potentials[label] = pd.to_numeric(pd.Series([cand[cols["potential"]]]), errors="coerce").iloc[0]
            # same Especial-run fix as the top5_rows loop above
            if is_especial_run and categoria_especial_name:
                prio_cat = categoria_especial_name
            else:
                prio_cat = max(cat_potentials, key=cat_potentials.get)
            example = {
                "pdv_id": norm_id(cand[m["client_id"]]),
                "city": str(cand[m["city"]]),
                "current_uc": cand["_current"],
                "mirror_id": mirror_id_norm,
                "mirror_current_uc": mirror_sales,
                "potential_uc": cand["_potential"],
                "growth_pct": cand["_growth"],
                "priority_category": prio_cat,
                "skipped_outlier_mirrors_before_this": skipped_outlier_mirrors,
            }
            break
        else:
            # every VH+High candidate either had no mirror match or an outlier one --
            # fall back to #1 by potential so the slide isn't empty; example_sentence1
            # will just come out blank (generate_content.py already handles that).
            first = vh_high_sorted.iloc[0]
            mirror_id_norm, mirror_sales = _lookup_mirror(first)
            example = {
                "pdv_id": norm_id(first[m["client_id"]]),
                "city": str(first[m["city"]]),
                "current_uc": first["_current"],
                "mirror_id": mirror_id_norm,
                "mirror_current_uc": None,  # deliberately suppressed even if found -- it was an outlier
                "potential_uc": first["_potential"],
                "growth_pct": first["_growth"],
                "priority_category": top5_rows[0]["priority_category"] if top5_rows else None,
                "skipped_outlier_mirrors_before_this": skipped_outlier_mirrors,
            }

    # ================= Assemble content.json =================
    content = {"manual": manual, "raw": {"exploratory": exploratory}, "display": {}, "copy": {}}

    is_especial = manual.get("tipo_corrida", "").strip().lower().startswith("espe")
    categoria_especial = manual.get("categoria_especial", "").strip()
    if is_especial and categoria_especial:
        portfolio_scope_line = f"Categoría Especial · {categoria_especial}"
        portfolio_scope_header = f"CATEGORÍA ESPECIAL: {categoria_especial.upper()}"
    else:
        portfolio_scope_line = "Total Portfolio · Colas · Single Serve · Sparkling"
        portfolio_scope_header = "TOTAL PORTAFOLIO"

    content["display"]["s9"] = {
        "cantidad_registros": f"{fmt_count(manual['cantidad_registros'])} · Cantidad de registros",
        "fecha_cliente": f"{manual['fecha_clientes']} ({manual['origen_clientes']}) · Fecha de cliente",
        "corte_ventas": f"Corte de ventas: {manual['corte_ventas']}",
        "fecha_altscore": f"Fecha altscore: {manual['fecha_altscore']}",
        "portfolio_scope_line": portfolio_scope_line,
    }
    content["display"]["s11_header"] = f"SEGMENTACIÓN DE POTENCIAL · {portfolio_scope_header}"

    content["display"]["s10"] = {
        "total_pdvs": fmt_count(total_pdvs),
        "total_current_uc": fmt_uc(total_current),
        "total_potential_uc": fmt_uc(total_potential),
        "overall_growth_pct": fmt_pct(overall_growth, signed=True),
        "seg_pct": {s: fmt_pct(segments[s]["pct_clients"]) for s in SEGMENT_ORDER},
        "seg_count": {s: fmt_count(segments[s]["count"]) for s in SEGMENT_ORDER},
        "seg_potential_value": {s: fmt_uc(segments[s]["potential_uc"]) for s in SEGMENT_ORDER},
        "seg_potential_pct": {s: fmt_pct(segments[s]["pct_of_potential"]) for s in SEGMENT_ORDER},
    }
    content["raw"]["s10"] = {
        "seg_pct_clients": {s: segments[s]["pct_clients"] for s in SEGMENT_ORDER},
        "seg_pct_potential": {s: segments[s]["pct_of_potential"] for s in SEGMENT_ORDER},
        "top_share_client_pct": top_share_client_pct,
        "top_share_potential_pct": top_share_potential_pct,
    }
    content["copy"]["s10"] = {
        "headline_line1": f"El {top_share_client_pct:.0f}% de los clientes",
        "headline_line2": f"concentra el {top_share_potential_pct:.0f}% de la oportunidad.",
        "callout": f"{top_share_potential_pct:.0f}% del potencial está en solo el {top_share_client_pct:.0f}% de los clientes",
    }

    content["display"]["s11"] = {
        "rows": {
            s: {
                "pdvs": fmt_count(segments[s]["count"]),
                "pct_clients": fmt_pct(segments[s]["pct_clients"]),
                "sales_uc": fmt_uc(segments[s]["sales_uc"]),
                "potential_uc": fmt_uc(segments[s]["potential_uc"]),
                "avg_potential_pdv": f"{fmt_uc_small(segments[s]['avg_potential_per_pdv'])} UC",
                "growth_pct": fmt_pct(segments[s]["growth_pct"]) if segments[s]["growth_pct"] is not None else "—",
                "pct_potential": fmt_pct(segments[s]["pct_of_potential"]),
            }
            for s in SEGMENT_ORDER + ["Total"]
        },
        "range_footnote": range_footnote,
    }

    content["display"]["s12"] = {
        "categories": [
            {
                "name": c["name"],
                "value_display": f"{fmt_uc(c['potential_uc'])} UC/mes",
                "growth_display": fmt_pct(c["growth_pct"], signed=True),
                "priority": c["priority"],
                "rank": c["rank"],
            }
            for c in cats
        ]
    }
    content["raw"]["s12"] = {"categories": cats, "top2_combined_pct": top2_combined_pct,
                              "callout_category": callout_cat}
    content["copy"]["s12"] = {
        "headline": f"{top2[0]['name']} + {top2[1]['name']} = {top2_combined_pct:.0f}% del potencial. "
                    f"Si solo hay tiempo para una conversación, que sea sobre estas dos categorías.",
        "callout": f"{callout_cat['name']}: {fmt_pct(callout_cat['growth_pct'], signed=True)} de crecimiento estimado — "
                   f"es la categoría con mayor % de upside en VH+H. Ideal para activación de categoría en clientes "
                   f"que ya compran {top2[0]['name']} y {top2[1]['name']}.",
    }

    content["display"]["s12_ciudad"] = {
        "rows": [
            {"name": str(c), "per_pdv": float(r.per_pdv), "value_display": f"{r.per_pdv:.1f} UC/PDV",
             "pdvs_display": f"{fmt_count(r.pdvs)} PDVs", "top": i < 2}
            for i, (c, r) in enumerate(dens_rows.iterrows())
        ],
    }
    content["raw"]["s12_ciudad"] = dens
    content["copy"]["s12_ciudad"] = {
        "headline": f"{', '.join(dens['names'][:-1])} y {dens['names'][-1]}: {dens['ratio']:.1f}x de potencial por "
                    f"PDV. Tienen el {dens['pct_pdvs']:.0f}% de los PDVs y el {dens['pct_potential']:.0f}% del potencial — "
                    f"{dens['avg_top']:.1f} UC/mes por PDV contra {dens['avg_rest']:.1f} en el resto del país.",
        "callout": (f"Priorizar {top_n_join(dens['names'][:2])} antes que {top_n_join(dens['ref'])}: "
                    f"las 4 ciudades de arriba concentran el {dens['pct_vh']:.0f}% del potencial Very High."),
    }

    content["display"]["s13"] = {
        "cities": [{"name": str(c[m["city"]]), "value_display": f"{fmt_uc(c['potential_uc'])} UC"} for c in cities],
        "subchannels": [
            {
                "name": str(s[m["subchannel"]]),
                "detail": f"{fmt_count(s['pdvs'])} PDVs · {fmt_uc(s['potential_uc'])} UC",
                "pct_display": fmt_pct(s["pct_share"]),
            }
            for s in subchannels
        ],
    }
    content["copy"]["s13"] = {
        "headline_line1": f"{top_n_cities} ciudad{'es' if top_n_cities != 1 else ''}, {dominant_subchannel_count} "
                           f"{pluralize_subcanal(dominant_subchannel_count)}.",
        "headline_line2": f"{cum_pct_top_n:.0f}% del potencial Very High.",
        # two separate facts: "<cities> en <subcanal> captura X%" read X (the subchannel's share) as the cities'
        "callout": f"{top_n_join(top_city_names)} concentran el {cum_pct_top_n:.0f}% del potencial VH y "
                   f"{top_subchannel} el {top_subchannel_pct:.0f}%: ahí está la mayor oportunidad con menos visitas.",
    }

    content["display"]["s15"] = {
        "rows": [
            {
                "pdv_id": r["pdv_id"],
                "city": r["city"],
                "subchannel": r["subchannel"],
                "potential_uc": f"{fmt_uc_small(r['potential_uc'])} UC",
                "growth_pct": fmt_pct(r["growth_pct"]),
                "priority_category": r["priority_category"],
                "potential_in_category": f"{fmt_uc_small(r['potential_in_category'])} UC",
            }
            for r in top5_rows
        ],
        "total_vh_high_count": fmt_count(len(vh_high)),
    }
    content["raw"]["s15"] = {
        "example_selection_note": (
            "The worked example below is the highest-potential VH+High PDV whose "
            "mirror/comparable client passed a sanity check: not a self-reference "
            "(Comparative_Client_ID == client_id) and not itself a top-5%-by-sales "
            "outlier region-wide. Candidates skipped for that reason before landing "
            f"on this one: {example['skipped_outlier_mirrors_before_this'] if example else 0}."
        ),
        "self_referencing_mirror_rate_overall": (
            round(self_mirror_rate, 3) if self_mirror_rate is not None else None
        ),
    }
    content["copy"]["s15"] = {
        # top VH city (not the #1 PDV's city: that mixed "Almacenes de GUALEGUAYCHU" when the #1 wasn't a Almacén)
        "subhead": f"Empezar por los clientes VH en {top_subchannel} de {top_city_names[0] if top_city_names else ''}. "
                   f"Top 5 clientes con alto potencial.",
        "example_title": f"Ejemplo — PDV {example['pdv_id']}, {example['city']}" if example else "",
        "example_sentence1": (
            f"Vende {fmt_uc_small(example['current_uc'])} UC/mes. Su espejo (PDV {example['mirror_id']}) vende "
            f"{fmt_uc_small(example['mirror_current_uc'])} UC/mes en el mismo entorno."
        ) if example and example["mirror_current_uc"] is not None else "",
        "example_sentence2": (
            f"Oportunidad: +{fmt_uc_small(example['potential_uc'])} UC enfocando {example['priority_category']}. "
            f"Eso es {fmt_pct(example['growth_pct'], signed=True)} sobre su venta actual."
        ) if example else "",
        "closing": f"El archivo completo tiene los {fmt_count(len(vh_high))} clientes VH+High ordenados por potencial. "
                   f"La misma lógica aplica a cada uno.",
    }

    return content


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--manual-inputs", required=True, help="JSON file with the 8 manual fields (see SKILL.md)")
    ap.add_argument("--mapping", default=None, help="Optional JSON overriding column-role mapping")
    ap.add_argument("--out", default="content.json")
    args = ap.parse_args()

    manual = json.loads(Path(args.manual_inputs).read_text(encoding="utf-8"))
    missing_manual = [f for f in REQUIRED_MANUAL_FIELDS if f not in manual]
    if missing_manual:
        sys.exit(f"generate_content.py: manual-inputs is missing fields: {missing_manual}")
    if manual.get("tipo_corrida", "").strip().lower().startswith("espe") and not manual.get("categoria_especial", "").strip():
        sys.exit(
            "generate_content.py: tipo_corrida is 'Especial' but manual-inputs has no 'categoria_especial' "
            "(e.g. 'Hidratación', 'Cero Azúcar', 'Monster'). This is what slide 9 and slide 11's header need "
            "to say instead of 'Total Portfolio'."
        )

    df = pd.read_csv(args.csv)
    if args.mapping:
        mapping = resolve_mapping(args.mapping)  # explicit --mapping always wins
    else:
        mapping = detect_mapping(df, manual) or resolve_mapping(None)
    require_columns(df, mapping)

    content = build(df, mapping, manual)
    Path(args.out).write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
