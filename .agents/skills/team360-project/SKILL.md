---
name: team360-project
description: Reglas y flujo de trabajo para desarrollar Team360 con Codex CLI, incluyendo team360_orquestador, AG-UI y laboratorio aislado de Mercado Libre.
---

# Team360

## Propósito
Team360 es una solución multicanal conversacional.
El núcleo del sistema es `team360_orquestador`.
AG-UI / SSE es parte estructural.
Providers iniciales:
- Gupshup
- Mercado Libre

Mercado Libre arranca con laboratorio aislado de browser automation.

## Ubicación del skill
Usar esta copia del skill dentro del repo:
`.agents/skills/team360-project/SKILL.md`

## Raíz del proyecto
Asumir como raíz el directorio actual del repositorio Team360.

## Estructura relevante
- `lat.md/lat.md`
- `lat.md/`
- `SrvRestAstroLS_v1/backend/modules/team360_orquestador/`
- `SrvRestAstroLS_v1/backend/modules/agui_stream/`
- `SrvRestAstroLS_v1/backend/modules/messaging/providers/gupshup/`
- `SrvRestAstroLS_v1/backend/modules/messaging/providers/mercadolibre/browser/`
- `SrvRestAstroLS_v1/backend/modules/messaging/providers/mercadolibre/probes/`
- `SrvRestAstroLS_v1/backend/modules/messaging/providers/mercadolibre/runtime/`
- `SrvRestAstroLS_v1/astro/src/lib/team360_orquestador/`
- `SrvRestAstroLS_v1/astro/src/components/demo/team360-orquestador/`
- `SrvRestAstroLS_v1/astro/src/pages/demo/team360-orquestador/`

## Convenciones para lat.md
`lat.md/` es la capa de arquitectura viva de Team360. Usarla para reglas estables, invariantes de dominio y decisiones transversales que deben sobrevivir a una tarea puntual.

Leer `lat.md/lat.md` antes de cambios que afecten:
- arquitectura general o limites de modulos
- IA, LiteLLM, providers o scoring
- workers, `package_worker`, paquetes o automatizaciones
- knowledge, RAG, GraphRAG o scopes
- seguridad, MFA, HITL, credenciales o acciones bloqueadas
- contratos que puedan quedar anclados desde codigo

Reglas de uso:
1. Crear documentos por concepto estable con nombre `kebab-case.md`.
2. Usar referencias tipo `[[concepto]]` entre documentos.
3. Usar anchors de codigo tipo `# @lat: [[concepto#Seccion]]` solo cerca de clases, funciones o decisiones donde se implementa una regla no trivial.
4. No anclar cada linea ni comentarios obvios.
5. No usar `lat.md/` para bitacoras diarias, evidencias, snapshots, instrucciones efimeras o estado de implementacion.
6. Al crear o modificar documentos de `lat.md/`, actualizar `lat.md/status_actual.md`.
7. Mantener `SrvRestAstroLS_v1/docs/status_actual.md` como bitacora tecnica principal; `lat.md/` solo registra invariantes y conceptos estables.

## Reglas de trabajo
1. No inventar una estructura nueva fuera del patrón actual.
2. No copiar módulos de Vertice360 fuera del alcance ya definido.
3. No tocar `team360_orquestador` salvo que el objetivo lo pida.
4. No mezclar probes/browser con AG-UI, rutas o frontend salvo que el objetivo lo pida.
5. Preferir cambios chicos, claros y reversibles.
6. Mantener compatibilidad con ejecución tipo:
   - `python -m modules.messaging.providers.mercadolibre.probes.smoke_login`
   - `python -m modules.messaging.providers.mercadolibre.probes.smoke_inbox`
7. No hacer scraping complejo en fases de smoke/probe.
8. Si la validación requiere intervención humana, dejarlo explícito.
9. No instalar dependencias ni ejecutar comandos destructivos salvo pedido explícito.
10. Respetar la estrategia de environment parity del backend con Vertice360, más extras necesarios como Playwright.

## Convenciones para Mercado Libre browser lab
- `browser/` contiene helpers reutilizables
- `probes/` contiene scripts ejecutables aislados
- `runtime/` contiene perfiles, screenshots y storage state
- `selectors.py` debe ser conservador y ajustable
- `smoke_*` primero validan acceso, luego lectura, después interacción

## Convenciones para resultados
Al terminar una tarea:
1. resumir archivos modificados
2. explicar diff o cambios principales
3. indicar cómo validar manualmente
4. listar supuestos y heurísticas

## Qué priorizar
- primero laboratorio Mercado Libre funcional
- luego normalización mínima
- luego integración gradual con `team360_orquestador`
- luego AG-UI/SSE/UI

## Qué evitar
- mezclar demasiado pronto dominio y provider
- sobreautomatizar antes de tener smoke tests sólidos
- introducir complejidad innecesaria
- refactors grandes fuera del objetivo puntual
