# Administración Console

CONSOLE_REAL_RBAC=BLOCKED. Existe administración service/CLI integrada al verificador Console; no existe evidencia de una sesión humana Console válida ni de una UI semántica autenticada.

## Implementación frente a validación

La inspección se limita al alcance Business Semantics y no cambia autenticación compartida.

BusinessConceptAdministration autoriza organization_admin activo dentro del workspace/organización; no usa default_admin. CLI recibe PASETO por stdin, exige coincidencia subject/user_id y consulta DB para autorización efectiva. La vía local-owner-bootstrap sólo sirve para seed/migración, no satisface pruebas Console.

No se ejecutó list/history con una identidad real no autenticada. history utiliza owned/FOR UPDATE: no reutilizar indiscriminadamente ese camino como una sonda PostgreSQL READ ONLY.

## Matriz pendiente

Los resultados requieren login legítimo y rol runtime validado, no tokens sintéticos ni grants agregados para el test.

| Contrato | Estado |
| --- | --- |
| Leer conceptos con sesión real | NOT_EXECUTED |
| Crear propuesta y versión | NOT_EXECUTED |
| Aprobar/publicar autorizado | NOT_EXECUTED |
| Retirar | NOT_EXECUTED |
| Rechazar lector/tenant ajeno y actor inválido | NOT_EXECUTED |
| Actor real y preservación de auditoría | NOT_EXECUTED |
| Idempotencia | NOT_EXECUTED |
| Concurrencia y persistencia | NOT_EXECUTED |

Por inspección, publish exige proposed_version y rechaza repetición; retire retorna changed=true y audita incluso si ya está retirado. No asumir idempotencia HTTP o auditoría exactly-once a partir del seed idempotente. UPSERT/owned usan locks, pero no sustituyen una prueba de carrera real.

No se implementaron fixes sin evidencia operacional. Próximo paso: resolver [AUTHENTICATED_USERS.md](AUTHENTICATED_USERS.md) y [ROLE_PRIVILEGES.md](ROLE_PRIVILEGES.md), ejecutar la matriz en DEV y corregir sólo un defecto reproducido dentro del scope autorizado.
