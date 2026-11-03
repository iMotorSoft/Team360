# Informe A — ¿Telchi vende más productos propios terminados en 2026 que en 2022?

**Volumen físico, enero–septiembre 2022 vs enero–septiembre 2026.**
Investigación read-only sobre los extractos Parquet ya auditados. Rama `feature/console-backend-core`. Corte de datos: **2026-09-30**. Fecha: 2026-10-22.

Complementa —y en tres puntos corrige— el informe original `report.md`. No lo modifica. No hubo ingesta, escritura en Data Lake, commit ni push.

---

## Respuesta directa

**Depende de la magnitud física, y esa es la conclusión central:**

| Dimensión | ene–sep 2022 | ene–sep 2026 | Variación | Lectura |
| --- | ---: | ---: | ---: | --- |
| **Litros** (bruto) | 439.634 | 345.958 | **−21,3%** | Cae por la licitación de alcohol 2022 |
| **Litros** (sin licitación) | 336.634 | 345.958 | **+2,8%** | Prácticamente plano |
| **Litros** (familias presentes ambos años, sin licitación) | 336.476 | 336.379 | **0,0%** | Ni más ni menos litros |
| **Kilogramos** | 20.537 | 31.467 | **+53,2%** | Sí vende más masa |
| **Dosis** (cápsulas, tabletas, sobres) | 159.371 | 1.417.613 | **+789,5%** | Categorías nuevas, no comparables 1:1 |
| **Unidades de presentación** | 4.062 | 762 | **−81,2%** | No es métrica de crecimiento: cambiaron los formatos |

**Veredicto:** Telchi **no vende más litros** de productos propios terminados que en 2022; vende **casi exactamente los mismos** una vez neutralizada la licitación de alcohol. Sí vende **más kilogramos** (+53%) y **muchas más dosis** (+790%), impulsado por líneas nuevas (citrato de magnesio, glucotel, carbonato de litio, colágeno premium).

**La facturación se duplicó, pero eso no prueba más volumen.** La venta nominal pasó de **Bs 13,37 M a Bs 27,45 M (+105,3%)**; sin la licitación 2022, **+124,5%**. En los SKUs comunes el importe sube **+70,4%** mientras los litros bajan **−1,6%**: el aumento es precio y mix, no litros.

**Tres correcciones al informe original:**

1. **El SKU de Bs 1,48 M sin nombre es colágeno:** `L03402` = COLÁGENO HIDROLIZADO GRANULADO PREMIUM SABOR ACAÍ x 300 g.
2. **El colágeno no “se consolidó, no creció”:** en kg creció **+31,5%** (4.092 → 5.383 kg) y en importe **+77,4%** (Bs 1,68 M → 2,98 M).
3. **El “30% del crecimiento por volumen” del informe original es volumen en bolivianos a precios de 2022, no volumen físico:** ese “volumen” es principalmente kg y dosis; en litros el volumen es plano.

---

## 1. Método

### 1.1 Universo

- **Producto terminado propio:** `product_business_type = LAB_FINISHED_PRODUCT` (404 SKUs en el período), clasificación **actual aplicada retroactivamente**.
- **Se excluyen** 45 SKUs no comerciales: combos, kits, botiquines, cápsulas vacías, material de laboratorio y preparados magistrales. Aportan Bs 0,46 M en 2026 (casi todo en la dimensión “presentación”).
- **Los 7 SKUs sin conversión posible** (combos/kits sin tamaño en el nombre ni UoM de base) son todos no comerciales; **no queda importe comercial sin convertir**.
- **No se incluye** `FRACTIONATED_PRODUCT` (químicos a granel: alcohol en bidón, bicarbonato, cloro, agua oxigenada). Es otra línea de negocio y otra pregunta; el informe original la mide aparte (Bs 16,81 M → 24,00 M, +42,8%).
- **Períodos:** 1 ene–30 sep de cada año. 2022 combina legacy (ene–5 abr) y SAP B1 real (6 abr–30 sep); 2026 usa Foundation. Es el mismo empalme auditado del informe original.

### 1.2 Cómo se pasa de cantidad a volumen físico

Para cada SKU se eligió **un factor de conversión por ítem**, en este orden de prioridad:

1. **UoM de inventario SAP** cuando ya es una unidad de base (`LT`, `ML`, `KG`, `GR`, `CAPS`, `COMP`, `TAB`, `SOB`). Tiene prioridad sobre el texto del nombre.
2. **Caja/pallet** (`CJA`, `JUEGO`, `PQTE`): tamaño del nombre × `ProductUC`.
3. **Tamaño declarado en el nombre** (`x 1 L`, `x 500 mL`, `x 300 g`, `x 100 cápsulas`).
4. **Unidad cruda** si el nombre no declara tamaño pero la UoM sí es de base.

Cada factor se validó con una **banda amplia de precio implausible** (Bs por litro, kg o dosis) usando los importes de ambos años. Resultado: **0 SKUs con precio implausible**, 4 SKUs fuera del rango 0,5–3,0× (todos Tintura de Yodo, con alza real de precio 3,0–3,9×). El detalle queda en `volumen_datos_clave.json → checks`.

Las magnitudes **nunca se suman entre sí**. Litros, kg, dosis y presentaciones se reportan en columnas separadas.

### 1.3 Crosswalk y nombres

- Se reutiliza el crosswalk auditado `productSB1.u_codactive = código legacy` (no similitud de texto). **67 códigos legacy mapean 1:N** y se mantienen separados.
- Los nombres 2026 provienen del dataset de referencia `v2_reference_closure_687bb2e9c034dc59` (SAP_HANA). Esto cierra el hueco de “28 SKUs sin nombre” del informe original.
- Los renombres `PREPARADO MAGISTRAL - NNNN` se tratan como el mismo ítem, usando el nombre legacy para leer el tamaño.

---

## 2. Resultado por dimensión

### 2.1 Litros: el efecto licitación lo explica todo

| Escenario | 2022 | 2026 | Variación |
| --- | ---: | ---: | ---: |
| Bruto | 439.634 | 345.958 | −21,3% |
| Sin licitación `L02924` (103.000 L) | 336.634 | 345.958 | **+2,8%** |
| Familias presentes ambos años, sin licitación | 336.476 | 336.379 | **0,0%** |
| Familias nuevas (no existían en 2022) | 0 | 9.580 | — |

La licitación `L02924` (103.000 L de alcohol 70% a SOLUTESA/DISPROMED, Bs 1.142.400, jun–ago 2022) es venta real pero **no recurrente**. Sin ella, los litros son planos. Las familias que ya existían en 2022 vendieron **exactamente el mismo volumen** en 2026; todo el crecimiento líquido proviene de familias nuevas (+9.580 L, +2,8%).

La suma cierra: 336.379 L de familias que sobreviven + 9.580 L de familias nuevas = 345.959 L. La base 2022 comparable es 336.476 L porque se excluyen **158 L de familias que desaparecieron por completo** (no solo SKUs, la familia entera).

### 2.2 Kilogramos: crecimiento real y concentrado

- **+53,2%** (20.537 → 31.467 kg).
- Familias comparables: **+41,6%** (20.287 → 28.718 kg).
- Familias nuevas: **+2.749 kg**.
- Explicado por **colágeno** (+1.291 kg), **Calentá** (+5.255 kg), **Pasta de Agua** (+2.195 kg), **Talco** (+1.835 kg) y **Nitrofuratel** (+1.212 kg). Compensado en parte por **Penicilina** (−1.625 kg) y **Celina** (−886 kg).

### 2.3 Dosis: categorías nuevas, no crecimiento de lo mismo

- **+789,5%** (159.371 → 1.417.613 dosis).
- **99,9% del volumen 2026 es de SKUs nuevos:** citrato de magnesio (1.159.800 cápsulas), glucotel (59.556 sobres), carbonato de litio en frascos (99.780 cápsulas), alcanfor tableta (98.469).
- Las familias comparables crecen **+24,4%** (159.371 → 198.257), sobre todo por **alcanfor** (+57,8%) y **carbonato de litio** (+2,9%, con migración de código).
- **Advertencia:** en 2022 el carbonato de litio se vendía **por cápsula suelta**; en 2026 se vende en **frascos de 30 y 90 cápsulas**. La dimensión dosis es comparable; la de “envases” no.

### 2.4 Presentaciones: no usar como métrica de crecimiento

Solo 4 SKUs comerciales quedan en esta dimensión (lacas, papel tornasol y un preparado magistral mal escrito en el maestro). Pasan de 4.062 a 762 unidades (−81,2%) y **no representan la evolución comercial**. Se reportan por completitud, no como evidencia.

---

## 3. Catálogo: qué había, qué hay y qué desapareció

La tabla usa el **universo comercial** (sin combos, botiquines ni magistrales). El catálogo LAB completo tiene 404 SKUs: 247 comunes, 92 nuevos y 65 discontinuados; al excluir los 45 no comerciales quedan **223 comunes, 83 nuevos y 53 discontinuados**.

| Grupo | SKUs | Litros 2022 → 2026 | kg 2022 → 2026 | Dosis 2022 → 2026 | Bs 2022 → 2026 |
| --- | ---: | ---: | ---: | ---: | ---: |
| **Comunes** | 223 | 325.095 → 319.762 (−1,6%) | 17.374 → 23.344 (+34,4%) | 159.371 → 1.308 (−99,2%)* | 10,74 M → 18,31 M (+70,4%) |
| **Nuevos 2026** | 83 | 0 → 26.197 | 0 → 8.122 | 0 → 1.416.305 | 0 → 9,14 M |
| **Discontinuados** | 53 | 11.539 → 0 | 3.163 → 0 | 0 → 0 | 1,48 M → 0 |
| **Total comercial** | 359 | 336.634 → 345.958 (+2,8%) | 20.537 → 31.467 (+53,2%) | 159.371 → 1.417.613 (+789,5%) | 12,22 M → 27,45 M (+124,5%) |

\* La caída de dosis en SKUs comunes es un **artefacto de sucesión de códigos**: el carbonato de litio y el alcanfor viejos se reemplazaron por códigos nuevos. La vista por familia lo corrige (sección 6).

**Lectura de cartera:**

- **60,0% del aumento de facturación** (ex-licitación) viene de SKUs nuevos: **Bs 9,14 M**.
- Los SKUs comunes aportan **Bs 7,57 M (+70,4%)**, pero con litros planos y kg +34%.
- Los discontinuados restan **Bs 1,48 M** en la base 2022.
- El catálogo **no se podó**: pasó de 190 a 206 SKUs con venta en litros y de 79 a 86 en kg. Hay más variedad, no menos.

---

## 4. Los SKUs comunes: más facturación, mismos litros

| Dimensión | Volumen 2022 | Volumen 2026 | Var. volumen | Bs 2022 | Bs 2026 | Var. importe | Bs/unidad 2022 → 2026 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Litros | 325.095 | 319.762 | **−1,6%** | 7,34 M | 13,12 M | +78,8% | 22,57 → 41,03 (**+81,8%**) |
| kg | 17.374 | 23.344 | +34,4% | 3,01 M | 5,14 M | +70,6% | 173,37 → 220,18 (+27,0%) |
| Dosis | 159.371 | 1.308 | −99,2%* | 0,22 M | 0,003 M | −98,8%* | — |
| Presentación | 4.062 | 762 | −81,2% | 0,18 M | 0,05 M | −73,6% | 43,45 → 61,15 (+40,7%) |

\* Sucesión de códigos, no desaparición del producto. Ver sección 6.

**Esto es lo que el informe original no podía ver:** en los mismos SKUs, el importe por litro subió **+81,8%**. El crecimiento en bolivianos de los productos que ya existían es **precio**, no litros. El volumen físico que sí crece en SKUs comunes son los **kg** (+34,4%), no los litros.

---

## 5. Productos que explican los movimientos

### 5.1 Litros — los que más suben

| SKU | Producto | 2022 (L) | 2026 (L) | Δ L | Bs 2026 |
| --- | --- | ---: | ---: | ---: | ---: |
| L01612 | Povidine 10% x 1 L | 11.426 | 23.647 | **+12.221** | 1.663.158 |
| L02024 | Alcohol 70% con atomizador x 500 mL | 3.560 | 15.613 | **+12.053** | 272.052 |
| L01003 | Alcohol 70% x 120 mL | 2.581 | 14.372 | **+11.791** | 365.683 |
| L02837 | Alcohol 70% con atomizador x 100 mL | 1.338 | 10.522 | **+9.183** | 390.436 |
| L01613 | Povidine 10% x 120 mL | 4.395 | 13.340 | **+8.945** | 1.167.685 |
| L01445 | Gel acuoso bidón x 5 L | 4.790 | 12.120 | **+7.330** | 263.303 |
| L03594 | Creolina x 20 L (nuevo) | 0 | 3.400 | +3.400 | 143.890 |

### 5.2 Litros — los que más caen

| SKU | Producto | 2022 (L) | 2026 (L) | Δ L |
| --- | --- | ---: | ---: | ---: |
| L02924 | Alcohol 70% x 1 L — licitación | 103.000 | 0 | **−103.000** |
| L01001 | Alcohol 70% x 1 L | 119.198 | 64.680 | **−54.518** |
| L00061 | Alcohol en gel neutro x 1 L | 13.488 | 6.229 | −7.259 |
| L01079 | Creolina Turril x 200 L | 14.945 | 8.010 | −6.935 |
| L01004 | Alcohol 70% x 10 L | 17.820 | 13.770 | −4.050 |
| L01622 | Tintura de Yodo x 1 L | 4.645 | 1.856 | −2.789 |

La caída de litros de alcohol **no es caída de unidades**: la familia pasó de 226.627 a 386.420 envases (+70,5%) porque migró a formatos de 100–500 mL.

### 5.3 Kilogramos — los que más suben

| SKU | Producto | 2022 (kg) | 2026 (kg) | Δ kg | Bs 2026 |
| --- | --- | ---: | ---: | ---: | ---: |
| L02822 | Calentá 250 g | 1.173 | 3.446 | **+2.273** | 555.456 |
| L03402 | Colágeno Premium Acaí 300 g (nuevo) | 0 | 2.044 | **+2.044** | 1.480.362 |
| L01643 | Pasta de Agua 50 g | 1.659 | 3.585 | **+1.926** | 486.539 |
| L02823 | Calentá 30 g | 80 | 1.611 | +1.530 | 369.510 |
| L03658 | Calentá Forte 250 g (nuevo) | 0 | 1.334 | +1.334 | 293.284 |
| L03258 | Glucotel manzana 300 g (nuevo) | 0 | 1.255 | +1.255 | 253.456 |

### 5.4 Kilogramos — los que más caen

| SKU | Producto | 2022 (kg) | 2026 (kg) | Δ kg |
| --- | --- | ---: | ---: | ---: |
| L01648 | Pomada Penicilina 16 g | 1.840 | 276 | **−1.564** |
| L01966 | Colágeno neutro 300 g (discontinuado) | 786 | 0 | −786 |
| L00057 | Celina crema de parafina 250 g | 1.285 | 618 | −667 |
| L00073 | Bronceador de Urucú 200 g (discontinuado) | 578 | 0 | −578 |
| L01963 | Colágeno frambuesa 300 g (discontinuado) | 557 | 0 | −557 |

### 5.5 Dosis — los que más suben

| SKU | Producto | 2026 (dosis) | Bs 2026 |
| --- | --- | ---: | ---: |
| L03612 | Citrato de Magnesio 400 mg x 100 cápsulas (nuevo) | **1.159.800** | 1.020.614 |
| L03600 | Alcanfor USP Telchi x 100 tabletas (nuevo) | 82.319 | 153.589 |
| L03506 | Carbonato de Litio Telchi 300 mg x 90 cápsulas (nuevo) | 67.770 | 181.586 |
| L03255 | Glucotel manzana sobre 10 g (nuevo) | 41.037 | 145.603 |
| L03504 | Carbonato de Litio Telchi 300 mg x 30 cápsulas (nuevo) | 32.010 | 86.310 |

---

## 6. Familias: sucesiones y migraciones de presentación

La comparación por código **castiga injustamente** a los productos que cambiaron de código. La vista por familia agrupa marca + producto e ignora presentación y sabor. Es la lente primaria para decidir si hay más o menos producto.

| Familia | Dim. | 2022 | 2026 | Var. | Comentario |
| --- | --- | ---: | ---: | ---: | --- |
| Povidine | L | 21.927 | 45.925 | **+109,4%** | Crece en 1 L y 120 mL |
| Alcohol 70% (sin licitación) | L | 196.658 | 157.745 | **−19,8%** | Menos litros, +70,5% envases |
| Colágeno | kg | 4.092 | 5.383 | **+31,5%** | Incluye L03402 |
| Minoxitel | L | 373 | 3.081 | **+725,9%** | Sucesión de códigos 5%/3% |
| Calentá | kg | 1.503 | 6.758 | **+349,6%** | Nuevos tamaños 30 g y Forte |
| Creolina | L | 58.541 | 50.056 | −14,5% | Menos bidones, más 20 L |
| Esencias | L | 23.659 | 29.731 | +25,7% | Recupera con formato 10 L |
| Geles | L | 4.859 | 13.124 | **+170,1%** | Bidón 5 L |
| Clorexitel | L | 420 | 7.928 | **+1.786,5%** | Casi todo nuevo |
| Aceite de Coco | L | 3.540 | 6.386 | +80,4% | Nuevo 250 mL |
| Pasta de Agua | kg | 2.001 | 4.196 | **+109,6%** | 50 g |
| Talco | kg | 2.884 | 4.719 | +63,6% | 100 g |
| Nitrofuratel | kg | 1.867 | 3.079 | +64,9% | 500 g |
| Aguas medicinales | L | 1.111 | 2.624 | +136,1% | Agua oxigenada |
| Tintura de Yodo / Lugol | L | 6.746 | 4.782 | −29,1% | Precio 3× |
| Celina | kg | 2.666 | 1.780 | −33,2% | Pierde surtido |
| Penicilina | kg | 1.958 | 333 | −83,0% | Cae fuerte |
| Citrato de Magnesio | dose | 0 | 1.159.800 | nuevo | Categoría nueva |
| Glucotel | dose | 0 | 59.556 | nuevo | Categoría nueva |
| Carbonato de Litio | dose | 96.955 | 99.788 | +2,9% | Migra de cápsula suelta a frasco |
| Alcanfor | dose | 62.416 | 98.469 | +57,8% | Migra a “USP Telchi” |

### 6.1 Migraciones de presentación detectadas

Tamaño promedio ponderado por volumen vendido (litros o kg por envase). Es la forma correcta de detectar un cambio de formato sin confundirlo con crecimiento.

| Familia | Tamaños 2022 | Tamaños 2026 | Tamaño prom. 2022 → 2026 | Var. tamaño | Var. volumen |
| --- | --- | --- | ---: | ---: | ---: |
| Alcohol 70% | 10 mL a 10 L | 60 mL a 10 L (salen 10, 250 y 450 mL) | 0,868 → 0,408 L | **−53,0%** | −19,8%* |
| Povidine | 120 mL, 1 L, 5 L | + 60 mL | 0,362 → 0,286 L | −21,0% | +109,4% |
| Geles | 5 L | + formatos menores | 4,433 → 2,961 L | −33,2% | +170,1% |
| Clorexitel | 120 mL, 1 L | + 5 L | 0,874 → 0,591 L | −32,3% | +1.786,5% |
| Calentá | 30, 50, 250 g | 30, 250 g (sale 50 g) | 0,122 → 0,079 kg | −34,6% | +349,6% |
| Aceite de Coco | 500 mL, 1 L | + 250 mL | 0,663 → 0,503 L | −24,1% | +80,4% |
| Nitrofuratel | 500 g | + 70 y 250 g | 0,500 → 0,340 kg | −32,0% | +64,9% |
| Creolina | 120 mL a 10 L | + 20 y 30 L | 1,084 → 0,989 L | −8,8% | −14,5% |
| Esencias | 30 mL a 1 L | + 10 L | 0,459 → 0,509 L | +11,1% | +25,7% |
| Minoxitel | 100 mL | 100 mL | 0,100 → 0,100 L | 0,0% | +725,9% |
| Colágeno | 300 g | + 400 g | 0,300 → 0,305 kg | +1,5% | +31,5% |

\* Sin licitación.

**Consecuencia metodológica:** cuando una familia migra a formatos pequeños, los **litros** pueden caer mientras los **envases** suben. Alcohol es el caso extremo: −19,8% de litros y +70,5% de envases. Por eso la conclusión “vende menos alcohol” en litros es cierta, pero “vende menos veces alcohol” es falsa.

### 6.2 Sucesiones que la vista por código no captura

| Producto | Código 2022 | Código 2026 | Efecto en la vista por código |
| --- | --- | --- | --- |
| Carbonato de Litio | `L01584` (cápsula suelta, 96.955) | `L03504` (30 caps), `L03506` (90 caps) | Parece −99,99%; en dosis es +2,9% |
| Alcanfor | `L01671` (100 tab), `L01886` (25 tab) | `L03599` (25 tab), `L03600` (100 tab) | Parece caída; en dosis es +57,8% |
| Minoxitel 5% | `L02033` | `L03281` | Parece discontinuado; la familia crece +726% |
| Minoxitel 3% | `L02923` | `L03283` | Igual |
| Colágeno | `L01963/64/65/66` (sabores) | `L03402` (premium acaí) | La familia crece; los códigos viejos desaparecen |

---

## 7. Precio, mix y presentación

| Concepto | 2022 | 2026 | Variación |
| --- | ---: | ---: | ---: |
| Facturación comercial | Bs 13,37 M | Bs 27,45 M | **+105,3%** |
| Facturación sin licitación | Bs 12,22 M | Bs 27,45 M | **+124,5%** |
| Bs por litro | 20,79 | 51,10 | **+145,8%** |
| Bs por kg | 186,65 | 254,99 | +36,6% |
| Bs por dosis | 1,36 | 1,20 | −12,1% |
| Bs por litro, solo SKUs comunes | 22,57 | 41,03 | **+81,8%** |

Tres fuerzas, en orden de importancia:

1. **Precio:** el litro vale 2,46 veces más que en 2022. Explica por sí solo más que el aumento de facturación total.
2. **Mix hacia productos de mayor valor por litro:** Povidine (Bs 76/L) y Minoxitel ganan peso; alcohol (Bs 20/L) lo pierde. Eso sube el ingreso por litro sin subir litros.
3. **Volumen físico real:** solo en kg (+53%) y dosis (+790%). En litros, plano.

No hay deflactor IPC en la fuente, así que **no se afirma crecimiento real**: se afirma que el volumen físico de litros no creció y que el de kg/dosis sí.

---

## 8. Conciliación con el informe original

| Afirmación original | Estado | Corrección con volumen físico |
| --- | --- | --- |
| “Facturación de terminados +100,7% (Bs 13,90 M → 27,91 M)” | Correcta en importe | Se confirma; la base comercial depurada da +105,3% (Bs 13,37 M → 27,45 M) |
| “70% precio / 30% volumen en SKUs comunes” | Correcta en Bs a precios 2022 | El “volumen” es kg/dosis; **en litros el volumen cae −1,6%** |
| “El colágeno se consolidó, no creció” | **Incorrecta en volumen físico** | kg +31,5%; importe +77,4%; `L03402` es colágeno premium |
| “28 SKUs sin nombre (14,6%)” | **Resuelta** | Los nombres se obtuvieron del dataset de referencia; `L03402`, `L03612` y `L03658` quedan identificados |
| “92 nuevos / 65 discontinuados” | Correcta | En el universo comercial son 83 y 53; la diferencia son SKUs no comerciales |
| “La licitación de alcohol no se repitió” | Correcta | 103.000 L y Bs 1,14 M; sin ella los litros son +2,8%, no −21,3% |

---

## 9. Límites

1. **Litros planos no significa estancamiento comercial:** la empresa vende más SKUs, más envases pequeños y más kg/dosis. La métrica de litros favorece a los productos a granel y castiga el cambio a formatos pequeños.
2. **Dosis no es comparable 1:1 entre años:** en 2022 parte del carbonato de litio se vendía por cápsula suelta y en 2026 por frasco. La dimensión dosis normaliza el contenido, pero el “envase” cambia.
3. **Clasificación actual aplicada a 2022:** no hay clasificación histórica por período. Un SKU pudo cambiar de uso.
4. **Excluye fraccionados:** la conclusión es sobre `LAB_FINISHED_PRODUCT`, no sobre toda la producción propia. Fraccionados (químicos a granel) crecieron +42,8% en Bs según el informe original y no se midieron aquí en volumen.
5. **Sin deflactor:** todo es nominal. No se afirma crecimiento real ni margen.
6. **4 SKUs con precio 3–3,9×** (Tintura de Yodo): el factor de conversión es correcto (1 L → 1 L), pero el salto de precio es atípico y conviene validarlo con lista de precios.
7. **Corte 2026-09-30:** no hay octubre–diciembre 2026.

---

## 10. Reproducibilidad

| Archivo | Contenido |
| --- | --- |
| `scripts/volume_2022_2026.py` | Pipeline completo: extracción, factores, familias, agregados |
| `volumen_skus_2022_vs_2026.csv` | 404 SKUs con q22/q26, factor, volumen, importe y precio unitario |
| `volumen_familias_2022_vs_2026.csv` | Agregado por familia y dimensión |
| `volumen_migraciones_presentacion.csv` | Tamaños detectados por familia |
| `volumen_factores.csv` / `volumen_factores_todos.csv` | Mapas de conversión reutilizables |
| `volumen_datos_clave.json` | Todos los números citados, descomposiciones y checks |

Ejecución (desde `SrvRestAstroLS_v1/backend`):

```bash
uv run python ../../data/reports/telchi/facturacion-terminados-y-domingos-2022-2026-v1/scripts/volume_2022_2026.py
```

El script es idempotente y no escribe fuera de esta carpeta ni de `/tmp/opencode/telchi-hist`.
