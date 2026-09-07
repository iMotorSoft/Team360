# TELCHI SAP — RETAIL ONE × DMS USER ATTRIBUTION V1

**Date:** 2026-08-26
**Gate:** `TELCHI_RETAIL_ONE_DMS_USER_ATTRIBUTION_V1_PASS`
**HANA writes:** ZERO (READ ONLY)

---

## 1. Pregunta respondida

¿Cuántas personas realmente usan Retail One, DMS y SAP directo — sin confundir
cuentas técnicas SAP con operadores humanos?

---

## 2. Respuesta ejecutiva

**En actividad reciente:**

```
Retail One:
  167 operadores/personas confirmados (163 con empleado vinculado)
  198 vendedores asociados
  5 sucursales, 54 estaciones
  Activos últimos 90 días: 62 operadores

DMS:
  SAP NO conserva el operador humano de DMS.
  Podemos demostrar 36 vendedores y 42 rutas,
  pero no afirmar cuántas personas operaron el sistema.

SAP directo:
  34 usuarios SAP (32 nombrados + 2 técnicos)
  12 con vínculo a empleado
```

**Overlap entre sistemas (a nivel de vendedor SlpCode): 22 vendedores aparecen
como vendedor en Retail One Y en DMS. A nivel de operador humano el overlap
es UNRESOLVED (SAP no conserva el operador humano de DMS).**

---

## 3. Método y campos fuente (validados EXACT)

### Retail One — operador humano EXACT (LEVEL 1)

La tabla `@SO1_01VENTA` (1.78M filas) conserva la identidad del operador POS:

| Campo | Valor | Semántica validada | Identidad |
|-------|-------|--------------------|-----------|
| `U_SO1_USUARIO` | 167 valores | = `OHEM.empID` (163/167 match) | **OPERADOR HUMANO (cajero)** |
| `U_SO1_VENDEDOR` | 198 valores | = `OSLP.SlpCode` (190/190 match) | **VENDEDOR** |
| `U_SO1_SUCURSAL` | 5 valores | código de sucursal | sucursal |
| `U_SO1_ESTACION` | 54 valores | terminal/estación | estación |

**Join a SAP**: `@SO1_01VENTA.Name` = `OINV.U_SO1_01FOLIORETAIL1`
(1:1, 1,565,279 facturas unidas sin fanout — ratio 1.000).

### DMS — solo vendedor, sin operador humano (LEVEL 3)

En OINV con `U_ORIGIN='DMS'`:
- `SlpCode` (36 vendedores) → vendedor SAP
- `U_OSLP_ID` (42 rutas) → **ruta/zona DMS** (agrupa varios vendedores, NO es persona)
- No existe campo de operador/cajero DMS en SAP

### SAP directo — usuario SAP (LEVEL 4/5)

En OINV con `U_ORIGIN='SAP' AND U_SO1_01RETAILONE='N'`:
- `UserSign` (34 usuarios) → 32 nombrados + 2 técnicos

---

## 4. Resultados completos

| Métrica | Retail One | DMS | SAP Direct |
|---------|-----------:|----:|-----------:|
| Documentos | 1,788,761 | 154,817 | 98,157 |
| Operadores humanos EXACT | **167** | — (no conservado) | — |
| Operadores con empleado | 163 | — | — |
| Vendedores (SlpCode) | 198 | 36 | — |
| Vendedores en OSLP | 190 | 36 | — |
| Rutas (U_OSLP_ID) | — | 42 | — |
| Sucursales | 5 | — | — |
| Estaciones | 54 | — | — |
| Usuarios SAP distintos | — | 11 | 34 |
| Usuarios SAP técnicos | — | 2 | 2 |
| Usuarios SAP nombrados | — | 9 | 32 |
| Nombrados con empleado | — | — | 12 |

### Operadores Retail One activos (ventana temporal)

| Ventana | Operadores |
|---------|-----------:|
| Todo el historial | 167 |
| Últimos 12 meses | 80 |
| Últimos 90 días | 62 |
| Últimos 30 días | 56 |

---

## 5. Identidad por niveles

| Canal | Nivel de identidad |
|-------|--------------------|
| Retail One | **LEVEL 1 — EXACT HUMAN OPERATOR** (`U_SO1_USUARIO`=empID) |
| DMS | LEVEL 3 — STRONG SALESPERSON (SlpCode); sin operador humano |
| SAP direct | LEVEL 4/5 — SAP user (32 nombrados, 2 técnicos) |

---

## 6. Overlap entre sistemas

Overlap medido a nivel de **vendedor (SlpCode)** — única identidad común
demostrable entre canales (la identidad humana DMS es UNRESOLVED):

| Combinación (SlpCode como vendedor) | Compartidos |
|--------------------------------------|------------:|
| Retail One × DMS | **22** |
| SAP direct × DMS | **26** |
| Retail One × SAP direct | **88** |

### Distinción de niveles de overlap

| Nivel | Estado | Resultado |
|-------|--------|-----------|
| `SALESPERSON_OVERLAP` (SlpCode) | EXACT | 22 (Retail One×DMS), 26 (SAP×DMS), 88 (Retail One×SAP) |
| `SAP_USER_OVERLAP` (UserSign) | EXACT | documentado en reporte usuarios (27 usuarios multi-canal) |
| `HUMAN_OPERATOR_OVERLAP` | **UNRESOLVED** | DMS no conserva operador humano → no demostrable |

**Conclusión**: NO es correcto afirmar "0 personas operan ambos sistemas".
Lo demostrable es que 22 vendedores (SlpCode) están acreditados en Retail One
y DMS a la vez; el solapamiento de personas físicas queda UNRESOLVED por la
limitación de identidad DMS.

---

## 7. Cuentas técnicas (excluidas de "humanos")

| Usuario | Rol |
|---------|-----|
| `soluone` | Retail One integración (1.31M docs, NO es persona) |
| `dms` | DMS integración (126K docs) |
| `manager` | admin/technical multi-endpoint |
| `B1i`, `Workflow`, `AlertSvc`, `EDsUser`, `alianza`, `terbol` | integración/servicio |

---

## 8. Limitaciones

1. **DMS**: no se conserva operador humano en SAP. `U_OSLP_ID` es ruta, no persona.
   `HUMAN_OPERATOR_IDENTITY` para DMS = **UNRESOLVED** (solo vendedor disponible).
2. **HUMAN_OPERATOR_OVERLAP = UNRESOLVED**: al no existir operador humano DMS,
   no es posible afirmar si una misma persona opera Retail One y DMS. Solo se
   demuestra `SALESPERSON_OVERLAP` (SlpCode) = 22 entre Retail One y DMS.
3. **Retail One**: 4 de 167 operadores no matchean a OHEM (empID huérfano).
4. **Ventana temporal**: los operadores históricos (167) incluyen personal que ya
   no opera; los activos 90d (62) son la métrica operativa actual.
5. **U_SO1_USUARIO = empID** es una coincidencia estructural validada por match
   masivo (163/167), no una afirmación documental explícita de SAP.

---

## 9. Muestras reales (verificación manual)

Retail One (join Name=folio):
```
VENTA.Name='SCMC12CA343320' → OINV.U_SO1_01FOLIORETAIL1='SCMC12CA343320'
  usuario=401 (Ana Lia Hinojosa), sucursal=SCM
```

DMS (vendedor sin operador):
```
OINV U_ORIGIN='DMS' → SlpCode=5 (Marcos Vargas), U_OSLP_ID=16 (ruta multi-vendedor)
```

---

## 10. Tests

| Suite | Resultado |
|-------|-----------|
| test_attribution_identity | 8 PASS |
| Join Retail One (Name=folio) ratio | 1.000 (sin fanout) |
| Operator→employee match | 163/167 |
| Seller→OSLP match | 190/190 |
| READ ONLY | PASS |

---

## 11. Gate

**TELCHI_RETAIL_ONE_DMS_USER_ATTRIBUTION_V1_PASS**

Retail One: operador humano EXACT resuelto (167 personas).
DMS: vendedor resuelto (36), operador humano `UNRESOLVED` (no conservado en SAP).
SAP directo: usuario resuelto (34, 32 nombrados).

El PASS significa que la limitación de identidad humana DMS fue **demostrada y
documentada**, no escondida. Distinción clara entre cuenta técnica, usuario
nombrado y operador humano.

---

## 12. Nota de auditoría documental (2026-08-26)

Corrección posterior al cierre inicial: la afirmación original
"0 personas operan Retail One y DMS" era **incorrecta**. La verificación
directa de `SlpCode` demostró **22 vendedores compartidos** entre Retail One y
DMS. El error original solo había comparado operadores (empID→salesPrson) contra
DMS, no el SlpCode directo. El overlap humano sigue `UNRESOLVED` (DMS no
conserva operador). Las secciones 2, 6 y 8 fueron corregidas en consecuencia.
