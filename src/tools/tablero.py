"""Tablero HTML autónomo (retail) para validar y comparar cadenas con todo el dato del análisis: tendencias mensuales y
estacionalidad, scorecard por cadena, productos del catálogo validado (segmento, marca, presentación), geografía INEGI
(PdV por 100 mil hab.), top de tiendas del país y calidad del dato. Filtros: embotellador, cadenas, estado, solo tiendas.

Los datos van embebidos como cubos (columnas + diccionarios) y se recalculan en el navegador. Sin coordenadas de PdV.
"""
import json

import numpy as np
import pandas as pd

from src.config import cadenas as cfg
from src.tools import inegi, marca


def _cubo(df, dims, medidas):
    """Columnar + diccionarios: {'dic': {dim: [valores]}, 'col': {dim: [índices], medida: [valores]}}."""
    out = {"dic": {}, "col": {}}
    for d in dims:
        cat = pd.Categorical(df[d].fillna("(vacío)").astype(str))
        out["dic"][d] = list(cat.categories)
        out["col"][d] = cat.codes.tolist()
    for m in medidas:
        out["col"][m] = np.round(df[m].astype(float).fillna(0).to_numpy(), 2).tolist()
    return out


def escribir(ruta, d, vv, cat, meta, analisis, pais, foco):
    t = d.assign(nombre=d["cliente"].fillna(""), ing=d["ingreso"], pot=d["potencial_cajas_mes"],
                 prim=d["primer_mes"].fillna(""), ult=d["ultimo_mes"].fillna(""), alertas=d["alertas"].replace("", "(sin alerta)"))
    tiendas = _cubo(t, ["embotellador", "cadena", "formato", "tipo_punto", "estado", "zona", "municipio", "estatus", "prioridad",
                        "alertas", "prim", "ult"],
                    ["revenue_12m", "revenue_12m_anterior", "cajas_12m", "ing", "pot", "meses_con_compra"])
    tiendas["col"]["nombre"] = t["nombre"].tolist()
    tiendas["col"]["pos_id"] = t["pos_id"].tolist()
    tiendas["col"]["ing_nulo"] = t["ingreso"].isna().astype(int).tolist()

    mens = vv.groupby(["embotellador", "cadena", "estado", "month_445"]).agg(
        rev=("revenue", "sum"), cj=("unit_cases", "sum"), pdv=("pos_id", "nunique")).reset_index()
    mensual = _cubo(mens, ["embotellador", "cadena", "estado", "month_445"], ["rev", "cj", "pdv"])

    vent = []
    for emb, m in meta.items():
        u = m["ult12"]
        a = [str(int(x) - 100) for x in u]
        x = vv[(vv["embotellador"] == emb) & vv["month_445"].isin(u + a)]
        vent.append(x.assign(ventana=np.where(x["month_445"].isin(u), "12m", "ant")))
    vent = pd.concat(vent)
    prod = vent.groupby(["embotellador", "cadena", "estado", "product_id", "ventana"]).agg(
        rev=("revenue", "sum"), cj=("unit_cases", "sum"), pdv=("pos_id", "nunique")).reset_index()
    prod["prod"] = prod["embotellador"] + "|" + prod["product_id"]
    productos = _cubo(prod, ["embotellador", "cadena", "estado", "prod", "ventana"], ["rev", "cj", "pdv"])
    atributos = {}
    if cat is not None:
        for _, r in cat.reset_index().iterrows():
            atributos[f"{r['embotellador']}|{r['product_id']}"] = {
                "desc": r["Descripción"], "seg": r.get("Segmento"), "marca": r.get("brand"), "pres": r.get("presentacion"),
                "serv": r.get("serving_type"), "sabor": r.get("flavor")}

    orden = list(dict.fromkeys(foco + [c["nombre"] for c in cfg.CADENAS.values()]))
    datos = {
        "analisis": analisis, "pais": pais.upper(), "foco": foco, "orden_cadenas": orden + ["Independientes"],
        "meta": {e: {"periodo": m["periodo"], "hallazgos": m["hallazgos"], "tiene_ingreso": m["tiene_ingreso"],
                     "tiene_potencial": m["tiene_potencial"], "fuentes": m["fuentes"], "mes_venta_clientes": m["mes_venta_clientes"],
                     "clientes_bronze": m["clientes_bronze"]} for e, m in meta.items()},
        "tiendas": tiendas, "mensual": mensual, "productos": productos, "atributos": atributos,
        "poblacion": {k: int(v) for k, v in inegi.poblacion_estados().items()},
    }
    html = PLANTILLA.replace("__FUENTES__", marca.fuentes_css()).replace("__LOGO__", marca.logo_data_uri("formal", "oscuro")) \
                    .replace("__SERIES__", json.dumps(marca.SERIES_OSCURO)).replace("__DATOS__", json.dumps(datos, ensure_ascii=False, separators=(",", ":"), default=str)) \
                    .replace("__TITULO__", f"Retail · {analisis} · {pais.upper()}")
    for a, b in zip(d["lat"].head(300), d["lon"].head(300)):
        assert not (f"{a}" in html and f"{b}" in html), "el tablero trae coordenadas exactas de un PdV: aborto"
    ruta.write_text(html, encoding="utf-8")
    return ruta


PLANTILLA = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITULO__</title>
<style>
__FUENTES__
:root{--neg:#141417;--ama:#E5FF01;--g1:#EFEFEE;--g2:#D4D5D6;--g3:#999EA6;--g4:#222326;--bg:#141417;--card:#222326;--txt:#FFFFFF;--txt2:#999EA6;--linea:#141417}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--txt);font-family:'Albert Sans',system-ui,sans-serif;font-size:14px}
header{background:var(--neg);color:#fff;padding:16px 24px 12px;position:sticky;top:0;z-index:5;border-bottom:1px solid var(--g4)}
.top{display:flex;justify-content:space-between;align-items:center;gap:16px}.top img{height:22px}
h1{font-family:'Space Grotesk',sans-serif;font-size:20px;margin:0}h1 b{color:var(--ama)}
.sub{color:var(--g3);font-size:12px;margin-top:2px}
.filtros{display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin-top:10px}
.filtros .g{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.filtros .l{font-size:11px;color:var(--g3);text-transform:uppercase;letter-spacing:.05em}
.chip{border:1px solid #444;background:transparent;color:#fff;border-radius:999px;padding:3px 10px;font:inherit;font-size:12px;cursor:pointer;display:inline-flex;gap:6px;align-items:center}
.chip.on{background:#fff;color:var(--neg);border-color:#fff;font-weight:600}.chip i{width:9px;height:9px;border-radius:50%;display:inline-block}
select{padding:4px 6px;border-radius:6px;border:0;font:inherit;font-size:12px}
nav{display:flex;gap:4px;margin-top:12px;flex-wrap:wrap}nav button{background:none;border:0;color:var(--g3);font:600 13px 'Space Grotesk',sans-serif;padding:6px 10px;border-radius:6px;cursor:pointer}
nav button.on{background:var(--ama);color:var(--neg)}
main{padding:18px 24px 40px;max-width:1500px;margin:0 auto}
.tab{display:none}.tab.on{display:block}
.grid{display:grid;gap:14px}.g2{grid-template-columns:1fr 1fr}.g3{grid-template-columns:repeat(3,1fr)}
@media(max-width:900px){.g2,.g3{grid-template-columns:1fr}main{padding:12px 16px}header{padding:12px 16px;position:static}}
.card{background:var(--card);border-radius:12px;padding:16px;min-width:0}
.card h2{font-family:'Space Grotesk',sans-serif;font-size:15px;margin:0 0 4px}.card .n{font-size:12px;color:var(--txt2);margin:0 0 10px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.kpi{background:var(--card);border-radius:12px;padding:12px 14px}.kpi .v{font:700 22px 'Space Grotesk',sans-serif}.kpi .l{font-size:12px;color:var(--txt2)}
.kpi.ac .v{color:var(--ama)}
table{border-collapse:collapse;width:100%;font-size:12.5px}th{font:600 11px 'Space Grotesk',sans-serif;text-transform:uppercase;letter-spacing:.03em;color:var(--txt2);text-align:right;padding:6px 8px;border-bottom:1px solid var(--g3);position:sticky;top:0;background:var(--card);cursor:pointer;white-space:nowrap}
th:first-child,td:first-child{text-align:left}td{padding:5px 8px;border-bottom:1px solid var(--linea);text-align:right;white-space:nowrap}
td.t{text-align:left;white-space:normal;max-width:280px}tr:hover td{background:var(--neg)}
.scroll{max-height:520px;overflow:auto}
.pos{color:var(--ama)}.negv{color:var(--g3)}
.bar{height:8px;border-radius:0 4px 4px 0;background:var(--neg);display:inline-block;vertical-align:middle;background:var(--ama)}
ul.h{margin:0;padding-left:18px;line-height:1.5}ul.h li{margin-bottom:6px}ul.h b{font-family:'Space Grotesk',sans-serif}
svg text{font-family:'Albert Sans',sans-serif;font-size:11px;fill:var(--txt2)}svg text.v{fill:#fff}
.leg{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;margin-bottom:6px}.leg span{display:inline-flex;gap:5px;align-items:center}.leg i{width:12px;height:3px;border-radius:2px;display:inline-block}
.tt{position:fixed;pointer-events:none;background:var(--neg);border:1px solid var(--ama);color:#fff;padding:8px 10px;border-radius:8px;font-size:12px;line-height:1.45;z-index:20;display:none;max-width:360px;max-height:calc(100vh - 24px);overflow:hidden}
.seg{display:flex;gap:4px;margin-bottom:8px;flex-wrap:wrap}.seg button{border:1px solid var(--g3);background:transparent;color:#fff;border-radius:999px;padding:3px 10px;font:inherit;font-size:12px;cursor:pointer}.seg button.on{background:var(--ama);color:var(--neg);border-color:var(--ama);font-weight:600}
input[type=search]{padding:5px 8px;border:1px solid var(--g3);background:var(--neg);color:#fff;border-radius:6px;font:inherit;width:220px}
.pill{display:inline-block;padding:1px 7px;border-radius:999px;font-size:11px;background:var(--neg);color:var(--g2)}
.foot{color:var(--g3);font:500 12px 'Albert Sans',sans-serif;letter-spacing:.02em;margin-top:20px;display:flex;justify-content:space-between;gap:16px}
</style></head><body>
<header>
  <div class="top"><h1>__TITULO__ <b>·</b> cadenas de retail</h1><img src="__LOGO__" alt="Kin Analytics"></div>
  <div class="sub" id="sub"></div>
  <div class="filtros">
    <div class="g"><span class="l">Embotellador</span><span id="fEmb"></span></div>
    <div class="g"><span class="l">Cadenas</span><span id="fCad"></span></div>
    <div class="g"><span class="l">Estado</span><select id="fEst"></select></div>
    <div class="g"><label class="chip" id="fTienda"><input type="checkbox" checked style="display:none">Solo tiendas</label></div>
  </div>
  <nav id="tabs"></nav>
</header>
<main>
<section class="tab" data-t="Resumen">
  <div class="kpis" id="kpis"></div>
  <div class="grid g2" style="margin-top:14px"><div class="card"><h2>Qué dicen los datos</h2><p class="n">Por embotellador, para las cadenas foco. Cifras del datawarehouse.</p><div id="hall"></div></div>
  <div class="card"><h2>Scorecard por cadena</h2><p class="n">Tiendas filtradas. Clic en una columna para ordenar.</p><div class="scroll" id="score"></div></div></div>
</section>
<section class="tab" data-t="Tendencias">
  <div class="card"><h2>Tendencia mensual por cadena</h2><p class="n" id="nTend"></p>
    <div class="seg" id="mTend"></div><div class="leg" id="legTend"></div><div id="cTend"></div></div>
  <div class="grid g2" style="margin-top:14px">
    <div class="card"><h2>Crecimiento vs mismos meses del año anterior</h2><p class="n">Revenue de los últimos meses completos contra el año anterior.</p><div id="cYoy"></div></div>
    <div class="card"><h2>Estacionalidad</h2><p class="n">Índice por mes del año (100 = mes promedio), todas las cadenas filtradas.</p><div id="cEst"></div></div>
  </div>
</section>
<section class="tab" data-t="Cadenas">
  <div class="grid g2">
    <div class="card"><h2>Penetración del análisis</h2><p class="n">% de tiendas que compraron en los últimos 12 meses.</p><div id="cPen"></div></div>
    <div class="card"><h2>Productividad por tienda compradora</h2><p class="n">Revenue 12 meses por tienda que compra.</p><div id="cProd"></div></div>
    <div class="card"><h2>Estatus de las tiendas</h2><p class="n">Activo · Nuevo (1.ª compra en 6 meses) · Perdido (3+ meses sin compra) · Nunca compró.</p><div id="cStat"></div></div>
    <div class="card"><h2>Por formato</h2><p class="n">Comparación dentro de cada cadena.</p><div class="scroll" id="tFmt"></div></div>
  </div>
</section>
<section class="tab" data-t="Productos">
  <div class="grid g2">
    <div class="card"><h2>Mezcla por segmento</h2><p class="n">% del revenue 12m de cada cadena (catálogo validado).</p><div class="leg" id="legSeg"></div><div id="cSeg"></div></div>
    <div class="card"><h2>Marcas</h2><p class="n">Revenue 12m, crecimiento y precio por caja.</p><div class="scroll" id="tMarca"></div></div>
  </div>
  <div class="grid g2" style="margin-top:14px">
    <div class="card"><h2>Presentaciones</h2><p class="n">Tamaño leído de la descripción del catálogo.</p><div class="scroll" id="tPres"></div></div>
    <div class="card"><h2>Top productos</h2><p class="n">Por revenue 12m, con su crecimiento y en cuántas tiendas se vende.</p><div class="scroll" id="tProd"></div></div>
  </div>
</section>
<section class="tab" data-t="Geografía">
  <div class="card"><h2>Por estado</h2><p class="n">PdV por cadena, densidad por 100 mil habitantes (INEGI), revenue y crecimiento.</p><div class="scroll" id="tGeo"></div></div>
  <div class="card" style="margin-top:14px"><h2>Espacio en blanco</h2><p class="n">Municipios donde está la 1.ª cadena filtrada y no está la 2.ª (por # de PdV de la 1.ª).</p><div class="scroll" id="tBlanco"></div></div>
</section>
<section class="tab" data-t="Top tiendas">
  <div class="card"><h2>Top tiendas del país</h2><p class="n">Ordenar por:</p><div class="seg" id="mTop"></div>
    <input type="search" id="buscar" placeholder="Buscar nombre o pos_id"><div class="scroll" id="tTop" style="margin-top:8px"></div></div>
</section>
<section class="tab" data-t="Calidad del dato">
  <div class="grid g2">
    <div class="card"><h2>Alertas</h2><p class="n">Se marcan, no se borran (validar, no limpiar).</p><div id="tAl"></div></div>
    <div class="card"><h2>Fuentes y periodo</h2><p class="n">Solo datawarehouse, corrida más reciente de cada ruta.</p><div id="tFu"></div></div>
  </div>
  <div class="card" style="margin-top:14px"><h2>PdV con alerta</h2><div class="scroll" id="tAlD"></div></div>
</section>
<div class="foot"><span>Datos del datawarehouse (bronze/gold) · estado y municipio INEGI · sin coordenadas de puntos de venta.</span><span>kinanalytics.com</span></div>
</main>
<div class="tt" id="tt"></div>
<script>
const D=__DATOS__;
const T=D.tiendas, TC=T.col, NT=TC.pos_id.length, TD=T.dic;
const PAL=__SERIES__;
const COLOR={},DASH={};D.orden_cadenas.forEach((c,i)=>{COLOR[c]=c==='Independientes'?PAL[2]:PAL[Math.min(i,3)];DASH[c]=c==='Independientes'||i>3?'5 4':''});
const st={emb:new Set(TD.embotellador),cad:new Set(D.foco),est:'',tienda:true,tab:'Resumen',mTend:'rev',mTop:'revenue_12m',orden:{}};
const $=id=>document.getElementById(id);
const fmtN=v=>v==null||!isFinite(v)?'—':Math.round(v).toLocaleString('es-MX');
const fmt$=v=>v==null||!isFinite(v)?'—':'$'+abr(v);
const fmtP=(v,s)=>v==null||!isFinite(v)?'—':(s&&v>0?'+':'')+(v*100).toFixed(1)+'%';
function abr(v){const a=Math.abs(v);return a>=1e9?(v/1e9).toFixed(2)+'B':a>=1e6?(v/1e6).toFixed(1)+'M':a>=1e4?(v/1e3).toFixed(1)+'K':Math.round(v).toLocaleString('es-MX')}
const tt=$('tt');function tip(e,h){tt.innerHTML=h;tt.style.display='block';const m=12,w=tt.offsetWidth,hh=tt.offsetHeight;let x=e.clientX+14,y=e.clientY+14;if(x+w>innerWidth-m)x=Math.max(m,e.clientX-14-w);if(y+hh>innerHeight-m)y=Math.max(m,e.clientY-14-hh);tt.style.left=x+'px';tt.style.top=y+'px'}function untip(){tt.style.display='none'}
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

// --- filtros ---
$('sub').textContent=Object.entries(D.meta).map(([e,m])=>`${e}: ventas ${m.periodo.desde}–${m.periodo.hasta} vs ${m.periodo.anterior_desde}–${m.periodo.anterior_hasta}`+(m.periodo.incompleto?` (mes ${m.periodo.incompleto} incompleto, fuera)`:'')).join(' · ');
function chips(id,vals,set,col){const el=$(id);el.innerHTML='';vals.forEach(v=>{const b=document.createElement('button');b.className='chip'+(set.has(v)?' on':'');
 b.innerHTML=(col?`<i style="background:${COLOR[v]}"></i>`:'')+esc(v);b.onclick=()=>{set.has(v)?set.delete(v):set.add(v);if(!set.size)set.add(v);b.classList.toggle('on',set.has(v));render()};el.appendChild(b)})}
chips('fEmb',TD.embotellador,st.emb);
chips('fCad',D.orden_cadenas.filter(c=>TD.cadena.includes(c)),st.cad,true);
const fe=$('fEst');fe.add(new Option('Todos',''));[...TD.estado].sort().forEach(e=>fe.add(new Option(e,e)));fe.onchange=()=>{st.est=fe.value;render()};
$('fTienda').onclick=e=>{e.preventDefault();st.tienda=!st.tienda;$('fTienda').classList.toggle('on',st.tienda);render()};$('fTienda').classList.add('on');
const tabs=['Resumen','Tendencias','Cadenas','Productos','Geografía','Top tiendas','Calidad del dato'];
tabs.forEach(t=>{const b=document.createElement('button');b.textContent=t;b.onclick=()=>{st.tab=t;render()};$('tabs').appendChild(b)});

const okT=i=>st.emb.has(TD.embotellador[TC.embotellador[i]])&&st.cad.has(TD.cadena[TC.cadena[i]])&&(!st.est||TD.estado[TC.estado[i]]===st.est)&&(!st.tienda||TD.tipo_punto[TC.tipo_punto[i]]==='Tienda');
function filas(){const r=[];for(let i=0;i<NT;i++)if(okT(i))r.push(i);return r}
const v=(i,k)=>TC[k][i], dv=(i,k)=>TD[k][TC[k][i]];
function cadenasSel(){return D.orden_cadenas.filter(c=>st.cad.has(c)&&TD.cadena.includes(c))}

// agregados por cadena desde tiendas
function porCadena(rows,key='cadena'){const A={};for(const i of rows){const c=dv(i,key);const a=A[c]||(A[c]={n:0,comp:0,rev:0,revp:0,cj:0,ing:0,nIng:0,sinv:0,pot:0,vh:0,nuevo:0,perd:0,nunca:0,activo:0,mc:0});
 a.n++;const r=v(i,'revenue_12m');a.rev+=r;a.revp+=v(i,'revenue_12m_anterior');a.cj+=v(i,'cajas_12m');if(r>0){a.comp++;a.mc+=v(i,'meses_con_compra')}
 if(!v(i,'ing_nulo')){a.nIng++;a.ing+=v(i,'ing');if(v(i,'ing')<=0)a.sinv++}a.pot+=v(i,'pot');const p=dv(i,'prioridad');if(p==='Very High'||p==='High')a.vh++;
 const s=dv(i,'estatus');if(s.startsWith('Nuevo'))a.nuevo++;else if(s.startsWith('Perdido'))a.perd++;else if(s.startsWith('Nunca'))a.nunca++;else a.activo++}return A}

// --- gráficas SVG ---
function barras(el,items,fmt,opt={}){// items: [{l,v,c,tip}]
 const W=$(el).clientWidth||560,h=26,lw=opt.lw||130,max=Math.max(...items.map(x=>Math.abs(x.v)).filter(isFinite),1e-9),neg=items.some(x=>x.v<0);
 const x0=neg?lw+(W-lw-70)/2:lw,esc_=(W-lw-70)/(neg?2:1)/max;
 let s=`<svg width="${W}" height="${items.length*h+6}" role="img">`;
 items.forEach((it,k)=>{const y=k*h+4,w=Math.abs(it.v)*esc_||0,x=it.v<0?x0-w:x0;
  s+=`<text x="${lw-8}" y="${y+14}" text-anchor="end">${esc(it.l)}</text><rect data-k="${k}" x="${x}" y="${y+3}" width="${Math.max(w,0)}" height="16" rx="4" fill="${it.c||PAL[0]}"/>
  <text x="${it.v<0?x-6:x+w+6}" y="${y+15}" text-anchor="${it.v<0?'end':'start'}" class="v">${fmt(it.v)}</text>`});
 if(neg)s+=`<line x1="${x0}" x2="${x0}" y1="0" y2="${items.length*h+4}" stroke="#999EA6"/>`;
 $(el).innerHTML=s+'</svg>';$(el).querySelectorAll('rect').forEach(r=>{const it=items[r.dataset.k];r.onmousemove=e=>tip(e,it.tip||`<b>${esc(it.l)}</b><br>${fmt(it.v)}`);r.onmouseleave=untip})}

function lineas(el,meses,series,fmt){// series: [{l,c,vals[]}]
 const W=$(el).clientWidth||900,H=300,m={l:64,r:16,t:10,b:28},w=W-m.l-m.r,h=H-m.t-m.b;
 const max=Math.max(...series.flatMap(s=>s.vals).filter(isFinite),1e-9),X=i=>m.l+(meses.length<2?0:i*w/(meses.length-1)),Y=v=>m.t+h-v/max*h;
 let s=`<svg width="${W}" height="${H}">`;
 for(let k=0;k<=4;k++){const yv=max*k/4,y=Y(yv);s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${y}" y2="${y}" stroke="#141417"/><text x="${m.l-8}" y="${y+4}" text-anchor="end">${fmt(yv)}</text>`}
 meses.forEach((mm,i)=>{if(i%3===0||i===meses.length-1)s+=`<text x="${X(i)}" y="${H-8}" text-anchor="middle">${mm.slice(0,4)}-${mm.slice(4)}</text>`});
 series.forEach(se=>{s+=`<path d="${se.vals.map((v,i)=>(i?'L':'M')+X(i)+','+Y(v||0)).join('')}" fill="none" stroke="${se.c}" stroke-width="2" stroke-dasharray="${DASH[se.l]||''}"/>`});
 s+=`<line id="${el}x" y1="${m.t}" y2="${m.t+h}" stroke="#999EA6" stroke-dasharray="3 3" style="display:none"/><rect x="${m.l}" y="${m.t}" width="${w}" height="${h}" fill="transparent" id="${el}r"/></svg>`;
 $(el).innerHTML=s;const r=$(el+'r'),cx=$(el+'x');
 r.onmousemove=e=>{const b=r.getBoundingClientRect(),i=Math.max(0,Math.min(meses.length-1,Math.round((e.clientX-b.left)/w*(meses.length-1))));cx.setAttribute('x1',X(i));cx.setAttribute('x2',X(i));cx.style.display='';
  tip(e,`<b>${meses[i]}</b><br>`+series.map(se=>`<span style="color:${se.c}">■</span> ${esc(se.l)}: ${fmt(se.vals[i])}`).join('<br>'))};
 r.onmouseleave=()=>{cx.style.display='none';untip()}}

function tabla(el,cols,rows,opt={}){// cols: [{k,l,f,t(text)}]
 const o=st.orden[el]||opt.orden;if(o){const c=cols.find(c=>c.k===o.k);rows=[...rows].sort((a,b)=>{const x=a[o.k],y=b[o.k];return(typeof x==='string'?String(x).localeCompare(y):((x??-1e18)-(y??-1e18)))*(o.d?-1:1)})}
 if(opt.lim)rows=rows.slice(0,opt.lim);
 let s='<table><thead><tr>'+cols.map(c=>`<th data-k="${c.k}">${c.l}${o&&o.k===c.k?(o.d?' ↓':' ↑'):''}</th>`).join('')+'</tr></thead><tbody>';
 for(const r of rows)s+='<tr>'+cols.map(c=>`<td class="${c.t?'t':''}">${c.h?c.h(r):c.f?c.f(r[c.k],r):esc(r[c.k])}</td>`).join('')+'</tr>';
 $(el).innerHTML=s+'</tbody></table>';$(el).querySelectorAll('th').forEach(th=>th.onclick=()=>{const k=th.dataset.k,p=st.orden[el]||opt.orden||{};st.orden[el]={k,d:p.k===k?!p.d:true};render()})}
const cP=v=>v==null||!isFinite(v)?'—':`<span class="${v>=0?'pos':'negv'}">${fmtP(v,1)}</span>`;
const cadCell=r=>`<span style="color:${COLOR[r.cadena]||PAL[3]}">●</span> ${esc(r.cadena)}`;

// --- pestañas ---
function resumen(rows){const A=porCadena(rows),t=Object.values(A).reduce((s,a)=>{for(const k in a)s[k]=(s[k]||0)+a[k];return s},{});
 const k=[['PdV',fmtN(t.n)],['Compran el análisis',fmtP(t.comp/t.n)],['Revenue 12m',fmt$(t.rev),1],['vs año anterior',fmtP(t.rev/t.revp-1,1)],['Revenue por tienda compradora',fmt$(t.rev/t.comp)],['Dejaron de comprar',fmtN(t.perd)],['Potencial (cajas/mes)',t.pot?fmtN(t.pot):'—',1],['Very High + High',t.vh?fmtN(t.vh):'—']];
 if(t.nIng)k.splice(2,0,['Venta del mes por tienda (todas las categorías)',fmt$(t.ing/t.nIng)]);
 $('kpis').innerHTML=k.map(([l,v,a])=>`<div class="kpi${a?' ac':''}"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
 $('hall').innerHTML=Object.entries(D.meta).filter(([e])=>st.emb.has(e)).map(([e,m])=>`<h2 style="font-size:13px;margin:8px 0 4px">${e}</h2><ul class="h">`+Object.entries(m.hallazgos).map(([a,b])=>`<li><b>${a}.</b> ${esc(b)}</li>`).join('')+'</ul>').join('');
 const R=cadenasSel().filter(c=>A[c]).map(c=>{const a=A[c];return{cadena:c,n:a.n,pen:a.comp/a.n,rev:a.rev,crec:a.revp?a.rev/a.revp-1:null,share:a.rev/t.rev,rpt:a.comp?a.rev/a.comp:null,ppc:a.cj?a.rev/a.cj:null,ing:a.nIng?a.ing/a.nIng:null,sinv:a.nIng?a.sinv/a.nIng:null,perd:a.perd,pot:a.pot||null,vh:a.vh||null}});
 tabla('score',[{k:'cadena',l:'Cadena',h:cadCell},{k:'n',l:'PdV',f:fmtN},{k:'pen',l:'% compran',f:v=>fmtP(v)},{k:'rev',l:'Revenue 12m',f:fmt$},{k:'share',l:'% del revenue',f:v=>fmtP(v)},{k:'crec',l:'vs año ant.',f:cP},{k:'rpt',l:'Rev./tienda compradora',f:fmt$},{k:'ppc',l:'Precio/caja',f:fmt$},{k:'ing',l:'Venta mes/tienda',f:fmt$},{k:'sinv',l:'% sin venta mes',f:v=>fmtP(v)},{k:'perd',l:'Dejaron de comprar',f:fmtN},{k:'pot',l:'Potencial cajas/mes',f:fmtN},{k:'vh',l:'VH+H',f:fmtN}],R,{orden:{k:'rev',d:true}})}

function okM(cube,i){const C=cube.col,Dd=cube.dic;return st.emb.has(Dd.embotellador[C.embotellador[i]])&&st.cad.has(Dd.cadena[C.cadena[i]])&&(!st.est||Dd.estado[C.estado[i]]===st.est)}
function tendencias(){const M=D.mensual,C=M.col,meses=[...M.dic.month_445].sort(),S={};
 for(let i=0;i<C.rev.length;i++){if(!okM(M,i))continue;const c=M.dic.cadena[C.cadena[i]],m=M.dic.month_445[C.month_445[i]],o=(S[c]=S[c]||{}),x=(o[m]=o[m]||{rev:0,cj:0,pdv:0});x.rev+=C.rev[i];x.cj+=C.cj[i];x.pdv+=C.pdv[i]}
 const mt=st.mTend,val=x=>!x?0:mt==='ppc'?(x.cj?x.rev/x.cj:null):x[mt],fm=mt==='rev'||mt==='ppc'?fmt$:fmtN;
 const ser=cadenasSel().filter(c=>S[c]).map(c=>({l:c,c:COLOR[c],vals:meses.map(m=>val(S[c][m]))}));
 $('legTend').innerHTML=ser.map(s=>`<span><i style="background:${s.c}"></i>${esc(s.l)}</span>`).join('');
 $('nTend').textContent='Ventas del catálogo validado. PdV compradores = tiendas distintas con compra en el mes. Precio/caja = revenue / cajas.';
 lineas('cTend',meses,ser,fm);
 const yoy=[];for(const [e,m] of Object.entries(D.meta)){if(!st.emb.has(e))continue}
 const P=Object.values(D.meta).filter((m,k)=>st.emb.has(Object.keys(D.meta)[k])).map(m=>m.periodo);
 const ult=new Set(),ant=new Set();P.forEach(p=>{meses.forEach(m=>{if(m>=p.desde&&m<=p.hasta){ult.add(m);ant.add(String(+m-100))}})});
 const Y=cadenasSel().filter(c=>S[c]).map(c=>{let a=0,b=0;for(const m in S[c]){if(ult.has(m))a+=S[c][m].rev;if(ant.has(m))b+=S[c][m].rev}return{l:c,v:b?a/b-1:NaN,c:COLOR[c],tip:`<b>${esc(c)}</b><br>12m: ${fmt$(a)}<br>año anterior: ${fmt$(b)}<br>${fmtP(a/b-1,1)}`}}).filter(x=>isFinite(x.v));
 barras('cYoy',Y,v=>fmtP(v,1));
 const tot={};for(const c in S)for(const m in S[c])tot[m]=(tot[m]||0)+S[c][m].rev;
 const comp=meses.filter(m=>P.some(p=>m<=p.hasta)),cal={};comp.forEach(m=>{const k=m.slice(4);(cal[k]=cal[k]||[]).push(tot[m]||0)});
 const avg=comp.reduce((s,m)=>s+(tot[m]||0),0)/comp.length,nom=['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
 barras('cEst',Object.keys(cal).sort().map(k=>({l:nom[+k-1],v:cal[k].reduce((a,b)=>a+b,0)/cal[k].length/avg*100,c:PAL[0]})),v=>Math.round(v)+'',{lw:50})}

function cadenas(rows){const A=porCadena(rows),cs=cadenasSel().filter(c=>A[c]);
 barras('cPen',cs.map(c=>({l:c,v:A[c].comp/A[c].n,c:COLOR[c],tip:`<b>${esc(c)}</b><br>${fmtN(A[c].comp)} de ${fmtN(A[c].n)} tiendas`})),v=>fmtP(v));
 barras('cProd',cs.map(c=>({l:c,v:A[c].comp?A[c].rev/A[c].comp:0,c:COLOR[c]})),fmt$);
 const est=['activo','nuevo','perd','nunca'],nomE={activo:'Activo',nuevo:'Nuevo',perd:'Perdido',nunca:'Nunca compró'},colE={activo:PAL[0],nuevo:PAL[1],perd:PAL[2],nunca:'#141417'};
 const W=$('cStat').clientWidth||560;let s=`<div class="leg">${est.map(k=>`<span><i style="background:${colE[k]};height:10px"></i>${nomE[k]}</span>`).join('')}</div><svg width="${W}" height="${cs.length*28+4}">`;
 cs.forEach((c,k)=>{let x=130;s+=`<text x="122" y="${k*28+18}" text-anchor="end">${esc(c)}</text>`;est.forEach(e=>{const w=(W-140)*A[c][e]/A[c].n;s+=`<rect x="${x}" y="${k*28+5}" width="${Math.max(w-2,0)}" height="18" fill="${colE[e]}" data-t="${esc(c)}: ${nomE[e]} ${fmtN(A[c][e])} (${fmtP(A[c][e]/A[c].n)})"/>`;x+=w})});
 $('cStat').innerHTML=s+'</svg>';$('cStat').querySelectorAll('rect').forEach(r=>{r.onmousemove=e=>tip(e,r.dataset.t);r.onmouseleave=untip});
 const F=porCadena(rows,'formato'),R=[];for(const i of rows){}
 const fc={};for(const i of rows)fc[dv(i,'formato')]=dv(i,'cadena');
 tabla('tFmt',[{k:'formato',l:'Formato',t:1},{k:'cadena',l:'Cadena'},{k:'n',l:'PdV',f:fmtN},{k:'pen',l:'% compran',f:v=>fmtP(v)},{k:'rpt',l:'Rev./tienda compradora',f:fmt$},{k:'crec',l:'vs año ant.',f:cP},{k:'ing',l:'Venta mes/tienda',f:fmt$}],
  Object.entries(F).map(([f,a])=>({formato:f,cadena:fc[f],n:a.n,pen:a.comp/a.n,rpt:a.comp?a.rev/a.comp:null,crec:a.revp?a.rev/a.revp-1:null,ing:a.nIng?a.ing/a.nIng:null})),{orden:{k:'n',d:true}})}

function productos(){const P=D.productos,C=P.col,At=D.atributos,ag={};
 for(let i=0;i<C.rev.length;i++){if(!okM(P,i))continue;const pr=P.dic.prod[C.prod[i]],c=P.dic.cadena[C.cadena[i]],w=P.dic.ventana[C.ventana[i]],a=(ag[pr]=ag[pr]||{}),x=(a[c]=a[c]||{rev:0,revp:0,cj:0,pdv:0});
  if(w==='12m'){x.rev+=C.rev[i];x.cj+=C.cj[i];x.pdv+=C.pdv[i]}else x.revp+=C.rev[i]}
 const at=p=>At[p]||{desc:p.split('|')[1],seg:'(sin catálogo)',marca:'(sin catálogo)',pres:'(sin catálogo)'};
 const por=(k)=>{const o={};for(const p in ag)for(const c in ag[p]){const key=at(p)[k]||'(vacío)',x=ag[p][c],y=(o[key]=o[key]||{rev:0,revp:0,cj:0,pdv:0,byC:{}});y.rev+=x.rev;y.revp+=x.revp;y.cj+=x.cj;y.pdv+=x.pdv;y.byC[c]=(y.byC[c]||0)+x.rev}return o};
 const seg=por('seg'),segs=Object.keys(seg).sort((a,b)=>seg[b].rev-seg[a].rev),cs=cadenasSel(),colS={};segs.forEach((s,i)=>colS[s]=PAL[Math.min(i,3)]);
 $('legSeg').innerHTML=segs.map(s=>`<span><i style="background:${colS[s]};height:10px"></i>${esc(s)}</span>`).join('');
 const W=$('cSeg').clientWidth||560;let s=`<svg width="${W}" height="${cs.length*28+4}">`;
 cs.forEach((c,k)=>{const tot=segs.reduce((a,g)=>a+(seg[g].byC[c]||0),0);if(!tot)return;let x=130;s+=`<text x="122" y="${k*28+18}" text-anchor="end">${esc(c)}</text>`;
  segs.forEach(g=>{const v=(seg[g].byC[c]||0)/tot,w=(W-140)*v;s+=`<rect x="${x}" y="${k*28+5}" width="${Math.max(w-2,0)}" height="18" fill="${colS[g]}" data-t="${esc(c)} · ${esc(g)}: ${fmtP(v)} (${fmt$(seg[g].byC[c]||0)})"/>`;if(w>40)s+=`<text x="${x+4}" y="${k*28+18}" style="fill:#141417">${Math.round(v*100)}%</text>`;x+=w})});
 $('cSeg').innerHTML=s+'</svg>';$('cSeg').querySelectorAll('rect').forEach(r=>{r.onmousemove=e=>tip(e,r.dataset.t);r.onmouseleave=untip});
 const fila=(o,k)=>Object.entries(o).map(([n,y])=>({[k]:n,rev:y.rev,crec:y.revp?y.rev/y.revp-1:null,ppc:y.cj?y.rev/y.cj:null,cj:y.cj,...Object.fromEntries(cs.map(c=>['c_'+c,y.byC[c]||0]))}));
 const colsC=cs.map(c=>({k:'c_'+c,l:c,f:fmt$}));
 tabla('tMarca',[{k:'marca',l:'Marca',t:1},{k:'rev',l:'Revenue 12m',f:fmt$},{k:'crec',l:'vs año ant.',f:cP},{k:'ppc',l:'Precio/caja',f:fmt$},...colsC],fila(por('marca'),'marca'),{orden:{k:'rev',d:true}});
 tabla('tPres',[{k:'pres',l:'Presentación',t:1},{k:'rev',l:'Revenue 12m',f:fmt$},{k:'crec',l:'vs año ant.',f:cP},{k:'ppc',l:'Precio/caja',f:fmt$},...colsC],fila(por('pres'),'pres'),{orden:{k:'rev',d:true}});
 const R=Object.entries(ag).map(([p,o])=>{const y={rev:0,revp:0,cj:0,pdv:0};for(const c in o){y.rev+=o[c].rev;y.revp+=o[c].revp;y.cj+=o[c].cj;y.pdv+=o[c].pdv}const a=at(p);return{emb:p.split('|')[0],desc:a.desc,seg:a.seg,marca:a.marca,pres:a.pres,rev:y.rev,crec:y.revp?y.rev/y.revp-1:null,ppc:y.cj?y.rev/y.cj:null,pdv:y.pdv}});
 tabla('tProd',[{k:'desc',l:'Producto',t:1},{k:'emb',l:'Emb.'},{k:'seg',l:'Segmento'},{k:'pres',l:'Pres.'},{k:'rev',l:'Revenue 12m',f:fmt$},{k:'crec',l:'vs año ant.',f:cP},{k:'ppc',l:'Precio/caja',f:fmt$},{k:'pdv',l:'Tiendas',f:fmtN}],R,{orden:{k:'rev',d:true},lim:60})}

function geografia(rows){const cs=cadenasSel(),E={};
 for(const i of rows){const e=dv(i,'estado'),c=dv(i,'cadena'),x=(E[e]=E[e]||{n:0,rev:0,revp:0,comp:0,byC:{}});x.n++;x.byC[c]=(x.byC[c]||0)+1;x.rev+=v(i,'revenue_12m');x.revp+=v(i,'revenue_12m_anterior');if(v(i,'revenue_12m')>0)x.comp++}
 const R=Object.entries(E).map(([e,x])=>({estado:e,n:x.n,dens:D.poblacion[e]?x.n/D.poblacion[e]*1e5:null,pob:D.poblacion[e]||null,rev:x.rev,crec:x.revp?x.rev/x.revp-1:null,pen:x.comp/x.n,...Object.fromEntries(cs.map(c=>['c_'+c,x.byC[c]||0]))}));
 const mx=Math.max(...R.map(r=>r.dens||0));
 tabla('tGeo',[{k:'estado',l:'Estado',t:1},...cs.map(c=>({k:'c_'+c,l:c,f:fmtN})),{k:'n',l:'Total PdV',f:fmtN},{k:'pob',l:'Población',f:fmtN},{k:'dens',l:'PdV / 100 mil hab.',h:r=>`${r.dens?r.dens.toFixed(1):'—'} <span class="bar" style="width:${(r.dens||0)/mx*60}px"></span>`},{k:'pen',l:'% compran',f:v=>fmtP(v)},{k:'rev',l:'Revenue 12m',f:fmt$},{k:'crec',l:'vs año ant.',f:cP}],R,{orden:{k:'n',d:true}});
 if(cs.length<2){$('tBlanco').innerHTML='<p class="n">Elige al menos 2 cadenas.</p>';return}
 const Mu={};for(const i of rows){const k=dv(i,'municipio')+' · '+dv(i,'estado'),c=dv(i,'cadena'),x=(Mu[k]=Mu[k]||{});x[c]=(x[c]||0)+1}
 const B=Object.entries(Mu).filter(([k,x])=>x[cs[0]]&&!x[cs[1]]).map(([k,x])=>({mun:k,a:x[cs[0]],...Object.fromEntries(cs.slice(2).map(c=>['c_'+c,x[c]||0]))}));
 tabla('tBlanco',[{k:'mun',l:'Municipio',t:1},{k:'a',l:`PdV ${cs[0]} (sin ${cs[1]})`,f:fmtN},...cs.slice(2).map(c=>({k:'c_'+c,l:c,f:fmtN}))],B,{orden:{k:'a',d:true},lim:100})}

function topTiendas(rows){const q=($('buscar').value||'').toLowerCase();
 const R=rows.filter(i=>!q||TC.nombre[i].toLowerCase().includes(q)||TC.pos_id[i].includes(q)).map(i=>({pos_id:TC.pos_id[i],nombre:TC.nombre[i],cadena:dv(i,'cadena'),emb:dv(i,'embotellador'),formato:dv(i,'formato'),estado:dv(i,'estado'),municipio:dv(i,'municipio'),
  revenue_12m:v(i,'revenue_12m'),delta:v(i,'revenue_12m')-v(i,'revenue_12m_anterior'),crec:v(i,'revenue_12m_anterior')?v(i,'revenue_12m')/v(i,'revenue_12m_anterior')-1:null,ing:v(i,'ing_nulo')?null:v(i,'ing'),pot:v(i,'pot')||null,pri:dv(i,'prioridad'),estatus:dv(i,'estatus'),ult:dv(i,'ult')}));
 const o=st.mTop==='caida'?{k:'delta',d:false}:{k:st.mTop,d:true};st.orden.tTop=st.orden.tTop&&st.orden.tTop._u?st.orden.tTop:o;
 tabla('tTop',[{k:'nombre',l:'Tienda',t:1},{k:'pos_id',l:'pos_id'},{k:'cadena',l:'Cadena',h:cadCell},{k:'emb',l:'Emb.'},{k:'estado',l:'Estado',t:1},{k:'municipio',l:'Municipio',t:1},{k:'revenue_12m',l:'Revenue 12m',f:fmt$},{k:'delta',l:'Δ vs año ant.',f:v=>`<span class="${v>=0?'pos':'negv'}">${fmt$(v)}</span>`},{k:'crec',l:'%',f:cP},{k:'ing',l:'Venta mes',f:fmt$},{k:'pot',l:'Potencial cajas/mes',f:fmtN},{k:'pri',l:'Prioridad'},{k:'estatus',l:'Estatus',f:v=>`<span class="pill">${esc(v)}</span>`},{k:'ult',l:'Últ. compra'}],R,{lim:200})}

function calidad(rows){const C={};const L=[];for(const i of rows){const a=dv(i,'alertas');if(a==='(sin alerta)')continue;a.split('; ').forEach(x=>C[x]=(C[x]||0)+1);L.push(i)}
 barras('tAl',Object.entries(C).sort((a,b)=>b[1]-a[1]).map(([k,n])=>({l:k,v:n,c:PAL[2]})),fmtN,{lw:290});
 $('tFu').innerHTML=Object.entries(D.meta).filter(([e])=>st.emb.has(e)).map(([e,m])=>`<h2 style="font-size:13px;margin:8px 0 4px">${e}</h2><ul class="h">`+m.fuentes.map(f=>`<li><b>${esc(f.dato)}</b> (${esc(f.fecha||'—')}): <code style="font-size:11px">${esc(f.ruta)}</code></li>`).join('')+
  `<li>Clientes validados en bronze: ${fmtN(m.clientes_bronze)}</li><li>Ventas: ${m.periodo.desde}–${m.periodo.hasta} (${m.periodo.meses} meses) vs ${m.periodo.anterior_desde}–${m.periodo.anterior_hasta}${m.periodo.incompleto?`; ${m.periodo.incompleto} incompleto (${Math.round(m.periodo.pct_incompleto*100)}% de un mes normal), fuera`:''}</li>`+
  (m.mes_venta_clientes?`<li>Mes de la venta del archivo de clientes: ${Object.entries(m.mes_venta_clientes).map(([a,b])=>esc(a)+' '+fmtN(b)).join(' · ')}</li>`:'<li>Venta del mes por tienda: POR VERIFICAR (el archivo de clientes no la trae)</li>')+'</ul>').join('');
 tabla('tAlD',[{k:'nombre',l:'PdV',t:1},{k:'pos_id',l:'pos_id'},{k:'cadena',l:'Cadena'},{k:'tipo',l:'Tipo',t:1},{k:'estado',l:'Estado',t:1},{k:'al',l:'Alertas',t:1}],
  L.map(i=>({nombre:TC.nombre[i],pos_id:TC.pos_id[i],cadena:dv(i,'cadena'),tipo:dv(i,'tipo_punto'),estado:dv(i,'estado'),al:dv(i,'alertas')})),{lim:300})}

const seg=(id,opts,key)=>{$(id).innerHTML='';opts.forEach(([k,l])=>{const b=document.createElement('button');b.textContent=l;b.className=st[key]===k?'on':'';b.onclick=()=>{st[key]=k;if(key==='mTop')st.orden.tTop=null;render()};$(id).appendChild(b)})};
$('buscar').oninput=()=>render();
function render(){document.querySelectorAll('.tab').forEach(s=>s.classList.toggle('on',s.dataset.t===st.tab));document.querySelectorAll('#tabs button').forEach(b=>b.classList.toggle('on',b.textContent===st.tab));
 const rows=filas();
 if(st.tab==='Resumen')resumen(rows);
 if(st.tab==='Tendencias'){seg('mTend',[['rev','Revenue'],['cj','Cajas'],['pdv','PdV compradores'],['ppc','Precio por caja']],'mTend');tendencias()}
 if(st.tab==='Cadenas')cadenas(rows);
 if(st.tab==='Productos')productos();
 if(st.tab==='Geografía')geografia(rows);
 if(st.tab==='Top tiendas'){seg('mTop',[['revenue_12m','Revenue 12m'],['delta','Mayor crecimiento $'],['caida','Mayor caída $'],['pot','Potencial'],['ing','Venta del mes']],'mTop');topTiendas(rows)}
 if(st.tab==='Calidad del dato')calidad(rows)}
addEventListener('resize',()=>render());
render();
</script></body></html>"""
