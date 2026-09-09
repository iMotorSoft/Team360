# Telchi Context Routing Design

Esta nota alinea el diseño de routing conceptual con la autoridad canónica [`CONTEXT.md`](CONTEXT.md). Es subordinada, tool-agnostic y no implementa un resolver.

## Decision status

`TELCHI_CONTEXT_MODEL_ALIGNMENT_V1` sustituye la parte conceptual basada en intents pares del gate anterior `TELCHI_CONTEXT_ROUTING_DESIGN_V1`.

La auditoría técnica anterior sobre `AGENTS.md`, OpenCode y portabilidad conserva validez. Cualquier reporte histórico permanece como evidencia; desde este gate, sus labels de intents no son instrucciones vigentes.

## Routing order

El orden de resolución obligatorio separa negocio, madurez, entradas, resultados y restricciones.

```text
ENTITY
  → DOMAIN
    → STAGE
      → SOURCES / OUTPUTS / POLICIES
```

`ENTITY=TELCHI` no se deriva de “SAP” o “HANA” aislados. Confirmada la entidad, se resuelve el área funcional y luego `INVESTIGATION`, `DEVELOPMENT` o `PRODUCTION`; recién después se agregan fuentes, outputs, roots y políticas.

## Classification correction

La corrección evita que sistemas e infraestructura compitan con las áreas funcionales o con la madurez de una capacidad.

| PREVIOUS LABEL | CURRENT RESOLUTION |
| --- | --- |
| `TELCHI_SAP` | Telchi + domain + stage + `SOURCE=SAP_HANA` |
| `TELCHI_DATALAKE` | Telchi + domain + stage + `SOURCE/OUTPUT=DATA_LAKE` |
| `TELCHI_LEGACY` | Telchi + domain + stage + `SOURCE=LEGACY_DS` o `LEGACY_DS0` |
| `TELCHI_PRODUCTIVE_MODULE` | Telchi + domain + `STAGE=DEVELOPMENT` o `PRODUCTION` |

Las etiquetas anteriores solo son admisibles al describir historia, nombres de gates o filenames. No son `primary_intent`, `intent_facets`, contextos actuales ni etapas.

## Default and promotion

La resolución segura por defecto es investigation. Development y Production se distinguen para impedir despliegues implícitos.

- Telchi confirmado + domain conocido + stage ausente → `INVESTIGATION`.
- Construir endpoint, servicio, API, productor o capacidad runtime → `DEVELOPMENT`.
- Desplegar, publicar, promover o habilitar una capacidad Development validada → `PRODUCTION`.
- `INVESTIGATION → DEVELOPMENT → PRODUCTION` requiere promoción explícita.
- Investigation permanece intacta y el código runtime no importa sus runners.

El ejemplo oficial es `CRÉDITO_Y_DEUDORES`: conocimiento de deudas en investigation, implementación separada de servicio/endpoint en Development y gate posterior para Production. El contrato completo está en `CONTEXT.md`.

## Portable context contract

El futuro mecanismo debe transportar conceptos y roots sin convertir este diseño en enums o schemas prematuros.

```text
entity, entity_confidence
domain, domain_status
stage, stage_confidence
sources, outputs
context_files
repository_root, module_root, investigation_root
source_root, physical_output_root, data_root, private_root, legacy_root
sap_policy, write_policy, git_policy
promotion_required
ambiguity, resolution_reason
```

`DATA_ROOT != DEVELOPMENT_ROOT`. SAP/HANA y legacy son read-only en investigation; el Data Root contiene datos físicos, nunca source code.

## Tool-agnostic bridge

Todas las herramientas deben converger en una sola autoridad funcional, sin copiar el modelo Telchi en configuraciones particulares.

```text
PI / CODEX CLI / OPENCODE / OMP / OTHER
                    ↓
       AGENTS.md / project instructions
                    ↓
     backend/modules/telchi/CONTEXT.md
```

La futura regla portable de `AGENTS.md` debe limitarse conceptualmente a lo siguiente: cuando una tarea pertenezca a Telchi, leer `SrvRestAstroLS_v1/backend/modules/telchi/CONTEXT.md` antes de elegir paths, ejecutar scripts o escribir; resolver domain, stage, sources y outputs; usar investigation salvo Development o Production explícitos.

## Implementation boundary

Este documento es diseño solamente. El próximo gate podrá implementar el puente mínimo, después de obtener la autorización GLOBAL necesaria para `AGENTS.md`.

En este gate no se modifica `AGENTS.md`, no se crea router, no se implementa context routing, no se crean endpoints y no se cambia runtime, SAP, Data Root, Private Root, Legacy Root ni `module_registry.py`.
