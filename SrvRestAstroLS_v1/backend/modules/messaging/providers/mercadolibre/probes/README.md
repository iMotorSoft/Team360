# Mercado Libre Probes

Pruebas aisladas del laboratorio Mercado Libre.

Smoke disponible ahora:

`python -m modules.messaging.providers.mercadolibre.probes.smoke_login --profile default --timeout 180`

Objetivo del smoke:

- abrir Chromium persistente
- permitir login manual
- validar si la sesion queda activa
- guardar screenshot y storage state
