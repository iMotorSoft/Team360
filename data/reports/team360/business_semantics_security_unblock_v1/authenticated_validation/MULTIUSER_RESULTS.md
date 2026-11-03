# Resultados multiusuario

TWO_USERS=BLOCKED; USER_STATE_ISOLATION=BLOCKED. U1 y U2 no fueron autenticados ni usados en operaciones reales. No se reinició ningún servicio.

## Matriz operacional

Todos los resultados indican falta de evidencia auténtica, no fallo lógico demostrado. Tests con MemoryStore no se contabilizan como usuarios reales.

| Prueba | Estado | Evidencia faltante |
| --- | --- | --- |
| MU-01 | BLOCKED | Dos logins humanos y negativas contraseña/expired/tampered/disabled/lockout sin exponer secretos |
| MU-02 | BLOCKED | Lectura publicada autorizada U1/U2; CLI list es admin-only |
| MU-03 | BLOCKED | Contextos distintos producto/cliente/período/métrica por actor |
| MU-04 | BLOCKED | Repregunta real mantiene exclusivamente contexto U1 |
| MU-05 | BLOCKED | Persistencia tras reinicio sólo de servicio DEV propio seguro |
| MU-06 | BLOCKED | Auditoría operacional conserva actor real U1/U2 |
| MU-07 | BLOCKED | Denegación admin con sesión humana de consulta |

## Garantías inspeccionadas

ConversationRepository filtra thread/event por workspace/channel/IDs y coteja owner=[environment,tenant,workspace,channel,user] también en caché. No prueba ejecución real ni sustituye autorización inicial del handler.

[STATE_ENGINE_REGRESSION.md](STATE_ENGINE_REGRESSION.md) separa contratos deterministas reutilizados de persistencia/reinicio humano no observado. El adapter HTTP existente está ligado a teléfono piloto/configuración DEV, no a estas sesiones PASETO: no se usó para simular dos personas.
