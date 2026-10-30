"""Mapa interactivo (HTML autónomo) de clientes, ventas, riesgo y potencial por hexágono H3.

Privacidad (SPEC RNF-06): el HTML no lleva ninguna coordenada de PDV; solo IDs de hexágono y sumas por hexágono
(h3-js dibuja el borde en el navegador). Si aparece una coordenada exacta, se aborta.
Mapa base: OpenFreeMap (sin key) con MapLibre GL dentro de Leaflet; la capa GL se agrega después del primer fitBounds.
"""
import json

import h3
import pandas as pd

from src.tools import marca

RESOLUCIONES = (6, 7, 8)
METRICAS = {  # clave: (etiqueta, formato)
    "n": ("Clientes", "n"), "r12": ("Revenue últimos 12 meses", "$"), "crec": ("Crecimiento vs año anterior", "%"),
    "c12": ("Cajas últimos 12 meses", "n"), "riesgo": ("Clientes en riesgo", "n"),
    "pot": ("Potencial (cajas/mes, modelo)", "n"), "vh": ("Clientes prioridad Very High + High", "n"),
}


def _datos(cli):
    d = cli.dropna(subset=["lat", "lon"]).copy()
    d["vh"] = d["prioridad"].isin(["Very High", "High"]).astype(int)
    d["riesgo"] = (d["segmento"] == "En riesgo").astype(int)
    dic = {k: sorted(d[k].fillna("(vacío)").unique().tolist()) for k in ("embotellador", "estado", "segmento")}
    filas = []
    for res in RESOLUCIONES:
        d["h"] = [h3.latlng_to_cell(a, b, res) for a, b in zip(d["lat"], d["lon"])]
        g = d.groupby(["h", "embotellador", "estado", "segmento"], dropna=False).agg(
            n=("pos_id", "size"), r12=("revenue_12m", "sum"), rp=("revenue_12m_anterior", "sum"), c12=("cajas_12m", "sum"),
            riesgo=("riesgo", "sum"), pot=("potencial_cajas_mes", "sum"), vh=("vh", "sum")).reset_index()
        g["res"] = res
        filas.append(g)
    g = pd.concat(filas)
    col = {"res": g["res"].tolist(), "h": g["h"].tolist()}
    for k in ("embotellador", "estado", "segmento"):
        idx = {v: i for i, v in enumerate(dic[k])}
        col[k] = [idx[v] for v in g[k].fillna("(vacío)")]
    for k in ("n", "riesgo", "vh"):
        col[k] = g[k].astype(int).tolist()
    for k in ("r12", "rp", "c12", "pot"):
        col[k] = g[k].fillna(0).round(1).tolist()
    con_pot = sorted(cli.loc[cli["potencial_cajas_mes"].notna(), "embotellador"].unique().tolist())
    return {"dic": dic, "col": col, "con_potencial": con_pot, "sin_coordenadas": int(len(cli) - len(d))}


def escribir(ruta, cli, r, hallazgos, analisis, pais):
    datos = _datos(cli)
    html = (PLANTILLA.replace("__FUENTES__", marca.fuentes_css()).replace("__LOGO__", marca.logo_data_uri("formal", "oscuro"))
            .replace("__DATOS__", json.dumps(datos, ensure_ascii=False, separators=(",", ":")))
            .replace("__METRICAS__", json.dumps(METRICAS, ensure_ascii=False))
            .replace("__HALLAZGOS__", json.dumps(hallazgos, ensure_ascii=False))
            .replace("__TITULO__", f"Customer Potential · {analisis} · {pais.upper()}"))
    muestra = cli.dropna(subset=["lat", "lon"]).sample(min(500, len(cli)), random_state=1)
    for a, b in zip(muestra["lat"], muestra["lon"]):
        assert f"{a}" not in html or f"{b}" not in html, "el mapa trae coordenadas exactas de un PDV: aborto"
    ruta.write_text(html, encoding="utf-8")
    print(f"mapa: {len(datos['col']['h']):,} filas de hexágonos; {datos['sin_coordenadas']} clientes sin coordenada")
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
:root{--neg:#141417;--ama:#E5FF01;--g1:#EFEFEE;--g2:#D4D5D6;--g3:#999EA6;--bg:#fff;--txt:#141417}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--bg);color:var(--txt);font-family:'Albert Sans',system-ui,sans-serif}
#app{display:flex;height:100%}
aside{width:360px;flex:none;overflow-y:auto;background:var(--neg);color:#fff;padding:18px 18px 28px}
h1{font-family:'Space Grotesk',sans-serif;font-size:19px;margin:0 0 2px;line-height:1.2}
h1 b{color:var(--ama)}
.sub{color:var(--g3);font-size:12px;margin-bottom:14px}
h2{font-family:'Space Grotesk',sans-serif;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--g3);margin:16px 0 6px}
.kpis{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.kpi{background:#222326;border-radius:10px;padding:9px 10px}
.kpi .v{font-family:'Space Grotesk',sans-serif;font-size:19px;font-weight:700}
.kpi .l{font-size:11px;color:var(--g3)}
.kpi.ac .v{color:var(--ama)}
label{display:flex;gap:6px;align-items:center;font-size:13px;margin:3px 0;cursor:pointer}
select{width:100%;padding:6px;border-radius:6px;border:0;font:inherit;font-size:13px}
.seg{display:flex;flex-wrap:wrap;gap:6px}
.seg button{border:1px solid #444;background:transparent;color:#fff;border-radius:999px;padding:4px 10px;font:inherit;font-size:12px;cursor:pointer}
.seg button.on{background:var(--ama);color:var(--neg);border-color:var(--ama);font-weight:600}
ul.h{padding-left:16px;margin:4px 0;font-size:12.5px;line-height:1.45;color:#ddd}ul.h li{margin-bottom:6px}
#map{flex:1;position:relative}
.leg{background:#fff;padding:8px 10px;border-radius:8px;font-size:12px;line-height:1.5;box-shadow:0 1px 4px rgba(0,0,0,.25)}
.leg i{display:inline-block;width:14px;height:10px;margin-right:6px;border:1px solid #0002}
.tip{font-family:'Albert Sans',sans-serif;font-size:12px}.tip b{font-family:'Space Grotesk',sans-serif}
.nota{font-size:11px;color:var(--g3);margin-top:14px}.url{font:500 12px 'Albert Sans',sans-serif;color:var(--g3);letter-spacing:.02em;margin-top:10px}
@media (max-width:760px){#app{flex-direction:column}aside{width:100%;max-height:45%}}
</style></head><body><div id="app">
<aside>
  <img src="__LOGO__" alt="Kin Analytics" style="height:20px;margin-bottom:12px">
  <h1>__TITULO__ <b>·</b></h1><div class="sub">Canal moderno · últimos 12 meses · revenue en MXN</div>
  <div class="kpis" id="kpis"></div>
  <h2>Ver por</h2><select id="met"></select>
  <h2>Embotellador</h2><div class="seg" id="embs"></div>
  <h2>Segmento de cliente</h2><div class="seg" id="segs"></div>
  <h2>Estado</h2><select id="est"></select>
  <h2>Tamaño del hexágono</h2><div class="seg" id="ress"></div>
  <h2>Qué dicen los datos</h2><ul class="h" id="hall"></ul>
  <div class="nota">Cada hexágono suma los clientes que caen en él; el mapa no muestra la ubicación exacta de ningún punto de venta.
  Potencial = resultado del modelo Customer Potential (solo embotelladores con gold). Mapa base © OpenFreeMap · OpenMapTiles · OpenStreetMap.</div>
  <div class="url">kinanalytics.com</div>
</aside>
<div id="map"></div></div>
<script>
const D=__DATOS__, M=__METRICAS__, H=__HALLAZGOS__;
const C=D.col, N=C.h.length;
const st={met:'r12',emb:new Set(D.dic.embotellador.map((_,i)=>i)),seg:new Set(D.dic.segmento.map((_,i)=>i)),est:-1,res:6};
const fmt=(v,t)=>t==='%'?(v==null||!isFinite(v)?'—':(v>=0?'+':'')+(v*100).toFixed(1)+'%'):t==='$'?'$'+abr(v):abr(v);
function abr(v){const a=Math.abs(v);return a>=1e9?(v/1e9).toFixed(2)+'B':a>=1e6?(v/1e6).toFixed(1)+'M':a>=1e4?(v/1e3).toFixed(1)+'K':Math.round(v).toLocaleString('es-MX')}
const sel=document.getElementById('met');
for(const[k,[l]]of Object.entries(M)){const o=new Option(l,k);if(k==='pot'||k==='vh')o.text+=' — '+(D.con_potencial.join(', ')||'sin gold');sel.add(o)}
sel.value=st.met;sel.onchange=()=>{st.met=sel.value;dibujar()};
function botones(id,items,set,unico){const el=document.getElementById(id);items.forEach(([v,l])=>{const b=document.createElement('button');b.textContent=l;
 const on=()=>b.classList.toggle('on',unico?st.res===v:set.has(v));on();
 b.onclick=()=>{if(unico)st.res=v;else{set.has(v)?set.delete(v):set.add(v);if(!set.size)set.add(v)}el.querySelectorAll('button').forEach(x=>x._on());dibujar()};b._on=on;el.appendChild(b)})}
botones('embs',D.dic.embotellador.map((e,i)=>[i,e]),st.emb);
botones('segs',D.dic.segmento.map((e,i)=>[i,e]),st.seg);
botones('ress',[[6,'Grande'],[7,'Mediano'],[8,'Chico']],null,true);
const se=document.getElementById('est');se.add(new Option('Todos',-1));D.dic.estado.forEach((e,i)=>se.add(new Option(e,i)));
se.onchange=()=>{st.est=+se.value;dibujar(true)};
document.getElementById('hall').innerHTML=H.map(x=>'<li>'+x.replace(/</g,'&lt;')+'</li>').join('');

const map=L.map('map',{preferCanvas:true,zoomControl:true,minZoom:3,maxZoom:15}).setView([23.6,-102.5],5);
const capa=L.layerGroup().addTo(map);let leyenda;
const RAMPA=['#D4D5D6','#999EA6','#222326','#141417','#E5FF01'], DIV=['#141417','#999EA6','#EFEFEE','#222326','#E5FF01'];

function agregar(){const A=new Map();const T={n:0,r12:0,rp:0,c12:0,riesgo:0,pot:0,vh:0},porE={};
 for(let i=0;i<N;i++){if(C.res[i]!==st.res||!st.emb.has(C.embotellador[i])||!st.seg.has(C.segmento[i])||(st.est>=0&&C.estado[i]!==st.est))continue;
  let a=A.get(C.h[i]);if(!a){a={n:0,r12:0,rp:0,c12:0,riesgo:0,pot:0,vh:0,e:{}};A.set(C.h[i],a)}
  const e=D.dic.embotellador[C.embotellador[i]];a.e[e]=(a.e[e]||0)+C.n[i];
  for(const k of['n','r12','rp','c12','riesgo','pot','vh']){a[k]+=C[k][i];T[k]+=C[k][i]}}
 return[A,T]}
const valor=(a,m)=>m==='crec'?(a.rp>0?a.r12/a.rp-1:null):a[m];

function dibujar(encuadrar){capa.clearLayers();const[A,T]=agregar(),m=st.met,t=M[m][1];
 const vals=[...A.values()].map(a=>valor(a,m)).filter(v=>v!=null&&isFinite(v)&&(m==='crec'||v>0)).sort((x,y)=>x-y);
 let cortes;if(m==='crec')cortes=[-0.2,-0.02,0.02,0.2];else cortes=[.2,.4,.6,.8].map(q=>vals[Math.floor(q*(vals.length-1))]||0);
 const pal=m==='crec'?DIV:RAMPA, color=v=>{let k=0;while(k<4&&v>cortes[k])k++;return pal[k]};
 const lim=[];
 for(const[h,a]of A){const v=valor(a,m);if(v==null||!isFinite(v)||(m!=='crec'&&v<=0))continue;
  const b=h3.cellToBoundary(h);lim.push(...b);
  L.polygon(b,{color:'#141417',weight:.3,fillColor:color(v),fillOpacity:.78}).bindTooltip(
   '<div class="tip"><b>'+M[m][0]+': '+fmt(v,t)+'</b><br>Clientes: '+a.n.toLocaleString('es-MX')+' ('+Object.entries(a.e).map(([e,n])=>e+' '+n).join(' · ')+')'+
   '<br>Revenue 12m: $'+abr(a.r12)+' · vs año anterior: '+fmt(a.rp>0?a.r12/a.rp-1:null,'%')+'<br>Cajas 12m: '+abr(a.c12)+
   '<br>En riesgo: '+a.riesgo+(a.pot?'<br>Potencial: '+abr(a.pot)+' cajas/mes · Very High+High: '+a.vh:'')+'</div>',{sticky:true}).addTo(capa)}
 if(encuadrar&&lim.length)try{map.fitBounds(L.latLngBounds(lim),{padding:[20,20]})}catch(e){console.warn('encuadre',e)}
 if(leyenda)map.removeControl(leyenda);leyenda=L.control({position:'bottomright'});
 leyenda.onAdd=()=>{const d=L.DomUtil.create('div','leg');const lab=m==='crec'?['< −20%','−20% a −2%','±2%','+2% a +20%','> +20%']:
  [0,1,2,3,4].map(k=>(k?'> '+fmt(cortes[k-1],t):'≤ '+fmt(cortes[0],t)));
  d.innerHTML='<b>'+M[m][0]+'</b><br>'+pal.map((c,k)=>'<i style="background:'+c+'"></i>'+lab[k]).join('<br>')+'<br><span style="color:#777">'+A.size.toLocaleString('es-MX')+' hexágonos</span>';return d};
 leyenda.addTo(map);
 const crec=T.rp>0?T.r12/T.rp-1:null;
 document.getElementById('kpis').innerHTML=[['Clientes',T.n.toLocaleString('es-MX')],['Revenue 12m','$'+abr(T.r12),1],['Vs año anterior',fmt(crec,'%')],
  ['Cajas 12m',abr(T.c12)],['En riesgo',T.riesgo.toLocaleString('es-MX')+' ('+(T.n?Math.round(100*T.riesgo/T.n):0)+'%)'],['Potencial cajas/mes',T.pot?abr(T.pot):'—',1]]
  .map(([l,v,ac])=>'<div class="kpi'+(ac?' ac':'')+'"><div class="v">'+v+'</div><div class="l">'+l+'</div></div>').join('')}
// La capa GL se agrega con el mapa ya dimensionado y encuadrado (antes lee un centro NaN y el mapa base queda en blanco)
window.addEventListener('load',()=>{map.invalidateSize();dibujar(true);
 L.maplibreGL({style:'https://tiles.openfreemap.org/styles/positron',attribution:'© OpenFreeMap © OpenMapTiles © OpenStreetMap'}).addTo(map);});
</script></body></html>"""
