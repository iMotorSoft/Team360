# Documentos Aprobados — pkg_sales_diagnosis

Este directorio contiene los documentos fuente validados y listos para ingesta por el worker `knowledge_ingestion_worker`.

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
- Los documentos en `approved/` son la fuente canónica. Las exportaciones PDF en `exports/` son derivadas.
- Usar `drafts/document-template.md` como punto de partida para nuevos documentos.
