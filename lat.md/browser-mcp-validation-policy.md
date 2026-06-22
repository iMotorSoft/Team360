# Browser MCP Validation Policy

## Proposito

Esta regla define como usar Browser MCP / `opencode-browser` para validaciones
visuales y end-to-end de Team360.

Aplica cuando un agente debe navegar la experiencia real en navegador, en
particular la Home publica y Vera en:

```text
http://127.0.0.1:3050/t360
```

## Regla central

Browser MCP valida la experiencia real servida por Astro contra el backend real
esperado. Antes de iniciar la fase browser, deben estar levantados los
servidores locales canonicos:

```text
Backend Litestar: http://127.0.0.1:7050
Astro frontend:  http://127.0.0.1:3050
```

Si backend o Astro no responden, responden desde un proceso viejo, usan una
configuracion dudosa o quedaron en un estado inconsistente, el agente puede
bajarlos y volver a levantarlos para la prueba.

Esta autorizacion aplica solo a los procesos locales de backend y Astro usados
por la validacion. No autoriza apagar, reiniciar, migrar ni modificar servicios
permanentes como PostgreSQL, Milvus o LiteLLM salvo pedido explicito.

## Precondiciones obligatorias

Antes de usar Browser MCP:

1. verificar que el backend responde en `127.0.0.1:7050`;
2. verificar que Astro responde en `127.0.0.1:3050`;
3. confirmar que la URL objetivo abre desde Astro, normalmente
   `http://127.0.0.1:3050/t360`;
4. si la prueba usa runtime real, cumplir `[[service-preflight-methodology]]`;
5. dejar claro si se reinicio backend, Astro o ambos para la prueba.

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

## Uso correcto durante la fase browser

Durante la validacion:

- usar herramientas `browsermcp_*` para navegar e interactuar;
- abrir la URL real servida por Astro;
- ejecutar snapshot antes de interactuar;
- usar referencias actuales del snapshot;
- ejecutar nuevo snapshot despues de cada accion que cambie la interfaz;
- no reutilizar referencias de snapshots anteriores si la pagina cambio;
- esperar estados asincronos antes de concluir;
- no inventar contenido visual que no aparece en el snapshot;
- no declarar validada una estetica, comportamiento o componente que todavia no
  fue implementado.

## Alcance de la evidencia

Browser MCP puede documentarse como herramienta exitosa cuando:

- interactuo con la experiencia real;
- recorrio el flujo en navegador;
- permitio observar comportamiento de UI;
- ayudo a detectar problemas de densidad, duplicacion, jerarquia visual,
  responsive o interaccion;
- genero evidencia util para decidir proximos cambios.

Browser MCP no debe documentarse como validacion de una implementacion futura o
no realizada.

Formulacion correcta cuando se usa para una decision UX previa a implementar:

```text
Browser MCP fue utilizado con exito para validar el flujo actual y detectar
problemas de densidad, duplicacion y jerarquia visual. La nueva propuesta UX
queda pendiente de implementacion y posterior validacion visual.
```

## Evidencia esperada en el cierre

Al cerrar una validacion Browser MCP, registrar:

- rama usada;
- URL recorrida;
- estado de backend `7050` y Astro `3050`;
- si backend o Astro fueron bajados y levantados nuevamente;
- pasos browser ejecutados;
- snapshots o evidencia observada;
- problemas detectados;
- si la prueba se detuvo por falla de Browser MCP;
- confirmacion de que no se sustituyo Browser MCP por otra herramienta sin
  autorizacion;
- aclaracion explicita si la implementacion visual queda pendiente.

La bitacora tecnica principal para estos cierres sigue siendo
`SrvRestAstroLS_v1/docs/status_actual.md`.
