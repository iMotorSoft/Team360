# LAT Documentation Policy

This policy defines the permanent structure, linking, indexing, status and validation rules for Team360 LAT and Markdown documentation.

## Purpose

This policy prevents repeated documentation failures and lets future agent prompts reference one canonical source instead of copying long rule sets.

## Scope

This policy applies whenever an agent creates or modifies project documentation in the following locations.

- `lat.md/`
- `SrvRestAstroLS_v1/docs/`
- `AGENTS.md`
- `.agents/skills/team360-project/SKILL.md`

## Heading rule

Every section must begin with a concise prose summary that remains useful in LAT search results and generated context.

Every Markdown heading must be followed by a short introductory paragraph of at most 250 characters before any list, table, code block, or subsection.

Después de cada encabezado debe haber un párrafo introductorio breve, máximo 250 caracteres, antes de listas, tablas, código o subsecciones.

The following structures are invalid:

- a heading followed directly by another heading;
- a heading followed directly by a list;
- a heading followed directly by a table;
- a heading followed directly by a code block.

## Link rule

Wiki links represent existing architectural concepts and must never be speculative placeholders.

Every `[[wiki]]` link must resolve to a real file or section.

Create the target document or section before adding its link, and use `lat locate` when the destination is ambiguous.

## LAT index rule

The root LAT index must remain a complete and navigable inventory of every concept document.

Every `.md` file inside `lat.md/` must appear in `lat.md/lat.md`.

Do not add a concept to `lat.md/lat.md` before creating its document.

## Status files rule

El único estado técnico GLOBAL vigente es [SrvRestAstroLS_v1/docs/status_actual.md](../SrvRestAstroLS_v1/docs/status_actual.md). Debe ser compacto: estado vigente + decisión + límite + enlace a evidencia, sin copiar resultados completos de tests o fases.

La jerarquía es AGENTS (cómo trabajar y coordinar ownership) → LAT (invariantes y reglas GLOBAL) → tablero técnico GLOBAL → estado o autoridad local → contratos, runbooks, reports y fases. El tablero enlaza LAT y las autoridades locales para navegación práctica.

El nombre canónico de estados nuevos es `status_actual.md`, en minúsculas. Autoridades locales existentes pueden conservar su nombre: Telchi mantiene `CONTEXT.md` para arquitectura, roots y etapas; un estado local nunca lo sustituye.

`lat.md/status_actual.md` registra mantenimiento de arquitectura e índice LAT, no otro estado técnico GLOBAL. Cuando LAT cambia, actualizarlo sin duplicar evidencia operacional.

Los cierres históricos, contratos y reportes permanecen en sus fuentes. Si un tablero acumuló historia, conservar una copia congelada íntegra antes de compactarlo; no modificar el histórico anterior ni borrar evidencia preexistente. Los resultados generados viven en `data/reports/`.

## Duplication rule

LAT documents preserve stable knowledge without copying operational reports or extensive implementation narratives.

LAT summarizes invariants, decisions, and links to extended sources.

Do not duplicate long evidence across LAT and `SrvRestAstroLS_v1/docs/`.

## Required gates

Run every documentation gate from the repository root before reporting a documentation task as complete.

```bash
lat check md
lat check index
lat check sections
lat check code-refs
lat check
git diff --check
```

## Failure policy

A documentation task remains incomplete while any mandatory gate fails.

If any LAT gate fails, the phase must not be reported as PASS.

Fix the documentation or report the blocker.

## Agent prompt guidance

Future prompts should reference this policy instead of embedding all structural rules again.

Respect the permanent LAT Documentation Policy in `lat.md/lat-documentation-policy.md`.

Prompts do not need to repeat these rules when the agent has read `AGENTS.md`, the Team360 project skill and this canonical policy.
