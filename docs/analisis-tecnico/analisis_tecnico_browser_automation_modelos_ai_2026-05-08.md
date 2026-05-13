# Analisis tecnico: browser automation y modelos AI

Fecha: 2026-05-08
Contexto: automatizacion de analisis tipo Meta Business Suite / Facebook para Team360
Caso base: `judaismoenvivo.com`

## Conclusion corta

Si, tecnicamente se puede implementar fuera de Codex CLI lo que se hizo en el analisis de Facebook: abrir navegador autenticado, respetar login/2FA con humano, extraer metricas, comentarios y tablas, y usar AI para analizar, clasificar y recomendar acciones.

La arquitectura correcta no es "una IA manejando Facebook libremente". Es un copiloto RPA controlado:

```text
Playwright / Chrome persistente
-> sesion del cliente
-> backend propio
-> cola de jobs
-> extraccion DOM/texto/tablas/screenshots
-> AI para clasificar y analizar
-> aprobacion humana para acciones sensibles
-> auditoria en Team360
```

## Seguridad y 2FA

Regla principal:

```text
El usuario conserva el control.
El sistema nunca debe prometer bypass de seguridad.
```

Cuando aparezca:

- password;
- 2FA;
- QR;
- passkey;
- aprobacion en app;
- verificacion por email/SMS;
- challenge de Meta;

el humano debe resolverlo. El sistema espera, detecta que la sesion quedo activa y continua.

Acciones que requieren aprobacion humana:

- login y 2FA;
- responder mensajes sensibles;
- respuestas masivas;
- publicar contenido;
- borrar comentarios;
- bloquear usuarios;
- activar anuncios;
- cambiar configuracion;
- tocar pagos, monetizacion o permisos.

## Produccion vs laboratorio

Para produccion, preferir APIs oficiales:

- Meta Graph API;
- Meta Business API;
- WhatsApp Cloud API o Gupshup;
- Pixel / Conversions API;
- Lead Ads API.

Browser automation queda como:

- laboratorio;
- fallback;
- auditoria visual;
- extraccion cuando la API no cubre algo;
- onboarding tecnico inicial.

Riesgos del browser automation:

- cambios de UI;
- bloqueos por comportamiento automatizado;
- dependencia de sesion;
- restricciones de Meta;
- fragilidad en inbox privado;
- necesidad de supervision humana.

## Modelo tecnico recomendado

No conviene que el modelo mire screenshots todo el tiempo. Es caro y menos estable.

Primero extraer con Playwright:

- texto visible;
- DOM;
- links;
- botones;
- tablas;
- metricas;
- comentarios;
- mensajes;
- capturas solo cuando haga falta.

Luego pasar al modelo datos estructurados:

```json
{
  "content_id": "...",
  "title": "ISRAEL HOY",
  "views": 308004,
  "comments": 1282,
  "shares": 1030,
  "follows": 476,
  "sample_comments": [...]
}
```

Esto permite usar modelos baratos.

## Modelos OpenAI

Arquitectura de costo:

```text
95% tareas: gpt-5-nano
4% tareas: gpt-5-mini / gpt-5.4-mini
1% tareas: modelo grande
```

Uso recomendado:

- `gpt-5-nano`: clasificacion masiva barata, intencion, spam, tags, resumen corto.
- `gpt-5-mini`: respuestas sugeridas, analisis de campanas, decisiones de workflow simples.
- `gpt-5.4-mini`: mejor candidato OpenAI para computer use/casos agentic mas complejos.
- modelo grande: auditorias estrategicas o casos criticos.

Precios oficiales observados en OpenAI API pricing:

- `gpt-5-nano`: aprox. USD 0.05 input / USD 0.40 output por 1M tokens.
- `gpt-5-mini`: aprox. USD 0.25 input / USD 2.00 output por 1M tokens.
- `gpt-5.4-mini`: aprox. USD 0.75 input / USD 4.50 output por 1M tokens.

## Modelos OpenRouter

Pueden dar resultados parecidos si reciben datos limpios extraidos por Playwright.

No se recomienda pedirles que operen Facebook visualmente y sin control.

### DeepSeek V4 Flash

Buen candidato costo/calidad para agente operativo.

Uso:

- clasificacion;
- resumen;
- razonamiento de workflows simples;
- analisis de tablas;
- recomendaciones operativas.

OpenRouter lo lista aprox. en:

- USD 0.14 input / USD 0.28 output por 1M tokens.

### DeepSeek V4 Pro

Mas fuerte para analisis complejo.

Uso:

- auditorias;
- decisiones dificiles;
- sintesis larga;
- analisis mas profundo de negocio.

OpenRouter lo lista aprox. en:

- USD 0.435 input / USD 0.87 output por 1M tokens.

### Gemma 4 26B A4B

Muy barato, contexto grande y buen candidato para alto volumen.

Uso:

- clasificacion;
- extraccion estructurada;
- resumen;
- procesamiento de comentarios;
- primer filtro de intencion.

OpenRouter lo lista aprox. en:

- USD 0.06 input / USD 0.33 output por 1M tokens.

### Gemma 4 free

Util para prototipos y pruebas.

No basar produccion en free tier por disponibilidad, limites y variabilidad.

## Recomendacion practica

Stack barato y realista:

```text
Playwright extrae datos
DeepSeek V4 Flash analiza y clasifica
Gemma 4 procesa volumen barato cuando se tolera revision
Modelo mas fuerte solo para auditoria o casos raros
Humano aprueba 2FA, publicaciones, respuestas masivas, ads y acciones sensibles
Team360 registra jobs, eventos, decisiones y auditoria
```

Para `judaismoenvivo.com`, DeepSeek V4 Flash o Gemma 4 podrian hacer gran parte del analisis si reciben:

- tablas limpias de Meta Business Suite;
- comentarios;
- mensajes;
- metricas por reel;
- historico de leads;
- productos/ofertas;
- reglas de escalamiento humano.

Lo que no debe delegarse ciegamente:

- operar la cuenta con permisos reales;
- tomar decisiones religiosas sensibles;
- responder masivamente sin revision;
- invertir dinero en anuncios;
- modificar pagos, permisos o configuracion.

## Decision fria

La ventaja competitiva no esta solo en el modelo.

Esta en:

1. extraccion confiable;
2. sesion segura con humano en 2FA;
3. datos estructurados;
4. prompts/evaluaciones por tarea;
5. auditoria;
6. workflow con aprobacion humana;
7. integracion con WhatsApp, CRM, pagos y reportes.

El modelo barato sirve si el sistema alrededor esta bien disenado.
