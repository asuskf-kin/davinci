#!/usr/bin/env python3
"""
Inserts ONE extra, data-driven slide into an already-built Customer Potential
deck, styled to match the Kin Analytics template exactly (same fonts, same
black/white/E5FF01 palette, same bar/bubble mechanics as slides 12 and 13).

Why this exists: the standard 16-slide deck is deliberately rigid (same
structure every run, for brand consistency and speed) but that means it can
miss the specific thing that's actually interesting about a given
operation's data -- e.g. a city that's small but has unusually high potential
per PDV, a subchannel that over-indexes on one category, a handful of PDVs
whose growth rate is wildly out of line with their segment. This script
doesn't decide WHAT to show -- that's a judgment call to make by looking at
`content.json`'s "exploratory" section (see generate_content.py) and the raw
data. It only handles turning that judgment call into an on-brand slide.

Two layouts are available, both capped at 6 items (matching the template's
own row/bubble slots -- more than 6 stops being readable at this text size):

  --layout bar     a ranked horizontal-bar list (same mechanic as slide 12's
                    category ranking) -- good for "top N of X by value"
  --layout bubble  a sized-bubble cluster + a secondary ranked list (same
                    mechanic as slide 13) -- good for geographic or
                    categorical clustering, optionally with a second metric
                    called out per item (e.g. "149 UC/PDV promedio")

This script does NOT duplicate the slide itself -- that needs the pptx
skill's own `add_slide.py`, which lives in that skill's own directory (a
different skill, at a path this one shouldn't hardcode). The two-step dance:

    1. Use the pptx skill's add_slide.py to duplicate slide12.xml (for a
       "bar" layout) or slide13.xml (for a "bubble" layout) into the deck,
       positioned with --after wherever it belongs. It prints the new
       slide's number, e.g. "Created ppt/slides/slide17.xml".
    2. Run this script against that same file, telling it which slide
       number it just created, to overwrite that slide's content:

    python restyle_insight_slide.py --pptx deck_with_extra_slide.pptx \
        --layout bar --spec insight_spec.json --slide-number 14 \
        --output deck_final.pptx

See references/insight-slides.md for the exact spec JSON shape and examples,
and SKILL.md's "optional insight slide" step for when to use this at all.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from pptx import Presentation

from fill_deck import (
    set_run_text, set_paragraph_text, set_width_keep_left,
    recenter_square, shapes_by_id, CATEGORY_BAR_TRACK_WIDTH, CATEGORY_BAR_LEFT,
    CATEGORY_VALUE_GAP, BUBBLE_MAX_DIAM,
)

BAR_ROW_SHAPES = [
    {"name": 587, "fill": 589, "value": 590, "metric": 592, "highlight_bg": 593, "highlight_text": 594},
    {"name": 595, "fill": 597, "value": 598, "metric": 600, "highlight_bg": 601, "highlight_text": 602},
    {"name": 603, "fill": 605, "value": 606, "metric": 608, "highlight_bg": None, "highlight_text": None},
    {"name": 609, "fill": 611, "value": 612, "metric": 614, "highlight_bg": None, "highlight_text": None},
    {"name": 615, "fill": 617, "value": 618, "metric": 620, "highlight_bg": None, "highlight_text": None},
    {"name": 621, "fill": 623, "value": 624, "metric": 626, "highlight_bg": None, "highlight_text": None},
]
BAR_HEADER_ID, BAR_TITLE_ID, BAR_SUBTITLE_ID = 583, 585, 586
BAR_CALLOUT_LEAD_ID, BAR_CALLOUT_REST_ID = 628, 629

BUBBLE_SLOTS = [
    {"bubble": 640, "name": 641, "value": 642},
    {"bubble": 643, "name": 644, "value": 645},
    {"bubble": 646, "name": 647, "value": 648},
    {"bubble": 649, "name": 650, "value": None},
    {"bubble": 651, "name": 652, "value": None},
    {"bubble": 653, "name": 654, "value": None},
]
BUBBLE_LIST_SLOTS = [
    {"name": 659, "detail": 660, "pct": 661},
    {"name": 664, "detail": 665, "pct": 666},
    {"name": 668, "detail": 669, "pct": 670},
    {"name": 672, "detail": 673, "pct": 674},
    {"name": 676, "detail": 677, "pct": 678},
]
BUBBLE_HEADER_ID, BUBBLE_TITLE_ID, BUBBLE_LIST_HEADER_ID = 637, 639, 656
BUBBLE_CALLOUT_LEAD_ID, BUBBLE_CALLOUT_REST_ID = 680, 681
BUBBLE_UNIT_LABEL_ID = 655


def find_slide_by_number(prs, slide_number):
    """slide_number is 1-based *display position* in the deck (what you'd
    call it in conversation - "slide 14"). prs.slides iterates in the deck's
    real display order (the <p:sldIdLst> order), not by XML filename, so
    this works regardless of what add_slide.py happened to name the new
    slide's XML part."""
    idx = slide_number - 1
    if not (0 <= idx < len(prs.slides)):
        sys.exit(f"restyle_insight_slide.py: slide-number {slide_number} out of range (deck has {len(prs.slides)} slides)")
    return prs.slides[idx]


def restyle_bar_slide(slide, spec):
    ids = shapes_by_id(slide)
    set_run_text(ids[BAR_HEADER_ID], spec.get("eyebrow", ""))
    set_run_text(ids[BAR_TITLE_ID], spec["title"])
    set_run_text(ids[BAR_SUBTITLE_ID], spec.get("subtitle", ""))

    items = spec["items"][:6]
    max_val = max(i["value"] for i in items) if items else 1
    n_highlight = spec.get("highlight_top_n", 0)

    for row, item in zip(BAR_ROW_SHAPES, items + [None] * (6 - len(items))):
        if item is None:
            for key in ("name", "fill", "value", "metric"):
                if row[key] is not None:
                    set_run_text(ids[row[key]], "")
            if row["highlight_bg"] is not None:
                set_run_text(ids[row["highlight_bg"]], "")
                set_run_text(ids[row["highlight_text"]], "")
            continue
        set_run_text(ids[row["name"]], item["label"])
        set_run_text(ids[row["metric"]], item.get("metric_display", ""))
        fill_width = (item["value"] / max_val) * CATEGORY_BAR_TRACK_WIDTH if max_val else 0
        set_width_keep_left(ids[row["fill"]], max(fill_width, 1))
        value_shape = ids[row["value"]]
        set_run_text(value_shape, item.get("value_display", str(item["value"])))
        value_shape.left = value_shape.left.__class__(int(CATEGORY_BAR_LEFT + fill_width + CATEGORY_VALUE_GAP))

    # highlight_bg (593/601) is a bare black pill shape with no text of its own -
    # highlight_text (594/602) is the label rendered on top of it. It's sized for a
    # short word like "PRIORIDAD" (~10 chars) - keep highlight_label that short or
    # it wraps and spills into the row below.
    for i, row in enumerate(BAR_ROW_SHAPES):
        if row["highlight_text"] is None:
            continue
        show = i < n_highlight and i < len(items)
        set_run_text(ids[row["highlight_text"]], spec.get("highlight_label", "DESTACADO") if show else "")

    if spec.get("callout"):
        lead, _, rest = spec["callout"].partition(" — ")
        set_run_text(ids[BAR_CALLOUT_LEAD_ID], lead + (" —" if rest else ""))
        set_run_text(ids[BAR_CALLOUT_REST_ID], rest or spec["callout"])
    else:
        set_run_text(ids[BAR_CALLOUT_LEAD_ID], "")
        set_run_text(ids[BAR_CALLOUT_REST_ID], "")


def _uc_like_to_number(display):
    s = str(display).upper().replace(",", "").strip()
    for suffix, mult in (("K", 1_000), ("M", 1_000_000)):
        if s.endswith(suffix):
            try:
                return float(s[:-1]) * mult
            except ValueError:
                pass
    try:
        return float(re.sub(r"[^0-9.\-]", "", s) or 0)
    except ValueError:
        return 0.0


def restyle_bubble_slide(slide, spec):
    ids = shapes_by_id(slide)
    set_run_text(ids[BUBBLE_HEADER_ID], spec.get("eyebrow", ""))
    set_paragraph_text(ids[BUBBLE_TITLE_ID], 0, spec.get("title_line1", spec.get("title", "")))
    set_paragraph_text(ids[BUBBLE_TITLE_ID], 1, spec.get("title_line2", ""))
    set_run_text(ids[BUBBLE_UNIT_LABEL_ID], spec.get("bubble_unit_label", "Tamaño = valor"))
    set_run_text(ids[BUBBLE_LIST_HEADER_ID], spec.get("list_header", ""))

    bubbles = spec.get("bubbles", [])[:6]
    max_val = max((b["value"] for b in bubbles), default=1)
    for slot, item in zip(BUBBLE_SLOTS, bubbles + [None] * (6 - len(bubbles))):
        bubble = ids[slot["bubble"]]
        name_shape = ids[slot["name"]]
        value_shape = ids[slot["value"]] if slot["value"] else None
        if item is None:
            recenter_square(bubble, 1)
            set_run_text(name_shape, "")
            if value_shape is not None:
                set_run_text(value_shape, "")
            continue
        import math
        diam = BUBBLE_MAX_DIAM * math.sqrt(item["value"] / max_val) if max_val else BUBBLE_MAX_DIAM
        recenter_square(bubble, max(diam, BUBBLE_MAX_DIAM * 0.15))
        set_run_text(name_shape, item["label"])
        if value_shape is not None:
            set_run_text(value_shape, item.get("value_display", str(item["value"])))

    list_items = spec.get("list_items", [])[:5]
    for slot, item in zip(BUBBLE_LIST_SLOTS, list_items + [None] * (5 - len(list_items))):
        if item is None:
            set_run_text(ids[slot["name"]], "")
            set_run_text(ids[slot["detail"]], "")
            set_run_text(ids[slot["pct"]], "")
            continue
        set_run_text(ids[slot["name"]], item["label"])
        set_run_text(ids[slot["detail"]], item.get("detail", ""))
        set_run_text(ids[slot["pct"]], item.get("value_display", ""))

    if spec.get("callout"):
        set_run_text(ids[BUBBLE_CALLOUT_LEAD_ID], spec.get("callout_lead", "Nota —"))
        set_run_text(ids[BUBBLE_CALLOUT_REST_ID], spec["callout"])
    else:
        set_run_text(ids[BUBBLE_CALLOUT_LEAD_ID], "")
        set_run_text(ids[BUBBLE_CALLOUT_REST_ID], "")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pptx", required=True,
                     help="deck that already has the duplicated blank-ish slide in it "
                          "(i.e. you already ran the pptx skill's add_slide.py)")
    ap.add_argument("--layout", required=True, choices=["bar", "bubble"],
                     help="must match what you duplicated: slide12.xml -> bar, slide13.xml -> bubble")
    ap.add_argument("--spec", required=True, help="JSON file with the slide's title/items/callout")
    ap.add_argument("--slide-number", required=True, type=int,
                     help="1-based display position of the slide add_slide.py just created")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))

    prs = Presentation(args.pptx)
    slide = find_slide_by_number(prs, args.slide_number)
    if args.layout == "bar":
        restyle_bar_slide(slide, spec)
    else:
        restyle_bubble_slide(slide, spec)
    prs.save(args.output)
    print(f"Restyled slide {args.slide_number} as a '{args.layout}' insight slide; wrote {args.output}")


if __name__ == "__main__":
    main()
