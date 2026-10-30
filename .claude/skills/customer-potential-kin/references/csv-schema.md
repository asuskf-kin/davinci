# CSV schema for Customer Potential model output

`scripts/generate_content.py` needs one row per PDV (point of sale). Identity
and location columns haven't varied across any bottler we've seen so far:
`pos_id`, `pos_city`, `pos_subchannel`, `pos_latitude`, `pos_longitude`.

**The script auto-detects which of the two known naming conventions the rest
of the CSV uses — you usually don't need to write a `mapping.json` at all.**
Just run it without `--mapping` first:

```
python generate_content.py --csv data.csv --manual-inputs manual.json --out content.json
```

If it printed `auto-detected '<name>' column-naming convention`, you're done.
It tries, in order:

**`standard`** — suffix-based, e.g. `PotentialQuantitativeFinal_TotalPortafolio`:

| Role | Column |
|---|---|
| `current_uc` | `PotentialQuantitative_TotalPortafolio` |
| `potential_uc` | `PotentialQuantitativeFinal_TotalPortafolio` |
| `growth_pct` | `PotentialEstimatedToCover_TotalPortafolio` |
| `segment` | `PotentialQualitative_TotalPortafolio` |
| `mirror_client_id` | `Comparative_Client_ID_TotalPortafolio` |

**`business_english`** — seen first from Brasal Brasil; confirmed to come
from an upstream rename step in Nico's pipeline that maps `standard` names to
these business-facing ones for some bottlers' exports (it also strips `&`
from the two category suffixes that have one):

| Role | Column |
|---|---|
| `current_uc` | `Monthly Sales (Unit Cases)_TotalPortafolio` |
| `potential_uc` | `Monthly Growth Potential (Unit Cases)_TotalPortafolio` |
| `growth_pct` | `Percentage (%)_TotalPortafolio` |
| `segment` | `Priority Level_TotalPortafolio` |
| `mirror_client_id` | `Comparative client ID_TotalPortafolio` |

For each, the 6 standard categories follow the same prefix with a
`GlobalCat_`/`ServingType_` suffix (e.g. `..._GlobalCat_CocaCola`); a
`categoria_especial` ("Especial") run instead looks for whatever single
`..._CustomCat_<name>` column exists under that prefix, so the CSV's own
spelling of the custom category name doesn't need to match `manual-inputs`
exactly.

## If neither convention matches

Inspect the real CSV's headers (`pd.read_csv(path, nrows=0).columns` is
enough). Write a small JSON with only the roles that need remapping and pass
it with `--mapping` — this always overrides auto-detection:

```json
{
  "client_id": "ID_Cliente",
  "categories": {
    "hydration": {"potential": "Hidratacion_Pot", "current": "Hidratacion_Actual"}
  }
}
```

If the new CSV turns out to follow yet another *recurring* convention (not a
one-off), consider adding it to `NAMING_CONVENTIONS` in
`generate_content.py` instead of writing `mapping.json` by hand every time
that bottler's export shows up.


## The "range footnote" caveat

Slide 11's footnote ("Rango VH: >X UC/mes · High: A–B · ...") is built from
the min/max of `potential_uc` observed inside each segment in the data — it
assumes the VH/H/M/L bins were cut on that same variable. If a given
operation's model instead bins on something else (a raw score, current
sales, etc.), the footnote will still render but the numbers may not be the
literal cutoffs the model used. If Nico or the data team says the bins come
from a different column, that column can be passed as the segmentation
reference and the footnote logic adjusted — flag this rather than guessing.

## Manual inputs (not in the CSV)

These 8 fields don't come from the model output — collect them from
whoever is running the deck, each time:

| Field | Example | Goes on |
|---|---|---|
| `embotelladora` | `"Nayar"` | Slide 1 title (slide 8 only has "Resultados / Ultrasegmentación" — it does not carry the bottler/month line, so there's nothing to fill in there) |
| `mes_anio` | `"Junio 2026"` | Slide 1 title |
| `tipo_corrida` | `"General"` or `"Especial"` | Slide 1 subtitle, and (combined with `categoria_especial`) slide 9 and slide 11's header |
| `cantidad_registros` | `18611` | Slide 9 |
| `fecha_clientes` | `"Junio 2026"` | Slide 9 |
| `origen_clientes` | `"Bottler"`, `"KO"`, or `"NSR"` | Slide 9 |
| `corte_ventas` | `"Junio 2026"` | Slide 9 |
| `fecha_altscore` | `"Junio 2026"` | Slide 9. **Do not assume this is "one month before `corte_ventas`"** — the AltScore date has no fixed relationship to when the model was run or to the sales cutoff; it depends entirely on that operation's scoring cycle. Always ask for the real value rather than defaulting to an offset. |
| `categoria_especial` | `"Hidratación"`, `"Cero Azúcar"`, `"Monster"` | Slide 9's portfolio-scope line and slide 11's header. **Required only when `tipo_corrida` is `"Especial"`** — the script will stop and ask for it if it's missing in that case. Leave it out (or empty) for a standard Total Portfolio run. |

## Optional deliverable: CSV renamed to the `business_english` convention

Some people want a copy of the CSV back with columns renamed from `standard`
to `business_english` (see the naming-convention tables above), independent
of the deck/map. `scripts/rename_columns_business_english.py` does just that
rename — it doesn't touch rows, doesn't need `manual-inputs`, and is
unrelated to `generate_content.py`'s auto-detection (that reads either
convention as-is; this rewrites one into the other for someone who needs the
file itself in that shape):

```
python rename_columns_business_english.py --csv data.csv --out data_business_english.csv
```

Columns already in `business_english`, or in neither known convention, are
left untouched — it only rewrites what matches a `standard` prefix. When
this is one of the deliverables asked for in step 0, run it on the same
cleaned/filtered CSV used for the deck and map, so all deliverables for that
operation reflect the same rows.
