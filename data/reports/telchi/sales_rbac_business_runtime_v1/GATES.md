# Activation gates

PASS acotado a Telchi DEV y estas dos operaciones documentales; no certifica PROD, WhatsApp delivery, importe neto ni ausencia universal de rechazos del intérprete.

```text
TELCHI_SALES_RBAC_CATALOG=PASS
TELCHI_SALES_RBAC_TENANT_ENTITLEMENT=PASS
TELCHI_SALES_RBAC_DELEGATION=PASS
TELCHI_SALES_RBAC_PILOT_ASSIGNMENT=PASS
TELCHI_SALES_EFFECTIVE_PERMISSIONS=PASS
TELCHI_SALES_UNAUTHORIZED_DENIAL=PASS
TELCHI_SALES_LATEST_HTTP=PASS
TELCHI_SALES_COVERAGE_HTTP=PASS
TELCHI_SALES_SQL_REFERENCE_PARITY=PASS
TELCHI_SALES_STATE_ENGINE_GUARD=PASS
TELCHI_SALES_BUSINESS_RESPONSE=PASS
TELCHI_SALES_RBAC_AND_BUSINESS_RUNTIME_V1=PASS
```

## Garantías y evidencia

Los cuatro gates permanentes se cumplen para latest_documents y coverage; código IMPLEMENTED no significa ACTIVATED fuera del alcance aquí acreditado.

- DATA_PASS: SQL real read-only CURRENT/1408; [paridad](FOUNDATION_PARITY.md).
- SEMANTIC_PASS: OINV activas por DocDate; no ingresos netos ni mes completo certificado.
- AUTH_PASS: catálogo/roles/entitlement/delegación/piloto y resolver Console real; [RBAC](RBAC_CHANGES.md), [efectivos](EFFECTIVE_PERMISSIONS.md).
- BUSINESS_RUNTIME_PASS: preguntas naturales por dispatcher/handler/State Engine/capabilities, datos empresariales y SQL independiente coincidentes; [HTTP](BUSINESS_HTTP_RESULTS.md).
- Seguridad: siete controles negativos, guard, rutas y aislamiento; [regresión](SECURITY_REGRESSION.md).
- Backup y reversión: snapshot privado antes de escrituras, SHA256/roundtrip y ensayo transaccional; no-op de segunda activación sin auditoría duplicada.

## Validaciones ejecutadas

Los comandos se ejecutaron desde backend salvo LAT/Git desde raíz. No se reutilizan PASS históricos para sustituir estas mediciones.

- `uv run pytest modules/telchi/assistant/tests modules/telchi/provisioning/tests tests/test_telchi_assistant_srv05.py modules/telchi/datalake/tests/test_messaging_sales_query.py -q`: 166 PASS / 2 skips PG disposable; advertencia baseline. [Log](tests_final.log).
- `prepare.py`: read-only precheck, backup privado único e integridad, identidades y catálogo original.
- `live_cli --sales-activation`: plan read-only; apply y segundo apply no-op, dos eventos en total.
- `live_probe --luna --preflight`: provider/model/effort real verificados, sin fallback; [preflight](luna_preflight.json).
- `run_battery`: regresión previa 12/32, correcciones focales y batería final B01–B06, 6/8; recheck final 12/32 sin ERROR. Rechazos intermedios preservados y explicados, no ocultos.
- `security_probes`: límites HTTP, sesiones y dos requests paralelos PASS.
- `verify.py`: permisos PG, negativos, rollback rehearsal y SQL independiente sobre respuestas HTTP PASS.
- Gates LAT y `git diff --check`: ver [validation_commands.log](validation_commands.log); revisión del diff final sin cambios fuera del scope propio.

## Recursos, riesgos y pendientes

Host seguro y presupuesto acotado: ~8 GB MemAvailable, 8 cores, carga observada 0.4–2.1, swap sin crecimiento sostenido. PostgreSQL no se reinició y no se detuvieron servicios ajenos.

```text
HOST_PREFLIGHT=SAFE
RESOURCE_GUARD=PASS
CONCURRENCY_USED=1 worker pytest; 2 threads DuckDB por conexión; máximo 2 requests HTTP en security
UNRELATED_PROCESSES_TERMINATED=0
ENVIRONMENTAL_ABORTS=0
OWN_PROCESSES_LEFT_RUNNING=0
```

Servidores temporales propios cerrados/reaped por los runners; cleanup final sin listener DEV. Queda riesgo real de propuestas inválidas/no disponibles del intérprete: fail-closed conservado, Luna sin cambios. No hay paginación, mes completo certificado ni métrica neta aprobada. Sin commit, push, deploy, cambios SAP/Foundation ni otros módulos.
