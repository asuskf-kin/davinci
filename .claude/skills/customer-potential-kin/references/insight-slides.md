# Optional insight slides

The 16-slide deck is deliberately the same structure every time — that's
what makes it fast and on-brand. But it can genuinely miss the most
interesting thing about a specific operation's data: a city that's small
but punches way above its weight, a subchannel that over-indexes on one
category, a handful of PDVs whose growth is wildly out of line with their
peers. `generate_content.py` computes a `raw.exploratory` section
specifically so you can look for that story — it is not used by any of the
fixed slides.

**Use judgment, don't force it.** Most runs won't need an extra slide. Only
add one if something in `exploratory` is genuinely surprising or would
change what the bottler does Monday morning. A forced, obvious, or
low-contrast "insight" is worse than no insight slide at all.

## What's in `raw.exploratory`

- `top_cities_by_potential_density` — cities ranked by potential-per-PDV
  (not just total potential). A city near the top here with a small
  `pdv_count` is the "small but mighty" story.
- `top_cities_by_pdv_volume` — the biggest markets by PDV count. Compare
  against the density ranking: if the two lists barely overlap, that's
  usually worth a slide (visiting for volume vs. visiting for yield are
  different strategies).
- `hidden_gem_cities` — already pre-filtered to below-median PDV count +
  top-quartile density, i.e. candidates for "you're probably under-visiting
  these."
- `subchannel_top_category` — for each subchannel (VH+High clients), which
  category has the most potential in it. Useful if one subchannel is
  clearly the way into a specific category that slide 12 doesn't call out.
- `growth_outlier_pdvs` — individual PDVs whose growth % is a real outlier
  (z-score ≥ 1.5) versus their own segment's average — a different cut
  than slide 15's "top 5 by potential," since a PDV can have huge relative
  upside without being a top-5 absolute number.

Feel free to compute something else from the CSV directly if none of these
capture it — this list is a starting point, not a ceiling.

## Building the slide once you've found something

Two layouts, both capped at 6 items:

- **`bar`** — ranked horizontal bars (same mechanic as slide 12). Good for
  "top N of X by value," optionally with a secondary metric per row (shown
  where slide 12 shows the growth %) and up to 2 rows highlighted with a
  short badge (≤10 characters — it's a small pill, sized for "PRIORIDAD").
- **`bubble`** — a sized-bubble cluster + a secondary ranked list (same
  mechanic as slide 13). Good for geographic or categorical clustering.

Two steps:

1. Duplicate a source slide with the pptx skill's own `add_slide.py`
   (**not** this skill's — it lives in the pptx skill's own directory):
   ```
   python <pptx-skill-path>/scripts/add_slide.py deck.pptx slide12.xml \
       --after slide13.xml -o deck_with_slot.pptx
   ```
   Use `slide12.xml` as the source for a `bar` layout, `slide13.xml` for
   `bubble`. `--after` controls where it lands — inserting after slide 13
   (before the map placeholder) or after slide 15 (before the closing
   slide) both read naturally; use your judgment about where the story
   fits the narrative flow. The command prints which slide number it
   ended up at, e.g. "position 14 of 17".

2. Restyle that slide with this skill's script, using the number from
   step 1:
   ```
   python scripts/restyle_insight_slide.py --pptx deck_with_slot.pptx \
       --layout bar --spec insight_spec.json --slide-number 14 \
       --output deck_final.pptx
   ```

### `bar` spec shape

```json
{
  "eyebrow": "HALLAZGO · POTENCIAL POR VISITA",
  "title": "No todas las ciudades valen lo mismo por visita.",
  "subtitle": "One or two sentences giving the actual number/comparison.",
  "highlight_top_n": 2,
  "highlight_label": "TOP DENSIDAD",
  "items": [
    {"label": "Bahía de Banderas", "value": 112.5, "value_display": "112.5 UC/PDV", "metric_display": "250 PDVs"}
  ],
  "callout": "Lead-in sentence — rest of the callout."
}
```
`value` drives the bar's length (relative to the max across `items`);
`value_display`/`metric_display` are just labels, format them however
reads best. `callout` splits on the first " — " into a bold lead-in and
plain rest, matching the template's own callout style; if there's no
" — " the whole string becomes the lead-in.

### `bubble` spec shape

```json
{
  "eyebrow": "HALLAZGO · MERCADOS ELITE",
  "title_line1": "Tres ciudades chicas,",
  "title_line2": "el mayor rendimiento por PDV.",
  "bubble_unit_label": "Tamaño = potencial por PDV",
  "list_header": "PDVs vs. RENDIMIENTO",
  "bubbles": [{"label": "Bahía de Banderas", "value": 112.5, "value_display": "112.5 UC/PDV"}],
  "list_items": [{"label": "Bahía de Banderas", "detail": "250 PDVs · 112.5 UC/PDV", "value_display": "16x"}],
  "callout_lead": "Lectura —",
  "callout": "The rest of the sentence."
}
```
`bubbles` takes up to 6 (first 3 get a value label under the name, the
rest are name-only — matches the template's own convention for its
smaller circles). `list_items` takes up to 5.

## After inserting

Re-render and look at it — same as any other slide (see SKILL.md's visual
QA step). Long labels can wrap inside these fixed-width boxes; if
something overflows, shorten the label rather than fighting the layout.
