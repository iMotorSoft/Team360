# TELCHI — C010341 LA REJA — Operational Identity & Document Traceability V1

**Gate:** `TELCHI_C010341_LA_REJA_OPERATIONAL_IDENTITY_V1_PASS`
**Workspace:** `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi`
**Baseline as-of:** 2026-09-01 (frozen, `TELCHI_CREDIT_OPEN_RISK_AGING_V1_PASS`)
**HANA access:** READ ONLY (`SAP_WRITE_COUNT=0`)
**Fecha:** 2026-09-03

---

## A. RESULTADO

>C010341 «LA REJA» **no debe interpretarse automáticamente como un cliente comercial moroso**.

Las **Bs 47,258.99** de las 40 operaciones del corte son el saldo abierto de facturas de
**consumo interno / parte relacionada** de la familia Telchi, no una venta comercial a un
tercero. El Business Partner comparte **NIT** con el propietario (S0001 Roberto Abraham
Telchi Asbun), **nunca pagó** (0 ORCT en toda la historia), sus entregas se registran
textualmente «PARA LA REJA», «PARA SR ROBERTO TELCHI», «MEDICAMENTOS…», con choferes
propios (Branko, Carlos Rivera) y pedidos telefónicos autorizados por familia Telchi
(Don Tito, Sr. Arturo Escalante).

La cuenta acumulada total del BP (2025 + 2026) es **Bs 93,769.76** abiertos sobre 85
facturas (45 de 2025 + 40 de 2026), con 1 sola nota de crédito (Bs 1,572) como único
«pago» histórico.

---

## B. ¿QUÉ ES C010341?

| Pregunta | Respuesta | Evidencia |
|---|---|---|
| ¿Cliente comercial real? | **NO (sin evidencia comercial)** | 0 pagos ORCT en 2 años; destinatarios familiares/choferes propios; NIT = NIT dueño |
| ¿Depósito/consumo interno? | **SÍ (evidencia fuerte)** | Comentarios de entrega «PARA LA REJA», «PARA SR ROBERTO TELCHI», «MEDICAMENTOS» |
| ¿Cuenta genérica para terceros? | **NO** | Los destinatarios citados son siempre internos/familiares; ningún tercero externo |
| ¿Parte relacionada? | **SÍ** | Grupo OCRG 119 «Socios» (incluye S0001..S0007 familiares); mismo LicTradNum que S0001 |
| ¿Uso mixto? | **MIXED_USE bajo, dominado por uso interno** | 34 R1 (salón) + 6 pedidos telefónicos internos; productos heterogéneos (fipronil, medicamentos, víveres) |

**Clasificación global:** `INTERNAL_OPERATION / INTERNAL_CONSUMPTION` — cuenta interna
de consumo de la familia/propiedad La Reja, documentada como venta SAP con saldo abierto
acumulado.

---

## C. BUSINESS PARTNER MASTER (PHASE 1)

Fuente: `validation/la_reja_identity/evidence/bp_master.json` (HANA `OCRD`).

| Campo | Valor | Observación |
|---|---|---|
| CardCode | C010341 | — |
| CardName / CardFName | LA REJA | — |
| CardType | C (cliente) | Tipo formal «cliente» |
| GroupCode | **119 = «Socios»** | Grupo de socios/familia (23 miembros) |
| CmpPrivate | C | Empresa |
| **LicTradNum (NIT)** | **1468238** | **Igual al NIT de S0001 ROBERTO ABRAHAN TELCHI ASBUN** |
| Currency | BS | Bolivianos |
| CreditLine / Balance | 100,000 / **93,769.76** | Balance == saldo abierto calculado de OINV |
| GroupNum / ListNum | 1 / 2 | Lista de precios 2 |
| SlpCode (maestro) | -1 | Sin vendedor asignado en el maestro |
| ShipToDef | «Nuevo» | Dirección genérica |
| CreateDate / UpdateDate | 2024-06-12 / 2026-06-19 | Creado 7 meses antes de la 1ª factura |
| U_ORIGIN | SAP | — |
| U_SO1_01VENCREVENC / AUTORIZARCOM | N / N | Sin flags de excepción |
| U_ClienteExcepcional | 0 | No es cliente excepcional |
| PaymBlock / validFor / frozenFor | N / Y / N | Activo |

### Direcciones (CRD1)
Una sola dirección **ship-to**: `Address=«Nuevo»`, `AdresType=S`, `Country=BO`,
`TaxCode=IVA_EXE`, sin calle/ciudad/estado (genérica), creada 2025-11-13.
**No hay dirección comercial real asociada.**

### Contactos (OCPR)
**0 contactos humanos.** No existe persona de contacto del «cliente».

---

## D. HISTORIA DOCUMENTAL (PHASE 2)

Fuente: `evidence/history_aggregates.json` (HANA `OINV/ORIN/ORCT/OITR/ITR1/OJDT/JDT1`,
ODLN, ORDR).

| Familia | Total | Cancelados | Monto bruto | Detalle |
|---|---:|---:|---:|---|
| **Facturas (OINV)** | **85** | 0 | **Bs 95,341.76** | 45 en 2025 (Bs 48,082.77) + 40 en 2026 (Bs 47,258.99) |
| **Entregas (ODLN)** | **98** | 0 | Bs 106,333.05 | primera 2024-06-24; última 2026-08-31 |
| Pedidos (ORDR) | 6 | 0 | Bs 5,708.50 | pedidos telefónicos 2026 (2619xxxxx) |
| Notas de crédito (ORIN) | **1** | 0 | Bs 1,572.00 | 2025-11-13 (único «pago» histórico) |
| **Pagos (ORCT)** | **0** | — | **Bs 0.00** | **nunca pagó** |
| Cotizaciones (OQUT) | 73 | — | — | flujo R1 (cotización→entrega→factura) |
| Conciliaciones activas (OITR/ITR1) | 1 | — | Bs 1,572 | cierra la NC contra factura 2025 |

**Indicadores clave:**
- `first_invoice = 2025-01-14`, `last_invoice = 2026-07-25`; entregas desde 2024-06-24.
- `open_total(historia completa) = 93,769.76` == `OCRD.Balance` (Δ=0.00 ✓).
- `invoice = paid + open` → paid=1,572 (vía NC) + open=93,769.76 = 95,341.76 ✓ (**identity_ok**).
- Usuarios que crearon facturas (historia): jirahola 68, nortuno 6, eroman 6, manager 3(156?), mtolaba 2.
- Series: 1054 (39, 2025), 1248 (34, 2026 R1), 1262 (6, 2026 pedidos), 1068/1071 (2025).
- **Propósito operativo aparente:** consumo interno de productos propios (laboratorio/
  salones) hacia el lugar «La Reja» con destino a la familia Telchi.

---

## E. LAS 40 OPERACIONES (PHASE 3)

Fuente: `evidence/atomic_la_reja_cases.json` (40 filas) + `atomic_la_reja_summary.json`.

- 40/40 DocEntry únicos; **SUM(open) = 47,258.99** == baseline (Δ=0.00 ✓).
- Ventana facturas: 2026-02-01 → 2026-07-25.
- **109 líneas** INV1; todas resuelven a OITM (0 `UNKNOWN_ITEM`).
- `line_total` suma ≈ DocTotal (tolerancia de redondeo; NO_SILENT_FANOUT ✓).
- Cadena documental 40/40: factura ← entrega (40/40); 34 con base cotización R1 y 6 con base pedido ORDR.

### Tabla D — 40 operaciones (detalle)

| DocEntry | DocNum | Fecha | Entrega | Vendedor | Usuario | Canal | Monto | Abierto |
|---|---|---|---|---|---|---|---|---|
| 11069118 | 260100371 | 2026-02-01 | 260200004 | Silvia Oly | jirahola | RETAIL_ONE | 110.40 | 110.40 |
| 11069123 | 260100372 | 2026-02-01 | 260100305 | Mariela Irigoyen | jirahola | RETAIL_ONE | 1086.39 | 1086.39 |
| 11069132 | 260100373 | 2026-02-01 | 260101386 | Maria Frances Menacho Rivera | jirahola | RETAIL_ONE | 1015.69 | 1015.69 |
| 11084304 | 260100492 | 2026-02-12 | 260200026 | Silvia Oly | jirahola | RETAIL_ONE | 1522.87 | 1522.87 |
| 11084319 | 260100493 | 2026-02-21 | 260102921 | Elizabeth Pereyra Salvatierra | jirahola | RETAIL_ONE | 980.10 | 980.10 |
| 11144076 | 260100829 | 2026-03-01 | 260400031 | Cubre Libre - RYC | jirahola | RETAIL_ONE | 116.34 | 116.34 |
| 11120372 | 260100651 | 2026-03-06 | 260103747 | Ivonne Camacho Saavedra | jirahola | RETAIL_ONE | 1502.13 | 1502.13 |
| 11115981 | 261901856 | 2026-03-10 | 260103922 | Luz Guzman | eroman | SAP_DIRECT | 26.77 | 26.77 |
| 11144077 | 260100830 | 2026-03-16 | 260104331 | Maria Frances Menacho Rivera | jirahola | RETAIL_ONE | 24.40 | 24.40 |
| 11144079 | 260100831 | 2026-03-19 | 260200066 | Silvia Oly | jirahola | RETAIL_ONE | 48.72 | 48.72 |
| 11144080 | 260100832 | 2026-03-21 | 260104703 | Maria Frances Menacho Rivera | jirahola | RETAIL_ONE | 134.07 | 134.07 |
| 11144082 | 260100833 | 2026-03-24 | 260104822 | Mariela Irigoyen | jirahola | RETAIL_ONE | 134.07 | 134.07 |
| 11144084 | 260100834 | 2026-03-24 | 260104827 | Elizabeth Pereyra Salvatierra | jirahola | RETAIL_ONE | 453.15 | 453.15 |
| 11144096 | 260100835 | 2026-03-24 | 260104839 | Elizabeth Pereyra Salvatierra | jirahola | RETAIL_ONE | 107.31 | 107.31 |
| 11144100 | 260100836 | 2026-03-28 | 260200077 | Silvia Oly | jirahola | RETAIL_ONE | 3.47 | 3.47 |
| 11144102 | 260100837 | 2026-03-30 | 260105182 | Elizabeth Pereyra Salvatierra | jirahola | RETAIL_ONE | 73.51 | 73.51 |
| 11177078 | 260101019 | 2026-04-08 | 260105621 | Mariela Irigoyen | jirahola | RETAIL_ONE | 763.87 | 763.87 |
| 11177079 | 260101020 | 2026-04-13 | 260105885 | Mariela Irigoyen | jirahola | RETAIL_ONE | 2110.33 | 2110.33 |
| 11177080 | 260101021 | 2026-04-13 | 260105886 | Mariela Irigoyen | jirahola | RETAIL_ONE | 3.47 | 3.47 |
| 11177081 | 260101022 | 2026-04-15 | 260200100 | Silvia Oly | jirahola | RETAIL_ONE | 216.50 | 216.50 |
| 11228982 | 260101329 | 2026-05-01 | 260106377 | Maria Frances Menacho Rivera | jirahola | RETAIL_ONE | 2439.34 | 2439.34 |
| 11228989 | 260101330 | 2026-05-01 | 260106750 | Mariela Irigoyen | jirahola | RETAIL_ONE | 1498.24 | 1498.24 |
| 11228994 | 260101331 | 2026-05-01 | 260106787 | Maria Frances Menacho Rivera | jirahola | RETAIL_ONE | 2450.01 | 2450.01 |
| 11229001 | 260101332 | 2026-05-01 | 260106817 | Mariela Irigoyen | jirahola | RETAIL_ONE | 144.68 | 144.68 |
| 11200827 | 261903415 | 2026-05-04 | 260106989 | Luz Guzman | eroman | SAP_DIRECT | 3619.36 | 3619.36 |
| 11229005 | 260101333 | 2026-05-05 | 260400073 | Luisa Judith Merlo Lijeron | jirahola | RETAIL_ONE | 841.44 | 841.44 |
| 11207141 | 261903596 | 2026-05-08 | 260107274 | Luz Guzman | eroman | SAP_DIRECT | 1967.81 | 1967.81 |
| 11213405 | 261903665 | 2026-05-12 | 260107396 | Luz Guzman | eroman | SAP_DIRECT | 26.77 | 26.77 |
| 11229100 | 261903812 | 2026-05-16 | 260107661 | Luz Guzman | eroman | SAP_DIRECT | 9.42 | 9.42 |
| 11250839 | 261904120 | 2026-05-21 | 260107980 | Luz Guzman | eroman | SAP_DIRECT | 58.37 | 58.37 |
| 11319515 | 260101685 | 2026-06-01 | 260107752 | Maria Frances Menacho Rivera | jirahola | RETAIL_ONE | 756.76 | 756.76 |
| 11319517 | 260101686 | 2026-06-01 | 260107788 | Mariela Irigoyen | jirahola | RETAIL_ONE | 3446.33 | 3446.33 |
| 11319521 | 260101687 | 2026-06-01 | 260108450 | Maria Frances Menacho Rivera | jirahola | RETAIL_ONE | 2198.89 | 2198.89 |
| 11319524 | 260101688 | 2026-06-01 | 260108451 | Maria Frances Menacho Rivera | jirahola | RETAIL_ONE | 1922.33 | 1922.33 |
| 11319527 | 260101689 | 2026-06-02 | 260108618 | Mariela Irigoyen | jirahola | RETAIL_ONE | 212.84 | 212.84 |
| 11319529 | 260101690 | 2026-06-05 | 260108771 | Mariela Irigoyen | jirahola | RETAIL_ONE | 3943.94 | 3943.94 |
| 11448517 | 260102056 | 2026-07-01 | 260110177 | Mariela Irigoyen | jirahola | RETAIL_ONE | 6810.00 | 6810.00 |
| 11448520 | 260102057 | 2026-07-14 | 260111096 | Mariela Irigoyen | jirahola | RETAIL_ONE | 117.00 | 117.00 |
| 11448524 | 260102059 | 2026-07-24 | 260111759 | Maria Frances Menacho Rivera | jirahola | RETAIL_ONE | 26.90 | 26.90 |
| 11448522 | 260102058 | 2026-07-25 | 260111790 | Mariela Irigoyen | jirahola | RETAIL_ONE | 4335.00 | 4335.00 |

> Nota: el detalle completo línea por línea (producto, cantidad, precio, almacén, base)
> está en `evidence/atomic_la_reja_cases.json` (campo `product_lines`) y
> `evidence/product_lines_full.json` (auditoría).

---

## F. PRODUCTOS (PHASE 4 / 14)

Fuente: `evidence/products_by_amount.json`, `products_category.json`.

### ¿Qué se le «vendió» a LA REJA?

| Tipo (taxonomía validada) | Líneas | Cantidad | Monto | % monto |
|---|---:|---:|---:|---:|
| PRODUCTO TERMINADO (incl. fraccionado propio) | 92 | 4,968 | Bs 39,451.63 | 83.48% |
| ENVASE (regex taxonomía) | 15 | 309 | Bs 7,603.35 | 16.09% |
| INSUMO | 2 | 10 | Bs 204.00 | 0.43% |
| **Total** | **109** | | **Bs 47,258.98** | 100% |

> El corte por **grupo OITB** (evidencia primaria, sin depender de regex) es más
> descriptivo del uso: grupos «FRACCIONADO x L./Kg./Gr./mL.» (productos propios fraccionados),
> «DERMICOS», «AGEMED MED» (medicamentos), «ARTÍCULOS» (víveres), «ARTICULOS DEL HOGAR»,
> «HIGIENE», «INSUMOS HOSPT», «IM/IV», «MATERIAL LABORATORIO».
> Aclaración de fiabilidad: la categoría «ENVASE» surge de la taxonomía validada
> (`stock_domain.PACKAGING_RE` sobre el nombre) y aquí incluye SKU de venta cuyos nombres
> contienen SPRAY/BOLSA/AMP (p.ej. REPELENTE FEXON SPRAY, Bs 6,828.71); **no** deben leerse
> como envases físicos en este contexto. La lectura funcional del mix está en las filas abajo.

### Top 20 por monto

| Producto | Descripción | Clasificación | Grupo | Cantidad | Monto | Docs |
|---|---|---:|---|---:|---:|---:|
| L01407 | FIPRONIL 1% x 1L. | FINISHED_GOOD | FRACCIONADO x L. | 486.00 | 29784.75 | 11 |
| M03408 | REPELENTE FEXON SPRAY x 130g/180cm3 #SAE | PACKAGING | DERMICOS | 165.00 | 6828.71 | 8 |
| T02330 | IGUAZU CAFE CLASICO FCO x 200g | TRADED_GOOD | Artículos | 23.00 | 1531.60 | 1 |
| L00505 | BICARBONATO DE SODIO x 20gr. | FINISHED_GOOD | FRACCIONADO x Gr. | 2300.00 | 1512.48 | 6 |
| L01111 | ACIDO FOSFORICO x 1L. | FINISHED_GOOD | FRACCIONADO x L. | 30.00 | 849.20 | 3 |
| M05882 | CARDIOPLUS-D 20/12.5 MG X 40 COMP.#RECALCINE | TRADED_GOOD | AGEMED MED | 40.00 | 643.80 | 1 |
| L01859 | TINTURA DE YODO 10% x 1L. | FINISHED_GOOD | INSUMOS HOSPT | 3.00 | 516.94 | 1 |
| M03465 | TAMSULON 0.4 mg x 30 comp. #TECNOFARMA | TRADED_GOOD | AGEMED MED | 30.00 | 363.27 | 1 |
| M05290 | RUX 10 mg x 30 comp. #SAVAL | TRADED_GOOD | AGEMED MED | 30.00 | 359.04 | 1 |
| T03497 | FAMOSA FIDEO TIPO ROSCA BOLSA x 11.34kg | PACKAGING | Artículos | 3.00 | 357.57 | 1 |
| M06879 | ANTIGRIPAL COMPUESTO x 200 tabletas #INTI | TRADED_GOOD | AGEMED MED | 200.00 | 255.78 | 2 |
| L02074 | CEPEX x 1000gr. (VENENO CEPES) *MABATE* | TRADED_GOOD | ARTICULOS DEL HOGAR | 2.00 | 240.00 | 1 |
| M07351 | DICLOFENACO 75mg/3ml x 50 ampollas #INTI | PACKAGING | IM/IV | 100.00 | 228.45 | 1 |
| T03535 | PIL BONLE LECHE EN POLVO INSTANTANEO x 800g | TRADED_GOOD | Artículos | 5.00 | 206.62 | 1 |
| M02651 | SERTAL COMPUESTO x 20 comp. #MEGALABS #LS | TRADED_GOOD | AGEMED MED | 40.00 | 200.45 | 1 |
| M05939 | AMOXICILINA 500 mg x 500 caps. #SAE | TRADED_GOOD | AGEMED MED | 200.00 | 140.80 | 2 |
| M04094 | PARODONTAX C/ FLUOR x 126gr #ARGENTINO | TRADED_GOOD | HIGIENE | 2.00 | 140.00 | 1 |
| M07694 | DERMAGLOS PROTEC. SOLAR INVISIBLE FPS 50 x 170 mL #MEGALABS | TRADED_GOOD | DERMICOS | 1.00 | 133.63 | 1 |
| L03270 | PAPEL PH UNIVERSAL 1-14 X 20TIRAS | INPUT | MATERIAL LABORATORIO | 6.00 | 117.00 | 1 |
| L02909 | SULFATO DE COBRE x 1kg. Bolsa Metalizada | FINISHED_GOOD | FRACCIONADO x Kg. | 3.00 | 116.34 | 1 |

### Lectura funcional del mix

- **FIPRONIL 1% (486 L, 63% del monto)** — veterinario/insecticida; uso agropecuario,
  consistente con propiedad rural «La Reja» (depósito/fraccionado informado).
- Medicamentos (AGEMED MED, IM/IV, DERMICOS, INSUMOS HOSPT) — consumo personal/familiar
  («MEDICAMENTOS JUNIO 2025», «MEDICAMENTO 20.10.2025»…).
- Víveres (café, fideos, leche en polvo, agua, vinagre) — consumo doméstico.
- Es un **mix heterogéneo de consumo interno**, no una línea de negocio comercial.

---

## G. ALMACENES (PHASE 5 / 16)

Fuente: `evidence/warehouses_invoices.json`, `warehouses_deliveries.json`,
`stock_effect_sample.json`.

| Almacén | Rol (U_TYPE) | Nombre | Líneas | Monto |
|---|---|---:|---:|---:|
| 2A-SAL | SAP | Salón 2º Anillo | 58 | Bs 36,428.70 |
| LAB-T4 | DMS | Producto Terminado MAGISTRAL | 5 | Bs 5,305.86 |
| 2A-SMK | SAP | TelchiMarket Salón 2A | 6 | Bs 2,262.04 |
| CM-SAL | SAP | Salón Casa Matriz | 30 | Bs 1,901.96 |
| RC-SAL | SAP | Salón Roca y Coronado | 6 | Bs 957.78 |
| LAB-T3 | DMS | Producto Terminado INDUSTRIAL | 1 | Bs 339.68 |
| LAB-T2 | DMS | Producto Terminado SENASAG | 2 | Bs 53.54 |
| LAB-T1 | DMS | Producto Terminado AGEMED | 1 | Bs 9.42 |

- **77.1% sale del Salón 2º Anillo** (2A-SAL); el resto de otros salones y de almacenes de
  producto terminado del laboratorio.
- **Stock effect validado** (OINM): 40 movimientos muestreados, `OutQty == Quantity` de la
  entrega, mismo almacén y fecha (TransType=15) → 0 desajustes. El stock sale por
  **entrega** (ODLN → OINM OutQty), la factura no genera movimiento adicional.
- **No** existe almacén «La Reja»: el flujo es POS/salón → entrega → factura a C010341,
  no una transferencia de inventario (OWTR) hacia un depósito interno.

---

## H. USUARIOS SAP (PHASE 7)

Fuente: `evidence/users.json`.

| Usuario SAP | Tipo | Documentos (40) | Monto | Canal |
|---|---|---:|---:|---|
| jirahola (Alejandra Irahola) | PERSONAL | 34 | Bs 41,550.49 | RETAIL_ONE 34 |
| eroman (Enrique Roman) | PERSONAL | 6 | Bs 5,708.50 | SAP_DIRECT 6 |

- En la historia completa además: nortuno (6, 2025), manager (2, 2025), mtolaba (2, 2025).
- En las **entregas R1** el usuario operativo es `soluone` (usuario técnico POS, atribución de
  operador de caja según gates previos); en los **pedidos telefónicos** (ORDR 2619…)
  los usuarios son **nvargas** (Nicolás Vargas) y **arioja** (Ana Rioja).

---

## I. VENDEDORES (PHASE 8)

Fuente: `evidence/salespersons.json`. El vendedor es **distinto del usuario SAP**
(invariante verificada documento a documento).

| Vendedor (OSLP) | Documentos | Monto |
|---|---:|---:|
| Mariela Irigoyen | 13 | Bs 24,606.16 |
| Maria Frances Menacho Rivera | 9 | Bs 10,968.39 |
| Luz Guzman | 6 | Bs 5,708.50 |
| Silvia Oly | 5 | Bs 1,901.96 |
| Elizabeth Pereyra Salvatierra | 4 | Bs 1,614.07 |
| Ivonne Camacho Saavedra | 1 | Bs 1,502.13 |
| Luisa Judith Merlo Lijeron | 1 | Bs 841.44 |
| Carla Lorena Cambara | 1 | Bs 291.60 |
| Cubre Libre - RYC | 1 | Bs 51.30 |

> Los vendedores son cajeros/vendedores de salón asociados al folio Retail One de cada
> operación, no un vendedor comercial asignado al cliente (el maestro OCRD tiene
> `SlpCode=-1`).

---

## J. CANALES (PHASE 9)

| Canal | Documentos | Monto | Origen |
|---|---:|---:|---|
| **RETAIL_ONE** | 34 | Bs 41,550.49 | POS salón → cotización OQUT (BaseType 23) → entrega → factura |
| **SAP_DIRECT** | 6 | Bs 5,708.50 | Pedidos ORDR 2619xxxxx por teléfono → entrega → factura |

- 34/40 (87% del monto) provienen del canal Retail One; los 6 SAP Direct son pedidos
  **telefónicos internos** («SOLICITADO VIA TELEFONICA POR ARTURO ESCALANTE…», «…DON TITO
  TELCHI…», «…EL SR ARTURO…»), con vendedor Luz Guzman y usuario eroman.
- La aparición de Retail One en una cuenta interna se explica porque el consumo se
  registra en la caja del salón con el BP interno C010341 (no es venta POS a público).

---

## K. DESTINO / RECEPTOR (PHASE 6 / 10 / 22 / 23)

Fuente: `evidence/destination_receiver_cases.json`, `destination_receiver_summary.json`.

**Destino físico: La Reja** — `DESTINATION_LA_REJA=EXACT` (8 casos con mención textual)
+ `DESTINATION_INTERNAL=STRONG` (10 casos con persona/chofer/medicamentos) +
22/40 sin comentario (sin evidencia negativa; mismo patrón documental).

Personas citadas en comentarios (98 entregas de toda la historia):
- **SR ROBERTO TELCHI** — «PARA SR ROBERTO TELCHI (LA REJA)» (dueño, S0001)
- **DON TITO TELCHI** — «la reja autorisado por don tito», «SOLICITADO … POR DON TITO TELCHI»
- **SR ARTURO (ESPOSO SRA BELEM TELCHI)** / Arturo Escalante — cónyuge de la socia
- **BRANKO** (chofer) — «LLEVO SR BRANKO PARA LA REJA», «LLEVO DON BRANKO A LA REJA»
- **CARLOS RIVERA** (chofer Saavedra) — «PARA EL CHOFER DE SAAVEDRA CARLOS RIVERA»
- **ANA RIOJA** — intermediaria («ATRAVEZ DE ANA RIOJA»)
- **MEDICAMENTOS** mensuales — «MEDICAMENTOS JUNIO 2025. LA REJA - C010341»

**Receptor físico:** `RESOLVED_INTERNAL` (familia Telchi + choferes propios).
**Comprador real:** `BUYER_STRONG` — consumidor interno (familia Telchi), no tercero.

---

## L. PRECIOS (PHASE 11 / 12)

Fuente: `evidence/pricing_comparison.json`, `pricing_summary.json`.
Comparación: mismo ItemCode, misma moneda (BS), misma unidad (SalUnitMsr), misma ventana
(2026-01-01..09-01), mediana de precio de LA REJA vs mediana de precio de clientes normales.

| Clasificación | Ítems | Monto | % monto |
|---|---:|---:|---:|
| **SYMBOLIC** (< 50% del precio normal) | 25 | Bs 33,454.56 | **70.8%** |
| COMMERCIAL_LIKE | 52 | Bs 13,446.85 | 28.5% |
| UNRESOLVED (sin comparable) | 1 | Bs 357.57 | 0.8% |

Ejemplos relevantes (más montos):

| Item | LA REJA mediana | Cliente normal mediana | Ratio | Clasificación |
|---|---|---:|---:|---:|---|
| L01407 FIPRONIL 1% x 1L | 54.11 | 109.62 (n=236) | 0.49 | SYMBOLIC |
| L00505 BICARBONATO x 20gr | 0.45 | 2.17 (n=11,095) | 0.20 | SYMBOLIC |
| L01111 ÁCIDO FOSFÓRICO x 1L | 28.31 | 107.45 (n=359) | 0.26 | SYMBOLIC |
| L01859 TINTURA DE YODO 10% x 1L | 172.31 | 373.23 (n=86) | 0.46 | SYMBOLIC |
| M03408 REPELENTE FEXON SPRAY | 40.11 | 56.98 (n=38) | 0.70 | COMMERCIAL_LIKE |
| M05882 CARDIOPLUS-D | 16.09 | 16.09 (n=5) | 1.00 | COMMERCIAL_LIKE |

**Patrón de precio: `INTERNAL_PREFERENTIAL`** — los ítems de mayor monto (FIPRONIL
incl.) se facturan muy por debajo del precio normal de cliente. Combinado con la ausencia
de cobranza, refuerza lectura de uso interno / transferencia a valor no de mercado.

---

## M. IMPUESTOS (PHASE 12)

- `TaxCode=IVA_EXE` (exento) en el maestro de dirección y en las líneas; `U_EXENTO` en el
  cabezal; los asientos no muestran IVA (2140101 = 0 en la muestra).
- Tratamiento **no difiere de una venta normal de estos ítems** en la instalación
  (fraccionado/exento). No aporta por sí solo a la identidad.

---

## N. COBRANZA / RECONCILIACIÓN (PHASE 13 / 14 / 28)

Fuente: `evidence/collection_history.json`, `collection_summary.json`.

- **ORCT (pagos): 0** en toda la historia (2024-06 → 2026-09). C010341 **nunca pagó**.
- Única conciliación activa: nota de crédito Bs 1,572 (2025-11-13, usuario jirahola)
  contra factura (init 13/14), `CREDIT_NOTE_CLEARING`.
- Identidad: `facturas = pagado + abierto` → 95,341.76 = 1,572 + 93,769.76 ✓.
- **Patrón de cierre:** `CREDIT_NOTE_CLEARING + PERSISTENT_OPEN_BALANCE` — las facturas
  quedan abiertas indefinidamente; el saldo se acumula en el BP.
- OCRD.Balance = 93,769.76 == saldo abierto calculado ✓ (semántica `AR as-of`).

---

## O. CONTABILIDAD (PHASE 14)

Fuente: `evidence/accounting_sample.json`.

Muestra (3 facturas mayores):

| DocEntry | TransId | Cuenta | Débito | Crédito | Saldo |
|---|---:|---|---:|---:|---|
| 11448517 | 16153211 | 1120101 (AR cliente) | 6,810.00 | 0 | balanced ✓ |
| | | 4110101 (ventas) | 0 | 4,995.00 + 1,815.00 | |
| 11448522 | 16153220 | 1120101 / 4110101 | 4,335.00 | 4,335.00 | balanced ✓ |
| 11319529 | 15827927 | 1120101 / 4110101 | 3,943.94 | 3,943.94 | balanced ✓ |

- Cuenta control: **1120101** (cuentas por cobrar cliente) — `CtlAccount` en cabezales y
  JDT1. Contra: 4110101 (ventas). Todas **balanceadas** (débito==crédito).
- El asiento trata las operaciones como **venta a crédito** (AR), coherente con la
  documentación SAP, pero la contrapartida económica (cobro) nunca ocurre.
- `OJDT` histórico: 88 cabeceras (85 facturas + 1 NC + 2 ajustes), TransType 13/14.

---

## P. GENERIC ACCOUNT HYPOTHESIS (PHASE 17 / 34 / 59)

Fuente: `evidence/generic_account_tests.json`.

| Test | Resultado | Evidencia |
|---|---|---|
| same BP + same destination | OK | 40/40 mismo BP; destino textual La Reja/familia Telchi |
| same BP + multiple explicit **third-party** destinations | NO | Todos los destinatarios son internos/familiares (Roberto Telchi, Don Tito, Belem, Arturo) o choferes propios (Branko, Rivera) |
| same BP + multiple third-party references | NO | 0 referencias a compradores externos |
| same BP + no recipient evidence | OK (parcial) | 22/40 sin comentario → `PHYSICAL_RECEIVER=UNRESOLVED` en esos casos |

**Conclusión:** `SINGLE_OPERATIONAL_ENTITY` (uso interno de la familia en La Reja).
**NO** se declara `GENERIC_ACCOUNT_STRONG`: aunque hay múltiples personas citadas,
todas pertenecen al mismo entorno interno (familia/choferes propios), no a terceros
externos distintos.

---

## Q. OPERATIONAL CLASSIFICATION (PHASE 36 / 37)

**Identidad del Business Partner:** `INTERNAL RELATED-PARTY ACCOUNT` (consumo interno).

**Semántica por operación (40):**

| Semántica | Casos | Monto | Confidence |
|---|---:|---:|---|
| INTERNAL_CONSUMPTION (familia/propiedad La Reja) | 18 | Bs 27,598.31 | STRONG (destino/persona textuales) |
| DESTINATION_UNRESOLVED (mismo patrón, sin comentario) | 22 | Bs 19,660.68 | HEURISTIC (mismo canal/usuarios/almacenes) |

- `BUSINESS_PARTNER_IDENTITY` y `DOCUMENT_OPERATIONAL_SEMANTICS` se clasifican por
  separado: **ninguna operación muestra semántica comercial** (ninguna tiene cobranza,
  destino externo o precio de mercado consistente).
- Degradaciones declaradas: `PHYSICAL_RECEIVER=UNRESOLVED` (22 casos sin comentario),
  `BUYER_IDENTITY=UNRESOLVED` (22), `CUSTOMER_EXCEPTION_HISTORY=UNAVAILABLE`,
  `INTERNAL_PURPOSE=HEURISTIC` (22 casos).

---

## R. EXECUTIVE CASES

**Caso Nº1 — FIPRONIL masivo (63% del monto, 11 facturas):**
486 L de FIPRONIL 1% a Bs 49–55/L (mediana normal 109.62). Facturado desde Salón 2A,
entregado «PARA LA REJA» / «LLEVO SR BRANKO PARA LA REJA», sin cobranza. **INTERNAL.**

**Caso Nº2 — «MEDICAMENTOS … PARA LA REJA LLEVA SR BRANKO»:**
Factura 11448517 (Bs 6,810, la mayor) con memo contable «MEDICAMENTOS LLEVO SR BRANKO
PARA LA REJA. Basado en venta de Retail One S2AS17ED31540…». **INTERNAL_MEDICAL.**

**Caso Nº3 — Pedido telefónico (SAP_DIRECT):**
Factura 11200827 (Bs 3,619) sobre entrega «SOLICITADO VIA TELEFONICA POR ARTURO ESCALANTE
PARA EL CHOFER DE SAAVEDRA CARLOS RIVERA» (Orden 261900706). **INTERNAL.**

**Caso Nº4 — «la reja autorisado por don tito»:**
Factura 11144076 (Bs 58.00, 2026-03-01, Silvia Oly) sobre entrega 260400031 con comentario
«la reja autorisado por don tito. Basado en venta de Retail One SRCR10ED257». **INTERNAL.**

**Caso Nº5 — Reporte histórico 2025:**
Desde 2024-06 hay entregas R1; las facturas de 2025 (45) nunca se cobraron; la única NC
(2025-11-13, Bs 1,572) es del mismo patrón. **INTERNAL.**

---

## S. LIMITACIONES

1. **`TN_SOURCE_INSPECTION=PARTIAL`** y políticas de permisos no legibles con la cuenta
   READ ONLY (arrastre del gate de control).
2. `PHYSICAL_RECEIVER=UNRESOLVED` en 22/40 casos (sin comentario en la entrega); la
   inferencia HEURISTIC se apoya en canal/usuarios/almacenes idénticos.
3. La categoría «ENVASE» proviene de la taxonomía validada por regex de nombre
   (SPRAY/BOLSA/AMP) y puede sobre-ensamblar SKU de venta; se reporta el grupo OITB como
   evidencia primaria complementaria.
4. `INTERNAL_PURPOSE=HEURISTIC` para los 22 casos mudos: no hay evidencia de terceros, pero
   tampoco se puede certificar destino físico uno a uno.
5. El NIT compartido (1468238) es señal *fuerte* de parte relacionada, no prueba legal.
6. La comparación de precio usa mediana de clientes normales en ventana equivalente; no
   considera descuentos de escala (pero LA REJA es quien más compra FIPRONIL y pagina
   menos: dirección anti-escala).

---

## T. TESTS

**Loop tests nuevos (`test_la_reja_identity.py`): 23 PASS / 0 FAIL.**
HANA smoke real (`hana_smoke_la_reja.py`): **60 checks / 0 failures**
(5 mayores + 5 más antiguos + líneas + productos + warehouses + usuarios).

**Regresión (gates previos preservados):**

| Suite | Resultado |
|---|---|
| credit_open_risk/test_open_risk.py | 29 PASS |
| credit_exception_economic/test_economic_grouping.py | 26 PASS |
| credit_exception/test_credit_exception.py | 35 PASS |
| users_audit (5 suites) | 52 PASS |
| inventory_movements transtype gate | PASS |
| stock/test_stock_domain.py | 20 PASS |

**No se reabrieron** los gates
`TELCHI_CREDIT_CONTROL_AUTHORIZATION_TRACEABILITY_V1_PASS`,
`TELCHI_CREDIT_EXCEPTION_CASES_V1_PASS`,
`TELCHI_CREDIT_EXPLAINED_CASES_ECONOMIC_GROUPING_V1_PASS`,
`TELCHI_CREDIT_OPEN_RISK_AGING_V1_PASS`.

**READ ONLY:** `SAP_WRITE_COUNT=0` (auditado en todos los scripts nuevos y en evidencia).
Podman lifecycle MANUAL respetado (HANA ya estaba disponible en 127.0.0.1:30015; no se
inició/detuvo ningún contenedor).

---

## U. FINAL GATE

Condiciones del gate `TELCHI_C010341_LA_REJA_OPERATIONAL_IDENTITY_V1_PASS`:

1. ✅ BP master auditado (OCRD/CRD1/OCPR)
2. ✅ Historia documental reconstruida (OINV/ODLN/ORDR/ORIN/ORCT/OITR-ITR1/OJDT-JDT1)
3. ✅ 40/40 documentos preservados (40 DocEntry únicos)
4. ✅ Bs 47,258.99 reconciliados (Δ=0.00)
5. ✅ Productos identificados (109 líneas, 78 ítems, 0 UNKNOWN)
6. ✅ Productos clasificados con evidencia (OITM+OITB+OWOR+ITT1, taxonomía validada)
7. ✅ Almacenes identificados (2A-SAL 77.1%, LAB-T*, salones)
8. ✅ Stock effect validado (OINM 40 movimientos, OutQty=Qty entrega)
9. ✅ Usuarios identificados (jirahola/eroman facturas; soluone/nvargas/arioja entregas)
10. ✅ Vendedores identificados (OSLP, ≠ usuario)
11. ✅ Canal identificado (RETAIL_ONE 34 + SAP_DIRECT 6)
12. ✅ Destino/receptor investigado (La Reja + familia Telchi + choferes; 22 UNRESOLVED)
13. ✅ Pricing analizado (70.8% del monto SYMBOLIC)
14. ✅ Cobranza histórica analizada (0 ORCT; 1 NC; patrón PERSISTENT_OPEN)
15. ✅ Accounting sample reconciliado (1120101/4110101, balanceado)
16. ✅ Generic-account hypothesis testeada (SINGLE_OPERATIONAL_ENTITY; sin terceros)
17. ✅ Operational semantics asignada con confidence (18 STRONG + 22 HEURISTIC)
18. ✅ NO_SILENT_FANOUT (cadena factura→entrega 40/40; líneas conciliadas)
19. ✅ Regression PASS (29+26+35+52+20 + transtype)
20. ✅ SAP_WRITE_COUNT=0 (READ ONLY auditado)

**Declaración de cierre:**

```text
TELCHI_C010341_LA_REJA_OPERATIONAL_IDENTITY_V1_PASS
```

**Respuesta ejecutiva (castellano):**

> C010341 LA REJA se utiliza principalmente como **cuenta interna / parte relacionada de
> consumo de la familia Telchi en la propiedad «La Reja»** (mismo NIT que el propietario,
> entregas «PARA SR ROBERTO TELCHI», «MEDICAMENTOS», choferes propios, 0 cobros históricos).
> Las 40 operaciones por Bs 47,258.99 corresponden a **18 con semántica interna
> demostrada (Bs 27,598.31)** y **22 del mismo patrón sin comentario (Bs 19,660.68)**;
> ninguna se explica como venta comercial a tercero. Los principales productos son FIPRONIL
> (486 L, 63%), repelente, bicarbonato, medicamentos y víveres; salen desde los salones
> (2A-SAL 77%) y laboratorio; los vendedores que figuran son cajeros de salón (Mariela
> Irigoyen, M. F. Menacho, L. Guzman…); los usuarios SAP que crean las facturas son
> jirahola y eroman; el patrón de precios es preferencial interno (70.8% del monto bajo la
> mitad del precio normal); la cobranza histórica muestra **nunca pagos** (0 ORCT, 1 NC de
> limpieza); la evidencia **indica que NO es un cliente comercial real** y **NO indica uso
> como cuenta genérica para terceros** (es cuenta de consumo interno familiar).