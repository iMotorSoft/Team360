# DeepSeek V4 Flash + opencode-browser

Guia operativa para usar DeepSeek V4 Flash con el plugin `opencode-browser`
dentro de OpenCode sobre Team360.

Este documento clasifica el uso validado, las restricciones, los prompts base y
la forma de extender una validacion browser hacia backend sin que el agente
reemplace la experiencia real de usuario por terminal, codigo o HTML.

## Clasificacion

| Eje | Clasificacion |
|---|---|
| Tipo de documento | Invariante operativo transversal para agentes |
| Alcance | OpenCode + DeepSeek V4 Flash + `opencode-browser` |
| Producto validado | Team360 public Home / Vera en `/t360` |
| URL validada | `http://127.0.0.1:3050/t360` |
| Modelo | DeepSeek V4 Flash |
| Plugin | `opencode-browser` con tools `browsermcp_*` |
| Uso recomendado | Browser QA dirigido, smoke tests, validacion frontend/backend acotada |
| Uso no recomendado | QA visual fino, comparacion contra mockups, debugging ambiguo o refactors amplios |
| Estado | Validado operativamente |
| Veredicto | Apto si el prompt fija herramientas, fases, snapshots, evidencia, restricciones y punto de detencion |

## Objetivo

Usar DeepSeek V4 Flash como orquestador textual para navegar, inspeccionar e
interactuar con aplicaciones web mediante `opencode-browser`, sin que el agente
se desvie hacia lectura de archivos, terminal, Playwright manual o cambios de
codigo cuando la tarea es verificar UI real.

La conclusion validada es:

> DeepSeek V4 Flash funciona correctamente con `opencode-browser` cuando el
> prompt define con claridad las herramientas, las fases, las acciones
> permitidas, la evidencia esperada y el punto de detencion.

No se detecto una incompatibilidad entre el modelo y el plugin. El problema
observado en prompts amplios era de disciplina de prompt: el navegador quedaba
como instruccion secundaria dentro de una tarea demasiado abierta.

## Resultado validado

DeepSeek V4 Flash pudo:

- navegar a una URL local;
- ejecutar snapshots del navegador;
- identificar titulos, secciones, campos y botones;
- localizar elementos mediante referencias del snapshot;
- hacer clic sobre elementos especificos;
- detectar cambios en la interfaz;
- completar campos;
- enviar mensajes;
- esperar respuestas asincronas;
- reconocer estados como `Vera está escribiendo...`;
- leer respuestas completas;
- identificar cambios de formulario a interfaz de chat;
- correlacionar un `conversation_id` visible en frontend con el almacenado en backend;
- inspeccionar PostgreSQL con consultas de solo lectura;
- detectar proveedores activos de estado, LLM, retrieval y embeddings;
- distinguir truncamiento visual de un problema de integridad;
- recurrir a base de datos cuando los logs no contenian evidencia suficiente.

## Problema inicial

El plugin funcionaba con prompts simples, por ejemplo:

```text
Abrí en el navegador http://127.0.0.1:3050/t360
```

En prompts mas grandes el modelo podia:

- ignorar el navegador;
- inspeccionar codigo antes de navegar;
- usar terminal como reemplazo;
- proponer cambios sin validar la interfaz;
- mezclar demasiadas fases;
- continuar mas alla de lo solicitado;
- interpretar que "revisar la aplicacion" significaba leer archivos.

El browser debe aparecer como herramienta obligatoria y fase atomica, no como
una sugerencia dentro de una tarea abierta.

## Patron principal

El patron mas confiable para DeepSeek V4 Flash es:

```text
navegar
-> snapshot
-> identificar referencia
-> realizar una accion
-> esperar cambio
-> nuevo snapshot
-> informar evidencia
-> detenerse
```

La estructura del prompt debe incluir:

```text
herramienta obligatoria
+ estado inicial
+ accion concreta
+ snapshot
+ condicion de espera
+ evidencia esperada
+ restricciones
+ detencion explicita
```

## Reglas obligatorias

- Antes de iniciar Browser MCP sobre Team360, aplicar `[[browser-mcp-validation-policy]]`: Playwright + Chromium es el gate E2E oficial; Browser MCP / `opencode-browser` es evidencia exploratoria y de diagnostico visual; backend `127.0.0.1:7050` y Astro `127.0.0.1:3050` deben estar levantados cuando se prueba local; si Browser MCP falla, la prueba se detiene y se informa.
- Para navegar e interactuar con paginas, usar herramientas `browsermcp_*` del plugin `opencode-browser`.
- No usar `curl`, `wget`, Playwright desde terminal ni lectura directa del HTML como reemplazo del navegador.
- No declarar cerrada una fase, regresion o validacion productiva solo con Browser MCP; confirmar con Playwright cuando el resultado deba quedar como PASS reproducible.
- Ejecutar snapshot antes de interactuar.
- Usar referencias actuales del snapshot para click, fill o inspeccion.
- Ejecutar nuevo snapshot despues de cada accion que cambie la interfaz.
- No reutilizar referencias de snapshots anteriores si la pagina cambio.
- Esperar respuestas y estados asincronos antes de concluir.
- No inventar contenido visual que no aparezca en el snapshot.
- Si una tool browser falla, informar el error exacto.
- Detenerse cuando el prompt lo indique.

## Uso correcto de snapshots

Antes de cada interaccion:

1. ejecutar `browsermcp_browser_snapshot`;
2. localizar el elemento;
3. tomar la referencia actual;
4. interactuar con esa referencia.

Despues de un click, render dinamico, envio de chat, navegacion o respuesta
asincrona, ejecutar otro snapshot. Las referencias pueden quedar obsoletas.

## Prompt inicial recomendado

Usar al crear una sesion nueva de OpenCode para confirmar que el plugin esta
disponible y fijar el contrato de browser.

```text
Vas a trabajar con la aplicacion Team360 usando el plugin opencode-browser.

Reglas obligatorias para el navegador:

- Para navegar e interactuar con paginas, usa las herramientas `browsermcp_*` del plugin opencode-browser.
- No uses `curl`, `wget`, Playwright desde terminal ni lectura directa del HTML como reemplazo del navegador.
- Antes de interactuar, ejecuta un snapshot para obtener las referencias actuales de los elementos.
- Usa las referencias del snapshot para hacer clic, completar campos o inspeccionar controles.
- Despues de cada accion que cambie la interfaz, ejecuta un nuevo snapshot.
- No reutilices referencias de snapshots anteriores si la pagina cambio.
- Espera las respuestas y estados asincronos antes de concluir.
- No inventes contenido visual que no aparezca en el snapshot.
- Si una herramienta browser falla, informa el error exacto.
- No modifiques codigo durante esta prueba inicial.

Prueba inicial obligatoria:

1. Abrí con opencode-browser:
   http://127.0.0.1:3050/t360

2. Ejecuta `browsermcp_browser_snapshot`.

3. Confirma que encuentras:
   - el titulo principal "Team360";
   - la seccion "Hablá con Vera";
   - el campo "Mensaje para Vera";
   - al menos un boton de ejemplo.

4. No hagas clic ni envies mensajes todavia.

5. Informa unicamente:
   - URL final;
   - titulo principal;
   - si encontraste "Hablá con Vera";
   - botones de ejemplo visibles;
   - nombre del campo de texto;
   - errores visibles.

Detente al terminar esta verificacion.
```

## Prompt minimo de navegacion

```text
Usa exclusivamente las herramientas del plugin opencode-browser.

Tarea unica:

1. Abrí:
   http://127.0.0.1:3050/t360

2. Espera a que la pagina termine de cargar.

3. Ejecuta un snapshot.

4. Informa solamente:
   - URL final;
   - titulo principal visible;
   - si existe la seccion "Hablá con Vera".

Restricciones:

- No uses terminal.
- No abras archivos.
- No modifiques codigo.
- No propongas mejoras.
- No hagas ninguna accion adicional.

Finaliza despues de informar esos tres puntos.
```

## Prompt de inspeccion de interfaz

```text
Entra en modo QA de navegador.

Usa exclusivamente opencode-browser sobre:

http://127.0.0.1:3050/t360

Objetivo unico:

Verificar visualmente que la Home publica de Team360 carga correctamente.

Pasos:

1. Abrí la URL.
2. Ejecuta un snapshot.
3. Busca estos textos visibles:
   - "Team360"
   - "Ver diagnóstico inicial"
   - "Hablá con Vera"
4. Baja hasta la seccion de Vera.
5. Ejecuta un nuevo snapshot.
6. Informa que elementos interactivos visibles encuentras.

Restricciones:

- No abras archivos del proyecto.
- No uses terminal.
- No edites codigo.
- No investigues la implementacion.
- No inventes resultados.
- Si una herramienta falla, informa el error exacto y detente.

Termina despues del informe.
```

## Prompt de interaccion basica

Prueba que el modelo puede seleccionar un ejemplo y detectar el cambio de
estado sin confundir seleccion con envio.

```text
Usa exclusivamente las herramientas de opencode-browser.

Abrí:

http://127.0.0.1:3050/t360

Tarea unica:

1. Localiza el boton:
   "Recibo leads por WhatsApp y no sé quién los sigue."

2. Haz clic una sola vez.

3. Ejecuta un snapshot despues del clic.

4. Informa:
   - texto exacto del boton utilizado;
   - contenido del campo;
   - si el boton "Enviar" quedo habilitado;
   - si aparecio una respuesta;
   - errores visibles.

Restricciones:

- No uses terminal.
- No leas ni modifiques archivos.
- No analices codigo.
- No hagas mas de un clic.
- No envies el mensaje todavia.
- No propongas cambios.

Detente inmediatamente despues del informe.
```

Resultado esperado:

- el boton de ejemplo completa el campo;
- `Enviar` pasa de deshabilitado a habilitado;
- todavia no hay respuesta de Vera;
- no hay errores visibles.

## Prompt para enviar mensaje y esperar respuesta

```text
Continua la validacion usando exclusivamente opencode-browser.

Estado esperado:

- La pagina esta abierta en:
  http://127.0.0.1:3050/t360

- El campo "Mensaje para Vera" contiene:
  "Recibo leads por WhatsApp y no sé quién los sigue."

- El boton "Enviar" esta habilitado.

Tarea unica:

1. Ejecuta un snapshot para confirmar el estado actual.
2. Haz clic una sola vez en "Enviar".
3. Espera hasta que ocurra una de estas condiciones:
   - aparezca una respuesta de Vera;
   - aparezca una pregunta nueva;
   - aparezca un error visible;
   - el estado deje de cambiar.
4. Ejecuta un snapshot final.
5. Informa:
   - si el mensaje aparecio en la conversacion;
   - si Vera respondio;
   - texto exacto de la respuesta;
   - estados de carga observados;
   - errores visibles;
   - estado final del campo;
   - ID visible de conversacion;
   - numero de turno.

Restricciones:

- No uses terminal.
- No abras archivos.
- No modifiques codigo.
- No recargues la pagina.
- No respondas una segunda pregunta.
- No hagas clic en ningun otro elemento.
- No inventes contenido.

Detente despues del informe.
```

Resultado observado:

- mensaje enviado;
- respuesta completa de Vera;
- estado `Vera está escribiendo...`;
- desaparicion del indicador de carga;
- transicion del formulario inicial a interfaz de chat;
- campo `Escribí tu mensaje...`;
- boton `Nueva conversacion`;
- `conversation_id`;
- etiqueta `Turno 1`;
- ausencia de errores visibles.

## Validacion integral frontend/backend

Usar solo despues de verificar que el flujo browser funciona.

Cadena a comprobar:

```text
Home /t360
-> frontend de Vera
-> request HTTP
-> backend Litestar
-> PostgreSQL
-> LiteLLM
-> modelo LLM
-> Milvus
-> respuesta renderizada
```

Reglas:

- Para UI usar exclusivamente `browsermcp_*`.
- Ejecutar snapshot antes de cada interaccion.
- Ejecutar snapshot despues de cada cambio de interfaz.
- No reutilizar referencias viejas.
- Para backend se permite terminal, logs y PostgreSQL de solo lectura.
- No modificar archivos.
- No reiniciar PostgreSQL, Milvus ni LiteLLM salvo pedido explicito.
- Se permite bajar y volver a levantar backend y Astro locales si no responden
  en `7050/3050`, quedaron viejos o el entorno es ambiguo.
- No ejecutar migraciones.
- No hacer commits.
- No mostrar secretos.
- No usar `curl` para reemplazar el flujo del navegador.

### Prompt integral recomendado

```text
La integracion con opencode-browser quedo verificada.

Ahora realiza una prueba integral pequena entre frontend y backend.

Objetivo:

Validar un turno real de Vera desde el navegador y encontrar evidencia minima de esa misma conversacion en el backend.

Reglas:

- Para la interfaz usa exclusivamente `browsermcp_*`.
- Ejecuta un snapshot antes de cada interaccion.
- Ejecuta otro snapshot despues de cada cambio de interfaz.
- No reutilices referencias viejas despues de que cambie la pagina.
- Para backend puedes usar terminal, logs y consultas PostgreSQL de solo lectura.
- No modifiques archivos.
- No reinicies PostgreSQL, Milvus ni LiteLLM salvo pedido explicito.
- Puedes bajar y volver a levantar backend y Astro locales si no responden en
  `7050/3050`, quedaron viejos o el entorno es ambiguo.
- No ejecutes migraciones.
- No hagas commits.
- No muestres secretos.
- No uses `curl` para reemplazar el flujo del navegador.

FASE 1 - Frontend real

1. Abrí:
   http://127.0.0.1:3050/t360

2. Localiza:
   "Recibo leads por WhatsApp y no sé quién los sigue."

3. Haz clic una vez.

4. Ejecuta un nuevo snapshot y confirma:
   - que el campo se completo;
   - que "Enviar" quedo habilitado.

5. Haz clic en "Enviar".

6. Espera mientras aparezca "Vera está escribiendo...".

7. Cuando termine, ejecuta un snapshot final.

8. Registra:
   - mensaje enviado;
   - respuesta exacta de Vera;
   - conversation_id visible;
   - numero de turno;
   - errores visibles;
   - transiciones observadas.

FASE 2 - Backend minimo

Usando el conversation_id obtenido en el navegador:

1. Revisa los logs del backend en ejecucion.
2. Busca evidencia de esa conversacion.
3. Si los logs no alcanzan, consulta PostgreSQL unicamente con SELECT.
4. Confirma, cuando este disponible:
   - endpoint recibido;
   - metodo HTTP;
   - codigo HTTP;
   - conversation_id;
   - estado o turnos persistidos;
   - proveedor LLM;
   - modelo o alias utilizado;
   - proveedor de retrieval;
   - coleccion Milvus;
   - proveedor de estado;
   - proveedor de embeddings;
   - errores;
   - warnings;
   - fallbacks.

FASE 3 - Cruce frontend/backend

Compara:

- conversation_id del frontend;
- conversation_id persistido;
- turno visible;
- turnos almacenados;
- mensaje enviado;
- respuesta recibida;
- estado persistido;
- errores y fallbacks.

Informe final:

1. Resultado: PASS, PASS con observaciones o FAIL.
2. Evidencia frontend.
3. Evidencia backend.
4. Correspondencia frontend/backend.
5. Problemas encontrados.
6. Proximo paso tecnico minimo.

No corrijas nada.
Detente despues del informe.
```

## Resultado integral observado

La prueba termino con:

```text
PASS con observacion menor
```

Frontend validado:

- carga de `/t360`;
- seleccion del caso de WhatsApp;
- llenado automatico del campo;
- habilitacion de `Enviar`;
- envio real;
- estado `Vera está escribiendo...`;
- render de la respuesta;
- limpieza del campo;
- deshabilitacion del boton;
- visualizacion de `conversation_id`;
- visualizacion del turno;
- ausencia de errores.

Backend validado:

- `POST /api/diagnosis/turn`;
- respuesta `201 Created`;
- estado persistido en PostgreSQL;
- tabla `sales_diagnosis_conversation_states`;
- upsert mediante `ON CONFLICT`;
- state provider PostgreSQL;
- LLM provider LiteLLM;
- modelo GPT-5 Nano mediante alias;
- retrieval provider Milvus;
- collection `team360_sales_diagnosis_knowledge_v1`;
- embeddings mediante `openai_text_embedding_3_small`;
- ausencia de fallbacks;
- ausencia de warnings;
- ausencia de errores asociados a la conversacion.

## Hallazgos

### Browser como fase atomica

No pedir en una sola instruccion:

```text
Abrí la pagina, revisa el frontend, encuentra problemas, corrige el codigo, ejecuta tests y valida el backend.
```

Separar:

```text
browser
-> informe
-> backend
-> informe
-> modificacion
-> browser final
```

### La palabra "primero" no alcanza

Esto es debil:

```text
Primero abri el navegador y despues revisa el codigo.
```

Es mas fuerte:

```text
En esta fase solamente usa opencode-browser.
Esta prohibido abrir archivos o usar terminal.
No avances a otra fase.
Detente despues del informe.
```

### Punto de detencion obligatorio

Incluir siempre:

```text
Detente inmediatamente despues del informe.
```

Esto evita exploracion, edicion o propuestas no solicitadas.

### Terminal no reemplaza navegador

Para validar experiencia real, el prompt debe prohibir:

```text
No uses curl, wget, Playwright ni lectura de HTML como reemplazo del navegador.
```

La terminal puede usarse despues para logs, PostgreSQL, configuracion y
correlacion, pero no como sustituto del recorrido de UI.

### Logs insuficientes

Si los logs no contienen evidencia por rotacion o retencion limitada, el orden
recomendado es:

```text
logs
-> PostgreSQL read-only
-> codigo/configuracion solo si todavia falta contexto
```

### `conversation_id` truncado visualmente

Caso observado:

```text
frontend: conv_59b66de8803...
backend:  conv_59b66de8803c
```

Esto fue truncamiento visual, no error de integridad.

Mejora UX recomendada:

- mantener truncamiento visual;
- agregar `title` con valor completo;
- agregar boton copiar;
- evitar mostrar el valor completo de forma permanente en mobile.

## Repetibilidad

Cada prueba integral debe empezar con conversacion nueva cuando el objetivo sea
aislar un unico intercambio.

Flujo recomendado:

```text
1. Abrir /t360
2. Pulsar "Nueva conversacion"
3. Capturar el nuevo conversation_id
4. Enviar un unico mensaje
5. Esperar la respuesta
6. Verificar que la conversacion nueva tenga exactamente un turno
7. Buscar ese mismo conversation_id en backend
```

## Plantilla de smoke repetible

```text
Usa opencode-browser para ejecutar un smoke test repetible sobre:

http://127.0.0.1:3050/t360

Reglas:

- Usa `browsermcp_*`.
- Ejecuta snapshot antes de interactuar.
- Genera un nuevo snapshot despues de cada cambio.
- No reutilices referencias viejas.
- No uses terminal hasta completar la fase browser.
- No modifiques archivos.

Pasos:

1. Abrí la pagina.
2. Ejecuta snapshot.
3. Si existe una conversacion previa, haz clic en "Nueva conversacion".
4. Ejecuta otro snapshot.
5. Captura el nuevo conversation_id visible.
6. Selecciona:
   "Recibo leads por WhatsApp y no sé quién los sigue."
7. Ejecuta snapshot.
8. Confirma que "Enviar" este habilitado.
9. Haz clic en "Enviar".
10. Espera la respuesta completa.
11. Ejecuta snapshot final.
12. Confirma:
    - mensaje enviado;
    - respuesta de Vera;
    - Turno 1;
    - conversation_id;
    - ausencia de errores.

Despues:

13. Revisa logs del backend.
14. Si no hay evidencia, consulta PostgreSQL con SELECT.
15. Confirma que el mismo conversation_id existe.
16. Confirma que corresponde a una conversacion nueva con un unico intercambio.
17. Informa PASS, PASS con observaciones o FAIL.

Detente al terminar.
```

## Tareas adecuadas para DeepSeek V4 Flash

Usar para:

- navegacion;
- smoke tests;
- QA browser guiado;
- formularios;
- chat;
- validacion de estados de carga;
- validacion de errores visibles;
- inspeccion basica de UX;
- correlacion frontend/backend;
- revision de logs;
- consultas SQL de solo lectura;
- identificacion de proveedores activos;
- validacion de integraciones;
- cambios acotados con posterior comprobacion.

## Tareas preferibles para GPT-5.5

Reservar GPT-5.5, o un modelo superior disponible, para:

- QA visual fino;
- comparacion contra mockups;
- deteccion de problemas sutiles de diseno;
- exploracion autonoma;
- debugging ambiguo;
- multiples hipotesis simultaneas;
- refactors amplios;
- correcciones de arquitectura;
- validaciones end-to-end muy largas;
- tareas donde browser, codigo, logs y decisiones UX deben coordinarse sin pasos predefinidos.

## Politica de modelos

DeepSeek V4 Flash:

```text
browser QA dirigido
smoke tests
validacion frontend/backend
inspeccion rapida
cambios pequenos
trabajo diario
```

GPT-5.5 o modelo superior:

```text
QA visual complejo
debugging profundo
arquitectura
UX
refactors
exploracion autonoma
```

## Veredicto

DeepSeek V4 Flash es apto para automatizacion browser estructurada y para
pruebas integrales frontend/backend, siempre que el prompt establezca
herramientas, fases, snapshots, evidencia esperada, restricciones y un punto de
detencion explicito.

El plugin `opencode-browser` funciona correctamente con DeepSeek V4 Flash. La
confiabilidad depende principalmente de la disciplina del prompt.

## Referencias

- [[model-selection-routing]]
- [[browser-mcp-validation-policy]]
- [[team360-runtime-operational-policy]]
- [[service-preflight-methodology]]
