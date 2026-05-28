# Status actual - lat.md

Objetivo: `arquitectura-viva`

Ultima actualizacion: 2026-05-28

## Estado general

`lat.md/` contiene definiciones de alto nivel, reglas de negocio, decisiones de arquitectura e invariantes para Team360.

Esta capa sigue el patron usado en JudaismoenVivo: indice raiz `lat.md/lat.md`, documentos por concepto y referencias `[[...]]` que pueden anclarse desde codigo con comentarios `@lat`. Las reglas de uso quedaron declaradas en `AGENTS.md` y en `.agents/skills/team360-project/SKILL.md`.

## Acciones realizadas

### 2026-05-28 - Reglas operativas de lat.md para agentes

- Se agrego en `AGENTS.md` la regla obligatoria para leer `lat.md/lat.md` ante cambios de arquitectura, dominio, IA, workers, knowledge, seguridad, paquetes o reglas transversales.
- Se agrego en `.agents/skills/team360-project/SKILL.md` el procedimiento de uso de `lat.md/`: documentos `kebab-case.md`, referencias `[[...]]`, anchors `@lat`, limites de uso y actualizacion de status local.
- Se explicito que `lat.md/` no reemplaza la bitacora tecnica `SrvRestAstroLS_v1/docs/status_actual.md`.

### 2026-05-28 - Base lat.md general de Team360

- Se creo `lat.md/lat.md` como indice raiz.
- Se agregaron documentos para:
  - plataforma Team360;
  - multi-paquete / multi-worker;
  - knowledge RAG / GraphRAG;
  - LiteLLM;
  - seguridad HITL / MFA;
  - automation diagnosis.

## Validacion

- No se movio documentacion tecnica viva desde `SrvRestAstroLS_v1/docs/`.
- `lat.md/` queda como capa de invariantes y conceptos estables anclables desde codigo.

## Pendientes recomendados

- Agregar nuevos documentos lat.md solo para conceptos estables de plataforma.
- Evitar duplicar bitacoras tecnicas: el estado de implementacion sigue en `SrvRestAstroLS_v1/docs/status_actual.md`.
