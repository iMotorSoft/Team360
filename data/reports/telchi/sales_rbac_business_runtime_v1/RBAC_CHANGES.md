# RBAC changes

Antes/después proviene de snapshots privados y del resolver real; no se movieron usuarios, se inventaron IDs ni se duplicaron registros preexistentes.

## Relaciones y catálogo

Sólo los códigos comerciales listados quedan incorporados al alcance Telchi DEV.

| Entidad | Antes | Después |
| --- | --- | --- |
| latest_documents.read.v1 | ausente | permiso business cerrado OINV activa, límite 1..50 |
| coverage.read.v1 | ausente | permiso business cerrado cobertura OINV activa |
| source_quantity.read.v1 | existente | sin cambio |
| Roles exclusivos workspace | ausentes | telchi_sales_latest_documents_reader_v1 y telchi_sales_coverage_reader_v1 |
| Relaciones rol/permiso | 0 nuevas | 2, un código exacto por rol |
| Relaciones piloto/rol | 0 nuevas | 2 |
| Perfiles/usuarios/organización/workspace | existentes | sin cambio |
| Límites globales delegados | sólo V1 original | evento adicional aprobado latest/coverage; bootstrap V1 intacto |

Total: ocho filas RBAC nuevas (dos permisos, dos roles, dos role_permissions, dos user_roles) y dos eventos auditables. Segunda ejecución: `changed=False`, cero filas/eventos adicionales. [apply](apply.json), [no-op](apply_second.json).

## Backup y auditoría

El respaldo está fuera de Git, no sobrescribe otros backups y contiene los registros originales afectados, relaciones, perfiles y ledger anterior. El repo sólo contiene path/hash y evidencia mínima.

- SHA256: `b7336ad613d37a6e2fada7cc295360d3cb5636f16ed747d2eb542b94f086463e`.
- Antes/después, actor, workspace, permisos, resultados y ledger exacto: [effective_and_security.json](effective_and_security.json).
- Run de asignación: `fcee785b-8380-408e-a3f9-b9ffbd979a3c`. El actor global aprueba; el administrador Telchi asigna dentro de esos límites, sin permisos comerciales personales implícitos al administrador.
- La extensión autenticada `admin_cli manage-client` acepta `grant-sales` sólo para el catálogo exacto y requiere entitlement global aprobado. No admite permisos arbitrarios ni módulos externos.

## Reversión limitada

La retirada afecta sólo relaciones creadas por el run, verificando snapshot sin cambios. Conserva usuarios, permisos, roles, grant original, bootstrap previo y auditoría; no ejecuta DELETE genérico.

```bash
uv run python -m modules.telchi.provisioning.live_cli \
  --sales-activation --manifest "$PRIVATE_MANIFEST" --apply \
  --local-owner-bootstrap --rollback-sales-run fcee785b-8380-408e-a3f9-b9ffbd979a3c
```

Rehearsal real PG18: tras retirar las dos asignaciones el piloto resuelve sólo el permiso original; repetir reversión es no-op. La transacción de ensayo fue descartada; snapshot posterior idéntico al anterior. No se revocó el acceso activado al cierre.
