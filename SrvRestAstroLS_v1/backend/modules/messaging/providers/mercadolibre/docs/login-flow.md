# Login Flow

Flujo real actual del laboratorio de browser automation para entrar a Mercado Libre y dejar una sesion reutilizable.

## Objetivo

Validar acceso manual a Mercado Libre desde un browser persistente y dejar lista la sesion para probes posteriores como home, summary, questions e inbox.

## Punto de entrada

Ejecutar desde `SrvRestAstroLS_v1/backend`:

```bash
python -m modules.messaging.providers.mercadolibre.probes.smoke_login --profile default --timeout 180
```

## Flujo

1. Abre Chromium con perfil persistente en `modules/messaging/providers/mercadolibre/runtime/profiles/<profile>`.
2. Navega a `https://www.mercadolibre.com.ar/`.
3. Evalua si ya existe sesion activa.
4. Si la sesion ya esta activa, no fuerza login y solo guarda artifacts.
5. Si no hay sesion, intenta abrir un entrypoint visible de login.
6. Espera que el operador complete el login manual en la ventana del browser.
7. Vuelve a evaluar la sesion hasta que quede validada o venza el timeout.
8. Guarda screenshot y `storage_state` para reutilizar la sesion en otras corridas.

## Heuristica de sesion activa

La sesion se considera activa si ocurre al menos una de estas condiciones:

- hay affordances visibles de cuenta, perfil o menu de usuario
- la URL actual contiene hints de cuenta como `/myml` o `/perfil`
- como fallback debil, existen cookies de sesion conocidas como `orguseridp` o `ssid`

La sesion se considera no autenticada si sigue visible un prompt de login o si la URL cae en rutas de login o registro.

## Entry points de login

El smoke intenta usar selectores conservadores como:

- `a[data-link-id='login']`
- `a[href*='login']`
- `a[href*='registration']`
- `button[data-link-id='login']`
- textos tipo `Ingresa`, `Iniciar sesion` o equivalentes

## Artefactos generados

- perfil persistente: `modules/messaging/providers/mercadolibre/runtime/profiles/<profile>`
- screenshot: `modules/messaging/providers/mercadolibre/runtime/screenshots/`
- storage state: `modules/messaging/providers/mercadolibre/runtime/storage_state/<profile>.json`

## Uso esperado

1. Correr `smoke_login`.
2. Completar credenciales y cualquier desafio manual directamente en la ventana del browser.
3. Esperar que la consola informe `login validado`.
4. Reutilizar el mismo `--profile` para correr probes autenticados.

## Probes que reutilizan la sesion

- `python -m modules.messaging.providers.mercadolibre.probes.smoke_home_inspect --profile default --timeout 90`
- `python -m modules.messaging.providers.mercadolibre.probes.smoke_summary_inspect --profile default --timeout 90`
- `python -m modules.messaging.providers.mercadolibre.probes.smoke_questions_inspect --profile default --timeout 90`
- `python -m modules.messaging.providers.mercadolibre.probes.smoke_questions_list_inspect --profile default --timeout 90`
- `python -m modules.messaging.providers.mercadolibre.probes.smoke_inbox --profile default --timeout 90`
- `python -m modules.messaging.providers.mercadolibre.probes.smoke_inbox_inspect --profile default --timeout 90`

## Limitaciones actuales

- el login sigue siendo manual
- la deteccion de sesion es heuristica y conservadora
- Mercado Libre puede variar DOM, rutas, labels y experimentos visuales
- `storage_state` se guarda como soporte de debugging, pero la fuente principal de continuidad es el perfil persistente
