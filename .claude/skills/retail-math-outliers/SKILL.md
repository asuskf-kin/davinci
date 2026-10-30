---
name: retail-math-outliers
description: Detecta atípicos (outliers) en datos retail con métodos matemáticos (reglas e identidades que no se pueden violar) y estadísticos robustos (z robusto con MAD, boxplot ajustado por medcouple, GESD de Rosner/Grubbs, valores extremos con Pareto generalizada, z dentro de grupo, residuos estudentizados y Cook, Mahalanobis con MCD, Isolation Forest, LOF, Hampel en series y atípico espacial contra vecinos), los combina por familias y mide su impacto antes de decidir. Usar cuando pidan "outliers", "atípicos", "valores raros", "anomalías", "limpiar ventas", "tiendas que venden raro", "PDV fuera de rango", "picos en la serie", "winsorizar", "quitar extremos", o antes de promediar, correlacionar o modelar ventas, CP, cajas, precios, tickets o pedidos. Complementa a retail-math-eda (paso 3).
---

# Retail Math Outliers

Detectar atípicos en datos retail con rigor: separar lo **imposible** (error matemático) de lo
**improbable** (atípico estadístico) y de lo **legítimamente extremo** (cola pesada, mayorista,
tienda ancla), y decidir con evidencia qué hacer con cada uno.

Basada en `retail-math-eda`: misma disciplina (grano, convención monetaria, BH, robustez) llevada a
fondo en su paso 3 ("Detect multivariate outliers"). Si el EDA no está hecho, hacer antes al menos
su paso 1 (integridad) y 2 (distribución).

## Antes de empezar

Fijar y escribir tres cosas:

1. **Qué es un atípico aquí.** Error de captura (se corrige o se quita), extremo legítimo (se
   conserva y se reporta) o novedad (un régimen nuevo, p. ej. tienda recién abierta). Los métodos
   solo dicen "improbable"; la clase la da el negocio.
2. **Unidad y población.** Una fila = ¿PDV, ticket, línea, PDV × mes? Los ceros y los negativos son
   **otra población** (no venta, devolución): van aparte, no al análisis de la cola.
3. **Para qué.** Para un promedio o una correlación basta winsorizar o usar estadísticos robustos;
   para un modelo importa la influencia (Cook); para operación, la lista de casos a revisar.

Módulo: `scripts/retail_outliers.py` (NumPy + SciPy + pandas; scikit-learn opcional para MCD,
Isolation Forest, LOF y vecinos). Acepta Series/DataFrames de pandas o polars.

```python
import sys; sys.path.insert(0, "<skill_dir>/scripts")
import retail_outliers as ro
```

Verificar el entorno: `python scripts/retail_outliers.py --self-test` (atípicos plantados; todo debe
salir `[ok ]`). Reporte directo en Excel desde la línea de comandos:

```bash
python scripts/retail_outliers.py datos.csv --col venta --id pos_id --grupo subcanal --lat lat --lon lon --multi venta,cp,hogares
```

Deja `<archivo>_atipicos_<col>.xlsx` con hojas Resumen, Por punto (un flag por método, familias que
marcan y clase), Impacto, Sensibilidad y Métodos.

## Flujo

### 1. Atípicos matemáticos (deterministas)

No necesitan estadística: violan una regla. Van primero y no se votan.

- Signos imposibles: cantidad o venta negativa fuera de devoluciones, precio ≤ 0.
- Identidades rotas: `importe ≠ cantidad × precio` (tolerancia de redondeo), `subtotal + IVA ≠ total`,
  suma de categorías ≠ total.
- Dominio: fechas fuera de la ventana, coordenadas fuera de la zona, porcentajes fuera de [0, 1],
  potencial < venta cuando por definición no puede.
- Duplicados de la clave del grano.

`ro.reglas(df, {"nombre": "expresión pandas" o Serie booleana})` → una columna por regla,
`n_reglas` y `reglas_violadas`.

### 2. Atípicos univariados

Elegir la escala antes que el método. Ventas, cajas y tickets son asimétricos a la derecha: en escala
original **casi todo método clásico marca la cola legítima**.

| Método | Función | Corte | Cuándo |
|---|---|---|---|
| z robusto (Iglewicz-Hoaglin) | `z_robusto` | \|z\| > 3.5 con mediana y MAD_n | escala ~simétrica (log de ventas) |
| Boxplot ajustado (Hubert-Vandervieren) | `boxplot_ajustado` | vallas Tukey corregidas por medcouple | ventas en escala original |
| Tukey lejano | `iqr_tukey(k=3)` | Q3 + 3·IQR | referencia conocida |
| Generalized ESD (Rosner; Grubbs si r = 1) | `gesd` | α = 0.05 global | prueba formal, datos ~normales (log) |
| Valores extremos (GPD sobre p90, censurada en p99) | `cola_gpd` | n·P(X ≥ x) < 0.05 | ¿la cola pesada lo explica? |
| z clásico | `z_clasico` | \|z\| > 3 | solo como contraste: se enmascara |

`ro.univariado(x)` hace todo: aparta ceros y negativos, elige log si la asimetría > 1, corre los
cinco métodos y vota por mayoría. `attrs` dice la escala y los excluidos.

La GESD y la GPD son **conservadoras** (controlan el error global): lo que marcan casi seguro no es
de la población; que no marquen nada no prueba que no haya errores. Fórmulas, supuestos y por qué
la GPD se ajusta censurada: `references/metodos.md`.

### 3. Atípicos contextuales (condicionales)

Un abarrote que vende como supermercado no es raro en la base, sí en su subcanal.

- **Dentro del grupo:** `ro.por_grupo(df, "venta", "subcanal", log=True)` (tienda, SKU, municipio,
  mes). Grupos con < 20 filas usan la referencia de toda la base y lo dicen.
- **Contra un modelo:** `ro.residuos_regresion(y, X)` (p. ej. `log venta ~ hogares + NSE`):
  residuo estudentizado externo con corte de Bonferroni, apalancamiento h > 2p/n y Cook > 4/n. El
  atípico es el PDV que vende muy distinto de lo que su entorno predice, no el que más vende.

### 4. Atípicos multivariados

Combinaciones raras que ninguna variable sola marca (venta alta con CP bajo y pocos hogares).

- `ro.mahalanobis_robusto(df, cols, log1p=True)`: D² con MCD (resiste ~50% de contaminación);
  corte χ²_p. Con miles de filas usar α = 0.999 (0.975 marca 2.5% de sanos por construcción).
  `variable_dominante` dice qué columna empuja.
- `ro.isolation_forest(df, cols, contaminacion=...)`: sin supuesto de forma; la contaminación sale
  del negocio (p. ej. % de mayoristas), no se ajusta para "que dé bien". **No ve** los puntos que
  solo rompen una correlación (cortes paralelos a los ejes): para eso Mahalanobis o LOF.
- `ro.lof(df, cols, k=20)`: atípico local dentro de un cúmulo.

Quitar columnas redundantes (importe = cantidad × precio) o el MCD queda singular.

### 5. Atípicos temporales

`ro.hampel(serie, ventana=7, t=3.5)`: mediana móvil y escala agrupada; da `valor_sugerido` para
imputar el pico. Con estacionalidad semanal fuerte, aplicarlo al residuo de STL (statsmodels) o por
día de la semana. Un hueco de captura (cero días seguidos) es un problema de integridad, no un
atípico: ver `retail_eda.densidad_temporal`.

### 6. Atípicos espaciales

`ro.espacial(lat, lon, venta, k=30)`: el valor contra la mediana y MAD de sus k vecinos (haversine).
Un PDV que vende 10× lo de su cuadra. Con k < 20 la MAD local es ruidosa y sobran falsos. Con
grupos (subcanal), comparar dentro del grupo: el reporte ya lo hace.

### 7. Decidir

1. **Consenso por familias** (`ro.consenso(flags, familias=...)`): univariado, contextual, espacial
   y multivariado. Una familia marca si más de la mitad de sus métodos marca; "atípico fuerte" si
   marca la mitad o más de las familias. Métodos de la misma familia no cuentan doble.
2. **Impacto** (`ro.impacto(x, flags)`): total, media, mediana, sd y CV con todos, sin atípicos y
   winsorizado, más el % del total que concentran. Si nada material cambia, se reportan y se dejan.
3. **Sensibilidad** (`ro.sensibilidad(x)`): conteo por umbral. Si salta mucho entre umbrales
   vecinos no hay corte natural: reportar el rango.
4. **Acción por clase:**

| Clase | Evidencia | Acción |
|---|---|---|
| Atípico matemático | viola una regla | corregir en la fuente; si no se puede, excluir y documentar |
| Atípico fuerte | ≥ mitad de las familias | revisar caso por caso con un atributo del negocio (tipo de cliente, formato, alta reciente) |
| Revisar | un método | conservar; usar estadísticos robustos |
| Extremo legítimo confirmado | negocio lo valida | conservar; analizar aparte si domina el total (mayoristas) |

Nunca borrar en silencio: marcar con una columna y dejar la decisión trazable.

## Gotchas

- **Enmascaramiento y anegamiento.** Media y sd se contaminan con los atípicos: un error grande
  esconde a los demás (masking) y hace parecer atípicos a los sanos (swamping). Siempre mediana/MAD,
  MCD, GESD o GPD censurada.
- **Cola pesada ≠ atípico.** En ventas el 1% más alto es real. Tukey en escala original marca
  5-10% de los PDV; usar log o boxplot ajustado y preguntar a la GPD.
- **Ceros y negativos dentro.** Un solo negativo impide la escala log; 20% de ceros arrastra la
  mediana y marca a media base. Van aparte.
- **Comparaciones múltiples.** Con 7,000 PDV y |z| > 3, ~19 sanos salen por azar. Usar cortes
  globales (GESD, Bonferroni en GPD y residuos) o BH sobre p-valores.
- **Umbrales ajustados al resultado.** Fijar corte y contaminación antes de ver la lista.
- **Atípico global vs contextual.** Sin grupo, toda una subpoblación (farmacias) sale atípica.

Detalle, detección y arreglo de cada uno: `references/gotchas.md`.

## Archivos

- `references/metodos.md` — fórmulas, supuestos, cortes y referencias de cada método.
- `references/gotchas.md` — las trampas, cómo detectarlas y cómo arreglarlas.
- `scripts/retail_outliers.py` — implementación, reporte Excel por línea de comandos y self-test.
