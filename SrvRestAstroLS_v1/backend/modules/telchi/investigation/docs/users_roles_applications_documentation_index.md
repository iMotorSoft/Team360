# TELCHI SAP — Users / Roles / Applications — Documentación

Índice ejecutivo del trabajo de auditoría de identidad, permisos y uso de SAP.
No duplica el detalle de los reportes; enlaza a la fuente canónica de cada gate.

## Gates cerrados

| Gate | Estado | Reporte |
|------|--------|---------|
| `TELCHI_SAP_USERS_ROLES_MODULES_APPLICATIONS_V1_PASS` | ✅ | `users_roles_authorizations_v1_report.md` |
| `TELCHI_RETAIL_ONE_DMS_USER_ATTRIBUTION_V1_PASS` | ✅ | `retail_one_dms_user_attribution_v1_report.md` |
| `TELCHI_USERS_DOCUMENTATION_AUDIT_V1_PASS` | ✅ | este índice + reportes anteriores |

## Contenido por gate

### 1. Usuarios × Roles × Autorizaciones × Aplicaciones
`docs/users_roles_authorizations_v1_report.md`
- Universo: 170 usuarios SAP (78 activos, 92 bloqueados, 16 superusers)
- Autorización: USR3/UGR1, niveles N/F/R/V, precedencia directa+grupo
- Capacidades de negocio: mapeo ObjType (EXACT) / SO1_AU_* (STRONG) / rangos B1 (HEURISTIC)
- Hallazgo contable: `OJDT.UserSign` ≠ asiento manual (solo `TransType=59`)
- Origen de canal EXACT: Retail One 86.1% / DMS 8.5% / SAP direct 5.4% (documentos)
- Authorized × Actual, SoD (126 ACTUAL_CONFLICT), cross traceability
- Casos: eroman, post-block (smercado/sruiz/manager6), manager

### 2. Retail One × DMS — Atribución de usuario
`docs/retail_one_dms_user_attribution_v1_report.md`
- Retail One: 167 operadores humanos EXACT (`@SO1_01VENTA.U_SO1_USUARIO`=empID)
- Join 1:1 a OINV via `Name = U_SO1_01FOLIORETAIL1`
- DMS: 36 vendedores / 42 rutas; operador humano UNRESOLVED
- Overlap: 22 vendedores (SlpCode) en Retail One × DMS; overlap humano UNRESOLVED

## Código y evidencia

| Artefacto | Ubicación |
|-----------|-----------|
| Scripts de validación | `validation/users_audit/*.py` |
| SQL | `sql/current/users/*.sql` |
| Tests unit | `validation/users_audit/test_*.py` (52 total: 44 + 8) |
| Estado ejecutivo | `STATUS_ACTUAL.md` |

## Invariantes vigentes

- `HISTORICAL_AUTHORIZATION=UNAVAILABLE` — SAP B1 no conserva historia de permisos.
- `DMS_HUMAN_OPERATOR_IDENTITY=UNRESOLVED` — SAP no conserva operador humano DMS.
- `RETAIL_ONE_DMS_HUMAN_OVERLAP=UNRESOLVED` — solo se demuestra overlap de vendedor (SlpCode).
- `APPLICATION_TRACEABILITY` origen = EXACT; canal→persona = HEURISTIC.
- SAP/HANA writes = 0 (READ ONLY).
