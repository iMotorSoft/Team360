# Facturación de productos terminados 2022 vs 2026 y ventas de domingos y feriados

Investigación read-only sobre Parquet histórico y Data Lake Telchi. Rama `feature/console-backend-core`.
Corte de datos: **2026-09-30** (máximo disponible). Fecha del informe: 2026-10-22.

No se modificó ningún dato, Parquet, pipeline, esquema, SAP ni PostgreSQL. No hubo ingesta, promoción, commit ni push.

---

## Respuestas directas

### 1. ¿Creció de verdad la facturación de productos terminados?

**Sí, y el crecimiento es grande en términos nominales: la facturación de productos terminados pasó de Bs 13,90 millones (ene–sep 2022) a Bs 27,91 millones (ene–sep 2026), +100,7%.**

Pero hay que decir las dos cosas juntas:

- **No es solo precio, pero el precio explica la mayor parte.** En los 247 productos que existían en ambos años, la facturación subió +67,4%. De esos Bs 7,54 millones adicionales, **Bs 5,27 millones (70%) son precio** y **Bs 2,26 millones (30%) son volumen**. El precio unitario mediano subió +41,7% y el ponderado por venta +50,2%.
- **El resto del crecimiento viene de productos nuevos.** 92 productos que no se vendían en 2022 aportaron Bs 9,19 millones en 2026; 65 productos de 2022 (Bs 2,73 millones) ya no se venden. El recambio neto suma **+Bs 6,47 millones**.
- **El resultado es robusto a las anomalías.** La factura anómala de Bs 69,49 millones (ácido acético, 2022-02-02) **no pertenece a productos terminados** (es fraccionado), así que no afecta esta respuesta. Si se excluye la licitación de alcohol de Bs 1,14 millones, el crecimiento neto sube a +114%. Si se agregan las presentaciones de caja/pallet que quedaron sin código SAP (Bs 0,48 millones), el crecimiento baja a +94%. **En cualquier escenario razonable, la facturación de terminados se duplicó o casi se duplicó.**
- **El salto no es un artefacto de 2022:** en ene–sep 2023 la categoría facturaba Bs 15,37 millones; en el mismo período de 2026, Bs 27,91 millones (+81,5%).

**Qué se vendía antes y qué se vende ahora** (detalle en la sección 2.3): en 2022 mandaban alcohol 70% (incluida una licitación), loción Povidine, colágeno en polvo y Creolina. En 2026 el primer producto es **Minoxitel 5% – Hombre (Bs 2,37 millones)**, seguido de Povidine 1 L (Bs 1,66 millones), un SKU sin nombre en el maestro (Bs 1,48 millones), Povidine 120 mL, alcohol 70% y colágeno con vitamina C. El alcohol perdió el primer lugar, el colágeno se consolidó y Minoxitel se multiplicó; Calentá, Pasta de Agua y Repelitel son las incorporaciones visibles.

### 2. ¿Las sucursales del "Centro" son las que más venden los domingos y feriados?

**Parcialmente. Casa Matriz (el "Centro") lidera en cantidad de tickets, pero no en facturación: el 2do. Anillo vende más.**

Domingos de 2026 (ene–sep, 35 domingos operados por cada salón):

| Salón | Facturación domingos | Tickets | Bs por domingo | Ticket promedio |
| --- | ---: | ---: | ---: | ---: |
| 2A (2do. Anillo) | **Bs 285.762** | 2.886 | **Bs 8.165** | Bs 99 |
| CM (Casa Matriz / Centro) | Bs 224.910 | **3.441** | Bs 6.426 | Bs 65 |
| VI (Villa 1ro. de Mayo) | Bs 90.909 | 1.743 | Bs 2.597 | Bs 52 |
| RC (Roca y Coronado) | Bs 116 | 1 | — | — |

- **2A factura +27,0% más que Casa Matriz los domingos**, y la diferencia se mantiene si se comparan solo los 34 domingos en que ambos abrieron (+27,7%).
- **Casa Matriz tiene +19,2% más tickets**, es decir, más tráfico, pero con un ticket promedio 34% menor.
- **En feriados de semana el orden se repite:** 2A Bs 104.737, CM Bs 82.242, RC Bs 55.446, VI Bs 29.060. En los 5 feriados en que ambos abrieron, 2A supera a CM por +38%.
- **La historia acompaña:** en domingos, 2A ya superaba a CM en 2022 (Bs 4.305 vs 3.533 por domingo), 2023 (4.869 vs 4.376) y 2024 (5.428 vs 5.388, prácticamente empate).
- **Matiz importante:** los domingos son un día menor. Representan 1,9% de la facturación de 2A y 2,3% de la de CM. Los feriados de semana venden entre 23% y 42% de un día hábil normal (excepto el 22 de enero, que se comporta como día normal). La discusión de domingos mueve poco la aguja frente a la operación de lunes a viernes.

**Conclusión:** si "el Centro vende más" significa **gente atendida**, es cierto. Si significa **facturación**, no: el 2do. Anillo vende más, todos los años medidos. RC no abre domingos y Villa abre pero con volumen bajo.

---

## 1. Cómo se respondió

### Fuentes

| Uso | Fuente | Cobertura |
| --- | --- | --- |
| Ventas ene–abr 5 2022 | `raw/legacy/parquet/saleProduct-2022-0*.parq` | 222.686 líneas, Bs 23,20 M |
| Ventas abr 6–sep 30 2022 y 2023 | `raw/legacy/parquet/saleSB1Product-*.parq` (sin sufijo `-h`) | SAP B1 real, Bs 37,30 M en 2022 |
| Ventas 2026 | Foundation `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot 1408 | 715.017 líneas activas en BS, Bs 80,35 M |
| Maestro SAP | `raw/legacy/parquet/productSB1.parq` | 11.245 ítems |
| Maestro legacy | `raw/legacy/parquet/product.parq` | 25.221 ítems |
| Clasificación de negocio | `crosswalk/_versions/v2_product_business_type_f9c1130d852ccb61` | 42.147 filas |
| Almacén → oficina | `raw/legacy/parquet/sapWhsOfficeName.parq` | 60 almacenes |

Los archivos `saleSB1Product-*-h.parq` **no** se usaron como SAP: son data legacy transformada al esquema SAP (el código legacy quedó en `ItemCode`). Los archivos sin sufijo son SAP B1 real.

### Métrica

Importe **neto de línea en bolivianos**, facturas activas, **antes de notas de crédito**:

- 2022 legacy: `ProductSalePriceNet` (neto de descuento; `ProductSalePrice` es precio de lista y sobreestima 2,6%).
- 2022 SAP: `ItemSale`, con `u_estadofc <> 'A'`.
- 2026: `line_total`, con `canceled='N'` y `doc_currency='BS'`.

Las notas de crédito se informan por separado y se usan como sensibilidad, no se mezclan con la venta.

### Períodos

- **2022:** 1 ene–5 abr desde legacy + 6 abr–30 sep desde SAP. Total Bs 60,50 M.
- **2026:** 1 ene–30 sep (máximo disponible; no hay oct–dic). Total Bs 80,35 M.
- **2023 ene–sep** solo como referencia de trayectoria.
- **2024** no se usa como período completo: el archivo de junio 2024 es parcial (5.954 líneas contra ~75.000 normales). Solo se usa como referencia parcial en domingos.

### Crosswalk legacy ↔ SAP (prerrequisito)

No se vinculó por descripción ni por similitud de texto. La llave auditada es **`productSB1.u_codactive` = código legacy**, exactamente el vínculo que documenta el script original `convertActiveToSap02.py`.

- 11.245 ítems SAP; **7.318 mapeados** (65,1%) a **7.236 códigos legacy**.
- 67 códigos legacy mapean a más de un ítem SAP; se mantienen separados como casos 1:N, **no se fusionan**.
- 3.927 ítems SAP no tienen código legacy en el maestro.
- El `product_crosswalk` del Data Lake es identidad por fuente, **no** equivalencia legacy↔SAP; no se usó como conciliación.

Cobertura real del empalme en el Q1 2022 (excluyendo la factura anómala):

- **98,75% de las líneas** y **96,05% del importe** tienen código SAP vinculado.
- Quedan **Bs 916.079** sin código (3,95%), en su mayoría presentaciones de caja/pallet de productos que sí están en el universo (alcohol 70% caja, Povidine caja, alcohol en gel pallet).
- En 2022 abr–sep, 12,5% del importe está en ítems SAP sin código legacy; en 2026, 26,9%. Eso **no afecta los totales por tipo de negocio** (la clasificación viene del ítem SAP), solo impide emparejar esos SKUs uno a uno.

---

## 2. Pregunta 1: facturación de productos terminados

### 2.1 Totales por tipo de negocio

| Tipo | 2022 (ene–sep) | 2026 (ene–sep) | Variación |
| --- | ---: | ---: | ---: |
| **LAB_FINISHED_PRODUCT** (terminados) | **13.902.604** | **27.907.000** | **+100,7%** |
| FRACTIONATED_PRODUCT | 16.807.586 | 24.001.404 | +42,8% |
| TRADED_PRODUCT (reventa) | 19.327.267 | 18.150.320 | −6,1% |
| RAW_MATERIAL | 4.416.820 | 6.617.234 | +49,8% |
| PACKAGING | 2.036.903 | 3.246.343 | +59,4% |
| Otros / sin clasificar | 4.006.075 | 427.853 | — |
| **Total** | **60.497.255** | **80.350.154** | **+32,8%** |

Nota: el total 2022 excluye la factura anómala de Bs 69,49 M (ver 2.5). Sin esa exclusión, 2022 sería Bs 130,0 M y la comparación total carecería de sentido; la comparación de terminados no se ve afectada porque el producto anómalo es fraccionado.

Lectura: el crecimiento de la empresa está concentrado en terminados. Reventa, que era la categoría más grande en 2022, hoy es más chica. La clasificación es **actual**, aplicada retroactivamente a los códigos de 2022: es una limitación, no una serie histórica certificada.

### 2.2 ¿Precio o volumen?

Sobre los **247 SKUs presentes en ambos años**:

| Concepto | Importe |
| --- | ---: |
| Facturación 2022 | Bs 11.176.863 |
| Facturación 2026 | Bs 18.712.688 |
| Variación | **+Bs 7.535.825 (+67,4%)** |
| Efecto precio | **Bs 5.273.730 (70,0%)** |
| Efecto volumen (a precios 2022) | **Bs 2.262.095 (30,0%)** |
| Residual | ≈ 0 |

- Precio unitario mediano: **×1,417** (+41,7%). Ponderado por venta 2026: **×1,502** (+50,2%). Rango intercuartil ×1,26 a ×1,69.
- No hay ningún SKU con caída de precio relevante: el ratio mínimo es 0,80.
- **Guard de presentación:** se compararon los tamaños en el nombre (mL, L, g, kg). Ninguno de los 88 SKUs con alza superior a 1,5× cambió de tamaño. Solo 1 SKU de 247 tiene unidad legacy distinta a la SAP (`L02891`, ENV→UNI, Bs 975 en 2022 y Bs 100 en 2026): irrelevante.
- **Guard de unidades:** kg, litros y unidades no se suman entre sí. La descomposición es SKU por SKU y solo suma importes; las cantidades se usan dentro de cada SKU.

**Advertencia:** todo es nominal. Sin deflactor (IPC Bolivia) no se puede afirmar cuánto del +50% de precio es inflación y cuánto es margen o mix. El volumen +20% a precios constantes de 2022 sí es una señal real de más unidades vendidas.

**Chequeo de consistencia:** el crecimiento no depende de un mes puntual. En 2022 la categoría facturaba entre Bs 1,2 y 1,9 millones por mes; en 2026, entre Bs 2,7 y 3,5 millones por mes, **todos los meses**. La comparación ene–sep no está apoyada en un pico aislado.

### 2.3 Qué se vendía en 2022 y qué se vende en 2026

**Top 10 por facturación, productos terminados**

| # | 2022 | Bs | 2026 | Bs |
| ---: | --- | ---: | --- | ---: |
| 1 | ALCOHOL 70% x 1 L | 1.520.288 | MINOXITEL 5% LOCIÓN – HOMBRE x 100 mL | 2.373.406 |
| 2 | ALCOHOL 70% x 1 L – LICITACIÓN | 1.142.400 | LOCIÓN POVIDINE LITEL 10% x 1 L | 1.663.158 |
| 3 | LOCIÓN POVIDINE LITEL 10% x 1 L | 563.254 | *(L03402, sin nombre en maestro)* | 1.480.362 |
| 4 | COLÁGENO HIDROLIZADO CON CALCIO (sabor) | 444.487 | LOCIÓN POVIDINE LITEL 10% x 120 mL | 1.167.685 |
| 5 | CREOLINA x 10 L | 341.931 | *(L03612, sin nombre en maestro)* | 1.020.614 |
| 6 | CREOLINA x 1 L | 301.805 | ALCOHOL 70% x 1 L | 903.367 |
| 7 | COLÁGENO HIDROLIZADO CON CALCIO (sabor) | 295.596 | COLÁGENO HIDROLIZADO C/VIT. C + CALCIO | 889.504 |
| 8 | LOCIÓN POVIDINE LITEL 10% x 120 mL | 292.219 | COLÁGENO HIDROLIZADO C/VIT. C + CALCIO | 605.583 |
| 9 | POMADA PENICILINA x 16 g | 285.646 | CREOLINA x 10 L | 604.790 |
| 10 | TINTURA DE YODO x 1 L | 283.691 | CREOLINA x 1 L | 557.868 |

**Movimientos que explican el cambio**

- **Minoxitel pasa a ser la línea más fuerte.** En 2022 vendía Bs 0,30 M entre sus versiones 5% y 3%; hoy aporta Bs 2,80 M (Bs 2,37 M la 5% hombre + Bs 0,42 M la 3% mujer). Los SKUs antiguos "MINOXITEL 5% LOCIÓN x 100 mL" (Bs 224 mil) y "3% LOCIÓN" (Bs 73 mil) desaparecieron: es una **sucesión probable por renombre/segmentación**, no se fusionó en los números.
- **Povidine creció fuerte y se consolidó:** los dos SKUs principales (1 L + 120 mL) pasaron de Bs 0,86 M a Bs 2,83 M; la familia completa, de Bs 1,16 M a Bs 3,46 M.
- **El alcohol 70% perdió peso:** la familia completa bajó de Bs 3,33 M a Bs 2,39 M (−28%), y la licitación de Bs 1,14 M no se repitió. El SKU de 1 L cayó de Bs 1,52 M a Bs 0,90 M. Sigue siendo grande, pero dejó de ser el primero.
- **El colágeno se consolidó, no creció:** pasó de 7 SKUs y Bs 1,68 M en 2022 a 3 SKUs y Bs 1,50 M, con la línea "vitamina C + calcio" (Bs 1,50 M) como única protagonista. Los códigos viejos con calcio y las variantes de sabor quedaron en cero.
- **Creolina acompaña:** de Bs 1,21 M a Bs 1,87 M (+55%).
- **Nuevos de nicho:** Calentá 250 g (Bs 0,56 M), Pasta de Agua 50 g (Bs 0,49 M), Repelitel 200 mL (Bs 0,33 M), Alcohol 75% (Bs 41 mil), Violeta de Genciana 2% (Bs 15 mil).
- **Desaparecen** la licitación de alcohol (Bs 1,14 M), la pomada de penicilina (de Bs 286 mil a Bs 104 mil), el bronceador de urucú viejo (reemplazado por versión "NUEVO") y varias esencias de 30–60 mL.

**Cartera:** 247 SKUs en ambos años, **65 descontinuados** (Bs 2,73 M en 2022) y **92 nuevos** (Bs 9,19 M en 2026). El recambio neto aporta **+Bs 6,47 M**, más que el efecto volumen de los SKUs comunes.

### 2.4 Sensibilidades

| Escenario | 2022 | 2026 | Crecimiento |
| --- | ---: | ---: | ---: |
| Bruto (base del informe) | 13.902.604 | 27.907.000 | **+100,7%** |
| Neto de notas de crédito | 13.791.256 | 27.077.005 | +96,3% |
| Neto, excluyendo licitación L02924 | 12.648.856 | 27.077.005 | +114,1% |
| Bruto + presentaciones caja/pallet sin código | 14.381.736 | 27.907.000 | +94,0% |

Las notas de crédito de terminados pasaron de 1,16% de la venta (abr–sep 2022) a **2,97%** en 2026 (Bs 829.994). Es un dato relevante por sí mismo: más devoluciones relativas.

### 2.5 Anomalías detectadas

1. **Factura 3247102 (2022-02-02):** 1.737.294 unidades de "ÁCIDO ACÉTICO x 1 L" por **Bs 69.491.640** en 2 líneas (una de 3 unidades y otra de 1.737.291). Es más de 7 veces la facturación mensual de la empresa y 1.737 toneladas de ácido acético. **Excluida como error demostrado.** Pertenece a FRACTIONATED_PRODUCT, así que **no afecta la comparación de terminados**; sí distorsionaría el total (2022 pasaría de Bs 60,5 M a Bs 130,0 M) y la categoría fraccionados.
2. **Licitación L02924 (jun–ago 2022):** 103.000 L de alcohol 70% a SOLUTESA y DISPROMED por Bs 1.142.400 en 8 facturas, canal Lab. Es venta real, no error; se mantiene en la base y se reporta la sensibilidad (+114% si se excluye).
3. **Presentaciones caja/pallet sin código SAP:** Bs 479.132 de productos terminados vendidos en caja/pallet en el Q1 2022 que no tienen ítem SAP vinculado. No se imputaron; se usan como sensibilidad (+94%).
4. **28 SKUs de 2026 sin nombre en el maestro:** Bs 4.064.409 (14,6% de la categoría). El maestro `productSB1.parq` es anterior a su creación. Los importes son válidos; **no se puede nombrar** L03402 (Bs 1,48 M), L03612 (Bs 1,02 M), L03658 (Bs 0,29 M) y 24 más.
5. **Códigos legacy reutilizados:** 5.970 códigos tienen más de un nombre entre 2018 y 2022 y "VACIO" es un nombre placeholder. Por eso el empalme se hizo por código SAP, no por nombre.

---

## 3. Pregunta 2: domingos y feriados

### 3.1 Quién es "Centro"

No existe un código de sucursal llamado "Centro". La evidencia convergente es:

- Almacén SAP **CM-SAL** = "Almacén Salón Casa Matriz".
- Almacén SAP **CM-DAN** = "Almacén de Dañados **Salón Centro**".
- Ambos cuelgan de la oficina **CasaMatriz**.
- En legacy, la oficina 1 es "Casa Matriz" y concentra el salón céntrico.

**Identificación: "Centro" = Casa Matriz (CM-SAL). Confianza ALTA**, aunque no CERTERA: no hay un código que se llame literalmente Centro.

### 3.2 Domingos 2026 (ene–sep)

Cada salón operó 35 domingos. RC solo registra 1 domingo (Bs 116, 1 ticket): está cerrado.

| Salón | Facturación | Tickets | Bs/domingo | Ticket prom. | % de su venta total |
| --- | ---: | ---: | ---: | ---: | ---: |
| **2A** | **285.762** | 2.886 | **8.165** | 99 | 1,9% |
| **CM** | 224.910 | **3.441** | 6.426 | 65 | 2,3% |
| VI | 90.909 | 1.743 | 2.597 | 52 | 2,9% |
| RC | 116 | 1 | — | — | 0,0% |

- 2A lidera facturación por **+27,0%** sobre CM.
- CM lidera tickets por **+19,2%** sobre 2A.
- En los **34 domingos comunes**: 2A Bs 279.819 / 2.819 tickets vs CM Bs 219.057 / 3.367 tickets. El orden no cambia.
- Cierres: ambos cerraron el 22 de marzo, 19 de abril y 27 de septiembre; CM además el 15 de febrero; 2A además el 5 de julio.

### 3.3 Feriados 2026 (solo días hábiles y alcance Santa Cruz)

| Fecha | Feriado | 2A | CM | RC | VI | Total |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 01-01 | Año Nuevo | cerrado | 6.840 | cerrado | cerrado | 6.840 |
| 01-22 | Estado Plurinacional | **61.015** | 44.461 | 34.244 | 14.287 | 154.006 |
| 02-16/17 | Carnaval | cerrado | cerrado | cerrado | cerrado | 0 |
| 04-03 | Viernes Santo | 6.590 | **6.645** | 5.839 | 3.111 | 22.185 |
| 05-01 | Día del Trabajo | **13.420** | 5.051 | 3.708 | 2.217 | 24.396 |
| 06-04 | Corpus Christi | **12.352** | 10.556 | 8.142 | 4.529 | 35.579 |
| 08-06 | Independencia | **10.810** | 8.690 | 3.307 | 4.916 | 27.724 |
| 09-24 | Santa Cruz (dep.) | **550** | cerrado | 206 | cerrado | 756 |

- 2A lidera 5 de 6 feriados operados; el Viernes Santo es un empate técnico (CM +Bs 55).
- En los 5 feriados comunes: **2A Bs 104.187 vs CM Bs 75.403 (+38,2%)**.
- El 22 de enero es el único feriado que se comporta como día normal. Los demás venden entre 23% y 42% de un día hábil, según el salón.
- **Los feriados no son una oportunidad de crecimiento:** son días de baja venta. El 24 de septiembre (feriado departamental) la operación es prácticamente nula.

### 3.4 Serie histórica de domingos

Facturación por domingo operado, solo almacenes de salón (para que la comparación sea limpia):

| Período | 2A | CM | VI | RC |
| --- | ---: | ---: | ---: | ---: |
| 2022 abr–sep | **4.305** | 3.533 | 1.448 | cerrado |
| 2023 | **4.869** | 4.376 | 1.640 | 1.500 (1 día) |
| 2024 ene–jun (parcial) | **5.428** | 5.388 | 1.655 | 1.349 (2 días) |
| 2026 ene–sep | **8.165** | 6.426 | 2.597 | cerrado |

Mismo patrón en los cuatro años: 2A primero en facturación, CM primero en tickets. En 2024 la diferencia de facturación fue casi nula; en 2026 se volvió a abrir a 27%.

### 3.5 Lectura de negocio

- **CM es la sucursal de tráfico:** más tickets, ticket promedio bajo (Bs 65 los domingos, Bs 74 en feriados). Es una tienda de conveniencia céntrica.
- **2A es la sucursal de facturación:** menos tickets pero ticket promedio 50% más alto.
- **Domingo y feriado no son el campo de batalla.** Entre ambos días suman 2,5%–3,1% de la venta de cada salón. La venta de lunes a viernes de 2A (Bs 74.270/día) es 9 veces un domingo.
- Si la pregunta es dónde poner esfuerzo comercial en domingo, la respuesta es **2A para facturar y CM para captar tráfico**. Si la pregunta es qué sucursal es más importante, la respuesta está en la semana, no en el domingo.

---

## 4. Límites de la evidencia

1. **Clasificación actual, no histórica.** `LAB_FINISHED_PRODUCT` se aplica hoy a los códigos de 2022. Un SKU pudo cambiar de uso; no hay clasificación por período.
2. **Nominal, sin deflactor.** No se afirma crecimiento real (ajustado por inflación), solo nominal y volumen a precios 2022.
3. **Corte 2026-09-30.** No hay oct–dic 2026 ni ventas 2024-07 a 2025-12 en las fuentes disponibles. La serie tiene un hueco de 18 meses.
4. **Hueco de nombres.** 28 SKUs de 2026 (Bs 4,06 M) no existen en el maestro legacy; 4 de ellos explican Bs 3,02 M.
5. **Cobertura del crosswalk.** 96,05% del importe del Q1 2022 está vinculado; Bs 916 mil quedan fuera, mayormente presentaciones de caja/pallet.
6. **2024 parcial.** El archivo de junio 2024 tiene 5.954 líneas contra ~75.000 normales; 2024 solo se usa como referencia de domingos, no como período completo.
7. **"Centro" = Casa Matriz** es una identificación por nombres de almacén, no por un código llamado Centro.
8. **Un solo canal de datos para 2026.** Foundation cubre solo documentos en BS y facturas activas; no incluye notas de crédito en la venta.

---

## 5. Qué haría falta para cerrar

1. **Maestro SAP actual** (o un export de `OITM` con `ItemCode`, `ItemName`, `U_codactive`) para nombrar los 28 SKUs y cerrar el 14,6% sin nombre.
2. **Deflactor IPC Bolivia 2022–2026** para separar inflación de precio real. Sin eso, el "+50% de precio" no se puede atribuir.
3. **Ventas 2024-07 a 2025-12** (o un backup SAP de ese período) para confirmar si el salto fue gradual o un escalón.
4. **Clasificación histórica por período** si se quiere comparar "terminados" con el criterio de cada año.
5. **Confirmación del negocio** de que "Centro" es Casa Matriz. La evidencia documental es fuerte pero no hay código con ese nombre.

---

## 6. Reproducibilidad

Los scripts y artefactos están en esta misma carpeta:

- `datos_clave.json`: todos los números citados, con períodos y fuentes.
- `comparacion_skus_lab_finished.csv`: 404 SKUs de terminados, 2022 vs 2026.
- `domingos_feriados_2026.csv`: detalle fecha por fecha y salón.
- `feriados_bolivia.csv`: calendario 2022–2026 usado.
- `scripts/`: extracción, crosswalk, cobertura, productos, sucesiones, cheques, notas de crédito, métricas finales, domingos y armado de evidencia.

Ejecución (desde un entorno con DuckDB y acceso read-only a las fuentes):

```bash
cd data/reports/telchi/facturacion-terminados-y-domingos-2022-2026-v1/scripts
python extract.py && python crosswalk.py && python coverage.py
python products.py && python successions.py && python checks.py && python credits.py
python final_metrics.py && python sundays.py && python branch_summary.py && python evidence.py
```

Los scripts escriben en `/tmp/opencode/telchi-hist/out/` y en esta carpeta; **no escriben en las fuentes**.

---

## Anexo: confianza por afirmación

| Afirmación | Confianza | Base |
| --- | --- | --- |
| Terminados se duplicó (94%–101%) | ALTA | Dos sistemas, 9 meses equivalentes, patrón mensual consistente |
| 70% precio / 30% volumen en SKUs comunes | MEDIA-ALTA | Descomposición exacta; nominal, sin deflactor |
| Minoxitel es el nuevo N°1 | ALTA | Importe y nombre en maestro |
| 28 SKUs sin nombre (14,6%) | ALTA (hecho) | No hay fuente de nombres disponible |
| 2A lidera domingos por facturación | ALTA | 35 domingos, 4 años de serie |
| CM lidera domingos por tickets | ALTA | Mismo corte |
| "Centro" = Casa Matriz | ALTA, no certera | Nombres de almacén, sin código "Centro" |
| Feriados venden menos que un día hábil | ALTA | 6 feriados 2026 y serie 2022–2024 |
