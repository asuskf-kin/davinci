# Métodos: fórmulas, supuestos y cortes

Cada sección: definición, supuesto, corte y cuándo falla. Las funciones están en
`scripts/retail_outliers.py`.

---

## 0. Estimadores robustos de base

```
mediana        m = med(x)
MAD            = med(|x_i - m|)
MAD_n          = 1.4826 · MAD          (= sigma bajo normalidad; punto de quiebre 50%)
IQR            = Q3 - Q1               (IQR / 1.349 = sigma bajo normalidad; quiebre 25%)
```

- Punto de quiebre: fracción de datos que puede ir a infinito sin que el estimador se vaya.
  Media y sd: 0%. Mediana y MAD: 50%. Por eso todo corte se construye sobre mediana/MAD o MCD.
- Si más de la mitad de los valores son iguales (p. ej. CP redondeado), MAD = 0. El módulo cae a
  IQR / 1.349 y luego a 1.2533 · media(|x − m|).

## 1. Reglas (atípico matemático)

Una regla es una proposición que no puede ser falsa si el dato es correcto. No hay umbral ni
probabilidad. Ejemplos retail: `cantidad ≥ 0` salvo devolución marcada, `|importe − cantidad · precio|
≤ 0.01`, `potencial ≥ venta` si así se define, `lat/lon` dentro del polígono de la zona, `fecha` dentro
de la ventana, clave del grano única.

## 2. Univariados

### z clásico

`z_i = (x_i − x̄) / s`, corte |z| > 3. Supone normalidad **y** que x̄, s no están contaminados.
Con n puntos, max |z| ≤ (n − 1)/√n (Shiffler 1988): con n = 10, ningún punto pasa de 2.85.
Se reporta solo como contraste.

### z robusto (Iglewicz y Hoaglin 1993)

```
M_i = (x_i − m) / MAD_n        atípico si |M_i| > 3.5
```

Supone simetría aproximada. En ventas, aplicarlo a log(x).

### Vallas de Tukey

`[Q1 − k·IQR, Q3 + k·IQR]`, k = 1.5 ("posible") o 3 ("lejano"). Bajo normalidad k = 1.5 marca 0.7%;
con log-normal σ = 0.8, ~6% (self-test: 158 de 2,400). Supone simetría.

### Boxplot ajustado (Hubert y Vandervieren 2008)

Medcouple (Brys, Hubert y Struyf 2004), asimetría robusta en [−1, 1]:

```
MC = med_{x_i ≤ m ≤ x_j} h(x_i, x_j),   h = ((x_j − m) − (m − x_i)) / (x_j − x_i)

MC ≥ 0:  [Q1 − 1.5·e^{−4 MC}·IQR,  Q3 + 1.5·e^{3 MC}·IQR]
MC < 0:  [Q1 − 1.5·e^{−3 MC}·IQR,  Q3 + 1.5·e^{4 MC}·IQR]
```

Marca ~0.7% en distribuciones asimétricas moderadas (MC ≤ 0.6). El módulo calcula MC exacto sobre
una submuestra de 3,000 (error ~1/√3000).

### Generalized ESD (Rosner 1983)

Prueba hasta r atípicos con error tipo I global α, sin enmascaramiento:

```
para i = 1..r:
    R_i = max |x − x̄| / s   sobre los datos que quedan; quitar ese punto
    λ_i = (n − i)·t_{p, n−i−1} / sqrt((n − i − 1 + t²)(n − i + 1)),   p = 1 − α / (2(n − i + 1))
número de atípicos = el mayor i con R_i > λ_i
```

Con r = 1 es la prueba de Grubbs. Supone normalidad de los no atípicos: aplicar en log. Por defecto
r = min(n/10, 500). Con n = 3,000, λ₁ ≈ 4.3: un punto a 4σ no es significativo y está bien que no lo
sea.

### Valores extremos: picos sobre umbral (Pickands-Balkema-de Haan)

Sobre un umbral alto u, los excesos y = x − u siguen aproximadamente una Pareto generalizada:

```
P(X > x | X > u) = (1 + ξ (x − u)/β)^{−1/ξ}        (ξ = 0: exponencial)
P(X ≥ x) = ζ_u · GPD_sf(x − u; ξ, β),   ζ_u = fracción de datos sobre u
p_ajustado = min(1, n · P(X ≥ x))                  atípico si p_ajustado < α
```

- u = p90, ajuste por máxima verosimilitud **censurada en el p99**: de los puntos sobre el p99 solo
  se usa que lo superan. Sin censura, 15 errores en 3,000 ventas suben ξ de ~0 a ~0.25 en log y la
  prueba no marca nada (la cola se estira para explicar a los propios errores).
- Supuesto: los errores son menos del 1% de las filas.
- Aplicar en log: una log-normal vista desde el p90 en escala original parece Pareto con ξ ≈ 0.5 y
  "explica" casi cualquier valor alto.
- Es el criterio más conservador del módulo: precisión alta, recall bajo.

## 3. Contextuales

### z dentro del grupo

`M_i = (x_i − m_g) / MAD_n,g` con mediana y MAD del grupo g. Grupo con < 20 filas: referencia de la base.

### Regresión: residuos, apalancamiento e influencia

```
h_ii   = x_i' (X'X)^{-1} x_i                           alto si > 2p/n
t_i    = e_i / (s_(i) · sqrt(1 − h_ii))                atípico en y si |t_i| > t_{1−α/(2n), n−p−1}
s_(i)² = (SSE − e_i²/(1 − h_ii)) / (n − p − 1)
D_i    = e_i² / (p · MSE) · h_ii / (1 − h_ii)²          influyente si > 4/n
```

Atípico en y ≠ influyente: un punto con residuo grande y h bajo casi no mueve los β. Para un modelo,
importa Cook; para operación, el residuo.

## 4. Multivariados

### Mahalanobis con MCD (Rousseeuw 1984)

```
D²(x) = (x − μ)' Σ^{-1} (x − μ),   D² ~ χ²_p bajo normalidad
```

μ, Σ del Minimum Covariance Determinant: el subconjunto de h ≈ (n + p + 1)/2 puntos con covarianza de
determinante mínimo. Corte χ²_p(0.975) en la literatura; con miles de filas, 0.999. Aplicar sobre
log1p de montos. Pseudo-inversa para columnas colineales.

### Isolation Forest (Liu, Ting y Zhou 2008)

Puntaje = longitud media del camino para aislar el punto en árboles con cortes aleatorios. Los
atípicos se aíslan en pocos cortes. `contaminacion` fija el corte; 'auto' (umbral 0.5 del puntaje)
marca ~10% en datos reales. Escalar antes (el módulo usa mediana/MAD por columna).

### LOF (Breunig et al. 2000)

Razón entre la densidad de alcance local de los k vecinos y la del punto. LOF ≫ 1: el punto está en
una zona menos densa que sus vecinos. Sensible a k (20 es un default razonable).

## 5. Temporal: filtro de Hampel

```
med_t = mediana(x_{t−k..t+k}),   atípico si |x_t − med_t| > t · σ̂
```

σ̂ agrupada = mediana de las MAD_n locales (estable si el ruido es homogéneo); σ̂ local = MAD_n de la
ventana (Hampel clásico, ruidosa con 15 puntos). t = 3.5: con t = 3 salen 1-2% de falsos porque la
mediana incluye al propio punto.

## 6. Espacial

```
z_i = (x_i − med(x_N(i))) / MAD_n(x_N(i)),   N(i) = k vecinos más cercanos (haversine) o radio
```

k = 30: con 10-15 vecinos la MAD local tiene error relativo ~30% y marca 2-3% de falsos. Si la MAD
local es 0 se usa la global.

## 7. Combinación

- **Por familias**: univariado, contextual, espacial, multivariado. Dentro de la familia, mayoría
  estricta; entre familias, "fuerte" si ≥ la mitad. Métodos de la misma familia están correlacionados
  (IQR y boxplot son casi la misma regla) y no son evidencia independiente.
- **Múltiples pruebas**: si hay p-valores (GPD, residuos), Benjamini-Hochberg (`ro._bh`) para listas
  exploratorias; Bonferroni (ya en GESD, GPD y residuos) para afirmar "este punto es un error".
- **Winsorizar** (recortar a la valla) conserva n y reduce la influencia; **recortar** (quitar) sesga
  la media hacia abajo si el extremo era legítimo. Para medias de ventas, preferir la media
  winsorizada o la mediana; reportar ambas.

## Referencias

- Iglewicz, B. y Hoaglin, D. (1993). *How to Detect and Handle Outliers*. ASQC.
- Rosner, B. (1983). Percentage points for a generalized ESD many-outlier procedure. *Technometrics* 25(2).
- Brys, G., Hubert, M. y Struyf, A. (2004). A robust measure of skewness. *JCGS* 13(4).
- Hubert, M. y Vandervieren, E. (2008). An adjusted boxplot for skewed distributions. *CSDA* 52(12).
- Rousseeuw, P. y Van Driessen, K. (1999). A fast algorithm for the MCD estimator. *Technometrics* 41(3).
- Liu, F. T., Ting, K. M. y Zhou, Z.-H. (2008). Isolation Forest. *ICDM*.
- Breunig, M. et al. (2000). LOF: identifying density-based local outliers. *SIGMOD*.
- Coles, S. (2001). *An Introduction to Statistical Modeling of Extreme Values*. Springer.
- Cook, R. D. (1977). Detection of influential observations in linear regression. *Technometrics* 19(1).
- Hampel, F. (1974). The influence curve and its role in robust estimation. *JASA* 69(346).
