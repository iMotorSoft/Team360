# TELCHI SAP — ÍNDICE DE DOCUMENTACIÓN

**Módulo:** Telchi SAP
**Capa actual:** DataScience — Ventas, Cobranzas, Crédito, Temporalidad SAP
**Workspace:** `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi`
**Baseline legacy:** `/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/`

---

## 1. Estructura del Módulo

```
Telchi SAP
│
├── Acceso SAP / HANA (READ ONLY)
├── Validación legacy
├── Extracción
├── Staging
├── Data Lake
├── DataScience ← CAPA ACTUAL
│   ├── Ventas
│   ├── Caja
│   ├── Crédito
│   ├── Cobranzas
│   ├── Deudores
│   ├── Pagos
│   ├── Reconciliaciones
│   ├── Notas de crédito
│   ├── Anulaciones
│   ├── Clientes
│   └── Vendedores
├── Reconciliación histórica
├── Análisis de negocio
└── Futura capa conversacional
```

---

## 2. Documentación Primaria

| Documento | Propósito | Ubicación |
|-----------|-----------|-----------|
| [STATUS_ACTUAL.md](../STATUS_ACTUAL.md) | Estado actual del módulo | Raíz |
| [LAT.md](../LAT.md) | Aprendizajes y decisiones arquitectónicas | Raíz |
| [DECISIONS.md](../DECISIONS.md) | Log de decisiones con evidencia | Raíz |
| [TELCHI_SAP_MODULE.md](../TELCHI_SAP_MODULE.md) | Documento canónico del módulo | Raíz |

---

## 3. Modelo Financiero (FINANCIAL-001 a FINANCIAL-005)

### Gates

| Gate | Estado | Change |
|------|--------|--------|
| `TELCHI_FINANCIAL_INVOICE_CONTRACT_PASS` | ✅ PASS | FINANCIAL-001 |
| `TELCHI_FINANCIAL_CREDIT_NOTE_PASS` | ✅ PASS | FINANCIAL-002 |
| `TELCHI_FINANCIAL_PAYMENT_APPLICATION_PASS` | ✅ PASS | FINANCIAL-003 |
| `TELCHI_FINANCIAL_RECONCILIATION_PASS` | ✅ PASS | FINANCIAL-004 |
| `TELCHI_FINANCIAL_CURRENT_AR_PASS` | ✅ PASS | FINANCIAL-005 |

### SQL Financieros

| Archivo | Propósito |
|---------|-----------|
| `sql/current/financial/invoice_contract_v1.sql` | Contrato de facturas |
| `sql/current/financial/credit_note_contract_v1.sql` | Contrato de NC |
| `sql/current/financial/payment_contract_v1.sql` | Contrato de pagos |
| `sql/current/financial/payment_application_v1.sql` | Aplicación de pagos |
| `sql/current/financial/reconciliation_contract_v1.sql` | Contrato de reconciliación |
| `sql/current/financial/reconciliation_members_v1.sql` | Miembros de reconciliación |
| `sql/current/financial/ar/settlement_aggregation_v1.sql` | Agregación de liquidación |
| `sql/current/financial/ar/current_ar_v1.sql` | AR actual |

---

## 4. Temporalidad SAP (FASE 0)

### Gates

| Gate | Estado |
|------|--------|
| `TELCHI_TEMPORAL_CANCELLATION_SEMANTICS_PASS` | ✅ PASS |
| `TELCHI_TEMPORAL_PAYMENT_CANCELLATION_PASS` | ✅ PASS |
| `TELCHI_TEMPORAL_RECONCILIATION_CANCELLATION_PASS` | ✅ PASS |
| `TELCHI_TEMPORAL_MODEL_ARCHITECTURE_PASS` | ✅ PASS |

### SQL Temporales

| Archivo | Propósito |
|---------|-----------|
| `sql/current/temporal/invoice_cancellation_lifecycle_v1.sql` | Timeline de facturas |
| `sql/current/temporal/payment_cancellation_lifecycle_v1.sql` | Timeline de pagos |
| `sql/current/temporal/as_of_ar_reconstruction_v1.sql` | AR por fecha histórica |
| `sql/current/temporal/test_T03_invoice_cancellation.sql` | Test marzo→junio |

### Validadores

| Archivo | Propósito |
|---------|-----------|
| `validation/temporal/investigate_cancellations.py` | Investigación de anulaciones |
| `validation/temporal/test_T03_invoice_cancellation.py` | Test de escenario real |

---

## 5. Documentos de Hallazgos

| Documento | Propósito |
|-----------|-----------|
| `docs/cancellation_findings.md` | Hallazgos de anulaciones |
| `docs/temporal_investigation_complete.md` | Investigación temporal completa |
| `docs/fase0_inventory.md` | Inventario Fase 0 |
| `docs/fase0_summary.md` | Resumen ejecutivo Fase 0 |

---

## 6. Referencias Legacy

| Archivo | Propósito |
|---------|-----------|
| `srvSyncTelchiSB101.py` | Sync SAP HANA |
| `sapb1Tools01.py` | Herramientas SAP B1 |
| `activeTools01.py` | Herramientas activas |

Legacy root: `/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/`

---

## 7. Cómo Reanudar

1. Leer `STATUS_ACTUAL.md` para estado actual
2. Leer `TELCHI_SAP_MODULE.md` para contexto del módulo
3. Leer `LAT.md` para aprendizajes
4. Leer `DECISIONS.md` para decisiones
5. Verificar gates en `validation/financial_audit/financial_audit_gate.json`
6. Usar prompt de reanudación al final de `STATUS_ACTUAL.md`

---

## 8. Reglas Fundamentales

### Regla SAP

Todo resultado analítico debe terminar en evidencia SAP:

```
Finding
   ↓
Explicación
   ↓
Documento / operación
   ↓
SAP (DocEntry, DocNum, TransId, ReconNum, LineNum)
```

### Regla de Lectura

```text
HANA es la fuente operacional de referencia.
Legacy y Parquet son fuentes históricas/baseline.
```

### Regla Modular

```text
Flow es otro módulo independiente.
No forma parte de Telchi SAP.
No se modifica en este ciclo.
```

---

## 9. Propósito del Módulo

Telchi SAP tiene como responsabilidad:

```text
Acceso read-only a SAP HANA
Validación de datos SAP
Validación contra legado
Extracción
Staging
Data Lake
Reconciliación histórica
Modelado temporal
Data Science
Detección de findings
Trazabilidad hasta documentos SAP
Futura capa conversacional
```
