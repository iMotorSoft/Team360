# Contrato de V2 pasiva (especificación, sin implementación)

Este documento especifica la única forma de V2 que el RCA considera justificable. No autoriza su implementación. `authorization.py` decide si una implementación futura puede habilitarse.

## Principio

V2 observa qué pidió el usuario, pero **no decide qué se ejecuta**.

Pipeline actual, sin modificar ni simplificar:

```text
Luna → State Engine → capability
```

Autoridad de ejecución:

| Componente | Responsabilidad V2 |
| --- | --- |
| Luna | Intérprete principal, sin cambios |
| State Engine | Estado aceptado, sin cambios |
| capability / availability | Autoridad de ejecución, sin cambios |
| Registro pasivo V2 | Sólo observación y auditoría |

## Requisitos del registro pasivo

- No sustituye a Luna ni crea una segunda interpretación autoritativa.
- No modifica el State Engine ni el plan ejecutable.
- No realiza llamadas LLM por defecto.
- No agrega permisos ni capabilities.
- No bloquea ninguna capability.
- No convierte afirmaciones del usuario en hechos certificados.
- Permite auditar requisitos perdidos o pendientes.

## Contenido mínimo

- Ledger inmutable de mensajes originales con offsets y turn IDs; conserva el texto original completo, no el truncamiento del intérprete.
- Enlaces separados al proposal parseado, al estado aceptado/pendiente y al resultado del plan; no aplana solicitudes dentro del estado aceptado.
- Índice opcional de spans literales y facet ya explícitos. Lo desconocido permanece sin clasificar, nunca "cubierto".
- Distinciones explícitas: `USER_REQUESTED`, `USER_ASSERTED_UNVERIFIED`, `REPRESENTED_BY_BASELINE`, `NOT_EVALUATED`.
- Una etiqueta de cobertura exige evidencia; no es permiso de ejecución, ni certificación de hecho, ni veto.

## Prohibiciones

- Escribir en State Engine.
- Cambiar el plan.
- Habilitar capabilities.
- Bloquear la ejecución por presencia de facet extra.
- Presentar una respuesta parcial como respuesta completa sin señalar los facet no resueltos.

## Presupuesto propuesto

- Llamadas LLM adicionales: 0.
- Overhead local p95 ≤ 50 ms y ≤ 2 % del p95 baseline, con almacenamiento acotado.

Son presupuestos propuestos, no resultados observados. Relajarlos exige un experimento de beneficio/costo separado.

## Compuertas objetivas

`authorization.authorize(candidate, gold_status)` aplica precondiciones duras y compuertas de comportamiento:

| Compuerta | Criterio |
| --- | --- |
| `independent_gold` | `gold_status == CERTIFIED` |
| `frozen_baseline` | baseline congelado |
| `literal_preservation` | 100 % |
| `no_new_authorizations` | 0 |
| `no_new_blocks` | 0 |
| `accepted_state_unchanged` | 0 |
| `request_set_exact_not_regressed` | ≥ baseline |
| `request_recall_not_regressed` | ≥ baseline |
| `no_assertion_certification` | 0 |
| `no_extra_llm_calls` | 0 |
| `overhead_budget` | p95 ≤ 50 ms y ≤ 2 % |

Cualquier fallo de precondición devuelve `INSUFFICIENT_EVIDENCE`. Cualquier fallo de comportamiento devuelve `REJECT`. Sólo todas las compuertas satisfechas devuelven `AUTHORIZE`.

## Criterios de rechazo explícito

- Cualquier autorización nueva, aunque el benchmark de requests mejore.
- Cualquier bloqueo nuevo de un plan previamente válido (7/7 controles simples; 80/80 planes congelados como invariante de laboratorio, no como permiso productivo).
- Cualquier pérdida entre los 96 turnos baseline-exactos.
- Cualquier afirmación del usuario certificada.
- Cualquier dependencia del registro pasivo en el plan ejecutable.