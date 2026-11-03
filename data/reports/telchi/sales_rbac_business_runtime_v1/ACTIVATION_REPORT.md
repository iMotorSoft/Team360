# Activation report

Telchi DEV: las dos operaciones documentales IMPLEMENTED pasan a ACTIVATED para el piloto aprobado. No hay promoción PROD ni cambios a consultas Foundation, Luna o State Engine.

## Resumen ejecutivo

Se verificó PG 18.4 (Debian 18.4-1.pgdg13+1), las tres identidades persistidas, organización Telchi y workspace `telchi_dev`. El propietario confirmó DEV y autorizó esta intervención limitada.

- Team360 global: catálogo de dos permisos, dos roles de workspace y dos relaciones rol/permiso; límites delegados en el ledger administrativo existente.
- Telchi: actor organization_admin validado; dos relaciones usuario/rol al piloto. Se conserva el permiso source_quantity y no se agregan permisos globales.
- Segunda ejecución: cero registros nuevos y cero eventos administrativos nuevos.
- HTTP B01–B06: datos empresariales reales, cobertura y ranking; sin inventar importes, mes completo ni página anterior.
- SQL independiente: igualdad completa de filas/orden en B01, fechas/universo/período en B02–B03, misma publicación y snapshot 1408.
- Seguridad: siete controles negativos con cero consultas; límites HTTP fail-closed verificados.

## Operación administrativa y respaldo

Se extiende el CLI existente de propietario local DEV, no se emite un token, no se simula un login Console y no se activa ninguna credencial. Actores auditados y roles persistidos se verifican antes de escribir.

- Comando: `uv run python -m modules.telchi.provisioning.live_cli --sales-activation --manifest <private_manifest> --apply --local-owner-bootstrap`.
- Plan previo read-only sin `--apply`; manifest propietario 0600, target exacto y fuentes revisadas con SHA256.
- Backup privado único: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/backups/sales-rbac-20261012T222043242007Z/before.json`; hash `b7336ad613d37a6e2fada7cc295360d3cb5636f16ed747d2eb542b94f086463e`; roundtrip JSON confirmado antes de escrituras.
- Dos eventos PG: `telchi.admin.sales-authorize` (actor global) y `telchi.admin.sales-grant` (actor Telchi), con antes/después, permisos, registros creados y resultado.
- Rollback limitado probado en transacción descartada: [detalle](RBAC_CHANGES.md). Estado final intacto.

## Archivos modificados

Paths relativos a `SrvRestAstroLS_v1/backend`; se preservaron los archivos preexistentes y no se hicieron operaciones Git de escritura.

- `modules/telchi/provisioning/live_cli.py`.
- `modules/telchi/provisioning/admin_repository.py`.
- `modules/telchi/provisioning/admin_service.py`.
- `modules/telchi/provisioning/sales_cli.py`.
- `modules/telchi/provisioning/sales_repository.py`.
- `modules/telchi/provisioning/tests/test_sales_admin.py`.
- `modules/telchi/assistant/handler.py`.
- `modules/telchi/assistant/tests/test_sales_business_contract.py`.
- `modules/telchi/assistant/tests/runtime_http/run_battery.py`.
- `modules/telchi/assistant/README.md`.
- `modules/telchi/status_actual.md`.
- `data/reports/telchi/sales_rbac_business_runtime_v1/`: siete entregables, scripts reproducibles y evidencia JSON/logs.

## Validación y límites

Las garantías se documentan por evidencia, no por HTTP 200. [Gates](GATES.md), [permisos](EFFECTIVE_PERMISSIONS.md), [HTTP](BUSINESS_HTTP_RESULTS.md), [paridad](FOUNDATION_PARITY.md) y [seguridad](SECURITY_REGRESSION.md) conservan el detalle.

- Rama `feature/console-backend-core`; HEAD `09d2ec715a31bb88574d734eacb9f437f008624e` conservado; sin commit/push/deploy.
- Tests focalizados: 166 PASS / 2 skips (PG disposable no configurado); una advertencia baseline de composición Diagnosis fixture. Evidencia PG18 real y rollback rehearsal separados, sin crear otra base.
- Runtime: Srv05/Telchi composición real mediante el adaptador DEV existente; loopback efímero, registro Telchi y State Engine V2 acreditados por auditoría persistida. Servidores propios reap al terminar; no se deja listener permanente.
- Modelo preflight: GPT-5.6 Luna Medium, OpenAI directo, eco verificado, sin fallback; Milvus/LiteLLM no son consumidores de esta cadena.
- No DDL, SAP, Parquet, Foundation DML/publicación, Flow, Diagnosis, Messaging, Evolution, Srv01 ni configuración del modelo modificados.
- Impacto transversal: sólo catálogo RBAC de dos códigos Telchi y roles del workspace autorizado. Las fuentes provisioning cambiaron: manifests históricos con hashes previos deben revisarse antes de reutilizarlos.
- Riesgo residual: propuestas ocasionalmente inválidas/no disponibles del intérprete siguen fallando cerrado. No se modificó Luna ni se ocultaron esos rechazos; [incidentes preservados](BUSINESS_HTTP_RESULTS.md).
- Próximo paso: validación WhatsApp separada si se solicita; no requerida ni certificada por este gate HTTP DEV.
