# Mercado Libre Probes

Pruebas aisladas del laboratorio Mercado Libre.

Smoke disponible ahora:

`python -m modules.messaging.providers.mercadolibre.probes.smoke_login --profile default --timeout 180`

`python -m modules.messaging.providers.mercadolibre.probes.smoke_home_inspect --profile default --timeout 90`

`python -m modules.messaging.providers.mercadolibre.probes.smoke_summary_inspect --profile default --timeout 90`

`python -m modules.messaging.providers.mercadolibre.probes.smoke_inbox --profile default --timeout 90`

`python -m modules.messaging.providers.mercadolibre.probes.smoke_inbox_inspect --profile default --timeout 90`

Objetivo del smoke:

- abrir Chromium persistente
- permitir login manual
- validar si la sesion queda activa
- guardar screenshot y storage state

Objetivo del smoke home inspect:

- reutilizar sesion existente
- abrir la home autenticada
- listar links y botones visibles
- filtrar affordances candidatas por keywords de mensajes, ventas y cuenta
- guardar screenshot, storage state y reporte de inspeccion

Objetivo del smoke summary inspect:

- reutilizar sesion existente
- abrir el summary de cuenta autenticado
- listar links y botones visibles
- filtrar affordances candidatas por keywords de mensajes, preguntas, ventas, publicaciones, cuenta y ayuda
- guardar screenshot, storage state y reporte de inspeccion

Objetivo del smoke inbox:

- reutilizar sesion existente
- abrir una URL candidata de inbox/messages
- validar acceso basico al inbox
- estimar cantidad visible de hilos
- guardar screenshot y storage state

Objetivo del smoke inbox inspect:

- reutilizar sesion existente
- abrir el inbox autenticado
- contar matches por grupo de selectores
- capturar textos visibles de muestra por selector con matches
- guardar screenshot, storage state y reporte de inspeccion
