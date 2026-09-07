# TELCHI SAP — INVENTARIO FASE 0

**Módulo:** Telchi SAP
**Capa:** DataScience — Ventas, Cobranzas, Crédito, Temporalidad SAP
**Fecha:** 2026-08-23
**Objetivo:** Inventario completo antes de implementar profundidad temporal + ventas + caja + crédito + cobranzas

---

## 1. Datasets Parquet Existentes (Legacy)

### Cash (Caja)
| Dataset | Período | Archivos | Tamaño aprox |
|---------|---------|----------|--------------|
| cash-YYYY-MM.parq | 2019-01 a 2022-03 | 39 | ~33 MB |
| **Total** | **3 años** | **39** | **~33 MB** |

### Payments (Pagos B1)
| Dataset | Período | Archivos | Tamaño aprox |
|---------|---------|----------|--------------|
| paymentB1-YYYY-MM.parq | 2022-04 a 2023-05 | 12 | ~8 MB |
| **Total** | **1 año** | **12** | **~8 MB** |

### Reconciliation (Reconciliaciones B1)
| Dataset | Período | Archivos | Tamaño aprox |
|---------|---------|----------|--------------|
| reconB1-YYYY-MM.parq | 2022-04 a 2023-05 | 12 | ~10 MB |
| **Total** | **1 año** | **12** | **~10 MB** |

### Cuentas por Cobrar (AR)
| Dataset | Período | Archivos | Tamaño aprox |
|---------|---------|----------|--------------|
| cuentasxCobrar-YYYY-MM.parq | 2020-01 a 2021-12 | 24 | ~20 MB |
| **Total** | **2 años** | **24** | **~20 MB** |

### Clientes
| Dataset | Notas |
|---------|-------|
| clientSB1.parq | Clientes SAP B1 |

### Productos
| Dataset | Notas |
|---------|-------|
| `No identificado` | Verificar existencia |

---

## 2. Scripts Legacy Identificados

### srvSyncTelchiSB101.py (Principal)
- **Fuente:** `/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/SrvRest/srvSyncTelchiSB101.py`
- **Conexión:** SQLAlchemy + HANA
- **Funciones principales:**
  - `makeSaleDFRange()` — Ventas con líneas (OINV + INV1)
  - `makeNCDFRange()` — Notas de crédito (ORIN + RIN1)
  - `syncDSSale()` — Sincronización mensual de ventas
  - `syncDSNC()` — Sincronización mensual de NC

### sapb1Tools01.py
- **Fuente:** `/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/sapb1Tools01.py`
- **Notas:** Herramientas SAP B1 variadas

### syncCosto01.py
- **Fuente:** `/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/SrvRest/syncCosto01.py`
- **Notas:** Sincronización de costos

---

## 3. SQL Current (Validados)

### Financial (FINANCIAL-001 a FINANCIAL-005)
| Archivo | Descripción | Grain | Estado |
|---------|-------------|-------|--------|
| `invoice_contract_v1.sql` | Contrato de facturas | OINV.DocEntry | PASS |
| `credit_note_contract_v1.sql` | Contrato de NC | ORIN.DocEntry | PASS |
| `payment_contract_v1.sql` | Contrato de pagos | ORCT.DocEntry | PASS |
| `payment_application_v1.sql` | Aplicación de pagos | ITR1 | PASS |
| `reconciliation_contract_v1.sql` | Contrato de reconciliación | OITR.ReconNum | PASS |
| `reconciliation_members_v1.sql` | Miembros de reconciliación | ITR1 | PASS |
| `settlement_aggregation_v1.sql` | Agregación de liquidación | OINV.DocEntry | PASS |
| `current_ar_v1.sql` | AR actual | OINV.DocEntry | PASS |

### Sales
| Archivo | Descripción | Grain | Estado |
|---------|-------------|-------|--------|
| `sales_v1_linenum.sql` | Ventas por línea | DocEntry+LineNum | PASS |

### Credit Notes
| Archivo | Descripción | Grain | Estado |
|---------|-------------|-------|--------|
| `credit_notes_v1.sql` | Notas de crédito | DocEntry+LineNum | PASS |

---

## 4. Tablas SAP HANA Identificadas

### Documentos Comerciales
| Tabla | Descripción | Grain |
|-------|-------------|-------|
| OINV | Facturas de venta | DocEntry |
| INV1 | Líneas de factura | DocEntry+LineNum |
| ORIN | Notas de crédito | DocEntry |
| RIN1 | Líneas de NC | DocEntry+LineNum |

### Pagos
| Tabla | Descripción | Grain |
|-------|-------------|-------|
| ORCT | Pagos recibidos | DocEntry |
| RCT1 | Cheques de pago | DocEntry+LineNum |
| RCT2 | Aplicación de pago | DocEntry (LIMITADO) |

### Reconciliación (Settlement Layer)
| Tabla | Descripción | Grain |
|-------|-------------|-------|
| OITR | Conciliaciones | ReconNum |
| ITR1 | Miembros de conciliación | ReconNum+LineSeq |

### Maestros
| Tabla | Descripción |
|-------|-------------|
| OCRD | Clientes |
| OSLP | Vendedores |
| OITB | Grupos de artículos |
| OWHS | Depósitos |

---

## 5. Campos Críticos SAP

### OINV (Facturas)
| Campo | Tipo | Descripción |
|-------|------|-------------|
| DocEntry | INT | PK documento |
| DocNum | INT | Número de documento |
| CardCode | VARCHAR | Código cliente |
| CardName | VARCHAR | Nombre cliente |
| SlpCode | INT | Código vendedor |
| DocDate | DATE | Fecha documento |
| DocDueDate | DATE | Fecha vencimiento |
| DocTotal | DECIMAL | Total documento |
| DocStatus | CHAR | Estado (O=abierta, C=cerrada) |
| CANCELED | CHAR | Anulado (N/Y/C) |
| DocSubType | VARCHAR | Subtipo (IB= factura) |
| TransId | INT | ID transacción contable |
| PaidSum | DECIMAL | Suma pagada |
| PaidToDate | DECIMAL | Pagado hasta fecha |
| DocCur | VARCHAR | Moneda |
| UpdateDate | DATE | Fecha última actualización |
| UpdateTS | VARCHAR | Timestamp actualización |

### ORIN (Notas de Crédito)
| Campo | Tipo | Descripción |
|-------|------|-------------|
| DocEntry | INT | PK documento |
| DocTotal | DECIMAL | Total (POSITIVO en SAP) |
| BaseRef | VARCHAR | Referencia documento base |
| CANCELED | CHAR | Anulado (N/Y/C) |

### RIN1 (Líneas NC)
| Campo | Tipo | Descripción |
|-------|------|-------------|
| BaseEntry | INT | DocEntry factura original |
| BaseLine | INT | Línea factura original |
| BaseType | INT | 13=factura, 16=devolución |

### ORCT (Pagos)
| Campo | Tipo | Descripción |
|-------|------|-------------|
| DocEntry | INT | PK documento |
| DocTotal | DECIMAL | Total pago |
| DocCurr | VARCHAR | Moneda (OJO: DocCurr, no DocCur) |
| Canceled | CHAR | Anulado |

### OITR (Reconciliaciones)
| Campo | Tipo | Descripción |
|-------|------|-------------|
| ReconNum | INT | PK reconciliación |
| ReconDate | DATE | Fecha reconciliación |
| Canceled | CHAR | Anulada (N/Y/C) |

### ITR1 (Miembros Reconciliación)
| Campo | Tipo | Descripción |
|-------|------|-------------|
| ReconNum | INT | FK reconciliación |
| LineSeq | INT | Secuencia línea |
| SrcObjTyp | INT | Tipo objeto fuente |
| SrcObjAbs | INT | DocEntry objeto fuente |
| ReconSum | DECIMAL | Monto reconciliado |
| IsCredit | CHAR | Crédito (Y/N) |

---

## 6. Decisiones de Anulación (TELCHI-DEC-014)

```
CANCELED = 'N' → Documento válido
CANCELED = 'Y' → Documento anulado (original)
CANCELED = 'C' → Documento de reversión (par del Y)
```

**Y y C siempre aparecen en pares.**

---

## 7. Brechas Identificadas (Requeridas por el Nuevo Prompt)

### 7.1 Temporalidad
- [ ] **No existe** vista AS-REPORTED (qué sabíamos en fecha X)
- [ ] **No existe** vista RESTATED (verdad económica actual)
- [ ] **No existe** timeline de eventos por documento
- [ ] **No existe** detección de late-arriving changes

### 7.2 Anulaciones
- [ ] **No se modela** fecha de anulación efectiva
- [ ] **No se distingue** anulación vs. cancelación vs. reversión
- [ ] **No se vincula** documento anulante con documento original
- [ ] **No se determina** cómo SAP provee fecha de anulación

### 7.3 Pagos
- [ ] **No se modela** pago anulado individual
- [ ] **No se vincula** pago → factura con granularidad de aplicación
- [ ] **No se calcula** días hasta primer pago
- [ ] **No se calcula** días hasta pago completo
- [ ] **No se modela** pago parcial vs. pago a cuenta

### 7.4 Caja
- [ ] **No se conecta** caja (cash) con reconciliaciones
- [ ] **No se valida** si efectivo entró realmente
- [ ] **No se detecta** cobro sin aplicación esperada
- [ ] **No se detecta** aplicación sin movimiento de caja

### 7.5 Crédito
- [ ] **No se compara** plazo contractual vs. real
- [ ] **No se calcula** exposición crediticia por cliente
- [ ] **No se detecta** crecimiento financiado por Telchi

### 7.6 Aging Histórico
- [ ] **No existe** `aging_as_of(fecha)` reconstruible
- [ ] **No se puede** reproducir aging de marzo sin conocimiento de junio

### 7.7 Cohorts
- [ ] **No se calcula** % cobrado a 7/30/60/90 días por cohorte

### 7.8 Vendedor + Cobranza
- [ ] **No se cruza** ventas por vendedor con cobranza del mismo

---

## 8. Prioridad de Investigación

### MÁXIMA (Bloqueante para arquitectura temporal)
1. **Fecha de anulación** — ¿Cómo obtener de SAP?
2. **Pago anulado** — ¿Cómo identificar pagos cancelados?
3. **Watermark incremental** — ¿Qué campo SAP permite detectar cambios?
4. **Reconciliación anulada** — ¿Cómo afecta al AR?

### ALTA (Requerida para findings de negocio)
5. **Caja ↔ Reconciliación** — Vinculación real
6. **Aplicación de pago** — Granularidad real en ITR1
7. **Notas de crédito ↔ Factura** — Vinculación completa
8. **Plazo contractual vs. real** — OCRD vs. cálculo

### MEDIA (Enriquecimiento)
9. **Aging histórico** — Reconstrucción por fecha
10. **Cohorts** — Curvas de cobranza
11. **Vendedor + Cobranza** — Métricas cruzadas

---

## 9. Archivos a Crear

```
sql/current/temporal/
├── invoice_lifecycle.sql          # Timeline de eventos por factura
├── payment_lifecycle.sql          # Timeline de eventos por pago
├── cancellation_date_derivation.sql  # Derivación fecha anulación
├── as_of_ar_reconstruction.sql    # AR reconstruible por fecha
├── aging_as_of.sql               # Aging por fecha histórica
├── payment_application_detail.sql # Aplicación granular
├── cash_vs_reconciliation.sql     # Caja vs reconciliación
├── seller_collection_metrics.sql  # Métricas vendedor+cobranza
└── cohort_collection_curves.sql   # Curvas de cobranza por cohorte

validation/temporal/
├── test_T03_invoice_cancellation.sql
├── test_T04_late_cancellation.sql
├── test_T05_payment_cancellation.sql
├── test_T06_partial_payments.sql
├── test_T10_aging_as_of.sql
├── test_T16_cancellation_restatement.sql
└── test_T17_as_reported.sql
```

---

## 10. Estado de HANA

| Componente | Estado |
|------------|--------|
| VPN | ACTIVA |
| HANA 192.168.20.20:30015 | TCP PASS |
| Schema TELCHI | ACCESIBLE |
| User INSIDING_HANA | AUTENTICADO |
| Lectura | HABILITADA |
| Escritura | PROHIBIDA |

---

**Próximo paso:** Investigar fecha de anulación en SAP Telchi.
