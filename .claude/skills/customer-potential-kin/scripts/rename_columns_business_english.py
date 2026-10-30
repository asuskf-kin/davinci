#!/usr/bin/env python3
"""
rename_columns_business_english.py — convert a Customer Potential CSV's
column names from the "standard" naming convention
(PotentialQuantitativeFinal_, PotentialQuantitative_, PotentialQualitative_,
PotentialEstimatedToCover_, Comparative_Client_ID_) to the "business_english"
one (Monthly Growth Potential (Unit Cases)_, Monthly Sales (Unit Cases)_,
Priority Level_, Percentage (%)_, Comparative client ID_) -- confirmed from
Nico's upstream pipeline (first seen applied to Brasal Brasil's export).

Columns that don't start with any of the known prefixes (pos_id, pos_city,
category suffixes, etc.) are left exactly as they are. If the CSV already
uses the business_english convention, this is a no-op copy.

Usage:
    python rename_columns_business_english.py --csv data.csv --out data_business_english.csv
"""
import argparse
import sys
import pandas as pd

# Same prefix_map confirmed from the upstream rename step; longest prefixes
# are checked first so e.g. "PotentialQuantitativeFinal_" (which starts with
# "PotentialQuantitative_" as a substring) isn't matched by the shorter key.
PREFIX_MAP = {
    'PotentialQuantitativeFinal_': 'Monthly Growth Potential (Unit Cases)_',
    'PotentialQuantitative_':      'Monthly Sales (Unit Cases)_',
    'PotentialQualitative_':       'Priority Level_',
    'PotentialEstimatedToCover_':  'Percentage (%)_',
    'Comparative_Client_ID_':      'Comparative client ID_',
}
SORTED_PREFIXES = sorted(PREFIX_MAP.keys(), key=len, reverse=True)


def rename_column(col):
    for prefix in SORTED_PREFIXES:
        if col.startswith(prefix):
            new_name = PREFIX_MAP[prefix] + col[len(prefix):]
            return new_name.replace('&', '')  # matches the two category
            # suffixes that contain one (HydratationSports&Tea,
            # NutritionJuiceDairy&Plant) -- business_english spells both
            # without the ampersand.
    return col


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    df = pd.read_csv(args.csv, low_memory=False)
    before = list(df.columns)
    df.columns = [rename_column(c) for c in df.columns]
    changed = sum(1 for a, b in zip(before, df.columns) if a != b)

    df.to_csv(args.out, index=False)
    print(f"Renamed {changed} of {len(before)} columns -> business_english convention")
    print(f"Wrote {args.out}")

    if changed == 0:
        print("Note: no columns matched the 'standard' prefixes -- the CSV "
              "may already be in business_english, or use a different "
              "convention entirely (nothing was changed either way).",
              file=sys.stderr)


if __name__ == "__main__":
    main()
