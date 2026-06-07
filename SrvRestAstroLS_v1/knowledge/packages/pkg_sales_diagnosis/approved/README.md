# Documentos Aprobados — pkg_sales_diagnosis

Este directorio contiene los documentos fuente validados y listos para ingesta por el worker `knowledge_ingestion_worker`.

`approved/` no es un lugar para ideas preliminares. Un documento aprobado debe tener evidencia suficiente, alcance claro y límites explícitos. Si una capacidad es solo oportunidad, hipótesis o línea futura, debe permanecer en `drafts/` hasta que exista validación suficiente o debe clasificarse de forma conservadora en su metadata.

## Áreas de conocimiento

| Carpeta | area_key | Descripción |
|---------|----------|-------------|
| `ventas/` | `ventas` | Procesos de venta, guías de producto, argumentación comercial |
| `automatizaciones/` | `automatizaciones` | Automatización de procesos, diagnóstico de factibilidad |
| `scoring/` | `scoring` | Modelos de scoring, ponderación, criterios de factibilidad |
| `seguridad/` | `seguridad` | Políticas de seguridad, privacidad, compliance |
| `integraciones/` | `integraciones` | APIs, conectores, integraciones con terceros |
| `industrias/` | `industrias` | Verticales de industria, casos de uso específicos |
| `objeciones/` | `objeciones` | Manejo de objeciones comerciales y técnicas |
| `glosario/` | `glosario` | Términos, definiciones, acrónimos del dominio |

## Reglas

- Todo documento DEBE tener front-matter YAML completo.
- El `area_key` en el front-matter DEBE coincidir con el nombre de la carpeta.
- Los `access_tags` DEBEN ser válidos según `_metadata/access-tags.yaml`.
- `evidence_level` DEBE ser `validated_by_source`, `validated_by_pilot` o `validated_by_production`. No promover documentos con `hypothesis`.
- `commercial_status` DEBE indicar si el contenido es `sellable_pilot`, `sellable_service`, `core_offer`, `future_package` o `not_offered`. No usar `exploratory` en `approved/` salvo que el documento sea una política explícita de límite o descarte.
- `implementation_status` DEBE reflejar el estado real: `not_implemented`, `prototype`, `pilot_done`, `production_client`, `paused` o `deprecated`.
- `service_maturity` DEBE usar una de estas etiquetas: `CORE_VALIDADO`, `PILOTO_VALIDADO`, `OPORTUNIDAD`, `PAQUETE_FUTURO`, `NO_OFRECER_AUN`.
- `offer_decision` DEBE distinguir entre `automatable`, `sellable_now`, `pilot`, `future_opportunity` y `human_review_required`.
- `evidence_sources`, `validation_context`, `last_validated_at`, `validated_by`, `risk_level` y `approval_notes` DEBEN estar completos antes de aprobar.
- `related_pilots` y `related_clients` son opcionales, pero DEBEN existir como lista vacía (`[]`) cuando no apliquen o no puedan divulgarse.
- El asistente no debe convertir una oportunidad no validada en una promesa comercial. Los documentos con `OPORTUNIDAD`, `PAQUETE_FUTURO` o `NO_OFRECER_AUN` solo deben usarse para orientar conversación, marcar límites o derivar a evaluación humana.
- Los documentos en `approved/` son la fuente canónica. Las exportaciones PDF en `exports/` son derivadas.
- Usar `drafts/document-template.md` como punto de partida para nuevos documentos.

## Criterios mínimos de aprobación

Antes de mover un documento desde `drafts/` a `approved/`, verificar:

- La fuente principal de evidencia está identificada y es defendible.
- El alcance indica qué cubre y qué no cubre.
- Los límites comerciales están documentados.
- El estado de implementación no exagera la capacidad real.
- La decisión de oferta separa automatizable, vendible hoy, piloto, oportunidad futura y revisión humana.
- La clasificación de madurez distingue core, piloto, oportunidad, paquete futuro o no ofrecer.
- No contiene datos sensibles, secretos ni datos de clientes reales sin anonimizar.

## Validación inicial Team360.live

Team360.live es el primer cliente/proyecto interno de prueba para este paquete. Los aprendizajes provenientes de la home pública de Team360 o del uso interno deben tratarse como insumo de curaduría, no como conocimiento aprobado automático.

El flujo recomendado para aprobar contenido es: prueba, aprendizaje, curaduría, update y nueva prueba. En la primera etapa, los documentos curados más un flujo controlado de carga/update son suficientes; una interfaz completa de administración de knowledge queda para una fase posterior.
