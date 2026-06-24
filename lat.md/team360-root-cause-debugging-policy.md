# Team360 Root Cause Debugging Policy

## Proposito

Definir una politica unica para investigar bugs no triviales en Team360,
especialmente cuando:

- los tests pasan pero la prueba manual encuentra un problema;
- Browser MCP reproduce un comportamiento inesperado;
- local y produccion difieren;
- el bug involucra interaction blocks, touch mobile, persistencia, requests,
  LiteLLM, Milvus, PostgreSQL o deploy.

Regla central:

```text
No corregir sin causa raiz verificable.
```

Esta politica adapta el concepto util de gstack `/investigate` a Team360 sin
adoptar el skill completo, su estado global, telemetry, hooks, freeze,
learnings cross-project ni commits automaticos.

## Cadena obligatoria

Todo bug no trivial debe avanzar por esta cadena:

```text
sintoma observado
→ reproduccion exacta
→ hipotesis de causa raiz
→ evidencia que confirma o descarta la hipotesis
→ fix minimo
→ test de regresion
→ validacion final
```

No alcanza con:

```text
tests pasan
```

si el usuario o una prueba manual encontro un problema real.

## Cuando aplica

Usar esta politica obligatoriamente cuando ocurra cualquiera de estos casos:

- bug reproducido manualmente aunque la suite pase;
- bug mobile/touch;
- bug de hydration, overlay, scroll, `pointer-events` o elemento tap/click;
- interaction block trabado, repetido, heredado como disabled o con estado
  incorrecto;
- request duplicado o request ausente;
- error 5xx, error critico de consola o response inesperado;
- diferencia entre `localhost` y `team360.live`;
- diferencia entre build local, dist remoto y assets servidos;
- persistencia inconsistente en PostgreSQL;
- retrieval o knowledge inesperado en Milvus;
- `fallback_used=true` cuando se esperaba modelo real;
- cambios de deploy donde el sitio responde pero ejecuta build viejo;
- un fix previo no resolvio el sintoma.

Para bugs simples, obvios y totalmente cubiertos por tests unitarios, puede
aplicarse una version reducida, pero la causa debe seguir siendo nombrada.

## Reproduccion

Antes de editar codigo, registrar:

```text
Sintoma:
Entorno:
Base URL:
HEAD:
Branch:
Session ID:
Mensaje exacto:
Resultado esperado:
Resultado observado:
Paso exacto donde falla:
```

Cuando aplique, agregar:

```text
Request:
Response:
HTTP status:
5xx:
Console critical errors:
Duplicate requests:
Device:
hasTouch:
isMobile:
Tap or click:
data-interaction-state:
```

Si no se puede reproducir de forma deterministica, no inventar una correccion.
Instrumentar, capturar evidencia o pedir el dato faltante.

## Hipotesis

Antes de corregir, escribir una hipotesis especifica:

```text
Root cause hypothesis: ...
```

La hipotesis debe ser verificable. Ejemplos validos:

```text
Root cause hypothesis: el bloque siguiente hereda disabled porque el frontend
usa el estado consumed del bloque anterior para todos los choices renderizados.
```

```text
Root cause hypothesis: mobile falla porque el test usa viewport angosto pero no
usa hasTouch/isMobile/tap, por eso no reproduce el bloqueo real de pointer events.
```

Ejemplos invalidos:

```text
Puede ser frontend.
```

```text
Tal vez es cache.
```

## Verificacion de hipotesis

Antes de aplicar un fix permanente:

1. Trazar el flujo desde el sintoma hasta el componente o modulo sospechado.
2. Revisar referencias con `rg`.
3. Revisar cambios recientes:

   ```bash
   git log --oneline -20 -- <archivo>
   ```

4. Confirmar la hipotesis con evidencia:

   - test que falla;
   - log temporal;
   - assertion;
   - trace Playwright;
   - request/response;
   - estado DOM;
   - query DB;
   - smoke real.

No dejar logs temporales o instrumentacion de diagnostico en el fix final salvo
que sean observabilidad intencional.

## Patrones frecuentes

Clasificar el bug si coincide con alguno de estos patrones:

| Patron | Senal | Donde mirar |
|---|---|---|
| Race/timing | Intermitente, depende de loading o hydration | frontend runtime, awaits, retries |
| Null/undefined | TypeError, campo ausente, default mal aplicado | normalizadores, DTOs, respuestas API |
| State corruption | estado persistido incoherente | PostgreSQL, session state, semantic memory |
| Integration failure | timeout, response inesperada | LiteLLM, Milvus, backend API, proxy |
| Configuration drift | local pasa, produccion falla | env vars, `IS_REST_PRO`, assets, Nginx |
| Stale cache/build | produccion parece vieja | `dist`, hashes Astro, curl HTML, assets |
| Touch mismatch | desktop pasa, mobile falla | `hasTouch`, `isMobile`, `tap`, overlays |

## Regla de tres hipotesis

Si tres hipotesis verificadas fallan:

```text
DETENER
```

Reportar:

```text
Hipotesis probadas:
Evidencia negativa:
Archivos inspeccionados:
Por que no conviene seguir parcheando:
Recomendacion:
```

En ese punto puede tratarse de un problema de arquitectura, contrato, estado
persistido o entorno, no de una linea aislada.

## Scope del fix

El fix debe ser el cambio mas chico que elimine la causa raiz.

Reglas:

- no refactor lateral;
- no tocar frontend y backend a la vez salvo causa demostrada;
- no tocar deploy, Nginx o servicios reales salvo que la evidencia apunte ahi;
- no mezclar mejora cosmetica con fix de bug;
- si el fix toca mas de 5 archivos, justificar el blast radius antes de seguir.

## Test de regresion

Todo bug manual repetible debe convertirse, cuando sea razonable, en:

```text
test backend
+
test Playwright permanente
```

La eleccion depende de la causa:

| Causa | Test minimo |
|---|---|
| Runtime backend, slots, classifier, persistence | pytest especifico |
| Interaction block, DOM, click/tap, hydration | Playwright Chromium |
| Mobile/touch | Playwright con `devices["Pixel 5"]`, `hasTouch`, `isMobile`, `tap()` |
| Deploy/build/assets | verificacion de build/dist/assets + smoke productivo |
| Modelo real/fallback | smoke backend con `fallback_used=false` |

El test debe fallar sin el fix o, si no es posible conservar esa evidencia, el
reporte debe explicar por que.

## Relacion con Browser MCP y Playwright

Browser MCP ayuda a descubrir o reproducir.

Playwright demuestra que el bug quedo protegido.

Flujo recomendado:

```text
prueba manual o Browser MCP reproduce
→ root cause debugging identifica causa
→ Playwright o pytest falla antes del fix
→ fix minimo
→ Playwright o pytest pasa
→ smoke manual confirma si aplica
```

No cerrar un bug visual/manual solo con Browser MCP.
No cerrar un bug reproducible solo con "tests pasan" si esos tests no cubren el
caso observado.

## Relacion con servicios reales

Si la investigacion depende de PostgreSQL, Milvus, LiteLLM, modelo real,
variables de entorno o proveedores externos, ejecutar primero la metodologia de
preflight:

```text
[[service-preflight-methodology]]
```

No interpretar una falla de preflight como calidad del modulo investigado.

## Relacion con despliegues

Ante un bug posterior a deploy:

- no repetir `rsync` a ciegas;
- no reiniciar servicios automaticamente;
- comparar source, build, dist remoto y assets servidos;
- confirmar HEAD, base URL y entorno;
- seguir las politicas:

```text
[[team360-frontend-rsync-deploy-policy]]
[[team360-backend-rsync-deploy-policy]]
```

## Reporte obligatorio

Toda investigacion cerrada debe entregar:

```text
DEBUG REPORT

Symptom:
Environment:
Base URL:
HEAD:
Root cause hypothesis:
Root cause:
Fix:
Evidence:
Regression test:
Browser validation:
Backend validation:
5xx:
Console critical errors:
Duplicate requests:
Residual risk:
Status:
```

Estados permitidos:

```text
DONE
DONE_WITH_CONCERNS
BLOCKED
```

`DONE` requiere causa raiz identificada, fix aplicado, test de regresion o
justificacion explicita, y validacion final.

## Regla final

```text
Manual descubre.
Investigacion explica.
Tests protegen.
Validacion confirma.
```
