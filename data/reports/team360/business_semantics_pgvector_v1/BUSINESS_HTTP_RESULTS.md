# Prueba empresarial HTTP DEV

Se ejecutó el adapter HTTP DEV existente: identidad telefónica PG → MessageDispatcher → handler → resolver → Luna real → State Engine → RBAC/capabilities → Foundation cuando corresponde. Sin transporte WhatsApp ni deploy.

## Resultados reales

Los significados pendientes se conocen, pero no se inventan operaciones o cifras. [Validación automatizada](validation_results.json) verifica contenido, métricas y número de ejecuciones.

| Preguntas | Resultado |
| --- | --- |
| Farmacia, menona, importar, deudas, perdidas | Definición y límites correctos, committed true, refs persistidas, cero Foundation. |
| Parafraseo de negocios presupuestados | Candidato vectorial lost_opportunities; no se afirma pérdida confirmada ni cálculo disponible. |
| Seis casos de canales/vendedores | Definiciones/relaciones recuperadas; cero importes o clasificación retrospectiva inventados. Comparación recupera ambos canales. |
| Calenta genérico | Aclaración de presentación/intención, sin imponer farmacia/menona como producto. |
| Últimas ventas Calenta | Nueve códigos comerciales localizados, líneas reales del 23/09/2026; circuito existente intacto. |
| Buscá Calenta → ventas de esos productos | Product Search persistido → ItemCodes reales → Sales Query; una capability por turno disponible. |
| Mayo 2026 | Facturación 8.761.459,22; NC 209.380,03; neto 8.552.079,19 Bs. DocTotal, no neto por producto. |
| Junio 2026 | Facturación 10.033.501,02; NC 270.007,35; neto 9.763.493,67 Bs. |
| Últimas facturas, ranking | Resultados reales del scope registrado, fuente CURRENT/snapshot 1408. |
| Última fecha | Fallo limit 1 detectado y preservado; corrida correctiva verifica cobertura hasta 24/09/2026. |
| Concepto inexistente | Aclaración, ninguna definición inventada ni ejecución; observación mínima pendiente. |
| Menona → mayo → nueva consulta mayo | Refinamiento sigue bloqueado por concepto pendiente; NEW_QUERY global explícita vuelve a facturación real. |
| Nueva conversación y reinicio propio | Farmacia recuperada automáticamente desde PG, sin configuración de sesión. |

Evidencia final: [27 turnos](http_final/http_results.json). R04 se sustituye **para evaluación**, no borrando el fallo, por [3 turnos correctivos](http_coverage_fix/http_results.json). Corridas exploratorias anteriores: [inicial](http/http_results.json), [follow-up](http_followup/http_results.json).

## Comandos reproducibles

El harness reutiliza arranque/shutdown y configuración privada del adapter existente, servidor loopback temporal y un token aleatorio por ejecución; no expone token ni teléfono en el reporte.

```bash
export TEAM360_ENV=dev TEAM360_BUSINESS_SEMANTICS=1
# Exportar alias/dimensión/revisión y calibración según EMBEDDING_CONFIGURATION.md.
uv run python -m modules.telchi.assistant.tests.runtime_http.business_semantics --output ../../data/reports/team360/business_semantics_pgvector_v1/http_new_run
uv run python -m modules.telchi.assistant.tests.runtime_http.business_semantics --only R04 --output ../../data/reports/team360/business_semantics_pgvector_v1/http_coverage_new_run
```

Servicios ajenos no se reiniciaron. Se reiniciaron únicamente hijos creados por el harness; lifecycle de servidores cerrados al final. La regresión posterior al fix reutiliza las otras preguntas porque el cambio documental está limitado a la pregunta literal R04; tests focalizados verifican consumidores no afectados.

## Límite de cierre

No se declara BUSINESS_RUNTIME_PASS para importar, deudas, ventas perdidas o canales todavía no calculables. Conocer su significado es una garantía distinta.

HTTP con segundo usuario comercial autorizado y segundo tenant real queda pendiente; no se impersonó al administrador ni se le añadieron grants para forzar PASS. Tampoco se certifica WhatsApp/Evolution outbound.
