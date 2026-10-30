"""
============================================================================
retail_outliers — deteccion de atipicos en datos retail, con rigor matematico
============================================================================
NumPy + SciPy + pandas. scikit-learn es opcional: sin el, la covarianza
robusta (MCD), Isolation Forest, LOF y el vecindario espacial no corren y
la funcion lo dice en vez de fallar.

Cubre los pasos computacionales del SKILL.md:

  1. reglas                                   -> atipicos matematicos (imposibles / identidades)
  2. univariado, z_clasico, z_robusto, iqr_tukey, boxplot_ajustado,
     gesd, cola_gpd                           -> atipicos univariados
  3. por_grupo, residuos_regresion            -> atipicos contextuales / condicionales
  4. mahalanobis_robusto, isolation_forest, lof -> atipicos multivariados
  5. hampel                                   -> atipicos temporales
  6. espacial                                 -> atipicos espaciales (vs vecinos)
  7. consenso, impacto, sensibilidad          -> decision y reporte

Uso:
    import sys; sys.path.insert(0, "<skill_dir>/scripts")
    import retail_outliers as ro
    tabla = ro.univariado(df["venta"])            # una fila por punto, un flag por metodo
    ro.impacto(df["venta"], tabla["atipico"])     # que cambia si se quitan

Linea de comandos (Excel con Resumen, Por punto, Metodos e Impacto):
    python retail_outliers.py datos.csv --col venta [--grupo subcanal]
           [--lat lat --lon lon] [--multi venta,cp,hogares] [--salida atipicos.xlsx]

Verificar el entorno:
    python retail_outliers.py --self-test
"""
from __future__ import annotations

import math
import sys
from typing import Sequence

import numpy as np
import pandas as pd
from scipy import stats

try:  # opcional
    from sklearn.covariance import MinCovDet as _MinCovDet
    from sklearn.ensemble import IsolationForest as _IsolationForest
    from sklearn.neighbors import BallTree as _BallTree
    from sklearn.neighbors import LocalOutlierFactor as _LOF
    _TIENE_SKLEARN = True
except ImportError:  # pragma: no cover - depende del entorno
    _TIENE_SKLEARN = False

SEMILLA = 0
K_MAD = 1.482602218505602  # MAD -> sigma bajo normalidad (1 / Phi^-1(0.75))
CORTE_Z_ROBUSTO = 3.5      # Iglewicz y Hoaglin (1993)


# ════════════════════════════════════════════════════════════════════════════
#  Utilidades internas
# ════════════════════════════════════════════════════════════════════════════

def _serie(x) -> pd.Series:
    """Lista, array, Serie de pandas o de polars -> Serie float64 (conserva el indice de pandas)."""
    if hasattr(x, "to_pandas") and not isinstance(x, pd.Series):  # polars
        x = x.to_pandas()
    if not isinstance(x, pd.Series):
        x = pd.Series(np.asarray(x, dtype="float64").ravel())
    return pd.to_numeric(x, errors="coerce").astype("float64")


def _df(df) -> pd.DataFrame:
    if hasattr(df, "to_pandas") and not isinstance(df, pd.DataFrame):  # polars
        return df.to_pandas()
    return df


def _bh(p) -> np.ndarray:
    """Benjamini-Hochberg sobre los p finitos; NaN se conserva."""
    p = np.asarray(p, dtype="float64")
    q = np.full_like(p, np.nan)
    m = np.isfinite(p)
    if m.any():
        q[m] = stats.false_discovery_control(np.clip(p[m], 0, 1), method="bh")
    return q


def mad_n(x) -> float:
    """MAD normalizada (estimador robusto de sigma, punto de quiebre 50%)."""
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    if x.size == 0:
        return float("nan")
    return float(K_MAD * np.median(np.abs(x - np.median(x))))


def _escala_robusta(x: np.ndarray) -> float:
    """MAD_n; si es 0 (mas de la mitad de valores iguales) cae a IQR/1.349 y luego a la media de |x - mediana|."""
    s = mad_n(x)
    if s > 0:
        return s
    q1, q3 = np.nanpercentile(x, [25, 75])
    if q3 > q1:
        return float((q3 - q1) / 1.349)
    return float(1.2533 * np.nanmean(np.abs(x - np.nanmedian(x))))  # sqrt(pi/2) * MeanAD


def medcouple(x, n_max: int = 3000, semilla: int = SEMILLA) -> float:
    """Medcouple de Brys, Hubert y Struyf (2004): asimetria robusta en [-1, 1].

    Version exacta O(n^2) sobre una submuestra de `n_max` puntos (el error de
    submuestreo es ~1/sqrt(n_max), despreciable para fijar las vallas).
    """
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    if x.size > n_max:
        x = np.random.default_rng(semilla).choice(x, n_max, replace=False)
    if x.size < 3:
        return 0.0
    m = np.median(x)
    xm = x[x <= m][:, None]  # x_i <= m
    xp = x[x >= m][None, :]  # x_j >= m
    den = xp - xm
    with np.errstate(divide="ignore", invalid="ignore"):
        h = ((xp - m) - (m - xm)) / den
    # nucleo en empates con la mediana (x_i = x_j = m): signo segun posicion; se toma 0 (neutro)
    h = np.where(den == 0, 0.0, h)
    return float(np.median(h))


# ════════════════════════════════════════════════════════════════════════════
#  1. Atipicos matematicos: valores imposibles e identidades rotas
# ════════════════════════════════════════════════════════════════════════════

def reglas(df, reglas: dict[str, str | pd.Series]) -> pd.DataFrame:
    """Evalua reglas deterministicas (un True = la fila VIOLA la regla).

    `reglas` = {nombre: expresion de pandas.eval o Serie booleana}, por ejemplo
        {"cantidad negativa": "cantidad < 0",
         "importe != cantidad x precio": "abs(importe - cantidad*precio) > 0.01",
         "fuera de la ZM": ~dentro_zm}
    Devuelve el df con una columna booleana por regla + `reglas_violadas` (texto) y `n_reglas`.
    Son atipicos ciertos (no estadisticos): no necesitan umbral ni prueba.
    """
    df = _df(df)
    out = pd.DataFrame(index=df.index)
    for nombre, regla in reglas.items():
        v = df.eval(regla) if isinstance(regla, str) else pd.Series(regla, index=df.index)
        out[nombre] = v.fillna(False).astype(bool)
    out["n_reglas"] = out.sum(axis=1)
    nombres = np.array(list(reglas))
    out["reglas_violadas"] = [
        " · ".join(nombres[fila]) if fila.any() else "" for fila in out[list(reglas)].to_numpy()
    ]
    return out


# ════════════════════════════════════════════════════════════════════════════
#  2. Atipicos univariados
# ════════════════════════════════════════════════════════════════════════════

def z_clasico(x, corte: float = 3.0) -> pd.DataFrame:
    """z = (x - media) / sd. Solo como referencia: media y sd se contaminan con los atipicos
    (enmascaramiento) y con n puntos el |z| maximo posible es (n-1)/sqrt(n)."""
    s = _serie(x)
    z = (s - s.mean()) / s.std(ddof=1)
    return pd.DataFrame({"z": z, "atipico": z.abs() > corte}, index=s.index)


def z_robusto(x, corte: float = CORTE_Z_ROBUSTO) -> pd.DataFrame:
    """z modificado de Iglewicz-Hoaglin: (x - mediana) / MAD_n. Corte 3.5."""
    s = _serie(x)
    v = s.to_numpy()
    z = (v - np.nanmedian(v)) / _escala_robusta(v)
    return pd.DataFrame({"z_robusto": z, "atipico": np.abs(z) > corte}, index=s.index)


def iqr_tukey(x, k: float = 1.5) -> pd.DataFrame:
    """Vallas de Tukey [Q1 - k IQR, Q3 + k IQR]; k = 1.5 'posible', k = 3 'lejano'.
    Bajo normalidad k = 1.5 marca 0.7% por construccion; en colas pesadas, mucho mas."""
    s = _serie(x)
    q1, q3 = np.nanpercentile(s, [25, 75])
    iqr = q3 - q1
    lo, hi = q1 - k * iqr, q3 + k * iqr
    return pd.DataFrame({"atipico": (s < lo) | (s > hi), "valla_inf": lo, "valla_sup": hi},
                        index=s.index)


def boxplot_ajustado(x, k: float = 1.5) -> pd.DataFrame:
    """Boxplot ajustado por asimetria (Hubert y Vandervieren 2008), con el medcouple MC:
       MC >= 0: [Q1 - k e^{-4MC} IQR, Q3 + k e^{3MC} IQR]
       MC <  0: [Q1 - k e^{-3MC} IQR, Q3 + k e^{4MC} IQR]
    Es el metodo por defecto para ventas en escala original (sesgo a la derecha)."""
    s = _serie(x)
    v = s.to_numpy()
    q1, q3 = np.nanpercentile(v, [25, 75])
    iqr = q3 - q1
    mc = medcouple(v)
    if mc >= 0:
        lo, hi = q1 - k * math.exp(-4 * mc) * iqr, q3 + k * math.exp(3 * mc) * iqr
    else:
        lo, hi = q1 - k * math.exp(-3 * mc) * iqr, q3 + k * math.exp(4 * mc) * iqr
    return pd.DataFrame({"atipico": (s < lo) | (s > hi), "valla_inf": lo, "valla_sup": hi,
                         "medcouple": mc}, index=s.index)


def gesd(x, max_atipicos: int | None = None, alpha: float = 0.05) -> pd.DataFrame:
    """Generalized ESD de Rosner (1983): prueba formal de hasta r atipicos bajo normalidad.
    Con r = 1 es la prueba de Grubbs. Aplicar a la escala donde los datos son ~normales
    (log para ventas). Controla el error tipo I global en `alpha` sin sufrir enmascaramiento.

    O(n log n): con los datos ordenados, el punto mas lejano de la media siempre esta en una
    de las dos puntas; media y varianza se actualizan al quitarlo. Mismo resultado que la
    version iterativa y corre en segundos con decenas de millones de filas."""
    s = _serie(x)
    v = s.to_numpy()
    idx = np.flatnonzero(np.isfinite(v))
    n = idx.size
    r = max_atipicos if max_atipicos is not None else max(1, min(n // 10, 500))
    r = min(r, n - 3)
    orden = np.argsort(v[idx], kind="stable")
    xs = v[idx][orden] - np.median(v[idx])  # centrar: sumas estables
    s1, s2 = float(xs.sum()), float((xs * xs).sum())
    lo, hi = 0, n - 1
    R, quitados = np.empty(r), np.empty(r, np.int64)
    k = 0
    for i in range(1, r + 1):
        m = hi - lo + 1
        mu = s1 / m
        var = (s2 - s1 * s1 / m) / (m - 1)
        if var <= 0:
            break
        d_lo, d_hi = mu - xs[lo], xs[hi] - mu
        if d_hi >= d_lo:
            pos, dev = hi, d_hi
            hi -= 1
        else:
            pos, dev = lo, d_lo
            lo += 1
        R[k], quitados[k] = dev / math.sqrt(var), orden[pos]
        s1 -= xs[pos]
        s2 -= xs[pos] * xs[pos]
        k += 1
    R, quitados = R[:k], quitados[:k]
    m = n - np.arange(1, k + 1) + 1
    t = stats.t.ppf(1 - alpha / (2 * m), m - 2)
    lam = (m - 1) * t / np.sqrt((m - 2 + t**2) * m)
    sig = np.flatnonzero(R > lam)
    n_atip = int(sig[-1] + 1) if sig.size else 0
    flag = np.zeros(v.size, bool)
    flag[idx[quitados[:n_atip]]] = True
    estad = np.full(v.size, np.nan)
    estad[idx[quitados]] = R
    return (pd.DataFrame({"atipico": flag, "R_i": estad}, index=s.index)
            .assign(n_atipicos_gesd=n_atip, r_maximo=r))


def _gpd_censurada(exc: np.ndarray, c: float) -> tuple[float, float]:
    """MLE de la Pareto generalizada con los excesos > c CENSURADOS: de ellos solo se usa que
    superan c, no su valor. Asi los atipicos que se buscan no inflan el indice de cola xi
    (enmascaramiento en la cola). c = inf da el MLE clasico."""
    from scipy.optimize import minimize
    obs, n_c = exc[exc <= c], int((exc > c).sum())
    xi0, _, b0 = stats.genpareto.fit(obs, floc=0)

    def nll(th):
        xi, lb = th
        b = math.exp(lb)
        ll = stats.genpareto.logpdf(obs, xi, 0, b).sum()
        if n_c:
            ll += n_c * stats.genpareto.logsf(c, xi, 0, b)
        return -ll if np.isfinite(ll) else 1e300

    r = minimize(nll, [xi0, math.log(b0)], method="Nelder-Mead")
    return float(r.x[0]), float(math.exp(r.x[1]))


def cola_gpd(x, cuantil_umbral: float = 0.90, alpha: float = 0.05,
             cuantil_censura: float | None = 0.99) -> pd.DataFrame:
    """Teoria de valores extremos (picos sobre umbral): ajusta una Pareto generalizada a los
    excesos sobre u = cuantil `cuantil_umbral` y da la probabilidad de cola P(X >= x) de cada punto.

    El ajuste censura lo que pasa del cuantil `cuantil_censura` de TODOS los datos (supuesto:
    los errores son < 1% de las filas; ver `_gpd_censurada`). Con None es el MLE clasico, que
    los propios atipicos contaminan: 15 errores en 3,000 ventas suben xi de ~0.2 a ~1.2 y la
    prueba ya no marca nada.
    p_ajustado = min(1, n * P(X >= x)): numero esperado de puntos al menos tan extremos en una
    muestra de tamano n (Bonferroni). Un punto es atipico si p_ajustado < alpha: ni siquiera la
    cola pesada ajustada lo explica. Es la forma correcta de separar 'cola pesada' de 'error'
    y es el criterio MAS conservador del modulo: marca poco, pero lo que marca casi seguro no
    es de la misma poblacion. No usarla sola para buscar atipicos (recall bajo).
    """
    s = _serie(x)
    v = s.to_numpy()
    fin = v[np.isfinite(v)]
    n = fin.size
    u = float(np.quantile(fin, cuantil_umbral))
    exc = fin[fin > u] - u
    p = np.full(v.size, np.nan)
    if exc.size < 30:
        return pd.DataFrame({"atipico": False, "p_cola": p, "p_ajustado": p}, index=s.index)
    c = float(np.quantile(fin, cuantil_censura)) - u if cuantil_censura else np.inf
    xi, beta = _gpd_censurada(exc, c)
    zeta = exc.size / n
    arriba = np.isfinite(v) & (v > u)
    p[arriba] = zeta * stats.genpareto.sf(v[arriba] - u, xi, 0, beta)
    padj = np.minimum(1.0, n * p)
    return pd.DataFrame({"atipico": np.nan_to_num(padj, nan=1.0) < alpha, "p_cola": p,
                         "p_ajustado": padj}, index=s.index).assign(gpd_xi=xi, gpd_umbral=u)


def univariado(x, *, escala: str = "auto", ceros: str = "aparte", negativos: str = "aparte",
               alpha: float = 0.05,
               metodos: Sequence[str] = ("z_robusto", "boxplot_ajustado", "iqr_3", "gesd", "cola_gpd"),
               ) -> pd.DataFrame:
    """Corre los metodos univariados y devuelve una fila por punto con un flag por metodo,
    `votos` y `atipico` (mayoria de los metodos que corrieron).

    escala = "auto": log si todos los valores > 0 (sin contar ceros apartados) y la asimetria > 1;
             "log" o "original" para forzar. z_robusto, gesd y cola_gpd van en la escala elegida;
             boxplot_ajustado e iqr_3 siempre en la original (el ajustado ya modela la asimetria).
             cola_gpd va en log porque una log-normal vista desde el p90 parece una Pareto con
             xi ~ 0.5 y "explica" casi cualquier valor alto en escala original.
    ceros = "aparte": los ceros no entran (distribucion inflada en cero: el cero es otra poblacion
            y tirar de la mediana hacia 0 marca como atipico a medio mundo); "incluir" los usa.
    negativos = "aparte": en una venta los negativos son devoluciones o errores (atipicos
            matematicos, ver `reglas`), no la cola izquierda; si se quedan, un solo -4 impide la
            escala log. "incluir" para variables con signo (margen, crecimiento).
    """
    s = _serie(x)
    base = s.copy()
    excluido = base.isna()
    if ceros == "aparte":
        excluido |= base == 0
    if negativos == "aparte":
        excluido |= base < 0
    w = base[~excluido]
    asim = float(stats.skew(w, bias=False)) if w.size > 2 else 0.0
    usar_log = escala == "log" or (escala == "auto" and (w > 0).all() and asim > 1)
    wt = np.log(w) if usar_log else w

    out = pd.DataFrame(index=s.index)
    out["valor"] = s
    out["excluido"] = np.select([s.isna(), excluido & (s < 0), excluido & (s == 0)],
                                ["nulo", "negativo (regla)", "cero (aparte)"], "")
    corrieron = []

    def poner(nombre, tabla, col="atipico"):
        out[nombre] = False
        out.loc[tabla.index, nombre] = tabla[col].astype(bool)
        corrieron.append(nombre)

    if "z_robusto" in metodos:
        t = z_robusto(wt)
        out["z_robusto_valor"] = np.nan
        out.loc[t.index, "z_robusto_valor"] = t["z_robusto"]
        poner("z_robusto", t)
    if "boxplot_ajustado" in metodos:
        poner("boxplot_ajustado", boxplot_ajustado(w))
    if "iqr_3" in metodos:
        poner("iqr_3", iqr_tukey(w, k=3.0))
    if "gesd" in metodos and w.size >= 10:
        poner("gesd", gesd(wt, alpha=alpha))
    if "cola_gpd" in metodos and w.size >= 200:
        t = cola_gpd(wt, alpha=alpha)
        out["p_cola_ajustado"] = np.nan
        out.loc[t.index, "p_cola_ajustado"] = t["p_ajustado"]
        poner("cola_gpd", t)

    out["votos"] = out[corrieron].sum(axis=1)
    out["atipico"] = out["votos"] >= math.ceil(len(corrieron) / 2)
    out.loc[out["excluido"] != "", corrieron] = False
    lado = np.sign(s - w.median())
    out["lado"] = np.where(out["atipico"], np.where(lado > 0, "alto", "bajo"), "")
    out.attrs.update(escala="log" if usar_log else "original", asimetria=asim, metodos=corrieron,
                     n_analizados=int(w.size), n_excluidos=int(excluido.sum()))
    return out


# ════════════════════════════════════════════════════════════════════════════
#  3. Atipicos contextuales: dentro del grupo y contra un modelo
# ════════════════════════════════════════════════════════════════════════════

def por_grupo(df, valor: str, grupo: str | Sequence[str], *, corte: float = CORTE_Z_ROBUSTO,
              log: bool = False, n_min: int = 20, base_si_chico: bool = True,
              escala_min: float = 0.0) -> pd.DataFrame:
    """z robusto DENTRO de cada grupo (tienda, SKU, subcanal, municipio...).
    Un abarrote que vende como supermercado es atipico en su subcanal aunque no en la base.
    Grupos con menos de `n_min` valores usan la mediana y MAD de toda la base (y lo marcan);
    con `base_si_chico=False` quedan sin z (p. ej. la serie de un PDV x producto: la base no
    es su referencia). Vectorizado: escala con millones de filas y grupos.
    Escala = MAD_n del grupo; si es 0 (mitad de valores iguales), 1.2533 x desviacion media.
    `escala_min` = piso de la escala (en la escala del analisis): un precio de lista tiene
    MAD ~ 0 y cualquier descuento saldria atipico. Con log=True, escala_min = log(1.2)/3.5
    exige desviarse mas de ~20% de la mediana del grupo para marcar."""
    df = _df(df)
    grupo = [grupo] if isinstance(grupo, str) else list(grupo)
    v = df[valor].astype("float64")
    v = np.log(v.where(v > 0)) if log else v
    claves = [df[g] for g in grupo]
    gb = v.groupby(claves, observed=True, sort=False)
    tam = gb.transform("count")
    med = gb.transform("median")
    dev = (v - med).abs().groupby(claves, observed=True, sort=False)
    esc = dev.transform("median") * K_MAD
    esc = esc.where(esc > 0, dev.transform("mean") * 1.2533)
    chico = tam < n_min
    if base_si_chico:
        med = med.where(~chico, v.median())
        esc = esc.where(~chico, _escala_robusta(v.to_numpy()))
    else:
        med = med.where(~chico)
    if escala_min:
        esc = esc.clip(lower=escala_min)
    z = (v - med) / esc.where(esc > 0)
    return pd.DataFrame({"z_en_grupo": z, "atipico": z.abs() > corte, "n_grupo": tam,
                         "mediana_grupo": np.exp(med) if log else med,
                         "referencia": np.where(chico, "base (grupo chico)" if base_si_chico
                                                else "sin referencia (grupo chico)", "grupo")},
                        index=df.index)


def residuos_regresion(y, X, *, alpha: float = 0.05) -> pd.DataFrame:
    """OLS y diagnostico de influencia: residuo estudentizado externo, apalancamiento y Cook.
    - atipico en y:  |t_i| > t_{1 - alpha/(2n), n-p-1}   (Bonferroni)
    - apalancamiento: h_ii > 2p/n   (x raro)
    - influyente:    Cook D_i > 4/n (cambia los coeficientes si se quita)
    Ejemplo retail: venta ~ hogares + NSE; el atipico es el PDV que vende muy distinto de lo
    que su entorno predice, no el que vende mucho."""
    y = np.asarray(y, dtype="float64")
    X = np.column_stack([np.ones(len(y)), np.asarray(X, dtype="float64").reshape(len(y), -1)])
    ok = np.isfinite(y) & np.isfinite(X).all(1)
    yo, Xo = y[ok], X[ok]
    n, p = Xo.shape
    XtX_inv = np.linalg.pinv(Xo.T @ Xo)
    beta = XtX_inv @ Xo.T @ yo
    e = yo - Xo @ beta
    h = np.einsum("ij,jk,ik->i", Xo, XtX_inv, Xo)
    sse = e @ e
    s2_i = (sse - e**2 / (1 - h)) / (n - p - 1)
    t = e / np.sqrt(s2_i * (1 - h))
    cook = e**2 / (p * sse / (n - p)) * h / (1 - h) ** 2
    corte_t = stats.t.ppf(1 - alpha / (2 * n), n - p - 1)
    res = pd.DataFrame(index=range(len(y)), columns=["residuo", "t_estudentizado", "apalancamiento",
                                                      "cook"], dtype="float64")
    res.loc[ok, :] = np.column_stack([e, t, h, cook])
    res["atipico_y"] = res["t_estudentizado"].abs() > corte_t
    res["alto_apalancamiento"] = res["apalancamiento"] > 2 * p / n
    res["influyente"] = res["cook"] > 4 / n
    res.attrs.update(beta=beta, corte_t=corte_t)
    return res


# ════════════════════════════════════════════════════════════════════════════
#  4. Atipicos multivariados
# ════════════════════════════════════════════════════════════════════════════

def _matriz(df, cols, log1p):
    df = _df(df)
    M = df[list(cols)].astype("float64")
    ok = M.notna().all(axis=1)
    A = M[ok].to_numpy()
    if log1p:
        A = np.log1p(np.clip(A, 0, None))
    return A, ok


def mahalanobis_robusto(df, cols: Sequence[str], *, alpha: float = 0.975, log1p: bool = False,
                        robusto: bool = True, n_ajuste: int | None = 20_000) -> pd.DataFrame:
    """D2 = (x - mu)' S^-1 (x - mu) con mu, S del MCD (Rousseeuw): resiste hasta ~50% de
    contaminacion. Corte chi2_p(alpha). Detecta combinaciones raras que ninguna variable
    sola marca (venta alta con CP bajo y pocos hogares). `log1p=True` para montos.
    El MCD se ajusta sobre `n_ajuste` filas al azar (FAST-MCD es superlineal) y la distancia
    se calcula para todas; con 20 mil filas la covarianza robusta ya es estable.
    Usar variables continuas: una columna casi constante (meses activos = 24 en casi todos)
    deja la covarianza del MCD degenerada y marca como atipico a cualquiera que se aparte."""
    df = _df(df)
    A, ok = _matriz(df, cols, log1p)
    if A.shape[0] <= 2 * A.shape[1]:
        raise ValueError("muy pocas filas para estimar la covarianza")
    if robusto and _TIENE_SKLEARN:
        B = A
        if n_ajuste and A.shape[0] > n_ajuste:
            B = A[np.random.default_rng(SEMILLA).choice(A.shape[0], n_ajuste, replace=False)]
        est = _MinCovDet(random_state=SEMILLA).fit(B)
        mu, S = est.location_, est.covariance_
    else:
        mu, S = A.mean(0), np.cov(A, rowvar=False)
    d = A - mu
    d2 = np.einsum("ij,jk,ik->i", d, np.linalg.pinv(S), d)
    corte = float(stats.chi2.ppf(alpha, A.shape[1]))
    out = pd.DataFrame({"d2": np.nan, "atipico": False}, index=df.index)
    out.loc[ok, "d2"] = d2
    out.loc[ok, "atipico"] = d2 > corte
    # que variable empuja: contribucion de cada columna (z robusto de la columna)
    zc = d / np.sqrt(np.diag(S))
    out["variable_dominante"] = ""
    out.loc[ok, "variable_dominante"] = np.array(cols)[np.abs(zc).argmax(1)]
    out.attrs.update(corte_chi2=corte, robusto=robusto and _TIENE_SKLEARN)
    return out


def isolation_forest(df, cols: Sequence[str], *, contaminacion="auto", log1p: bool = False) -> pd.DataFrame:
    """Isolation Forest (Liu et al. 2008), sin supuesto de distribucion. `contaminacion` debe
    salir del negocio (p. ej. % esperado de mayoristas), no ajustarse para 'que de bien'."""
    if not _TIENE_SKLEARN:
        raise ImportError("isolation_forest necesita scikit-learn")
    df = _df(df)
    A, ok = _matriz(df, cols, log1p)
    A = (A - np.median(A, 0)) / np.array([_escala_robusta(c) for c in A.T])
    m = _IsolationForest(contamination=contaminacion, random_state=SEMILLA, n_estimators=300, n_jobs=-1).fit(A)
    out = pd.DataFrame({"puntaje_if": np.nan, "atipico": False}, index=df.index)
    out.loc[ok, "puntaje_if"] = -m.score_samples(A)  # mayor = mas aislado
    out.loc[ok, "atipico"] = m.predict(A) == -1
    return out


def lof(df, cols: Sequence[str], *, k: int = 20, contaminacion="auto", log1p: bool = False) -> pd.DataFrame:
    """Local Outlier Factor: densidad del punto vs la de sus k vecinos. Encuentra atipicos
    locales (un punto raro dentro de su cumulo) que Mahalanobis global no ve."""
    if not _TIENE_SKLEARN:
        raise ImportError("lof necesita scikit-learn")
    df = _df(df)
    A, ok = _matriz(df, cols, log1p)
    A = (A - np.median(A, 0)) / np.array([_escala_robusta(c) for c in A.T])
    m = _LOF(n_neighbors=k, contamination=contaminacion, n_jobs=-1)  # mismos vecinos, en paralelo
    pred = m.fit_predict(A)
    out = pd.DataFrame({"lof": np.nan, "atipico": False}, index=df.index)
    out.loc[ok, "lof"] = -m.negative_outlier_factor_
    out.loc[ok, "atipico"] = pred == -1
    return out


# ════════════════════════════════════════════════════════════════════════════
#  5. Atipicos temporales
# ════════════════════════════════════════════════════════════════════════════

def hampel(x, ventana: int = 7, t: float = 3.5, escala: str = "agrupada") -> pd.DataFrame:
    """Filtro de Hampel: |x_t - mediana movil| > t * escala (ventana centrada 2k+1).
    Marca picos y caidas puntuales sin confundirlos con tendencia o estacionalidad lenta.

    escala = "local": MAD_n de la ventana (Hampel clasico). Con 15 puntos la MAD es muy
             ruidosa y da ~3-5% de falsos con t = 3.
    escala = "agrupada" (defecto): mediana de las MAD locales de toda la serie; estable si el
             ruido es homogeneo. Si la varianza cambia con el nivel, aplicar a log(x).
    t = 3.5 (no el 3 clasico): la mediana movil incluye al propio punto y encoge el residuo,
    asi que con t = 3 salen ~1-2% de falsos en ruido normal.
    Para estacionalidad semanal fuerte, aplicarlo al residuo de STL o por dia de la semana."""
    s = _serie(x)
    w = 2 * ventana + 1
    med = s.rolling(w, center=True, min_periods=ventana + 1).median()
    mad = (s - med).abs().rolling(w, center=True, min_periods=ventana + 1).median() * K_MAD
    if escala == "agrupada":
        mad = pd.Series(float(mad[mad > 0].median()), index=s.index)
    mad = mad.where(mad > 0, _escala_robusta(s.to_numpy()))
    z = (s - med) / mad
    return pd.DataFrame({"mediana_movil": med, "z_hampel": z, "atipico": z.abs() > t,
                         "valor_sugerido": s.where(z.abs() <= t, med)}, index=s.index)


# ════════════════════════════════════════════════════════════════════════════
#  6. Atipicos espaciales
# ════════════════════════════════════════════════════════════════════════════

def espacial(lat, lon, valor, *, k: int = 30, radio_m: float | None = None, log: bool = True,
             corte: float = CORTE_Z_ROBUSTO, n_min: int = 5) -> pd.DataFrame:
    """Atipico espacial: el valor del punto contra la mediana y MAD de sus vecinos (k mas
    cercanos o los que esten a <= radio_m), distancia haversine. Un PDV que vende 10x lo de
    su cuadra es atipico aunque en la ciudad sea normal. Sin vecinos suficientes -> NaN.
    k = 30 por defecto: con 10-15 vecinos la MAD local es tan ruidosa que marca ~2-3% de falsos."""
    if not _TIENE_SKLEARN:
        raise ImportError("espacial necesita scikit-learn (BallTree)")
    lat, lon, v = (np.asarray(a, dtype="float64") for a in (lat, lon, valor))
    vt = np.log(np.where(v > 0, v, np.nan)) if log else v
    ok = np.isfinite(lat) & np.isfinite(lon) & np.isfinite(vt)
    X = np.radians(np.column_stack([lat[ok], lon[ok]]))
    arbol = _BallTree(X, metric="haversine")
    if radio_m is None:
        _, vec = arbol.query(X, k=min(k + 1, ok.sum()))
        vec = [fila[1:] for fila in vec]
    else:
        vec = arbol.query_radius(X, r=radio_m / 6_371_008.8)
        vec = [fila[fila != i] for i, fila in enumerate(vec)]
    vo = vt[ok]
    esc_global = _escala_robusta(vo)
    med = np.full(ok.sum(), np.nan)
    esc = np.full(ok.sum(), np.nan)
    nv = np.zeros(ok.sum(), int)
    for i, fila in enumerate(vec):
        nv[i] = len(fila)
        if len(fila) >= n_min:
            vv = vo[fila]
            med[i] = np.median(vv)
            e = mad_n(vv)
            esc[i] = e if e > 0 else esc_global
    z = (vo - med) / esc
    out = pd.DataFrame({"z_espacial": np.nan, "mediana_vecinos": np.nan, "n_vecinos": 0,
                        "atipico": False}, index=range(len(v)))
    out.loc[ok, "z_espacial"] = z
    out.loc[ok, "mediana_vecinos"] = np.exp(med) if log else med
    out.loc[ok, "n_vecinos"] = nv
    out.loc[ok, "atipico"] = np.abs(np.nan_to_num(z)) > corte
    return out


# ════════════════════════════════════════════════════════════════════════════
#  7. Decision y reporte
# ════════════════════════════════════════════════════════════════════════════

def consenso(flags: pd.DataFrame, *, familias: dict[str, Sequence[str]] | None = None,
             fuerte: float = 0.5) -> pd.DataFrame:
    """Combina flags booleanos de varios metodos: `votos`, `fraccion` y `clase`:
    'atipico fuerte' (>= `fuerte` de las familias), 'revisar' (al menos un metodo) o 'normal'.

    Con `familias` ({familia: [metodos]}) se vota POR FAMILIA: una familia marca si mas de la
    mitad de sus metodos marca. Asi IQR, Tukey y boxplot ajustado (casi la misma regla) no
    cuentan tres veces. Un solo metodo es una hipotesis; el acuerdo entre familias distintas
    (univariado, contextual, espacial, multivariado) es evidencia."""
    f = flags.fillna(False).astype(bool)
    if familias:
        fam = pd.DataFrame({nombre: f[list(cols)].mean(axis=1) > 0.5 if len(cols) > 1 else f[cols[0]]
                            for nombre, cols in familias.items()}, index=f.index)
    else:
        fam = f
    votos = fam.sum(axis=1)
    frac = votos / fam.shape[1]
    clase = np.where(frac >= fuerte, "atipico fuerte", np.where(f.any(axis=1), "revisar", "normal"))
    metodos = np.array(f.columns)
    cuales = [" · ".join(metodos[fila]) for fila in f.to_numpy()]
    nf = np.array(fam.columns)
    out = pd.DataFrame({"votos": f.sum(axis=1), "familias": votos, "fraccion": frac, "clase": clase,
                        "metodos": cuales,
                        "familias_que_marcan": [" · ".join(nf[fila]) for fila in fam.to_numpy()]},
                       index=flags.index)
    return out


def impacto(x, atipico) -> pd.DataFrame:
    """Que cambia en los agregados si se quitan o se winsorizan los atipicos.
    Si nada material cambia, no hace falta tratarlos: basta reportarlos."""
    s = _serie(x)
    a = pd.Series(np.asarray(atipico, bool), index=s.index)
    s_ok = s[~a]
    lo, hi = s_ok.min(), s_ok.max()
    wins = s.clip(lo, hi)
    filas = {
        "n": (s.notna().sum(), s_ok.notna().sum(), wins.notna().sum()),
        "total": (s.sum(), s_ok.sum(), wins.sum()),
        "media": (s.mean(), s_ok.mean(), wins.mean()),
        "mediana": (s.median(), s_ok.median(), wins.median()),
        "desv. estandar": (s.std(), s_ok.std(), wins.std()),
        "CV": (s.std() / s.mean(), s_ok.std() / s_ok.mean(), wins.std() / wins.mean()),
    }
    out = pd.DataFrame(filas, index=["todos", "sin atipicos", "winsorizado"]).T
    out["cambio % sin atipicos"] = 100 * (out["sin atipicos"] / out["todos"] - 1)
    out.attrs["pct_del_total_en_atipicos"] = float(100 * s[a].sum() / s.sum()) if s.sum() else np.nan
    return out


def sensibilidad(x, metodo=z_robusto, parametro: str = "corte",
                 valores: Sequence[float] = (2.5, 3.0, 3.5, 4.0, 5.0)) -> pd.DataFrame:
    """Cuantos atipicos marca el metodo para cada umbral. Si el conteo salta mucho entre
    umbrales vecinos no hay separacion natural: reportar el rango, no un numero."""
    filas = []
    for val in valores:
        r = metodo(x, **{parametro: val})
        filas.append({parametro: val, "n_atipicos": int(r["atipico"].sum()),
                      "pct": 100 * float(r["atipico"].mean())})
    return pd.DataFrame(filas)


def metodos_tabla() -> pd.DataFrame:
    """Hoja 'Metodos' del reporte: que hace cada metodo, su umbral y cuando usarlo."""
    return pd.DataFrame([
        ("reglas", "Matematico", "Viola una regla o identidad", "sin umbral", "Siempre primero"),
        ("z_robusto", "Univariado", "(x - mediana) / MAD_n", "|z| > 3.5", "Escala ~simetrica (log de ventas)"),
        ("boxplot_ajustado", "Univariado", "Vallas de Tukey corregidas por medcouple", "k = 1.5", "Ventas en escala original"),
        ("iqr_3", "Univariado", "Vallas de Tukey lejanas", "k = 3", "Referencia simple y conocida"),
        ("gesd", "Univariado", "Generalized ESD de Rosner (Grubbs para r = 1)", "alpha = 0.05", "Prueba formal; datos ~normales"),
        ("cola_gpd", "Univariado", "Pareto generalizada sobre el p90, censurada en el p99 (EVT)", "n·P(X>=x) < 0.05", "Colas pesadas: separa cola de error"),
        ("por_grupo", "Contextual", "z robusto dentro del grupo", "|z| > 3.5", "Subcanal, tienda, SKU, municipio"),
        ("residuos_regresion", "Contextual", "Residuo estudentizado, h_ii, Cook", "Bonferroni · 2p/n · 4/n", "Venta vs lo que predice su entorno"),
        ("mahalanobis_robusto", "Multivariado", "D2 con MCD", "chi2_p(0.975)", "Combinaciones raras de 2-10 variables"),
        ("isolation_forest", "Multivariado", "Profundidad de aislamiento", "contaminacion del negocio", "Sin supuesto de forma"),
        ("lof", "Multivariado", "Densidad local vs vecinos", "contaminacion", "Atipicos dentro de un cumulo"),
        ("hampel", "Temporal", "Mediana movil y MAD agrupada", "|z| > 3.5", "Picos y caidas en series"),
        ("espacial", "Espacial", "Valor vs mediana de k vecinos", "|z| > 3.5", "PDV vs su vecindario"),
    ], columns=["metodo", "familia", "que mide", "umbral", "cuando"])


# ════════════════════════════════════════════════════════════════════════════
#  Linea de comandos: reporte en Excel
# ════════════════════════════════════════════════════════════════════════════

def reporte(df, col: str, *, grupo: str | None = None, lat: str | None = None, lon: str | None = None,
            multi: Sequence[str] | None = None, id_col: str | None = None,
            contaminacion: float = 0.01, alpha_multi: float = 0.999) -> dict[str, pd.DataFrame]:
    """Corre todo lo que aplica a los datos dados y devuelve las hojas del reporte.
    Las filas excluidas del univariado (nulos, ceros, negativos) no entran a ningun metodo:
    son otra poblacion y en el multivariado forman un cumulo propio que se marca entero.
    `contaminacion` = fraccion esperada para Isolation Forest (del negocio; 'auto' marca ~10%).
    `alpha_multi` = cuantil chi2 de Mahalanobis: 0.999 y no 0.975, porque con miles de filas
    0.975 marca 2.5% de puntos sanos por construccion."""
    df = _df(df).reset_index(drop=True)
    uni = univariado(df[col])
    flags = uni[uni.attrs["metodos"]].copy()
    detalle = pd.DataFrame(index=df.index)
    if id_col:
        detalle[id_col] = df[id_col]
    detalle[col] = df[col]
    detalle = detalle.join(uni.drop(columns=["valor"]))
    if grupo:
        g = por_grupo(df, col, grupo, log=uni.attrs["escala"] == "log")
        g.loc[uni["excluido"] != "", "atipico"] = False
        flags["por_grupo"] = g["atipico"]
        detalle[grupo] = df[grupo]
        detalle["z_en_grupo"] = g["z_en_grupo"]
        detalle["por_grupo"] = g["atipico"]
    dentro = uni["excluido"] == ""
    # con grupo, el espacial y el multivariado comparan dentro del grupo (grupos chicos: toda la base)
    bloques = [dentro]
    if grupo:
        tam = df.groupby(grupo)[col].transform("size")
        bloques = [dentro & (df[grupo] == g) for g in df.loc[tam >= 50, grupo].unique()]
        bloques.append(dentro & (tam < 50))
    familias = {"univariado": [], "contextual": [], "espacial": [], "multivariado": []}
    familias["univariado"] = list(uni.attrs["metodos"])
    if grupo:
        familias["contextual"] = ["por_grupo"]
    if lat and lon and _TIENE_SKLEARN:
        flags["espacial"] = False
        detalle["z_espacial"] = np.nan
        detalle["mediana_vecinos"] = np.nan
        for b in bloques:
            if b.sum() < 50:
                continue
            e = espacial(df.loc[b, lat], df.loc[b, lon], df.loc[b, col],
                         log=uni.attrs["escala"] == "log")
            e.index = df.index[b]
            flags.loc[e.index, "espacial"] = e["atipico"].astype(bool)
            detalle.loc[e.index, "z_espacial"] = e["z_espacial"]
            detalle.loc[e.index, "mediana_vecinos"] = e["mediana_vecinos"]
        detalle["espacial"] = flags["espacial"]
        familias["espacial"] = ["espacial"]
    if multi and _TIENE_SKLEARN:
        for nombre in ("mahalanobis_robusto", "isolation_forest"):
            flags[nombre] = False
        detalle["d2"] = np.nan
        detalle["variable_dominante"] = ""
        for b in bloques:
            if b.sum() <= max(50, 4 * len(multi)):
                continue
            sub = df.loc[b, list(multi)]
            m = mahalanobis_robusto(sub, multi, log1p=True, alpha=alpha_multi)
            f = isolation_forest(sub, multi, log1p=True, contaminacion=contaminacion)
            flags.loc[m.index, "mahalanobis_robusto"] = m["atipico"].astype(bool)
            flags.loc[f.index, "isolation_forest"] = f["atipico"].astype(bool)
            detalle.loc[m.index, "d2"] = m["d2"]
            detalle.loc[m.index, "variable_dominante"] = m["variable_dominante"]
        detalle["mahalanobis_robusto"] = flags["mahalanobis_robusto"]
        detalle["isolation_forest"] = flags["isolation_forest"]
        familias["multivariado"] = ["mahalanobis_robusto", "isolation_forest"]
    familias = {k: v for k, v in familias.items() if v}
    c = consenso(flags, familias=familias)
    neg = uni["excluido"] == "negativo (regla)"
    c.loc[neg, "clase"] = "atipico matematico (negativo)"
    detalle = detalle.drop(columns=["votos", "atipico"]).join(c)
    detalle = detalle.sort_values(["familias", "votos", col], ascending=[False, False, False])

    a = c["clase"] == "atipico fuerte"
    imp = impacto(df[col], a)
    resumen = pd.DataFrame([
        ("variable", col),
        ("filas", len(df)),
        ("analizadas (sin nulos ni ceros)", uni.attrs["n_analizados"]),
        ("excluidas (nulos, ceros y negativos: otra poblacion)", uni.attrs["n_excluidos"]),
        ("negativos (atipico matematico)", int((uni["excluido"] == "negativo (regla)").sum())),
        ("asimetria", round(uni.attrs["asimetria"], 2)),
        ("escala de z robusto y GESD", uni.attrs["escala"]),
        ("metodos", " · ".join(flags.columns)),
        ("familias", " · ".join(f"{k} ({', '.join(v)})" for k, v in familias.items())),
        ("atipico fuerte (>= mitad de las familias)", int(a.sum())),
        ("revisar (al menos un metodo)", int((c["clase"] == "revisar").sum())),
        ("% del total en atipicos fuertes", round(imp.attrs["pct_del_total_en_atipicos"], 2)),
        ("por metodo", " · ".join(f"{k} {int(v)}" for k, v in flags.sum().items())),
    ], columns=["concepto", "valor"])
    w = df[col].where(uni["excluido"] == "")
    sens = sensibilidad(np.log(w) if uni.attrs["escala"] == "log" else w)
    return {"Resumen": resumen, "Por punto": detalle, "Impacto": imp.reset_index(names="estadistico"),
            "Sensibilidad z robusto": sens, "Metodos": metodos_tabla()}


def _cli(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Reporte de atipicos de una columna (Excel).")
    ap.add_argument("archivo", help="CSV, XLSX o Parquet")
    ap.add_argument("--col", required=True, help="columna numerica a revisar")
    ap.add_argument("--id", dest="id_col", help="columna identificadora (p. ej. pos_id)")
    ap.add_argument("--grupo", help="columna de grupo para el atipico contextual")
    ap.add_argument("--lat"), ap.add_argument("--lon")
    ap.add_argument("--multi", help="columnas para Mahalanobis e Isolation Forest, separadas por coma")
    ap.add_argument("--contaminacion", type=float, default=0.01,
                    help="fraccion esperada de atipicos para Isolation Forest (del negocio)")
    ap.add_argument("--salida", default=None, help="xlsx de salida (por defecto <archivo>_atipicos.xlsx)")
    a = ap.parse_args(argv)
    ruta = a.archivo
    if ruta.endswith(".parquet"):
        df = pd.read_parquet(ruta)
    elif ruta.endswith((".xlsx", ".xls")):
        df = pd.read_excel(ruta)
    else:
        try:
            df = pd.read_csv(ruta, encoding="utf-8-sig", low_memory=False)
        except UnicodeDecodeError:
            df = pd.read_csv(ruta, encoding="latin-1", low_memory=False)
    hojas = reporte(df, a.col, grupo=a.grupo, lat=a.lat, lon=a.lon, id_col=a.id_col,
                    multi=a.multi.split(",") if a.multi else None, contaminacion=a.contaminacion)
    salida = a.salida or ruta.rsplit(".", 1)[0] + f"_atipicos_{a.col}.xlsx"
    with pd.ExcelWriter(salida) as xw:
        for nombre, h in hojas.items():
            h.to_excel(xw, sheet_name=nombre[:31], index=False)
    print(hojas["Resumen"].to_string(index=False))
    print(f"\nReporte: {salida}")
    return 0


# ════════════════════════════════════════════════════════════════════════════
#  Self-test con atipicos plantados
# ════════════════════════════════════════════════════════════════════════════

def _self_test() -> int:
    print("retail_outliers self-test")
    print(f"  pandas {pd.__version__} | numpy {np.__version__} | sklearn: {_TIENE_SKLEARN}")
    rng = np.random.default_rng(7)
    ok = True

    def check(nombre, cond, detalle=""):
        nonlocal ok
        ok = ok and bool(cond)
        print(f"  [{'ok ' if cond else 'FAIL'}] {nombre}{(' — ' + detalle) if detalle else ''}")

    # ventas log-normales (cola pesada legitima) + 15 errores x80 + 20% de ceros
    n = 3000
    v = rng.lognormal(1.0, 0.8, n)
    plant = rng.choice(n, 15, replace=False)
    v[plant] *= 80
    ceros = rng.choice(np.setdiff1d(np.arange(n), plant), 600, replace=False)
    v[ceros] = 0
    es = np.zeros(n, bool); es[plant] = True

    u = univariado(v)
    tp = int((u["atipico"] & es).sum()); fp = int((u["atipico"] & ~es).sum())
    check("univariado (consenso)", tp >= 14 and fp <= 15,
          f"escala {u.attrs['escala']}, {tp}/15 plantados, {fp} falsos de {n - 615} sanos")
    check("ceros aparte", (u.loc[ceros, "excluido"] == "cero (aparte)").all())
    zc = z_clasico(pd.Series(v)[v > 0])
    print(f"  [info] z clasico |z| > 3 marca {int(zc['atipico'].sum())}, "
          f"{int(zc['atipico'][es[v > 0]].sum())} de ellos plantados (enmascaramiento)")
    tk = iqr_tukey(pd.Series(v)[v > 0], k=1.5)
    ba = boxplot_ajustado(pd.Series(v)[v > 0])
    check("boxplot ajustado < Tukey en cola pesada", ba["atipico"].sum() < tk["atipico"].sum(),
          f"Tukey 1.5 {int(tk['atipico'].sum())} vs ajustado {int(ba['atipico'].sum())} (MC {ba['medcouple'].iloc[0]:.2f})")
    g = gesd(np.log(v[v > 0]))
    check("gesd", g["n_atipicos_gesd"].iloc[0] >= 10, f"{g['n_atipicos_gesd'].iloc[0]} atipicos")
    c = cola_gpd(np.log(v[v > 0]))
    c0 = cola_gpd(np.log(v[v > 0]), cuantil_censura=None)
    print(f"  [info] cola_gpd sin censura: xi {c0['gpd_xi'].iloc[0]:.2f}, {int(c0['atipico'].sum())} atipicos "
          "(los errores inflan la cola que deberia delatarlos)")
    vp = np.asarray(c["atipico"]); plant_pos = es[v > 0]
    check("cola_gpd (conservadora: cero falsos)", (vp & ~plant_pos).sum() == 0
          and c["gpd_xi"].iloc[0] < c0["gpd_xi"].iloc[0],
          f"xi censurado {c['gpd_xi'].iloc[0]:.2f}, {int(vp.sum())} marcados, todos plantados")
    mc = medcouple(rng.normal(size=2000))
    check("medcouple ~0 en simetrica", abs(mc) < 0.05, f"{mc:+.3f}")

    # reglas
    df = pd.DataFrame({"cantidad": [1, 2, -1, 3], "precio": [10, 5, 5, 4], "importe": [10, 10, -5, 99]})
    r = reglas(df, {"cantidad negativa": "cantidad < 0",
                    "importe != cantidad x precio": "abs(importe - cantidad*precio) > 0.01"})
    check("reglas", r["n_reglas"].tolist() == [0, 0, 1, 1], r["reglas_violadas"].tolist().__repr__())

    # contextual: grupo B vende 10x; un PDV de A vende como B
    grp = np.repeat(["A", "B"], 500)
    val = np.where(grp == "A", rng.lognormal(0, 0.3, 1000), rng.lognormal(2.3, 0.3, 1000))
    val[3] = np.exp(2.3)
    d = pd.DataFrame({"g": grp, "v": val})
    pg = por_grupo(d, "v", "g", log=True)
    glob = z_robusto(np.log(val))
    check("por_grupo", bool(pg.loc[3, "atipico"]) and not bool(glob.loc[3, "atipico"]),
          f"z en grupo {pg.loc[3, 'z_en_grupo']:.1f} vs global {glob.loc[3, 'z_robusto']:.1f}")

    # regresion: un punto lejos de la recta
    x = rng.normal(size=400); y = 2 * x + rng.normal(scale=0.5, size=400); y[10] += 6
    rr = residuos_regresion(y, x)
    check("residuos_regresion", bool(rr.loc[10, "atipico_y"]) and rr["atipico_y"].sum() <= 3,
          f"t = {rr.loc[10, 't_estudentizado']:.1f}")

    # temporal: seno + 4 picos
    t = np.arange(365); serie = 100 + 20 * np.sin(2 * np.pi * t / 365) + rng.normal(0, 2, 365)
    picos = [50, 120, 200, 300]; serie[picos] += 40
    hp = hampel(serie)
    check("hampel", hp.loc[picos, "atipico"].all() and hp["atipico"].sum() <= 7,
          f"{int(hp['atipico'].sum())} marcados")

    if _TIENE_SKLEARN:
        # multivariado: correlacion fuerte; 10 puntos rompen la relacion sin ser raros por variable
        z = rng.multivariate_normal([0, 0], [[1, 0.95], [0.95, 1]], 1000)
        z[:10] = np.column_stack([rng.uniform(1.5, 2, 10), rng.uniform(-2, -1.5, 10)])
        dm = pd.DataFrame(z, columns=["a", "b"])
        mh = mahalanobis_robusto(dm, ["a", "b"])
        uni_a = z_robusto(dm["a"])["atipico"][:10].sum()
        check("mahalanobis MCD", mh["atipico"][:10].all(),
              f"10/10 vs z robusto por variable {int(uni_a)}/10, {int(mh['atipico'][10:].sum())} falsos")
        fi = isolation_forest(dm, ["a", "b"], contaminacion=0.02)
        print(f"  [info] isolation_forest ve {int(fi['atipico'][:10].sum())}/10 de los que rompen la "
              "correlacion (cortes paralelos a los ejes: para eso, Mahalanobis o LOF)")
        dg = dm.copy(); dg.iloc[:10] = rng.uniform(4, 6, (10, 2)) * rng.choice([-1, 1], (10, 2))
        fg = isolation_forest(dg, ["a", "b"], contaminacion=0.02)
        check("isolation_forest (atipicos globales)", fg["atipico"][:10].all(),
              f"{int(fg['atipico'][:10].sum())}/10")
        lf = lof(dm, ["a", "b"], contaminacion=0.02)
        check("lof", lf["atipico"][:10].sum() >= 7, f"{int(lf['atipico'][:10].sum())}/10")

        # espacial: retícula de ejemplo, un punto vende 20x lo de su cuadra
        la = 20.97 + rng.uniform(0, 0.05, 1500); lo = -89.62 + rng.uniform(0, 0.05, 1500)
        ve = np.exp(1 + 2 * (la - 20.97) / 0.05 + rng.normal(0, 0.3, 1500))  # gradiente espacial
        ve[0] *= 20
        es_ = espacial(la, lo, ve)
        check("espacial", bool(es_.loc[0, "atipico"]) and es_["atipico"].sum() <= 15,
              f"z = {es_.loc[0, 'z_espacial']:.1f}, {int(es_['atipico'].sum())} marcados")

    im = impacto(v, u["atipico"])
    check("impacto", im.loc["media", "cambio % sin atipicos"] < -10,
          f"media {im.loc['media', 'cambio % sin atipicos']:+.0f}% sin atipicos, "
          f"{im.attrs['pct_del_total_en_atipicos']:.0f}% del total en atipicos")

    print("  OK" if ok else "  HAY FALLAS")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(_self_test())
    raise SystemExit(_cli(sys.argv[1:]))
