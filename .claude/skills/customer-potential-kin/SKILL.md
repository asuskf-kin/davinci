---
name: customer-potential-kin
description: Build a Kin Analytics "Customer Potential / Ultrasegmentación" results deck (the 16-slide Kin Analytics template covering the model explanation plus a bottler's results) from a Customer Potential model output CSV, and/or an interactive HTML density map of the same results. Use this whenever Nico or a Kin Analytics teammate asks to build, generate, or update a Customer Potential (CP) deck, a "resultados de Ultrasegmentación" presentation, a "mapa interactivo" or "mapa de densidad" of CP/Ultrasegmentación results, or mentions running the CP/Ultrasegmentación results for a bottler (Nayar, or any other embotelladora) — even if they just paste a CSV and ask for "the deck," "la presentación de resultados," or "el mapa". Always reach for this skill instead of hand-building slides or a map from scratch when a Customer Potential CSV is involved, since the numbers must be computed deterministically from the data, not estimated.
---

# Kin Analytics — Customer Potential Results Deck

## What this produces

A .pptx in the fixed Kin Analytics Customer Potential template, at minimum
16 slides: slides 1-8 explain the Ultrasegmentación model (fixed, never
edited), slide 9 states the operation's data inputs, slides 10-13 and 15
are the bottler's results computed from a CSV, slide 14 is a map
placeholder left for manual insertion, and slide 16 closes on "corrida
estándar vs. especial" (fixed).

That base structure is the same every run on purpose — it's what makes the
deck fast to produce and instantly recognizable as a Kin Analytics
deliverable. But every operation's data has its own story, and the fixed
slides can genuinely miss it: a city that's small but punches way above its
weight, a subchannel that over-indexes on one category, a segment
concentrated somewhere unexpected. **Use judgment on whether this
particular dataset has something worth an extra slide** — step 6 below
covers how to look for it and how to build one. Most runs won't need it;
don't force an insight that isn't actually there.

## Why the numbers are scripted, not written freeform

Every sentence on the results slides (S10, S12, S13, S15) turns out to be a
fill-in-the-blank pattern around a handful of numbers — e.g. "El {X}% de los
clientes concentra el {Y}% de la oportunidad." Getting the *numbers* right is
the entire job; there's no freeform copywriting needed. `generate_content.py`
computes every number and slots them into these known sentence patterns, so
the same CSV always produces the same deck and there is one place
(`content.json`) to sanity-check before anything touches the .pptx.

## Workflow

0. **Ask which deliverable(s) are needed, before doing anything else** — but
   default to all three unless the person asks for fewer:
   the .pptx deck, the interactive HTML map, and the CSV with columns
   renamed to the `business_english` convention. This changes which steps
   below actually run:
   - **"El deck" / "la presentación" with nothing else specified, or
     explicitly "las tres" / "todo"** → all three: steps 1-6, step 7b, and
     `scripts/rename_columns_business_english.py`.
   - **Deck only** → steps 1-6, skip step 7b and the rename script.
   - **Map only** → step 7b (still do step 1 for the CSV/mapping, and
     collect whichever of the 8 manual inputs `references/interactive-map.md`
     needs), skip the deck steps and the rename script.
   - **Renamed CSV only** → just the rename script; skip everything else,
     including manual inputs (it doesn't need any).
   Still worth a quick check when the map isn't possible (no lat/long
   columns) — confirm whether to proceed with just the other two rather
   than silently dropping it.


1. **Get the CSV and inspect its columns.** Run
   `python -c "import pandas as pd; print(pd.read_csv('data.csv', nrows=0).columns.tolist())"`.
   `generate_content.py` auto-detects the column-naming convention (see
   `references/csv-schema.md`) — just run it without `--mapping` first. Only
   write a `mapping.json` if it can't detect a match; don't rename the user's
   CSV.

2. **Collect the 8 manual inputs by asking in chat** (these aren't in the
   CSV): embotelladora name, mes/año, tipo de corrida (General/Especial),
   cantidad de registros, fecha de clientes, origen (Bottler/KO/NSR), corte
   de ventas, fecha AltScore. Save them as `manual_inputs.json` — see the
   table in `references/csv-schema.md` for the exact keys and an example.

3. **Compute the numbers:**
   ```
   python scripts/generate_content.py --csv data.csv --manual-inputs manual_inputs.json \
       [--mapping mapping.json] --out content.json
   ```
   Open `content.json` and sanity-check it before moving on: do the KPI
   totals look right, does the segment table add up, are the top cities and
   categories names that actually exist in this operation's data? This is
   the cheap place to catch a column-mapping mistake — much cheaper than
   catching it after the deck is built.

4. **Fill the template:**
   ```
   python scripts/fill_deck.py --template assets/Customer_Potential_Results_Template.pptx \
       --content content.json --output <Bottler>_CP_Results.pptx
   ```

5. **Look for a story the standard slides miss.** `content.json` includes a
   `raw.exploratory` section built exactly for this (city density vs.
   volume, subchannel-category cross-cuts, growth outliers) — read
   `references/insight-slides.md` for what's in it and how to build an
   extra on-brand slide if something stands out. This is a judgment call,
   not a required step: most runs ship fine without one. Do this *before*
   final visual QA so the extra slide gets checked along with everything
   else.

6. **Visual QA before handing it over** — this template has bars and bubbles
   whose *size* is computed from the data (not just their text), so a purely
   textual read of the deck can miss a bar that's the wrong length. Convert
   to images and look at every one of slides 9-13 and 15 (see the pptx
   skill's "Converting to Images" section for the soffice/pdftoppm
   commands). Check specifically:
   - Slide 10: do the stacked-bar segment widths and the four potential
     bars look proportional to their stated percentages?
   - Slide 12: are the category bars ordered by size, and does the longest
     bar belong to the category with the largest stated value?
   - Slide 13: do bubble sizes look proportional to their UC values, and is
     any city/subchannel name overflowing its box (long names can wrap
     oddly since the box widths are fixed)?
   - Slide 11 and 15: any table cell showing "—" or blank that shouldn't be?
   - Slide 1/8/9: bottler name, month, and the 4 manual data points reading
     correctly and not overlapping the fixed label text.

7. **Slide 14 (static map) is intentionally left untouched** — unless the
   CSV has latitude/longitude, in which case offer the interactive map
   instead (next step). Without coordinates, tell whoever's using the deck
   to drop in a screenshot from their GIS/Tableau tool manually.

7b. **If the CSV has coordinates, build the interactive density map too.**
   This is a separate HTML deliverable, not something embedded in the
   .pptx (PowerPoint can't run the interactivity). Read
   `references/interactive-map.md` first — it explains an important
   constraint: the output must never contain a single raw PDV coordinate,
   only aggregated hexagon statistics, and the doc covers exactly how that
   works and how to verify it. Then:
   ```
   python scripts/build_interactive_map.py --csv data.csv --manual-inputs manual_inputs.json \
       [--mapping mapping.json] --out <Bottler>_Mapa_Interactivo.html
   ```
   Mention it as a companion to the deck when you hand things over — it's
   a good replacement for slide 14 in an actual presentation (open it live
   instead of a static screenshot).

8. Present whichever deliverable(s) were asked for in step 0 — the .pptx,
   the map HTML, the renamed CSV, or any combination. Don't hand over one
   that wasn't requested just because it happens to exist from a prior run.

## Known limitations to flag if the output looks off

- The slide-10 stacked bar's small legend row (the dots + segment names +
  counts below the bar) stays at its original template position rather than
  reflowing under the new bar segments — for very lopsided distributions
  this can look slightly misaligned. Worth a glance in visual QA.
- Slide 13's "N ciudades, M subcanal(es)" headline and the geography
  numbers only ever look at **Very High** clients, matching the template's
  own framing ("PRIORIZACIÓN GEOGRÁFICA · CLIENTES VERY HIGH").
- Slide 12's categories are always the same fixed 6 (Multi Serve, Coca
  Cola, Single Serve, Hydration, Nutrition, Sparkling Flavors), scoped to
  Very High + High clients, matching the template header.
- For a "corrida especial" (a specific SKU/category combo instead of Total
  Portfolio), pass `categoria_especial` in the manual inputs (e.g.
  `"Hidratación"`) — `generate_content.py` will refuse to run without it
  when `tipo_corrida` is `"Especial"`, and it re-labels both slide 9's
  portfolio-scope line and slide 11's header automatically. Slides 12 and
  13's headers are already generic enough ("CLIENTES VH + HIGH", "CLIENTES
  VERY HIGH") that they don't need adapting.

## Files

- `scripts/generate_content.py` — CSV + manual inputs → `content.json`
  (all computed numbers, pre-composed sentences, and the `exploratory`
  section for spotting an extra story). Run this first.
- `scripts/fill_deck.py` — `content.json` + template → the base 16-slide
  `.pptx`.
- `scripts/restyle_insight_slide.py` — turns a judgment call ("this
  dataset's real story is X") into an extra on-brand slide. Used together
  with the pptx skill's own `add_slide.py`; see `references/insight-slides.md`.
- `scripts/build_interactive_map.py` — CSV (with lat/long) + manual inputs →
  a standalone interactive HTML density map. See `references/interactive-map.md`
  — read it before touching this script, it explains a privacy constraint
  that shapes the whole design (never ship raw PDV coordinates).
- `assets/interactive_map_template.html` — the HTML/CSS/JS shell
  `build_interactive_map.py` fills in with the computed hex data.
- `references/csv-schema.md` — expected CSV columns, the mapping-override
  mechanism, and the manual-input fields.
- `references/insight-slides.md` — what's in `content.json`'s
  `exploratory` section, and how to build an optional extra slide from it.
- `references/interactive-map.md` — the interactive map's data model, the
  privacy design, and its own required/optional CSV columns (lat/long, GEC).
- 2026-10-23: the template was replaced by the team's "Customer Potential.pptx" (a finished Femsa Venezuela
  deck); `fill_deck.py` was re-derived for it (slide 12 is now potential per PDV by city, slide 16 a closing;
  `--map-image` fills slide 14) and refuses to save if any Venezuela text survives (`LEFTOVERS`).
- `assets/Customer_Potential_Results_Template.pptx` — the fixed Kin
  Analytics template this skill fills in. If Nico hands over a newer
  corrected version of the template, replace this file — but note that
  `fill_deck.py` is written against specific shape IDs in this exact file,
  so a structurally different template will need the shape IDs re-derived
  (open the template, dump shape IDs + text with python-pptx per slide, and
  update the `*_ids` dictionaries in `fill_deck.py` accordingly).
