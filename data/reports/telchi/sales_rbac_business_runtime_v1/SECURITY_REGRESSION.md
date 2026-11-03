# Security regression

Controles negativos sin crear usuarios ni alterar grants ajenos. [effective_and_security.json](effective_and_security.json) distingue identidades PG de fixtures; positivos empresariales sólo se acreditan por HTTP real.

## Matriz de autorización

Los handlers negativos usan persistencia/interpretación aisladas; permisos actuales de identidades existentes se leen de PG sin impersonar sesiones ni enviar mensajes operacionales de esos usuarios.

| Caso | Resultado | Queries | Evidencia |
| --- | --- | --- | --- |
| existing_telchi_admin_without_business_permission | DENIED | 0 | identidad existente, permisos PG |
| existing_team360_actor_other_tenant | DENIED | 0 | identidad existente, permisos PG |
| wrong_workspace_fixture | DENIED | 0 | fixture aislada |
| module_not_enabled_fixture | DENIED | 0 | fixture aislada |
| new_capability_without_permission_fixture | DENIED | 0 | fixture aislada |
| outside_catalog_fixture | ERROR | 0 | fixture aislada |
| committed_false_fixture | ERROR | 0 | fixture aislada |

Usuario piloto autorizado: ambos permisos efectivos y ejecución empresarial positiva por HTTP. Sin permiso, otro tenant y workspace incorrecto: DENIED. Módulo deshabilitado y nueva capability sin grant: DENIED. Fuera del catálogo y committed=False: rechazo sin ejecución, incluso ante output EXECUTE.

## Frontera HTTP y administración

El adapter permanece opt-in/token/loopback; no acepta identidades suministradas por el cliente. El CLI tampoco acepta permisos arbitrarios ni delegación sin aprobación global.

- [security_http/security_results.json](security_http/security_results.json): token ausente/incorrecto 401; body inválido/user_id/phone 400; rutas Console/webhook 404; health 200; token/teléfono ausentes del log; sesiones y concurrencia aisladas.
- Tests administrativos rechazan PROD, permisos globales, permisos extra, otros módulos, acciones SQL libres y falta de entitlement antes de asignar.
- Regresión del handler: revalidación PG del grant nuevo, permisos faltantes y committed=False; contrato B02 no elimina el guard ni el grant coverage.
- Rollback rehearsal no persiste, idempotencia confirmada y original source_quantity preservado.
- No bypass del resolver telefónico, default_admin, permission fallback, SQL libre o outbound transport.
