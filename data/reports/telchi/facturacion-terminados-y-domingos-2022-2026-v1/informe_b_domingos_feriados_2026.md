# Informe B — Domingos y feriados 2026: ¿qué sucursal vende más?

**Salones CM, 2A, RC y VI. Enero–septiembre 2026.**
Investigación read-only sobre ventas activas en bolivianos. Rama `feature/console-backend-core`. Corte: **2026-09-30**. Fecha: 2026-10-22.

Complementa la sección 3 del informe original `report.md` y le agrega **volumen físico, promedio por día operado y separación estricta domingo/feriado**. No modifica el informe original. No hubo ingesta, commit ni push.

---

## Respuesta directa

**El 2do. Anillo (2A) es la sucursal que más vende en domingos y en feriados, tanto en facturación total como por día operado.** Casa Matriz (CM, el “Centro”) lidera en cantidad de tickets, no en facturación.

| Ranking | Domingos | Feriados (días hábiles) |
| --- | --- | --- |
| 1.º | **2A — Bs 285.762** (Bs 8.165/domingo) | **2A — Bs 104.737** (Bs 17.456/feriado) |
| 2.º | CM — Bs 224.910 (Bs 6.426/domingo) | CM — Bs 82.242 (Bs 13.707/feriado) |
| 3.º | VI — Bs 90.909 (Bs 2.597/domingo) | RC — Bs 55.446 (Bs 9.241/feriado)* |
| 4.º | RC — Bs 116 (no opera domingos) | VI — Bs 29.060 (Bs 5.812/feriado) |

\* RC solo opera 6 feriados y su total incluye una venta única de azufre por Bs 8.700 (15,7% de su feriado). Sin esa línea, RC queda en Bs 46.746.

**Hallazgos que cambian la lectura:**

1. **2A gana por ticket, no por tráfico.** En domingos, 2A factura **+27,0% más** que CM con **−16,1%** de tickets. Ticket promedio: **Bs 99 vs Bs 65**. En 24 de 34 domingos comunes 2A supera a CM (70,6%).
2. **En feriados la brecha es mayor:** en los 5 feriados en que abrieron los cuatro salones, 2A vendió **Bs 104.187 vs Bs 75.403 de CM (+38,2%)**.
3. **La ventaja de 2A no es retail premium, es químico/fraccionado.** En domingos+feriados, 2A vende **Bs 116.970 de fraccionados** contra **Bs 60.895 de CM (+92%)**; en producto terminado propio la diferencia es menor (**+26%**). CM, en cambio, vende más reventa (traded): **Bs 119.293 vs Bs 110.028**.
4. **Los domingos son un día menor:** representan **1,9% de la venta de 2A**, **2,3% de CM**, **2,9% de VI** y **0% de RC**. La discusión de domingos no cambia el ranking anual de sucursales.
5. **El 22 de enero explica cerca de la mitad o más de los feriados:** 58,3% del feriado de 2A, 54,1% de CM, 61,8% de RC y 49,2% de VI. Es el único feriado que se comporta como día hábil (reposición post-feriado).

---

## 1. Método y calendario

### 1.1 Fuente y métrica

- **Ventas:** Foundation `foundation_sales_lines`, líneas activas (`canceled='N'`), moneda de documento `BS`, importe neto de línea (`line_total`), **antes de notas de crédito**.
- **Salones:** almacenes `CM-SAL`, `2A-SAL`, `RC-SAL`, `VI-SAL`.
- **Período:** 2026-01-01 a 2026-09-30.
- **Tickets:** facturas distintas (`doc_entry`) por salón y día. No se suman tickets por ítem.
- **Volumen físico:** solo productos propios (`LAB_FINISHED_PRODUCT` + `FRACTIONATED_PRODUCT` + `SEMI_FINISHED`), con el mismo mapa de conversión del Informe A. Litros, kg y dosis se reportan por separado; nunca se suman.
- **Cobertura del volumen:** 98,8% del importe del período tiene factor de conversión; el 1,2% restante son servicios, empaques y líneas sin presentación parseable. El volumen físico se reporta solo para producto propio, que representa **63,6% del importe**; la reventa queda solo en facturación.

### 1.2 Calendario

- **39 domingos** entre el 1 de enero y el 30 de septiembre de 2026.
- **10 feriados** en el rango; **1 cae domingo** (21 de junio, Año Nuevo Andino), por lo que hay **9 feriados no domingo**.
- Se excluye el **16 de julio (La Paz)**: los salones están en Santa Cruz y ese feriado es departamental de La Paz.
- Se incluye el **24 de septiembre (Santa Cruz)**, aunque la operación fue simbólica.

**Regla anti-doble-conteo:** un domingo que coincide con feriado se cuenta **solo como domingo**.

### 1.3 Días efectivamente operados

| Salón | Domingos operados | Feriados no domingo operados |
| --- | ---: | ---: |
| CM | 35 | 6 |
| 2A | 35 | 6 |
| VI | 35 | 5 |
| RC | **1** | 6 |

- **3 domingos cerraron todos:** 22 de marzo, 19 de abril y 27 de septiembre.
- CM y VI cerraron además el **15 de febrero**; 2A cerró además el **5 de julio**.
- RC está cerrado los domingos: su único registro es el 1 de marzo (1 ticket, Bs 116).
- **Carnaval (16 y 17 de febrero) cerraron todos.** El 1 de enero solo abrió CM. El 24 de septiembre solo hubo ventas testimoniales (2A Bs 550, RC Bs 206).

Por eso los promedios se calculan **sobre días operados**, no sobre el calendario completo.

---

## 2. Domingos 2026

| Salón | Facturación | Tickets | Ticket prom. | Domingos operados | **Bs por domingo** | % de su venta total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **2A** | **285.762** | 2.886 | **99** | 35 | **8.165** | 1,86% |
| CM | 224.910 | **3.441** | 65 | 35 | 6.426 | 2,28% |
| VI | 90.909 | 1.743 | 52 | 35 | 2.597 | 2,93% |
| RC | 116 | 1 | 116 | 1 | 116 | 0,00% |

- **2A vs CM:** +27,0% en facturación, −16,1% en tickets, +52,3% en ticket promedio.
- **En los 34 domingos comunes** (se excluyen el 15-Feb de CM/VI y el 5-Jul de 2A): 2A Bs 279.819 / 2.819 tickets vs CM Bs 219.057 / 3.367 tickets. La diferencia se mantiene (+27,7%).
- **No depende de un domingo puntual:** 2A gana 24 de los 34 domingos comunes; la mediana de la diferencia es +Bs 1.937 por domingo.
- **VI** tiene el mayor peso relativo de domingos (2,93% de su venta), pero el menor ticket (Bs 52).
- **RC no compite:** un solo domingo operado en nueve meses.

---

## 3. Feriados 2026 (días hábiles)

### 3.1 Totales por salón

| Salón | Facturación | Tickets | Ticket prom. | Feriados operados | **Bs por feriado** |
| --- | ---: | ---: | ---: | ---: | ---: |
| **2A** | **104.737** | 686 | 153 | 6 | **17.456** |
| CM | 82.242 | **1.114** | 74 | 6 | 13.707 |
| RC | 55.446 | 368 | 151 | 6 | 9.241 |
| VI | 29.060 | 423 | 69 | 5 | 5.812 |

- **2A lidera en facturación y por día**, pero **CM lidera en tickets** (185,7 por feriado vs 114,3 de 2A) con un ticket promedio 52% menor.
- **RC tiene un ticket promedio alto (Bs 151) que no es retail:** su feriado incluye compras grandes de químicos (azufre 25 kg, agua desionizada 10 L, ácido nítrico) y materia prima. Sin la línea de azufre de Bs 8.700, su ticket promedio baja a Bs 127.

### 3.2 Detalle por fecha

| Fecha | Feriado | 2A | CM | RC | VI | Total |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 01-01 | Año Nuevo | cerrado | **6.840** | cerrado | cerrado | 6.840 |
| 01-22 | Estado Plurinacional | **61.015** | 44.461 | 34.244 | 14.287 | 154.006 |
| 04-03 | Viernes Santo | 6.590 | **6.645** | 5.839 | 3.111 | 22.185 |
| 05-01 | Día del Trabajo | **13.420** | 5.051 | 3.708 | 2.217 | 24.396 |
| 06-04 | Corpus Christi | **12.352** | 10.556 | 8.142 | 4.529 | 35.579 |
| 08-06 | Independencia | **10.810** | 8.690 | 3.307 | 4.916 | 27.724 |
| 09-24 | Santa Cruz (dep.) | **550** | cerrado | 206 | cerrado | 756 |
| 02-16/17 | Carnaval | cerrado | cerrado | cerrado | cerrado | 0 |

- **2A gana 5 de las 6 fechas con operación real.** CM gana el Viernes Santo por **Bs 55** (empate técnico).
- **El 24-S es simbólico** (756 Bs en total): no debe leerse como demanda.
- **El 22-E concentra 49%–62% del total de feriados** de cada salón y se comporta como un día hábil. Es reposición, no ocio.

### 3.3 Comparación limpia: 5 feriados comunes

Para eliminar el efecto de días distintos (1-E solo CM, 24-S casi cerrado), se comparan los **5 feriados en que abrieron los cuatro salones**: 22-E, 3-A, 1-M, 4-J y 6-A.

| Salón | Facturación (5 feriados) | Tickets | Ticket prom. | **Bs por feriado** | Vs. 2A |
| --- | ---: | ---: | ---: | ---: | ---: |
| **2A** | **104.187** | 678 | 154 | **20.837** | — |
| CM | 75.403 | 995 | 76 | 15.081 | −27,6% |
| RC | 55.240 | 366 | 151 | 11.048 | −47,0% |
| VI | 29.060 | 423 | 69 | 5.812 | −72,1% |

**2A supera a CM por +38,2%** en la base comparable. El orden no cambia.

---

## 4. Domingo vs feriado

| Indicador | Domingo (2A) | Feriado (2A) | Lectura |
| --- | ---: | ---: | --- |
| Facturación por día | Bs 8.165 | Bs 17.456 | El feriado hábil vende **2,1×** un domingo |
| Tickets por día | 82,5 | 114,3 | +39% |
| Ticket promedio | Bs 99 | Bs 153 | +55% |
| Litros propios por día | 38,6 | 141,9 | +268% (químico/fraccionado) |
| kg propios por día | 36,2 | 78,9 | +118% |
| Dosis por día | 352 | 392 | +11% |

- **El feriado de semana es un día de reposición**, no de paseo: más litros y kg por ticket, sobre todo químicos.
- **El domingo es un día de conveniencia:** más tickets por hora, ticket bajo, mix de retail (colágeno, citrato, minoxitel).
- **La diferencia de ticket promedio entre 2A y CM se agranda en feriados** (Bs 153 vs Bs 74), porque 2A captura compras de químicos que CM no tiene.

---

## 5. Tráfico vs ticket: quién es cada sucursal

| Salón | Tickets domingo | Ticket prom. domingo | Tickets feriado | Ticket prom. feriado | Perfil |
| --- | ---: | ---: | ---: | ---: | --- |
| **CM** | **3.441** | Bs 65 | **1.114** | Bs 74 | **Tráfico / conveniencia** |
| **2A** | 2.886 | **Bs 99** | 686 | **Bs 153** | **Facturación / ticket alto** |
| VI | 1.743 | Bs 52 | 423 | Bs 69 | Volumen bajo, barrio |
| RC | 1 | — | 368 | Bs 151 | Cerrado domingos; mayoreo químico |

- **CM atiende más gente, pero cada ticket vale menos.** Es una tienda céntrica de conveniencia.
- **2A atiende menos gente, pero cada ticket vale más.** Su ventaja no es tráfico: es composición de compra.
- **VI** replica el patrón de CM a menor escala (más tickets que 2A en términos relativos, ticket bajo).
- **RC** no es comparable en domingos y en feriados su venta es mayormente químico/mayoreo.

---

## 6. Volumen físico en domingos y feriados

Producto propio (LAB terminado + fraccionado + semiterminado). Litros, kg y dosis en columnas separadas.

### 6.1 Totales del período (domingos + feriados)

| Salón | Litros | kg | Dosis | Días operados | Litros/día | kg/día | Dosis/día |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **2A** | **2.202,5** | **1.740,4** | 14.681 | 41 | **53,7** | **42,4** | 358 |
| CM | 828,2 | 1.079,2 | **15.127** | 41 | 20,2 | 26,3 | **369** |
| RC | 903,9 | 255,5 | 1.177 | 7 | 129,1 | 36,5 | 168 |
| VI | 525,1 | 461,9 | 4.704 | 40 | 13,1 | 11,5 | 118 |

- **2A lidera litros y kg**, y lo hace por amplio margen: **2,7× los litros de CM**.
- **CM lidera dosis** (15.127 vs 14.681) y por día (369 vs 358). Es la sucursal de cápsulas/tabletas/sobres.
- **RC tiene el mayor litro/día** (129,1), pero sobre solo 7 días y con una venta de químico de Bs 8.700. No es un dato comparable.
- **VI es la más chica en todas las dimensiones.**

### 6.2 Solo domingos, por domingo operado

| Salón | Litros/domingo | kg/domingo | Dosis/domingo |
| --- | ---: | ---: | ---: |
| **2A** | **38,6** | **36,2** | 352 |
| CM | 17,2 | 21,8 | **313** |
| VI | 10,9 | 8,9 | 103 |

2A vende **2,2× los litros** y **1,7× los kg** de CM por domingo. En dosis, CM se acerca (313 vs 352).

---

## 7. Qué productos explican las diferencias

### 7.1 Mezcla por tipo de producto (domingos + feriados)

| Tipo | CM | 2A | RC | VI |
| --- | ---: | ---: | ---: | ---: |
| **LAB terminado propio** | 112.343 (36,6%) | **142.052 (36,4%)** | 14.436 (26,0%) | 44.863 (37,4%) |
| **Reventa (traded)** | **119.293 (38,8%)** | 110.028 (28,2%) | 12.565 (22,6%) | 44.452 (37,1%) |
| **Fraccionado** | 60.895 (19,8%) | **116.970 (30,0%)** | 17.759 (32,0%) | 26.993 (22,5%) |
| Materia prima | 916 | 10.254 | **9.886 (17,8%)** | 78 |
| Empaque | 8.634 | 7.470 | 745 | 2.307 |
| Otros insumos | 5.060 | 3.720 | 170 | 1.170 |

**La diferencia 2A−CM se explica por fraccionado (+Bs 56.075) y terminado (+Bs 29.709), no por reventa (CM vende +Bs 9.265).** En otras palabras: 2A gana con producto propio y químico; CM gana con reventa.

### 7.2 Familias propias: dónde 2A supera a CM

| Familia | CM | 2A | Diferencia 2A−CM |
| --- | ---: | ---: | ---: |
| Tintura de Yodo / Lugol | 1.805 | 12.569 | **+10.764** |
| Alcohol 70% | 6.011 | 15.667 | **+9.656** |
| Tricloro | 935 | 6.285 | +5.350 |
| Cloro | 1.270 | 6.008 | +4.738 |
| Aceite de Coco | 6.363 | 10.535 | +4.172 |
| Sulfato de Cobre | 965 | 4.898 | +3.933 |
| Aguas medicinales | 4.614 | 8.347 | +3.733 |
| Ácido Nítrico | 1.300 | 3.711 | +2.411 |

### 7.3 Familias propias: dónde CM supera a 2A

| Familia | CM | 2A | Diferencia CM−2A |
| --- | ---: | ---: | ---: |
| Colágeno | 26.719 | 23.735 | **+2.984** |
| Ácido Ascórbico | 3.724 | 2.981 | +743 |
| Minoxitel | 14.971 | 14.307 | +665 |
| Citrato de Magnesio | 11.985 | 11.324 | +661 |
| Talco | 3.497 | 3.255 | +243 |

**Lectura:** CM gana en las líneas de alto valor unitario y retail (colágeno, minoxitel, citrato); 2A gana en químicos, alcoholes y formatos grandes. La ventaja de 2A es de **mix y formato**, no de surtido premium.

### 7.4 Productos más vendidos por salón (domingos + feriados)

| Puesto | CM | 2A | VI | RC |
| ---: | --- | --- | --- | --- |
| 1 | Bicarbonato 1 kg — Bs 17.687 | Bicarbonato 1 kg — Bs 18.745 | Colágeno Premium Acaí — Bs 6.246 | Azufre Tech 25 kg — Bs 8.700 |
| 2 | Colágeno Premium Acaí — Bs 15.193 | Colágeno Premium Acaí — Bs 12.545 | Bicarbonato 1 kg — Bs 5.356 | Agua desionizada 10 L — Bs 2.923 |
| 3 | Minoxitel 5% Hombre — Bs 12.871 | Minoxitel 5% Hombre — Bs 12.267 | Minoxitel 5% Hombre — Bs 4.875 | Bicarbonato 1 kg — Bs 1.951 |
| 4 | Citrato de Magnesio — Bs 11.985 | Citrato de Magnesio — Bs 11.324 | Citrato de Magnesio — Bs 3.881 | Cloro 1 kg — Bs 1.744 |
| 5 | Colágeno Manzana — Bs 8.585 | Colágeno Manzana — Bs 7.748 | Colágeno Manzana — Bs 2.489 | Sulfato de Cobre — Bs 1.603 |

- **En CM y 2A el producto más vendido en domingos/feriados es bicarbonato de sodio**, un fraccionado de bajo precio unitario; no es colágeno ni minoxitel. En VI el primero es colágeno premium.
- **RC es un caso aparte:** su venta está marcada por operaciones puntuales de azufre e insumos, no por retail.
- **VI** tiene el mix más “retail” de las tres sucursales que abren domingos: colágeno primero.

---

## 8. Contexto 2022–2024

Facturación por domingo operado, solo almacenes de salón (misma metodología del informe original):

| Período | 2A | CM | VI | RC |
| --- | ---: | ---: | ---: | ---: |
| 2022 abr–sep | **4.305** | 3.533 | 1.448 | cerrado |
| 2023 | **4.869** | 4.376 | 1.640 | 1.500 (1 día) |
| 2024 ene–jun (parcial) | **5.428** | 5.388 | 1.655 | 1.349 (2 días) |
| **2026 ene–sep** | **8.165** | 6.426 | 2.597 | cerrado |

- El patrón **2A primero en facturación, CM primero en tickets** se repite en los cuatro años.
- En 2024 la diferencia fue casi nula (Bs 40 por domingo); en 2026 se reabrió a **+27%**.
- La serie es **nominal** y los períodos no son idénticos (2022 empieza en abril, 2024 es parcial). Sirve como dirección, no como comparación estricta.

---

## 9. Límites

1. **RC no opera domingos.** Su inclusión en el ranking dominical es solo para mostrar que está cerrado; no es un competidor.
2. **Feriados con denominadores distintos.** CM y 2A operaron 6; VI 5; el 1-E solo CM y el 24-S es simbólico. Por eso se reporta la base de **5 feriados comunes**.
3. **El 22-E domina los feriados** (49%–62% del total). Los promedios de feriado sin ese día son mucho menores y el ranking se mantiene, pero la magnitud cambia.
4. **RC está inflado por una línea de azufre de Bs 8.700** (15,7% de su feriado). Sin ella, sigue tercero pero con Bs 46.746.
5. **Volumen físico solo de producto propio.** La reventa (28%–39% de la venta) no tiene presentación comparable y queda fuera del volumen; sí está en la facturación.
6. **Venta antes de notas de crédito.** No se Netean devoluciones; el informe original reporta que las notas de crédito de terminados son 2,97% en 2026.
7. **Nominal, sin deflactor.** No se afirma crecimiento real; solo posición relativa entre sucursales.
8. **Un solo canal:** Foundation cubre documentos en BS y facturas activas; puede faltar alguna venta fuera de ese circuito.

---

## 10. Reproducibilidad

| Archivo | Contenido |
| --- | --- |
| `scripts/sundays_2026_volume.py` | Pipeline de domingos/feriados con volumen físico |
| `domingos_datos_clave.json` | Rankings, resumen por salón, calendario y checks |
| `domingos_feriados_2026_resumen_salon.csv` | Totales por salón y tipo de día |
| `domingos_feriados_2026_volumen_por_fecha.csv` | Detalle fecha × salón con litros, kg y dosis |
| `domingos_feriados_2026_top_productos.csv` | Top productos de domingos+feriados |
| `domingos_feriados_2026_familias_por_salon.csv` | Familias propias por salón |
| `domingos_feriados_2026_tipo_producto.csv` | Mezcla LAB / fraccionado / reventa por salón |

Ejecución (desde `SrvRestAstroLS_v1/backend`):

```bash
uv run python ../../data/reports/telchi/facturacion-terminados-y-domingos-2022-2026-v1/scripts/sundays_2026_volume.py
```

El script es idempotente, no modifica los archivos originales (`domingos_feriados_2026.csv`, `report.md`, `datos_clave.json`) y no escribe fuera de esta carpeta ni de `/tmp/opencode/telchi-hist`.
