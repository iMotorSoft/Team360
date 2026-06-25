# Politica de validacion de navegador - Team360

## Objetivo

Definir una unica politica para pruebas de navegador en Team360,
diferenciando claramente:

- Playwright como gate E2E oficial.
- Browser MCP como herramienta exploratoria y de diagnostico visual.
- Cuando usar cada uno.
- Como levantar backend y frontend.
- Que condiciones deben cumplirse antes de declarar PASS.

## Regla central

Playwright + Chromium es el gate E2E oficial de Team360.

Toda validacion que deba proteger una regresion, comprobar un flujo completo o
aprobar un despliegue debe terminar con una prueba Playwright reproducible.

Browser MCP no reemplaza Playwright. Browser MCP puede ayudar a investigar,
observar y reproducir, pero no debe ser la unica evidencia para cerrar una
fase.

Regla final:

```text
Browser MCP ayuda a descubrir.
Playwright demuestra que quedo resuelto.
```

## Herramienta oficial

Playwright + Chromium es la herramienta oficial para gates E2E.

Usar Playwright cuando la validacion:

- protege una regresion;
- comprueba un flujo completo;
- valida interacciones conversacionales;
- valida interaction blocks;
- comprueba persistencia;
- comprueba requests duplicados;
- mide errores 5xx o errores criticos de consola;
- aprueba una fase;
- aprueba produccion o un despliegue.

Browser MCP puede acompañar esas tareas como observacion exploratoria, pero el
cierre debe quedar respaldado por Playwright cuando el objetivo sea estable o
regresivo.

## Instalacion disponible

Playwright esta disponible de dos formas.

### Instalacion local del proyecto

Es la forma preferida para tests permanentes:

```bash
corepack pnpm exec playwright test
```

Esta opcion usa la version declarada en el proyecto y evita diferencias entre
entornos.

### Instalacion global

Existe una instalacion global operativa:

```text
/usr/local/bin/playwright
```

Version observada:

```text
Playwright 1.61.0
```

Modulos globales:

```text
/usr/local/lib/node_modules
```

Para scripts Node independientes que importen Playwright globalmente puede ser
necesario:

```bash
NODE_PATH=/usr/local/lib/node_modules node script.js
```

La instalacion global es util para:

- pruebas temporales;
- diagnostico rapido;
- scripts fuera del arbol de Astro;
- comprobar disponibilidad del navegador.

No debe reemplazar los tests permanentes del proyecto.

## Chromium disponible

Chromium esta instalado en:

```text
/usr/bin/chromium-browser
```

Antes de una prueba aislada puede verificarse con:

```bash
which chromium-browser
chromium-browser --version
```

Los tests permanentes deben ejecutarse mediante el proyecto Chromium
configurado en Playwright:

```bash
--project=chromium
```

No asumir que un simple viewport movil equivale a un dispositivo tactil real.
Para errores moviles deben usarse ademas:

```typescript
hasTouch: true
isMobile: true
```

Preferentemente reutilizando un dispositivo oficial:

```typescript
devices["Pixel 5"]
```

## Launchers oficiales

Backend y Astro deben levantarse con los scripts oficiales del proyecto:

```bash
./backend-dev.sh
./astro-dev.sh
```

No iniciar manualmente Uvicorn o Astro con comandos alternativos salvo que el
launcher falle y se este diagnosticando ese fallo.

## Regla obligatoria para tests de paginas y E2E locales

Antes de probar paginas, componentes hidratados, flujos de usuario o tests
end-to-end locales, leer esta politica.

Para validaciones locales de paginas reales, los scripts `.sh` son los unicos
responsables de levantar y bajar el runtime:

```text
backend-dev.sh -> backend real en 127.0.0.1:7050
astro-dev.sh   -> Astro real en 127.0.0.1:3050
```

Playwright no debe levantar servidores para estos casos. Playwright debe usarse
solo como automatizador de navegador:

```text
Playwright abre Chromium, navega, interactua, observa red/DOM y valida.
No levanta backend.
No levanta Astro.
No inventa otro puerto.
No usa un proxy paralelo.
```

El `webServer` automatico de `playwright.config.ts` no representa el runtime
real de Team360 para `/t360`, paginas publicas o Console conectada. Usarlo para
cerrar funcionalidad real puede validar contra puertos, proxy o configuracion
distintos del entorno objetivo.

Por defecto, todo test local de pagina o E2E real debe ejecutarse con:

```bash
PLAYWRIGHT_SKIP_WEBSERVER=1
```

Si una prueba necesita usar el `webServer` automatico de Playwright, el agente
debe explicarlo antes de ejecutarla y dejar claro que no esta validando el
runtime real levantado por `backend-dev.sh` y `astro-dev.sh`.

Servicios permanentes:

```text
PostgreSQL
Milvus
LiteLLM
```

No deben iniciarse, detenerse ni reiniciarse automaticamente durante
validaciones. Solo se administran por pedido explicito.

## Configuracion local

Para pruebas locales, en:

```text
SrvRestAstroLS_v1/astro/src/components/global.js
```

debe estar:

```javascript
const IS_REST_PRO = false;
```

Esto permite que la UX local se conecte al backend local.

Secuencia canonica:

```bash
cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1

./backend-dev.sh
./astro-dev.sh
```

Verificacion:

```bash
curl -fsS http://127.0.0.1:7050/api/health

curl -fsS -o /dev/null -w 'astro=%{http_code}\n' \
  http://127.0.0.1:3050/
```

Base local oficial:

```text
http://127.0.0.1:3050
```

Para runtime real, aplicar tambien `[[service-preflight-methodology]]`.

## Variables estandar de Playwright local

Cuando backend y Astro ya fueron levantados con los scripts oficiales:

```bash
PLAYWRIGHT_SKIP_WEBSERVER=1 \
PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050 \
corepack pnpm exec playwright test \
  --project=chromium
```

`PLAYWRIGHT_SKIP_WEBSERVER=1` indica que Playwright no debe intentar iniciar
Astro, porque Astro ya esta corriendo mediante:

```bash
./astro-dev.sh
```

Esta variable es obligatoria para validar paginas reales locales y evitar el
webserver/proxy paralelo de Playwright.

`PLAYWRIGHT_BASE_URL` define la URL usada por tests que navegan con rutas
relativas:

```typescript
await page.goto("/");
```

En local:

```text
http://127.0.0.1:3050
```

En produccion:

```text
https://team360.live
```

## Pruebas contra produccion

Para validar la UX ya desplegada:

```bash
PLAYWRIGHT_SKIP_WEBSERVER=1 \
PLAYWRIGHT_BASE_URL=https://team360.live \
corepack pnpm exec playwright test \
  e2e/test-especifico.spec.ts \
  --project=chromium \
  --workers=1 \
  --reporter=line
```

Reglas:

- No levantar backend local.
- No levantar Astro local.
- No usar localhost.
- Usar `--workers=1`.
- No generar concurrencia innecesaria contra produccion.
- Ejecutar primero un test especifico.
- Ejecutar suite consolidada solo despues del PASS individual.
- No modificar produccion durante la validacion.

## Build productivo

Para generar el frontend productivo:

```javascript
const IS_REST_PRO = true;
```

Luego:

```bash
cd SrvRestAstroLS_v1/astro

corepack pnpm check
rm -rf dist
corepack pnpm build
```

El contenido desplegable queda en:

```text
SrvRestAstroLS_v1/astro/dist/
```

Regla:

```text
IS_REST_PRO=false -> desarrollo local y Playwright local
IS_REST_PRO=true  -> build productivo
```

No correr E2E locales apuntando a `127.0.0.1:3050` despues de cambiar
`IS_REST_PRO` a `true`.

## Que debe validar un E2E real

No aprobar un test solo porque aparecieron determinadas palabras.

Un E2E conversacional debe comprobar:

- mensaje enviado;
- respuesta nueva recibida;
- pregunta activa;
- interaction block visible;
- estado del bloque;
- opcion seleccionada;
- request enviado;
- response HTTP;
- persistencia del dato;
- ausencia de pregunta repetida;
- ausencia de requests duplicados;
- ausencia de errores 5xx;
- ausencia de errores criticos de consola.

Para interaction blocks:

```text
requires-response
-> interaccion
-> answered
```

Para bloques consecutivos:

```text
bloque A answered
-> bloque B nuevo
-> bloque B requires-response
```

No probar unicamente cada bloque por separado.

## Pruebas moviles

Un viewport movil no es suficiente.

Prueba incompleta:

```typescript
viewport: {
  width: 390,
  height: 844,
}
```

Prueba tactil correcta:

```typescript
test.use({
  ...devices["Pixel 5"],
  hasTouch: true,
  isMobile: true,
});
```

Usar:

```typescript
await option.tap();
```

ademas de pruebas con:

```typescript
await option.click();
```

Validar:

- `disabled`;
- `aria-disabled`;
- `pointer-events`;
- overlays;
- elemento detectado con `document.elementFromPoint`;
- contador;
- submit;
- request;
- estado posterior.

Una prueba desktop con viewport angosto no sustituye un test tactil.

## Cuando usar Browser MCP

Browser MCP se usa para:

- exploracion manual;
- inspeccion visual;
- entender el flujo actual;
- reproducir un bug rapidamente;
- revisar copy;
- navegar durante diagnostico;
- observar estados dificiles de explicar;
- verificar una hipotesis antes de escribir el E2E;
- capturar una reproduccion humana;
- identificar donde se congela la UX;
- comprobar si aparece un bloque inesperado;
- revisar responsive;
- detectar problemas de scroll o superposicion.

## Cuando Browser MCP no alcanza

Browser MCP no debe ser la unica validacion para:

- cerrar una fase;
- aprobar una regresion;
- aprobar produccion;
- comprobar persistencia;
- validar multiples sesiones;
- comprobar requests duplicados;
- medir 5xx;
- validar interaccion tactil;
- proteger un bug ya corregido;
- declarar que un flujo quedo estable.

Todo bug reproducido con Browser MCP debe, cuando sea razonable, convertirse en:

```text
test backend
+
test Playwright permanente
```

## Condiciones para usar Browser MCP

Antes de usar Browser MCP:

1. Confirmar que entorno se probara: local o produccion.
2. Si es local:
   - backend levantado con `backend-dev.sh`;
   - Astro levantado con `astro-dev.sh`;
   - `IS_REST_PRO=false`;
   - backend responde en `127.0.0.1:7050`;
   - Astro responde en `127.0.0.1:3050`.
3. Si es produccion:
   - usar `https://team360.live`;
   - no levantar servicios locales;
   - no modificar produccion.
4. Definir el objetivo:
   - copy;
   - layout;
   - comportamiento;
   - interaccion;
   - reproduccion de bug.
5. Registrar:
   - secuencia exacta;
   - mensaje enviado;
   - respuesta;
   - punto donde falla;
   - screenshot si es util.

No validar Browser MCP contra `4321`, `8000`, HTML directo, `curl`, lectura de
archivos, Playwright o rutas sueltas salvo que el objetivo lo pida
explicitamente.

## Detencion obligatoria ante falla de Browser MCP

Si Browser MCP falla, la prueba debe detenerse.

Fallas que obligan a detener:

- no abre la URL objetivo;
- no puede tomar snapshot;
- no detecta elementos esperados;
- no puede hacer click, fill o interactuar;
- pierde sesion o estado de pagina;
- devuelve referencias obsoletas sin posibilidad de renovar snapshot;
- no permite verificar el flujo solicitado;
- la herramienta `browsermcp_*` devuelve error;
- la pagina queda inaccesible desde el navegador aunque los servicios respondan.

En esos casos el agente debe informar:

- accion intentada;
- error o comportamiento observado;
- URL y paso donde fallo;
- estado conocido de backend `7050` y Astro `3050`;
- si reinicio algun servidor local;
- si la causa parece Browser MCP, frontend, backend o entorno;
- evidencia obtenida antes de detenerse, si existe.

No se debe reemplazar la validacion Browser MCP con terminal, `curl`, lectura de
HTML, Playwright, inspeccion de codigo ni suposiciones salvo autorizacion
explicita del usuario.

## Limitaciones de Browser MCP

Browser MCP puede producir falsos positivos o falsos negativos por:

- timing;
- hidratacion;
- cache;
- diferencias de navegador;
- ausencia de touch real;
- interaccion asistida distinta de un usuario;
- falta de assertions;
- dificultad para repetir exactamente el flujo.

Por eso su resultado debe interpretarse como:

```text
evidencia exploratoria
```

y no como:

```text
gate de release
```

## Regla de modelos para browser automation

Para validaciones visuales complejas y browser end-to-end:

```text
GPT-5.5 es el modelo preferido
```

DeepSeek V4 Flash puede utilizarse para:

- desarrollo;
- analisis de codigo;
- ejecucion de comandos;
- creacion de tests;
- correcciones acotadas.

Pero no debe considerarse el modelo mas confiable para automatizacion visual
compleja mediante navegador.

Si DeepSeek V4 Flash ejecuta Browser MCP, sus conclusiones deben ser
confirmadas por Playwright.

## Evidencia minima para PASS

Una validacion puede declararse PASS solo si incluye:

```text
test reproducible
resultado exacto
cantidad de tests
errores 5xx
errores de consola
requests duplicados
entorno usado
base URL
HEAD probado
```

Ejemplo:

```text
HEAD: 1195328
Base URL: https://team360.live
Playwright: 9/9 PASS
5xx: 0
Console critical errors: 0
Duplicate requests: 0
```

## Evidencia ante fallo

Ante un fallo conservar:

- trace;
- screenshot;
- video si esta habilitado;
- mensaje del usuario;
- respuesta de Vera;
- HTML del bloque;
- estado `data-interaction-state`;
- request;
- response;
- consola;
- base URL;
- HEAD;
- dispositivo;
- `hasTouch`;
- `isMobile`.

No corregir a ciegas sin conocer si la causa esta en:

```text
backend
frontend
estado persistido
hidratacion
touch
overlay
loading
cache
```

## Politica de regresiones

Despues de cambiar interaccion o runtime ejecutar, como minimo:

```text
Phone problems
Email orders
Kommo
Salesforce
New conversation
```

Cuando el alcance lo requiera:

```text
Adversarial
Social metadata
Mobile sequential blocks
Persistence
```

Las suites deben ejecutarse con:

```bash
--workers=1
```

cuando usan un backend compartido o produccion.

## Cierre de una fase

Una fase de navegador queda cerrada solo si:

```text
Browser MCP reproduce o inspecciona
-> se identifica causa
-> se agrega Playwright
-> Playwright falla antes del fix
-> se corrige
-> Playwright pasa
-> regresiones pasan
-> revision humana confirma
```

No declarar cerrado un problema movil hasta probar:

```text
hasTouch=true
isMobile=true
tap()
```

## Evidencia esperada en el cierre

Al cerrar una validacion de navegador, registrar:

- rama usada;
- entorno usado;
- base URL;
- HEAD probado;
- estado de backend `7050` y Astro `3050` cuando aplique local;
- si backend o Astro fueron bajados y levantados nuevamente;
- test reproducible ejecutado;
- cantidad exacta de tests;
- errores 5xx;
- errores criticos de consola;
- requests duplicados;
- pasos Browser MCP ejecutados, si se uso;
- snapshots o evidencia observada, si aplica;
- problemas detectados;
- si la prueba se detuvo por falla de Browser MCP;
- aclaracion explicita si la implementacion visual queda pendiente.

La bitacora tecnica principal para estos cierres sigue siendo
`SrvRestAstroLS_v1/docs/status_actual.md`.
