# Administración Console

BLOCKED para administración real autenticada. No se ejecutó el CLI con un token legítimo ni se hicieron mutaciones DB.

## Implementación inspeccionada

cli.py verifica token Console PASETO desde stdin y exige subject=user:user_id. service.py exige identidad activa en workspace y rol organization_admin activo. No se creó una consola paralela ni se utilizó bootstrap local como login.

Existen operaciones list, propose, alias, publish, retire, history, embed. Publicación requiere versión proposed. Auditoría escribe core_events con actor real suministrado por la frontera autenticada.

## Contratos no cerrados

ADM-01 a ADM-10 y negativos pendientes con sesiones reales. No hay contrato explícito de idempotency key ni expected_version en el servicio inspeccionado. propose usa upsert antes de max(version); no inferir que esto evita todos los conflictos comerciales.

Publicar una versión ya publicada devuelve proposed_version_required; esto no acredita publicación idempotente. La auditoría actual registra acción/resultados, pero no se acreditó cobertura íntegra de versión anterior, nueva y resultado de rechazos.

Estas brechas requieren prueba reproducible sobre DEV aislado antes de decidir un cambio mínimo; no se alteraron migraciones históricas ni permisos.
