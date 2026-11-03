# Bloqueos abiertos

No se demostró fallo funcional nuevo. Los bloqueos son evidencia humana/ruta operacional/configuración, no necesidad de reconstruir login o PostgreSQL.

## Dependencias concretas

Cada dependencia mantiene sus garantías separadas; una acción humana de enrollment no cierra los otros contratos por sí sola.

| Bloqueo | Intervención mínima / responsable |
| --- | --- |
| Credenciales y sesiones U1–U4 ausentes | Operador/personas: designación, consentimiento y comandos getpass del runbook |
| U1/U2 consulta/conversación no acreditada vía PASETO | Acreditar consumidor soportado y verificación principal/permisos; list es admin-only, HTTP piloto no es login humano multiusuario |
| Rol runtime Srv05 | Ventana controlada propia con política/lifecycle seguro y observar conexión real; configuración actual global usa administrator. No cambiar pool global en esta tarea |
| RLS inexistente | Mantener honestidad sobre defensa DB; demostrar exhaustivamente rutas de aplicación autenticadas, no activar RLS automáticamente |
| Tenant B y fixtures privados controlados | Designar organización real, autorizar datos DEV de prueba y ejecutar MT con sesiones, sin publicar candidatos comerciales |
| Admin CLI / auditoría / idempotencia / concurrencia | Sesión U4; comprobar operaciones soportadas, semántica de reintento y ruta de lectura audit autorizada |
| Calibración pgvector | Sesión legítima, config explícita alias/revision/dim y preflight provider/quota/fallback; 16+16 corpus intacto; congelar parámetros antes de holdout |
| Persistencia/reinicio | Sólo servicio propio seguro tras resolver ruta de sesiones; no reiniciar servicios compartidos |

## Acciones realizadas y límites

Se ejecutó lectura efectiva con rol dedicado, revalidación de destino/privilegios, audit corpus/hashes y 28 tests focalizados; no se detuvo en inventario. Informes contienen resultados reproducibles, no una nueva arquitectura.

Ninguna contraseña activada, sesión fabricada, escritura DB, cambio de grants/RLS/pool, seed, llamada SAP/Foundation, modificación Messaging/Evolution/frontend ni deploy/commit. Sin iniciar procesos persistentes propios. Python raíz no disponible; comando auxiliar reejecutado con python3, sin defecto funcional.

Siguiente paso humano: [HUMAN_ACTION_REQUIRED.md](HUMAN_ACTION_REQUIRED.md). No hay comandos existentes whoami ni standard-query en este runbook; no se inventaron ni se concedió FULL_ACCESS. Tras sesiones, cerrar sólo pruebas pendientes dentro del TTL y gates A/B/C separados.
