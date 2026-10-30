"""Tablero comparativo de territorios (p. ej. Mérida vs CDMX) para cadenas de retail: visual, poco texto, marca Kin.

Vista "Juntos" (todo sumado) o "Separados" (un panel por territorio, misma escala para comparar): KPIs y barras cara a
cara, mapa interactivo de hexágonos H3 (un mapa o dos lado a lado), tendencias (valores o índice 100), productos del
catálogo validado y top de tiendas. Datos embebidos como cubos; sin coordenadas de PdV (solo IDs de hexágono).
"""
import json

import h3
import numpy as np
import pandas as pd

from src.tools import marca

def _cubo(df, dims, medidas):
    out = {"dic": {}, "col": {}}
    for d in dims:
        cat = pd.Categorical(df[d].fillna("(vacío)").astype(str))
        out["dic"][d], out["col"][d] = list(cat.categories), cat.codes.tolist()
    for m in medidas:
        out["col"][m] = np.round(df[m].astype(float).fillna(0).to_numpy(), 2).tolist()
    return out


def con_producto(v, cat):
    """Une el catálogo validado: `producto` = descripción del catálogo (cada ciudad con su propio catálogo)."""
    if cat is None:
        return v.assign(producto=v["product_id"], Segmento=None, brand=None)
    atr = cat.reset_index()[["embotellador", "product_id", "Descripción", "Segmento", "brand"]]
    v = v.merge(atr, on=["embotellador", "product_id"], how="left")
    return v.assign(producto=v["Descripción"].fillna(v["product_id"]))


def _franquicia_producto(d, vt, cat, meta):
    """Qué vende cada franquicia en cada ciudad: tiendas únicas que compraron cada producto en 12m y revenue."""
    tiendas = d[d["tipo_punto"].eq("Tienda")]
    u = pd.concat([vt[vt["territorio"].eq(t) & vt["month_445"].isin(m["ult12"])] for t, m in meta.items()])
    u = con_producto(u[(u["revenue"] > 0) & u["pos_id"].isin(tiendas["pos_id"])], cat)
    if "franquicia" not in u:
        u = u.join(tiendas.set_index("pos_id")["franquicia"], on="pos_id")
    g = u.groupby(["territorio", "franquicia", "producto"]).agg(n=("pos_id", "nunique"), rev=("revenue", "sum")).reset_index()
    den = tiendas.groupby(["territorio", "franquicia"]).size()
    return {"filas": g.round(2).to_dict("records"), "den": {f"{t}|{f}": int(n) for (t, f), n in den.items()}}


def top_ciudad(u, n=None):
    """Top de productos de cada ciudad por revenue 12m (los catálogos no coinciden: cada ciudad con su propio top)."""
    g = u.groupby(["territorio", "producto"]).agg(segmento=("Segmento", "first"), marca=("brand", "first"), rev=("revenue", "sum"),
                                                  tiendas=("pos_id", "nunique"),
                                                  franquicias=("franquicia", lambda s: ", ".join(s.value_counts().index[:4]))).reset_index()
    g["pct_rev"] = g["rev"] / g.groupby("territorio")["rev"].transform("sum")
    g["rank"] = g.groupby("territorio")["rev"].rank(ascending=False, method="first").astype(int)
    g = g.sort_values(["territorio", "rank"])
    return g if n is None else g[g["rank"] <= n]


def escribir(ruta, d, vv, cat, meta, analisis, foco):
    terrs = list(dict.fromkeys(d["territorio"]))
    t = d.assign(nombre=d["cliente"].fillna(""), comp=(d["revenue_12m"] > 0).astype(int), ing=d["ingreso"],
                 pot=d["potencial_cajas_mes"], ult=d["ultimo_mes"].fillna(""))
    tiendas = _cubo(t, ["territorio", "cadena", "franquicia", "formato", "tipo_punto", "estatus", "prioridad", "municipio", "ult"],
                    ["revenue_12m", "revenue_12m_anterior", "cajas_12m", "ing", "pot", "comp"])
    tiendas["col"]["nombre"], tiendas["col"]["pos_id"] = t["nombre"].tolist(), t["pos_id"].tolist()
    tiendas["col"]["celda"] = [h3.latlng_to_cell(a, b, 10) if pd.notna(a) and pd.notna(b) else "" for a, b in zip(t["lat"], t["lon"])]
    tiendas["col"]["ing_nulo"] = t["ingreso"].isna().astype(int).tolist()

    vt = vv.join(d.set_index("pos_id")[["tipo_punto", "franquicia"]], on="pos_id")
    mens = vt.groupby(["territorio", "cadena", "franquicia", "tipo_punto", "month_445"]).agg(
        rev=("revenue", "sum"), cj=("unit_cases", "sum"), pdv=("pos_id", "nunique")).reset_index()
    mensual = _cubo(mens, ["territorio", "cadena", "franquicia", "tipo_punto", "month_445"], ["rev", "cj", "pdv"])

    partes = []
    for nombre, m in meta.items():
        u = m["ult12"]
        a = [str(int(x) - 100) for x in u]
        x = vt[(vt["territorio"] == nombre) & vt["month_445"].isin(u + a)]
        partes.append(x.assign(ventana=np.where(x["month_445"].isin(u), "12m", "ant")))
    p = pd.concat(partes)
    if cat is not None:
        atr = cat.reset_index()[["embotellador", "product_id", "Descripción", "Segmento", "brand", "presentacion"]]
        p = p.merge(atr, on=["embotellador", "product_id"], how="left")
    for c in ("Descripción", "Segmento", "brand", "presentacion"):
        p[c] = p.get(c, pd.Series(index=p.index, dtype=object)).fillna("(sin catálogo)")
    prod = p.groupby(["territorio", "cadena", "tipo_punto", "Descripción", "Segmento", "brand", "presentacion", "ventana"]).agg(
        rev=("revenue", "sum"), cj=("unit_cases", "sum"), pdv=("pos_id", "nunique")).reset_index()
    productos = _cubo(prod, ["territorio", "cadena", "tipo_punto", "Descripción", "Segmento", "brand", "presentacion", "ventana"],
                      ["rev", "cj", "pdv"])

    orden = list(dict.fromkeys(foco + sorted(set(d["cadena"]) - {"Independientes"}) + ["Independientes"]))
    datos = {"analisis": analisis, "terrs": terrs, "foco": foco,
             "otras": sorted(d.loc[d["cadena"].eq("Otras cadenas"), "franquicia"].unique().tolist()), "orden": [c for c in orden if c in set(d["cadena"])],
             # solo se comparan indicadores que existen en TODOS los territorios (comparación justa)
             "comparable": {"ing": all(m["tiene_ingreso"] for m in meta.values()), "pot": all(m["tiene_potencial"] for m in meta.values())},
             "meta": {k: {"periodo": m["periodo"], "embotellador": m.get("embotellador"), "tiene_ingreso": m["tiene_ingreso"],
                          "tiene_potencial": m["tiene_potencial"], "fuentes": m["fuentes"]} for k, m in meta.items()},
             "tiendas": tiendas, "mensual": mensual, "productos": productos, "pxf": _franquicia_producto(d, vt, cat, meta)}
    html = (PLANTILLA.replace("__FUENTES__", marca.fuentes_css()).replace("__LOGO__", marca.logo_data_uri("formal", "oscuro"))
            .replace("__SERIES__", json.dumps(marca.SERIES_OSCURO))
            .replace("__DATOS__", json.dumps(datos, ensure_ascii=False, separators=(",", ":"), default=str))
            .replace("__TITULO__", " vs ".join(f"{t} ({meta[t].get('embotellador')})" for t in terrs) + f" · {analisis}"))
    for a, b in zip(d["lat"].head(300), d["lon"].head(300)):
        assert not (f"{a}" in html and f"{b}" in html), "el tablero trae coordenadas exactas de un PdV: aborto"
    ruta.write_text(html, encoding="utf-8")
    return ruta


PLANTILLA = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITULO__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<script src="https://unpkg.com/@maplibre/maplibre-gl-leaflet@0.1.3/leaflet-maplibre-gl.js"></script>
<script src="https://unpkg.com/h3-js@4.1.0/dist/h3-js.umd.js"></script>
<style>
__FUENTES__
:root{--neg:#141417;--ama:#E5FF01;--g1:#EFEFEE;--g2:#D4D5D6;--g3:#999EA6;--g4:#222326;--txt:#FFFFFF}
*{box-sizing:border-box}html,body{margin:0;background:var(--neg);color:var(--txt);font-family:'Albert Sans',system-ui,sans-serif;font-size:14px}
header{padding:16px 24px 10px;position:sticky;top:0;z-index:1000;background:var(--neg);border-bottom:1px solid var(--g4)}
.top{display:flex;justify-content:space-between;align-items:center;gap:16px}.top img{height:22px}
h1{font:700 22px 'Space Grotesk',sans-serif;margin:0}h1 b{color:var(--ama)}
.sub{color:var(--g3);font-size:12px;margin-top:2px}
.ctl{display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin-top:10px}.ctl .l{font-size:11px;color:var(--g3);text-transform:uppercase;letter-spacing:.06em;margin-right:4px}
.seg{display:inline-flex;gap:4px;flex-wrap:wrap}.seg button,.chip{border:1px solid var(--g3);background:transparent;color:#fff;border-radius:999px;padding:4px 12px;font:inherit;font-size:12px;cursor:pointer;display:inline-flex;gap:6px;align-items:center}
.seg button.on{background:var(--ama);color:var(--neg);border-color:var(--ama);font-weight:600}
.chip i{width:9px;height:9px;border-radius:50%;box-shadow:0 0 0 1px #ffffff40}.chip{color:var(--g3);border-color:var(--g4)}.chip.on{background:var(--g4);color:#fff;border-color:var(--ama);font-weight:600}
.chip:not(.on) i{opacity:.35}.chip:hover,.seg button:hover{border-color:var(--g2)}
button:focus-visible{outline:2px solid var(--ama);outline-offset:2px}::selection{background:var(--ama);color:var(--neg)}
*{scrollbar-color:var(--g3) var(--neg);scrollbar-width:thin}body{font-variant-numeric:tabular-nums}
.vista button{font:700 13px 'Space Grotesk',sans-serif;padding:6px 16px}
nav{display:flex;gap:4px;margin-top:10px}nav button{background:none;border:0;color:var(--g3);font:600 13px 'Space Grotesk',sans-serif;padding:6px 12px;border-radius:6px;cursor:pointer}nav button.on{background:var(--g4);color:#fff}
main{padding:18px 24px 32px;max-width:1500px;margin:0 auto}.tab{display:none}.tab.on{display:block}
.grid{display:grid;gap:14px}.g2{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}.maps.dos{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}@media(max-width:900px){.g2{grid-template-columns:1fr}main,header{padding-left:16px;padding-right:16px}header{position:static}h1{font-size:18px}}
html,body{overflow-x:hidden}svg{max-width:100%}
.card{background:var(--g4);border-radius:12px;padding:16px;min-width:0}.card h2{font:600 15px 'Space Grotesk',sans-serif;margin:0 0 10px}
.terr{font:700 18px 'Space Grotesk',sans-serif;margin:0 0 10px;display:flex;align-items:center;gap:8px}.terr i{width:12px;height:12px;border-radius:3px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}
.kpi{background:var(--g4);border-radius:12px;padding:14px}.kpi .v{font:700 26px 'Space Grotesk',sans-serif;line-height:1.1}.kpi .l{font-size:12px;color:var(--g3);margin-top:4px}.kpi.ac .v{color:var(--ama)}
.insights{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin:14px 0}
.ins{background:var(--g4);border-radius:12px;padding:12px 14px;font-size:12.5px;line-height:1.4;color:var(--g2)}.ins b{font:700 20px 'Space Grotesk',sans-serif;display:block;color:var(--ama);margin-bottom:2px}
svg text{font-family:'Albert Sans',sans-serif;font-size:11px;fill:var(--g3)}svg text.v{fill:#fff;font-weight:600}svg text.g{fill:#fff;font:600 12px 'Space Grotesk',sans-serif}
.leg{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;margin-bottom:8px;color:var(--g2)}.leg span{display:inline-flex;gap:6px;align-items:center}.leg i{width:12px;height:10px;border-radius:2px}
.mapa{height:480px;border-radius:12px;overflow:hidden;margin-top:10px}
.mk{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.mk div{background:var(--g4);border-radius:10px;padding:10px 12px}.mk b{display:block;font:700 19px 'Space Grotesk',sans-serif}.mk span{font-size:11.5px;color:var(--g3)}
.mk .ac b{color:var(--ama)}.tops{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:8px;margin-top:10px}
.tc{background:var(--g4);border:1px solid var(--g4);border-radius:10px;padding:9px 11px;cursor:pointer;text-align:left;color:#fff;font:inherit}.tc:hover,.tc:focus-visible{border-color:var(--ama)}
.tc small{display:block;color:var(--g3);font-size:11px;margin-top:2px}.tc b{font:700 15px 'Space Grotesk',sans-serif;color:var(--ama)}.tc em{font-style:normal;font-size:11px;margin-left:6px}.maps{display:grid;gap:14px}.maps.dos{grid-template-columns:1fr 1fr}@media(max-width:900px){.maps.dos{grid-template-columns:1fr}}
.mleg{background:var(--neg);color:#fff;padding:8px 10px;border-radius:8px;font-size:12px;line-height:1.6}.mleg i{display:inline-block;width:14px;height:10px;margin-right:6px;border:1px solid #fff3}
table{border-collapse:collapse;width:100%;font-size:12.5px}th{font:600 11px 'Space Grotesk',sans-serif;text-transform:uppercase;color:var(--g3);text-align:right;padding:6px 8px;border-bottom:1px solid var(--g3);position:sticky;top:0;background:var(--g4);cursor:pointer;white-space:nowrap}
th:first-child,td:first-child{text-align:left}td{padding:5px 8px;border-bottom:1px solid var(--neg);text-align:right;white-space:nowrap}td.t{text-align:left;white-space:normal}tr:hover td{background:var(--neg)}
.scroll{max-height:520px;overflow:auto}.pos{color:var(--ama)}.negv{color:var(--g3)}
input[type=search]{padding:5px 8px;border:1px solid var(--g3);background:var(--neg);color:#fff;border-radius:6px;font:inherit;width:220px;margin-bottom:8px}
.tt{position:fixed;pointer-events:none;background:var(--neg);border:1px solid var(--ama);color:#fff;padding:8px 10px;border-radius:8px;font-size:12px;line-height:1.45;z-index:2000;display:none;max-width:360px;max-height:calc(100vh - 24px);overflow:hidden}
.foot{color:var(--g3);font:500 12px 'Albert Sans',sans-serif;margin-top:20px;display:flex;justify-content:space-between;gap:16px}
.leaflet-tooltip{background:var(--neg);color:#fff;border:1px solid var(--ama);font-family:'Albert Sans',sans-serif}
</style></head><body>
<header>
  <div class="top"><div><h1>__TITULO__ <b>·</b> cadenas</h1><div class="sub" id="sub"></div></div><img src="__LOGO__" alt="Kin Analytics"></div>
  <div class="ctl">
    <span><span class="l">Clientes</span><span id="fCad"></span></span>
  </div>
  <nav id="tabs"></nav>
</header>
<main>
<section class="tab" data-t="Resumen"><div class="ctl" style="margin:0 0 12px"><span><span class="l">Ver ciudades</span><span class="seg vista" id="vistaR"></span></span></div><div id="rRes"></div></section>
<section class="tab" data-t="Mapa">
  <div class="ctl" style="margin:0 0 12px"><span><span class="l">Cadena</span><span class="seg" id="mFra"></span></span></div>
  <div class="maps dos" id="maps"></div>
  <p class="sub" style="margin-top:10px">Cada punto es una tienda (ubicada en el centro de su celda de ~70 m); tamaño y color según su revenue 12m. Clic en una tarjeta del top para ir a la tienda.</p>
</section>
<section class="tab" data-t="Tendencias">
  <div class="card"><h2>Tendencia mensual por franquicia</h2>
   <div class="ctl" style="margin:0 0 8px"><span class="seg" id="tMet"></span><span class="seg" id="tEsc"></span></div>
   <div class="ctl" style="margin:0 0 10px"><span><span class="l">Franquicias</span><span id="tFra"></span></span></div>
   <div class="grid g2" id="tLin"></div></div>
  <div class="grid g2" style="margin-top:14px"><div class="card"><h2>Crecimiento por franquicia vs año anterior</h2><div class="leg" id="tYoyL"></div><div id="tYoy"></div></div><div class="card"><h2>Estacionalidad (100 = mes promedio)</h2><div class="leg" id="tEstL"></div><div id="tEst"></div></div></div>
</section>
<section class="tab" data-t="Productos"><div id="rProd"></div></section>
<section class="tab" data-t="Franquicias"><div class="card"><div class="ctl" style="margin:0 0 8px"><span><span class="l">Ver ciudades</span><span class="seg vista" id="vistaF"></span></span><span class="seg" id="sTop"></span></div><input type="search" id="buscar" placeholder="Buscar franquicia"><div id="rTop"></div></div></section>
<div class="foot"><span>Datos del datawarehouse (bronze/silver/gold) · estado y municipio INEGI · sin coordenadas de puntos de venta.</span><span>kinanalytics.com</span></div>
</main>
<div class="tt" id="tt"></div>
<script>
const D=__DATOS__,PAL=__SERIES__,T=D.tiendas,TC=T.col,TD=T.dic,NT=TC.pos_id.length,TERRS=D.terrs;
const CT={};TERRS.forEach((t,i)=>CT[t]=PAL[i%PAL.length]);           // territorio: amarillo, blanco…
const CC={},DASH={};D.orden.forEach((c,i)=>{CC[c]=c==='Independientes'?PAL[2]:PAL[Math.min(i,3)];DASH[c]=(c==='Independientes'||i>3)?'5 4':''});
const AYUDA={'Otras cadenas':'Otras cadenas: '+(D.otras||[]).join(', '),'Independientes':'Clientes del canal moderno que no son de una cadena (tiendas, minisúpers, farmacias, gimnasios…)'};
const _st0={mFra:'Todas'};const st={..._st0,vistaR:'Juntos',vistaF:'Juntos',cad:new Set(D.foco.filter(c=>D.orden.includes(c))),tienda:true,tab:'Resumen',mMet:'n',mRes:7,tMet:'rev',tEsc:'val',sTop:'rev',orden:{}};
const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function abr(v){const a=Math.abs(v);return a>=1e9?(v/1e9).toFixed(2)+'B':a>=1e6?(v/1e6).toFixed(1)+'M':a>=1e4?(v/1e3).toFixed(1)+'K':Math.round(v).toLocaleString('es-MX')}
const fN=v=>v==null||!isFinite(v)?'—':Math.round(v).toLocaleString('es-MX'),f$=v=>v==null||!isFinite(v)?'—':'$'+abr(v),fP=(v,s)=>v==null||!isFinite(v)?'—':(s&&v>0?'+':'')+(v*100).toFixed(1)+'%';
const tt=$('tt');function tip(e,h){tt.innerHTML=h;tt.style.display='block';const m=12,w=tt.offsetWidth,hh=tt.offsetHeight;let x=e.clientX+14,y=e.clientY+14;if(x+w>innerWidth-m)x=Math.max(m,e.clientX-14-w);if(y+hh>innerHeight-m)y=Math.max(m,e.clientY-14-hh);tt.style.left=x+'px';tt.style.top=y+'px'}function untip(){tt.style.display='none'}
$('sub').textContent=TERRS.map(t=>{const m=D.meta[t],p=m.periodo;return `${t} (${m.embotellador}): ${p.desde}–${p.hasta} vs ${p.anterior_desde}–${p.anterior_hasta}`+(p.incompleto?` · ${p.incompleto} incompleto, fuera`:'')}).join(' · ');

function seg(id,opts,key,cb){const el=$(id);el.innerHTML='';opts.forEach(([k,l])=>{const b=document.createElement('button');b.textContent=l;b.className=st[key]===k?'on':'';b.onclick=()=>{st[key]=k;(cb||render)()};el.appendChild(b)})}
(function(){const el=$('fCad');D.orden.forEach(c=>{const b=document.createElement('button');b.className='chip'+(st.cad.has(c)?' on':'');b.innerHTML=`<i style="background:${CC[c]}"></i>${esc(c)}`;b.title=AYUDA[c]||c;
 b.onclick=()=>{st.cad.has(c)?st.cad.delete(c):st.cad.add(c);if(!st.cad.size)st.cad.add(c);b.classList.toggle('on',st.cad.has(c));render()};el.appendChild(b)})})();
// siempre solo tiendas (sin comedores, oficinas, CEDIS ni vending); el filtro no se muestra al usuario
['Resumen','Mapa','Tendencias','Productos','Franquicias'].forEach(t=>{const b=document.createElement('button');b.textContent=t;b.onclick=()=>{st.tab=t;render()};$('tabs').appendChild(b)});
const cads=()=>D.orden.filter(c=>st.cad.has(c));
const okC=(cube,i,t)=>{const C=cube.col,Dd=cube.dic;return st.cad.has(Dd.cadena[C.cadena[i]])&&(!t||Dd.territorio[C.territorio[i]]===t)&&(!st.tienda||Dd.tipo_punto[C.tipo_punto[i]]==='Tienda')};

function agg(t,key='cadena'){const A={},tot={n:0,comp:0,rev:0,revp:0,cj:0,ing:0,nIng:0,pot:0,vh:0,perd:0};
 for(let i=0;i<NT;i++){if(!okC(T,i,t))continue;const k=TD[key][TC[key][i]],a=A[k]||(A[k]={n:0,comp:0,rev:0,revp:0,cj:0,ing:0,nIng:0,pot:0,vh:0,perd:0});
  for(const x of [a,tot]){x.n++;x.comp+=TC.comp[i];x.rev+=TC.revenue_12m[i];x.revp+=TC.revenue_12m_anterior[i];x.cj+=TC.cajas_12m[i];x.pot+=TC.pot[i];
   if(!TC.ing_nulo[i]){x.nIng++;x.ing+=TC.ing[i]}const p=TD.prioridad[TC.prioridad[i]];if(p==='Very High'||p==='High')x.vh++;if(TD.estatus[TC.estatus[i]].startsWith('Perdido'))x.perd++}}
 return [A,tot]}
const IND=[['PdV',a=>a.n,fN],['% que compran',a=>a.comp/a.n,v=>fP(v)],['Revenue 12m',a=>a.rev,f$],['vs año anterior',a=>a.revp?a.rev/a.revp-1:null,v=>fP(v,1)],
 ['Revenue por tienda compradora',a=>a.comp?a.rev/a.comp:null,f$],['Precio por caja',a=>a.cj?a.rev/a.cj:null,f$]]
 .concat(D.comparable.ing?[['Venta del mes por tienda',a=>a.nIng?a.ing/a.nIng:null,f$]]:[]).concat(D.comparable.pot?[['Potencial (cajas/mes)',a=>a.pot||null,fN]]:[]);

// ---------- gráficas ----------
const esCero=t=>/^[+−-]?\$?0([.,]0+)?(%| pts)?$/.test(String(t).trim());
function barras(el,items,fmt,opt={}){items=items.filter(it=>!isFinite(it.v)||!esCero(fmt(it.v)));if(!items.length){el.innerHTML='<p class="sub">Sin datos que mostrar.</p>';return}const W=el.clientWidth||520,h=opt.h||26,lw=opt.lw||120,vv=items.map(x=>x.v).filter(isFinite);
 const neg=vv.some(v=>v<0),pos=vv.some(v=>v>0),max=opt.max||Math.max(...vv.map(Math.abs),1e-9),ancho=W-lw-70;
 const x0=!neg?lw:!pos?lw+ancho:lw+ancho/2,k=(neg&&pos?ancho/2:ancho)/max;let s=`<svg width="${W}" height="${items.length*h+6}">`;
 items.forEach((it,j)=>{const y=j*h+3,ok=isFinite(it.v),w=ok?Math.abs(it.v)*k:0,x=it.v<0?x0-w:x0;
  s+=`<text x="${lw-10}" y="${y+h/2+1}" text-anchor="end">${esc(it.l)}</text><rect data-j="${j}" x="${x}" y="${y+4}" width="${Math.max(w,0)}" height="${h-12}" rx="3" fill="${it.c}"/>`+
   `<text class="v" x="${it.v<0?x0+6:x+w+6}" y="${y+h/2+1}">${ok?fmt(it.v):'—'}</text>`});
 if(neg)s+=`<line x1="${x0}" x2="${x0}" y1="0" y2="${items.length*h+4}" stroke="#999EA6"/>`;el.innerHTML=s+'</svg>';
 el.querySelectorAll('rect').forEach(r=>{const it=items[r.dataset.j];r.onmousemove=e=>tip(e,it.tip||`<b>${esc(it.l)}</b><br>${fmt(it.v)}`);r.onmouseleave=untip})}
// pares: un grupo (cadena, franquicia, marca…) y debajo una barra por territorio, siempre en el mismo orden y color
function pares(el,grupos,val,fmt){grupos=grupos.filter(g=>TERRS.some(t=>{const v=val(g,t);return v!=null&&isFinite(v)&&!esCero(fmt(v))}));if(!grupos.length){el.innerHTML='<p class="sub">Sin datos que mostrar.</p>';return}const W=el.clientWidth||520,fila=12,gap=8,alto=g=>18+TERRS.length*(fila+3)+gap;
 const vals=grupos.flatMap(g=>TERRS.map(t=>val(g,t))).filter(v=>v!=null&&isFinite(v)),neg=vals.some(v=>v<0),pos=vals.some(v=>v>0),max=Math.max(...vals.map(Math.abs),1e-9);
 const ancho=W-80,x0=!neg?0:!pos?ancho:ancho/2,k=(neg&&pos?ancho/2:ancho)/max;let y=0,s='';
 grupos.forEach(g=>{s+=`<text class="g" x="0" y="${y+12}">${esc(g)}</text>`;y+=18;
  TERRS.forEach(t=>{const v=val(g,t),ok=v!=null&&isFinite(v),w=ok?Math.abs(v)*k:0,x=ok&&v<0?x0-w:x0;
   s+=`<rect x="${x}" y="${y}" width="${Math.max(w,ok?2:0)}" height="${fila}" rx="3" fill="${CT[t]}"><title>${esc(g)} · ${esc(t)}: ${ok?fmt(v):'sin dato'}</title></rect>`+
    `<text class="v" x="${ok&&v<0?x0+6:x+w+6}" y="${y+fila-2}">${ok?fmt(v):'—'}</text>`;y+=fila+3});y+=gap});
 if(neg)s+=`<line x1="${x0}" x2="${x0}" y1="18" y2="${y}" stroke="#999EA6"/>`;el.innerHTML=`<svg width="${W}" height="${y}">${s}</svg>`}
const leyT=()=>`<div class="leg">${TERRS.map(t=>`<span><i style="background:${CT[t]}"></i>${esc(t)} · ${esc(D.meta[t].embotellador)}</span>`).join('')}</div>`;
function lineas(el,meses,series,fmt){const W=el.clientWidth||900,H=300,m={l:64,r:16,t:10,b:28},w=W-m.l-m.r,h=H-m.t-m.b,max=Math.max(...series.flatMap(s=>s.vals).filter(isFinite),1e-9);
 const X=i=>m.l+(meses.length<2?0:i*w/(meses.length-1)),Y=v=>m.t+h-v/max*h;let s=`<svg width="${W}" height="${H}">`;
 for(let k=0;k<=4;k++){const y=Y(max*k/4);s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${y}" y2="${y}" stroke="#141417"/><text x="${m.l-8}" y="${y+4}" text-anchor="end">${fmt(max*k/4)}</text>`}
 meses.forEach((mm,i)=>{if(i%3===0||i===meses.length-1)s+=`<text x="${X(i)}" y="${H-8}" text-anchor="middle">${mm.slice(0,4)}-${mm.slice(4)}</text>`});
 series.forEach(se=>{let pen=false;s+=`<path d="${se.vals.map((v,i)=>{if(v==null||!isFinite(v)){pen=false;return ''}const c=(pen?'L':'M')+X(i)+','+Y(v);pen=true;return c}).join('')}" fill="none" stroke="${se.c}" stroke-width="2.2" stroke-dasharray="${se.d||''}"/>`});
 const id='x'+Math.random().toString(36).slice(2);s+=`<line id="${id}" y1="${m.t}" y2="${m.t+h}" stroke="#999EA6" stroke-dasharray="3 3" style="display:none"/><rect x="${m.l}" y="${m.t}" width="${w}" height="${h}" fill="transparent"/></svg>`;
 el.innerHTML=s;const r=el.querySelector('rect:last-of-type'),cx=el.querySelector('#'+id);
 r.onmousemove=e=>{const b=r.getBoundingClientRect(),i=Math.max(0,Math.min(meses.length-1,Math.round((e.clientX-b.left)/w*(meses.length-1))));cx.setAttribute('x1',X(i));cx.setAttribute('x2',X(i));cx.style.display='';
  tip(e,`<b>${meses[i]}</b><br>`+series.map(se=>`<span style="color:${se.c}">■</span> ${esc(se.l)}: ${fmt(se.vals[i])}`).join('<br>'))};r.onmouseleave=()=>{cx.style.display='none';untip()}}
function tabla(el,cols,rows,opt={}){const key=opt.id||el.id,o=st.orden[key]||opt.orden;if(o)rows=[...rows].sort((a,b)=>{const x=a[o.k],y=b[o.k];return(typeof x==='string'?String(x).localeCompare(y):((x??-1e18)-(y??-1e18)))*(o.d?-1:1)});
 if(opt.lim)rows=rows.slice(0,opt.lim);let s='<div class="scroll"><table><thead><tr>'+cols.map(c=>`<th data-k="${c.k}">${c.l}${o&&o.k===c.k?(o.d?' ↓':' ↑'):''}</th>`).join('')+'</tr></thead><tbody>';
 for(const r of rows)s+='<tr>'+cols.map(c=>`<td class="${c.t?'t':''}">${c.h?c.h(r):c.f?c.f(r[c.k],r):esc(r[c.k])}</td>`).join('')+'</tr>';el.innerHTML=s+'</tbody></table></div>';
 el.querySelectorAll('th').forEach(th=>th.onclick=()=>{const k=th.dataset.k,p=st.orden[key]||opt.orden||{};st.orden[key]={k,d:p.k===k?!p.d:true};render()})}
const cP=v=>v==null||!isFinite(v)?'—':`<span class="${v>=0?'pos':'negv'}">${fP(v,1)}</span>`;
const dot=c=>`<span style="color:${CC[c]||PAL[3]}">●</span> ${esc(c)}`;
const tit=t=>`<div class="terr"><i style="background:${CT[t]}"></i>${esc(t)} <span class="sub" style="font:400 12px 'Albert Sans'">${esc(D.meta[t].embotellador)}</span></div>`;

// ---------- Resumen ----------
function resumen(){const el=$('rRes');const R={};TERRS.forEach(t=>R[t]=agg(t));const J=agg(null);
 const kp=(tot)=>IND.filter(([l,f])=>f(tot)!=null).slice(0,7).map(([l,f,fm],i)=>`<div class="kpi${i===2||i===7?' ac':''}"><div class="v">${fm(f(tot))}</div><div class="l">${l}</div></div>`).join('');
 // insights automáticos (cortos)
 const [a,b]=TERRS,A=R[a][1],B=R[b][1],ins=[];
 if(A.n&&B.n){const r=B.n/A.n;ins.push([`${r>=1?r.toFixed(1)+'×':(1/r).toFixed(1)+'×'}`,`${r>=1?b:a} tiene más PdV que ${r>=1?a:b}`]);
  ins.push([`${fP(A.comp/A.n)} · ${fP(B.comp/B.n)}`,`compran ${D.analisis} en ${a} y ${b}`]);
  ins.push([`${f$(A.comp?A.rev/A.comp:0)} · ${f$(B.comp?B.rev/B.comp:0)}`,`revenue 12m por tienda compradora`]);
  ins.push([`${fP(A.revp?A.rev/A.revp-1:null,1)} · ${fP(B.revp?B.rev/B.revp-1:null,1)}`,`vs año anterior (${a} · ${b})`])}
 let h=`<div class="insights">${ins.map(([x,y])=>`<div class="ins"><b>${x}</b>${esc(y)}</div>`).join('')}</div>`;
 if(st.vistaR==='Juntos'){h+=`<div class="kpis">${kp(J[1])}</div><div class="grid g2" style="margin-top:14px">
   <div class="card"><h2>Cara a cara</h2><div class="leg">${TERRS.map(t=>`<span><i style="background:${CT[t]}"></i>${esc(t)}</span>`).join('')}</div><div id="cara"></div></div>
   <div class="card"><h2>Por cadena</h2><div class="seg" id="rMet" style="margin-bottom:8px"></div>${leyT()}<div id="rCad"></div></div></div>`;el.innerHTML=h;
  // cara a cara: barras por indicador, normalizadas al mayor de los territorios
  const W=$('cara').clientWidth||520;let s=`<svg width="${W}" height="${IND.length*44}">`;const rows=IND.filter(([l,f])=>TERRS.some(t=>f(R[t][1])!=null));
  rows.forEach(([l,f,fm],k)=>{const vs=TERRS.map(t=>f(R[t][1])),mx=Math.max(...vs.map(v=>Math.abs(v||0)),1e-9);s+=`<text x="0" y="${k*44+12}">${esc(l)}</text>`;
   TERRS.forEach((t,j)=>{const v=vs[j],w=(W-110)*Math.abs(v||0)/mx;s+=`<rect x="0" y="${k*44+16+j*12}" width="${Math.max(w,1)}" height="10" rx="3" fill="${CT[t]}"/><text class="v" x="${w+6}" y="${k*44+25+j*12}">${v==null?'—':fm(v)}</text>`})});
  $('cara').innerHTML=s.replace(`height="${IND.length*44}"`,`height="${rows.length*44}"`)+'</svg>';
  seg('rMet',[['n','PdV'],['rev','Revenue 12m'],['pen','% compran'],['rpt','Rev./tienda compradora']],'rMet',resumenTodo);st.rMet=st.rMet||'n';
  const v=a=>st.rMet==='n'?a.n:st.rMet==='rev'?a.rev:st.rMet==='pen'?a.comp/a.n:(a.comp?a.rev/a.comp:0),fm=st.rMet==='pen'?(x=>fP(x)):st.rMet==='n'?fN:f$;
  pares($('rCad'),cads().filter(c=>J[0][c]),(c,t)=>R[t][0][c]?v(R[t][0][c]):null,fm)}
 else{h+=`<div class="grid g2">`+TERRS.map(t=>`<div>${tit(t)}<div class="kpis">${kp(R[t][1])}</div><div class="card" style="margin-top:12px"><h2>Por cadena</h2><div class="seg rMet2" style="margin-bottom:8px"></div><div class="rCad2" data-t="${esc(t)}"></div></div></div>`).join('')+'</div>';
  el.innerHTML=h;st.rMet=st.rMet||'n';
  const v=a=>st.rMet==='n'?a.n:st.rMet==='rev'?a.rev:st.rMet==='pen'?a.comp/a.n:(a.comp?a.rev/a.comp:0),fm=st.rMet==='pen'?(x=>fP(x)):st.rMet==='n'?fN:f$;
  const mx=Math.max(...TERRS.flatMap(t=>cads().filter(c=>R[t][0][c]).map(c=>v(R[t][0][c]))),1e-9);
  el.querySelectorAll('.rMet2').forEach((x,i)=>{x.id='rm'+i;seg(x.id,[['n','PdV'],['rev','Revenue 12m'],['pen','% compran'],['rpt','Rev./tienda']],'rMet',resumenTodo)});
  el.querySelectorAll('.rCad2').forEach(x=>{const t=x.dataset.t;barras(x,cads().filter(c=>R[t][0][c]).map(c=>({l:c,v:v(R[t][0][c]),c:CC[c]})),fm,{max:mx})})}}

function resumenTodo(){resumen();graficasGrupo()}   // la métrica de 'Por cadena' redibuja TODO el resumen (antes borraba lo de abajo)
function graficasGrupo(){
 // Comparativas que siempre muestran los territorios lado a lado: mezcla, crecimiento, consumo y franquicias
 const el=$('rRes'),R={};TERRS.forEach(t=>R[t]=agg(t));const cs=cads();
 el.insertAdjacentHTML('beforeend',`<div class="grid g2" style="margin-top:14px">
  <div class="card"><h2>Mezcla del revenue 12m por grupo</h2><div class="leg">${cs.map(c=>`<span><i style="background:${CC[c]}"></i>${esc(c)}</span>`).join('')}</div><div id="gMix"></div></div>
  <div class="card"><h2>Crecimiento del revenue vs año anterior</h2>${leyT()}<div id="gCre"></div></div>
  <div class="card"><h2>Consumo: cajas 12m por tienda compradora</h2>${leyT()}<div id="gCaj"></div></div>
  <div class="card"><h2>Otras cadenas: revenue 12m por franquicia</h2>${leyT()}<div id="gFra"></div></div></div>`);
 const W=$('gMix').clientWidth||520;let s=`<svg width="${W}" height="${TERRS.length*40}">`;
 TERRS.forEach((t,k)=>{const tot=cs.reduce((a,c)=>a+(R[t][0][c]?.rev||0),0)||1;let x=90;s+=`<text class="g" x="82" y="${k*40+23}" text-anchor="end">${esc(t)}</text>`;
  cs.forEach(c=>{const v=(R[t][0][c]?.rev||0)/tot,w=(W-100)*v;s+=`<rect x="${x}" y="${k*40+6}" width="${Math.max(w-2,0)}" height="26" fill="${CC[c]}"><title>${t} · ${c}: ${fP(v)} (${f$(R[t][0][c]?.rev||0)})</title></rect>`;
   if(w>40)s+=`<text x="${x+6}" y="${k*40+23}" style="fill:${CC[c]===PAL[0]||CC[c]===PAL[1]?'#141417':'#fff'};font-weight:700">${Math.round(v*100)}%</text>`;x+=w})});$('gMix').innerHTML=s+'</svg>';
 pares($('gCre'),cs,(c,t)=>{const a=R[t][0][c];return a&&a.revp?a.rev/a.revp-1:null},v=>fP(v,1));
 pares($('gCaj'),cs,(c,t)=>{const a=R[t][0][c];return a&&a.comp?a.cj/a.comp:null},v=>Math.round(v).toLocaleString('es-MX')+' cajas');
 const F={};for(let i=0;i<NT;i++){if(TD.cadena[TC.cadena[i]]!=='Otras cadenas'||(st.tienda&&TD.tipo_punto[TC.tipo_punto[i]]!=='Tienda'))continue;
  const f=TD.franquicia[TC.franquicia[i]],t=TD.territorio[TC.territorio[i]];(F[f]=F[f]||{})[t]=(F[f][t]||0)+TC.revenue_12m[i]}
 const fr=Object.keys(F).filter(f=>TERRS.some(t=>(F[f][t]||0)>0)).sort((a,b)=>TERRS.reduce((s,t)=>s+(F[b][t]||0),0)-TERRS.reduce((s,t)=>s+(F[a][t]||0),0));
 if(fr.length)pares($('gFra'),fr,(f,t)=>F[f][t]>0?F[f][t]:null,f$);else $('gFra').innerHTML='<p class="sub">Activa “Otras cadenas” en el filtro de clientes.</p>'}
// ---------- Mapa ----------
// Mapa dividido: un mapa por ciudad con las tiendas de la cadena elegida, tarjetas de resumen y top 5 tiendas
const MAPS={};const RAMPA=['#D4D5D6','#999EA6','#222326','#141417','#E5FF01'];
function mapa(){const F2C={};for(let j=0;j<NT;j++)F2C[TD.franquicia[TC.franquicia[j]]]=TD.cadena[TC.cadena[j]];
 const cuenta={};for(let j=0;j<NT;j++){if(!okC(T,j))continue;const f=TD.franquicia[TC.franquicia[j]];cuenta[f]=(cuenta[f]||0)+1}
 const fr=['Todas',...Object.keys(cuenta).sort((a,b)=>cuenta[b]-cuenta[a])];if(!fr.includes(st.mFra))st.mFra='Todas';
 seg('mFra',fr.map(f=>[f,f==='Todas'?'Todas':`${f} · ${fN(cuenta[f])}`]),'mFra',mapa);
 const cont=$('maps');if(!cont.dataset.ok){cont.innerHTML=TERRS.map((t,i)=>`<div>${tit(t)}<div class="mk" id="mk${i}"></div><div class="mapa" id="mp${i}"></div><div class="tops" id="mt${i}"></div></div>`).join('');cont.dataset.ok=1}
 const X=D.pxf;
 TERRS.forEach((t,i)=>{const P=[];for(let j=0;j<NT;j++){if(!okC(T,j,t)||!TC.celda[j])continue;const f=TD.franquicia[TC.franquicia[j]];if(st.mFra!=='Todas'&&f!==st.mFra)continue;
   P.push({j,f,nom:TC.nombre[j],mun:TD.municipio[TC.municipio[j]],rev:TC.revenue_12m[j],revp:TC.revenue_12m_anterior[j],comp:TC.comp[j],cj:TC.cajas_12m[j],est:TD.estatus[TC.estatus[j]],ll:h3.cellToLatLng(TC.celda[j])})}
  // tarjetas de resumen
  const a=P.reduce((s,p)=>(s.n++,s.comp+=p.comp,s.rev+=p.rev,s.revp+=p.revp,s),{n:0,comp:0,rev:0,revp:0});
  const tp=X.filas.filter(r=>r.territorio===t&&(st.mFra==='Todas'||r.franquicia===st.mFra)).reduce((o,r)=>(o[r.producto]=(o[r.producto]||0)+r.rev,o),{});
  const top=Object.entries(tp).sort((x,y)=>y[1]-x[1])[0],sinVenta=P.length&&!P.some(p=>p.rev>0),A=D.analisis.charAt(0).toUpperCase()+D.analisis.slice(1);
  if(!P.length){$('mk'+i).innerHTML=`<div style="grid-column:span 3;border:1px solid var(--g3)"><b style="font-size:14px;color:var(--g2)">${esc(st.mFra)} no tiene tiendas en ${esc(t)}</b><span>Elige otra cadena o “Todas”.</span></div>`}
  else if(sinVenta){$('mk'+i).innerHTML=`<div><b>${fN(a.n)}</b><span>Tiendas</span></div><div style="grid-column:span 2;border:1px solid var(--g3)"><b style="font-size:14px;color:var(--g2)">Sin venta de ${esc(A)} en los datos</b><span>${esc(st.mFra==='Todas'?'Estas tiendas':st.mFra)} no tiene compras de ${esc(D.analisis)} en las ventas NSR de ${esc(D.meta[t].embotellador)}</span></div>`}
  else $('mk'+i).innerHTML=[['Tiendas',fN(a.n)],['Compran '+D.analisis,a.n?fP(a.comp/a.n):'—'],['Revenue 12m',f$(a.rev),1],['vs año anterior',fP(a.revp?a.rev/a.revp-1:null,1)],['Revenue por tienda compradora',f$(a.comp?a.rev/a.comp:null)],
   ['Producto top',top?esc(top[0].length>22?top[0].slice(0,21)+'…':top[0]):'—']].map(([l,v,ac])=>`<div class="${ac?'ac':''}" title="${l==='Producto top'&&top?esc(top[0]):''}"><b style="${l==='Producto top'?'font-size:13px':''}">${v}</b><span>${l}</span></div>`).join('');
  // mapa
  let M=MAPS[t];if(!M){const map=L.map('mp'+i,{preferCanvas:true,minZoom:3,maxZoom:18}).setView([21,-94],5);M=MAPS[t]={map,capa:L.layerGroup().addTo(map),gl:null,mk:{}}}
  M.map.stop();M.capa.clearLayers();M.mk={};const revs=P.map(p=>p.rev).filter(v=>v>0).sort((x,y)=>x-y),q=k=>revs[Math.floor(k*(revs.length-1))]||0,cortes=[.2,.4,.6,.8].map(q),mx=revs[revs.length-1]||1;
  const col=v=>{if(v<=0)return '#999EA6';let k=0;while(k<4&&v>cortes[k])k++;return RAMPA[k]};
  P.sort((x,y)=>x.rev-y.rev).forEach(p=>{const m=L.circleMarker(p.ll,{radius:3+9*Math.sqrt(Math.max(p.rev,0)/mx),color:'#141417',weight:1,fillColor:col(p.rev),fillOpacity:.9})
   .bindTooltip(`<b>${esc(p.nom)}</b><br>${esc(p.f)} · ${esc(p.mun)}<br>`+(p.rev>0?`Revenue 12m ${f$(p.rev)} · vs año ant. ${fP(p.revp?p.rev/p.revp-1:null,1)}<br>${esc(p.est)}`:`Sin venta de ${esc(D.analisis)} en los datos`),{sticky:true}).addTo(M.capa);M.mk[p.j]=m});
  M.lim=P.map(p=>p.ll);setTimeout(()=>encuadrar(M),60);
  if(M.leg)M.map.removeControl(M.leg);M.leg=L.control({position:'bottomright'});M.leg.onAdd=()=>{const d=L.DomUtil.create('div','mleg');
   d.innerHTML=!revs.length?`<b>Tiendas</b><br><i style="background:#999EA6"></i>sin venta de ${esc(D.analisis)}`:
    '<b>Revenue 12m por tienda</b><br>'+RAMPA.map((c,k)=>`<i style="background:${c}"></i>${k?'> '+f$(cortes[k-1]):'≤ '+f$(cortes[0])}`).join('<br>')+(P.some(p=>p.rev<=0)?'<br><i style="background:#999EA6"></i>sin compra':'');return d};M.leg.addTo(M.map);
  // top 5 tiendas en tarjetas: clic → el mapa vuela a la tienda
  const t5=[...P].sort((x,y)=>y.rev-x.rev).slice(0,5);
  $('mt'+i).innerHTML=t5.map((p,k)=>`<button class="tc" data-j="${p.j}">`+(p.rev>0?`<b>${f$(p.rev)}</b><em class="${p.rev>=p.revp?'pos':'negv'}">${fP(p.revp?p.rev/p.revp-1:null,1)}</em><small>${k+1}. ${esc(p.nom)}</small>`:
   `<small style="color:#fff;font-weight:600">${esc(p.nom)}</small><small>Sin venta de ${esc(D.analisis)}</small>`)+`<small>${esc(p.f)} · ${esc(p.mun)}</small></button>`).join('');
  $('mt'+i).querySelectorAll('.tc').forEach(b=>b.onclick=()=>{const m=M.mk[b.dataset.j];if(!m||!M.map.getContainer().offsetWidth)return;
   M.map.stop();M.map.flyTo(m.getLatLng(),16,{duration:.8});M.map.once('moveend',()=>{if(M.capa.hasLayer(m))m.openTooltip()})})})}
function encuadrar(M){const el=M.map.getContainer();if(!el.offsetWidth||!el.offsetHeight)return;   // oculto: se hará al volver a la pestaña
 M.map.invalidateSize({animate:false});if(M.lim&&M.lim.length)M.map.fitBounds(L.latLngBounds(M.lim),{padding:[24,24],maxZoom:14,animate:false});
 if(!M.gl)M.gl=L.maplibreGL({style:'https://tiles.openfreemap.org/styles/positron',attribution:'© OpenFreeMap © OpenMapTiles © OpenStreetMap'}).addTo(M.map)}

// ---------- Tendencias ----------
function tendencias(){const M=D.mensual,C=M.col,meses=[...M.dic.month_445].sort(),S={};
 // series por franquicia y ciudad: S[ciudad][franquicia][mes]
 for(let i=0;i<C.rev.length;i++){if(!okC(M,i))continue;const t=M.dic.territorio[C.territorio[i]],f=M.dic.franquicia[C.franquicia[i]],mm=M.dic.month_445[C.month_445[i]];
  const x=(((S[t]=S[t]||{})[f]=S[t][f]||{})[mm]=S[t][f][mm]||{rev:0,cj:0,pdv:0});x.rev+=C.rev[i];x.cj+=C.cj[i];x.pdv+=C.pdv[i]}
 const tot={};TERRS.forEach(t=>{for(const f in S[t]||{})for(const mm in S[t][f])tot[f]=(tot[f]||0)+S[t][f][mm].rev});
 const fr=Object.keys(tot).sort((a,b)=>tot[b]-tot[a]);
 if(!st.tFra)st.tFra=new Set(fr.slice(0,4));[...st.tFra].forEach(f=>{if(!fr.includes(f))st.tFra.delete(f)});if(!st.tFra.size&&fr.length)st.tFra.add(fr[0]);
 const FC={},FD={};fr.forEach((f,k)=>{FC[f]=PAL[k%4];FD[f]=['','6 4','2 3'][Math.floor(k/4)%3]});
 $('tFra').innerHTML='';fr.forEach(f=>{const b=document.createElement('button');b.className='chip'+(st.tFra.has(f)?' on':'');
  b.innerHTML=`<svg width="18" height="8"><line x1="0" y1="4" x2="18" y2="4" stroke="${FC[f]}" stroke-width="2.5" stroke-dasharray="${FD[f]}"/></svg>${esc(f)}`;
  b.onclick=()=>{st.tFra.has(f)?st.tFra.delete(f):st.tFra.add(f);if(!st.tFra.size)st.tFra.add(f);tendencias()};$('tFra').appendChild(b)});
 const val=x=>!x?null:st.tMet==='ppc'?(x.cj?x.rev/x.cj:null):x[st.tMet];let fm=st.tMet==='rev'||st.tMet==='ppc'?f$:fN;if(st.tEsc==='idx')fm=v=>Math.round(v)+'';
 $('tLin').innerHTML=TERRS.map((t,i)=>`<div>${tit(t)}<div id="tL${i}"></div></div>`).join('');
 TERRS.forEach((t,i)=>{let ser=fr.filter(f=>st.tFra.has(f)&&(S[t]||{})[f]).map(f=>({l:f,c:FC[f],d:FD[f],vals:meses.map(mm=>mm>D.meta[t].periodo.ultimo_completo?null:val(S[t][f][mm]))}));
  if(st.tEsc==='idx')ser=ser.map(se=>{const ok=se.vals.filter(v=>v!=null&&isFinite(v)),pr=ok.reduce((a,b)=>a+b,0)/ok.length;return{...se,vals:se.vals.map(v=>v==null?null:v/pr*100)}});
  const inc=D.meta[t].periodo.incompleto;
  if(ser.length){lineas($('tL'+i),meses,ser,fm);if(inc)$('tL'+i).insertAdjacentHTML('beforeend',`<p class="sub" style="margin:4px 0 0">${inc.slice(0,4)}-${inc.slice(4)} viene incompleto en ${esc(t)} (corte del extracto): no se grafica.</p>`)}else $('tL'+i).innerHTML=`<p class="sub">Ninguna de las franquicias elegidas vende ${esc(D.analisis)} en ${esc(t)}.</p>`});
 // crecimiento por franquicia (pares: misma franquicia, una barra por ciudad)
 const RT={};TERRS.forEach(t=>{RT[t]={};for(const f in S[t]||{}){const p=D.meta[t].periodo;let a=0,b=0;for(const mm in S[t][f]){if(mm>=p.desde&&mm<=p.hasta)a+=S[t][f][mm].rev;if(mm>=p.anterior_desde&&mm<=p.anterior_hasta)b+=S[t][f][mm].rev}RT[t][f]=b?a/b-1:null}});
 $('tYoyL').innerHTML=leyT().replace(/^<div class="leg">|<\/div>$/g,'');pares($('tYoy'),fr.filter(f=>st.tFra.has(f)),(f,t)=>RT[t][f],v=>fP(v,1));
 // estacionalidad por ciudad (todas las franquicias elegidas)
 const nom=['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];$('tEstL').innerHTML=TERRS.map(t=>`<span><i style="background:${CT[t]}"></i>${esc(t)}</span>`).join('');
 const W=$('tEst').clientWidth||520,mesC={};TERRS.forEach(g=>{const tt={},p=D.meta[g].periodo;for(const f in S[g]||{}){if(!st.tFra.has(f))continue;for(const mm in S[g][f]){if(mm>p.hasta)continue;tt[mm]=(tt[mm]||0)+S[g][f][mm].rev}}
  const avg=Object.values(tt).reduce((a,b)=>a+b,0)/Math.max(Object.keys(tt).length,1),cal={};for(const mm in tt)(cal[mm.slice(4)]=cal[mm.slice(4)]||[]).push(tt[mm]);mesC[g]=Object.fromEntries(Object.entries(cal).map(([k,v])=>[k,v.reduce((a,b)=>a+b,0)/v.length/avg*100]))});
 const bw=(W-40)/12,mx=Math.max(...TERRS.flatMap(g=>Object.values(mesC[g])),1);let s=`<svg width="${W}" height="200">`;
 nom.forEach((n,k)=>{const kk=String(k+1).padStart(2,'0');TERRS.forEach((g,j)=>{const v=mesC[g][kk]||0,h=150*v/mx,x=30+k*bw+j*(bw-6)/TERRS.length;s+=`<rect x="${x}" y="${170-h}" width="${(bw-6)/TERRS.length-1}" height="${h}" rx="2" fill="${CT[g]}"><title>${n} ${g}: ${Math.round(v)}</title></rect>`});s+=`<text x="${30+k*bw+bw/2-3}" y="186" text-anchor="middle">${n}</text>`});
 s+=`<line x1="30" x2="${W}" y1="${170-150*100/mx}" y2="${170-150*100/mx}" stroke="#999EA6" stroke-dasharray="4 3"/>`;$('tEst').innerHTML=s+'</svg>'}

// ---------- Productos ----------
function productos(){const P=D.productos,C=P.col,el=$('rProd'),X=D.pxf,den=X.den;
 // Los catálogos de cada ciudad no coinciden: cada ciudad muestra su propio top (no se comparan producto a producto)
 const sum=(t,k)=>{const o={};for(let i=0;i<C.rev.length;i++){if(!okC(P,i,t))continue;const key=P.dic[k][C[k][i]],w=P.dic.ventana[C.ventana[i]],x=(o[key]=o[key]||{rev:0,revp:0,cj:0,pdv:0});if(w==='12m'){x.rev+=C.rev[i];x.cj+=C.cj[i];x.pdv+=C.pdv[i]}else x.revp+=C.rev[i]}return o};
 const S={};TERRS.forEach(t=>S[t]=sum(t,'Segmento'));const segs=[...new Set(TERRS.flatMap(t=>Object.keys(S[t])))].filter(g=>TERRS.some(t=>(S[t][g]?.rev||0)>0)).sort((a,b)=>TERRS.reduce((s,t)=>s+(S[t][b]?.rev||0),0)-TERRS.reduce((s,t)=>s+(S[t][a]?.rev||0),0));
 const corto=x=>x.length>34?x.slice(0,33)+'…':x;
 el.innerHTML=`<div class="grid g2"><div class="card"><h2>Mezcla por segmento (% del revenue 12m)</h2><div class="leg" id="pLeg"></div><div id="pSeg"></div></div>
  <div class="card"><h2>Crecimiento por segmento vs año anterior</h2>${leyT()}<div id="pSegC"></div></div></div>
  <div class="card" style="margin-top:14px"><h2>Top 10 productos de cada ciudad · revenue 12m</h2><div class="grid g2">${TERRS.map((t,i)=>`<div>${tit(t)}<div id="pTop${i}"></div></div>`).join('')}</div></div>
  <div class="card" style="margin-top:14px"><h2>¿Qué vende cada cadena? · cómo se reparte su revenue 12m de ${esc(D.analisis)} (100%)</h2>
   <div class="seg" id="pFra" style="margin-bottom:12px"></div><div class="grid g2">${TERRS.map((t,i)=>`<div>${tit(t)}<div id="pFx${i}"></div></div>`).join('')}</div></div>`;
 const cs={};segs.forEach((g,i)=>cs[g]=PAL[Math.min(i,3)]);$('pLeg').innerHTML=segs.map(g=>`<span><i style="background:${cs[g]}"></i>${esc(g)}</span>`).join('');
 const W=$('pSeg').clientWidth||520;let s=`<svg width="${W}" height="${TERRS.length*40}">`;
 TERRS.forEach((t,k)=>{const tot=segs.reduce((a,g)=>a+(S[t][g]?.rev||0),0)||1;let x=90;s+=`<text class="g" x="82" y="${k*40+23}" text-anchor="end">${esc(t)}</text>`;
  segs.forEach(g=>{const v=(S[t][g]?.rev||0)/tot,w=(W-100)*v;s+=`<rect x="${x}" y="${k*40+6}" width="${Math.max(w-2,0)}" height="26" fill="${cs[g]}"><title>${t} · ${g}: ${fP(v)}</title></rect>`;
   if(w>40)s+=`<text x="${x+6}" y="${k*40+23}" style="fill:${cs[g]===PAL[0]||cs[g]===PAL[1]?'#141417':'#fff'};font-weight:700">${Math.round(v*100)}%</text>`;x+=w})});$('pSeg').innerHTML=s+'</svg>';
 pares($('pSegC'),segs.filter(g=>TERRS.every(t=>S[t][g])),(g,t)=>{const x=S[t][g];return x&&x.revp?x.rev/x.revp-1:null},v=>fP(v,1));
 TERRS.forEach((t,i)=>{const o=sum(t,'Descripción'),tot=Object.values(o).reduce((a,x)=>a+x.rev,0)||1;
  barras($('pTop'+i),Object.entries(o).sort((a,b)=>b[1].rev-a[1].rev).slice(0,10).map(([k,x])=>({l:corto(k),v:x.rev,c:CT[t],
   tip:`<b>${esc(k)}</b><br>${f$(x.rev)} · ${fP(x.rev/tot)} de ${esc(t)}<br>${fN(x.pdv)} tiendas · vs año ant. ${fP(x.revp?x.rev/x.revp-1:null,1)}`})),f$,{lw:240,h:24})});
 const F2C={};for(let j=0;j<NT;j++)F2C[TD.franquicia[TC.franquicia[j]]]=TD.cadena[TC.cadena[j]];
 const fr=[...new Set(Object.keys(den).map(k=>k.split('|')[1]))].filter(f=>st.cad.has(F2C[f])).sort((a,b)=>TERRS.reduce((s,t)=>s+(den[t+'|'+b]||0),0)-TERRS.reduce((s,t)=>s+(den[t+'|'+a]||0),0));
 if(!fr.includes(st.pFra))st.pFra=fr[0];seg('pFra',fr.map(f=>[f,f]),'pFra',productos);
 // mezcla: cada producto como % del revenue de la franquicia en la ciudad (suma 100%; lo que no entra en el top va a "Otros productos")
 TERRS.forEach((t,i)=>{const n=den[t+'|'+st.pFra]||0,R=X.filas.filter(r=>r.franquicia===st.pFra&&r.territorio===t&&r.rev>0).sort((a,b)=>b.rev-a.rev),tot=R.reduce((a,r)=>a+r.rev,0);
  if(!n){$('pFx'+i).innerHTML=`<p class="sub">${esc(st.pFra)} no tiene tiendas en ${esc(t)}.</p>`;return}
  if(!tot){$('pFx'+i).innerHTML=`<p class="sub">${fN(n)} tiendas de ${esc(st.pFra)} en ${esc(t)}: sin venta de ${esc(D.analisis)} en los datos (ventas NSR).</p>`;return}
  // solo entran al top los productos de hydration con al menos 1% del revenue de la cadena; los demás se avisan aparte
  const bajo=R.filter(r=>r.rev/tot<0.01),pctBajo=bajo.reduce((a,r)=>a+r.rev,0)/tot;R.splice(0,R.length,...R.filter(r=>r.rev/tot>=0.01));
  const lista=xs=>'<table style="margin-top:4px;font-size:11.5px">'+xs.map(r=>`<tr><td style="padding:1px 8px 1px 0;text-align:left;white-space:normal">${esc(r.producto)}</td><td style="padding:1px 6px;text-align:right">${r.rev/tot<0.001?'&lt;0.1%':fP(r.rev/tot)}</td><td style="padding:1px 0;text-align:right">${f$(r.rev)}</td></tr>`).join('')+'</table>';
  const top=R.slice(0,8),resto=R.slice(8).reduce((a,r)=>a+r.rev,0),items=top.map(r=>({l:corto(r.producto),v:r.rev/tot,c:CT[t],tip:`<b>${esc(r.producto)}</b><br>${fP(r.rev/tot)} del revenue · ${f$(r.rev)}<br>lo compran ${fN(r.n)} de ${fN(n)} tiendas`}));
  if(resto>0)items.push({l:`Resto de ${D.analisis} (${R.length-8} productos)`,v:resto/tot,c:PAL[2],tip:`<b>${R.length-8} productos de ${esc(D.analisis)} fuera del top 8</b> (cada uno ≥ 1%) · ${fP(resto/tot)} · ${f$(resto)}`+lista(R.slice(8))});
  barras($('pFx'+i),items,v=>fP(v),{lw:240,h:24,max:Math.max(...items.map(x=>x.v))});
  $('pFx'+i).insertAdjacentHTML('afterbegin',`<p class="sub" style="margin:0 0 6px">${f$(tot)} de revenue 12m · ${fN(n)} tiendas de ${esc(st.pFra)} · ${R.length+bajo.length} productos de ${esc(D.analisis)}</p>`);
  if(bajo.length){$('pFx'+i).insertAdjacentHTML('beforeend',`<p class="sub aviso" style="margin:8px 0 0;cursor:help;text-decoration:underline dotted">ⓘ Hay ${bajo.length} producto${bajo.length>1?'s':''} más de ${esc(D.analisis)} que no llega${bajo.length>1?'n':''} al 1% del revenue de ${esc(st.pFra)} (suman ${pctBajo<0.001?'menos de 0.1%':fP(pctBajo)}): no entra${bajo.length>1?'n':''} en el top.</p>`);
   const av=$('pFx'+i).querySelector('.aviso'),bt=[...bajo].sort((a,b)=>b.rev-a.rev);
   av.onmousemove=e=>tip(e,`<b>${bt.length} producto${bt.length>1?'s':''} con menos de 1%</b> · ${pctBajo<0.001?'menos de 0.1%':fP(pctBajo)} · ${f$(bt.reduce((a,r)=>a+r.rev,0))}`+lista(bt));av.onmouseleave=untip}})}

// ---------- Tiendas ----------
function tiendas(){
 // Por franquicia (todas sus tiendas sumadas: todos los OXXO, todas las Bodega Aurrerá…), no tienda por tienda
 const q=($('buscar').value||'').toLowerCase(),el=$('rTop'),F={};
 for(let j=0;j<NT;j++){if(!okC(T,j))continue;const f=TD.franquicia[TC.franquicia[j]];if(q&&!f.toLowerCase().includes(q))continue;const t=TD.territorio[TC.territorio[j]];
  const x=((F[f]=F[f]||{cadena:TD.cadena[TC.cadena[j]]})[t]=F[f][t]||{n:0,comp:0,rev:0,revp:0,cj:0});x.n++;x.comp+=TC.comp[j];x.rev+=TC.revenue_12m[j];x.revp+=TC.revenue_12m_anterior[j];x.cj+=TC.cajas_12m[j]}
 const fila=(f,x)=>({franq:f,cadena:F[f].cadena,n:x.n,pen:x.comp/x.n,rev:x.rev,delta:x.rev-x.revp,crec:x.revp?x.rev/x.revp-1:null,rpt:x.comp?x.rev/x.comp:null,cpt:x.comp?x.cj/x.comp:null});
 const cols=[{k:'franq',l:'Franquicia',t:1,h:r=>dot(r.franq)+(r.franq!==r.cadena?` <span class="sub">${esc(r.cadena)}</span>`:'')},{k:'n',l:'Tiendas',f:fN},{k:'pen',l:'% compran',f:v=>fP(v)},
  {k:'rev',l:'Revenue 12m',f:f$},{k:'delta',l:'Δ vs año ant.',f:v=>`<span class="${v>=0?'pos':'negv'}">${f$(v)}</span>`},{k:'crec',l:'Crecimiento',f:cP},{k:'rpt',l:'Revenue / tienda compradora',f:f$},{k:'cpt',l:'Cajas / tienda compradora',f:fN}];
 const o=st.sTop==='caida'?{k:'delta',d:false}:{k:st.sTop,d:true};
 if(st.vistaF==='Juntos'){el.className='';el.innerHTML=`<h2 style="font:600 15px 'Space Grotesk';margin:0 0 8px">Franquicias cara a cara</h2>${leyT()}<div id="frPar"></div>`;
  const fr=Object.keys(F).sort((a,b)=>TERRS.reduce((s,t)=>s+(F[b][t]?.rev||0),0)-TERRS.reduce((s,t)=>s+(F[a][t]?.rev||0),0)).filter(f=>TERRS.some(t=>F[f][t]));
  const met={rev:[x=>x.rev,f$],delta:[x=>x.rev-x.revp,f$],caida:[x=>x.rev-x.revp,f$],crec:[x=>x.revp?x.rev/x.revp-1:null,v=>fP(v,1)],rpt:[x=>x.comp?x.rev/x.comp:null,f$],n:[x=>x.n,fN]}[st.sTop]||[x=>x.rev,f$];
  pares($('frPar'),fr,(f,t)=>F[f][t]?met[0](F[f][t]):null,met[1])}
 else{el.className='grid g2';el.innerHTML=TERRS.map((t,i)=>`<div>${tit(t)}<div id="top${i}"></div></div>`).join('');
  TERRS.forEach((t,i)=>tabla($('top'+i),cols,Object.keys(F).filter(f=>F[f][t]).map(f=>fila(f,F[f][t])),{orden:o,id:'top'+i+st.sTop}))}}
$('buscar').oninput=()=>render();
function render(){
 document.querySelectorAll('.tab').forEach(s=>s.classList.toggle('on',s.dataset.t===st.tab));document.querySelectorAll('#tabs button').forEach(b=>b.classList.toggle('on',b.textContent===st.tab));
 if(st.tab==='Resumen'){seg('vistaR',[['Juntos','Juntos'],['Separados','Separados']],'vistaR');resumenTodo()}
 if(st.tab==='Mapa')mapa();
 if(st.tab==='Tendencias'){seg('tMet',[['rev','Revenue'],['cj','Cajas'],['pdv','PdV compradores'],['ppc','Precio por caja']],'tMet');seg('tEsc',[['val','Valores'],['idx','Índice 100']],'tEsc');tendencias()}
 if(st.tab==='Productos')productos();
 if(st.tab==='Franquicias'){seg('vistaF',[['Juntos','Juntos'],['Separados','Separados']],'vistaF');seg('sTop',[['rev','Revenue 12m'],['crec','Crecimiento'],['delta','Más crece $'],['caida','Más cae $'],['rpt','Revenue por tienda'],['n','Tiendas']],'sTop');tiendas()}}
addEventListener('resize',()=>{if(st.tab!=='Mapa')render()});
render();
</script></body></html>"""
