# Gotchas

Las trampas que producen listas de atípicos seguras y equivocadas. Cada una: mecanismo, cómo
detectarla y arreglo.

---

## 1. Enmascaramiento (masking) y anegamiento (swamping)

**Mecanismo.** Los atípicos inflan la sd y mueven la media. Un error de ×80 sube tanto la sd que los
demás errores quedan con |z| < 3 (masking), y la media desplazada deja a puntos sanos del otro lado
con |z| alto (swamping). Lo mismo pasa en multivariado con la covarianza clásica y en la cola con
una GPD ajustada sobre los propios errores.

**Detección.** Comparar `z_clasico` con `z_robusto`: si el robusto marca muchos más, hay
enmascaramiento. En la GPD: ξ sin censura ≫ ξ censurado (el self-test lo muestra).

**Arreglo.** Mediana/MAD, MCD, GESD (quita y recalcula) y GPD censurada. Nunca media y sd para
fijar un corte de atípicos.

## 2. Cola pesada no es atípico

**Mecanismo.** Venta por PDV, ticket y cajas siguen log-normal o Pareto. En escala original, Tukey
1.5 marca 5-10% de los PDV: la cola legítima. Quitarlos borra a las tiendas que más venden.

**Detección.** Asimetría > 1 o medcouple > 0.2; `sensibilidad` crece sin meseta.

**Arreglo.** Trabajar en log (z robusto, GESD, GPD) o con el boxplot ajustado. Preguntar a la GPD:
si la cola ajustada explica el punto (p_ajustado ≥ 0.05), es extremo, no error.

## 3. Ceros y negativos mezclados

**Mecanismo.** Una venta inflada en cero es dos poblaciones (vende / no vende). Con 20% de ceros la
mediana baja y medio mundo sale atípico alto; un solo negativo impide el log y obliga a la escala
original.

**Detección.** `(x == 0).mean()`, `(x < 0).sum()`.

**Arreglo.** `univariado(ceros="aparte", negativos="aparte")` (default). Los negativos son atípicos
matemáticos (devolución o error) y van a `reglas`; los ceros, a un análisis de conversión aparte.

## 4. Comparaciones múltiples

**Mecanismo.** Con n = 7,000 y |z| > 3 bajo normalidad, se esperan ~19 falsos; con χ²(0.975), 175.
Cuanto más grande la base, más "atípicos" sin que haya ningún error.

**Detección.** % marcado ≈ tasa nominal del corte (0.27%, 2.5%).

**Arreglo.** Cortes globales: GESD (α global), Bonferroni en GPD y residuos, χ²(0.999) en
Mahalanobis. Para listas exploratorias, BH con q = 0.10 y decirlo.

## 5. Atípico global vs contextual

**Mecanismo.** Sin grupo, una subpoblación entera (farmacias, mayoristas, tiendas de 24 h) sale
atípica, y un abarrote anómalo que vende como farmacia pasa desapercibido.

**Detección.** Los atípicos se concentran en un valor de una categórica (`crosstab`).

**Arreglo.** `por_grupo`, y espacial y multivariado dentro del grupo (el reporte lo hace con
`--grupo`). La subpoblación se analiza aparte, no se borra.

## 6. Umbrales ajustados al resultado

**Mecanismo.** Mover el corte o la `contaminacion` de Isolation Forest hasta que la lista "se vea
bien" convierte la detección en opinión.

**Arreglo.** Fijar cortes antes de ver la lista (los defaults del módulo tienen justificación en
`metodos.md`); reportar `sensibilidad`. La contaminación sale de un hecho del negocio.

## 7. Isolation Forest no ve correlaciones rotas

**Mecanismo.** Corta paralelo a los ejes. Un PDV con venta alta y CP bajo cuando ambas suelen ir
juntas no es raro en ninguna variable y se aísla tan lento como uno normal (self-test: 2-7 de 10).

**Arreglo.** Mahalanobis MCD o LOF para estructura de dependencia; IF para extremos globales.

## 8. Borrar en lugar de marcar

**Mecanismo.** Quitar filas sin dejar rastro cambia totales, cifras de referencia y comparaciones
entre corridas, y nadie puede revisar la decisión.

**Arreglo.** Columna de clase (`consenso`), hoja de impacto (`impacto`) y motivo por fila. Excluir
solo atípicos matemáticos o casos confirmados por el negocio, y decir cuántos y cuánto pesan.

## 9. Series: picos vs cambios de nivel y huecos

**Mecanismo.** Hampel marca picos aislados; un cambio de nivel (tienda remodelada, nueva ruta) dura
más que la ventana y no es atípico puntual. Un hueco de captura (ceros seguidos) tampoco.

**Arreglo.** Revisar `densidad_temporal` (retail-math-eda) antes; para cambios de nivel, CUSUM o
partición por fecha; Hampel sobre el residuo de STL cuando hay estacionalidad.

## 10. Muestras chicas

**Mecanismo.** Con n < 20 la MAD es inestable y el máximo |z| clásico está acotado; Tukey y GESD
casi no tienen potencia. La GPD necesita ≥ 30 excesos (≥ ~300 filas con u = p90).

**Arreglo.** En grupos chicos usar la referencia de la base (`por_grupo` lo hace con n < 20) o
reglas de negocio; no reportar "sin atípicos" como hallazgo.
