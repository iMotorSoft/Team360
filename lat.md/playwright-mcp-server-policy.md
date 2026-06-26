# Playwright MCP Server Policy

## Proposito

Playwright MCP Server es el servidor MCP que expone capacidades de navegador
Playwright para agentes y clientes compatibles con MCP.

En Team360 se usa para:

- navegacion interactiva;
- inspeccion visual;
- captura de screenshots;
- lectura del DOM;
- consola;
- requests;
- reproduccion manual asistida;
- validacion UX.

No es el gate final de calidad. Sirve para investigar, observar, reproducir e
inspeccionar una experiencia real de navegador, pero no reemplaza tests
reproducibles ni asserts versionados.

## Diferencia entre Playwright MCP y Playwright CLI

Playwright MCP se usa para exploracion, diagnostico visual e interaccion humana
asistida. Es apropiado cuando el agente necesita navegar una pagina, inspeccionar
estado visible, leer DOM, revisar consola, observar requests o capturar evidencia
visual durante una reproduccion manual.

Playwright CLI se usa para tests reproducibles, assertions, regresiones y gates
E2E. Es la herramienta que debe proteger cambios y demostrar que un flujo queda
cubierto de forma repetible.

Regla:

```text
Playwright MCP observa.
Playwright CLI demuestra.
```

## Comando de arranque

El comando de arranque observado para el servidor MCP actual es:

```bash
./run-podman.sh sse
```

La salida esperada es:

```text
Listening on http://localhost:8931
```

No iniciar otro servidor MCP si ya existe uno activo en el endpoint oficial.

## Endpoint oficial

Endpoint MCP oficial:

```text
http://localhost:8931/mcp
```

Endpoint legacy compatible:

```text
http://localhost:8931/sse
```

El endpoint nuevo debe preferirse para configuraciones nuevas. El endpoint
legacy queda solo para clientes que todavia dependan de SSE.

## Configuracion del cliente

Configuracion minima del cliente MCP:

```json
{
  "mcpServers": {
    "playwright": {
      "url": "http://localhost:8931/mcp"
    }
  }
}
```

## Red local

El contenedor Playwright MCP debe tener acceso a la red local.

Debe poder abrir:

```text
http://127.0.0.1:3050/
http://127.0.0.1:7050/
```

o las URLs equivalentes definidas por la configuracion de red vigente.

Dentro de un contenedor:

```text
127.0.0.1
localhost
```

pueden apuntar al propio contenedor si no se usa una configuracion de red
apropiada. La solucion adoptada en `run-podman.sh` debe asegurar que el servidor
MCP pueda acceder a servicios del host, sin cambiar la configuracion productiva
de Team360.

## Validacion minima del servidor

Prueba corta para validar el servidor:

1. Conectar el cliente al MCP.
2. Abrir `http://127.0.0.1:3050/`.
3. Confirmar el titulo de la pagina.
4. Obtener un snapshot.
5. Capturar un screenshot.
6. Escribir en un input sin enviar.
7. Limpiar el input.
8. Revisar consola.
9. Revisar requests fallidos.
10. Cerrar solo el contexto o la pagina creada.

La prueba no debe detener el servidor MCP salvo pedido explicito.

## Herramientas esperadas

El servidor debe exponer funciones equivalentes a:

```text
browser_navigate
browser_snapshot
browser_evaluate
browser_type
browser_take_screenshot
browser_close
```

No se documentan schemas internos completos en esta politica. La lista es una
expectativa funcional minima para navegar, inspeccionar, interactuar, capturar y
cerrar recursos creados durante la prueba.

## Reglas de uso

- No usar Chrome MCP.
- No usar Browser MCP para este flujo.
- No levantar otro navegador externo para reemplazar esta validacion.
- No detener el servidor MCP sin pedido explicito.
- No usar Playwright MCP como reemplazo de `pytest`.
- No usar Playwright MCP como reemplazo de Playwright CLI.
- No modificar backend, frontend, tests ni configuracion productiva solo para
  hacer funcionar el MCP.
- No dejar inputs modificados ni acciones enviadas salvo que la prueba lo pida
  explicitamente.

## Uso junto con Team360

Para entorno local:

```text
backend con ./backend-dev.sh
Astro con ./astro-dev.sh
Playwright MCP en localhost:8931
```

URLs:

```text
Astro: http://127.0.0.1:3050/
Backend: http://127.0.0.1:7050/
MCP: http://localhost:8931/mcp
```

El backend y Astro deben levantarse con los scripts del proyecto cuando la prueba
requiera runtime local real.

## Servicios permanentes

No tocar durante validaciones Playwright MCP:

```text
PostgreSQL
Milvus
LiteLLM
```

Estos servicios pueden ser prerequisitos de una validacion, pero no deben
detenerse, reiniciarse ni reconfigurarse como parte de una prueba MCP salvo
instruccion explicita.

## Que validar con Playwright MCP

Ejemplos adecuados:

- flujo conversacional;
- bloques visibles;
- estado `answered` / `requires-response`;
- idioma;
- RTL hebreo;
- scroll;
- overlay;
- botones;
- inputs;
- errores de consola;
- requests fallidos.

## Que no cerrar solo con MCP

No declarar cerrado un cambio unicamente con Playwright MCP cuando el riesgo sea:

- persistencia;
- regresiones;
- requests duplicados;
- errores `5xx`;
- restart recovery;
- contratos backend.

Estos casos requieren una o mas de estas evidencias:

```text
pytest
Playwright CLI
tests de integracion
```

## Evidencia minima

Registrar como minimo:

- endpoint MCP;
- URL probada;
- pagina cargada;
- titulo;
- screenshot;
- errores de consola;
- requests fallidos;
- input editable;
- navegador cerrado;
- servidor MCP detenido o no.

La evidencia puede estar en el informe final de la tarea o en un artefacto
documental cuando el objetivo pida conservarla.

## Cierre

Regla final:

```text
Playwright MCP sirve para investigar y validar visualmente.
Playwright CLI sirve para proteger y cerrar el cambio.
```
