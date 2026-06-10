# Team360 — Orquestación global

## Propósito

Mantener una visión unificada de Team360 entre ramas Git, hilos de chat, frentes técnicos, documentación knowledge, labs y decisiones comerciales/productivas.

Team360 trabaja con ramas separadas para aislar riesgos, pero las decisiones globales deben mantenerse en una vista transversal.

Regla central:

> Trabajar separado, decidir globalmente.

## Ramas activas

| Rama | Rol | Uso |
|---|---|---|
| `main` | Producción / snapshot estable | No trabajar directo salvo hotfix o consolidación final |
| `feature/console-backend-core` | Desarrollo principal productivo | Backend, Console, UX real, diagnosis assistant, LiteLLM, PostgreSQL, `lab/` y orquestación viva |
| `ux/team360-console-design-handoff` | Referencia visual congelada | Handoff visual, diseño base, no UX viva |
| `feature/knowledge-ingestion-service` | Servicio técnico de ingesta | Embeddings, chunking, scanner, retrieval, package behavior, golden answers y labs de ingesta |
| `docs/knowledge-documents-foundation` | Documentación knowledge | Estándares, paquetes, manuales, authoring, metadata y contenido curado |

## Regla de trabajo para una sola persona

El proyecto lo lleva principalmente una sola persona, por lo que se prefiere:

- pocas ramas;
- roles claros;
- commits pequeños;
- push frecuente;
- revisión por paths antes de publicar cambios grandes;
- evitar ramas nuevas salvo experimento riesgoso, hotfix o necesidad real.

No crear ramas por cada detalle menor.

## UX real vs handoff visual

La UX real productiva vive en:

`feature/console-backend-core`

Esto incluye:

- flujos reales;
- navegación;
- estados de componentes;
- integración con API;
- validaciones de UI;
- experiencia final de consola;
- diagnóstico conectado al backend.

La rama:

`ux/team360-console-design-handoff`

queda como referencia visual congelada / diseño base. No debe confundirse con la UX viva del producto.

## Knowledge ingestion vs documentación knowledge

Separar claramente:

### `feature/knowledge-ingestion-service`

Incluye:

- scanner;
- worker;
- schemas;
- validaciones;
- tests de ingestion;
- embeddings;
- chunking;
- retrieval;
- package behavior;
- golden answers;
- labs de ingesta.

### `docs/knowledge-documents-foundation`

Incluye:

- documentación knowledge;
- estándares de authoring;
- manuales;
- drafts;
- metadata editorial;
- contenido curado;
- estructura de paquetes.

No mezclar código de ingesta con armado editorial de documentos, salvo corpus mínimo aprobado cuando sea necesario para validar ingestion end-to-end.

## Regla de `lab/`

`SrvRestAstroLS_v1/lab/` no es código temporal descartable.

Es un banco de pruebas técnico:

- reproducible;
- auditable;
- aislado de producción;
- útil para comparar hipótesis;
- útil para conservar evidencia de resultados.

Los experimentos `lab/` pueden existir en distintas ramas.

La rama correcta se decide por:

1. la hipótesis validada;
2. el sistema bajo prueba;
3. el uso real del resultado.

No se decide solo por el nombre del directorio.

Guía:

- `feature/console-backend-core`: labs de backend runtime, diagnosis API, assistant productivo, UX real conectada o experiencia final de consola.
- `feature/knowledge-ingestion-service`: labs de embeddings, chunking, scanner, retrieval, package behavior, golden answers o conversación como efecto de knowledge package.
- `docs/knowledge-documents-foundation`: labs de authoring, metadata, manuales, contenido curado o estructura documental.
- `ux/team360-console-design-handoff`: labs puramente visuales de handoff.

## Decisiones globales de producto

- `pkg_sales_diagnosis` es un knowledge package evolutivo.
- Team360.live será el primer contexto de validación.
- Vera es nombre comercial visible, no identificador técnico.
- El diagnóstico no se limita a ventas; ventas es la entrada comercial inicial.
- Automatizable no significa vendible hoy.
- Step-to-Action, lead capture, diagnostic_code y WhatsApp handoff son capacidades futuras.
- La primera etapa productiva prioriza:
  - conversación clara;
  - slots mínimos;
  - preguntas mínimas necesarias;
  - diagnóstico útil;
  - orientación concreta.

## Comunicación, marketing y distribuidores

Conviene mantener un hilo separado para:

- ventas;
- comunicación;
- marketing;
- distribuidores;
- pricing;
- mensajes comerciales;
- materiales para canales;
- paquetes iniciales.

Nombre sugerido del hilo:

`Team360 — Ventas, Comunicación, Marketing y Distribuidores`

Este frente no debe mezclar detalles de ramas, tests, schemas o implementación salvo que impacten promesas comerciales.

Regla comercial:

> Vender valor real de la primera etapa productiva. No vender capacidades futuras como si ya estuvieran listas.

## Cierre de trabajo por rama

Cada bloque de trabajo debería cerrar con:

- rama usada;
- objetivo del bloque;
- archivos creados/modificados;
- validaciones ejecutadas;
- impacto sobre otros frentes;
- si requiere actualizar esta orquestación global;
- próximo paso recomendado.

Formato sugerido:

```text
Rama:
...

Objetivo:
...

Archivos modificados:
...

Validaciones:
...

Impacto transversal:
...

Próximo paso:
...
```

## Regla contra fragmentación

No asumir que el contexto de una rama representa todo Team360.

Antes de tomar decisiones amplias, revisar:

- este documento;
- `lat.md/lat.md`;
- `lat.md/status_actual.md`;
- `SrvRestAstroLS_v1/docs/status_actual.md`;
- el mapa de ramas;
- el hilo de orquestación global.

Si un cambio técnico afecta producto, knowledge, UX real, documentación o ventas, mencionarlo explícitamente en el cierre.

## Estado global actual

Fecha: 2026-06-10

Estado de ramas:

- `main`: sincronizada con `origin/main`.
- `feature/console-backend-core`: sincronizada con `origin/feature/console-backend-core`.
- `feature/knowledge-ingestion-service`: sincronizada con `origin/feature/knowledge-ingestion-service`.
- `docs/knowledge-documents-foundation`: sincronizada con `origin/docs/knowledge-documents-foundation`.
- `ux/team360-console-design-handoff`: sincronizada con `origin/ux/team360-console-design-handoff`.

Avances recientes:

- `feature/console-backend-core` incorporó la convención de `lab/` como banco de pruebas técnico reproducible.
- `feature/knowledge-ingestion-service` incorporó labs de embeddings, retrieval, package behavior y conversación como efecto de knowledge package.
- El skill del proyecto documenta ownership de experimentos `lab/` por hipótesis validada y sistema bajo prueba.
- Todas las ramas principales tienen upstream remoto y worktree limpio al último checkpoint.

Próximos focos:

- Consolidar experimento de embeddings.
- Mantener `pkg_sales_diagnosis` como package evolutivo.
- Usar Team360.live como primer contexto de validación.
- Separar el hilo comercial de ventas/marketing/distribuidores.
- Evitar que los resultados de labs crezcan sin pushes o revisiones intermedias.
