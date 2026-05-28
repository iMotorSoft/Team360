# Browser Automation Y Desktop Automation

Browser automation y desktop automation son workers posibles, no canales directos al cliente.

El cliente interactua con Team360. Team360 valida permisos, crea job, audita eventos y delega en package_worker interno o externo.

## Browser Automation

Sirve para portales autorizados, backoffices, marketplaces y sistemas sin API disponible.

Debe usarse con perfil persistente, screenshots, logs, deteccion de login y fallback humano.

No debe usarse para pelear contra anti-bot agresivo ni violar terminos.

## Desktop Automation

Sirve para aplicaciones Windows, ERP Desktop y procesos repetitivos visuales.

Requiere sesion controlada, resolucion estable, manejo de popups, evidencia visual y aprobacion humana para acciones sensibles.

## Workers

En Fase 1 los workers pueden ser modulos internos. Deben tener contrato de input/output, allowed_actions, blocked_actions, modo operativo y correlation_id.

Mas adelante pueden migrar a procesos externos, colas, servicios independientes, browser workers o desktop workers.
