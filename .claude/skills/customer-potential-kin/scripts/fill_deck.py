#!/usr/bin/env python3
"""
Takes the Kin Analytics Customer Potential Results template + content.json
(produced by generate_content.py) and writes the final .pptx with slides 1,
9-13 and 15 populated (and, with --map-image, the map screenshot on slide 14).
Slides 2-8 and 16 are copied through untouched.

The template (assets/Customer_Potential_Results_Template.pptx) is the deck the
team handed over on 2026-10-23: a finished Femsa Venezuela deck. Every
operation-specific shape is overwritten by shape ID below; at the end the
script refuses to save if any Venezuela text survived (LEFTOVERS). If the
template changes, re-derive the IDs (dump shape IDs + text per slide with
python-pptx) and update LEFTOVERS with the new sample operation's words.

Usage:
    python fill_deck.py --template assets/Customer_Potential_Results_Template.pptx \
        --content content.json --output Final_Deck.pptx [--map-image mapa.png]
"""
import argparse
import json
import math
import sys
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.util import Emu

SEGMENT_ORDER = ["Very High", "High", "Moderate", "Low"]
# words of the template's sample operation that must not survive in a filled deck
LEFTOVERS = ["Femsa", "Venezuela", "Maracaibo", "Zulia", "Caracas", "Cabimas", "Chiquinquirá", "Ojeda",
             "Valencia", "Cristóbal", "ABL", "PND", "OHM", "FAR", "Gaseosa", "991220", "45,197", "392.6K"]

# ---- geometry constants measured from the template (EMU) ----
CLIENT_BAR_CONTAINER_WIDTH = 3635654   # slide10 stacked "distribución de clientes" bar, sum of 4 segments
CLIENT_BAR_START_LEFT = 475488
POTENTIAL_BAR_TRACK_WIDTH = 3566100    # slide10 horizontal potential bars, fixed background width
POTENTIAL_BAR_LEFT = 4892040           # slide10 potential bars, fixed left edge of the track
POTENTIAL_VALUE_GAP = 54852            # gap between end of a potential bar and its value text
POTENTIAL_VALUE_WIDTH = 640200         # fixed width of the value text box (e.g. "47.2K")
POTENTIAL_PCT_GAP = 18168              # gap between end of value text and its % text
CITY_BAR_TRACK_WIDTH = 4114800         # slide12 potential-per-PDV bars
CITY_BAR_LEFT = 2011680
CITY_VALUE_GAP = 91440                 # gap between end of a bar and its value text
BUBBLE_MAX_DIAM = 1243500              # slide13 largest bubble slot

CANAL = {  # slide 9 filter card + slide 10 KPI caption, by manual["canal"]
    "tradicional": ("Canal tradicional", "Canal moderno excluido"),
    "moderno": ("Canal moderno", "Supermercados, hipermercados y autoservicios"),
    "ambos": ("Canal tradicional y moderno", "Ambos canales incluidos"),
}


def shapes_by_id(slide):
    return {sh.shape_id: sh for sh in slide.shapes}


def set_run_text(shape, text):
    """Overwrite the text of a shape with a single line, preserving the first run's formatting.

    Some template shapes hold a name pre-wrapped across two paragraphs ('San' / 'Cristóbal'): write
    into paragraph 0 and blank every paragraph after it, so no leftover half-name survives.
    """
    tf = shape.text_frame
    p = tf.paragraphs[0]
    if not p.runs:
        p.add_run()
    p.runs[0].text = text
    for r in p.runs[1:]:
        r.text = ""
    for extra_p in tf.paragraphs[1:]:
        for r in extra_p.runs:
            r.text = ""


def set_paragraph_text(shape, para_idx, text):
    p = shape.text_frame.paragraphs[para_idx]
    if not p.runs:
        p.add_run()
    p.runs[0].text = text
    for r in p.runs[1:]:
        r.text = ""


def set_left_and_width(shape, new_left, new_width):
    shape.left = Emu(int(new_left))
    shape.width = Emu(int(new_width))


def recenter_square(shape, new_diam):
    cx = shape.left + shape.width / 2
    cy = shape.top + shape.height / 2
    new_diam = int(new_diam)
    shape.width = Emu(new_diam)
    shape.height = Emu(new_diam)
    shape.left = Emu(int(cx - new_diam / 2))
    shape.top = Emu(int(cy - new_diam / 2))


def fill_slide1(slide, content):
    ids = shapes_by_id(slide)
    man = content["manual"]
    set_run_text(ids[19], f"{man['embotelladora']} {man.get('pais', '')}".strip())
    set_run_text(ids[21], f"{man.get('pais', '')}  ·  {man['mes_anio']}")


def fill_slide9(slide, content):
    ids = shapes_by_id(slide)
    man = content["manual"]
    canal, excluido = CANAL[man.get("canal", "tradicional")]
    set_run_text(ids[392], canal)
    set_run_text(ids[393], excluido)
    # 421: para0 = descriptive text (unchanged), para2 = "<n> Cantidad de clientes de canal X a <fecha>"
    # the client master's own count (manual cantidad_registros), not the segmented PDVs of slide 10
    set_paragraph_text(ids[421], 2, f"{int(man['cantidad_registros']):,} Cantidad de clientes de "
                                     f"{canal.lower()} a {man['fecha_clientes'].lower()}")
    # 414: para0 = "Promedio mensual en Unit Cases por PDV" (unchanged), para1 = scope of the run
    set_paragraph_text(ids[414], 1, f"-  {content['display']['s9']['portfolio_scope_line']}")


def fill_slide10(slide, content):
    ids = shapes_by_id(slide)
    d = content["display"]["s10"]
    raw = content["raw"]["s10"]
    copy = content["copy"]["s10"]

    set_run_text(ids[434], d["total_pdvs"])
    set_run_text(ids[436], CANAL[content["manual"].get("canal", "tradicional")][0])
    set_run_text(ids[438], d["total_current_uc"])
    set_run_text(ids[442], d["total_potential_uc"])
    set_run_text(ids[446], d["overall_growth_pct"])

    set_paragraph_text(ids[432], 0, copy["headline_line1"])
    set_paragraph_text(ids[432], 1, copy["headline_line2"])
    set_run_text(ids[494], copy["callout"])

    # stacked client-distribution bar: VH, High, Moderate, Low laid out contiguously
    block_ids = {"Very High": 451, "High": 452, "Moderate": 454, "Low": 456}
    label_ids = {"High": 453, "Moderate": 455, "Low": 457}  # VH label omitted (template convention: too narrow)
    count_ids = {"Very High": 466, "High": 467, "Moderate": 468, "Low": 469}

    cursor = CLIENT_BAR_START_LEFT
    for seg in SEGMENT_ORDER:
        width = raw["seg_pct_clients"][seg] / 100.0 * CLIENT_BAR_CONTAINER_WIDTH
        set_left_and_width(ids[block_ids[seg]], cursor, width)
        if seg in label_ids:
            lbl = ids[label_ids[seg]]
            set_left_and_width(lbl, cursor, width)
            set_run_text(lbl, d["seg_pct"][seg])
        set_run_text(ids[count_ids[seg]], d["seg_count"][seg])
        cursor += width

    # horizontal potential bars
    fill_ids = {"Very High": 474, "High": 479, "Moderate": 484, "Low": 489}
    value_ids = {"Very High": 476, "High": 481, "Moderate": 486, "Low": 491}
    pct_ids = {"Very High": 477, "High": 482, "Moderate": 487, "Low": 492}
    for seg in SEGMENT_ORDER:
        width = max(raw["seg_pct_potential"][seg] / 100.0 * POTENTIAL_BAR_TRACK_WIDTH, 1)
        value_shape, pct_shape = ids[value_ids[seg]], ids[pct_ids[seg]]
        # the template's own text position is a floor (it clears the segment label at the start of the
        # track); text only moves further right when the real bar is longer than the sample's
        original_value_left, original_pct_left = value_shape.left, pct_shape.left
        ids[fill_ids[seg]].width = Emu(int(width))
        set_run_text(value_shape, d["seg_potential_value"][seg])
        set_run_text(pct_shape, d["seg_potential_pct"][seg])
        value_shape.left = Emu(int(max(POTENTIAL_BAR_LEFT + width + POTENTIAL_VALUE_GAP, original_value_left)))
        pct_shape.left = Emu(int(max(value_shape.left + POTENTIAL_VALUE_WIDTH + POTENTIAL_PCT_GAP, original_pct_left)))


def fill_slide11(slide, content):
    ids = shapes_by_id(slide)
    rows = content["display"]["s11"]["rows"]
    set_run_text(ids[504], content["display"]["s11_header"])
    # per row, in column order: [pdvs, pct_clients, sales_uc, potential_uc, avg_potential_pdv, growth_pct, pct_potential]
    row_ids = {
        "Very High": [520, 521, 522, 523, 524, 525, 526],
        "High": [530, 531, 532, 533, 534, 535, 536],
        "Moderate": [539, 540, 541, 542, 543, 544, 545],
        "Low": [548, 549, 550, 551, 552, 553, 554],
        "Total": [557, 558, 559, 560, 561, 562, 563],
    }
    cols = ["pdvs", "pct_clients", "sales_uc", "potential_uc", "avg_potential_pdv", "growth_pct", "pct_potential"]
    for seg, shape_ids in row_ids.items():
        for sid, col in zip(shape_ids, cols):
            set_run_text(ids[sid], rows[seg][col])


def fill_slide12(slide, content):
    """¿Dónde rinde más cada visita? — potential per PDV by city (generate_content.py's s12_ciudad)."""
    ids = shapes_by_id(slide)
    rows = content["display"]["s12_ciudad"]["rows"]
    copy = content["copy"]["s12_ciudad"]
    slots = [  # name, fill bar, value, PDV count (+ TOP 2 tag shapes on the first two rows)
        {"name": 576, "fill": 578, "value": 579, "pdvs": 581, "tag": (582, 583)},
        {"name": 584, "fill": 586, "value": 587, "pdvs": 589, "tag": (590, 591)},
        {"name": 592, "fill": 594, "value": 595, "pdvs": 597},
        {"name": 598, "fill": 600, "value": 601, "pdvs": 603},
        {"name": 604, "fill": 606, "value": 607, "pdvs": 609},
        {"name": 610, "fill": 612, "value": 613, "pdvs": 615},
    ]
    max_val = max((r["per_pdv"] for r in rows), default=0)
    for slot, row in zip(slots, rows + [None] * (len(slots) - len(rows))):
        if row is None:
            for k in ("name", "value", "pdvs"):
                set_run_text(ids[slot[k]], "")
            ids[slot["fill"]].width = Emu(1)
            continue
        width = max(row["per_pdv"] / max_val * CITY_BAR_TRACK_WIDTH if max_val else 0, 1)
        ids[slot["fill"]].width = Emu(int(width))
        set_run_text(ids[slot["name"]], row["name"])
        set_run_text(ids[slot["value"]], row["value_display"])
        ids[slot["value"]].left = Emu(int(CITY_BAR_LEFT + width + CITY_VALUE_GAP))
        set_run_text(ids[slot["pdvs"]], row["pdvs_display"])
    set_run_text(ids[575], copy["headline"])
    set_run_text(ids[618], copy["callout"])


def fill_slide13(slide, content):
    ids = shapes_by_id(slide)
    cities = content["display"]["s13"]["cities"]
    subchannels = content["display"]["s13"]["subchannels"]
    copy = content["copy"]["s13"]

    set_paragraph_text(ids[630], 0, copy["headline_line1"])
    set_paragraph_text(ids[630], 1, copy["headline_line2"])
    set_run_text(ids[672], copy["callout"])

    bubble_slots = [
        {"bubble": 631, "name": 632, "value": 633},
        {"bubble": 634, "name": 635, "value": 636},
        {"bubble": 637, "name": 638, "value": 639},
        {"bubble": 640, "name": 641, "value": None},
        {"bubble": 642, "name": 643, "value": None},
        {"bubble": 644, "name": 645, "value": None},
    ]
    max_val = max((_uc_to_number(c["value_display"]) for c in cities), default=0)
    for slot, city in zip(bubble_slots, cities + [None] * (6 - len(cities))):
        bubble, name_shape = ids[slot["bubble"]], ids[slot["name"]]
        value_shape = ids[slot["value"]] if slot["value"] else None
        if city is None:
            recenter_square(bubble, 1)  # shrink to invisible
            set_run_text(name_shape, "")
            if value_shape is not None:
                set_run_text(value_shape, "")
            continue
        val = _uc_to_number(city["value_display"])
        diam = BUBBLE_MAX_DIAM * math.sqrt(val / max_val) if max_val else BUBBLE_MAX_DIAM
        recenter_square(bubble, max(diam, BUBBLE_MAX_DIAM * 0.15))
        set_run_text(name_shape, city["name"])
        if value_shape is not None:
            set_run_text(value_shape, city["value_display"])

    subchan_slots = [(650, 651, 652), (655, 656, 657), (659, 660, 661), (663, 664, 665), (667, 668, 669)]
    for (n, det, pct), sc in zip(subchan_slots, subchannels + [None] * (5 - len(subchannels))):
        set_run_text(ids[n], sc["name"] if sc else "")
        set_run_text(ids[det], sc["detail"] if sc else "")
        set_run_text(ids[pct], sc["pct_display"] if sc else "")


def _uc_to_number(display):
    """'29.7K UC' -> 29700.0, '210.6K' -> 210600.0, '2.4M' -> 2400000.0"""
    s = display.replace("UC", "").strip()
    mult = 1
    if s.endswith("K"):
        mult, s = 1_000, s[:-1]
    elif s.endswith("M"):
        mult, s = 1_000_000, s[:-1]
    return float(s) * mult


def fill_slide14(slide, image_path):
    """Swap the template's map screenshot (shape 689) for this operation's, cropped to the same box.

    Keeps the top-left corner (the map's panel header and KPIs, as in the template); crops right or bottom.
    """
    old = shapes_by_id(slide)[689]
    box_ratio = old.width / old.height
    img = Image.open(image_path)
    w, h = img.size
    if w / h > box_ratio:
        img = img.crop((0, 0, int(h * box_ratio), h))
    else:
        img = img.crop((0, 0, w, int(w / box_ratio)))
    cropped = Path(image_path).with_name(Path(image_path).stem + "_recorte.png")
    img.save(cropped)
    new = slide.shapes.add_picture(str(cropped), old.left, old.top, old.width, old.height)
    old._element.addprevious(new._element)  # keep the template's z-order
    old._element.getparent().remove(old._element)


def fill_slide15(slide, content):
    ids = shapes_by_id(slide)
    rows = content["display"]["s15"]["rows"]
    copy = content["copy"]["s15"]
    row_shape_ids = [
        [711, 712, 713, 714, 715, 717, 718],
        [721, 722, 723, 724, 725, 727, 728],
        [731, 732, 733, 734, 735, 737, 738],
        [741, 742, 743, 744, 745, 747, 748],
        [751, 752, 753, 754, 755, 757, 758],
    ]
    cols = ["pdv_id", "city", "subchannel", "potential_uc", "growth_pct", "priority_category", "potential_in_category"]
    for shape_ids, row in zip(row_shape_ids, rows + [None] * (5 - len(rows))):
        for sid, col in zip(shape_ids, cols):
            set_run_text(ids[sid], row[col] if row else "")
    set_run_text(ids[700], copy["subhead"])
    set_run_text(ids[760], copy["example_title"])
    set_paragraph_text(ids[761], 0, copy["example_sentence1"])
    set_paragraph_text(ids[761], 1, copy["example_sentence2"])


def leftovers(prs, content):
    # a word that this run's own data also uses (e.g. a Femsa Venezuela run) is not a leftover
    own = json.dumps(content, ensure_ascii=False)
    words = [w for w in LEFTOVERS if w not in own]
    found = []
    for i, slide in enumerate(prs.slides, 1):
        for sh in slide.shapes:
            if sh.has_text_frame:
                found += [f"slide {i}: {w}" for w in words if w in sh.text_frame.text]
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--template", required=True)
    ap.add_argument("--content", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--map-image", help="screenshot of the interactive map for slide 14")
    args = ap.parse_args()

    content = json.loads(Path(args.content).read_text(encoding="utf-8"))
    prs = Presentation(args.template)

    fill_slide1(prs.slides[0], content)
    fill_slide9(prs.slides[8], content)
    fill_slide10(prs.slides[9], content)
    fill_slide11(prs.slides[10], content)
    fill_slide12(prs.slides[11], content)
    fill_slide13(prs.slides[12], content)
    if args.map_image:
        fill_slide14(prs.slides[13], args.map_image)
    fill_slide15(prs.slides[14], content)

    quedan = leftovers(prs, content)
    if quedan:
        sys.exit("fill_deck.py: template text survived (not saved): " + "; ".join(quedan))
    prs.save(args.output)
    print(f"Wrote {args.output}")
    if not args.map_image:
        print("Warning: no --map-image, slide 14 still shows the template's map screenshot.")


if __name__ == "__main__":
    main()
