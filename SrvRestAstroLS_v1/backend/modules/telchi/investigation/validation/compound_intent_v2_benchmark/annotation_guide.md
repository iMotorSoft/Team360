# Guía de anotación del gold

Esta guía define cómo anotar un turno para el benchmark de Compound Intent. El objetivo es describir **lo que se quiso solicitar**, no lo que el catálogo puede ejecutar ni la salida de un candidato.

## Principios

1. El gold se anota desde el mensaje original del usuario y el estado conversacional aceptado. Nunca se copia de la salida de V1, Luna o cualquier extractor evaluado.
2. Todo requisito existe sólo si tiene evidencia literal. Sin evidencia, no hay requisito.
3. Una afirmación del usuario no es un hecho certificado. Nunca se marca `CERTIFIED` sin evidencia registrada.
4. Se distinguen cuatro procedencias y ninguna se colapsa en otra.

## Clases de procedencia

| Procedencia | Cuándo usarla | Evidencia exigida |
| --- | --- | --- |
| `CURRENT_REQUEST` | El turno actual expresa el requisito | subcadena exacta del mensaje actual |
| `INHERITED_CONTEXT` | El requisito viene del estado aceptado previo y sigue vigente | subcadena del `source_turn_id` |
| `USER_ASSERTED_UNVERIFIED` | El usuario afirma un hecho (relación, permiso, distribución) | subcadena exacta; `status` nunca `CERTIFIED` |
| `VERIFIED_EVIDENCE` | Sólo con un `evidence_id` registrado en `verified_evidence` | id existente; puede ser `CERTIFIED` |

## Categorías de requisito

`metric`, `entity_product`, `segment_geography`, `temporal_periodicity`, `relation`, `negation`, `correction`, `reference`, `assertion`, `ambiguity`, `non_executable`.

- Una corrección reemplaza o invierte un requisito previo; no se anota como requisito nuevo aislado si sólo corrige.
- Una negación se conserva explícitamente (`negation`); no se asume inclusión.
- Una ambigüedad legítima se registra en `ambiguity`: no se resuelve inventando.
- Un requisito no ejecutable por el catálogo se anota igual (`non_executable`); el gold describe la intención, no el catálogo.

## Reglas de evidencia

- `evidence` debe ser una subcadena exacta del mensaje de `source_turn_id` (o del turno actual si se omite).
- `value` debe aparecer bajo `field` en `request_intent`; el validador lo verifica.
- Para `relations` y `claims`, `value` es el objeto completo de la aserción y debe estar presente en la lista correspondiente.
- Para `time.periods`, `value` es el período completo y debe estar presente en `request_intent.time.periods`.

## Independencia

| Nivel | Significado | ¿Autoriza V2? |
| --- | --- | --- |
| `HUMAN_INDEPENDENT` | Revisor humano que no es autor de la implementación | Sí, con las compuertas de comportamiento |
| `MODEL_ASSISTED_PROVISIONAL` | Anotación por modelo con reglas, sin revisión humana | No |
| `MACHINE_DERIVED_LEGACY` | Derivado de un gold previo, no independiente | No |

Declarar independencia sólo por usar otro modelo está prohibido. Si no hay revisión humana, el conjunto es `PROVISIONAL_GOLD`.

## Desacuerdos e incertidumbre

- Un desacuerdo entre anotadores se documenta; no se promedia silenciosamente.
- Una incertidumbre se registra como `PENDING_ADJUDICATION` o en `ambiguities`.
- `algo no ejecutable` no se elimina del gold para que el candidato parezca correcto.

## Contraejemplos que el gold debe soportar

- `No farmacias, salvo las de la cadena X` no es una pertenencia plana de farmacias.
- `Allá lo hace L&S; acá nosotros` necesita ligadura de antecedente y geografía.
- `Primero importes` reordena; `solo importes` elimina una métrica.
- `Los mismos cinco` necesita un resultado verificado y row IDs ausentes del texto.
- Un swap de ciudad/distribuidor tiene el mismo conjunto de palabras y distinta tupla.
- `Farmacia Central` puede ser nombre propio y no clasificación.

## Checklist antes de cerrar una anotación

1. Cada requisito tiene evidencia literal verificada.
2. Ninguna afirmación quedó `CERTIFIED`.
3. `request_intent` contiene cada `value` bajo su `field`.
4. Las ambigüedades y los no ejecutables quedaron registrados.
5. El nivel de independencia refleja la revisión realmente disponible.